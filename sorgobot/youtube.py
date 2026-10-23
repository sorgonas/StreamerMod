"""Independent YouTube session: desktop OAuth, broadcasts, resumable gRPC chat."""
import asyncio,copy,datetime as dt,json,time
from collections import OrderedDict
from aiohttp import ClientTimeout,ClientError
from .core import ActionError,expand
from .youtube_auth import API,YouTubeOAuth,YouTubeError
from .youtube_events import parse
from .catalog import ConfigStore
STEPS={96000:('Send Message to Channel',{'message':'Hallo %user%!','useBot':True,'fallback':True}),96001:('Chat · Delete Message',{'messageId':'%msgId%'}),96002:('Moderation · Timeout User',{'userId':'%userId%','duration':60}),96003:('Moderation · Ban User',{'userId':'%userId%'}),96004:('Moderation · Unban User',{'banId':''}),96010:('Set Title',{'broadcastId':'','title':''}),96011:('Set Description',{'broadcastId':'','description':''}),96012:('Set Title And Description',{'broadcastId':'','title':'','description':''})}
for _kind in (96000,96002,96003,96010,96011,96012):
 STEPS[_kind][1].update(broadcastMode='latest',broadcastId='')
def message_lines(message):
 if not isinstance(message,str):raise YouTubeError('Chatnachricht muss Text sein')
 lines=[line for line in message.splitlines() if line.strip()]
 if not lines or any(len(line)>200 or '\0' in line for line in lines):raise YouTubeError('Chatnachricht: je Zeile 1–200 Zeichen')
 return lines
