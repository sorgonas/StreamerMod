import asyncio
import collections
import logging
import datetime as dt
from zoneinfo import ZoneInfo

import aiohttp

from .core import ActionError
from .twitch_features import TwitchFeatures


class TwitchEvents:
    def __init__(self, io, dispatcher, spawn):
        self.io, self.dispatcher, self.spawn = io, dispatcher, spawn
        self.status = 'offline'
        self.seen = collections.OrderedDict()
        self.messages = []
        self.viewers = {}
        self.events = []
        self.features=TwitchFeatures(self);self.subscription_status={};self.hype_snapshot={}
        from .twitch_chat_modes import ChatModes
        self.chat_modes=ChatModes(io)
        from .twitch_connections_whispers import Connections
        self.connections=Connections(io,dispatcher,spawn)

    async def subscriptions(self, session_id):
        cfg = self.io.config
        broadcaster = cfg['broadcaster_id']
        subs = [('stream.online','1',{'broadcaster_user_id':broadcaster}),('stream.offline','1',{'broadcaster_user_id':broadcaster}),('channel.follow', '2', {'broadcaster_user_id': broadcaster, 'moderator_user_id': broadcaster}),
                ('channel.raid', '1', {'to_broadcaster_user_id': broadcaster}),
                ('channel.channel_points_custom_reward_redemption.add', '1', {'broadcaster_user_id': broadcaster}),
                ('channel.chat.message', '1', {'broadcaster_user_id': broadcaster, 'user_id': broadcaster}),
                ('channel.chat.notification','1',{'broadcaster_user_id':broadcaster,'user_id':broadcaster}),
                ('channel.update','2',{'broadcaster_user_id':broadcaster})]
        from .twitch_rewards import scopes,READ
        granted=scopes(cfg)
        from .twitch_reward_lifecycle import TYPES as REWARD_LIFECYCLE
        from .twitch_chat_modes import EVENT_TYPE,EVENT_SCOPE
        self.chat_modes.previous=None;self.chat_modes.cutoff=None
        if EVENT_SCOPE in granted:
            try:await self.chat_modes.start_session()
            except (ActionError,OSError,ValueError,KeyError,TypeError):self.io.trace('twitch_chat_modes_baseline_unavailable',message='Erster Ereignisstand wird als Basis verwendet; kein erfundener Übergang.')
            subs.append((EVENT_TYPE,'1',{'broadcaster_user_id':broadcaster,'user_id':broadcaster}))
        else:self.subscription_status[EVENT_TYPE]={'state':'missing_scope','message':EVENT_SCOPE+' fehlt'}
        if granted & READ:
            for change in ('add','update','remove'):subs.append(('channel.channel_points_custom_reward.'+change,'1',{'broadcaster_user_id':broadcaster}))
        subs.append(('channel.channel_points_custom_reward_redemption.update','1',{'broadcaster_user_id':broadcaster}))
        for family,parts in [('poll',('begin','progress','end')),('prediction',('begin','progress','lock','end'))]:
            for part in parts:subs.append((f'channel.{family}.{part}','1',{'broadcaster_user_id':broadcaster}))
        for part in ('begin','progress','end'):subs.append(('channel.hype_train.'+part,'2',{'broadcaster_user_id':broadcaster}))
        subs.append(('channel.raid','1',{'from_broadcaster_user_id':broadcaster}))
        subs.append(('channel.ad_break.begin','1',{'broadcaster_user_id':broadcaster}))
        subs.append(('channel.subscribe','1',{'broadcaster_user_id':broadcaster}))
        subs.append(('channel.subscription.end','1',{'broadcaster_user_id':broadcaster}))
        from .twitch_moderation import EVENT_SCOPES
        for kind in EVENT_SCOPES:subs.append((kind,'1',{'broadcaster_user_id':broadcaster}))
        from .twitch_expansion_events import subscriptions as expansion_subscriptions,MAP as EXPANSION_TYPES,required as expansion_rights
        subs.extend(expansion_subscriptions(broadcaster))
        from .twitch_shared_chat import subscriptions as shared_subscriptions,SESSIONS as SHARED_TYPES
        subs.extend(shared_subscriptions(broadcaster))
        from .twitch_moderation_details import subscriptions as details_subscriptions,TYPES as DETAILS_TYPES,missing as details_missing
        subs.extend(details_subscriptions(broadcaster))
        from .twitch_goals_bits import subscriptions as goals_bits_subscriptions,TYPES as GOALS_BITS_TYPES,required as goals_bits_rights
        subs.extend(goals_bits_subscriptions(broadcaster))
        from .twitch_connections_whispers import WHISPER_TYPE,WHISPER_RIGHTS,confirmed as whisper_confirmed
        if granted & WHISPER_RIGHTS:subs.append((WHISPER_TYPE,'1',{'user_id':broadcaster}))
        else:self.subscription_status[WHISPER_TYPE]={'state':'missing_scope','message':'user:read:whispers oder user:manage:whispers fehlt'}
        for kind, version, condition in subs:
            if kind in GOALS_BITS_TYPES and not granted & goals_bits_rights(kind):
                self.subscription_status[kind]={'state':'missing_scope','message':' oder '.join(sorted(goals_bits_rights(kind)))+' fehlt'}
                continue
            if kind in DETAILS_TYPES and details_missing(kind,granted):
                self.subscription_status[kind]={'state':'missing_scope','message':' und '.join(' / '.join(sorted(group)) for group in details_missing(kind,granted))+' fehlt'}
                continue
            if kind in EXPANSION_TYPES and not granted & expansion_rights(kind):
                self.subscription_status[kind]={'state':'missing_scope','message':' oder '.join(sorted(expansion_rights(kind)))+' fehlt'}
                continue
            if kind.startswith('channel.hype_train.') and 'channel:read:hype_train' not in granted:
                self.subscription_status[kind]={'state':'missing_scope','message':'channel:read:hype_train fehlt'}
                continue
            if kind=='channel.ad_break.begin' and 'channel:read:ads' not in granted:
                self.subscription_status[kind]={'state':'missing_scope','message':'channel:read:ads fehlt'}
                continue
            if kind in ('channel.subscribe','channel.subscription.end') and 'channel:read:subscriptions' not in granted:
                self.subscription_status[kind]={'state':'missing_scope','message':'channel:read:subscriptions fehlt'}
                continue
            if kind in EVENT_SCOPES and not granted & EVENT_SCOPES[kind]:
                self.subscription_status[kind]={'state':'missing_scope','message':' oder '.join(sorted(EVENT_SCOPES[kind]))+' fehlt'}
                continue
            family='polls' if kind.startswith('channel.poll.') else 'predictions' if kind.startswith('channel.prediction.') else None
            if family and not granted&{'channel:read:'+family,'channel:manage:'+family}:
                self.subscription_status[kind]={'state':'missing_scope','message':'channel:read:'+family+' oder channel:manage:'+family+' fehlt'}
                continue
            if 'channel_points_custom_reward_redemption' in kind and not granted&READ:
                self.subscription_status[kind]={'state':'missing_scope','message':'channel:read:redemptions oder channel:manage:redemptions fehlt'}
                continue
            try:
                reply=await self.io.twitch('POST', 'eventsub/subscriptions', {'type': kind, 'version': version,
                    'condition': condition, 'transport': {'method': 'websocket', 'session_id': session_id}})
                if kind in EXPANSION_TYPES or kind in SHARED_TYPES or kind in DETAILS_TYPES or kind in GOALS_BITS_TYPES or kind in REWARD_LIFECYCLE:
                    rows=reply.get('data') if isinstance(reply,dict) else None
                    if kind in GOALS_BITS_TYPES:
                        from .twitch_goals_bits import confirmed
                        if not confirmed(kind,version,condition,reply):raise ActionError('EventSub-Anmeldung wurde nicht vollständig bestätigt')
                    elif not isinstance(rows,list) or len(rows)!=1 or not isinstance(rows[0],dict) or rows[0].get('type')!=kind or rows[0].get('version')!=version or rows[0].get('condition')!=condition or rows[0].get('status')!='enabled':raise ActionError('EventSub-Anmeldung wurde nicht vollständig bestätigt')
                if kind in ('channel.chat.message',WHISPER_TYPE) and not whisper_confirmed(kind,condition,reply):raise ActionError('Chat-/Whisper-Anmeldung wurde nicht vollständig bestätigt')
                self.subscription_status[kind]={'state':'enabled'}
            except ActionError as exc:
                self.subscription_status[kind]={'state':'error','message':str(exc)}
                self.io.trace('twitch_subscription_error',event=kind,error=str(exc))

    async def connect(self, url, subscribe):
        socket = await self.io.session.ws_connect(url, autoping=True)
        try:
            welcome = await asyncio.wait_for(socket.receive_json(), 15)
            if welcome['metadata']['message_type'] != 'session_welcome':
                raise ActionError('Twitch EventSub Welcome fehlt')
            session = welcome['payload']['session']
            if subscribe:
                await self.connections.change('eventsub',True)
                await self.subscriptions(session['id'])
                await self.connections.change('broadcasterChat',self.subscription_status.get('channel.chat.message',{}).get('state')=='enabled')
            return socket, (session.get('keepalive_timeout_seconds') or 10) + 5
        except BaseException:
            try:
                if subscribe:await self.connections.reset_broadcaster('connection_failed')
            finally:await socket.close()
            raise

    async def run(self):
        presence=self.spawn(self.features.run())
        try:await self.event_loop()
        finally:
            presence.cancel();await asyncio.gather(presence,return_exceptions=True)

    async def event_loop(self):
        while True:
            ws = None
            try:
                ws, timeout = await self.connect('wss://eventsub.wss.twitch.tv/ws', True)
                self.status = 'connected'
                self.spawn(self.features.connected())
                while True:
                    msg = await asyncio.wait_for(ws.receive(), timeout)
                    if msg.type != aiohttp.WSMsgType.TEXT:
                        raise ActionError('Twitch-Verbindung getrennt')
                    body = msg.json()
                    meta = body['metadata']
                    kind = meta['message_type']
                    if kind == 'session_reconnect':
                        replacement, timeout = await self.connect(body['payload']['session']['reconnect_url'], False)
                        await ws.close()
                        ws = replacement
                    elif kind == 'revocation':
                        revoked=body['payload']['subscription'];event_type=revoked['type']
                        self.subscription_status[event_type]={'state':'revoked','message':'Twitch-Berechtigung widerrufen: '+revoked.get('status','unknown')}
                        if event_type=='channel.chat.message':raise ActionError('Twitch-Chat-Berechtigung widerrufen')
                    elif kind == 'notification':
                        identity = meta['message_id']
                        if identity in self.seen:
                            continue
                        self.seen[identity] = True
                        if len(self.seen) > 5000:
                            self.seen.popitem(last=False)
                        self.spawn(self.notification(body['payload']['subscription']['type'], body['payload']['event'], identity,meta.get('message_timestamp','')))
            except (aiohttp.ClientError, OSError, ValueError, KeyError, ActionError, TimeoutError) as exc:
                self.status = str(exc) if isinstance(exc, ActionError) else 'Twitch-Verbindung fehlgeschlagen'
                logging.warning('%s', self.status)
            finally:
                try:await self.connections.reset_broadcaster('disconnected')
                finally:
                    if ws:await ws.close()
                self.features.pyramids.reset()
                registry=self.features.registry()
                if registry:registry.clear_presence('twitch')
            await asyncio.sleep(10)

    async def notification(self, kind, event, identity,occurred_at=''):
        from .websocket_twitch_progress import DELIVERY
        delivery={'active':True,'engine':getattr(self.dispatcher,'engine',None),'kind':kind,'event':event,'stamp':occurred_at}
        token=DELIVERY.set(delivery)
        try:return await self._notification(kind,event,identity,occurred_at)
        finally:
            delivery['active']=False
            DELIVERY.reset(token)

    async def _notification(self, kind, event, identity,occurred_at=''):
        from .twitch_connections_whispers import WHISPER_TYPE,ingest as whisper_ingest
        if kind==WHISPER_TYPE:
            mapped=whisper_ingest(self.io,event,identity)
            if mapped:
                from .twitch_connections_whispers import dispatch_whisper
                await dispatch_whisper(self.dispatcher,mapped)
            return
        # A queued delivery can outlive an account switch. Never dispatch its
        # old broadcaster's events or Command matches into the new project account.
        if event.get('broadcaster_user_id') is not None and event['broadcaster_user_id']!=self.io.config.get('broadcaster_id'):return
        prefix = 'chatter_' if kind in ('channel.chat.message','channel.chat.notification') else 'from_broadcaster_' if kind == 'channel.raid' else 'user_'
        login = event.get(prefix + ('user_login' if prefix != 'user_' else 'login'), '') or ''
        display = event.get(prefix + ('user_name' if prefix != 'user_' else 'name'), login) or login
        uid = event.get(prefix + ('user_id' if prefix != 'user_' else 'id'), '') or ''
        if kind=='channel.chat.notification' and event.get('chatter_is_anonymous'):login='';display='Anonymous';uid=''
        args = {'userType': 'twitch', 'platform': 'twitch', 'userName': login, 'userLogin': login, 'user': display, 'userId': uid, 'messageId': identity, 'msgId':event.get('message_id',''), 'input0': '', 'rawInput': ''}
        timestamp=dt.datetime.now(ZoneInfo(self.io.config.get('timezone','Europe/Berlin'))).isoformat(timespec='seconds')
        self.events.append({'id':identity,'time':timestamp,'type':kind,'user':display,'platform':'Twitch'})
        self.events[:]=self.events[-300:]
        if kind != 'channel.chat.message' and login:
            registry=self.features.registry()
            if registry:registry.remember('twitch',login,uid,display)
        from .twitch_expansion_events import MAP as EXPANSION_TYPES,Events as ExpansionEvents
        from .twitch_goals_bits import TYPES as GOALS_BITS_TYPES,ingest as goals_bits_ingest
        from .twitch_reward_lifecycle import TYPES as REWARD_LIFECYCLE,ingest as reward_change
        if kind in REWARD_LIFECYCLE:
            mapped=reward_change(self.io,kind,event,identity)
            if mapped:await self.dispatcher.event(*mapped,rewardId=mapped[1]['rewardId'])
        elif kind in GOALS_BITS_TYPES:
            for mapped in goals_bits_ingest(self.io,kind,event,identity):await self.dispatcher.event(*mapped)
        elif kind in EXPANSION_TYPES:
            mapped=ExpansionEvents(self.io).ingest(kind,event,identity)
            if mapped:await self.dispatcher.event(*mapped)
        elif kind=='channel.moderate' and event.get('action') in ('raid','unraid'):
            from .twitch_raid_lifecycle import ingest
            mapped=await ingest(self.io,event,identity,occurred_at)
            if mapped:await self.dispatcher.event(*mapped)
        elif kind in ('channel.moderate','automod.message.hold','automod.message.update','channel.suspicious_user.message','channel.suspicious_user.update','channel.unban_request.create','channel.unban_request.resolve'):
            from .twitch_moderation_details import ingest
            mapped=ingest(self.io,kind,event,identity,occurred_at)
            if mapped:await self.dispatcher.event(*mapped)
        elif kind.startswith('channel.shared_chat.'):
            from .twitch_shared_chat import ingest
            mapped=ingest(self.io,kind,event,identity)
            if mapped:await self.dispatcher.event(*mapped)
        elif kind == 'channel.chat.message':
            from .internal_chat import matches as internal_message
            if await internal_message(getattr(getattr(self.dispatcher,'engine',None),'studio',None),event):args['isInternal']=True
            args['message'] = event['message']['text']
            badges = {b['set_id'] for b in event.get('badges', [])}
            args['roles'] = [v for k, v in [('broadcaster', 'Broadcaster'), ('moderator', 'Moderators'), ('vip', 'VIPs'), ('subscriber', 'Subscribers')] if k in badges]
            self.features.chat_user(args,timestamp)
            await self.features.chat(event,args)
            from .chat_messages import history_row
            self.messages.append(history_row(event,args))
            self.messages[:] = self.messages[-100:]
            from .websocket_twitch_events import chat as notify_chat
            await notify_chat(self,event,args,occurred_at or timestamp)
        elif kind=='channel.chat_settings.update':
            for trigger,values in self.chat_modes.ingest(event,identity,occurred_at):await self.dispatcher.event(trigger,values)
        elif kind=='channel.chat.notification':
            from .twitch_shared_chat import NOTICES,ingest
            if event.get('notice_type') in NOTICES:
                mapped=ingest(self.io,kind,event,identity)
                if mapped:
                    trigger,values=mapped
                    if not (trigger==92307 and values.get('fromGiftBomb') and self.io.config.get('twitch_ignore_gift_bombs',True)):await self.dispatcher.event(trigger,values)
                return
            from .twitch_subscription_events import notification
            mapped=notification(event)
            if mapped:
                trigger,values=mapped;values['messageId']=identity
                if not (trigger==90031 and values.get('fromGiftBomb') and self.io.config.get('twitch_ignore_gift_bombs',True)):
                    await self.dispatcher.event(trigger,values)
                # Subscription notices carry user text but are not a second
                # public chat message. Keep channel/first-word counters separate.
                if trigger in (90850,90851) and not values.get('anonymous') and values.get('userId') and values.get('userName') and isinstance(values.get('message'),str) and values['message'].strip():
                    chat=getattr(self.dispatcher,'chat',None)
                    if chat:
                        from .twitch_shared_chat import roles
                        context=dict(values,commandSource='twitch',commandType='subscription' if trigger==90850 else 'resubscription')
                        roles(context,event.get('badges'))
                        context['roles']=list(dict.fromkeys([*context.get('roles',[]),'Subscribers',*(['Broadcaster'] if values['userId']==self.io.config.get('broadcaster_id') else [])]))
                        await chat(context)
        elif kind in ('stream.online','stream.offline'):
            from .twitch_channel import stream_event
            mapped=await stream_event(self.io,kind,event,identity,occurred_at)
            if mapped:await self.dispatcher.event(*mapped)
        elif kind=='channel.subscribe':
            from .twitch_sub_counter import SubCounter,ROLLOVER
            values=SubCounter(self.io).ingest(event,identity,occurred_at)
            if values:await self.dispatcher.event(ROLLOVER,values)
        elif kind=='channel.subscription.end':
            from .twitch_subscription_events import expired
            trigger,values=expired(event);values['messageId']=identity
            await self.dispatcher.event(trigger,values)
        elif kind in ('channel.ban','channel.unban','channel.vip.add','channel.vip.remove','channel.moderator.add','channel.moderator.remove'):
            from .twitch_moderation_events import notification
            trigger,values=notification(kind,event);values['messageId']=identity
            await self.dispatcher.event(trigger,values)
        elif kind.startswith(('channel.poll.','channel.prediction.')):
            from .twitch_vote_events import notification
            mapped=notification(kind,event)
            if mapped:
                trigger,values=mapped;values.update(userType='twitch',platform='twitch',broadcasterUserId=event.get('broadcaster_user_id',''),broadcasterUserName=event.get('broadcaster_user_login',''),broadcasterUser=event.get('broadcaster_user_name',''),messageId=identity)
                await self.dispatcher.event(trigger,values)
        elif kind=='channel.update':await self.features.update(event)
        elif kind == 'channel.follow':
            args.update(followedAt=event.get('followed_at'),broadcasterUserId=event.get('broadcaster_user_id',self.io.config.get('broadcaster_id')),broadcasterUserName=event.get('broadcaster_user_login',self.io.config.get('twitch_login')),broadcasterUser=event.get('broadcaster_user_name',self.io.config.get('twitch_login')))
            await self.dispatcher.event(101, args)
        elif kind.startswith('channel.hype_train.'):
            from .twitch_hype_train import HypeTrain
            output,snapshot=HypeTrain(self.io).ingest(kind,event,identity)
            if snapshot:self.hype_snapshot=snapshot
            for trigger,values in output:await self.dispatcher.event(trigger,values)
        elif kind=='channel.ad_break.begin':
            from .twitch_ads_raids_events import ad
            trigger,values=ad(event);values['messageId']=identity
            await self.dispatcher.event(trigger,values)
        elif kind == 'channel.raid':
            from .twitch_ads_raids_events import raid
            mapped=raid(event,self.io.config['broadcaster_id'])
            if mapped:
                trigger,values=mapped;values['messageId']=identity
                await self.dispatcher.event(trigger,values)
        elif kind in ('channel.channel_points_custom_reward_redemption.add','channel.channel_points_custom_reward_redemption.update'):
            from .twitch_reward_events import arguments,store
            args.update(arguments(self.io,event))
            engine=getattr(self.dispatcher,'engine',None)
            if engine:
                counters=store(engine)
                from .twitch_rewards import Rewards
                account=Rewards(self.io).key()
                if kind.endswith('.add'):
                    counts=counters.add(account,args['rewardId'],uid,event['id'],event.get('redeemed_at'),event.get('reward',{}).get('cost',0))
                    if counts is None:return
                else:counts=counters.get(account,args['rewardId'],uid)
                args['counter'],args['userCounter']=counts
            if kind.endswith('.add'):await self.dispatcher.event(112,args,rewardId=args['rewardId'])
            else:await self.dispatcher.event(90550,args,rewardId=args['rewardId'],rewardStatus=args['rewardStatus'])
