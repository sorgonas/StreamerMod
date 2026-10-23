"""Read-only Hype Train status and durable event progression."""
import copy,json,sqlite3,time
from contextlib import closing,contextmanager
from datetime import datetime
from .core import ActionError
from .twitch_rewards import scopes,integer
SCOPE='channel:read:hype_train'
TRIGGERS={91050:'Hype Train Starts',91051:'Hype Train Update',91052:'Hype Train Level Up',91053:'Hype Train End'}
def date(value):
 try:
  result=datetime.fromisoformat(value.replace('Z','+00:00'));return result if result.tzinfo else None
 except (ValueError,TypeError,AttributeError):return None

def variables(row):
 kind=row.get('type','regular');level=integer(row.get('level',0),0);goal=row.get('goal');progress=row.get('progress');ratio=None
 if goal is not None and progress is not None:
  goal=integer(goal,0);progress=integer(progress,0)
  if goal:ratio=progress/goal
 args={'id':row.get('id',''),'hypeTrainId':row.get('id',''),'level':level,'total':integer(row.get('total',0),0),'startedAt':row.get('started_at',''),'expiresAt':row.get('expires_at',''),'endedAt':row.get('ended_at',''),'cooldownEndsAt':row.get('cooldown_ends_at',''),'percentSource':row.get('_percent_source','payload' if ratio is not None else 'unknown'),'percentDecimal':ratio,'percent':ratio*100 if ratio is not None else None,'trainType':kind,'isGoldenKappaTrain':kind=='golden_kappa','isTreasureTrain':kind=='treasure','isSharedTrain':bool(row.get('is_shared_train',False)),'sharedTrainParticipants':copy.deepcopy(row.get('shared_train_participants') or []),'userType':'twitch','platform':'twitch','broadcasterUserId':row.get('broadcaster_user_id',''),'broadcasterUserName':row.get('broadcaster_user_login',''),'broadcasterUser':row.get('broadcaster_user_name','')}
 start=date(row.get('started_at'));end=date(row.get('ended_at') or row.get('expires_at'))
 if start and end:args['duration']=max(0,int((end-start).total_seconds()))
 for key,target in [('all_time_high_level','allTimeHighLevel'),('all_time_high_total','allTimeHighTotal')]:
  if key in row:args[target]=row[key]
 for category in ('bits','subscription','other'):
  items=[c for c in row.get('top_contributions',[]) if c.get('type')==category]
  if not items:continue
  top=max(items,key=lambda c:integer(c.get('total',0),0))
  for field,value in {'user':top.get('user_name',''),'userName':top.get('user_login',''),'userId':top.get('user_id',''),'total':integer(top.get('total',0),0)}.items():args['top.'+category+'.'+field]=value
 return args
