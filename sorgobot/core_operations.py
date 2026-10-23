"""Core operations using actual local runtime state and Linux services."""
import asyncio
import copy
import datetime as dt
import random
import socket
from .core import ActionError,expand
from .core_services import Signals
from .catalog import ConfigStore
from .action_controls import changed_state

QUOTE_FIELDS=('quote','quoteGame','quoteId','quotePlatform','quoteTime','quoteTimestamp','quoteUser','quoteUserId')

def quote_operation(engine,node,args):
    kind=node['type'];store=engine.state;quotes=store.get('core:quotes',[])
    if kind==90113:args['quoteCount']=len(quotes);return None
    for key in QUOTE_FIELDS:args.pop(key,None)
    if kind==90110:
        text=node.get('text','').strip()
        if not text:raise ActionError('Zitattext fehlt')
        identity=store.get('core:quoteNextId',1);stamp=dt.datetime.now().astimezone()
        quote={'quote':text,'quoteId':identity,'quoteGame':args.get('currentGame',args.get('game',store.get('currentGame',''))),'quotePlatform':args.get('platform','twitch'),'quoteTime':stamp.strftime('%x'),'quoteTimestamp':stamp.isoformat(),'quoteUser':args.get('user',args.get('userName','')),'quoteUserId':args.get('userId','')}
        quotes.append(quote);store.set('core:quoteNextId',identity+1);store.set('core:quotes',quotes);args.update(quote,success=True);return 90203
    if kind==90112 and node.get('selection')=='random':quote=random.choice(quotes) if quotes else None
    else:
        try:identity=int(node.get('quoteId',''))
        except (ValueError,TypeError):raise ActionError('Zitat-ID muss eine Zahl sein') from None
        quote=next((q for q in quotes if q['quoteId']==identity),None)
    args['success']=quote is not None
    if quote is None:return None
    args.update(quote)
    if kind==90111:
        store.set('core:quotes',[q for q in quotes if q['quoteId']!=quote['quoteId']]);return 90204
    return 90254 if kind==90112 else None

