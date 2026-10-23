"""Validated scheduled-ad warnings, presence ticks and channel emote changes."""
import asyncio,copy,datetime as dt,math,re,time,urllib.parse
from dateutil.parser import isoparse
from .core import ActionError
from .twitch_expansion_events import Events,string,count
from .twitch_connections_whispers import broadcaster
from .twitch_user_info import UserInfo
ENTRIES={92700:('Ads · Upcoming Ad',{}),92701:('General · Present Viewers',{}),92702:('Emotes · BetterTTV Emote Added',{}),92703:('Emotes · BetterTTV Emote Removed',{}),92704:('Emotes · SevenTV Emote Added',{}),92705:('Emotes · SevenTV Emote Removed',{})}
ALIASES={92700:'twitch/ads/upcoming-ad',92701:'twitch/general/present-viewers',92702:'twitch/emotes/betterttv-emote-added',92703:'twitch/emotes/betterttv-emote-removed',92704:'twitch/emotes/seventv-emote-added',92705:'twitch/emotes/seventv-emote-removed'}
REMOVED={'twitch/community-goal/contribution','twitch/community-goal/ended'}

def ad_time(value):
 if value is None or value=='' or type(value) is int and value==0:return ''
 if type(value) is int:
  if value<0:raise ActionError('Ungültige Werbezeit')
  try:value=dt.datetime.fromtimestamp(value,dt.timezone.utc).isoformat()
  except (ValueError,OverflowError,OSError):raise ActionError('Ungültige Unix-Werbezeit') from None
 if not isinstance(value,str):raise ActionError('Ungültiger Werbezeitstempel')
 try:
  at=isoparse(value)
  if at.tzinfo is None:raise ValueError()
 except (ValueError,OverflowError):raise ActionError('Ungültiger Werbezeitstempel') from None
 return value

def schedule(reply,now):
 rows=reply.get('data') if isinstance(reply,dict) else None
 if not isinstance(rows,list) or len(rows)!=1 or not isinstance(rows[0],dict):raise ActionError('Kein eindeutiger Twitch-Werbezeitplan')
 row=rows[0]
 if 'next_ad_at' not in row:raise ActionError('Werbezeitplan ohne next_ad_at')
 stamp=ad_time(row['next_ad_at'])
 if not stamp:return None
 seconds=isoparse(stamp).timestamp()-now
 from .twitch_rewards import integer
 length=integer(row.get('duration',row.get('length_seconds')),0);snoozes=integer(row.get('snooze_count'),0)
 if length==0 or seconds<=0 or seconds>300:return None
 return {'minutes':math.ceil(seconds/60),'adLength':length,'snoozesLeft':snoozes,'nextAdAt':stamp}

async def present_users(io):
 from .twitch_user_selection import normalized
 from .twitch_rewards import scopes,integer
 cache=UserInfo(io);before=cache.session()
 if 'moderator:read:chatters' not in scopes(io.config):raise ActionError('moderator:read:chatters fehlt für Present Viewers')
 rows=[];cursor='';seen=set()
 for _ in range(1000):
  params={'broadcaster_id':before[0],'moderator_id':before[0],'first':1000}
  if cursor:params['after']=cursor
  reply=await io.twitch('GET','chat/chatters',params=params);cache.check_session(before)
  if not isinstance(reply,dict) or not isinstance(reply.get('data'),list) or not isinstance(reply.get('pagination'),dict):raise ActionError('Kein vollständiger Chatnutzerstand')
  integer(reply.get('total'),0);normalized(reply['data']);rows.extend(reply['data']);cursor=reply['pagination'].get('cursor','')
  if not isinstance(cursor,str) or cursor and cursor in seen:raise ActionError('Ungültiger oder wiederholter Chatnutzer-Cursor')
  if not cursor:break
  seen.add(cursor)
 else:raise ActionError('Chatnutzer-Abfrage überschreitet 1000 Seiten')
 normalized(rows);cache.save('present-users','channel',{'users':rows});return normalized(rows)