class HypeTrain:
 def __init__(self,io):self.io=io
 def key(self):return self.io.config.get('broadcaster_id','')+'|'+self.io.config.get('twitch_client_id','')
 @contextmanager
 def db(self):
  path=self.io.root/'state/twitch-hype-train.sqlite3';path.parent.mkdir(parents=True,exist_ok=True)
  with closing(sqlite3.connect(path,timeout=10)) as db:
   db.executescript('CREATE TABLE IF NOT EXISTS hype_status(account TEXT PRIMARY KEY,body TEXT);CREATE TABLE IF NOT EXISTS hype_events(account TEXT,train TEXT,body TEXT,seen TEXT,updated REAL,PRIMARY KEY(account,train));')
   path.chmod(0o600)
   with db:yield db
 def cached(self):
  with self.db() as db:
   row=db.execute('SELECT body FROM hype_status WHERE account=?',(self.key(),)).fetchone()
   return json.loads(row[0]) if row else {}
 async def status(self):
  if self.io.dry_run:return {**self.cached(),'preview':True}
  cfg=self.io.config
  if not all(cfg.get(k) for k in ('twitch_token','twitch_client_id','broadcaster_id')):raise ActionError('Broadcaster-Konto zuerst anmelden')
  if SCOPE not in scopes(cfg):raise ActionError('Hype-Train-Leserecht fehlt. Die gemeinsame Broadcaster-Freigabe unter Accounts ergänzt alle eingebauten Funktionen.')
  result=await self.io.twitch('GET','hypetrain/status',params={'broadcaster_id':cfg['broadcaster_id']})
  if not result.get('data'):raise ActionError('Twitch hat keinen Hype-Train-Status geliefert')
  current=result['data'][0].get('current')
  if current:variables(current)
  with self.db() as db:db.execute('INSERT OR REPLACE INTO hype_status VALUES(?,?)',(self.key(),json.dumps(result)))
  return result
 def ingest(self,kind,event,identity):
  part=kind.rsplit('.',1)[-1]
  if part not in ('begin','progress','end') or not event.get('id'):raise ActionError('Ungültiges Hype-Train-Ereignis')
  event=copy.deepcopy(event);event['level']=integer(event.get('level',0),0);event['total']=integer(event.get('total',0),0)
  variables(event);account=self.key();train=event['id']
  if event.get('broadcaster_user_id')!=self.io.config.get('broadcaster_id'):return [],None
  with self.db() as db:
   db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT body,seen FROM hype_events WHERE account=? AND train=?',(account,train)).fetchone();old=json.loads(row[0]) if row else {};seen=json.loads(row[1]) if row else []
   if identity in seen or old.get('_ended'):return [],None
   previous=old.get('level');regression=bool(old and (int(event.get('level',0))<int(old.get('level',0)) or int(event.get('total',0))<int(old.get('total',0))))
   if part=='progress' and regression:return [],None
   merged=copy.deepcopy(old)
   if part=='begin' and regression:
    # A late begin must not reset a newer progress snapshot.
    for key,value in event.items():merged.setdefault(key,value)
   else:
    merged.update(event)
    if part=='end' and previous!=event.get('level'):
     merged.pop('progress',None);merged.pop('goal',None)
   if part=='end':merged['_percent_source']='last_observed' if merged.get('goal') is not None and merged.get('progress') is not None else 'unknown'
   else:merged['_percent_source']='payload'
   merged['_ended']=part=='end';seen.append(identity);seen=seen[-512:]
   begin_already=bool(old.get('_began'));merged['_began']=begin_already or part=='begin'
   values=variables(merged);values['messageId']=identity;values['hypeTrainActive']=not merged['_ended']
   output=[]
   if part=='begin' and not begin_already:output.append((91050,variables(event)|{'messageId':identity,'hypeTrainActive':True}))
   if part=='progress':
    output.append((91051,dict(values)))
    if previous is not None and event['level']>previous:output.append((91052,{**values,'prevLevel':previous}))
   if part=='end':output.append((91053,dict(values)))
   db.execute('INSERT OR REPLACE INTO hype_events VALUES(?,?,?,?,?)',(account,train,json.dumps(merged),json.dumps(seen),time.time()))
   db.execute('DELETE FROM hype_events WHERE account=? AND train NOT IN (SELECT train FROM hype_events WHERE account=? ORDER BY updated DESC LIMIT 100)',(account,account))
  return output,values
async def operation(io,node,args):
 result=await HypeTrain(io).status()
 if not result.get('data'):raise ActionError('Kein gespeicherter Hype-Train-Status. Im Live-Modus aktualisieren.')
 current=result['data'][0].get('current');args['hypeTrainActive']=current is not None
 if current:args.update(variables(current))
 if result.get('preview'):args['isPreview']=True

def matches(kind,node,args):
 if kind!=91052:return True
 for field,minimum in [('rangeMin',True),('rangeMax',False)]:
  bound=node.get(field,-1)
  if bound==-1:continue
  try:bound=integer(bound,0);level=integer(args.get('level'),0)
  except ActionError:return False
  if (level<bound if minimum else level>bound):return False
 return True
