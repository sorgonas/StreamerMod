"""Native Qt Widgets application. No WebView, Electron or browser required."""
from __future__ import annotations

import argparse
import asyncio
import copy
import json
import sys
import uuid
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer, Signal, QLockFile
from PySide6.QtGui import QAction, QPixmap
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QFormLayout, QSplitter, QTabWidget, QTreeWidget, QTreeWidgetItem, QTableWidget,
    QTableWidgetItem, QPushButton, QLineEdit, QPlainTextEdit, QComboBox, QCheckBox,
    QLabel, QDialog, QDialogButtonBox, QMessageBox, QInputDialog, QHeaderView, QScrollArea, QKeySequenceEdit)

from .app import Studio
from .catalog import ConfigStore, PROMPTS, STEPS, TRIGGERS, new_action, new_step, validate_action
from .core import ActionError

ROLE = Qt.ItemDataRole.UserRole


class Runtime(QThread):
    ready = Signal()
    input_requested = Signal(str,object)
    result = Signal(str, object)
    error = Signal(str)

    def __init__(self, root, live=False, obs_test=False):
        super().__init__()
        self.root, self.live = root, live
        self.obs_test = obs_test
        self.loop = None
        self.studio = None
        self.stopping = False
        self.booted = False
        self.input_requests = {}

    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self.boot())
            self.booted = True
            self.ready.emit()
            if not self.stopping:self.loop.run_forever()
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            async def cancel_pending():
                if self.studio:self.studio.closing=True
                pending=[t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
                for task in pending:task.cancel()
                await asyncio.gather(*pending,return_exceptions=True)
            self.loop.run_until_complete(cancel_pending())
            if self.studio and hasattr(self.studio,'session'):
                self.loop.run_until_complete(self.studio.close(None))
            if getattr(self,'runner',None):
                self.loop.run_until_complete(self.runner.cleanup())
            self.loop.close()

    async def boot(self):
        self.studio=Studio(self.root,self.live,self.obs_test)
        await self.studio.start(None)
        self.studio.io.request_input=self.request_input
        self.twitch_auth=self.studio.twitch_auth;self.studio.auth_error=self.error.emit
        # The desktop talks directly to the runtime. HTTP is only needed in live
        # mode for OBS browser sources and the existing voice integration.
        self.runner=None
        if self.live:
            from aiohttp import web
            app=self.studio.application()
            app.on_startup.clear();app.on_cleanup.clear()
            self.runner=web.AppRunner(app)
            await self.runner.setup()
            await web.TCPSite(self.runner,'127.0.0.1',8766).start()

    async def request_input(self,node):
        identity=uuid.uuid4().hex;future=asyncio.get_running_loop().create_future();self.input_requests[identity]=future
        self.input_requested.emit(identity,node)
        try:return await future
        finally:self.input_requests.pop(identity,None)
    def input_reply(self,identity,text,accepted):
        def finish():
            future=self.input_requests.get(identity)
            if future and not future.done():future.set_result((text,accepted))
        if self.loop and not self.loop.is_closed():self.loop.call_soon_threadsafe(finish)

    def submit(self, kind, **data):
        if self.stopping or not self.booted or not self.loop or self.loop.is_closed() or not self.studio: return
        future=asyncio.run_coroutine_threadsafe(self.dispatch(kind,data),self.loop)
        def complete(f):
            try: self.result.emit(kind,f.result())
            except Exception as exc:
                if getattr(self.studio,'diagnostics',None):self.studio.diagnostics.write('runtime_error',operation=kind,error=str(exc))
                step=getattr(exc,'subaction_details',{})
                self.error.emit((str(step['name'])+': ' if step else '')+str(exc))
        future.add_done_callback(complete)

    async def dispatch(self, kind, data):
        s=self.studio
        if kind in ('services_get','services_save','services_start','services_control','services_clear_log'):
            if kind=='services_start':
                await s.services.save(data['section'],data['value']);return await s.services.control(data['section'],True)
            if kind=='services_save':return await s.services.save(data['section'],data['value'])
            if kind=='services_control':return await s.services.control(data['section'],data['running'])
            if kind=='services_clear_log':
                section=data['section']
                if section not in s.services.logs:raise ActionError('Unbekanntes Protokoll')
                s.services.logs[section].clear()
            return s.services.status()
        if kind=='speech_cancel_model':
            await s.services.speech.cancel_model();return s.services.status()
        if kind=='speech_install_model':
            if 'value' in data:await s.services.save('voice',data['value'])
            await s.services.speech.install_model();return s.services.status()
        if kind=='services_ws_password':return s.services.websocket_password()
        if kind=='services_ws_password_set':return await s.services.set_websocket_password(data['password'])
        if kind=='services_token':return s.token
        if kind=='remote_status':return s.remote.status()
        if kind=='remote_save':return await s.remote.save(data)
        if kind=='remote_token':return s.remote.config['token']
        if kind in ('quotes_get','quotes_add','quotes_edit','quotes_delete'):
            from .csharp_quotes import quotes
            from .core_operations import quote_operation
            rows=copy.deepcopy(quotes(s.engine))
            if kind!='quotes_get':
                if kind=='quotes_add':
                    values=data['value'];text=values.get('quote','').strip()
                    if not text or len(text)>10000:raise ActionError('Zitattext fehlt oder ist zu lang')
                    args={k:values.get(k,'') for k in ('user','userId','platform','currentGame')}
                    event=quote_operation(s.engine,{'type':90110,'text':text},args)
                    if event:await s.dispatcher.event(event,args)
                else:
                    current=next((r for r in rows if r['quoteId']==data['original']['quoteId']),None)
                    if current!=data['original']:raise ActionError('Zitat wurde inzwischen geändert; bitte neu laden')
                    if kind=='quotes_delete':
                        args={};event=quote_operation(s.engine,{'type':90111,'quoteId':current['quoteId']},args)
                        if event:await s.dispatcher.event(event,args)
                    else:
                        value=data['value'];text=value.get('quote','').strip()
                        if not text or len(text)>10000:raise ActionError('Zitattext fehlt oder ist zu lang')
                        current.update(quote=text,quoteUser=str(value.get('user',''))[:200],quoteUserId=str(value.get('userId',''))[:200],quotePlatform=str(value.get('platform',''))[:50],quoteGame=str(value.get('currentGame',''))[:500])
                        s.state.set('core:quotes',rows)
                rows=copy.deepcopy(quotes(s.engine))
            return rows
        if kind.startswith('youtube_'):
            youtube=s.youtube
            try:
                if kind.startswith('youtube_bot_'):
                    auth=youtube.bot_auth
                    auth.client=dict(youtube.auth.client)
                    if kind=='youtube_bot_login':return await auth.begin()
                    elif kind=='youtube_bot_login_poll':return await auth.poll()
                    elif kind=='youtube_bot_login_cancel':await auth.cancel();return {'state':'cancelled'}
                    elif kind=='youtube_bot_forget':await auth.forget()
                    else:raise ValueError('YouTube bot request')
                elif kind=='youtube_setup':
                    if youtube.bot_auth.account.get('refresh_token') and data.get('value',{}).get('installed',{}).get('client_id')!=youtube.auth.client.get('client_id'):raise ActionError('Vor einem Clientwechsel auch den YouTube-Bot abmelden')
                    await youtube.auth.configure(data['value']);youtube.bot_auth.client=dict(youtube.auth.client)
                elif kind=='youtube_login':await youtube.stop();return await youtube.auth.begin()
                elif kind=='youtube_login_poll':
                    result=await youtube.auth.poll()
                    if result.get('state')=='connected':
                        await youtube.stop();youtube.messages.clear();youtube.seen.clear();youtube.page_token='';youtube.session_chat_id='';await youtube.connect()
                    return result
                elif kind=='youtube_login_cancel':await youtube.auth.cancel();return {'state':'cancelled'}
                elif kind=='youtube_forget':await youtube.stop();await youtube.auth.forget();youtube.messages.clear()
                elif kind=='youtube_broadcasts':await youtube.refresh_broadcasts()
                elif kind=='youtube_configure':return await youtube.configure(data.get('broadcast',''),data.get('auto',True))
                elif kind=='youtube_connect':return await youtube.connect()
                elif kind=='youtube_disconnect':await youtube.stop()
                elif kind!='youtube_status':raise ValueError('YouTube request')
                return youtube.status()
            except (ActionError,ValueError,OSError) as exc:return {'state':'error','message':str(exc)}
        if kind=='status':
            from .queue_controls import queue_states
            from .chat_events import snapshot as chat_events
            from .youtube_events import combined_messages
            from .csharp_core_services import snapshot as code_triggers
            return {'connectionStates':{identity:{'connected':s.connections.connected(item),'listening':s.connections.listening(item),'error':s.connections.failed.get(identity,'')} for identity,item in s.connections.definitions().items()},'midiOpen':list(getattr(getattr(s,'device_listeners',None),'active',set())),'midiDiagnostics':{'errors':dict(getattr(getattr(s,'device_listeners',None),'errors',{})),'messages':list(getattr(getattr(s,'device_listeners',None),'messages',[]))},'services':s.services.status(),'linuxAudio':s.audio.status(),'streamDeck':s.streamdeck.status(),'streamerModRemote':s.remote.status(),'viewerPresence':s.twitch.features.presence_status(),'youtube':s.youtube.status() if getattr(s,'youtube',None) else {},'viewers':copy.deepcopy(list(s.twitch.viewers.values()))+(s.youtube.active_viewers() if getattr(s,'youtube',None) else []),'events':chat_events(s),'queueCounts':dict(s.engine.completed_counts),'pending':[copy.deepcopy({k:v for k,v in record.items() if k!='task'}) for record in s.engine.pending.values() if not record.get('excludeHistory')],
                    'running':[copy.deepcopy({k:v for k,v in record.items() if k!='task'}) for record in s.engine.running.values() if not record.get('excludeHistory')],
                    'history':copy.deepcopy(s.engine.history[-150:]),'effects':copy.deepcopy(s.io.effects[-40:]),
                    'queueStates':queue_states(s.engine),
                    'commandStates':[(c['id'],c.get('enabled',True)) for c in s.dispatcher.commands],
                    'timerStates':[(t['id'],t.get('enabled',True)) for t in s.timer_definitions],
                    'coreStates':copy.deepcopy(s.core_services.config),'codeTriggers':code_triggers(s.engine),
                    'obsConnections':s.io.obs_pool.statuses(),'obs':s.io.obs.status,'twitch':s.twitch.status,'twitchAccounts':self.twitch_auth.account_states(),'twitchConnections':s.twitch.connections.snapshot(),'twitchBot':s.twitch_bot.status,'twitchBotSubscriptions':copy.deepcopy(s.twitch_bot.subscription_status),
                    'twitchPyramidCurrent':s.twitch.features.pyramids.snapshot(),'twitchHypeTrain':copy.deepcopy(s.twitch.hype_snapshot),'twitchSubscriptionStates':copy.deepcopy(s.twitch.subscription_status),'twitchEventsActive':self.live,'chat':combined_messages(s,1000)}
        if kind=='credits_get':
            from .csharp_core_services import credits_snapshot
            return credits_snapshot(s.engine)
        if kind in ('credits_add','credits_reset'):
            from .csharp_core_services import rpc,credits_snapshot
            if kind=='credits_reset':await rpc(s.engine,'credits',['reset'])
            else:
                section=data['section'].strip();name=data['name'].strip()
                if not section or not name or len(section)>200 or len(name)>1000:raise ActionError('Credits-Bereich oder Name ist ungültig.')
                await rpc(s.engine,'credits',['add',section,{'name':name}])
            return credits_snapshot(s.engine)
        if kind=='audio_snapshot':
            await s.audio.refresh();return s.audio.status()
        if kind=='known_users':
            from .users import store
            rows=store(s.engine).known(data.get('platform',''),window=data.get('window',300))
            return {'users':rows[:1000],'total':len(rows)}
        if kind=='user_register':
            from .users import store
            store(s.engine).remember(data['platform'],data['user'],data.get('userId',''),data.get('displayName',''),now=0)
            return True
        if kind=='points_accounts':
            from .points import store
            points=store(s.engine);points.definition(data['definition'])
            return {'definition':data['definition'],'accounts':points.leaderboard(data['definition'],1000)}
        if kind=='points_set':
            from .points import operation
            args={};operation(s.engine,{'type':90414,'pointDefinitionId':data['definition'],'user':data['user'],'platform':data['platform'],'amount':data['amount']},args)
            return args
        if kind=='camera_preview':return await s.camera_preview()
        if kind=='chat_dock_url':
            from .chat_dock import url
            return url(s,data.get('events',False))
        if kind=='chat_dock_sync':
            from .chat_dock import sync
            sync(ConfigStore(self.root));return True
        if kind=='chat_quick_action':
            from .chat_events import execute
            return execute(s,ConfigStore(self.root),data)
        if kind=='voice_text':
            await s.core_services.voice(data.get('text',''));return True
        if kind=='run':
            raw=data.get('input','')
            arguments=await s.engine.run(data['id'],dict(rawInput=raw,message=raw,input0=raw.split()[0].lstrip('@') if raw else '',
                user=s.config.get('twitch_login') or s.config.get('channel',''),userName=s.config.get('twitch_login') or s.config.get('channel',''),userLogin=s.config.get('twitch_login') or s.config.get('channel',''),roles=['Broadcaster']))
            record=next((r for r in reversed(s.engine.history) if r.get('id')==arguments.get('runningActionId')),None)
            return {'arguments':arguments,'executionStatus':record['status'] if record else 'finished'}
        if kind=='csharp_format':
            from .csharp_refs import format_code
            try:return {'code':await format_code(self.root,data.get('code',''),data.get('indent',4)),'success':True,'requestId':data.get('requestId')}
            except (ActionError,OSError,TimeoutError) as exc:return {'message':str(exc),'success':False,'requestId':data.get('requestId')}
        if kind=='csharp_find_refs':
            from .csharp_refs import find_references
            try:return {**(await find_references(self.root,data.get('code',''),data.get('references',[]))),'requestId':data.get('requestId')}
            except (ActionError,OSError,TimeoutError) as exc:return {'message':str(exc),'diagnostics':[str(exc)],'requestId':data.get('requestId')}
        if kind=='csharp_compile':
            from .csharp import compile_code,prepare
            try:
                if data.get('codeId'):
                    dll=await prepare(s.engine,dict(id=data['codeId'],code=data.get('code',''),references=data.get('references',[]),timeout=data.get('timeout',30)))
                else:dll=await compile_code(self.root,data.get('code',''),data.get('references',[]))
                return {'message':(dll.parent.parent/'compile.log').read_text() if (dll.parent.parent/'compile.log').exists() else 'Compiled successfully.','success':True,'requestId':data.get('requestId')}
            except (ActionError,OSError,TimeoutError) as exc:return {'message':str(exc),'success':False,'requestId':data.get('requestId')}
        if kind=='clear_history':s.engine.history.clear();return True
        if kind=='detect_game':
            from .game_detection import detect_local
            return await asyncio.to_thread(detect_local,self.root)
        if kind=='first_words_reset':
            s.dispatcher.first_users.clear();s.state.set('first_words_users',[]);return True
        if kind=='queue_pause':s.engine.queue_pause(data.get('id'),data['paused']);return True
        if kind=='queue_clear':s.engine.clear_queue(data.get('id'));return True
        if kind=='requeue':return await s.engine.run(data['id'],data.get('arguments',{}))
        if kind in ('twitch_login','twitch_login_poll','twitch_login_cancel','twitch_validate','twitch_forget'):
            import aiohttp
            bot=bool(data.get('bot'))
            try:
                if kind=='twitch_login':return await self.twitch_auth.begin(bot,data.get('features',[]))
                if kind=='twitch_login_cancel':self.twitch_auth.cancel(bot);return {'bot':bot,'state':'cancelled'}
                if kind=='twitch_forget':
                    self.twitch_auth.cancel(bot)
                    if not bot:self.twitch_auth.authenticated_identity=None
                    cfg=ConfigStore(self.root).read('local.json')
                    for key in (*self.twitch_auth.keys(bot),'twitch_bot_scopes' if bot else 'twitch_scopes'):cfg.pop(key,None)
                    # update() alone would retain removed credentials in memory.
                    for key in self.twitch_auth.keys(bot):s.config.pop(key,None)
                    ConfigStore(self.root).update('local.json',{key:'' for key in (*self.twitch_auth.keys(bot),'twitch_bot_scopes' if bot else 'twitch_scopes')});await self.dispatch('reload',{})
                    return {'bot':bot,'state':'forgotten'}
                result=await (self.twitch_auth.poll(bot) if kind=='twitch_login_poll' else self.twitch_auth.validate(bot))
                if result.get('state')=='connected':await self.restart_twitch()
                return result
            except (ActionError,aiohttp.ClientError,OSError,asyncio.TimeoutError) as exc:
                self.twitch_auth.cancel(bot)
                return {'bot':bot,'state':'error','message':str(exc) if isinstance(exc,ActionError) else 'Twitch-Anmeldedienst momentan nicht erreichbar. Erneut versuchen.'}
            except (KeyError,TypeError,ValueError):
                self.twitch_auth.cancel(bot)
                return {'bot':bot,'state':'error','message':'Unerwartete Antwort vom Twitch-Anmeldedienst. Erneut versuchen.'}
        if kind=='twitch_channel_tools':
            from .twitch_channel_tools import ChannelTools
            try:
                service=ChannelTools(s.io);op=data.get('operation','info')
                if op=='info':result=await service.info()
                else:
                    if not self.live:raise ActionError('Kanaländerungen sind nur im Live-Modus verfügbar')
                    result=await service.change(op,**{k:v for k,v in data.items() if k in ('tag','tags','state','description')})
                return {'success':True,'result':result,'requestId':data.get('requestId')}
            except (ActionError,OSError,ValueError,KeyError,TypeError) as exc:return {'success':False,'message':str(exc) if isinstance(exc,ActionError) else 'Kanalverwaltungsaktion fehlgeschlagen','requestId':data.get('requestId')}
        if kind=='twitch_custom_power_ups':
            from .twitch_goals_bits import PowerUpList
            try:return {'success':True,'result':await PowerUpList(s.io).read(),'requestId':data.get('requestId')}
            except (ActionError,OSError,ValueError,KeyError,TypeError) as exc:return {'success':False,'message':str(exc) if isinstance(exc,ActionError) else 'Custom-Power-up-Abfrage fehlgeschlagen','requestId':data.get('requestId')}
        if kind=='twitch_channel':
            from .twitch_channel import Channel
            try:return {'success':True,'result':await Channel(s.io).read(data.get('operation','stream')),'requestId':data.get('requestId')}
            except (ActionError,OSError,ValueError,KeyError,TypeError) as exc:return {'success':False,'message':str(exc) if isinstance(exc,ActionError) else 'Kanalabfrage fehlgeschlagen','requestId':data.get('requestId')}
        if kind=='twitch_sub_counter':
            from .twitch_sub_counter import SubCounter
            try:
                service=SubCounter(s.io);op=data.get('operation','read')
                if op=='read':result=service.get()
                elif op=='latest':result=service.latest()
                elif op=='save':
                    if not self.live:raise ActionError('Sub Counter kann nur im Live-Modus verändert werden')
                    result=service.save(count=data.get('count'),rollover=data['rollover'],enabled=data['enabled'])
                else:raise ActionError('Unbekannte Sub-Counter-Anfrage')
                return {'success':True,'result':result,'preview':not self.live,'requestId':data.get('requestId')}
            except (ActionError,OSError,ValueError,KeyError,TypeError) as exc:return {'success':False,'message':str(exc) if isinstance(exc,ActionError) else 'Sub-Counter-Anfrage fehlgeschlagen','requestId':data.get('requestId')}
        if kind=='twitch_pyramids':
            from .twitch_pyramids import PyramidStats
            try:return {'success':True,'result':{**PyramidStats(s.io).summary(),'current':s.twitch.features.pyramids.snapshot(),'preview':not self.live},'requestId':data.get('requestId')}
            except (ActionError,OSError,ValueError,KeyError,TypeError) as exc:return {'success':False,'message':str(exc) if isinstance(exc,ActionError) else 'Pyramiden-Übersicht konnte nicht geladen werden','requestId':data.get('requestId')}
        if kind=='twitch_hype_train':
            from .twitch_hype_train import HypeTrain
            try:return {'success':True,'result':await HypeTrain(s.io).status(),'requestId':data.get('requestId')}
            except (ActionError,OSError,ValueError,KeyError,TypeError) as exc:
                return {'success':False,'message':str(exc) if isinstance(exc,ActionError) else 'Hype-Train-Abfrage fehlgeschlagen','requestId':data.get('requestId')}
        if kind=='twitch_broadcast_tools':
            from .twitch_ads_raids import BroadcastTools
            try:
                service=BroadcastTools(s.io);op=data.get('operation','schedule')
                if op=='schedule':result=await service.schedule()
                else:
                    if not self.live:raise ActionError('Werbung und Raids sind nur im Live-Modus verfügbar')
                    if op=='commercial':result=await service.commercial(data['duration'])
                    elif op=='snooze':result=await service.snooze()
                    elif op=='raid_start':result=await service.raid_start(data['userLogin'])
                    elif op=='raid_cancel':result=await service.raid_cancel()
                    else:raise ActionError('Unbekannte Ads-/Raid-Anfrage')
                return {'success':True,'result':result,'requestId':data.get('requestId')}
            except (ActionError,OSError,ValueError,KeyError,TypeError) as exc:
                return {'success':False,'message':str(exc) if isinstance(exc,ActionError) else 'Ads-/Raid-Anfrage fehlgeschlagen','requestId':data.get('requestId')}
        if kind=='twitch_subscribers':
            from .twitch_subscriptions import Subscribers
            try:
                result=await Subscribers(s.io).list(data.get('cursor',''))
                return {'success':True,'result':result,'requestId':data.get('requestId')}
            except (ActionError,OSError,ValueError,KeyError,TypeError) as exc:
                return {'success':False,'message':str(exc) if isinstance(exc,ActionError) else 'Abonnentenabfrage fehlgeschlagen','requestId':data.get('requestId')}
        if kind=='twitch_moderation':
            from .twitch_moderation import Moderation
            try:
                service=Moderation(s.io);op=data.get('operation','list')
                if op=='list':result=await service.list(data.get('listKind','bans'),data.get('cursor',''))
                else:
                    if not self.live:raise ActionError('Echte Moderation ist nur im Live-Modus verfügbar')
                    result=await service.change(op,data['userLogin'],data.get('reason',''),data.get('duration',60))
                return {'success':True,'result':result,'requestId':data.get('requestId')}
            except (ActionError,OSError,ValueError,KeyError,TypeError) as exc:
                return {'success':False,'message':str(exc) if isinstance(exc,ActionError) else 'Moderationsanfrage fehlgeschlagen','requestId':data.get('requestId')}
        if kind=='twitch_votes':
            from .twitch_votes import Votes
            try:
                service=Votes(s.io,data['voteKind']);op=data.get('operation','list')
                if op=='list':result=await service.list(data.get('cursor',''))
                else:
                    if not self.live:raise ActionError('Echte Twitch-Abstimmungen sind nur im Live-Modus verfügbar')
                    if op=='create':result=await service.create(data['title'],data['options'],data['duration'],data.get('points',0))
                    elif op=='change':result=await service.change(data['id'],data['status'],data.get('winner',''))
                    else:raise ActionError('Unbekannte Abstimmungsanfrage')
                return {'success':True,'result':result,'requestId':data.get('requestId'),'voteKind':data['voteKind']}
            except (ActionError,OSError,ValueError,KeyError,TypeError) as exc:
                return {'success':False,'message':str(exc) if isinstance(exc,ActionError) else 'Abstimmungsanfrage fehlgeschlagen','requestId':data.get('requestId'),'voteKind':data.get('voteKind')}
        if kind.startswith('twitch_reward'):
            from .twitch_rewards import Rewards
            rewards=Rewards(s.io)
            try:
                if kind=='twitch_rewards':result=await rewards.list()
                elif kind=='twitch_reward_group':result=rewards.group(data['rewardId'],data['group'])
                else:
                    if not self.live:raise ActionError('Echte Reward-Verwaltung ist nur im Live-Modus verfügbar')
                    if kind=='twitch_reward_create':result=await rewards.create(data['payload'])
                    elif kind=='twitch_reward_update':result=await rewards.update(data['rewardId'],data['payload'])
                    elif kind=='twitch_reward_delete':result=await rewards.delete(data['rewardId'])
                    elif kind=='twitch_reward_redemptions':result=await rewards.redemptions(data['rewardId'],data.get('status','UNFULFILLED'),data.get('cursor',''))
                    elif kind=='twitch_reward_redeem':result=await rewards.redeem(data['rewardId'],data['redemptionId'],data['status'])
                    else:raise ActionError('Unbekannte Reward-Anfrage')
                return {'success':True,'result':result,'rewardId':data.get('rewardId'),'requestId':data.get('requestId')}
            except (ActionError,OSError,KeyError,ValueError,TypeError) as exc:
                return {'success':False,'message':str(exc) if isinstance(exc,ActionError) else 'Reward-Anfrage konnte nicht verarbeitet werden','requestId':data.get('requestId')}
        if kind=='test_trigger':
            if data.get('triggerId'):
                from .trigger_test import arguments
                store=ConfigStore(self.root);document=store.read('actions.json')
                action=next((a for a in document['actions'] if a['id']==data['id']),None)
                trigger=next((t for t in action.get('triggers',[]) if t['id']==data['triggerId']),None) if action else None
                if trigger is None:raise ActionError('Der ausgewählte Trigger existiert nicht mehr.')
                # Use the persisted action too, including an edit queued just before Test.
                s.engine.actions[action['id']]=action
                from .core_services import read_config
                values=arguments(trigger,store.read('commands.json')['commands'],store.read('timers.json'),s.config,read_config(self.root))
                return await s.engine.run(action['id'],values)
            return await s.engine.run(data['id'],data.get('arguments',{}))
        if kind=='obs_force':
            identity=data.get('connectionId')
            if identity and identity not in s.io.obs_pool.rows:raise ActionError('OBS-Verbindung fehlt')
            s.io.obs_pool.force=identity
            return {'obsConnections':s.io.obs_pool.statuses()}
        if kind in ('obs_connect','obs_disconnect'):
            s.config.update(ConfigStore(self.root).read('local.json'))
            await s.io.obs_pool.configure(s.config,s.obs_event if self.live else None)
            identity=data.get('connectionId','default')
            if kind=='obs_disconnect':await s.io.obs_pool.disconnect(identity)
            else:
                if not (self.live or self.obs_test):return {'status':'Vorschau: Verbindung wird nicht geöffnet','obsConnections':s.io.obs_pool.statuses()}
                client=s.io.obs_pool.connect(identity,s.spawn)
                try:await asyncio.wait_for(client.ready.wait(),6)
                except TimeoutError:raise ActionError('OBS-Verbindung fehlgeschlagen. Adresse und Passwort prüfen.') from None
            return {'status':s.io.obs_pool.clients[identity].status,'obsConnections':s.io.obs_pool.statuses()}
        if kind=='obs_info':
            client=s.io.obs_pool.clients.get(data.get('connectionId','default'))
            if client is None:raise ActionError('OBS-Verbindung fehlt')
            return await client.call('GetVersion') if client.ready.is_set() else {}
        if kind=='global_set':
            if not data['name'].strip():raise ActionError('Variablenname fehlt')
            from .core_events import set_global
            set_global(s.engine,data['name'],data['value'],True);return True
        if kind=='global_delete':
            from .core_events import set_global
            set_global(s.engine,data['name'],persisted=True,delete=True)
            return True
        if kind=='clipboard_changed':
            if self.live:s.engine.core_events.emit(90250,{'clipboardText':data['text'],'clipboardContent':data['text'],'clipboardTruncated':data.get('truncated',False),'rawInput':data['text']})
            return True
        if kind=='globals':
            return {key:json.loads(value) for key,value in s.state.db.execute('SELECT key,value FROM kv ORDER BY key')}
        if kind=='reload':
            store=ConfigStore(self.root)
            doc=store.read('actions.json')
            s.engine.document=doc;s.engine.actions={a['id']:a for a in doc['actions']}
            from .csharp import reconcile
            await reconcile(s.engine)
            s.engine.blocking_queues={q['id']:q.get('blocking',False) for q in doc.get('queues',[])}
            for queue in doc.get('queues',[]):s.engine.queue_pause(queue['id'],queue.get('paused',False))
            s.engine.queue_pause(None,doc.get('paused',False))
            s.dispatcher.commands=store.read('commands.json')['commands']
            s.timer_definitions=store.read('timers.json')
            s.timer_due.clear();s.core_services.reload()
            await s.services.refresh_voice()
            emote_before=tuple(s.config.get(k,True) for k in ('twitch_emotes_bttv','twitch_emotes_ffz','twitch_emotes_7tv'))
            previous=tuple(s.config.get(k) for k in ('twitch_client_id','twitch_token','broadcaster_id','twitch_bot_token','bot_id'))
            obs_before=copy.deepcopy(s.io.obs_pool.rows)
            s.config.update(store.read('local.json'))
            await s.io.obs_pool.configure(s.config,s.obs_event if self.live else None)
            if (self.live or self.obs_test) and obs_before!=s.io.obs_pool.rows:s.io.obs_pool.auto_connect(s.spawn)
            if self.live and s.twitch.status=='connected' and emote_before!=tuple(s.config.get(k,True) for k in ('twitch_emotes_bttv','twitch_emotes_ffz','twitch_emotes_7tv')):s.spawn(s.twitch.features.load_emotes())
            if previous!=tuple(s.config.get(k) for k in ('twitch_client_id','twitch_token','broadcaster_id','twitch_bot_token','bot_id')):await self.restart_twitch()
            if not s.config.get('twitch_token') and getattr(s,'twitch_task',None):
                s.twitch_task.cancel();await asyncio.gather(s.twitch_task,return_exceptions=True);s.twitch_task=None;s.twitch.status='offline'
            await s.configure_camera()
            s.config['prompts']=store.read('prompts.json')
            s.state.set('LLM_BEHAVIOR',s.config['prompts']['behavior'])
            return True
        if kind=='obs_scenes':
            return await s.io.obs_call('GetSceneList') if self.live or self.obs_test else {'scenes':[{'sceneName':'Gaming - Live'},{'sceneName':'_SteamPause'}]}
        if kind=='obs': return await s.io.obs_call(data['command'],**data.get('params',{}))
        if kind=='preview':
            if not (self.live or self.obs_test):return None
            scene=(await s.io.obs_call('GetCurrentProgramScene'))['currentProgramSceneName']
            return (await s.io.obs_call('GetSourceScreenshot',sourceName=scene,imageFormat='jpeg',imageWidth=640,imageCompressionQuality=60))['imageData']
        if kind=='chat_emotes':
            from .websocket_emotes import catalogue
            return await catalogue(s)
        if kind=='chat_send':
            from .chat_commands import send
            try:
                result=await send(s,data);return result if isinstance(result,dict) and 'success' in result else {'success':True}
            except (ActionError,OSError,ValueError) as exc:return {'success':False,'error':str(exc)}
        if kind=='chat_moderate':
            from .chat_operations import moderate
            return await moderate(s,data)
        if kind=='chat': return await s.io.send(data['message'])
        if kind=='ai_test': return await s.custom.llm('chat_response',data['text'],{},prompt_kind=data['promptKind'])
        raise ValueError('Unbekannte Desktop-Anfrage')

    async def restart_twitch(self):
        s=self.studio;task=getattr(s,'twitch_task',None)
        if task:task.cancel();await asyncio.gather(task,return_exceptions=True)
        bot_task=getattr(s,'twitch_bot_task',None)
        if bot_task:bot_task.cancel();await asyncio.gather(bot_task,return_exceptions=True)
        s.twitch_bot_task=None
        s.twitch_task=None;s.twitch.status='offline'
        if self.live and s.config.get('twitch_bot_token') and s.config.get('bot_id'):s.twitch_bot_task=s.spawn(s.twitch_bot.run())
        if self.live and s.config.get('twitch_token') and s.config.get('broadcaster_id'):
            s.twitch_task=s.spawn(s.twitch.run())

    def stop(self):
        self.stopping = True
        if self.loop and self.booted and not self.loop.is_closed() and self.isRunning(): self.loop.call_soon_threadsafe(self.loop.stop)
        return self.wait(15000)


def buttons(layout, labels):
    row=QHBoxLayout();layout.addLayout(row)
    output=[]
    for label,callback in labels:
        button=QPushButton(label);button.clicked.connect(callback);row.addWidget(button);output.append(button)
    row.addStretch()
    return output


def step_dialog(title,node,parent):
    if node.get('type') in (90060,90061):
        from .csharp_ui import CSharpDialog
        host=getattr(parent,'host',None) or parent
        if not hasattr(host,'runtime') and parent.parent():host=parent.parent()
        return CSharpDialog(node,host)
    return FieldsDialog(title,node,parent)


class FieldsDialog(QDialog):
    """Forms for ordinary fields; structured values stay inspectable as JSON."""
    def __init__(self,title,value,parent=None):
        super().__init__(parent);self.setWindowTitle(title);self.resize(650,530)
        self.value=copy.deepcopy(value);self.controls={}
        from .streamdeck_bridge import STEPS as DECK_STEPS,TRIGGERS as DECK_TRIGGERS
        if self.value.get('type')==90004:
            if 'autoContext' not in self.value and self.value.get('prompt'):self.value['promptKind']='__custom__'
            self.value.setdefault('promptKind','chat');self.value.setdefault('prompt','');self.value.setdefault('resultVariable','kiAntwort');self.value['autoContext']=True
        deck_kind=self.value.get('type');is_deck=deck_kind in DECK_STEPS or deck_kind in DECK_TRIGGERS
        if self.value.get('type')==91701:
            for key,default in (('groups',[]),('includeFrom',False)):self.value.setdefault(key,copy.deepcopy(default))
        if is_deck:
            for key,default in (DECK_STEPS.get(deck_kind) or DECK_TRIGGERS[deck_kind])[1].items():self.value.setdefault(key,copy.deepcopy(default))
        from .obs_connections import OBS_TYPES
        if self.value.get('type') in OBS_TYPES or self.value.get('type') in (14004,14005,14006,*range(90350,90367)):self.value.setdefault('obsConnection','default')
        if self.value.get('type') in (90018,90019,90021,90022,90023,90024,90025,90026,90027,90028,90029,90050,90051,90052):self.resize(596,330)
        layout=QVBoxLayout(self)
        hints=[]
        if any(self.value.get(field)==['none'] for field in self.value.get('_flagValues',[])):
            hints.append('Originalfilter: ["none"] bedeutet keine Auswahl. Eine leere Liste [] wählt alle Stufen beziehungsweise Monate.')
        if 94000<=self.value.get('type',0)<=94058:
            from .linux_audio_fields import HINT
            hints.append(HINT)
        if is_deck:
            from .streamdeck_fields import hint
            hints.append(hint(deck_kind,parent))
        if 91500<=self.value.get('type',0)<=91502:hints.append('Lokale Gruppen unter Core Services → User Groups anlegen. Twitch-Login oder %userName%, Gruppenname oder Variable. Add/Remove liefern addResult/removeResult; User in Group liefert inGroup und foundUser/Name/Id/Type. Vorschau verändert keine Gruppen. Bei Gruppen mit plattformübergreifenden alten Mitgliedern entfernt Remove nur Twitch.')
        if 91400<=self.value.get('type',0)<=91403:hints.append('Chatmodus: State true = On, false = Off. Follow-Dauer in Minuten (0–129600), Slow-Dauer in Sekunden (3–120). Leere Dauer nutzt den Twitch-Standard (Follow 0 Minuten, Slow 30 Sekunden); beim Abschalten wird sie nicht gesendet. Benötigt die gemeinsame Broadcaster-Freigabe unter Accounts. Vorschau verändert Twitch nicht.')
        if self.value.get('type') in (10,15,39,602):
            hints.extend([
                'Nutzer: %user% = Anzeigename · %userName% = Login · %userId% = Nutzer-ID',
                'Nachricht: %message% = vollständiger Chattext · %rawInput% = Text hinter dem Befehl · %input0% = erstes Wort daraus',
                'KI-Zusatztext: %kiAntwort% = Chat · %kiGeneral% = nur General',
                'KI-Ereignisse: %kiRaid%, %kiShoutout%, %kiRandom%, %kiFollow%',
                'KI-Clip: %kiClip% · KI-Titel: %kiTitel% = aktuelles Spiel/Kategorie, ohne Bild',
                'KI-Bild: Nur %kiSnapshot% benötigt zuvor einen Screenshot.',
                'KI-Variablen erzeugen fehlenden Text automatisch. General gilt immer; der passende Ereignis-Prompt ergänzt ihn. Andere Variablen sind vom Trigger abhängig.',
            ])
        elif not is_deck and any(key in self.value for key in ('text','message','prompt','input','value','content')):
            hints.append('Variablen: %user%, %userName%, %rawInput%, %input0%.')
        if self.value.get('type') in (90004,90007,90008):
            hints.append('Wähle einen gespeicherten Prompt aus KI → Prompts. General gilt zusätzlich. Ereignisdaten und Ergebnisse vorheriger Nutzerabfragen werden automatisch übergeben. Bei Benutzerdefiniert kannst du einen eigenen Prompt eintragen. Die Antwort steht nachfolgenden Unteraktionen als %kiAntwort% bzw. unter dem gewählten Variablennamen zur Verfügung. Anbieter, Server, Zugang und Modell stammen aus den zentralen KI-Einstellungen.')
        if 91800<=self.value.get('type',0)<=91806:hints.append('Twitch Chat: Message/Reply Id ist die echte Chat-ID (%msgId%), nicht die EventSub-Zustellungs-ID. Pin-Dauer: leer bis Streamende oder 30–1800 Sekunden. Vorschau sendet, löscht und pinnt nichts. Get Pinned benötigt einen gespeicherten echten Stand. Bot-Ankündigungen benötigen Bot-Recht und Moderatorrolle; kein stiller Konto-Wechsel.')
        if self.value.get('type')==91700:hints.append('Index ab 0 oder %variable%. Lädt Chatnutzer über Twitch und sortiert nach Login. Liefert presentUsersCount und presentUser/Name/Id/Type; außerhalb der Liste ist presentUser False. Vorschau verwendet gespeicherte echte Daten, keine aktuelle Anwesenheitsbestätigung.')
        if self.value.get('type')==91701:hints.append('Count oder %variable%. Zufällige Twitch-Nutzer ohne Wiederholung, maximal verfügbare Anzahl. Present Only: Chatnutzerliste; sonst lokal beobachtete bekannte Twitch-Nutzer. Liefert randomUser0/Name0/Id0/Type0 usw. und randomUsersCount. Vorschau fragt Twitch nicht ab.')
        if self.value.get('type')==91600:hints.append('Lädt das angemeldete Broadcaster-Konto: broadcastUser/Name/Id/Type, Affiliate/Partner und Profilinformationen. Vorschau verwendet ausschließlich gespeicherte echte Daten.')
        if self.value.get('type')==91601:hints.append('Broadcaster, auslösender User, From Input (%input0%) oder Variable mit Twitch-Login. Liefert teamId0/Name0/DisplayName0/BackgroundUrl0/BannerUrl0 usw., teamCount und _jsonTeamData. Vorschau nutzt gespeicherte Daten; keine Teams ist ein gültiges leeres Ergebnis.')
        if self.value.get('type')==90021:
            hints.append('Ergebnis: %'+str(self.value.get('resultVariable','commands'))+'% als Text und die gleichnamige Variable mit List als Liste. Ausgeschlossen: deaktivierte Befehle, Regex und Anywhere. Only Has Permission verwendet die Rollen und den Login aus dem Aktionskontext.')
        if self.value.get('type') in (90022,90023):
            hints.append('Enable, Disable oder Toggle. Im Live-Modus wird der Zustand gespeichert; in der Vorschau gilt er nur für die laufende Sitzung.')
        if self.value.get('type')==90024:
            hints.append('Ergebnis: %commandGroupState% = 0 Disabled, 1 Enabled, 2 Mixed; %commandsEnabled% und %commandsDisabled% enthalten die IDs.')
        if self.value.get('type')==90025:hints.append('Liefert %commandState% als true/false.')
        if self.value.get('type') in (90018,90019,90026,90027,90028,90029):hints.append('Aktionszustände und Gewichte gelten für die laufende Sitzung. Get Action Group State liefert %actionGroupState% (0 Disabled, 1 Enabled, 2 Mixed) sowie %actionsEnabled% und %actionsDisabled%. Gewichtungen wirken bei Random-Aktionen/-Gruppen.')
        if self.value.get('type') in (90050,90051,90052):hints.append('Clear entfernt nur wartende Aktionen. Bereits laufende Aktionen werden fortgesetzt. Pause/Blocking werden im Live-Modus gespeichert; in der Vorschau gelten sie nur für die laufende Sitzung.')
        if self.value.get('type') in (90214,90215):
            hints.append('Linux-Prozessname (z. B. obs oder Albion-Online). Leer = alle Prozesse. .exe-Namen von Wine/Proton werden mitberücksichtigt. Die Überwachung läuft automatisch im Live-Modus, sobald ein solcher Trigger aktiviert ist; bereits laufende Prozesse werden beim Start nicht erneut ausgelöst.')
        if self.value.get('type') in (90210,90211,90212,90213):
            hints.append('Watcher unter Core Services → File/Folder Watcher einrichten. Any berücksichtigt alle aktiven Watcher. Liefert changeType, fullPath und fileName; Renamed zusätzlich oldFilename und oldFullPath.')
        if self.value.get('type')==90006:
            hints.append('Lokalen Kameradienst unter Settings → Devices aktivieren. OBS-Szene und Browserquelle angeben; Browser-URL http://127.0.0.1:8766/camera. announce aktiviert optional die Chatnachricht. Die Bildvorschau benötigt kein Mikrofon.')
        if self.value.get('type')==90240:
            hints.append('Tastenkombination durch Drücken im Feld erfassen. Any nutzt das Wayland/X11-Desktop-Portal; KDE kann einen Freigabedialog anzeigen. Für ein bestimmtes evdev-Gerät dieses unter Core Services → Input Devices einrichten.')
        if self.value.get('type') in (90241,90242,90243,90244):
            hints.append('Eingabegeräte unter Core Services → Input Devices einrichten. Linux-Namen wie BTN_LEFT, BTN_SOUTH, ABS_X oder ABS_HAT0X. Leserechte für das ausgewählte Gerät erforderlich; Geräte werden nicht gesperrt.')
        if self.value.get('_originalMidiFilter')=='definition':hints.append('Original-MIDI-Ereignis: midiEventEnabled erhält dessen Aktivierung. Bei PatchChange, ChannelAfterTouch und PitchWheelChange prüft das Original Data1 als 0; für freie Auswahl Data1=-1. Bearbeitete Filter als Linux-JSON exportieren.')
        if self.value.get('type')==90245:
            hints.append('MIDI-Eingang unter Core Services → MIDI Inputs einrichten. commandCode leer, channel 0 und data1 -1 bedeuten Any. Beispiele: NoteOn, NoteOff, ControlChange. Liefert channel, noteNumber, velocity und rawMessage.')
        if self.value.get('type') in (90220,90221,90222,90223):
            hints.append('Variablenname leer = Any; Persisted Either/Yes/No. Liefert global.name, global.oldValue, global.newValue, global.persisted. Ein unveränderter Wert löst kein Update aus.')
        if self.value.get('type') in (90260,90261,90262,90263,90264,90265):
            hints.append('Verbindungen unter Core Services → WebSocket Connections einrichten. Client oder lokaler Server. Message liefert message/rawInput, connectionId und clientId.')
        if self.value.get('type')==90020:
            hints.append('Erkennt konfigurierte Spielprozesse. Ohne Treffer gilt die Rückfallkategorie (Standard: Just Chatting). Liefert %detectedGame%, %currentGame%, %game% und %gameDetected%. Zuordnungen unter Stream Apps → Game Detection.')
        if self.value.get('type')==30:
            hints.append('state: 0 = Quelle sichtbar, 1 = Quelle verborgen.')
        if 'operation' in self.value and 'input' in self.value:
            hints.append('Auto Type wandelt Zahlentexte und true/false um. Argument fehlt verwendet den Namen ohne %. Regex liefert match.count, match[index] und benannte Gruppen.')
            if 'autoType' not in self.value:hints.append('Importierter Altvergleich: Gleichheit ignoriert Groß-/Kleinschreibung; leer umfasst Leerzeichen.')
        if 90500<=self.value.get('type',0)<=90516:hints.append('Reward-ID oder %rewardId% aus dem Einlösungsereignis. Änderungen benötigen channel:manage:redemptions und einen mit dieser Twitch-Anwendung erstellten Reward. Reset to Original verwendet den ersten hier gespeicherten Stand. Gruppenbuchungen bei Twitch sind nicht atomar.')
        if self.value.get('type')==20 or 90700<=self.value.get('type',0)<=90706:hints.append('Twitch-Moderation: Benutzername oder %userName%. Timeout in Sekunden; 0 bedeutet dauerhafte Sperre. Untimeout entfernt ausschließlich zeitliche Sperren. Rollen: User, From Input (input0), Variable oder direkter userLogin. Automatische Wiedervergabe von Moderatorrechten nach Timeout ist noch nicht implementiert.')
        if self.value.get('type') in (90031,90032,90850,90851,90855):hints.append('tiers: leere Liste = alle, sonst prime / tier 1 / tier 2 / tier 3. rangeMin/rangeMax: -1 = unbegrenzt. Resub-Range prüft kumulative Monate, Gift-Range geteilte Gesamtgeschenke, Gift-Bomb-Range Anzahl der Geschenke. Nicht geteilte Werte erfüllen keine gesetzte Range. monthsGifted: leere Liste = alle, sonst z. B. [1, 3, 6, 12].')
        if self.value.get('type') in (90900,90901,90902,90903,90910,90911):hints.append('Ads/Raids benötigen die passende Broadcaster-Freigabe. Ein bestätigter Raid-Start bedeutet laufenden Countdown; Raid Send kommt erst durch Twitch EventSub. Vorschau sendet keine Änderungen. Werbezeitplan in der Vorschau ist ein gespeicherter Stand.')
        if self.value.get('type')==107:hints.append('Raid-Range prüft die Zuschauerzahl. rangeMin/rangeMax: -1 = unbegrenzt; sonst nichtnegative Ganzzahl.')
        if self.value.get('_originalEventFilter')==492:hints.append('Original-Timeoutbereich in Sekunden: rangeMin/rangeMax = -1 bedeutet unbegrenzt. Nur Maximum wurde beim Import in einen exakten Wert umgewandelt. duration wird wie in Original 1.0.7 aus Ablaufzeit minus Twitch-Nachrichtenzeitstempel gerundet; ohne gültige Zeitangaben erfüllen Ereignisse keinen gesetzten Bereich.')
        if self.value.get('type')==95003:hints.append('Mikrofoneingang der lokalen Spracherkennung: @default oder stabiler Eingabegerätename aus Stream Apps → Linux Audio; auch %variable% möglich. Eine laufende Erkennung wird neu gestartet, eine gestoppte bleibt gestoppt. Fehlende Geräte werden gemeldet. Vorschau ändert nichts.')
        if self.value.get('type') in (90141,90142):hints.append('audioDevice: @default oder stabiler Linux-Ausgangsname aus Stream Apps → Linux Audio. Ein konkreter Ausgang wird nur für diese Wiedergabe gewählt; fehlende Geräte werden gemeldet. Importierte Windows-Geräte unter Abhängigkeiten zuordnen auf einen Linux-Ausgang abbilden.')
        if self.value.get('type')==90145:hints.append('iconPath: optionaler lokaler Bildpfad; attribution: optionaler Zusatztext. Windows-Bildpfade beim Import auf eine Linux-Datei zuordnen. Darstellung und Klickaktionen hängen vom Desktop-Benachrichtigungsdienst ab.')
        if self.value.get('type')==91052:hints.append('rangeMin/rangeMax filtern die neue Hype-Train-Stufe; -1 = unbegrenzt. Level Up benötigt einen zuvor beobachteten niedrigeren Stand desselben Trains. Nicht gelieferte Fortschritts-/Shared-Chat-Werte werden nicht erfunden.')
        if 91900<=self.value.get('type',0)<=91904:hints.append('Shield: Yes, No oder Toggle (aktuellen Stand live abfragen). Warnungen benötigen einen Grund mit 1–500 Zeichen. Verdächtige Nutzer: ACTIVE_MONITORING überwacht, RESTRICTED schränkt ein. Vorschau verändert nichts und erzeugt keine erfolgreiche Moderationsbestätigung; Shield-Abfrage nutzt den gespeicherten echten Stand.')
        if 92000<=self.value.get('type',0)<=92003:hints.append('Twitch-Abfragen: Vorschau liest nur gespeicherte echte Daten; Clip-URLs können inzwischen abgelaufen sein. Charity liefert nur laufende Kampagnen. Follow-Alter: User, From Input (input0) oder Variable. Shoutout meldet Erfolg erst nach Twitch-Bestätigung; Vorschau sendet nichts.')
        if 92100<=self.value.get('type',0)<=92111:hints.append('Guest Star: eigenes Broadcaster-Konto. Session Id leer = aktuelle Sitzung; angegebene ID muss noch aktiv sein. Gastslots 1–6, begrenzt durch Slot Count. Audio/Video/Live: Unverändert, Yes oder No; Volume leer = unverändert, sonst 0–100. Regenerate Browser Sources macht vorhandene Browserquellen ungültig. Create benötigt den Host in der Twitch-Call-Oberfläche. Vorschau ändert nichts.')
        if self.value.get('type')==92209:hints.append('Charity Donation: Range in Hauptwährungseinheiten, z. B. 5 für 5 EUR/USD; -1 = unbegrenzt. Unterschiedliche Währungen werden nicht umgerechnet.')
        if self.value.get('type')==92212:hints.append('Guest Star Guest Update: Any oder den tatsächlichen Gästezustand auswählen; unbekannte oder fehlende Werte werden nicht als Live erfunden.')
        if 92305<=self.value.get('type',0)<=92308:hints.append('Shared-Chat-Abo: getrennt vom lokalen Abo. Leere tiers/monthsGifted = alle; Range -1 = unbegrenzt. Nicht geteilte Geschenkzahlen erfüllen keine gesetzte Range. Quellkanal bleibt source.*; Geschenk-Bomben beachten die Twitch-Settings.')
        if self.value.get('type')==92503:hints.append('Cheer-Range: -1 = leer. Nur Max = exakter Bits-Wert; nur Min = mindestens; beide = inklusive Grenzen.')
        if self.value.get('type')==92505:hints.append('Custom Power-up: Any oder einen Twitch-Eintrag auswählen. Liste im Live-Modus aktualisieren; Vorschau nutzt den gespeicherten Stand. Eine gespeicherte, derzeit fehlende ID bleibt erhalten.')
        if self.value.get('type')==92506:hints.append('Automatische Kanalpunkte-Rewards und Standard-Bits-Power-ups. rewardCostUnit gibt channel_points oder bits an. Bei Actions mit beiden Reward-Triggern wird die Action je passendem Trigger ausgeführt.')
        if self.value.get('type') in (92312,92315):hints.append('Range: inklusive Zuschauerzahl bei Shared Raid bzw. aufeinanderfolgende Streams bei Watch Streak. -1 = unbegrenzt.')
        if 97100<=self.value.get('type',0)<=97109:
            hints.append('StreamerMod-Plugin in separat laufendem OpenDeck. Item = sichtbare eigene Plugin-Belegung. Page = OpenDeck-Profilname oder Seitennummer ab 1 (alphabetisch). Next/Previous laufen zyklisch. Icon = Datei/URL/SVG oder Iconify-Name, z. B. mdi:home. Notify zeigt Titel/Beschreibung kurz auf eigenen sichtbaren Belegungen.')
        if 97200<=self.value.get('type',0)<=97250:
            hints.append('Instanzen unter Integrations → StreamerMod Remote einrichten. instanceId leer = alle Ziele beim Senden / beliebiger Absender beim Warten. Signal-/Ereignisnamen exakt vergleichen. Timeout in Millisekunden. Direkte Verbindung zwischen StreamerMod-Instanzen.')
        if self.value.get('type')==97400:
            hints.append('Sperrt genau einen Buchstaben für 1–600 Sekunden und gibt ihn danach automatisch frei. A/a ist dieselbe Taste; das gewählte Tastaturlayout berücksichtigt Y/Z. Bei überlappenden Sperren erfolgt die Freigabe nach der letzten aktiven Frist. Wait For Finish lässt die Action für die eingestellte Dauer warten. Benötigt den eingerichteten Tastensperrdienst. Eine zusätzliche Freigabe-Action ist nicht nötig. Vorschau verändert nichts.')
        if self.value.get('type')==97401:
            hints.append('Optionaler manueller Abbruch: hebt alle noch aktiven Buchstabensperren dieser StreamerMod-Laufzeit sofort auf. Für die automatische Freigabe nach Ablauf der Dauer wird diese Action nicht benötigt. Vorschau verändert nichts.')
        if self.value.get('type')==97500:
            hints.append('Schaltet Mikrofon oder Audioausgabe für 1–600 Sekunden stumm und stellt danach automatisch den vorherigen Stummzustand wieder her. @default = Standardgerät; @all = alle aktuell vorhandenen Geräte der gewählten Art, bei Mikrofonen ohne Monitor-Quellen. Überlappende Timer enden nach der letzten aktiven Frist. Wait For Finish lässt die Action für die eingestellte Dauer warten. Eine zusätzliche Wiederherstellungs-Action ist nicht nötig. Vorschau verändert nichts.')
        if self.value.get('type')==97501:
            hints.append('Optionaler manueller Abbruch: beendet alle temporären Audio-Stummschaltungen dieser StreamerMod-Laufzeit vorzeitig und stellt deren vorherigen Stummzustand wieder her. Betrifft Mikrofone und Audioausgabe gemeinsam. Für die automatische Wiederherstellung nach Ablauf der Dauer wird diese Action nicht benötigt. Vorschau verändert nichts.')
        if self.value.get('type')==97300:
            hints.append('Discord Basic Webhook: Nachrichten an einen Discord-Kanal senden. URL nach dem Speichern privat abgelegt; leer = vorhandene URL beibehalten. Inhalt 1–2000 Zeichen, Variablen und Zeilenumbrüche möglich. Leerer Username/Avatar verwendet Discord-Standard. Erwähnungen sind zunächst aus; Vorschau sendet nichts. Nach bestätigter Zustellung: %messageId%.')
        if hints:
            hint=QLabel('\n'.join(hints));hint.setWordWrap(True);hint.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse);layout.addWidget(hint)
        scroll=QScrollArea();scroll.setWidgetResizable(True);container=QWidget();form=QFormLayout(container)
        for key,val in self.value.items():
            if self.value.get('type')==90004 and key in ('provider','limit','autoContext'):continue
            if key.startswith('_') or key in ('id','parentId','subActions','type') or (key=='index' and self.value.get('type')!=91700) or (key=='weight' and self.value.get('type')!=90029):continue
            from .streamdeck_fields import control as deck_control
            deck_widget=deck_control(deck_kind,key,val,parent) if is_deck else None
            from .timed_effect_fields import control as timed_control
            timed_widget=timed_control(deck_kind,key,val,self.value,parent) if deck_kind in (97400,97401,97500,97501) else None
            from .streamermod_fields import control as own_control
            own_widget=own_control(deck_kind,key,val,parent) if 97100<=deck_kind<=97250 else None
            from .linux_audio_fields import control as audio_control
            audio_widget=audio_control(self.value.get('type'),key,val,self.value,parent) if 94000<=self.value.get('type',0)<=94058 else None
            if key in self.value.get('_stateValues',{}):
                widget=QComboBox()
                for option in self.value['_stateValues'][key]:widget.addItem(str(option),option)
                if widget.findData(val)<0:widget.addItem(str(val),val)
                widget.setCurrentIndex(widget.findData(val))
            elif timed_widget is not None:widget=timed_widget
            elif own_widget is not None:widget=own_widget
            elif audio_widget is not None:widget=audio_widget
            elif deck_widget is not None:widget=deck_widget
            elif self.value.get('type') in (95003,90141,90142) and key=='audioDevice':
                from .linux_audio_fields import host_snapshot
                widget=QComboBox();widget.setEditable(True);widget.addItem('@default')
                for row in host_snapshot(parent):
                    if row.get('kind')==('input' if self.value['type']==95003 else 'output') and row.get('name'):widget.addItem(row['name'])
                widget.setCurrentText(str(val))
            elif self.value.get('type')==92505 and key=='customPowerUpId':
                from .twitch_power_up_picker import PowerUpPicker
                widget=PowerUpPicker(val,parent)
            elif self.value.get('type')==92212 and key=='state':
                from .twitch_expansion_events import STATES
                widget=QComboBox()
                for option in ('Any',*(value.title() for value in STATES)):widget.addItem(option,option)
                widget.setCurrentIndex(widget.findData(val))
            elif 92100<=self.value.get('type',0)<=92111 and key in ('moderatorSendLiveEnabled','browserSourceAudioEnabled','audioEnabled','videoEnabled','live'):
                widget=QComboBox()
                for label,data in [('Unverändert',''),('Yes',True),('No',False)]:widget.addItem(label,data)
                widget.setCurrentIndex(widget.findData(val))
            elif self.value.get('type') in (92504,92506) and key in ('powerUpType','rewardType'):
                from .twitch_goals_bits import POWER_TYPES,REWARD_TYPES
                widget=QComboBox();widget.addItem('Any','')
                for option in (POWER_TYPES if key=='powerUpType' else REWARD_TYPES):widget.addItem(option,option)
                if widget.findData(val)<0:widget.addItem(str(val),val)
                widget.setCurrentIndex(max(0,widget.findData(val)))
            elif self.value.get('type')==92101 and key=='groupLayout':
                from .twitch_guest_star import LAYOUTS
                widget=QComboBox();widget.addItem('Unverändert','')
                for option in LAYOUTS:widget.addItem(option,option)
                widget.setCurrentIndex(widget.findData(val))
            elif 92100<=self.value.get('type',0)<=92111 and key in ('slot','slotCount','sourceSlot','destinationSlot','volume'):
                widget=QComboBox();widget.setEditable(True);widget.addItem('')
                widget.setCurrentText(str(val))
            elif (self.value.get('type')==91901 and key=='state') or (self.value.get('type')==91903 and key=='status'):
                widget=QComboBox()
                for option in (('Yes','No','Toggle') if key=='state' else ('ACTIVE_MONITORING','RESTRICTED')):widget.addItem(option,option)
                widget.setCurrentIndex(widget.findData(val))
            elif key=='chatPlatform' and self.value.get('type')==96005:
                widget=QComboBox()
                for label,option in [('Ursprungsplattform','source'),('Twitch','twitch'),('YouTube','youtube'),('Twitch und YouTube','both')]:widget.addItem(label,option)
                widget.setCurrentIndex(max(0,widget.findData(val)))
            elif self.value.get('type')==91804 and key in ('preferredAccount','color'):
                widget=QComboBox()
                for option in (('Bot','Broadcaster') if key=='preferredAccount' else ('Default','Blue','Green','Orange','Purple')):widget.addItem(option,option)
                widget.setCurrentIndex(max(0,widget.findData(val)))
            elif key=='rewards' and self.value.get('type')==90516:
                from .twitch_reward_config_ui import RewardConfiguration
                widget=RewardConfiguration(val,getattr(parent,'store',None))
            elif key=='groups' and self.value.get('type')==91701 and isinstance(val,list) and all(isinstance(v,str) for v in val):
                from .twitch_random_groups_ui import GroupSelection
                widget=GroupSelection(val,getattr(parent,'store',None))
            elif key=='groupName' and 91500<=self.value.get('type',0)<=91502:
                from .core_services import read_config
                widget=QComboBox();widget.setEditable(True);widget.addItem('')
                store=getattr(parent,'store',None)
                if store:
                    for name in sorted({g['name'] for g in read_config(store.root)['userGroups']}):widget.addItem(name)
                widget.setCurrentText(str(val))
            elif key=='rewardId':
                widget=QComboBox();widget.addItem('Any' if self.value.get('type') in (112,90550) else 'From Event (%rewardId%)','' if self.value.get('type') in (112,90550) else '%rewardId%')
                store=getattr(parent,'store',None)
                if store:
                    from .twitch_rewards import Rewards
                    from types import SimpleNamespace
                    rows=Rewards(SimpleNamespace(root=store.root,config=store.read('local.json'))).cache()['rewards']
                    for row in rows:widget.addItem(row['title'],row['id'])
                if widget.findData(val)<0:widget.addItem(str(val),val)
                widget.setCurrentIndex(max(0,widget.findData(val)))
            elif key=='rewardStatus' and self.value.get('type')==90550:
                widget=QComboBox()
                for label,data in [('Any',''),('Fulfilled','fulfilled'),('Canceled','canceled')]:widget.addItem(label,data)
                widget.setCurrentIndex(max(0,widget.findData(val)))
            elif 90500<=self.value.get('type',0)<=90515 and key in ('state','operator','status'):
                options={'operator':('none','add','subtract','multiply','divide'),'status':('FULFILLED','CANCELED'),'state':('enabled','disabled','toggle') if self.value['type'] in (90501,90512) else ('paused','unpaused','toggle')}[key]
                widget=QComboBox()
                for option in options:widget.addItem(option,option)
                widget.setCurrentIndex(max(0,widget.findData(val)))
            elif key=='duration' and self.value.get('type')==90902:
                widget=QComboBox();widget.setEditable(True)
                for seconds in (30,60,90,120,150,180):widget.addItem(str(seconds),seconds)
                if widget.findData(val)<0:widget.addItem(str(val),val)
                widget.setCurrentIndex(max(0,widget.findData(val)))
            elif key=='anonymous' and self.value.get('type') in (90031,90032,92307,92308):
                widget=QComboBox()
                for option in ('either','public','anonymous'):widget.addItem(option,option)
                widget.setCurrentIndex(max(0,widget.findData(val)))
            elif key=='sourceType' and (90703<=self.value.get('type',0)<=90706 or self.value.get('type') in (91601,92002)):
                widget=QComboBox()
                for option in (('Broadcaster','User','From Input','Variable') if self.value.get('type')==91601 else ('User','From Input','Variable')):widget.addItem(option,option)
                if widget.findData(val)<0:widget.addItem(str(val),val)
                widget.setCurrentIndex(max(0,widget.findData(val)))
            elif key=='obsConnection':
                from .obs_connections import definitions
                widget=QComboBox();widget.addItem('Default','default');widget.addItem('Any','any')
                widget.addItem('Local OBS','__local__')
                store=getattr(parent,'store',None)
                for row in definitions(store.read('local.json') if store else {}):
                    if row['id']!='default' and row.get('enabled',True):widget.addItem(row['name'],row['id'])
                if val not in ('default','any') and widget.findData(val)<0:widget.addItem(str(val)+' (missing)',val)
                widget.setCurrentIndex(max(0,widget.findData(val)))
            elif key=='operation' and self.value.get('type')==120:
                widget=QComboBox()
                for index,label in enumerate(('Equals','Not Equals','Contains','Regex Match','Less Than','Greater Than','Does Not Exist','Equals (Ignore Case)','Not Equals (Ignore Case)','Is Null or Empty')):
                    widget.addItem(label,index)
                widget.setCurrentIndex(max(0,widget.findData(val)))
            elif 90300<=self.value.get('type',0)<=90324 and key in ('state','axis'):
                from .obs_actions import CHOICES
                kind=self.value['type'];options=CHOICES.get(key,())
                if key=='state' and kind==90310:options=('play','pause','stop','restart','next','previous')
                elif key=='state' and kind in (90311,90312,90313):options=('start','stop','toggle','pause','resume') if kind==90311 else ('start','stop','toggle')
                widget=QComboBox()
                for option in options:widget.addItem(option,option)
                widget.setCurrentIndex(max(0,widget.findData(val)))
            elif self.value.get('type') in (90018,90019,90021,90022,90023,90024,90025,90026,90027,90028,90029,90050,90051,90052) and key in ('group','commandId','state','actionId','subActionId','queueId'):
                widget=QComboBox()
                store=getattr(parent,'store',None)
                commands=store.read('commands.json')['commands'] if store else []
                actions=store.read('actions.json')['actions'] if store else []
                if key=='state':
                    options=[('Pause','pause'),('Resume','resume')] if self.value['type']==90051 else [('Enabled','enabled'),('Disabled','disabled'),('Toggle','toggle')]
                    for label,state in options:widget.addItem(label,state)
                elif key=='queueId':
                    widget.addItem('Default',None)
                    if self.value['type'] in (90050,90051):widget.addItem('All','All')
                    for queue in store.read('actions.json').get('queues',[]) if store else []:widget.addItem(queue['name'],queue['id'])
                elif key=='commandId':
                    for command in commands:widget.addItem(command['name'],command['id'])
                elif key=='actionId':
                    for action in actions:widget.addItem(action['name'],action['id'])
                elif key=='subActionId':pass
                else:
                    if self.value['type']==90021:widget.addItem('All','All')
                    items=actions if self.value['type'] in (90026,90027) else commands
                    for group in sorted({c.get('group','') for c in items}):widget.addItem(group or 'None',group)
                selection=('enabled' if val else 'disabled') if key=='state' and isinstance(val,bool) else val
                index=widget.findData(selection)
                if index<0 and selection:
                    widget.addItem('Missing: '+str(val),val);index=widget.count()-1
                widget.setCurrentIndex(max(0,index))
            elif key in ('timerId','fileTailId','voiceCommandId','groupId','triggerId','watcherId','inputDeviceId','midiDeviceId','connectionId','scheduleId','pointDefinitionId') or (key=='actionId' and self.value.get('type') in (90131,90134) or key=='actionId' and 'command' in self.value and 'location' in self.value):
                widget=QComboBox();store=getattr(parent,'store',None)
                from .core_services import read_config
                core=read_config(store.root) if store else {}
                if key=='timerId':items=store.read('timers.json') if store else []
                elif key=='actionId':items=store.read('actions.json')['actions'] if store else []
                elif key=='triggerId':items=[]
                else:items=core.get({'fileTailId':'fileTails','voiceCommandId':'voiceCommands','groupId':'userGroups','watcherId':'fileWatchers','inputDeviceId':'inputDevices','midiDeviceId':'midiDevices','connectionId':'websocketConnections','scheduleId':'cronSchedules','pointDefinitionId':'pointDefinitions'}[key],[])
                if key=='actionId' and 'location' in self.value:widget.addItem('(Trigger only)','')
                if self.value.get('type',0)>=90200 and key not in ('triggerId','pointDefinitionId','groupId'):widget.addItem('Any','')
                for item in items:widget.addItem(item.get('name',item['id']),item['id'])
                index=widget.findData(val)
                if index<0 and val:widget.addItem('Missing: '+str(val),val);index=widget.count()-1
                widget.setCurrentIndex(max(0,index))
            elif key=='state' and (90100<=self.value.get('type',0)<=90160 or self.value.get('type')==91304):
                widget=QComboBox()
                for text,state in [('Enabled','enabled'),('Disabled','disabled'),('Toggle','toggle')]:widget.addItem(text,state)
                widget.setCurrentIndex(max(0,widget.findData(val)))
            elif key in ('operator','selection') and self.value.get('type') in (90112,90161):
                widget=QComboBox()
                options=['random','specific'] if key=='selection' else ['equals','notEquals','lessThan','greaterThan']
                for option in options:widget.addItem(option,option)
                widget.setCurrentIndex(max(0,widget.findData(val)))
            elif key=='effect' and self.value.get('type')==90006:
                from .camera import EFFECTS
                widget=QComboBox()
                for effect in sorted(EFFECTS):widget.addItem(effect,effect)
                widget.setCurrentIndex(max(0,widget.findData(val)))
            elif key=='keys' and self.value.get('type')==90240:
                widget=QKeySequenceEdit(str(val));widget.setMaximumSequenceLength(1)
            elif key=='persisted' and self.value.get('type') in (90220,90221,90222,90223):
                widget=QComboBox()
                for label,value in [('Either','either'),('Yes',True),('No',False)]:widget.addItem(label,value)
                widget.setCurrentIndex(max(0,widget.findData(val)))
            elif key=='mode' and 'url' in self.value:
                widget=QComboBox();widget.addItem('Client','client');widget.addItem('Local Server','server');widget.setCurrentIndex(max(0,widget.findData(val)))
            elif key=='path' and 'path' in self.value and set(self.value)<= {'id','name','path','enabled'}:
                widget=QComboBox();widget.setEditable(True)
                from pathlib import Path
                for path in sorted(Path('/dev/input/by-id').glob('*')):widget.addItem(str(path))
                widget.setCurrentText(str(val))
            elif isinstance(val,bool): widget=QCheckBox();widget.setChecked(val)
            elif key=='channel' and self.value.get('type') in (90150,90151,90152):
                widget=QComboBox();widget.addItem('All','')
                for channel in range(1,17):widget.addItem(str(channel),channel)
                widget.setCurrentIndex(max(0,widget.findData(val)))
            elif key=='device' and (self.value.get('type') in (90150,90151,90152) or 'device' in self.value and 'type' not in self.value):
                from .linux_midi import devices
                widget=QComboBox();widget.setEditable(True)
                for device in devices():widget.addItem(device,device)
                widget.setCurrentText(val)
            elif key=='command' and self.value.get('type')==90151:
                widget=QComboBox()
                for command in ('NoteOn','NoteOff','ControlChange','PatchChange','ChannelAfterTouch','PitchWheelChange'):widget.addItem(command,command)
                widget.setCurrentIndex(max(0,widget.findData(val)))
            elif key=='broadcastMode':
                widget=QComboBox()
                for label,value in [('All','all'),('Latest','latest'),('From Variable (broadcast.id)','variable')]:widget.addItem(label,value)
                widget.setCurrentIndex(max(0,widget.findData(val)))
            elif key=='promptKind' and self.value.get('type') in (90004,90007,90008):
                from .ai_fields import prompt_box
                widget=prompt_box(val,parent)
            elif key=='provider':
                widget=QComboBox()
                for label,provider in [('Zentrale KI-Einstellungen verwenden','default'),('Local LLM','local'),('OpenAI','openai')]:widget.addItem(label,provider)
                widget.setCurrentIndex(max(0,widget.findData(val)))
            elif isinstance(val,(dict,list)):
                widget=QPlainTextEdit(json.dumps(val,ensure_ascii=False,indent=2));widget.setMaximumHeight(110)
            elif key in ('text','message','prompt','value','description','content'):
                widget=QPlainTextEdit('' if val is None else str(val));widget.setMaximumHeight(105)
            else: widget=QLineEdit('' if val is None else str(val))
            if self.value.get('type')==97300 and key=='webhookUrl':
                widget.setEchoMode(QLineEdit.EchoMode.Password)
                widget.setPlaceholderText('Gespeicherte URL beibehalten (leer)' if self.value.get('_discordWebhookId') else 'Discord-Webhook-URL eintragen')
            labels={'group':'Group','commandId':'Command','state':'State','resultVariable':'Variable Name','includeAll':'Include All','onlyHasPermission':'Only Has Permission','ignoreAliases':'Ignore Aliases','actionId':'Action','subActionId':'Sub-Action','weight':'Weight','queueId':'Queue','clear':'Clear'} if self.value.get('type') in (90018,90019,90021,90022,90023,90024,90025,90026,90027,90028,90029,90050,90051,90052) else {}
            if isinstance(widget,QComboBox) and not widget.isEditable() and val=='' and widget.count()==0:
                widget.insertItem(0,'(Select...)','');widget.setCurrentIndex(0)
            if 94000<=self.value.get('type',0)<=94058:
                from .linux_audio_fields import LABELS as AUDIO_LABELS
                labels=AUDIO_LABELS
            if 97100<=self.value.get('type',0)<=97250:
                from .streamermod_fields import LABELS as OWN_LABELS
                labels=OWN_LABELS
            if self.value.get('type') in (97400,97401,97500,97501):
                from .timed_effect_fields import LABELS as TIMED_LABELS
                labels=TIMED_LABELS
            if self.value.get('type')==97300:labels={'webhookName':'Webhook Name','webhookUrl':'Webhook URL (privat)','content':'Inhalt','username':'Benutzername (optional)','avatarUrl':'Avatar URL (optional)','textToSpeech':'Discord Text to Speech','allowMentions':'Erwähnungen erlauben'}
            if self.value.get('type')==97050:labels={'webhookName':'Webhook Name (empty = any)'}
            if self.value.get('type')==97000:labels={'method':'HTTP Method','url':'Webhook URL','headers':'HTTP Headers (JSON)','body':'Payload (JSON)','resultVariable':'Result Variable'}
            if self.value.get('type')==95003:labels={'audioDevice':'Audio Input Device'}
            if is_deck:
                from .streamdeck_fields import LABELS
                labels=LABELS
            if self.value.get('type')==91701:labels={'count':'Count','presentOnly':'Present Only','groups':'Groups','includeFrom':'Include From'}
            if self.value.get('type') in (90004,90007,90008):
                from .ai_fields import LABELS as AI_LABELS
                labels=AI_LABELS
            if key=='provider' and self.value.get('type')==90004:
                override=QCheckBox('Für diese Unteraktion einen anderen Anbieter verwenden')
                override.setChecked(val not in ('default','',None));form.addRow(override)
                widget.setVisible(override.isChecked())
                def override_changed(checked,box=widget):
                    box.setVisible(checked)
                    if not checked:box.setCurrentIndex(box.findData('default'))
                    elif box.currentData()=='default':box.setCurrentIndex(box.findData('local'))
                override.toggled.connect(override_changed)
                form.addRow(widget)
            else:form.addRow(labels.get(key,key),widget)
            self.controls[key]=(widget,val)
        if self.value.get('type') in (90028,90029):
            def subactions_changed(*_):
                from .core import walk
                action_box=self.controls['actionId'][0];target_box=self.controls['subActionId'][0]
                selected=target_box.currentData() or self.value.get('subActionId')
                target_box.clear()
                action=next((a for a in actions if a['id']==action_box.currentData()),None)
                if action:
                    from .next_catalog import steps
                    for node in walk(action.get('subActions',[])):
                        if node['type'] in (99901,99902):continue
                        label=steps().get(node['type'],(str(node['type']),{}))[0]
                        target_box.addItem(label+' ('+node['id'][:8]+')',node['id'])
                index=target_box.findData(selected)
                if index<0 and selected and self.value.get('actionId')==action_box.currentData():
                    target_box.addItem('Missing: '+selected,selected);index=target_box.count()-1
                target_box.setCurrentIndex(max(0,index))
            self.controls['actionId'][0].currentIndexChanged.connect(subactions_changed)
            subactions_changed()
        if self.value.get('type')==90131:
            def refresh_trigger(*_):
                box=self.controls['triggerId'][0];selected=box.currentData() or self.value.get('triggerId');box.clear()
                document=parent.store.read('actions.json') if getattr(parent,'store',None) else {'actions':[]}
                action=next((a for a in document['actions'] if a['id']==self.controls['actionId'][0].currentData()),None)
                if action:
                    for trigger in action.get('triggers',[]):box.addItem(TRIGGERS.get(trigger['type'],(str(trigger['type']),{}))[0]+' ('+trigger['id'][:8]+')',trigger['id'])
                index=box.findData(selected)
                if index<0 and selected and self.value.get('actionId')==self.controls['actionId'][0].currentData():box.addItem('Missing: '+selected,selected);index=box.count()-1
                box.setCurrentIndex(max(0,index))
            self.controls['actionId'][0].currentIndexChanged.connect(refresh_trigger);refresh_trigger()
        if 94000<=self.value.get('type',0)<=94058 and 'audioKind' in self.controls:
            def audio_kind_changed(*_):
                from .linux_audio_fields import control
                node={**self.value,'audioKind':self.controls['audioKind'][0].currentData()}
                for key in ('audioTarget','audioDevice'):
                    if key not in self.controls:continue
                    box=self.controls[key][0];text=box.currentText();choices=control(self.value['type'],key,text,node,parent)
                    box.clear()
                    for i in range(choices.count()):box.addItem(choices.itemText(i),choices.itemData(i))
                    box.setCurrentText(text);choices.deleteLater()
            self.controls['audioKind'][0].currentIndexChanged.connect(audio_kind_changed)
        if self.value.get('type')==90004 and 'promptKind' in self.controls:
            selector=self.controls['promptKind'][0];custom_box=self.controls['prompt'][0]
            label=form.labelForField(custom_box)
            def prompt_mode_changed(*_):
                custom=selector.currentData()=='__custom__';custom_box.setVisible(custom)
                if label:label.setVisible(custom)
            selector.currentIndexChanged.connect(prompt_mode_changed);prompt_mode_changed()
        scroll.setWidget(container);layout.addWidget(scroll)
        box=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(self.accept);box.rejected.connect(self.reject);layout.addWidget(box)

    def accept(self):
        try:
            for key,(widget,old) in self.controls.items():
                if getattr(widget,'reward_configuration',False) or getattr(widget,'random_group_selection',False):value=widget.value()
                elif isinstance(widget,QKeySequenceEdit):value=widget.keySequence().toString()
                elif isinstance(widget,QCheckBox): value=widget.isChecked()
                elif isinstance(widget,QComboBox):
                    value=widget.currentText() if widget.isEditable() else widget.currentData()
                    if value is None and old=='':value=''
                    if widget.isEditable() and isinstance(old,int) and not isinstance(old,bool):
                        try:value=int(value)
                        except ValueError:pass
                    if isinstance(old,bool) and value in ('enabled','disabled'):value=value=='enabled'
                else:
                    text=widget.toPlainText() if isinstance(widget,QPlainTextEdit) else widget.text()
                    if isinstance(old,(dict,list)):value=json.loads(text)
                    elif isinstance(old,int):value=int(text)
                    elif isinstance(old,float):value=float(text)
                    else:value=text
                self.value[key]=value
            if self.value.get('type')==90004:
                self.value.pop('provider',None);self.value.pop('limit',None)
                if self.value.get('promptKind')!='__custom__':self.value['prompt']=''
            if self.value.get('type')==91701:
                from .twitch_random_groups import validate
                validate(self.value)
            if 94000<=self.value.get('type',0)<=94005:
                from .linux_audio_fields import validate as validate_audio
                validate_audio(self.value)
            if 93000<=self.value.get('type',0)<=93006:
                from .streamdeck_fields import validate
                validate(self.value)
            if self.value.get('type')==95003 and (not self.value.get('audioDevice','').strip() or len(self.value['audioDevice'])>500 or any(ord(c)<32 for c in self.value['audioDevice'])):raise ValueError('Bitte @default oder einen gültigen Mikrofon-Gerätenamen angeben.')
            if self.value.get('type')==97300 and self.value.get('webhookUrl'):
                from .discord_webhooks import save_url
                host=self.parent();store=getattr(host,'store',None)
                if store is None:store=getattr(getattr(host,'host',None),'store',None)
                if store is None:raise ValueError('Discord-URL benötigt ein geöffnetes lokales Projekt')
                save_url(store.root,self.value)
            if self.value.get('type')==90165 and not isinstance(self.value.get('values'),list):raise ValueError('Case values must be a JSON list.')
        except (ValueError,ActionError) as exc:
            QMessageBox.warning(self,'Ungültige Eingabe',str(exc));return
        super().accept()


