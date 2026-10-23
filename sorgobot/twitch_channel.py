"""Read-only channel overview, cached preview and stream event adapters."""
import json,sqlite3,time
import aiohttp
from contextlib import closing
from .core import ActionError
from .twitch_rewards import scopes,integer
STEPS={91200:'Add Viewer Count',91201:'Get Follower Count',91202:'Get Latest Follower'}
TRIGGERS={91250:'Stream Online',91251:'Stream Offline',91252:'Viewer Count Update'}
class Channel:
 def __init__(self,io):self.io=io
 def key(self):
  cfg=self.io.config
  if not cfg.get('broadcaster_id') or not cfg.get('twitch_client_id'):raise ActionError('Broadcaster-Konto zuerst einrichten')
  return cfg['broadcaster_id']+'|'+cfg['twitch_client_id']
 def db(self):
  path=self.io.root/'state/twitch-channel.sqlite3';path.parent.mkdir(parents=True,exist_ok=True);db=sqlite3.connect(path,timeout=10);db.execute('CREATE TABLE IF NOT EXISTS channel_cache(account TEXT,kind TEXT,body TEXT,PRIMARY KEY(account,kind))');path.chmod(0o600);return db
 def cached(self,kind):
  key=self.key()
  with closing(self.db()) as db:
   row=db.execute('SELECT body FROM channel_cache WHERE account=? AND kind=?',(key,kind)).fetchone();return json.loads(row[0]) if row else {}
 def save(self,kind,result):
  key=self.key()
  with closing(self.db()) as db:
   with db:db.execute('INSERT OR REPLACE INTO channel_cache VALUES(?,?,?)',(key,kind,json.dumps(result)))
 async def read(self,kind):
  if kind not in ('stream','followers'):raise ActionError('Unbekannte Kanalabfrage')
  if self.io.dry_run:return {**self.cached(kind),'preview':True}
  cfg=self.io.config;account=self.key()
  if not cfg.get('twitch_token'):raise ActionError('Broadcaster-Konto zuerst anmelden')
  if kind=='followers':
   if 'moderator:read:followers' not in scopes(cfg):raise ActionError('Follower-Leserecht fehlt; gemeinsame Broadcaster-Freigabe verwenden')
   reply=await self.io.twitch('GET','channels/followers',params={'broadcaster_id':cfg['broadcaster_id'],'first':1})
   if not isinstance(reply.get('data'),list) or reply.get('total') is None:raise ActionError('Twitch hat keinen gültigen Followerstand geliefert')
   total=integer(reply['total'],0);latest=reply['data'][0] if reply['data'] else None
   if total and latest is None:raise ActionError('Followerdetails nicht verfügbar; Antwort wird nicht als leerer Kanal ausgegeben')
   result={'followerCount':total,'latestFollower':latest,'checkedAt':time.time()}
  else:
   reply=await self.io.twitch('GET','streams',params={'user_id':cfg['broadcaster_id'],'first':1})
   if not isinstance(reply.get('data'),list):raise ActionError('Twitch hat keinen gültigen Streamstatus geliefert')
   stream=reply['data'][0] if reply['data'] else None
   if stream and stream.get('user_id')!=cfg['broadcaster_id']:raise ActionError('Streamantwort gehört zu einem anderen Kanal')
   result={'online':stream is not None,'viewerCount':integer(stream.get('viewer_count'),0) if stream else 0,'stream':stream,'checkedAt':time.time()}
  if self.key()!=account:raise ActionError('Konto während der Kanalabfrage gewechselt; Antwort verworfen')
  self.save(kind,result);return result
async def operation(io,node,args):
 kind=node['type'];result=await Channel(io).read('stream' if kind==91200 else 'followers')
 field='viewerCount' if kind==91200 else 'followerCount'
 if field not in result:raise ActionError('Kein gespeicherter Kanalstand; im Live-Modus aktualisieren')
 if kind==91202:
  row=result['latestFollower']
  if row is None:raise ActionError('Der Kanal hat keinen abrufbaren letzten Follower')
  args.update({'latestFollower.user':row.get('user_name',''),'latestFollower.userName':row.get('user_login',''),'latestFollower.userId':row.get('user_id','')})
 else:args[field]=result[field]
 if result.get('preview'):args['isPreview']=True
async def stream_event(io,kind,event,identity,occurred_at=''):
 if event.get('broadcaster_user_id')!=io.config.get('broadcaster_id'):return None
 args={'platform':'twitch','userType':'twitch','broadcasterUserId':event['broadcaster_user_id'],'broadcasterUserName':event.get('broadcaster_user_login',''),'broadcasterUser':event.get('broadcaster_user_name',''),'messageId':identity,'eventReceivedAt':occurred_at}
 if kind=='stream.offline':return 91251,{**args,'endedAt':'','endedAtSource':'unknown'}
 args.update(startedAt=event.get('started_at',''),streamId=event.get('id',''),streamType=event.get('type',''),channelInfoAvailable=False)
 try:
  result=await io.twitch('GET','channels',params={'broadcaster_id':event['broadcaster_user_id']});row=next(iter(result.get('data',[])),None)
  if row and row.get('broadcaster_id')==event['broadcaster_user_id']:
   tags=row.get('tags',[]);args.update(channelInfoAvailable=True,game=row.get('game_name',''),gameId=row.get('game_id',''),tags=tags,tagCount=len(tags),tagsDelimited=', '.join(tags));args.update({'tag'+str(i):tag for i,tag in enumerate(tags)})
 except (ActionError,aiohttp.ClientError,TimeoutError,OSError,ValueError,KeyError,TypeError):pass
 return 91250,args

def matches(kind,node,args):
 if kind!=91252:return True
 try:
  count=integer(args.get('viewerCount'),0)
  for field,minimum in (('rangeMin',True),('rangeMax',False)):
   bound=node.get(field,-1)
   if bound==-1:continue
   bound=integer(bound,0)
   if (count<bound if minimum else count>bound):return False
 except ActionError:return False
 return True
