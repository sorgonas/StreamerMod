"""Twitch user selection from validated chatters or observed local identities."""
import random,re,sqlite3
from contextlib import closing
from .core import ActionError,expand
from .twitch_rewards import scopes,integer
from .twitch_user_info import UserInfo,login
from .users import store as user_store

ENTRIES={91700:('Add Present User',{'index':'0'}),91701:('Add Random Users',{'count':'1','presentOnly':False,'groups':[],'includeFrom':False})}
PREFIXES=('randomUser','randomUserName','randomUserId','randomUserType')

def normalized(rows):
 if not isinstance(rows,list):raise ActionError('Twitch hat keine gültige Chatnutzerliste geliefert')
 result={};logins={}
 for row in rows:
  if not isinstance(row,dict) or not isinstance(row.get('user_id'),str) or not row['user_id'] or not isinstance(row.get('user_name'),str) or not row['user_name']:raise ActionError('Unvollständiger Twitch-Chatnutzer')
  name=login(row.get('user_login'));uid=row['user_id'];user={'userName':name,'userId':uid,'displayName':row['user_name']}
  if uid in result and result[uid]!=user or name in logins and logins[name]!=uid:raise ActionError('Widersprüchliche Twitch-Nutzeridentitäten; Abfrage wiederholen')
  result[uid]=user;logins[name]=uid
 return sorted(result.values(),key=lambda row:(row['userName'],row['userId']))

class Selection:
 def __init__(self,engine):self.engine=engine;self.io=engine.io;self.cache=UserInfo(self.io)
 async def present(self):
  before=self.cache.session()
  if self.io.dry_run:
   body,checked=self.cache.cached('present-users','channel')
   if not isinstance(body,dict):raise ActionError('Ungültiger gespeicherter Chatnutzerstand')
   return normalized(body.get('users')),checked
  if not before[-1]:raise ActionError('Broadcaster-Konto zuerst unter Twitch → Accounts anmelden')
  if 'moderator:read:chatters' not in scopes(self.io.config):raise ActionError('Chatnutzer-Leserecht fehlt; gemeinsame Broadcaster-Freigabe unter Twitch → Accounts verwenden')
  rows=[];cursor='';seen=set()
  for page in range(1000):
   params={'broadcaster_id':before[0],'moderator_id':before[0],'first':1000}
   if cursor:params['after']=cursor
   reply=await self.io.twitch('GET','chat/chatters',params=params);self.cache.check_session(before)
   if not isinstance(reply,dict) or not isinstance(reply.get('data'),list) or not isinstance(reply.get('pagination'),dict):raise ActionError('Twitch hat keinen vollständigen Chatnutzerstand geliefert')
   integer(reply.get('total'),0);normalized(reply['data']);rows.extend(reply['data'])
   cursor=reply['pagination'].get('cursor','')
   if not isinstance(cursor,str):raise ActionError('Ungültiger Twitch-Seitencursor')
   if not cursor:break
   if cursor in seen:raise ActionError('Wiederholter Twitch-Seitencursor; kein vollständiger Nutzerstand')
   seen.add(cursor)
  else:raise ActionError('Chatnutzer-Abfrage überschreitet 1000 Seiten; kein vollständiger Nutzerstand')
  users=normalized(rows);checked=self.cache.save('present-users','channel',{'users':rows})
  registry=user_store(self.engine)
  for user in users:registry.remember('twitch',user['userName'],user['userId'],user['displayName'])
  return users,checked
 def known(self):
  def read(db):
   if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='known_users'").fetchone():return []
   result=[];seen=set();ids=set()
   for name,uid,display in db.execute("SELECT user,user_id,display_name FROM known_users WHERE platform='twitch' ORDER BY last_seen DESC,user"):
    try:name=login(name)
    except ActionError:continue
    if name in seen or uid and uid in ids:continue
    result.append({'userName':name,'userId':uid,'displayName':display or name});seen.add(name)
    if uid:ids.add(uid)
   return sorted(result,key=lambda row:(row['userName'],row['userId']))
  # Preview uses the real observed registry when available, through a read-only
  # connection. It neither creates users nor queries Twitch.
  path=(self.io.root/'state/live.db').resolve()
  if self.io.dry_run and path.exists():
   with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as db:return read(db)
  return read(self.engine.state.db)

async def operation(engine,node,args):
 kind=node['type'];io=engine.io
 for key in ('twitchUsersFromCache','twitchUsersCheckedAt','twitchUsersSource'):args.pop(key,None)
 if kind==91700:
  for key in ('presentUsersCount','presentUser','presentUserName','presentUserId','presentUserType'):args.pop(key,None)
  index=integer(expand(node.get('index','0'),args),0)
  users,checked=await Selection(engine).present();args.update(presentUsersCount=len(users),presentUser=False,presentUserName='',presentUserId='',presentUserType='')
  if index<len(users):
   user=users[index];args.update(presentUser=user['displayName'],presentUserName=user['userName'],presentUserId=user['userId'],presentUserType='twitch')
  args.update(twitchUsersFromCache=io.dry_run,twitchUsersCheckedAt=checked,twitchUsersSource='cached-chatters' if io.dry_run else 'chatters')
 elif kind==91701:
  for key in list(args):
   if key=='randomUsersCount' or any(re.fullmatch(re.escape(prefix)+r'\d+',key) for prefix in PREFIXES):args.pop(key,None)
  from .twitch_random_groups import validate,resolve,configured,filter_users
  names=validate(node)
  if names:resolve(names,configured(engine))
  count=integer(expand(node.get('count','1'),args),0);present=expand(node.get('presentOnly',False),args)
  if not isinstance(present,bool):raise ActionError('Present Only muss true/false sein')
  if count==0:users=[]
  elif present:
   users,checked=await Selection(engine).present();args['twitchUsersCheckedAt']=checked
  else:users=Selection(engine).known()
  if count and names:users=await filter_users(engine,node,users)
  selected=random.SystemRandom().sample(users,min(count,len(users)));args['randomUsersCount']=len(selected)
  for index,user in enumerate(selected):args.update({'randomUser'+str(index):user['displayName'],'randomUserName'+str(index):user['userName'],'randomUserId'+str(index):user['userId'],'randomUserType'+str(index):'twitch'})
  args.update(twitchUsersFromCache=bool(count and io.dry_run and present),twitchUsersSource='none' if count==0 else ('cached-chatters' if io.dry_run else 'chatters') if present else 'known')
 else:raise ActionError('Unbekannte Twitch-Nutzerauswahl')
 if io.dry_run:args['isPreview']=True