def emotes(provider,data):
 if not isinstance(data,dict):raise ActionError('Ungültiger Emote-Kanalstand')
 if provider=='bttv':
  if not isinstance(data.get('channelEmotes'),list) or not isinstance(data.get('sharedEmotes'),list):raise ActionError('Unvollständiger BetterTTV-Kanalstand')
  rows=data['channelEmotes']+data['sharedEmotes']
 else:
  if not isinstance(data.get('emotes'),list):raise ActionError('Unvollständiger 7TV-Emote-Set-Stand')
  rows=data['emotes']
 result={}
 for row in rows:
  if not isinstance(row,dict):raise ActionError('Ungültiges Anbieter-Emote')
  identity=string(row,'id');name=string(row,'code' if provider=='bttv' else 'name')
  if not re.fullmatch(r'[a-zA-Z0-9_-]+',identity):raise ActionError('Ungültige Anbieter-Emote-ID')
  image='https://cdn.betterttv.net/emote/'+identity+'/3x' if provider=='bttv' else 'https://cdn.7tv.app/emote/'+identity+'/4x.webp'
  if provider=='7tv' and isinstance(row.get('data'),dict) and row['data'].get('host') is not None:
   host=row['data']['host']
   if not isinstance(host,dict):raise ActionError('Ungültige 7TV-Bilddaten')
   url=string(host,'url');url='https:'+url if url.startswith('//') else url;parsed=urllib.parse.urlparse(url)
   if parsed.scheme!='https' or parsed.hostname!='cdn.7tv.app' or parsed.query or parsed.fragment:raise ActionError('Ungültige 7TV-Bildadresse')
   files=host.get('files')
   if not isinstance(files,list) or not files:raise ActionError('Unvollständige 7TV-Bilddateien')
   choices=[f for f in files if isinstance(f,dict) and isinstance(f.get('name'),str) and re.fullmatch(r'[a-zA-Z0-9_.-]+',f['name']) and type(f.get('width')) is int and f['width']>0]
   if len(choices)!=len(files):raise ActionError('Ungültige 7TV-Bilddatei')
   chosen=max(choices,key=lambda f:(f['name']=='4x.webp',f['width']));image=url.rstrip('/')+'/'+chosen['name']
  key=(identity,name);value={'id':identity,'name':name,'imageUrl':image}
  if type(row.get('zeroWidth')) is bool:value['zeroWidth']=row['zeroWidth']
  elif provider=='7tv' and isinstance(row.get('data'),dict) and type(row['data'].get('flags')) is int:value['zeroWidth']=bool(row['data']['flags']&256)
  if key in result and result[key]!=value:raise ActionError('Widersprüchlicher Emote-Kanalstand')
  result[key]=value
 return sorted(result.values(),key=lambda r:(r['id'],r['name']))