class ActionDialog(QDialog):
    def __init__(self,action,store,parent=None):
        super().__init__(parent);self.setWindowTitle('Aktion bearbeiten');self.resize(1050,740)
        self.value=copy.deepcopy(action);self.store=store
        layout=QVBoxLayout(self);form=QFormLayout()
        self.name=QLineEdit(action['name']);self.group=QLineEdit(action.get('group',''))
        self.enabled=QCheckBox('Aktiviert');self.enabled.setChecked(action.get('enabled',True))
        self.queue=QComboBox();self.queue.addItem('Standard',None)
        for q in store.read('actions.json').get('queues',[]):self.queue.addItem(q['name'],q['id'])
        self.queue.setCurrentIndex(max(0,self.queue.findData(action.get('queue'))))
        form.addRow('Name',self.name);form.addRow('Gruppe',self.group);form.addRow('Warteschlange',self.queue);form.addRow('',self.enabled);layout.addLayout(form)
        if action.get('cameraEffect'):
            self.camera=QComboBox()
            from .camera import EFFECTS
            self.camera.addItems(sorted(EFFECTS));self.camera.setCurrentText(action['cameraEffect']);form.addRow('Linux-Kameraeffekt',self.camera)
        split=QSplitter();layout.addWidget(split)
        left=QWidget();ll=QVBoxLayout(left);ll.addWidget(QLabel('Trigger'))
        self.triggers=QTreeWidget();self.triggers.setHeaderLabels(['Ereignis','Zuordnung']);ll.addWidget(self.triggers)
        buttons(ll,[('+ Trigger',self.add_trigger),('Bearbeiten',self.edit_trigger),('Entfernen',self.remove_trigger)])
        right=QWidget();rl=QVBoxLayout(right);rl.addWidget(QLabel('Unteraktionen – in dieser Reihenfolge'))
        self.steps=QTreeWidget();self.steps.setHeaderLabels(['Unteraktion','Wert']);rl.addWidget(self.steps)
        buttons(rl,[('+ Unteraktion',self.add_step),('Bearbeiten',self.edit_step),('Entfernen',self.remove_step)])
        buttons(rl,[('Nach oben',lambda:self.move(-1)),('Nach unten',lambda:self.move(1)),('JSON bearbeiten',self.edit_json)])
        split.addWidget(left);split.addWidget(right);split.setSizes([350,650])
        self.steps.itemDoubleClicked.connect(self.edit_step);self.triggers.itemDoubleClicked.connect(self.edit_trigger)
        box=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(self.accept);box.rejected.connect(self.reject);layout.addWidget(box);self.refresh()
        from .editor_menus import bind, editor_menu
        bind(self.steps,lambda:editor_menu(self));bind(self.triggers,lambda:editor_menu(self,True))

    def refresh(self):
        identities=[tree.currentItem().data(0,ROLE) if tree.currentItem() else None for tree in (self.steps,self.triggers)]
        self.steps.clear();self.triggers.clear()
        def populate(nodes,parent):
            for n in nodes:
                label=STEPS.get(n['type'],({99999:'Portiertes Originalskript',99901:'Wenn wahr',99902:'Sonst'}.get(n['type'],str(n['type'])),{}))[0]
                item=QTreeWidgetItem([label,str(n.get('text',n.get('value',n.get('sourceName',n.get('name','')))))[:100]])
                item.setData(0,ROLE,n['id']);item.setDisabled(False);item.setText(0,label if n.get('enabled',True) else label+' [deaktiviert]');parent.addChild(item);populate(n.get('subActions',[]),item)
        def ensure_ids(nodes):
            for n in nodes:n.setdefault('id',str(uuid.uuid4()));ensure_ids(n.get('subActions',[]))
        ensure_ids(self.value['subActions']);populate(self.value['subActions'],self.steps.invisibleRootItem());self.steps.expandAll()
        for t in self.value['triggers']:
            from .trigger_labels import criteria
            item=QTreeWidgetItem([TRIGGERS.get(t['type'],(str(t['type']),{}))[0],criteria(t,self.store)])
            item.setData(0,ROLE,t['id']);self.triggers.addTopLevelItem(item)
        self.steps.resizeColumnToContents(0)
        def restore(parent,tree,identity):
            for i in range(parent.childCount()):
                item=parent.child(i)
                if item.data(0,ROLE)==identity:tree.setCurrentItem(item)
                restore(item,tree,identity)
        for tree,identity in zip((self.steps,self.triggers),identities):restore(tree.invisibleRootItem(),tree,identity)

    def selected(self):
        item=self.steps.currentItem()
        if not item:return None,None,None
        identity=item.data(0,ROLE)
        def find(nodes):
            for i,n in enumerate(nodes):
                if n['id']==identity:return nodes,i,n
                found=find(n.get('subActions',[]))
                if found:return found
        return find(self.value['subActions']) or (None,None,None)

    def add_step(self,kind=None):
        if kind is None or kind is False:
            labels=[v[0] for v in STEPS.values()]
            label,ok=QInputDialog.getItem(self,'Unteraktion hinzufügen','Baustein',labels,0,False)
            if not ok:return
            kind=list(STEPS)[labels.index(label)]
        label=STEPS[kind][0];node=new_step(kind)
        if kind==4:
            actions=self.store.read('actions.json')['actions'];names=[a['name'] for a in actions]
            name,ok=QInputDialog.getItem(self,'Aktion auswählen','Aktion',names,0,False)
            if not ok:return
            node['actionId']=actions[names.index(name)]['id']
        dialog=step_dialog(label,node,self)
        if dialog.exec()!=QDialog.DialogCode.Accepted:return
        nodes,index,selected=self.selected()
        if selected and 'subActions' in selected and selected['type']!=120:selected['subActions'].append(dialog.value)
        elif nodes is not None:nodes.insert(index+1,dialog.value)
        else:self.value['subActions'].append(dialog.value)
        self.refresh()

    def edit_step(self,*_):
        nodes,index,node=self.selected()
        if node is None:return
        dialog=step_dialog('Unteraktion bearbeiten',node,self)
        if dialog.exec()==QDialog.DialogCode.Accepted:nodes[index]=dialog.value;self.refresh()

    def remove_step(self):
        nodes,index,node=self.selected()
        if node is not None:del nodes[index];self.refresh()

    def move(self,offset):
        nodes,index,node=self.selected()
        if node is not None and 0<=index+offset<len(nodes):
            nodes[index],nodes[index+offset]=nodes[index+offset],nodes[index];self.refresh()

    def add_trigger(self,kind=None):
        if kind is None or kind is False:
            labels=[v[0] for v in TRIGGERS.values()];label,ok=QInputDialog.getItem(self,'Trigger hinzufügen','Ereignis',labels,0,False)
            if not ok:return
            kind=list(TRIGGERS)[labels.index(label)]
        label=TRIGGERS[kind][0]
        trigger={'id':str(uuid.uuid4()),'type':kind,'enabled':True,**copy.deepcopy(TRIGGERS[kind][1])}
        if kind in (401,701):
            values=self.store.read('commands.json')['commands'] if kind==401 else self.store.read('timers.json')
            names=[v['name']+('  '+v['command'] if kind==401 else '') for v in values]
            if not names:QMessageBox.information(self,'Zuordnung','Zuerst einen Befehl bzw. Timer im Hauptfenster anlegen.');return
            name,ok=QInputDialog.getItem(self,'Zuordnung','Befehl / Timer',names,0,False)
            if not ok:return
            trigger['commandId' if kind==401 else 'timerId']=values[names.index(name)]['id']
        dialog=FieldsDialog(label,trigger,self)
        if dialog.exec()==QDialog.DialogCode.Accepted:self.value['triggers'].append(dialog.value);self.refresh()

    def edit_trigger(self,*_):
        item=self.triggers.currentItem()
        if not item:return
        for i,t in enumerate(self.value['triggers']):
            if t['id']==item.data(0,ROLE):
                dialog=FieldsDialog('Trigger bearbeiten',t,self)
                if dialog.exec()==QDialog.DialogCode.Accepted:self.value['triggers'][i]=dialog.value;self.refresh()
                return

    def remove_trigger(self):
        item=self.triggers.currentItem()
        if item:self.value['triggers']=[t for t in self.value['triggers'] if t['id']!=item.data(0,ROLE)];self.refresh()

    def edit_json(self):
        dialog=QDialog(self);dialog.setWindowTitle('Unteraktionen als JSON');dialog.resize(800,600);layout=QVBoxLayout(dialog)
        edit=QPlainTextEdit(json.dumps(self.value['subActions'],ensure_ascii=False,indent=2));layout.addWidget(edit)
        box=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);box.accepted.connect(dialog.accept);box.rejected.connect(dialog.reject);layout.addWidget(box)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            try:
                value=json.loads(edit.toPlainText());validate_action(dict(self.value,subActions=value));self.value['subActions']=value;self.refresh()
            except ValueError as exc:QMessageBox.warning(self,'JSON',str(exc))

    def accept(self):
        self.value.update(name=self.name.text().strip(),group=self.group.text(),enabled=self.enabled.isChecked(),queue=self.queue.currentData())
        if hasattr(self,'camera'):self.value['cameraEffect']=self.camera.currentText()
        try:validate_action(self.value)
        except ValueError as exc:QMessageBox.warning(self,'Aktion',str(exc));return
        super().accept()


