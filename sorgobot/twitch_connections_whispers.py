"""Account-specific Whisper delivery and confirmed connection transitions."""
import asyncio,collections,copy
import aiohttp
from .core import ActionError
from .twitch_expansion_events import Events,string,person,put_user
from .twitch_shared_chat import base
ENTRIES={
92600:('Connections · Broadcaster Authenticated',{}),
92601:('Connections · Broadcaster Chat Connected',{}),92602:('Connections · Broadcaster Chat Disconnected',{}),
92603:('Connections · Broadcaster EventSub Connected',{}),92604:('Connections · Broadcaster EventSub Disconnected',{}),
92605:('Connections · Bot Chat Connected',{}),92606:('Connections · Bot Chat Disconnected',{}),
92609:('Connections · Bot EventSub Connected',{}),92610:('Connections · Bot EventSub Disconnected',{}),
92607:('Chat · Whispers',{}),92608:('Chat · Bot Whispers',{}),
}
ALIASES={kind:'twitch/'+('chat/' if kind in (92607,92608) else 'connections/')+label.split(' · ')[1].lower().replace(' ','-') for kind,(label,_) in ENTRIES.items()}
WHISPER_TYPE='user.whisper.message';WHISPER_RIGHTS={'user:read:whispers','user:manage:whispers'}

def broadcaster(config):
 return base({'broadcaster_user_id':config.get('broadcaster_id'),'broadcaster_user_login':config.get('twitch_login'),'broadcaster_user_name':config.get('twitch_display_name') or config.get('twitch_login')})

def confirmed(kind,condition,reply):
 rows=reply.get('data') if isinstance(reply,dict) else None
 return isinstance(rows,list) and len(rows)==1 and isinstance(rows[0],dict) and rows[0].get('type')==kind and rows[0].get('version')=='1' and rows[0].get('status')=='enabled' and rows[0].get('condition')==condition

def whisper_variables(config,event,bot=False):
 receiver=config.get('bot_id' if bot else 'broadcaster_id')
 if not isinstance(event,dict) or not receiver or event.get('to_user_id')!=receiver:return None
 args=broadcaster(config);sender=person(event,'from_user_');target=person(event,'to_user_');put_user(args,sender)
 content=event.get('whisper')
 if not isinstance(content,dict):raise ActionError('Whisper-Nachricht fehlt')
 message=string(content,'text',True);identity=string(event,'whisper_id')
 args.update(commandSource='twitch',commandType='whisper',roles=['Broadcaster'] if sender['Id']==config.get('broadcaster_id') else [],whisperId=identity,messageId=identity,message=message,rawInput=message,input0='',isWhisper=True,receivingAccount='Bot' if bot else 'Broadcaster',receiverUserId=target['Id'],receiverUserName=target['Name'],receiverUser=target[''])
 for index,word in enumerate(message.split()):args['input'+str(index)]=word
 return (92608 if bot else 92607),args

def ingest(io,event,identity,bot=False):
 if io.dry_run:return None
 mapped=whisper_variables(io.config,event,bot)
 if not mapped:return None
 return Events(io).commit(WHISPER_TYPE+':'+mapped[1]['receiverUserId'],identity,*mapped)

class Connections:
 def __init__(self,io,dispatcher,spawn=None):
  self.io=io;self.dispatcher=dispatcher;self.spawn=spawn;self.states={'eventsub':False,'broadcasterChat':False,'botChat':False,'botEventsub':False};self.context={}
 async def emit(self,trigger,args):
  owner=getattr(self.spawn,'__self__',None)
  if getattr(owner,'closing',False):return
  if self.spawn:self.spawn(self.dispatcher.event(trigger,args))
  else:await self.dispatcher.event(trigger,args)
 def snapshot(self):return dict(self.states)
 async def change(self,stream,connected,reason=''):
  if stream not in self.states or type(connected) is not bool:raise ActionError('Ungültiger Twitch-Verbindungszustand')
  if self.io.dry_run or self.states[stream]==connected:return
  if connected:
   args=broadcaster(self.io.config);bot=stream in ('botChat','botEventsub');identity=self.io.config.get('bot_id' if bot else 'broadcaster_id');login=self.io.config.get('twitch_bot_login' if bot else 'twitch_login')
   if not identity or not login:raise ActionError('Twitch-Verbindung ohne gültige Kontoidentität')
   args.update(connectionAccount='Bot' if bot else 'Broadcaster',connectionType='EventSub' if stream in ('eventsub','botEventsub') else 'Chat',connectionUserId=identity,connectionUserName=login)
   self.context[stream]=args
  args=copy.deepcopy(self.context[stream]);self.states[stream]=connected;args.update(connected=connected,reason=reason)
  trigger={'eventsub':(92603,92604),'broadcasterChat':(92601,92602),'botChat':(92605,92606),'botEventsub':(92609,92610)}[stream][0 if connected else 1]
  await self.emit(trigger,args)
 async def reset_broadcaster(self,reason=''):
  await self.change('broadcasterChat',False,reason);await self.change('eventsub',False,reason)
 async def authenticated(self,account):
  if self.io.dry_run or account.get('user_id')!=self.io.config.get('broadcaster_id'):return
  args=broadcaster(self.io.config);args.update(authenticated=True,connectionAccount='Broadcaster',connectionUserId=account['user_id'],connectionUserName=account['login']);await self.emit(92600,args)

