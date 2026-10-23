"""Durable local subscription counter; canonical new-subscription events only."""
import json,sqlite3,time
from contextlib import closing,contextmanager
from .core import ActionError,expand
from .twitch_rewards import integer
GET=91100;SET=91101;LATEST=91102;ROLLOVER=91150
DEFAULT={'enabled':False,'count':0,'rollover':0,'rolloverCount':0}
class SubCounter:
 def __init__(self,io):self.io=io
 def key(self):
  cfg=self.io.config
  if not cfg.get('broadcaster_id') or not cfg.get('twitch_client_id'):raise ActionError('Broadcaster-Konto zuerst einrichten')
  return cfg['broadcaster_id']+'|'+cfg['twitch_client_id']
 @contextmanager
 def db(self):
  path=self.io.root/'state/twitch-sub-counter.sqlite3';path.parent.mkdir(parents=True,exist_ok=True)
  with closing(sqlite3.connect(path,timeout=10)) as db:
   db.executescript('CREATE TABLE IF NOT EXISTS sub_counter(account TEXT PRIMARY KEY,body TEXT);CREATE TABLE IF NOT EXISTS sub_counter_seen(account TEXT,message TEXT,stamp REAL,PRIMARY KEY(account,message));CREATE TABLE IF NOT EXISTS sub_latest(account TEXT PRIMARY KEY,body TEXT,stamp REAL);');path.chmod(0o600)
   with db:yield db
 def row(self,db,key):
  row=db.execute('SELECT body FROM sub_counter WHERE account=?',(key,)).fetchone();return json.loads(row[0]) if row else dict(DEFAULT)
 def get(self):
  key=self.key()
  with self.db() as db:return self.row(db,key)
 def save(self,count=None,rollover=None,enabled=None):
  key=self.key()
  if count is not None:
   count=integer(count,0)
   if count>2**31-1:raise ActionError('Sub Counter Count maximal 2147483647')
  if rollover is not None:
   rollover=integer(rollover,0)
   if rollover>32767:raise ActionError('Rollover muss zwischen 0 und 32767 liegen')
  if enabled is not None and type(enabled) is not bool:raise ActionError('Ungültiger Sub-Counter-Zustand')
  with self.db() as db:
   db.execute('BEGIN IMMEDIATE');row=self.row(db,key)
   if count is not None:row['count']=count
   if rollover is not None:row['rollover']=rollover
   if enabled is not None:row['enabled']=enabled
   # Manual edits never fire actions or increase the automatic rollover total.
   if row['rollover']:row['count']%=row['rollover']
   db.execute('INSERT OR REPLACE INTO sub_counter VALUES(?,?)',(key,json.dumps(row)))
   return row
 def latest(self):
  key=self.key()
  with self.db() as db:
   row=db.execute('SELECT body FROM sub_latest WHERE account=?',(key,)).fetchone()
   if not row:raise ActionError('Noch kein neues Abo beobachtet; eine Abonnentenliste liefert keine verlässliche zeitliche Reihenfolge.')
   return json.loads(row[0])
 def ingest(self,event,identity,occurred_at=''):
  cfg=self.io.config
  if event.get('broadcaster_user_id')!=cfg.get('broadcaster_id'):return None
  if not identity or not event.get('user_id'):raise ActionError('Subscription ohne Nachrichten-/Nutzer-ID')
  key=self.key()
  with self.db() as db:
   db.execute('BEGIN IMMEDIATE')
   if db.execute('SELECT 1 FROM sub_counter_seen WHERE account=? AND message=?',(key,identity)).fetchone():return None
   row=self.row(db,key);db.execute('INSERT INTO sub_counter_seen VALUES(?,?,?)',(key,identity,time.time()))
   db.execute('DELETE FROM sub_counter_seen WHERE account=? AND message NOT IN (SELECT message FROM sub_counter_seen WHERE account=? ORDER BY stamp DESC LIMIT 10000)',(key,key))
   from .twitch_hype_train import date
   timestamp=date(occurred_at);stamp=timestamp.timestamp() if timestamp else time.time()
   previous=db.execute('SELECT stamp FROM sub_latest WHERE account=?',(key,)).fetchone()
   if previous is None or stamp>previous[0]:
    latest={'userName':event.get('user_name',''),'userId':event['user_id'],'userLogin':event.get('user_login',''),'tier':{'1000':'Tier1','2000':'Tier2','3000':'Tier3'}.get(event.get('tier'),''),'planName':'','planNameAvailable':False,'isGift':bool(event.get('is_gift',False)),'isObserved':True,'observedAt':occurred_at if timestamp else '', 'timeSource':'event_metadata' if timestamp else 'received','source':'channel.subscribe'}
    db.execute('INSERT OR REPLACE INTO sub_latest VALUES(?,?,?)',(key,json.dumps(latest),stamp))
   if not row['enabled']:return None
   value=row['count']+1
   if value>2**31-1:raise ActionError('Sub Counter Count überläuft; Zähler manuell zurücksetzen')
   crossed=bool(row['rollover'] and value>=row['rollover'])
   row['count']=value%row['rollover'] if crossed else value
   if crossed:row['rolloverCount']+=1
   db.execute('INSERT OR REPLACE INTO sub_counter VALUES(?,?)',(key,json.dumps(row)))
   if not crossed:return None
   return {'subCounter':row['count'],'rollover':row['rollover'],'rolloverCount':row['rolloverCount'],'messageId':identity,'platform':'twitch','userType':'twitch','broadcasterUserId':cfg['broadcaster_id'],'broadcasterUserName':event.get('broadcaster_user_login',''),'broadcasterUser':event.get('broadcaster_user_name','')}
async def operation(io,node,args):
 service=SubCounter(io)
 if node['type']==LATEST:
  args.update({'latestSubscriber.'+key:value for key,value in service.latest().items()})
  if io.dry_run:args['isPreview']=True
  return
 if node['type']==SET:
  args['setResult']=False;count=expand(node.get('count',''),args)
  # Validation also happens in preview, without changing the stored count.
  value=integer(count,0)
  if value>2**31-1:raise ActionError('Sub Counter Count maximal 2147483647')
  if io.dry_run:args['isPreview']=True;return
  service.save(count=value);args['setResult']=True;return
 row=service.get();args.update({'subCounter.count':row['count'],'subCounter.rollover':row['rollover'],'subCounter.rolloverCount':row['rolloverCount']})
 if io.dry_run:args['isPreview']=True
