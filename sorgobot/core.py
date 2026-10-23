from __future__ import annotations

import asyncio
import contextvars
import copy
import time
import uuid
from zoneinfo import ZoneInfo
import datetime as dt
import json
import random
import re
import sqlite3
from contextlib import nullcontext
from pathlib import Path


class ActionError(RuntimeError):
    pass


class StopAction(Exception):
    pass


def walk(nodes):
    for node in nodes:
        yield node
        yield from walk(node.get('subActions', []))


class State:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute('CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS variable_writes (key TEXT PRIMARY KEY, last_write TEXT, is_global INTEGER NOT NULL DEFAULT 0)')

    def get(self, key, default=None):
        row = self.db.execute('SELECT value FROM kv WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set(self, key, value):
        encoded=json.dumps(value,allow_nan=False)
        with nullcontext() if self.db.in_transaction else self.db:
            self.db.execute('INSERT OR REPLACE INTO kv VALUES (?,?)', (key, encoded))
            self.db.execute('INSERT INTO variable_writes(key,last_write) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET last_write=excluded.last_write',(key,dt.datetime.now(dt.timezone.utc).isoformat()))


class RenderedText(str):
    """A rendered field stays literal through downstream adapter expansion."""

PARSE_CONTEXT=contextvars.ContextVar('native_parse_context',default=(None,False))

def expand(value, args):
    if not isinstance(value,str) or isinstance(value,RenderedText):return value
    from .original_values import render
    engine,original=PARSE_CONTEXT.get()
    return RenderedText(render(value,args,engine,preserve_unknown=original))


def condition(node, args, engine=None):
    from .core_logic import resolve, equal, compare
    op = node['operation']
    # Existing imported actions retain the pre-migration case/whitespace rules.
    legacy = 'autoType' not in node
    value = resolve(node.get('input', ''), args, engine)
    expected = resolve(node.get('value', ''), args, engine)
    auto = node.get('autoType', False)
    if op == 0 and legacy:
        return str(value).casefold() == str(expected).casefold()
    if op in (0, 1, 7, 8):
        result = equal(value, expected, auto, op in (7, 8) or (legacy and op == 0))
        return not result if op in (1, 8) else result
    if op == 2:
        return str(expected) in str(value)
    if op == 3:
        pattern = str(expected).replace('^(?i)', '(?i)^')
        # Translate the two documented .NET named-group spellings.
        pattern = re.sub(r"\(\?'([A-Za-z_]\w*)'", r'(?P<\1>', pattern)
        pattern = re.sub(r'\(\?<([A-Za-z_]\w*)>', r'(?P<\1>', pattern)
        try:
            match = re.search(pattern, '' if value is None else str(value))
        except re.error as exc:
            raise ActionError(f'Ungültiger regulärer Ausdruck: {exc}') from exc
        if match:
            args['match.count'] = len(match.groups()) + 1
            for index in range(len(match.groups()) + 1):
                args[f'match[{index}]'] = match.group(index) or ''
            args.update({key: val or '' for key, val in match.groupdict().items()})
        return match is not None
    if op in (4, 5):
        return compare(value, expected, auto, False, op == 4)
    if op == 6:
        return str(node['input']).casefold() not in {str(k).casefold() for k in args}
    if op == 9:
        return value is None or (str(value).strip() == '' if legacy else value == '')
    raise ActionError(f'Unbekannter Vergleich: {op}')


class Engine:
    def __init__(self, document, state, adapter, custom):
        self.document = document
        self.actions = {a['id']: a for a in document['actions']}
        self.state, self.io, self.custom = state, adapter, custom
        self.session_globals = {}
        self.user_session_globals = {}
        self.csharp_session_globals = self.session_globals
        self.locks = {}
        self.stack = contextvars.ContextVar('action_stack', default=())
        self.history = []
        self.pending = {}
        self.running = {}
        self.queue_gates = {}
        self.completed_counts = {}
        self.blocking_queues = {q['id']: q.get('blocking', False) for q in document.get('queues', [])}

    def queue_pause(self,identity,paused):
        gate=self.queue_gates.setdefault(identity,asyncio.Event())
        gate.clear() if paused else gate.set()
        for q in self.document.get('queues',[]):
            if q['id']==identity:q['paused']=paused
        if identity is None:self.document['paused']=paused

    def queue_gate(self,identity):
        if identity not in self.queue_gates:
            paused=next((q.get('paused',False) for q in self.document.get('queues',[]) if q['id']==identity),self.document.get('paused',False) if identity is None else False)
            self.queue_pause(identity,paused)
        return self.queue_gates[identity]

    def clear_queue(self,identity):
        for record in list(self.pending.values()):
            if record['queueId']==identity:record['task'].cancel()

    async def run(self, identity, args=None):
        if getattr(getattr(self,'studio',None),'closing',False):raise ActionError('Laufzeit wird beendet')
        action=self.actions.get(identity) or next((a for a in self.actions.values() if a['name']==identity),None)
        if action is None:raise ActionError('Aktion nicht gefunden')
        if not action.get('enabled',True):raise ActionError('Aktion ist deaktiviert')
        if action.get('migrationBlock'):raise ActionError(action['migrationBlock'])
        stack=self.stack.get()
        if action['id'] in stack or len(stack)>=20:raise ActionError('Zyklischer Aktionsaufruf')
        token=self.stack.set(stack+(action['id'],));context=copy.deepcopy(args or {})
        context.setdefault('broadcastUser',self.io.config.get('channel',''))
        now=lambda:dt.datetime.now(ZoneInfo(self.io.config.get('timezone','Europe/Berlin'))).isoformat(timespec='milliseconds')
        queue=action.get('queue')
        record={'id':str(uuid.uuid4()),'actionId':action['id'],'name':action['name'],'queueId':queue,
                'queue':next((q['name'] for q in self.document.get('queues',[]) if q['id']==queue),'Default'),
                'queuedAt':now(),'startedAt':'','completedAt':'','duration':0,'argumentsQueued':{},
                'argumentsAfter':{},'excludeHistory':action.get('excludeHistory',False),'task':asyncio.current_task()}
        from .action_context import stamp
        stamp(context,record);record['argumentsQueued']=copy.deepcopy(context)
        self.pending[record['id']]=record;started=None;status='ok';error=''
        if getattr(self,'diagnostics',None):self.diagnostics.write('action_queued',action=action['name'],actionId=action['id'],executionId=record['id'],queue=record['queue'])
        async def execute():
            nonlocal started
            if not stack and not action.get('alwaysRun'):await self.queue_gate(queue).wait()
            self.pending.pop(record['id'],None);self.running[record['id']]=record
            record['startedAt']=now();started=time.perf_counter()
            if getattr(self,'diagnostics',None):self.diagnostics.write('action_start',action=action['name'],actionId=action['id'],executionId=record['id'],queue=record['queue'])
            from .websocket_core_events import action as notify_action
            notify_action(self,'Action',record)
            from .core_logic import DEPTH
            loop_token=DEPTH.set(0)
            try:
                if action.get('cameraEffect'):await self.custom.camera_effect(action,context)
                else:await self.action_nodes(action,context)
            finally:DEPTH.reset(loop_token)
        try:
            if not stack and not action.get('alwaysRun'):await self.queue_gate(queue).wait()
            if stack or action.get('concurrent') or not self.blocking_queues.get(queue,self.document.get('blocking',False)):await execute()
            else:
                async with self.locks.setdefault(queue,asyncio.Lock()):await execute()
        except StopAction as exc:
            status='stopped';error=str(exc) or 'Unteraktion hat die Action beendet.';record['failedStep']=getattr(exc,'subaction_details',{})
        except asyncio.CancelledError:status='cancelled';raise
        except Exception as exc:
            status='error';error=str(exc);record['failedStep']=getattr(exc,'subaction_details',{});raise
        finally:
            self.pending.pop(record['id'],None);self.running.pop(record['id'],None)
            record['completedAt']=now();record['duration']=round((time.perf_counter()-started)*1000,3) if started is not None else 0
            record['argumentsAfter']=copy.deepcopy(context);record.pop('task',None)
            self.completed_counts[queue]=self.completed_counts.get(queue,0)+1
            self.record(action,status,error,record);self.stack.reset(token)
            if started is not None:
                from .websocket_core_events import action as notify_action
                notify_action(self,'ActionCompleted',record,status)
        return context

    async def action_nodes(self,action,args):
        children=[n for n in action['subActions'] if n.get('enabled',True)]
        if action.get('random') and children:
            weights=[max(0,float(n.get('weight',1))) for n in children]
            children=random.choices(children,weights=weights if any(weights) else None,k=1)
        if action.get('concurrent'):
            tasks=[asyncio.create_task(self.nodes([node],args,action)) for node in children]
            try:await asyncio.gather(*tasks)
            finally:
                for task in tasks:
                    if not task.done():task.cancel()
                await asyncio.gather(*tasks,return_exceptions=True)
        else:await self.nodes(children,args,action)

    def record(self, action, status, error='',execution=None):
        if getattr(self,'diagnostics',None):
            item=execution or {};step=item.get('failedStep',{})
            self.diagnostics.write('action_complete',action=action['name'],actionId=action['id'],executionId=item.get('id'),status=status,error=error,durationMs=item.get('duration'),step=step.get('name'),stepType=step.get('type'),stepId=step.get('id'))
        if action.get('excludeHistory'):return
        self.history.append({**(execution or {}),'time':dt.datetime.now().astimezone().isoformat(timespec='seconds'),'name':action['name'],'status':status,'error':error})
        self.history[:] = self.history[-150:]

    async def nodes(self, nodes, args, action):
        for n in nodes:
            if not n.get('enabled', True):
                continue
            parse_token=PARSE_CONTEXT.set((self,bool(n.get('_original') or n.get('_originalSemantics'))))
            try:
                t = n['type']
                from .websocket_core_events import subaction as notify_subaction
                notify_subaction(self,action,n)
                output_field={10:'text',39:'text',602:'message',15:'title',91803:'message',91804:'message'}.get(t)
                resolved={}
                if output_field:
                    from .ai_variables import fill
                    resolved[output_field]=await fill(n.get(output_field,''),args,self.custom,limit=500 if t in (10,91803,91804) else 2000)
                get = lambda k, default='': resolved[k] if k in resolved else expand(n.get(k, default), args)
                if n.get('_originalSemantics'):
                    from .original_runtime import operation as imported_operation
                    await imported_operation(self,{**n,**resolved},args);continue
                if t == 124:
                    raise StopAction()
                elif t == 1009:
                    continue
                elif t in (99900, 99901, 99902):
                    children = [x for x in n.get('subActions', []) if x.get('enabled', True)]
                    if n.get('random') and children:
                        weights = [max(0, x.get('weight', 0)) for x in children]
                        children = random.choices(children, weights=weights if any(weights) else None, k=1)
                    await self.nodes(children, args, action)
                elif t == 120:
                    branch_type = 99901 if condition(n, args, self) else 99902
                    await self.nodes([b for b in n['subActions'] if b['type'] == branch_type], args, action)
                elif t == 1002:
                    if action.get('concurrent'):continue
                    delay = float(get('value') or 0)
                    if n.get('random'):
                        delay = random.uniform(delay, float(get('maxValue') or delay))
                    await self.io.wait(delay / 1000)
                elif t == 4:
                    from .action_context import merge_child
                    args.update(merge_child(args,await self.run(n['actionId'],args)))
                elif t == 123:
                    from .core_logic import typed
                    args[n['variableName']] = typed(get('value'),n.get('autoType',False))
                elif t == 122:
                    from .core_events import set_global
                    from .core_logic import typed
                    set_global(self,n['variableName'],typed(get('value'),n.get('autoType',False)),n.get('persisted',True))
                elif t == 121:
                    args[n['destinationVariable']] = self.state.get(n['variableName'], n.get('defaultValue')) if n.get('persisted',True) else self.session_globals.get(n['variableName'],n.get('defaultValue'))
                elif t == 99999:
                    await self.custom.execute(n['id'], action, args)
                elif t in (90004,90007,90008):
                    from .ai_action import generate
                    args[n.get('resultVariable','kiAntwort')] = await generate(self.custom,n,args,lambda value:expand(value,args))
                elif t in (90021,90022,90023,90024,90025):
                    from .command_actions import command_operation
                    command_operation(self,{k:expand(v,args) for k,v in n.items()},args)
                elif t in (90026,90027,90028,90029):
                    from .action_controls import action_operation
                    action_operation(self,{k:expand(v,args) for k,v in n.items()},args)
                elif t in (90050,90051,90052):
                    from .queue_controls import queue_operation
                    queue_operation(self,{k:expand(v,args) for k,v in n.items()})
                elif t in (90161,90162,90163,90164):
                    from .core_logic import logic
                    await logic(self,n,args,action)
                elif 90100<=t<=90160 or t in (90170,90171,90172):
                    from .core_operations import operation
                    # Custom event useArgs controls its own expansion.
                    values={k:(v if t==90132 and k=='eventName' else expand(v,args)) for k,v in n.items()}
                    await operation(self,values,args)
                elif t in (91700,91701):
                    from .twitch_user_selection import operation
                    await operation(self,n,args)
                elif 91500<=t<=91502:
                    from .twitch_user_groups import operation
                    await operation(self,n,args)
                elif 90400<=t<=90417:
                    from .points import operation
                    operation(self,n,args)
                elif t==90165:raise ActionError('Case muss innerhalb eines Switch liegen')
                elif t in (90060,90061):
                    from .csharp import execute
                    await execute(self,n,args)
                elif t==90020:
                    from .game_detection import detect_local
                    result=await asyncio.to_thread(detect_local,self.io.root)
                    args.update(result);args.update(game=result['detectedGame'],currentGame=result['detectedGame'])
                    args[n.get('resultVariable','detectedGame')]=result['detectedGame']
                    self.state.set('currentGame',result['detectedGame'])
                elif t == 90010:
                    low,high=int(get('minimum',0)),int(get('maximum',100))
                    if low>high:raise ActionError('Minimum darf nicht größer als Maximum sein')
                    args[n.get('resultVariable','randomNumber')]=random.randint(low,high)
                elif t == 90011:
                    self.io.trace('log',text=get('text'),level=n.get('logLevel','info'))
                elif t in (90012,90013,90014,90015,90016,90017):
                    path=Path(get('path')).expanduser()
                    if not str(get('path')).strip():raise ActionError('Dateipfad fehlt')
                    if not path.is_absolute():path=self.io.root/path
                    if t==90012:result=path.is_file()
                    elif t==90013:result=path.is_dir()
                    elif t==90017:
                        if self.io.dry_run:self.io.trace('file_write',path=str(path),simulated=True)
                        else:
                            def write():
                                with path.open('a' if n.get('append',True) else 'w',encoding='utf-8') as file:file.write(str(get('text')))
                            await asyncio.to_thread(write)
                        continue
                    else:
                        lines=(await asyncio.to_thread(path.read_text,encoding='utf-8-sig')).splitlines()
                        if t==90014:result=lines
                        elif t==90015:result=random.choice(lines) if lines else ''
                        else:
                            line=int(get('line',0))
                            if not 0<=line<len(lines):raise ActionError('Zeilennummer außerhalb der Datei (erste Zeile: 0)')
                            result=lines[line]
                    args[n.get('resultVariable','fileResult')]=result
                elif t in (90018,90019):
                    target=self.actions.get(get('actionId'))
                    if target is None:raise ActionError('Zielaktion nicht gefunden')
                    if t==90018:
                        args['actionState']=target.get('enabled',True)
                        args[n.get('resultVariable','actionEnabled')]=args['actionState']
                    else:
                        from .action_controls import changed_state
                        target['enabled']=changed_state(target.get('enabled',True),n.get('state',True))
                elif t == 90006:
                    await self.custom.camera_effect({'cameraEffect':get('effect'),'cameraDuration':int(get('duration',300)),'sceneName':get('sceneName') or '-Overlay','sourceName':get('sourceName') or 'Kamera','announce':n.get('announce',True)},args)
                else:
                    if t==48:args['filedatetime']=dt.datetime.now().astimezone().isoformat()
                    await self.io.step(t, {k: v if k=='raw' and n.get('_originalObs')==46 else resolved[k] if k in resolved else expand(v,args) for k,v in n.items()},args)

            except Exception as exc:
                if not hasattr(exc,'subaction_details'):
                    from .catalog import STEPS
                    exc.subaction_details={'id':n.get('id',''),'type':n.get('type'),'name':n.get('name') or STEPS.get(n.get('type'),('Typ '+str(n.get('type')),{}))[0]}
                raise
            finally:
                PARSE_CONTEXT.reset(parse_token)

class Dispatcher:
    def __init__(self, engine, commands):
        self.engine, self.commands = engine, commands
        engine.dispatcher = self
        self.cooldowns = {}
        self.command_counts={c['id']:engine.state.get('command_counter:'+c['id'],0) if c.get('persistCounter') else 0 for c in commands}
        self.command_user_counts={c['id']:engine.state.get('command_user_counters:'+c['id'],{}) if c.get('persistUserCounter') else {} for c in commands}
        closed=engine.state.get('first_words_started_at',engine.state.get('first_words_closed_at'))
        hours=float(engine.io.config.get('first_words_reset_hours',12))
        reset=closed is not None and hours>0 and time.time()-closed>=hours*3600
        self.first_users = set() if reset else set(engine.state.get('first_words_users',[]) or [])
        if reset:engine.state.set('first_words_users',[])
        engine.state.set('first_words_started_at',time.time())
        self.message_count = 0

    async def event(self, trigger_type, args, **filters):
        from .websocket_core_events import forward as notify_core
        notify_core(self.engine,trigger_type,args)
        from .websocket_notifications import quote as notify_quote
        notify_quote(self.engine,trigger_type,args)
        from .websocket_twitch_events import forward as notify_platform
        notify_platform(self.engine,trigger_type,args)
        from .youtube_events import forward as notify_youtube
        notify_youtube(self.engine,trigger_type,args)
        if trigger_type==133:
            from .service_management import credit_roles
            args=await credit_roles(self.engine,args)
        from .csharp_core_services import capture
        try:capture(self.engine,trigger_type,args)
        except (ActionError,OSError,TypeError,ValueError):self.engine.io.trace('credits_capture_error',message='Ereignis konnte nicht in den Credits gespeichert werden')
        matched=[]
        for a in self.engine.actions.values():
            if not a.get('enabled', True):
                continue
            for t in a.get('triggers', []):
                if not t.get('enabled', True) or t['type'] != trigger_type:
                    continue
                remaining_filters=filters
                if 'obsConnection' in filters:
                    pool=getattr(self.engine.io,'obs_pool',None)
                    if pool:
                        try:
                            if filters['obsConnection'] not in pool.targets(t.get('obsConnection','default'),respect_force=False):continue
                        except ActionError:continue
                    remaining_filters={k:v for k,v in filters.items() if k!='obsConnection'}
                from .twitch_goals_bits import matches as goals_bits_matches
                if not goals_bits_matches(trigger_type,t,args):continue
                from .twitch_shared_chat import matches as shared_matches
                if not shared_matches(trigger_type,t,args):continue
                from .twitch_expansion_events import matches as expansion_matches
                if not expansion_matches(trigger_type,t,args):continue
                from .twitch_channel import matches as channel_matches
                if not channel_matches(trigger_type,t,args):continue
                from .twitch_hype_train import matches as hype_matches
                if not hype_matches(trigger_type,t,args):continue
                from .twitch_ads_raids_events import matches as broadcast_matches
                if not broadcast_matches(trigger_type,t,args):continue
                from .twitch_subscription_events import matches as subscription_matches
                if not subscription_matches(trigger_type,t,args):continue
                from .linux_audio import matches as audio_matches
                if not audio_matches(trigger_type,t,args):continue
                from .streamdeck_bridge import matches as streamdeck_matches
                if not streamdeck_matches(trigger_type,t,args):continue
                from .linux_inputs import matches
                if not matches(trigger_type,t,args):continue
                if trigger_type in (90214,90215) and t.get('processName'):
                    from .game_detection import process_name
                    if process_name(t['processName']) not in args.get('processNames',[]):continue
                from .original_triggers import filter_matches,event_matches
                if not event_matches(t,args):continue
                if any(not filter_matches(t,k,v) for k, v in remaining_filters.items()):
                    continue
                matched.append((a,t))
        # Original exclusions reference other matching trigger IDs. Determine
        # the complete match set first so behavior is independent of row order.
        from .original_graph import canonical
        identities={canonical(t.get('id')) for _,t in matched if canonical(t.get('id'))}
        executed=set()
        for a,t in matched:
            own=canonical(t.get('id'))
            if a['id'] in executed or any(canonical(identity) in identities-{own} for identity in t.get('exclusions',[])):continue
            executed.add(a['id'])
            try:
                from .event_context import arguments as event_arguments
                from .original_triggers import arguments as trigger_arguments
                await self.engine.run(a['id'], event_arguments(trigger_type,trigger_arguments(t,args)))
            except (ActionError, OSError, ValueError):
                pass  # Engine records the error; subsequent independent actions still run.

    async def chat(self, args):
        private=args.get('isWhisper',False)
        command_only=private or args.get('commandType','message')!='message'
        if args.get('userName'):
            from .users import store
            platform=args.get('userType',args.get('platform','twitch'))
            store(self.engine).remember(platform,args['userName'],args.get('userId',''),args.get('user',''),active=not command_only)
        if not command_only:self.message_count += 1
        services=getattr(self.engine,'services',None)
        if services:
            from .users import members
            current={'platform':str(args.get('userType',args.get('platform','twitch'))).casefold(),'userName':(str(args.get('userName','')) if str(args.get('userType',args.get('platform','twitch'))).casefold()=='youtube' else str(args.get('userName','')).casefold()),'userId':str(args.get('userId',''))}
            memberships=[g['name'] for g in services.config['userGroups'] if members(g,[current])]
            args=dict(args,roles=list(dict.fromkeys([*args.get('roles',[]),*memberships])))
        text = args.get('message', '')
        user = args.get('userName', '').lower()
        source_platform=str(args.get('userType',args.get('platform','twitch'))).casefold()
        if source_platform=='twitch' and user in self.engine.io.config.get('bots', []):
            return
        first_key=('youtube:'+str(args.get('youtubeChannelId',''))+':id:'+str(args.get('userId') or args.get('userName',''))) if source_platform=='youtube' else user
        if not command_only and first_key not in self.first_users:
            self.first_users.add(first_key)
            self.engine.state.set('first_words_users',sorted(self.first_users))
            await self.event(4016 if source_platform=='youtube' else 120, args)
        matched = False
        for command in self.commands:
            if command.get('migrationBlock') or not command.get('enabled', True):
                continue
            source=str(args.get('commandSource',args.get('userType',args.get('platform','twitch')))).casefold();command_type=args.get('commandType','message')
            from .command_state import source_enabled
            if not source_enabled(command.get('sources',{}),args):continue
            if command.get('ignoreInternalMessages',True) and args.get('isInternal',False):continue
            bot_login=self.engine.io.config.get('twitch_bot_login','')
            if command.get('ignoreBotAccount',True) and ((source=='twitch' and bot_login and user==bot_login.lower()) or (source=='youtube' and args.get('isBot') is True)):continue
            from .command_actions import has_permission
            roles = args.get('roles', [])
            if not has_permission(command,args):continue
            # Streamer.bot command mode 1 is regex.
            flags = 0 if command.get('caseSensitive') else re.I
            pattern = command.get('command', '')
            if command.get('mode', 0) == 1:
                match = re.search(pattern.replace('(?i)', ''), text, flags)
            else:
                aliases = pattern.splitlines()
                location=command.get('location',0)
                search = re.search if location==2 else re.fullmatch if location==1 else re.match
                match = next((m for alias in aliases if alias and (m := search(re.escape(alias)+(r'(?:\s|$)' if location!=1 else ''),text,flags))),None)
            if not match:
                continue
            now = asyncio.get_running_loop().time()
            cid = command['id']
            raw = text[match.end():].strip()
            context = dict(args, rawInput=raw, input0=raw.split()[0].lstrip('@') if raw else '',commandId=cid,commandName=command.get('name',''),command=match.group(0).strip(),commandSource=source,commandType=command_type)
            from .command_state import cooldown_key,usage
            user_key=cooldown_key(context)
            global_left=max(0,self.cooldowns.get((cid,'*'),0)-now);user_left=max(0,self.cooldowns.get((cid,user_key),0)-now)
            if 'Broadcaster' not in roles and max(global_left,user_left)>0:
                await self.event(402,dict(context,cooldownLeft=max(global_left,user_left),globalCooldownLeft=global_left,userCooldownLeft=user_left),commandId=cid)
                matched=True
                continue
            total,user_count=usage(self).record(command,context)
            self.cooldowns[cid, '*'] = now + command.get('globalCooldown', 0)
            self.cooldowns[cid, user_key] = now + command.get('userCooldown', 0)
            context.update(counter=total,userCounter=user_count)
            await self.event(401, context, commandId=cid)
            matched = True
        if not matched and not command_only:
            await self.event(133, args)
