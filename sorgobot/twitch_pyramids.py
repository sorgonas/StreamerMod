"""Local emote-pyramid progression and durable per-channel chat-game statistics."""
import collections,copy,json,sqlite3,time
from contextlib import closing,contextmanager
from .core import ActionError
class PyramidStats:
 def __init__(self,io):self.io=io
 def key(self):return self.io.config.get('broadcaster_id','')+'|'+self.io.config.get('twitch_client_id','')
 @contextmanager
 def db(self):
  path=self.io.root/'state/twitch-pyramids.sqlite3';path.parent.mkdir(parents=True,exist_ok=True)
  with closing(sqlite3.connect(path,timeout=10)) as db:
   db.row_factory=sqlite3.Row
   db.executescript('CREATE TABLE IF NOT EXISTS pyramid_users(account TEXT,user_id TEXT,login TEXT,display TEXT,success INTEGER DEFAULT 0,broken INTEGER DEFAULT 0,PRIMARY KEY(account,user_id));CREATE TABLE IF NOT EXISTS pyramid_results(account TEXT,message TEXT,body TEXT,stamp REAL,PRIMARY KEY(account,message));')
   path.chmod(0o600)
   with db:yield db
 def record(self,kind,args,state):
  uid=args.get('userId');identity=args.get('messageId')
  if not uid or not identity:raise ActionError('Pyramiden-Ergebnis ohne Twitch-Nutzer-/Nachrichten-ID')
  key=self.key();field='success' if kind==90033 else 'broken'
  with self.db() as db:
   db.execute('BEGIN IMMEDIATE')
   if db.execute('SELECT 1 FROM pyramid_results WHERE account=? AND message=?',(key,identity)).fetchone():return None
   db.execute('INSERT INTO pyramid_users(account,user_id,login,display) VALUES(?,?,?,?) ON CONFLICT(account,user_id) DO UPDATE SET login=excluded.login,display=excluded.display',(key,uid,args.get('userName',args.get('userLogin','')),args.get('user','')))
   db.execute('UPDATE pyramid_users SET '+field+'='+field+'+1 WHERE account=? AND user_id=?',(key,uid))
   total=db.execute('SELECT '+field+' FROM pyramid_users WHERE account=? AND user_id=?',(key,uid)).fetchone()[0]
   values=event_arguments(kind,args,state,total);body={'kind':kind,'time':time.time(),'userId':uid,'user':args.get('user',''),'userName':args.get('userName',''),'width':state['height'],'emote':state['emote'],'owner':state['owner'],'total':total}
   db.execute('INSERT INTO pyramid_results VALUES(?,?,?,?)',(key,identity,json.dumps(body),body['time']))
   db.execute('DELETE FROM pyramid_results WHERE account=? AND message NOT IN (SELECT message FROM pyramid_results WHERE account=? ORDER BY stamp DESC LIMIT 5000)',(key,key))
   return values
 def summary(self):
  key=self.key()
  with self.db() as db:
   users=[dict(row) for row in db.execute('SELECT user_id,login,display,success,broken FROM pyramid_users WHERE account=? ORDER BY success DESC,broken DESC,user_id LIMIT 1000',(key,))]
   totals=dict(db.execute('SELECT COALESCE(SUM(success),0) AS success,COALESCE(SUM(broken),0) AS broken,COUNT(*) AS users FROM pyramid_users WHERE account=?',(key,)).fetchone())
   recent=[json.loads(row['body']) for row in db.execute('SELECT body FROM pyramid_results WHERE account=? ORDER BY stamp DESC LIMIT 100',(key,))]
  return {'users':users,'totals':totals,'recent':recent}
def event_arguments(kind,args,state,total):
 values=copy.deepcopy(args);owner=state['owner'];values.update(platform='twitch',userType='twitch',pyramidEmote=state['emote'],pyramidWidth=state['height'],pyramidHeight=state['height'],pyramidUsers=sorted(state['users']),pyramidOwnerId=owner['userId'],pyramidOwnerUsername=owner.get('userName',owner.get('userLogin','')),pyramidOwnerDisplayName=owner.get('user',''))
 values['totalPyramids' if kind==90033 else 'totalPyramidsBroken']=total
 return values
class Pyramids:
 def __init__(self,io):self.io=io;self.state=None;self.mode=None;self.seen=collections.OrderedDict()
 def reset(self):self.state=None
 def ingest(self,event,args,valid,emote,count):
  cfg=self.io.config;minimum=max(2,min(100,int(cfg.get('twitch_pyramids_minimum',2))));mode=(cfg.get('broadcaster_id',''),cfg.get('twitch_client_id',''),bool(cfg.get('twitch_pyramids',False)),bool(cfg.get('twitch_pyramids_shared',False)),minimum)
  if mode!=self.mode:self.reset();self.seen.clear();self.mode=mode
  if not mode[2]:return []
  if not mode[3] and event.get('source_broadcaster_user_id') not in (None,'',cfg.get('broadcaster_id')):return []
  identity=args.get('messageId')
  if identity:
   if identity in self.seen:return []
   self.seen[identity]=True
   if len(self.seen)>5000:self.seen.popitem(last=False)
  state=self.state;output=[]
  if state:
   same=valid and emote==state['emote'];expected=state['count']+(-1 if state['down'] else 1)
   if same and not state['down'] and state['count']>=minimum and count==state['count']-1:state['down']=True;expected=count
   if same and count==expected:
    state['count']=count;state['height']=max(state['height'],count)
    if args.get('userId'):state['users'].add(args['userId'])
    if state['down'] and count==1:
     self.state=None;values=PyramidStats(self.io).record(90033,args,state)
     if values:output.append((90033,values))
    return output
   self.state=None
   if state['height']>=minimum:
    values=PyramidStats(self.io).record(90034,args,state)
    if values:output.append((90034,values))
  if valid and count==1:self.state={'emote':emote,'count':1,'height':1,'down':False,'users':{args['userId']} if args.get('userId') else set(),'owner':{key:args.get(key,'') for key in ('userId','userName','userLogin','user')}}
  return output
 def snapshot(self):
  state=self.state
  return {'active':bool(state),'emote':state['emote'],'width':state['height'],'row':state['count'],'descending':state['down'],'owner':copy.deepcopy(state['owner'])} if state else {'active':False}