class MainWindow(QMainWindow):
    def __init__(self,root,live=False,obs_test=False):
        super().__init__();self.root=Path(root);self.store=ConfigStore(root);self.live=live;self.obs_test=obs_test
        self.mode_label='LIVE' if live else 'OBS-TEST' if obs_test else 'VORSCHAU'
        self.setWindowTitle('Sorgobot Studio — '+self.mode_label)
        self.resize(1180,800)
        self.document=self.store.read('actions.json')
        central=QWidget();layout=QVBoxLayout(central);self.setCentralWidget(central)
        banner=QLabel('SORGOBOT STUDIO   |   '+('Live-Betrieb: echte Aktionen aktiviert' if live else 'OBS-Test: echte OBS-Steuerung · übrige Aktionen simuliert · automatische Trigger aus' if obs_test else 'Vorschaumodus: Aktionen werden simuliert'))
        banner.setStyleSheet('padding:10px;background:#263645;font-weight:bold;color:#d7e9f6');layout.addWidget(banner)
        self.tabs=QTabWidget();layout.addWidget(self.tabs)
        self.make_actions();self.make_commands();self.make_timers();self.make_ai();self.make_connections();self.make_obs();self.make_log()
        if obs_test:self.search.setText('Debian-Test')
        menu=self.menuBar().addMenu('Datei');reload_action=QAction('Konfiguration neu laden',self);reload_action.triggered.connect(self.reload_files);menu.addAction(reload_action)
        quit_action=QAction('Beenden',self);quit_action.triggered.connect(self.close);menu.addAction(quit_action)
        self.statusBar().showMessage('Starte lokale Aktions-Engine …')
        self.start_runtime()
        QApplication.clipboard().dataChanged.connect(self.clipboard_changed)
        self.poll=QTimer(self);self.poll.timeout.connect(lambda:self.runtime.submit('status'))

    def start_runtime(self):
        self.runtime=Runtime(self.root,self.live,self.obs_test);self.runtime.result.connect(self.on_result);self.runtime.error.connect(self.on_error)
        self.runtime.input_requested.connect(self.show_input);self.runtime.ready.connect(self.runtime_ready);self.runtime.start()

    def clipboard_changed(self):
        if self.live and any(a.get('enabled',True) and any(t['type']==90250 and t.get('enabled',True) for t in a.get('triggers',[])) for a in self.document['actions']):
            text=QApplication.clipboard().text()
            self.runtime.submit('clipboard_changed',text=text[:65536],truncated=len(text)>65536)

    def show_input(self,identity,node):
        if node.get('kind')=='color':
            from PySide6.QtWidgets import QColorDialog
            from PySide6.QtGui import QColor
            color=QColor(node.get('originalText','#ffffff'))
            dialog=QColorDialog(color if color.isValid() else QColor('#ffffff'),self);dialog.setWindowTitle(node.get('title','Pick Color'));dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            dialog.finished.connect(lambda result:self.runtime.input_reply(identity,dialog.selectedColor().name(),result==QDialog.DialogCode.Accepted));dialog.open();return
        dialog=QInputDialog(self);dialog.setWindowTitle(node.get('title','Input'));dialog.setLabelText(node.get('prompt',''));dialog.setTextValue(node.get('originalText',''));dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.finished.connect(lambda result:self.runtime.input_reply(identity,dialog.textValue(),result==QDialog.DialogCode.Accepted));dialog.open()

    def page(self,name):
        page=QWidget();layout=QVBoxLayout(page);self.tabs.addTab(page,name);return layout

    def make_actions(self):
        layout=self.page('Aktionen');buttons(layout,[('＋ Hinzufügen',self.add_action),('Bearbeiten',self.edit_action),('Duplizieren',self.clone_action),('Entfernen',self.delete_action),('▶ Ausführen',self.run_action)])
        self.search=QLineEdit();self.search.setPlaceholderText('Aktionen filtern …');self.search.textChanged.connect(self.populate_actions);layout.addWidget(self.search)
        split=QSplitter();layout.addWidget(split)
        self.actions=QTreeWidget();self.actions.setHeaderLabels(['Name / Gruppe','Aktiv','Trigger','Unteraktionen']);self.actions.itemSelectionChanged.connect(self.select_action);self.actions.itemDoubleClicked.connect(self.edit_action);split.addWidget(self.actions)
        detail=QWidget();dl=QVBoxLayout(detail);self.selected_name=QLabel('Aktion auswählen');dl.addWidget(self.selected_name)
        self.trigger_view=QTreeWidget();self.trigger_view.setHeaderLabels(['Trigger','Zuordnung']);dl.addWidget(self.trigger_view)
        self.step_view=QTreeWidget();self.step_view.setHeaderLabels(['Unteraktionen','Wert']);dl.addWidget(self.step_view)
        self.run_input=QLineEdit();self.run_input.setPlaceholderText('Testeingabe: %rawInput% / %input0%');dl.addWidget(self.run_input)
        split.addWidget(detail);split.setSizes([620,700]);self.populate_actions()
        from .editor_menus import bind, action_menu, detail_menu
        bind(self.actions,lambda:action_menu(self))
        bind(self.trigger_view,lambda:detail_menu(self,True));bind(self.step_view,lambda:detail_menu(self))

    def populate_actions(self):
        selected=self.current_action();identity=selected['id'] if selected else None
        self.actions.clear();groups={};term=self.search.text().casefold()
        for a in self.document['actions']:
            if term and term not in (a['name']+' '+a.get('group','')).casefold():continue
            group=a.get('group') or 'Ohne Gruppe'
            if group not in groups:groups[group]=QTreeWidgetItem([group]);self.actions.addTopLevelItem(groups[group])
            item=QTreeWidgetItem([a['name'],'Ja' if a.get('enabled') else 'Nein',str(len(a['triggers'])),str(len(a['subActions']))]);item.setData(0,ROLE,a['id']);groups[group].addChild(item)
        self.actions.expandAll();self.actions.resizeColumnToContents(0)
        for group in groups.values():
            for i in range(group.childCount()):
                if group.child(i).data(0,ROLE)==identity:self.actions.setCurrentItem(group.child(i));return
        if self.actions.topLevelItemCount() and self.actions.topLevelItem(0).childCount():
            self.actions.setCurrentItem(self.actions.topLevelItem(0).child(0))

    def current_action(self):
        item=self.actions.currentItem()
        return next((a for a in self.document['actions'] if item and a['id']==item.data(0,ROLE)),None)

    def select_action(self):
        a=self.current_action();self.trigger_view.clear();self.step_view.clear()
        if not a:return
        self.selected_name.setText(a['name']+'   ·   '+a['id'])
        for t in a['triggers']:
            details=t.get('commandId',t.get('rewardId',t.get('sceneName',t.get('timerId',''))))
            if t['type']==401:
                details=next((c['command'] for c in self.store.read('commands.json')['commands'] if c['id']==details),details)
            item=QTreeWidgetItem([TRIGGERS.get(t['type'],(str(t['type']),{}))[0]+(' [deaktiviert]' if not t.get('enabled',True) else ''),str(details)]);item.setData(0,ROLE,t['id']);self.trigger_view.addTopLevelItem(item)
        def add(nodes,parent):
            for n in nodes:
                name=STEPS.get(n['type'],({99999:'Originalskript · Python-Port',99901:'Wenn wahr',99902:'Sonst'}.get(n['type'],str(n['type'])),{}))[0]
                item=QTreeWidgetItem([name+(' [deaktiviert]' if not n.get('enabled',True) else ''),str(n.get('text',n.get('value',n.get('sourceName',n.get('name','')))))[:160]]);item.setData(0,ROLE,n.get('id'));parent.addChild(item);add(n.get('subActions',[]),item)
        if a.get('cameraEffect'):self.step_view.addTopLevelItem(QTreeWidgetItem(['Linux-Kameraeffekt',a['cameraEffect']+' · 5 Minuten']))
        else:add(a['subActions'],self.step_view.invisibleRootItem())
        self.step_view.expandAll();self.step_view.resizeColumnToContents(0)
        self.trigger_view.resizeColumnToContents(0)
        self.trigger_view.header().setStretchLastSection(True)

    def save_actions(self):
        self.store.save('actions.json',self.document);self.populate_actions();self.runtime.submit('reload');self.statusBar().showMessage('Aktionen gespeichert. Vorherige Version unter state/backups.',6000)

    def add_action(self):
        dialog=ActionDialog(new_action(),self.store,self)
        if dialog.exec()==QDialog.DialogCode.Accepted:self.document['actions'].append(dialog.value);self.save_actions()

    def edit_action(self,*_):
        action=self.current_action()
        if not action:return
        dialog=ActionDialog(action,self.store,self)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            self.document['actions']=[dialog.value if a['id']==action['id'] else a for a in self.document['actions']];self.save_actions()

    def clone_action(self):
        action=self.current_action()
        if not action:return
        clone=copy.deepcopy(action);clone['id']=str(uuid.uuid4());clone['name']+=' (Kopie)';clone['triggers']=[]
        # C# port IDs deliberately stay stable: they identify translated implementations.
        self.document['actions'].append(clone);self.save_actions()

    def delete_action(self):
        action=self.current_action()
        if not action:return
        self.document['actions']=[a for a in self.document['actions'] if a['id']!=action['id']];self.save_actions()

    def run_action(self):
        action=self.current_action()
        if action:self.runtime.submit('run',id=action['id'],input=self.run_input.text());self.statusBar().showMessage('Aktion gestartet: '+action['name'])

    def make_commands(self):
        layout=self.page('Befehle');self.command_table=QTreeWidget();self.command_table.setHeaderLabels(['Name','Befehl / Regex','Aktiv','Rechte']);layout.addWidget(self.command_table)
        buttons(layout,[('＋ Befehl',lambda:self.command_edit(True)),('Bearbeiten',lambda:self.command_edit(False)),('Entfernen',self.command_delete)])
        self.command_table.itemDoubleClicked.connect(lambda *_:self.command_edit(False));self.populate_commands()
        from .editor_menus import bind
        from PySide6.QtWidgets import QMenu
        def command_menu():
            menu=QMenu(self);menu.addAction('Hinzufügen',lambda:self.command_edit(True))
            menu.addAction('Bearbeiten',lambda:self.command_edit(False)).setEnabled(self.command_table.currentItem() is not None)
            menu.addAction('Entfernen',self.command_delete).setEnabled(self.command_table.currentItem() is not None)
            return menu
        bind(self.command_table,command_menu)

    def populate_commands(self):
        self.command_table.clear()
        for c in self.store.read('commands.json')['commands']:
            item=QTreeWidgetItem([c['name'],c['command'],'Ja' if c['enabled'] else 'Nein',', '.join(c.get('permittedGroups',[]))]);item.setData(0,ROLE,c['id']);self.command_table.addTopLevelItem(item)
        for i in (0,1):self.command_table.resizeColumnToContents(i)

    def command_edit(self,new):
        doc=self.store.read('commands.json');item=self.command_table.currentItem()
        c={'id':str(uuid.uuid4()),'name':'Neuer Befehl','command':'!neu','enabled':True,'mode':0,'location':0,'caseSensitive':False,'permittedGroups':[],'permittedUsers':[],'globalCooldown':0,'userCooldown':0} if new else next((x for x in doc['commands'] if item and x['id']==item.data(0,ROLE)),None)
        if c is None:return
        dialog=FieldsDialog('Chatbefehl · mode 0 Text, 1 Regex',c,self)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            if not dialog.value['command'].strip():return
            if new:doc['commands'].append(dialog.value)
            else:doc['commands']=[dialog.value if x['id']==c['id'] else x for x in doc['commands']]
            self.store.save('commands.json',doc);self.populate_commands();self.runtime.submit('reload')

    def command_delete(self):
        item=self.command_table.currentItem()
        if not item:return
        doc=self.store.read('commands.json');doc['commands']=[c for c in doc['commands'] if c['id']!=item.data(0,ROLE)];self.store.save('commands.json',doc);self.populate_commands();self.runtime.submit('reload')

    def make_timers(self):
        layout=self.page('Timer');self.timer_table=QTreeWidget();self.timer_table.setHeaderLabels(['Name','Intervall (s)','Aktiv']);layout.addWidget(self.timer_table)
        buttons(layout,[('＋ Timer',lambda:self.timer_edit(True)),('Bearbeiten',lambda:self.timer_edit(False))]);self.populate_timers()

    def populate_timers(self):
        self.timer_table.clear()
        for t in self.store.read('timers.json'):
            item=QTreeWidgetItem([t['name'],str(t['interval']),'Ja' if t['enabled'] else 'Nein']);item.setData(0,ROLE,t['id']);self.timer_table.addTopLevelItem(item)

    def timer_edit(self,new):
        timers=self.store.read('timers.json');item=self.timer_table.currentItem()
        timer={'id':str(uuid.uuid4()),'name':'Neuer Timer','enabled':True,'repeat':True,'interval':600,'randomInterval':False,'upperInterval':900,'lines':0} if new else next((t for t in timers if item and t['id']==item.data(0,ROLE)),None)
        if timer is None:return
        dialog=FieldsDialog('Timer',timer,self)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            if dialog.value['interval']<1:QMessageBox.warning(self,'Timer','Intervall muss mindestens 1 Sekunde sein.');return
            if new:timers.append(dialog.value)
            else:timers=[dialog.value if t['id']==timer['id'] else t for t in timers]
            self.store.save('timers.json',timers);self.populate_timers();self.runtime.submit('reload')

    def make_ai(self):
        layout=self.page('KI / Prompts');config=self.store.read('local.json');form=QFormLayout()
        from .ai_settings import AISettings
        self.ai_settings=AISettings(config);layout.addWidget(self.ai_settings)
        self.provider=self.ai_settings.provider;self.bridge=self.ai_settings.bridge
        self.ai_fields=self.ai_settings.fields
        self.reply_probability=QLineEdit(str(config.get('reply_probability',0)))
        form.addRow('Zufallsantworten (%)',self.reply_probability);layout.addLayout(form)
        hint=QLabel('General gilt bei jeder KI-Anfrage. Der Ereignis-Prompt ergänzt ihn und hat bei widersprüchlichen Vorgaben Vorrang. KI-Variablen in Nachrichtentexten erzeugen automatisch einen passenden Zusatztext; bereits gesetzte Antworten werden übernommen.');hint.setWordWrap(True);layout.addWidget(hint)
        from .ai_variables import VARIABLES
        variables=QComboBox()
        for name,(kind,label) in VARIABLES.items():variables.addItem('%'+name+'% — '+label,'%'+name+'%')
        variable_row=QHBoxLayout();variable_row.addWidget(QLabel('KI-Textvariable'));variable_row.addWidget(variables,1);copy_button=QPushButton('Kopieren');copy_button.clicked.connect(lambda:QApplication.clipboard().setText(variables.currentData()));variable_row.addWidget(copy_button);layout.addLayout(variable_row)
        tabs=QTabWidget();self.prompt_fields={};prompts=self.store.read('prompts.json')
        from .ai_fields import prompt_label
        for key in dict.fromkeys([*PROMPTS,*prompts]):
            default=PROMPTS.get(key,('', ''))[1]
            edit=QPlainTextEdit(prompts.get(key,default));tabs.addTab(edit,'General' if key=='behavior' else prompt_label(key));self.prompt_fields[key]=edit
        layout.addWidget(tabs);buttons(layout,[('KI-Einstellungen speichern',self.save_ai)])

    def save_ai(self):
        config=self.store.read('local.json')
        config.update(self.ai_settings.values())
        config['reply_probability']=self.reply_probability.text()
        try:config['reply_probability']=max(0,min(100,int(config['reply_probability'])))
        except ValueError:QMessageBox.warning(self,'Eingabe','Antwortwahrscheinlichkeit muss eine Zahl sein.');return
        config['ai_provider']=self.provider.currentData();config['bridge_enabled']=self.bridge.isChecked()
        self.store.save('local.json',config);self.store.save('prompts.json',{k:w.toPlainText() for k,w in self.prompt_fields.items()});self.runtime.submit('reload');self.statusBar().showMessage('KI-Anbieter und alle Ereignis-Prompts gespeichert.',6000)

    def make_connections(self):
        layout=self.page('Verbindungen / Geräte');scroll=QScrollArea();scroll.setWidgetResizable(True);container=QWidget();form=QFormLayout(container);config=self.store.read('local.json');self.connection_fields={}
        for key,label in [('obs_url','OBS WebSocket'),('obs_password','OBS-Passwort'),('twitch_client_id','Twitch Client-ID'),('broadcaster_id','Broadcaster-ID'),('bot_id','Bot-ID'),('twitch_token','Twitch Broadcaster-Token'),('twitch_bot_token','Twitch Bot-Token'),('camera_device','Kameragerät'),('keyboard_device','Physische Tastatur'),('tts_voice','TTS-Stimme'),('microphone','PipeWire Mikrofon'),('headset','PipeWire Headset'),('own3d_token','OWN3D-Token'),('summary_token','Summary-Token')]:
            edit=QLineEdit(str(config.get(key,'')))
            if 'token' in key or 'password' in key:edit.setEchoMode(QLineEdit.EchoMode.Password)
            self.connection_fields[key]=edit;form.addRow(label,edit)
        self.camera_enabled=QCheckBox('Lokalen Kameradienst aktivieren');self.camera_enabled.setChecked(config.get('camera_enabled',False));form.addRow('',self.camera_enabled)
        scroll.setWidget(container);layout.addWidget(scroll);buttons(layout,[('Verbindungen speichern (Neustart erforderlich)',self.save_connections)])

    def save_connections(self):
        config=self.store.read('local.json')
        for k,w in self.connection_fields.items():config[k]=w.text()
        if str(config['camera_device']).isdigit():config['camera_device']=int(config['camera_device'])
        config['camera_enabled']=self.camera_enabled.isChecked();self.store.save('local.json',config)
        self.statusBar().showMessage('Gespeichert. Der Kameradienst wird mit den neuen Einstellungen geladen.',10000)

    def make_obs(self):
        layout=self.page('OBS / Chat');self.obs_image=QLabel('OBS-Vorschau – im Live-Modus verfügbar');self.obs_image.setAlignment(Qt.AlignmentFlag.AlignCenter);self.obs_image.setMinimumHeight(280);self.obs_image.setStyleSheet('background:#17202b');layout.addWidget(self.obs_image)
        row=QHBoxLayout();self.scenes=QComboBox();row.addWidget(self.scenes);scene_button=QPushButton('Szene wechseln');scene_button.clicked.connect(lambda:self.runtime.submit('obs',command='SetCurrentProgramScene',params={'sceneName':self.scenes.currentText()}));row.addWidget(scene_button);refresh=QPushButton('Aktualisieren');refresh.clicked.connect(lambda:self.runtime.submit('obs_scenes'));row.addWidget(refresh);layout.addLayout(row)
        output_buttons=buttons(layout,[(label,lambda checked=False,c=command:self.runtime.submit('obs',command=c)) for label,command in [('Stream starten','StartStream'),('Stream stoppen','StopStream'),('Aufnahme starten','StartRecord'),('Aufnahme stoppen','StopRecord')]])
        for button in output_buttons:button.setEnabled(self.live)
        self.chat_view=QPlainTextEdit();self.chat_view.setReadOnly(True);layout.addWidget(self.chat_view)
        row=QHBoxLayout();self.chat_input=QLineEdit();self.chat_input.setPlaceholderText('Chatnachricht als Bot');row.addWidget(self.chat_input);send=QPushButton('Senden');send.clicked.connect(self.send_chat);row.addWidget(send);layout.addLayout(row)

    def send_chat(self):
        if self.chat_input.text().strip():self.runtime.submit('chat',message=self.chat_input.text());self.chat_input.clear()

    def make_log(self):
        layout=self.page('Verlauf / Diagnose');self.log=QPlainTextEdit();self.log.setReadOnly(True);layout.addWidget(self.log)

    def runtime_ready(self):
        if self.runtime.stopping:return
        self.statusBar().showMessage('Bereit · '+self.mode_label);self.poll.start(4000);self.runtime.submit('obs_scenes')

    def on_result(self,kind,value):
        if kind=='status':
            self.statusBar().showMessage(self.mode_label+'   |   OBS: '+value['obs']+'   |   Twitch: '+value['twitch'])
            self.log.setPlainText('\n'.join(f"{h['time']}  {h['status']}  {h['name']}  {h['error']}" for h in value['history'])+'\n\nSchritte:\n'+json.dumps(value['effects'],ensure_ascii=False,indent=2))
            self.chat_view.setPlainText('\n'.join(m['user']+': '+m['message'] for m in value['chat']))
            if self.tabs.tabText(self.tabs.currentIndex())=='OBS / Chat':self.runtime.submit('preview')
        elif kind=='obs_scenes':
            self.scenes.clear();self.scenes.addItems([s['sceneName'] for s in value.get('scenes',[])])
            current=value.get('currentProgramSceneName')
            if current:self.scenes.setCurrentText(current)
        elif kind=='camera_preview' and value:
            import base64
            pix=QPixmap();pix.loadFromData(base64.b64decode(value.split(',',1)[1]))
            if hasattr(self,'camera_image'):self.camera_image.setPixmap(pix.scaled(self.camera_image.size(),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
        elif kind=='preview' and value:
            import base64
            pix=QPixmap();pix.loadFromData(base64.b64decode(value.split(',',1)[1]));self.obs_image.setPixmap(pix.scaled(self.obs_image.size(),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
        elif kind=='run':self.statusBar().showMessage('Aktion vorzeitig beendet – siehe Action History / Logs.' if value.get('executionStatus')=='stopped' else 'Aktion beendet.' if value.get('executionStatus')=='finished' else 'Aktion abgeschlossen.',15000)

    def on_error(self,message):
        self.statusBar().showMessage('Fehler: '+message,15000)
        if hasattr(self,'log'):self.log.appendPlainText('FEHLER: '+message)

    def reload_files(self):
        self.document=self.store.read('actions.json');self.populate_actions();self.populate_commands();self.populate_timers();self.runtime.submit('reload')

    def closeEvent(self,event):
        self.poll.stop()
        if not self.runtime.stop():
            self.statusBar().showMessage('Aufräumen laufender Aktionen dauert noch …');event.ignore();return
        event.accept()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);parser.add_argument('--live',action='store_true');parser.add_argument('--with-obs',action='store_true');parser.add_argument('--screenshot',type=Path)
    parser.add_argument('--obs-test',action='store_true',help='OBS echt steuern, übrige Aktionen simulieren')
    parser.add_argument('--allow-idle',action='store_true',help='Automatische Bildschirmsperre und Standby auch bei geöffnetem Studio zulassen')
    args=parser.parse_args()
    if args.live and args.obs_test:parser.error('--live und --obs-test schließen sich aus')
    if args.with_obs:
        import shutil,subprocess
        if shutil.which('obs') and sys.platform=='linux' and subprocess.run(['pgrep','-x','obs'],capture_output=True).returncode:
            subprocess.Popen(['obs'],start_new_session=True)
    app=QApplication(sys.argv[:1]);app.setApplicationName('Sorgobot Studio');app.setStyle('Fusion')
    (args.root/'state').mkdir(exist_ok=True)
    lock=QLockFile(str(args.root/'state/desktop.lock'))
    if not lock.tryLock(0):
        QMessageBox.information(None,'Sorgobot Studio','Für diesen Projektordner ist die Desktop-Anwendung bereits geöffnet.')
        return
    app.setStyleSheet('QWidget{font-size:12px} QTreeWidget,QPlainTextEdit,QLineEdit,QComboBox{selection-background-color:#376c91} QTreeWidget{alternate-background-color:#f0f3f6} QTabBar::tab{padding:9px 14px} QPushButton{padding:6px 11px} QHeaderView::section{padding:5px;font-weight:bold}')
    window=MainWindow(args.root,args.live,args.obs_test);window.show()
    if sys.platform=='linux' and not args.allow_idle:
        import os,subprocess
        keeper=subprocess.Popen(['/usr/bin/python3',str(Path(__file__).with_name('keepawake.py')),
                                 '--watch-pid',str(os.getpid())])
        app.aboutToQuit.connect(keeper.terminate)
    if args.screenshot:
        QTimer.singleShot(1800,lambda:window.grab().save(str(args.screenshot)))
    sys.exit(app.exec())


if __name__=='__main__':main()