class Polling:
 def __init__(self,io):self.io=io;self.cache=UserInfo(io);self.checked={};self.mode=None;self.baseline=set();self.status={}
 def account(self):return self.cache.session()
 async def ad(self,now=None,online=None):
  if self.io.dry_run:return []
  from .twitch_rewards import scopes
  if 'channel:read:ads' not in scopes(self.io.config):raise ActionError('channel:read:ads fehlt für Upcoming Ad')
  before=self.account();reply=await self.io.twitch('GET','channels/ads',params={'broadcaster_id':before[0]});self.cache.check_session(before);args=schedule(reply,time.time() if now is None else now)
  if args is None:return []
  if online is None:
   from .twitch_channel import Channel
   online=(await Channel(self.io).read('stream'))['online'];self.cache.check_session(before)
  if type(online) is not bool:raise ActionError('Kein bestätigter Streamstatus für Upcoming Ad')
  if not online:return []
  args.update(broadcaster(self.io.config));identity=str(isoparse(args['nextAdAt']).timestamp())+':'+str(args['minutes']);mapped=Events(self.io).commit('upcoming-ad',identity,92700,args)
  return [mapped] if mapped else []
 async def read_emotes(self,provider,before):
  owner=urllib.parse.quote(before[0],safe='')
  if provider=='bttv':return emotes(provider,await self.io.http('GET','https://api.betterttv.net/3/cached/users/twitch/'+owner))
  data=await self.io.http('GET','https://7tv.io/v3/users/twitch/'+owner,headers={'X-7tv-Missing-EmoteSet-Aware':'1'})
  if not isinstance(data,dict):raise ActionError('Ungültige 7TV-Kanalantwort')
  if data.get('id') is not None and data['id']!=before[0]:raise ActionError('7TV-Kanalantwort gehört zu einem anderen Twitch-Konto')
  if isinstance(data.get('emote_set'),dict):return emotes(provider,data['emote_set'])
  if 'emote_set_id' not in data:raise ActionError('7TV-Kanalantwort ohne Emote-Set-Zuordnung')
  if data['emote_set_id'] is None:return []
  identity=string(data,'emote_set_id')
  if not re.fullmatch(r'[a-zA-Z0-9_-]+',identity):raise ActionError('Ungültige 7TV-Emote-Set-ID')
  reply=await self.io.http('GET','https://7tv.io/v3/emote-sets/'+identity)
  if not isinstance(reply,dict) or reply.get('id')!=identity:raise ActionError('7TV-Antwort gehört zu einem anderen Emote-Set')
  return emotes(provider,reply)
 def compare(self,provider,rows,reset=False):
  if self.io.dry_run:return []
  owner=self.cache.account()[0];kind='emote-membership:'+provider
  try:previous,_=self.cache.cached(kind,'channel')
  except ActionError:previous=None
  if previous is not None and (not isinstance(previous,dict) or type(previous.get('revision')) is not int or not isinstance(previous.get('emotes'),list)):raise ActionError('Ungültiger gespeicherter Emote-Vergleichsstand')
  revision=previous['revision']+1 if previous else 1
  old={(r['id'],r['name']):r for r in previous['emotes']} if previous and not reset else None;current={(r['id'],r['name']):r for r in rows};output=[]
  if old is not None:
   for change,keys in (('removed',old.keys()-current.keys()),('added',current.keys()-old.keys())):
    for key in sorted(keys):
     row=(old if change=='removed' else current)[key];args=broadcaster(self.io.config);args.update(emote=row['name'],emoteId=row['id'],imageUrl=row['imageUrl'],emoteProvider=provider,changeSource='polling')
     trigger=(92702 if provider=='bttv' else 92704)+(change=='removed');mapped=Events(self.io).commit('channel-emotes:'+provider,str(revision)+':'+change+':'+row['id']+':'+row['name'],trigger,args)
     if mapped:output.append(mapped)
  # Persist before user Actions, so the next refresh does not repeat the delta.
  self.cache.save(kind,'channel',{'revision':revision,'emotes':rows});return output
 async def channel_emotes(self,provider,reset=False):
  if self.io.dry_run or not self.io.config.get('twitch_emotes_'+provider,True):return [],None
  before=self.account()
  try:rows=await asyncio.wait_for(self.read_emotes(provider,before),10)
  except TimeoutError:raise ActionError('Emote-Anbieter antwortet nicht rechtzeitig') from None
  self.cache.check_session(before)
  if not self.io.config.get('twitch_emotes_'+provider,True):return [],None
  return self.compare(provider,rows,reset),rows
 async def refresh(self,features,force=False):
  if self.io.dry_run:return
  cfg=self.io.config;account=(cfg.get('broadcaster_id'),cfg.get('twitch_client_id'));now=time.monotonic()
  if account!=self.mode:self.checked={};self.baseline=set();self.mode=account;features.set_emote_account(account)
  for provider in ('bttv','7tv'):
   if not cfg.get('twitch_emotes_'+provider,True):self.baseline.add(provider);self.status[provider]={'state':'disabled'};continue
   if not force and provider in self.checked and now-self.checked[provider]<60:continue
   self.checked[provider]=now
   try:
    output,rows=await self.channel_emotes(provider,provider in self.baseline)
    if rows is None:self.baseline.add(provider);self.status[provider]={'state':'disabled'};continue
    self.baseline.discard(provider);features.channel_emotes(provider,rows);self.status[provider]={'state':'checked','count':len(rows)}
    for mapped in output:await features.emit(*mapped)
   except (ActionError,OSError,ValueError,KeyError,TypeError) as exc:self.status[provider]={'state':'unavailable'};self.io.trace('twitch_emotes_monitor_error',provider=provider,error=str(exc) if isinstance(exc,ActionError) else type(exc).__name__)
  if force or 'ads' not in self.checked or now-self.checked['ads']>=10:
   self.checked['ads']=now
   try:
    for mapped in await self.ad():await features.emit(*mapped)
    self.status['ads']={'state':'checked'}
   except (ActionError,OSError,ValueError,KeyError,TypeError) as exc:self.status['ads']={'state':'unavailable'};self.io.trace('twitch_upcoming_ad_error',error=str(exc) if isinstance(exc,ActionError) else type(exc).__name__)

def presence_arguments(io,viewers,online,live_update):
 if type(online) is not bool:raise ActionError('Kein bestätigter Streamstatus für Present Viewers')
 args=broadcaster(io.config);users=[]
 for row in sorted(viewers.values(),key=lambda r:(r['login'],r['id'])):
  users.append({'id':row['id'],'name':row['name'],'login':row['login'],'userId':row['id'],'userName':row['login'],'displayName':row['name'],'user':row['name'],'platform':'twitch','userType':'twitch','roles':copy.deepcopy(row.get('roles',[]))})
 args.update(users=users,isLive=online,isTest=False,presentUsersCount=len(users),presentUsersSource='chatters' if live_update else 'recent-chat');return args

def example(kind,config):
 cfg=dict(config);cfg.setdefault('broadcaster_id','test-broadcaster');cfg.setdefault('twitch_login','testbroadcaster')
 args=broadcaster(cfg)
 if kind==92700:args.update(minutes=5,adLength=60,snoozesLeft=2,nextAdAt='2026-10-14T12:05:00Z')
 elif kind==92701:args.update(presence_arguments(type('ExampleIO',(),{'config':cfg})(),{'test-user':{'id':'test-user','name':'Test User','login':'testuser','roles':[]}},True,False))
 else:
  provider='bttv' if kind in (92702,92703) else '7tv';args.update(emote='TestEmote',emoteId='test-emote',imageUrl=('https://cdn.betterttv.net/emote/test-emote/3x' if provider=='bttv' else 'https://cdn.7tv.app/emote/test-emote/4x.webp'),emoteProvider=provider,changeSource='manual test')
 return args