class YouTube:
 def __init__(self,studio):
  self.studio=studio;self.auth=YouTubeOAuth(studio);self.bot_auth=YouTubeOAuth(studio,role='bot');self.task=None;self.phase='disconnected';self.error='';self.broadcasts=[];self.broadcast=None;self.messages=[];self.viewers={};self.seen=OrderedDict();self.page_token='';self.call=None;self.channel=None;self.monitor_started=0;self.session_chat_id='';self.watch_task=None;self.ended=False
  try:self.settings=ConfigStore(studio.root).read('youtube.json')
  except FileNotFoundError:self.settings={'broadcastId':'','autoConnect':False}
  if not isinstance(self.settings,dict):raise ActionError('Ungültige YouTube-Einstellungen')
  self.auto_connect=self.settings.get('autoConnect',False) is True
  self.metadata_lock=asyncio.Lock()
  from .youtube_extras import Extras
  self.extras=Extras(self)
 def status(self):return {'account':self.auth.status(),'botAccount':self.bot_auth.status(),'state':self.phase,'error':self.error,'broadcastId':self.broadcast.get('id','') if self.broadcast else '', 'title':self.broadcast.get('snippet',{}).get('title','') if self.broadcast else '', 'broadcasts':copy.deepcopy(self.broadcasts),'selectedBroadcast':self.settings.get('broadcastId',''),'autoConnect':self.auto_connect}
 async def request(self,method,path,*,params=None,body=None,auth=None):
  from .csharp_youtube import check_bound_account
  check_bound_account(self)
  self.auth.mutable()
  if path not in ('channels','liveBroadcasts','videos','videoCategories','liveChat/messages','liveChat/messages/transition','liveChat/bans'):raise ValueError('YouTube resource')
  sender=auth or self.auth;owner_identity=self.auth.identity();identity=sender.identity();token=await sender.access_token()
  for attempt in range(2 if method=='GET' else 1):
   if sender.identity()!=identity or self.auth.identity()!=owner_identity:raise YouTubeError('YouTube-Konto wurde geändert')
   try:
    async with self.studio.session.request(method,API+path,params=params,json=body,headers={'Authorization':'Bearer '+token},timeout=ClientTimeout(total=30)) as response:
     data=await response.json() if response.status!=204 else {}
     status=response.status
   except (ValueError,ClientError,TimeoutError):raise YouTubeError('Verbindungsfehler; Schreibanfrage nicht automatisch wiederholt') from None
   check_bound_account(self)
   if sender.identity()!=identity or self.auth.identity()!=owner_identity:raise YouTubeError('Konto während der Anfrage geändert; Ergebnis prüfen')
   if status==401 and method=='GET' and attempt==0:token=await sender.access_token(force=True);continue
   if status>=400:
    reason='API-Anfrage abgewiesen'
    if isinstance(data,dict):
     errors=data.get('error',{}).get('errors',[]) if isinstance(data.get('error'),dict) else []
     if isinstance(errors,list) and errors and isinstance(errors[0],dict) and isinstance(errors[0].get('reason'),str) and errors[0]['reason'].isalnum():reason=errors[0]['reason'][:80]
    raise YouTubeError(reason,status)
   if not isinstance(data,dict):raise YouTubeError('Ungültige API-Antwort')
   sender.state='valid';return data
 async def refresh_broadcasts(self):
  rows=[]
  for status in ('active','upcoming'):
   page='';seen_pages=set()
   while True:
    params={'part':'id,snippet,status','broadcastStatus':status,'broadcastType':'all','maxResults':50}
    if page:params['pageToken']=page
    data=await self.request('GET','liveBroadcasts',params=params)
    values=data.get('items')
    if not isinstance(values,list):raise YouTubeError('Ungültige Broadcast-Liste')
    rows.extend(values);page=data.get('nextPageToken','')
    if not page:break
    if not isinstance(page,str) or page in seen_pages:raise YouTubeError('Ungültige Broadcast-Paginierung')
    seen_pages.add(page)
  if not isinstance(rows,list):raise YouTubeError('Ungültige Broadcast-Liste')
  owner=self.auth.account.get('channelId');current=[]
  for row in rows:
   if not isinstance(row,dict) or not isinstance(row.get('snippet'),dict) or row['snippet'].get('channelId')!=owner:continue
   if not isinstance(row.get('status'),dict):continue
   if row.get('status',{}).get('lifeCycleStatus') not in ('live','liveStarting','testing','ready','created','testStarting'):continue
   if not isinstance(row.get('id'),str) or not row['id']:continue
   if any(r['id']==row['id'] for r in current):continue
   current.append({'id':row['id'],'snippet':{k:row['snippet'][k] for k in ('channelId','title','description','liveChatId','scheduledStartTime','actualStartTime') if isinstance(row['snippet'].get(k),str)},'status':{'lifeCycleStatus':row.get('status',{}).get('lifeCycleStatus')}})
  await self.extras.discovery(current)
  self.broadcasts=current;return current
 async def emit(self,kind,args):
  if isinstance(args.get('broadcastId'),str):args={**args,'broadcast.id':args['broadcastId']}
  await self.studio.dispatcher.event(kind,{**args,'platform':'youtube','userType':'youtube','youtubeChannelId':self.auth.account.get('channelId','')})
 async def start(self):
  if self.studio.live and self.auto_connect and self.auth.account.get('refresh_token'):await self.connect()
 async def connect(self):
  self.auth.mutable()
  if not self.auth.account.get('refresh_token'):raise YouTubeError('Zuerst das YouTube-Konto anmelden')
  if self.task and not self.task.done():return self.status()
  self.phase='connecting';self.error='';self.task=self.studio.spawn(self.run());return self.status()
 async def stop(self):
  task=self.task;self.task=None
  if task and task is not asyncio.current_task():task.cancel();await asyncio.gather(task,return_exceptions=True)
  self.phase='disconnected';self.broadcast=None;self.viewers={}
 async def close(self):await self.stop();await self.auth.cancel();await self.bot_auth.cancel()
 async def configure(self,broadcast,auto):
  self.auth.mutable()
  if not isinstance(broadcast,str) or len(broadcast)>200 or type(auto) is not bool:raise ValueError('YouTube settings')
  await self.stop();self.settings={'broadcastId':broadcast,'autoConnect':auto};self.auto_connect=auto;ConfigStore(self.studio.root).save('youtube.json',self.settings)
  if auto:await self.connect()
  return self.status()
 async def run(self):
  connected=False;identity=self.auth.identity();delay=5
  try:
   checked=await self.request('GET','channels',params={'part':'id','mine':'true'})
   if not any(r.get('id')==self.auth.account.get('channelId') for r in checked.get('items',[]) if isinstance(r,dict)):raise YouTubeError('Anmeldung gehört nicht zum gespeicherten YouTube-Kanal')
   connected=True;await self.emit(96050,{})
   while identity==self.auth.identity() and not self.studio.closing:
    try:
     await self.refresh_broadcasts();selected=self.settings.get('broadcastId','');active=[r for r in self.broadcasts if r['status']['lifeCycleStatus']=='live']
     chosen=next((r for r in self.broadcasts if r['id']==selected),None) if selected else active[0] if len(active)==1 else None
     if not chosen or not chosen['snippet'].get('liveChatId'):
      self.phase='select_broadcast' if not selected and len(active)>1 else 'waiting';self.error='';await asyncio.sleep(60);continue
     self.broadcast=chosen;self.phase='connected';self.error='';self.ended=False
     initial=chosen['snippet']['liveChatId']!=self.session_chat_id
     if initial:self.session_chat_id=chosen['snippet']['liveChatId'];self.seen.clear();self.page_token='';self.monitor_started=time.time()
     args={'broadcastId':chosen['id'],'liveChatId':chosen['snippet']['liveChatId'],'title':chosen['snippet'].get('title','')}
     await self.emit(4019,args)
     if initial and chosen['status']['lifeCycleStatus']=='live':await self.emit(4001,{**args,'isInitialState':True})
     self.watch_task=asyncio.create_task(self.watch_broadcast(chosen,identity))
     try:await self.monitor(identity)
     finally:
      self.watch_task.cancel();await asyncio.gather(self.watch_task,return_exceptions=True);self.watch_task=None
      await self.emit(4020,args)
     self.broadcast=None;self.viewers={};delay=5
    except YouTubeError as exc:
     self.error=str(exc);self.phase='quota_exceeded' if exc.reason in ('quotaExceeded','dailyLimitExceeded') else 'error'
     if exc.reason in ('liveChatEnded','liveChatDisabled','LIVE_CHAT_ENDED','LIVE_CHAT_DISABLED'):
      if self.broadcast and exc.reason in ('liveChatEnded','LIVE_CHAT_ENDED'):await self.emit(4002,{'broadcastId':self.broadcast['id'],'liveChatId':self.broadcast['snippet']['liveChatId']})
      self.broadcast=None;self.viewers={}
     await asyncio.sleep(300 if self.phase=='quota_exceeded' else delay);delay=min(delay*2,120)
  except YouTubeError as exc:self.phase='error';self.error=str(exc)
  finally:
   if self.call:self.call.cancel();self.call=None
   if self.channel:await self.channel.close();self.channel=None
   self.viewers={}
   if connected:await self.emit(96051,{})
 async def watch_broadcast(self,chosen,identity):
  previous=chosen['status']['lifeCycleStatus'];args={'broadcastId':chosen['id'],'liveChatId':chosen['snippet']['liveChatId'],'title':chosen['snippet'].get('title','')}
  while identity==self.auth.identity() and not self.studio.closing:
   await asyncio.sleep(60)
   try:
    reply=await self.request('GET','liveBroadcasts',params={'part':'id,snippet,status','id':chosen['id']})
    rows=reply.get('items',[])
    row=next((r for r in rows if isinstance(r,dict) and r.get('id')==chosen['id'] and r.get('snippet',{}).get('channelId')==self.auth.account.get('channelId')),None)
    if row is None:continue
    current=row.get('status',{}).get('lifeCycleStatus')
    if current=='live' and previous!='live':await self.emit(4001,{**args,'isInitialState':False})
    if current in ('complete','revoked'):
     if previous=='live':await self.emit(4002,args)
     self.ended=True
     if self.call:self.call.cancel()
     return
    previous=current
    await self.refresh_broadcasts()
    await self.extras.stats(chosen['id'])
   except YouTubeError as exc:self.error=str(exc)
 async def stream(self,token):
  try:
   import grpc
   from google.protobuf.json_format import MessageToDict
   from .youtube_proto import stream_list_pb2 as pb
  except ImportError:raise YouTubeError('YouTube-Streaming-Abhängigkeiten fehlen; requirements-youtube.txt installieren') from None
  self.channel=grpc.aio.secure_channel('youtube.googleapis.com:443',grpc.ssl_channel_credentials(),options=[('grpc.max_receive_message_length',4*1024*1024)])
  method=self.channel.unary_stream('/youtube.api.v3.V3DataLiveChatMessageService/StreamList',request_serializer=pb.LiveChatMessageListRequest.SerializeToString,response_deserializer=pb.LiveChatMessageListResponse.FromString)
  request=pb.LiveChatMessageListRequest(live_chat_id=self.broadcast['snippet']['liveChatId'],part=['id','snippet','authorDetails'],hl='de',page_token=self.page_token)
  self.call=method(request,metadata=(('authorization','Bearer '+token),),timeout=2700)
  types={'POLL_EVENT':'pollEvent','GIFT_EVENT':'giftEvent','TEXT_MESSAGE_EVENT':'textMessageEvent','TOMBSTONE':'tombstone','CHAT_ENDED_EVENT':'chatEndedEvent','SPONSOR_ONLY_MODE_STARTED_EVENT':'sponsorOnlyModeStartedEvent','SPONSOR_ONLY_MODE_ENDED_EVENT':'sponsorOnlyModeEndedEvent','NEW_SPONSOR_EVENT':'newSponsorEvent','MEMBER_MILESTONE_CHAT_EVENT':'memberMilestoneChatEvent','MEMBERSHIP_GIFTING_EVENT':'membershipGiftingEvent','GIFT_MEMBERSHIP_RECEIVED_EVENT':'giftMembershipReceivedEvent','USER_BANNED_EVENT':'userBannedEvent','SUPER_CHAT_EVENT':'superChatEvent','SUPER_STICKER_EVENT':'superStickerEvent'}
  try:
   async for packet in self.call:
    value=MessageToDict(packet)
    for item in [*value.get('items',[]),*([value['activePollItem']] if isinstance(value.get('activePollItem'),dict) else [])]:
     snippet=item.get('snippet',{});snippet['type']=types.get(snippet.get('type'),snippet.get('type'))
     ban=snippet.get('userBannedDetails')
     if isinstance(ban,dict):ban['banType']=str(ban.get('banType','')).lower()
    yield value
  except asyncio.CancelledError:
   if self.ended and not asyncio.current_task().cancelling():return
   raise
  except grpc.aio.AioRpcError as exc:
   if self.ended:return
   status=exc.code();reason={grpc.StatusCode.UNAUTHENTICATED:'Token abgelaufen',grpc.StatusCode.RESOURCE_EXHAUSTED:'quotaExceeded',grpc.StatusCode.PERMISSION_DENIED:'forbidden',grpc.StatusCode.FAILED_PRECONDITION:'Chat nicht mehr verfügbar',grpc.StatusCode.NOT_FOUND:'liveChatNotFound'}.get(status,'Chatverbindung unterbrochen')
   raise YouTubeError(reason) from None
  finally:
   self.call=None
   if self.channel:await self.channel.close();self.channel=None
 async def monitor(self,identity):
  delay=2
  while identity==self.auth.identity() and not self.studio.closing and not self.ended:
   try:
    token=await self.auth.access_token()
    async for packet in self.stream(token):
     if identity!=self.auth.identity():return
     if not isinstance(packet,dict) or not isinstance(packet.get('items',[]),list):raise YouTubeError('Ungültiges Chatpaket')
     for item in packet.get('items',[]):
      if not isinstance(item,dict) or not isinstance(item.get('snippet'),dict):raise YouTubeError('Ungültige Chatnachricht')
      if item.get('snippet',{}).get('type')=='chatEndedEvent':raise YouTubeError('liveChatEnded')
      try:await self.ingest(item)
      except ActionError:
       self.error='Ungültiges YouTube-Ereignis verworfen'
       self.studio.io.trace('youtube_invalid_event',message=self.error)
     if isinstance(packet.get('activePollItem'),dict):
      try:await self.ingest(packet['activePollItem'])
      except ActionError:self.error='Ungültiges YouTube-Umfrageereignis verworfen'
     if isinstance(packet.get('nextPageToken'),str):self.page_token=packet['nextPageToken']
     if packet.get('offlineAt'):raise YouTubeError('liveChatEnded')
     delay=2
    await asyncio.sleep(delay)
   except YouTubeError as exc:
    if exc.reason=='Token abgelaufen':await self.auth.access_token(force=True)
    elif exc.reason in ('quotaExceeded','forbidden','liveChatEnded','liveChatDisabled','Chat nicht mehr verfügbar','liveChatNotFound'):raise
    self.error=str(exc);self.phase='reconnecting';await asyncio.sleep(delay);delay=min(delay*2,60)
   else:self.phase='connected';self.error=''
 async def ingest(self,item):
  if self.studio.io.dry_run or not self.broadcast:return
  if isinstance(item,dict) and item.get('snippet',{}).get('type')=='pollEvent':
   await self.extras.poll(item);return
  mapped=parse(item,self.auth.account['channelId'],self.broadcast['id'],self.broadcast['snippet']['liveChatId'])
  if mapped is None:return
  kind,args,row,stamp=mapped;identity=(args['liveChatId'],args['messageId'])
  if kind==4030:
   await self.extras.gift(args,stamp);return
  if identity in self.seen:return
  self.seen[identity]=True
  while len(self.seen)>10000:self.seen.popitem(last=False)
  self.messages.append(row);self.messages=self.messages[-1000:]
  if stamp<self.monitor_started:return # Display initial history without replaying Actions/Commands.
  if kind==4003:
   from .internal_chat import matches
   args['isInternal']=await matches(self.studio,{'broadcaster_user_id':'youtube:'+args['liveChatId'],'chatter_user_id':args['userId'],'message_id':args['messageId'],'message':{'text':args['message']}})
   if args['userId']:
    self.viewers[args['userId']]={'id':args['userId'],'login':args['userId'],'name':args['user'],'platform':'YouTube','roles':args['roles'],'lastActive':args['publishedAt'],'seenAt':time.time()}
   await self.studio.dispatcher.chat(args)
  await self.studio.dispatcher.event(kind,args)
 def active_viewers(self):return [copy.deepcopy(r) for r in self.viewers.values() if time.time()-r['seenAt']<=300]
 def live_chat(self):
  self.auth.mutable()
  if not self.broadcast or self.phase not in ('connected','reconnecting'):raise YouTubeError('Kein YouTube-Livechat verbunden; Broadcast auswählen oder starten')
  return self.broadcast['snippet']['liveChatId']
 async def chat_target(self,broadcast_id=None):
  if broadcast_id is None or broadcast_id=='':return self.live_chat()
  self.auth.mutable()
  if not isinstance(broadcast_id,str) or not broadcast_id.strip() or len(broadcast_id)>200:raise YouTubeError('Ungültige Broadcast-ID')
  if self.broadcast and broadcast_id==self.broadcast['id']:return self.live_chat()
  result=await self.request('GET','liveBroadcasts',params={'part':'snippet,status','id':broadcast_id})
  rows=result.get('items',[])
  if not isinstance(rows,list):raise YouTubeError('Ungültige Broadcast-Antwort')
  rows=[r for r in rows if isinstance(r,dict) and r.get('id')==broadcast_id and isinstance(r.get('snippet'),dict) and r['snippet'].get('channelId')==self.auth.account.get('channelId')]
  if len(rows)!=1 or not isinstance(rows[0]['snippet'].get('liveChatId'),str) or not rows[0]['snippet']['liveChatId']:raise YouTubeError('Eigener Livechat nicht eindeutig verfügbar')
  if rows[0].get('status',{}).get('lifeCycleStatus') not in ('live','ready','testing','liveStarting','testStarting'):raise YouTubeError('Livechat ist nicht aktiv')
  return rows[0]['snippet']['liveChatId']
 async def send(self,message,internal=False,use_bot=True,fallback=True,broadcast_id=None):
  chat=await self.chat_target(broadcast_id)
  if type(use_bot) is not bool or type(fallback) is not bool:raise YouTubeError('Ungültige Bot-Auswahl')
  sender=self.bot_auth if use_bot and self.bot_auth.account.get('refresh_token') else self.auth
  if use_bot and sender is self.auth and not fallback:raise YouTubeError('YouTube-Bot ist nicht angemeldet')
  if not isinstance(message,str) or not message.strip() or len(message)>200 or any(c in message for c in ('\0','\r','\n')):raise YouTubeError('Chatnachricht: 1–200 Zeichen, eine Zeile')
  from .internal_chat import begin,finish
  reservation=begin(self.studio,'youtube:'+chat,sender.account['channelId'],message) if internal else None
  try:
   result=await self.request('POST','liveChat/messages',auth=sender,params={'part':'snippet'},body={'snippet':{'liveChatId':chat,'type':'textMessageEvent','textMessageDetails':{'messageText':message}}})
   if not isinstance(result.get('id'),str) or not result['id']:raise YouTubeError('Nachrichtenbestätigung fehlt; nicht automatisch wiederholen')
   if reservation:finish(self.studio,reservation,result['id'])
   return result['id']
  finally:
   if reservation:finish(self.studio,reservation)
 async def set_metadata(self,broadcast_id='',*,title=None,description=None,privacy=None,tags=None,category_id=None,tag_mode='set'):
  """Read before updating snippet, preserving unrelated writable fields."""
  self.auth.mutable()
  if title is not None and (not isinstance(title,str) or not title.strip() or len(title)>100 or any(c in title for c in ('<','>','\0'))):raise YouTubeError('Titel: 1–100 Zeichen, ohne < und >')
  if description is not None and (not isinstance(description,str) or len(description.encode('utf-8'))>5000 or any(c in description for c in ('<','>','\0'))):raise YouTubeError('Beschreibung: maximal 5000 UTF-8-Bytes, ohne < und >')
  if privacy is not None and privacy not in ('public','private','unlisted'):raise YouTubeError('Ungültige Sichtbarkeit')
  if tags is not None and (not isinstance(tags,list) or any(not isinstance(t,str) or not t.strip() or any(c in t for c in ('<','>','\0')) for t in tags) or sum(len(t)+(2 if ' ' in t else 0) for t in tags)+max(0,len(tags)-1)>500):raise YouTubeError('Ungültige Videotags oder mehr als 500 Zeichen')
  if category_id is not None and (not isinstance(category_id,str) or not category_id.isdigit()):raise YouTubeError('Ungültige Videokategorie')
  if all(v is None for v in (title,description,privacy,tags,category_id)):raise YouTubeError('Keine Änderung angegeben')
  if not isinstance(broadcast_id,str):raise YouTubeError('Ungültige Broadcast-ID')
  async with self.metadata_lock:
   identity=self.auth.identity()
   target=broadcast_id or (self.broadcast or {}).get('id') or self.settings.get('broadcastId','')
   if not target:
    rows=await self.refresh_broadcasts()
    if len(rows)!=1:raise YouTubeError('Broadcast-ID angeben: kein eindeutiger eigener Broadcast')
    target=rows[0]['id']
   result=await self.request('GET','videos',params={'part':'snippet,status' if privacy is not None else 'snippet','id':target})
   rows=result.get('items',[])
   if not isinstance(rows,list):raise YouTubeError('Ungültige Videoantwort')
   row=next((r for r in rows if isinstance(r,dict) and r.get('id')==target),None)
   snippet=row.get('snippet') if row else None
   if not isinstance(snippet,dict) or snippet.get('channelId')!=self.auth.account.get('channelId'):raise YouTubeError('Broadcast gehört nicht zum angemeldeten Kanal')
   writable=('title','description','tags','categoryId','defaultLanguage','defaultAudioLanguage')
   update={k:copy.deepcopy(snippet[k]) for k in writable if k in snippet}
   if not isinstance(update.get('categoryId'),str) or not update['categoryId']:raise YouTubeError('Videokategorie fehlt; Änderung abgebrochen')
   if title is not None:update['title']=title
   if description is not None:update['description']=description
   if tags is not None:
    original=update.get('tags',[])
    if not isinstance(original,list) or any(not isinstance(t,str) for t in original):raise YouTubeError('Ungültige vorhandene Tags')
    if tag_mode=='set':update['tags']=list(tags)
    elif tag_mode=='add':
     update['tags']=list(original);known={t.casefold() for t in original}
     for tag in tags:
      if tag.casefold() not in known:update['tags'].append(tag);known.add(tag.casefold())
    elif tag_mode=='remove':update['tags']=[t for t in original if t.casefold() not in {v.casefold() for v in tags}]
    else:raise YouTubeError('Unbekannte Tagoperation')
    if sum(len(t)+(2 if ' ' in t else 0) for t in update['tags'])+max(0,len(update['tags'])-1)>500:raise YouTubeError('Videotags überschreiten 500 Zeichen')
   if category_id is not None:update['categoryId']=category_id
   body={'id':target};parts=[]
   if any(v is not None for v in (title,description,tags,category_id)):body['snippet']=update;parts.append('snippet')
   if privacy is not None:
    status=row.get('status')
    if not isinstance(status,dict) or not isinstance(status.get('privacyStatus'),str):raise YouTubeError('Vorhandene Sichtbarkeit fehlt; Änderung abgebrochen')
    body['status']={k:copy.deepcopy(status[k]) for k in ('privacyStatus','license','embeddable','publicStatsViewable','publishAt','selfDeclaredMadeForKids','containsSyntheticMedia') if k in status}
    body['status']['privacyStatus']=privacy
    if privacy!='private':body['status'].pop('publishAt',None)
    parts.append('status')
   if identity!=self.auth.identity():raise YouTubeError('YouTube-Konto wurde geändert')
   reply=await self.request('PUT','videos',params={'part':','.join(parts)},body=body)
   if reply.get('id')!=target:raise YouTubeError('Änderungsbestätigung fehlt; Ergebnis prüfen')
   for cached in self.broadcasts+([self.broadcast] if self.broadcast else []):
    if cached.get('id')==target:
     for key,value in (('title',title),('description',description)):
      if value is not None:cached.setdefault('snippet',{})[key]=value
   return target
 async def moderate(self,operation,identity,duration=60,broadcast_id=None):
  chat=await self.chat_target(broadcast_id)
  if not isinstance(identity,str) or not identity or len(identity)>500:raise YouTubeError('YouTube-Ziel-ID fehlt')
  if operation=='delete':return await self.request('DELETE','liveChat/messages',params={'id':identity})
  if operation=='unban':return await self.request('DELETE','liveChat/bans',params={'id':identity})
  if operation not in ('ban','timeout'):raise ValueError('Moderation')
  if operation=='timeout' and (type(duration) is not int or not 1<=duration<=86400):raise YouTubeError('Timeout: 1–86400 Sekunden')
  snippet={'liveChatId':chat,'type':'temporary' if operation=='timeout' else 'permanent','bannedUserDetails':{'channelId':identity}}
  if operation=='timeout':snippet['banDurationSeconds']=duration
  result=await self.request('POST','liveChat/bans',params={'part':'snippet'},body={'snippet':snippet})
  if not isinstance(result.get('id'),str) or not result['id']:raise YouTubeError('Sperrbestätigung fehlt; Ergebnis prüfen')
  return result