class BotEvents:
 """A separate WebSocket owned by the Bot token; never dispatches channel chat."""
 def __init__(self,io,dispatcher,connections):
  self.io=io;self.dispatcher=dispatcher;self.connections=connections;self.status='offline';self.subscription_status={};self.seen=collections.OrderedDict()
 async def subscriptions(self,session):
  cfg=self.io.config;granted=set(cfg.get('twitch_bot_scopes',[]));self.subscription_status={}
  for kind,condition,rights in [('channel.chat.message',{'broadcaster_user_id':cfg.get('broadcaster_id'),'user_id':cfg.get('bot_id')},{'user:read:chat'}),(WHISPER_TYPE,{'user_id':cfg.get('bot_id')},WHISPER_RIGHTS)]:
   if not all(condition.values()):self.subscription_status[kind]={'state':'missing_account'};continue
   if not granted & rights:self.subscription_status[kind]={'state':'missing_scope','message':' oder '.join(sorted(rights))+' fehlt'};continue
   try:
    reply=await self.io.twitch('POST','eventsub/subscriptions',{'type':kind,'version':'1','condition':condition,'transport':{'method':'websocket','session_id':session}},bot=True)
    if not confirmed(kind,condition,reply):raise ActionError('Bot-EventSub-Anmeldung wurde nicht vollständig bestätigt')
    self.subscription_status[kind]={'state':'enabled'}
   except ActionError:self.subscription_status[kind]={'state':'error','message':'Bot-EventSub-Anmeldung fehlgeschlagen'}
  await self.connections.change('botChat',self.subscription_status.get('channel.chat.message',{}).get('state')=='enabled')
  if not any(row['state']=='enabled' for row in self.subscription_status.values()):raise ActionError('Keine Bot-EventSub-Anmeldung bestätigt')
 async def connect(self,url,subscribe):
  socket=await self.io.session.ws_connect(url,autoping=True)
  try:
   welcome=await asyncio.wait_for(socket.receive_json(),15)
   if welcome.get('metadata',{}).get('message_type')!='session_welcome':raise ActionError('Bot EventSub Welcome fehlt')
   session=welcome['payload']['session']
   if subscribe:await self.subscriptions(session['id'])
   if subscribe:await self.connections.change('botEventsub',True)
   return socket,(session.get('keepalive_timeout_seconds') or 10)+5
  except BaseException:await socket.close();raise
 async def notification(self,kind,event,identity):
  if kind!=WHISPER_TYPE:return # Broadcaster connection already routes channel messages.
  mapped=ingest(self.io,event,identity,True)
  if mapped:await dispatch_whisper(self.dispatcher,mapped)
 async def run(self):
  if self.io.dry_run:return
  while True:
   socket=None
   try:
    socket,timeout=await self.connect('wss://eventsub.wss.twitch.tv/ws',True);self.status='connected'
    while True:
     message=await asyncio.wait_for(socket.receive(),timeout)
     if message.type!=aiohttp.WSMsgType.TEXT:raise ActionError('Bot-Verbindung getrennt')
     body=message.json();meta=body['metadata'];kind=meta['message_type']
     if kind=='session_reconnect':
      replacement,timeout=await self.connect(body['payload']['session']['reconnect_url'],False);await socket.close();socket=replacement
     elif kind=='revocation':
      event=body['payload']['subscription'];event_type=event['type'];self.subscription_status[event_type]={'state':'revoked'}
      if event_type=='channel.chat.message':await self.connections.change('botChat',False,'revoked')
     elif kind=='notification':
      identity=meta['message_id']
      if identity in self.seen:continue
      notification=self.notification(body['payload']['subscription']['type'],body['payload']['event'],identity)
      if self.connections.spawn:self.connections.spawn(notification)
      else:await notification
      self.seen[identity]=True
      if len(self.seen)>5000:self.seen.popitem(last=False)
   except (aiohttp.ClientError,OSError,ValueError,KeyError,ActionError,TimeoutError):self.status='Bot-Verbindung fehlgeschlagen'
   finally:
    try:
     await self.connections.change('botChat',False,'disconnected')
     await self.connections.change('botEventsub',False,'disconnected')
    finally:
     if socket:await socket.close()
    self.status='offline'
   await asyncio.sleep(10)

def example(kind,config):
 cfg=dict(config);cfg.setdefault('broadcaster_id','test-broadcaster');cfg.setdefault('twitch_login','testbroadcaster');cfg.setdefault('bot_id','test-bot');cfg.setdefault('twitch_bot_login','testbot')
 if kind in (92607,92608):
  bot=kind==92608;event={'from_user_id':'test-sender','from_user_login':'testsender','from_user_name':'Test Sender','to_user_id':cfg['bot_id' if bot else 'broadcaster_id'],'to_user_login':cfg['twitch_bot_login' if bot else 'twitch_login'],'to_user_name':'Test Receiver','whisper_id':'test-whisper','whisper':{'text':'Test private message'}};return whisper_variables(cfg,event,bot)[1]
 args=broadcaster(cfg);bot=kind in (92605,92606,92609,92610);args.update(connectionAccount='Bot' if bot else 'Broadcaster',connectionUserId=cfg['bot_id' if bot else 'broadcaster_id'],connectionUserName=cfg['twitch_bot_login' if bot else 'twitch_login'])
 if kind==92600:args['authenticated']=True
 else:args.update(connectionType='EventSub' if kind in (92603,92604,92609,92610) else 'Chat',connected=kind in (92601,92603,92605,92609),reason='manual test')
 return args

async def dispatch_whisper(dispatcher,mapped):
 await dispatcher.event(*mapped)
 chat=getattr(dispatcher,'chat',None)
 if chat:await chat(mapped[1])