async def operation(engine,node,args):
    kind=node['type']
    if kind in (90105,90106):
        if kind==90106 and not node.get('userId'):raise ActionError('Nutzer-ID ist erforderlich')
        from .core_events import set_global
        set_global(engine,node.get('variableName',''),persisted=node.get('persisted',True),delete=True,user=node.get('userId') if kind==90106 else None,platform=node.get('platform','twitch'))
    elif kind in (90170,90171):
        services=engine.services;target=next((g for g in services.config['userGroups'] if g['id']==node.get('groupId')),None)
        if target is None:raise ActionError('Gruppe nicht gefunden')
        user=node.get('user','').strip().casefold()
        if not user:raise ActionError('Nutzername fehlt')
        users=list(target.get('users',[]))
        if kind==90170 and user not in users:users.append(user)
        if kind==90171:users=[u for u in users if u.casefold()!=user]
        services.set_entry('userGroups',target['id'],{'users':users})
    elif kind==90172:
        await engine.studio.connections.send(node.get('connectionId',''),str(node.get('text','')))
    elif kind in (90110,90111,90112,90113):
        event=quote_operation(engine,node,args)
        if event and getattr(engine,'dispatcher',None):await engine.dispatcher.event(event,args)
    elif kind in (90120,90121):
        signals=getattr(engine,'signals',None)
        if signals is None:signals=engine.signals=Signals()
        name=node.get('signalName','').strip()
        if not name:raise ActionError('Signalname fehlt')
        if kind==90120:
            payload=copy.deepcopy(args) if node.get('includeArguments') else {}
            extra=node.get('arguments',{})
            if not isinstance(extra,dict):raise ActionError('Signal-Arguments müssen ein JSON-Objekt sein')
            payload.update({k:expand(v,args) for k,v in extra.items()});signals.send(name,payload,node.get('queue',False))
        else:
            timeout=float(node.get('timeout') or 30000);timeout=timeout if 0<timeout<=30000 else 30000
            try:payload=await signals.wait(name,timeout/1000)
            except TimeoutError:args['signalTimeout']=True;return
            for key,value in payload.items():
                if node.get('overwrite',True) or key not in args:args[key]=value
            args.update(signalTimeout=False,signalName=name,hasResult=bool(payload))
    elif kind==90130:
        from .timer_control import resolve,set_enabled
        timer=resolve(engine,node.get('timerId'),legacy=True)
        if timer is None:raise ActionError('Timer nicht gefunden')
        set_enabled(engine,timer,changed_state(timer.get('enabled',True),node.get('state')))
    elif kind==90131:
        action=engine.actions.get(node.get('actionId'))
        target=next((t for t in action.get('triggers',[]) if t['id']==node.get('triggerId')),None) if action else None
        if target is None:raise ActionError('Trigger nicht gefunden')
        target['enabled']=changed_state(target.get('enabled',True),node.get('state'))
    elif kind==90132:
        name=expand(node.get('eventName',''),args) if node.get('useArgs') else node.get('eventName','')
        if not name.strip():raise ActionError('Eventname fehlt')
        dispatcher=getattr(engine,'dispatcher',None)
        if not dispatcher:raise ActionError('Trigger-Laufzeit fehlt')
        await dispatcher.event(90202,dict(args,eventName=name),eventName=name)
    elif kind in (90100,90133,90134,90135):
        services=getattr(engine,'services',None)
        if not services:raise ActionError('Core-Laufzeit fehlt')
        section,key={90100:('fileTails','fileTailId'),90133:('userGroups','groupId'),90134:('voiceCommands','voiceCommandId'),90135:('voiceCommands','voiceCommandId')}[kind]
        target=next((x for x in services.config[section] if x['id']==node.get(key)),None)
        if target is None:raise ActionError('Zieleintrag nicht gefunden')
        if kind==90133:changes={'users':[]}
        elif kind==90134:
            if node.get('actionId') not in engine.actions:raise ActionError('Zielaktion nicht gefunden')
            if not node.get('command','').strip():raise ActionError('Voice-Command-Text fehlt')
            changes={'command':node['command'],'actionId':node['actionId']}
        else:changes={'enabled':changed_state(target.get('enabled',True),node.get('state'))}
        services.set_entry(section,target['id'],changes)
    elif kind in (90101,90102):
        if kind==90101:
            from .core_events import set_global
            for name in list(engine.session_globals):set_global(engine,name,persisted=False,delete=True)
        else:
            platform=node.get('platform','All')
            for key in list(engine.user_session_globals):
                if platform=='All' or key[0]==platform:
                    from .core_events import set_global
                    set_global(engine,key[2],persisted=False,delete=True,user=key[1],platform=key[0])
    elif kind in (90103,90104):
        user=node.get('userId','');name=node.get('variableName','');platform=node.get('platform','twitch')
        if not user or not name:raise ActionError('Nutzer-ID und Variablenname sind erforderlich')
        key=(platform,user,name)
        if kind==90103:
            from .core_events import set_global
            set_global(engine,name,node.get('value',''),node.get('persisted',False),user=user,platform=platform)
        elif node.get('persisted'):
            import json
            args[node.get('destinationVariable','value')]=engine.state.get('core:user:'+json.dumps(key),node.get('defaultValue',''))
        else:args[node.get('destinationVariable','value')]=engine.user_session_globals.get(key,node.get('defaultValue',''))
    elif kind==90140:
        host=node.get('host','127.0.0.1');port=int(node.get('port',0));payload=str(node.get('text','')).encode()
        if not 1<=port<=65535 or len(payload)>65507:raise ActionError('Ungültiger UDP-Port oder zu große Nachricht')
        if engine.io.dry_run:engine.io.trace('udp',host=host,port=port,simulated=True);return
        def send():
            with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET,socket.SO_BROADCAST,1);sock.settimeout(3);sock.sendto(payload,(host,port))
        await asyncio.to_thread(send)
    elif kind in (90141,90142,90143,90144,90145,90146,90150,90151,90152):
        from .linux_core_io import output
        await output(engine,node,args)
    elif kind==90160:
        callback=getattr(engine.io,'request_input',None)
        if callback is None:raise ActionError('Get Input benötigt die native Desktop-Oberfläche')
        text,accepted=await callback(node)
        args['success']=accepted
        if accepted:
            from .core_logic import typed
            args[node.get('resultVariable','inputResult')]=typed(text,node.get('autoType',False))
    else:raise ActionError('Unbekannte Core-Unteraktion')