async def operation(io,node,args):
 service=getattr(getattr(getattr(io,'engine',None),'studio',None),'youtube',None)
 if io.dry_run:io.trace('youtube_preview',operation=node['type']);args['isPreview']=True;return
 if service is None:raise YouTubeError('YouTube-Laufzeit fehlt')
 n={k:expand(v,args) for k,v in node.items()};kind=n['type']
 from .youtube_targets import target
 if kind in (96002,96003):
  args['timeoutResult' if kind==96002 else 'banResult']=False;args['youtubeBanId']=''
  prefix='timedOutUser' if kind==96002 else 'bannedUser'
  for suffix in ('','Id','Name','Type'):args[prefix+suffix]=''
 if kind in (96010,96012):args['titleSuccess']=False
 if kind in (96011,96012):args['descriptionSuccess']=False
 bid=target(service,n,args) if kind in (96000,96002,96003,96010,96011,96012) else None
 if kind in (96010,96011,96012):
  args['youtubeBroadcastId']=await service.set_metadata(bid,title=n.get('title','') if kind in (96010,96012) else None,description=n.get('description','') if kind in (96011,96012) else None)
  if kind in (96010,96012):args['titleSuccess']=True
  if kind in (96011,96012):args['descriptionSuccess']=True
 elif kind==96000:
  lines=message_lines(n.get('message',''));args['youtubeMessageIds']=[]
  for line in lines:
   mid=await service.send(line,internal=True,use_bot=n.get('useBot',True),fallback=n.get('fallback',True),broadcast_id=bid)
   args['youtubeMessageIds'].append(mid);args['youtubeMessageId']=mid
 else:
  op={96001:'delete',96002:'timeout',96003:'ban',96004:'unban'}[kind]
  result=await service.moderate(op,n.get('messageId' if op=='delete' else 'banId' if op=='unban' else 'userId',''),int(n.get('duration',60)),**({'broadcast_id':bid} if bid is not None else {}))
  if op in ('ban','timeout'):
   args['youtubeBanId']=result['id'];args['timeoutResult' if op=='timeout' else 'banResult']=True
   uid=n.get('userId','');display=args.get('user','') if args.get('platform')=='youtube' and args.get('userId')==uid else ''
   prefix='timedOutUser' if op=='timeout' else 'bannedUser'
   args.update({prefix:display,prefix+'Id':uid,prefix+'Name':uid,prefix+'Type':'youtube'})
