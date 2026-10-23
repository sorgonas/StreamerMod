"""Runtime behavior for the Twitch Settings controls."""
import asyncio
import time
from datetime import datetime, timezone
import aiohttp
from .core import ActionError

class TwitchFeatures:
    def __init__(self,events):
        self.events=events;self.io=events.io;self.emotes={};self.emote_sources={};self.emote_status={};self.emote_account=None;
        self.emote_load_lock=asyncio.Lock();self.emote_load_checked=0
        from .twitch_polling_triggers import Polling
        self.polling=Polling(self.io);
        from .twitch_pyramids import Pyramids
        self.pyramids=Pyramids(self.io);self.viewer_updated=0;self.viewer_mode=None;self.viewer_error=False;self.viewer_checked=None;self.channel_checked=None;self.channel_count=None;self.channel_account=None
        self.previous_channel=None;self.previous_channel_account=None

    async def load_emotes(self):
        async with self.emote_load_lock:await self._load_emotes()

    async def _load_emotes(self):
        cfg=self.io.config;uid=cfg.get('broadcaster_id','');account=(uid,cfg.get('twitch_client_id'));self.set_emote_account(account)
        self.emote_load_checked=time.monotonic()
        sources=[('bttv','https://api.betterttv.net/3/cached/emotes/global'),('bttv','https://api.betterttv.net/3/cached/users/twitch/'+uid),('ffz','https://api.frankerfacez.com/v1/set/global'),('ffz','https://api.frankerfacez.com/v1/room/id/'+uid),('7tv','https://7tv.io/v3/emote-sets/global'),('7tv','https://7tv.io/v3/users/twitch/'+uid)]
        for provider,url in sources:
            layer='global' if url.endswith('/global') else 'channel'
            if not cfg.get('twitch_emotes_'+provider,True):
                self.emote_sources.pop((provider,layer),None);continue
            try:
                if provider=='7tv' and layer=='channel':
                    rows=await self.polling.read_emotes('7tv',self.polling.account())
                    if account!=(cfg.get('broadcaster_id'),cfg.get('twitch_client_id')):raise ActionError('Konto während Emote-Abfrage gewechselt')
                    self.channel_emotes(provider,rows)
                    continue
                data=await self.io.http('GET',url)
                if account!=(cfg.get('broadcaster_id'),cfg.get('twitch_client_id')):raise ActionError('Konto während Emote-Abfrage gewechselt')
                if provider=='bttv':items=data if isinstance(data,list) else data.get('channelEmotes',[])+data.get('sharedEmotes',[])
                elif provider=='ffz':items=[emote for group in data.get('sets',{}).values() for emote in group.get('emoticons',[])]
                else:items=data.get('emote_set',data).get('emotes',[])
                parsed={}
                for emote in items:
                    name=emote.get('code',emote.get('name',''))
                    if name:
                        from .websocket_emotes import provider_row
                        parsed[name]=provider_row(provider,emote)
                self.emote_sources[(provider,layer)]=parsed
                self.emote_status[(provider,layer)]={'state':'ready','checkedAt':datetime.now(timezone.utc).isoformat()}
            except (ActionError,aiohttp.ClientError,OSError,ValueError,TypeError,KeyError) as exc:
                # No channel registration (404) is normal; an emote service cannot
                # prevent EventSub chat from connecting.
                if account==(cfg.get('broadcaster_id'),cfg.get('twitch_client_id')):
                    absent=isinstance(exc,ActionError) and str(exc).startswith('HTTP 404:') and layer=='channel'
                    if absent:self.emote_sources.pop((provider,layer),None)
                    self.emote_status[(provider,layer)]={'state':'notRegistered' if absent else 'error'}
                continue
        self.rebuild_emotes()

    def registry(self):
        engine=getattr(self.events.dispatcher,'engine',None)
        if engine is None:return None
        from .users import store
        return store(engine)

    async def emit(self,kind,args):
        owner=getattr(self.events.spawn,'__self__',None)
        if self.io.dry_run or getattr(owner,'closing',False):return
        if self.events.spawn:self.events.spawn(self.events.dispatcher.event(kind,args))
        else:await self.events.dispatcher.event(kind,args)

    def set_emote_account(self,account):
        if self.emote_account==account:return
        self.emote_account=account
        self.emote_load_checked=0
        self.emote_sources={key:value for key,value in self.emote_sources.items() if key[1]!='channel'}
        self.emote_status={key:value for key,value in self.emote_status.items() if key[1]!='channel'}
        self.rebuild_emotes()

    def rebuild_emotes(self):
        combined={}
        for (provider,source),items in sorted(self.emote_sources.items(),key=lambda row:(row[0][1]=='channel',row[0][0])):
            if self.io.config.get('twitch_emotes_'+provider,True):combined.update(items)
        self.emotes=combined

    def channel_emotes(self,provider,rows):
        from .websocket_emotes import provider_row
        self.emote_sources[(provider,'channel')]={r['name']:provider_row(provider,r) for r in rows}
        self.emote_status[(provider,'channel')]={'state':'ready','checkedAt':datetime.now(timezone.utc).isoformat()}
        self.rebuild_emotes()

    def presence_mode(self):
        cfg=self.io.config
        enabled=cfg.get('twitch_present_viewers',True);live=cfg.get('twitch_viewers_live',False)
        interval=max(1,min(10,int(cfg.get('twitch_viewers_interval',5))))*60
        mode=(enabled,live,interval,(cfg.get('broadcaster_id'),cfg.get('twitch_client_id')))
        if mode!=self.viewer_mode:
            self.events.viewers.clear();self.viewer_updated=None;self.viewer_checked=None;self.viewer_error=False;self.viewer_mode=mode
            registry=self.registry()
            if registry:registry.clear_presence('twitch')
        return enabled,live,interval

    def presence_status(self):
        enabled,live,interval=self.presence_mode()
        return {'enabled':enabled,'live':live,'intervalMinutes':interval//60,
                'state':'preview' if self.io.dry_run else 'disabled' if not enabled else 'error' if self.viewer_error else 'ready' if self.viewer_checked else 'waiting',
                'checkedAt':self.viewer_checked}

    async def presence(self):
        if self.io.dry_run:return
        from .twitch_polling_triggers import present_users,presence_arguments
        from .twitch_channel import Channel
        from .twitch_user_info import UserInfo
        enabled,live,interval=self.presence_mode();mode=self.viewer_mode;registry=self.registry()
        if not enabled:return
        now=time.monotonic();due=interval if live else 60
        if not live:self.events.viewers={key:value for key,value in self.events.viewers.items() if time.time()-value.get('seenAt',0)<interval}
        if self.viewer_updated is not None and now-self.viewer_updated<due:return
        cache=UserInfo(self.io);before=cache.session()
        current=self.events.viewers
        if live:
            users=await present_users(self.io);current={}
            for user in users:
                uid=user['userId'];old=self.events.viewers.get(uid,{})
                current[uid]={'id':uid,'name':user['displayName'],'login':user['userName'],'platform':'Twitch','roles':old.get('roles',[]),'lastActive':old.get('lastActive',''),'seenAt':time.time()}
        stream=await Channel(self.io).read('stream');cache.check_session(before)
        self.presence_mode()
        if self.viewer_mode!=mode:return
        self.events.viewers=current;self.viewer_updated=now
        self.viewer_checked=datetime.fromtimestamp(time.time(),timezone.utc).isoformat(timespec="seconds");self.viewer_error=False
        if registry:registry.replace_presence('twitch',current.values(),ttl=max(60,interval*2 if live else 120))
        await self.emit(92701,presence_arguments(self.io,current,stream['online'],live))

    def chat_user(self,args,timestamp):
        enabled,live,interval=self.presence_mode()
        if enabled:
            self.events.viewers[args['userId'] or args['userLogin']]={'id':args['userId'],'name':args['user'],'login':args['userLogin'],'platform':'Twitch','roles':args['roles'],'lastActive':timestamp,'seenAt':time.time()}

    async def chat(self,event,args):
        cfg=self.io.config;text=args['message'];words=text.split()
        emotes=[self.emotes[word] for word in words if word in self.emotes and cfg.get('twitch_emotes_'+self.emotes[word]['provider'],True)]
        native={fragment['text'] for fragment in event.get('message',{}).get('fragments',[]) if fragment.get('type')=='emote'}
        args['emotes']=emotes;args['emoteCount']=len(emotes)+sum(word in native for word in words)
        valid=bool(words) and len(set(words))==1 and (words[0] in native or any(e['name']==words[0] for e in emotes))
        output=self.pyramids.ingest(event,args,valid,words[0] if words else '',len(words))
        # Progression and counters finish before yielding to user actions.
        for kind,values in output:await self.events.dispatcher.event(kind,values)

    @property
    def pyramid(self):return self.pyramids.state
    @pyramid.setter
    def pyramid(self,value):self.pyramids.state=value

    async def update(self,event=None,*,on_connect=False):
        account=(self.io.config.get('broadcaster_id'),self.io.config.get('twitch_client_id'))
        if event is None:
            reply=await self.io.twitch('GET','channels',params={'broadcaster_id':self.io.config['broadcaster_id']});event=next(iter(reply.get('data',[])),{})
        if account!=(self.io.config.get('broadcaster_id'),self.io.config.get('twitch_client_id')):return
        owner=event.get('broadcaster_user_id',event.get('broadcaster_id',account[0]))
        if not event or owner!=account[0]:return
        values=dict(event,title=event.get('title',''),gameId=event.get('category_id',event.get('game_id','')),gameName=event.get('category_name',event.get('game_name','')),broadcasterUserId=owner)
        if self.previous_channel_account==account and self.previous_channel:
            values.update(oldTitle=self.previous_channel['title'],oldGameId=self.previous_channel['gameId'],oldGameName=self.previous_channel['gameName'])
        values.update(status=values['title'],oldStatus=values.get('oldTitle',''),gameUpdate=values['gameId']!=values.get('oldGameId'),statusUpdate=values['title']!=values.get('oldTitle'))
        self.previous_channel_account=account;self.previous_channel={k:values[k] for k in ('title','gameId','gameName')}
        if on_connect:
            engine=getattr(self.events.dispatcher,'engine',None)
            if engine is not None:
                from .websocket_twitch_events import stream_initial
                stream_initial(engine,values)
        await self.events.dispatcher.event(90030,values)

    async def connected(self):
        self.pyramids.reset()
        await self.load_emotes()
        if self.io.config.get('twitch_update_on_connect',False):await self.update(on_connect=True)

    async def channel_status(self):
        if getattr(self.io,'dry_run',False):return
        from .twitch_channel import Channel
        cfg=self.io.config
        if not all(cfg.get(k) for k in ('twitch_token','twitch_client_id','broadcaster_id')):return
        account=(cfg['broadcaster_id'],cfg['twitch_client_id'])
        if account!=self.channel_account:self.channel_account=account;self.channel_checked=None;self.channel_count=None
        now=time.monotonic()
        if self.channel_checked is not None and now-self.channel_checked<60:return
        self.channel_checked=now;result=await Channel(self.io).read('stream');count=result['viewerCount']
        if count!=self.channel_count:
            initial=self.channel_count is None;self.channel_count=count
            await self.events.dispatcher.event(91252,dict(viewerCount=count,platform='twitch',userType='twitch',broadcasterUserId=cfg['broadcaster_id'],broadcasterUserName=cfg.get('twitch_login',''),broadcasterUser=cfg.get('twitch_login',''),isInitialSample=initial))

    async def run(self):
        while True:
            try:await self.polling.refresh(self)
            except (ActionError,OSError,ValueError,KeyError,TypeError) as exc:self.io.trace('twitch_polling_error',error=type(exc).__name__)
            try:await self.presence()
            except (ActionError,aiohttp.ClientError,OSError,ValueError,KeyError) as exc:
                self.io.trace('twitch_presence_error',error=str(exc) if isinstance(exc,ActionError) else type(exc).__name__)
                self.viewer_updated=time.monotonic();self.viewer_error=True
            try:await self.channel_status()
            except (ActionError,aiohttp.ClientError,OSError,ValueError,KeyError) as exc:self.io.trace('twitch_channel_error',error=str(exc) if isinstance(exc,ActionError) else type(exc).__name__)
            await asyncio.sleep(10)
