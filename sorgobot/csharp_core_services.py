"""Registered code triggers and persistent native credits shared with the UI."""
import copy,json
from .core import ActionError

CODE_TRIGGER=90255

def registrations(engine):
 if not hasattr(engine,'csharp_code_triggers'):engine.csharp_code_triggers={}
 return engine.csharp_code_triggers

def snapshot(engine):return copy.deepcopy(list(registrations(engine).values()))

def unregister(engine,owner):
 values=registrations(engine)
 for name in list(values):
  if values[name]['owner']==owner:values.pop(name,None)

def trigger(engine,event,payload):
 if not isinstance(event,str) or not event.strip() or not isinstance(payload,dict):raise ActionError('Code Event benötigt einen Namen und ein Argumentobjekt')
 if event not in registrations(engine):return None
 try:json.dumps(payload,allow_nan=False)
 except (ValueError,TypeError,RecursionError):raise ActionError('Code-Event-Argumente benötigen endliche, gültige JSON-Werte') from None
 events=getattr(engine,'core_events',None)
 if events is None:raise ActionError('Code-Event-Laufzeit fehlt')
 arguments=copy.deepcopy(payload);arguments.pop('__source',None);arguments['eventName']=event
 events.emit(CODE_TRIGGER,arguments,eventName=event)
 return None

def catalog(base,records):
 result=dict(base)
 for record in records:
  selector='code:'+record['eventName'];path=' · '.join(['Custom',*record['categories'],record['name']])
  result[selector]=(path,{'eventName':record['eventName'],'codeTriggerName':record['name'],'categories':record['categories']})
 return result

def legacy_credits(engine):
 value=engine.state.get('cph:credits')
 return value if isinstance(value,dict) and isinstance(value.get('Custom'),dict) and isinstance(value.get('Events'),dict) else None

def credits(engine):
 manager=getattr(getattr(engine,'studio',None),'services',None)
 if manager:
  import time
  hours=manager.settings['credits']['autoResetHours'];now=time.time();last=engine.state.get('credits:lastReset',now)
  if engine.state.get('credits:lastReset') is None:engine.state.set('credits:lastReset',now)
  if hours and now-last>=hours*3600:
   save_credits(engine,{'Custom':{},'Events':{}});engine.state.set('credits:lastReset',now)
 db=engine.state.db
 if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='cph_credits'").fetchone():
  row=db.execute('SELECT body FROM cph_credits WHERE id=1').fetchone()
  if row:return json.loads(row[0])
 return copy.deepcopy(legacy_credits(engine) or {'Custom':{},'Events':{}})

def save_credits(engine,value):
 if engine.state.db.in_transaction:raise ActionError('Credits benötigen eine eigene Transaktion')
 encoded=json.dumps(value,allow_nan=False);legacy=legacy_credits(engine);db=engine.state.db
 with db:
  db.execute('CREATE TABLE IF NOT EXISTS cph_credits(id INTEGER PRIMARY KEY CHECK(id=1),body TEXT NOT NULL)')
  db.execute('INSERT INTO cph_credits VALUES(1,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body',(encoded,))
  if legacy is not None:
   db.execute('DELETE FROM kv WHERE key=?',('cph:credits',));db.execute('DELETE FROM variable_writes WHERE key=?',('cph:credits',))

def credits_snapshot(engine):
 value=credits(engine)
 native_tracking(value)
 value['Events']={key:value.get('Events',{}).get(key,[]) for key in ('Follows','Cheers','Subs','ReSubs','GiftSubs','GiftBombs','Raided','RewardRedemptions','GoalContributions','GameUpdates','Pyramids')}
 # Observed data only; no invented contributors or rankings from absent history.
 value.update(HypeTrainConductor=value.get('HypeTrainConductor',[]),HypeTrainContributors=value.get('HypeTrainContributors',[]),User=value.get('User',{}),TopBits=value.get('TopBits',{'All':[],'Month':[],'Week':[]}),TopChannelRewards=value.get('TopChannelRewards',[]))
 return value

def native_tracking(value):
 import time
 rows=value.get('NativeCheers',[]);now=time.time()
 result={}
 for window,seconds in [('All',None),('Month',30*86400),('Week',7*86400)]:
  counts={}
  for row in rows:
   if seconds and now-row['time']>seconds:continue
   key=row['key'];entry=counts.setdefault(key,{'user':row['user'],'userName':row['userName'],'bits':0});entry['bits']+=row['bits']
  result[window]=sorted(counts.values(),key=lambda r:(-r['bits'],r['userName'].casefold()))
 if rows:value['TopBits']=result
 if value.get('NativeRewards'):
  value['TopChannelRewards']=sorted(value['NativeRewards'].values(),key=lambda r:(-r.get('points',0),r['userName'].casefold()))

def capture(engine,kind,args):
 if getattr(engine,'state',None) is None:return
 from .event_metadata import NATIVE_TYPES
 original=NATIVE_TYPES.get(kind,kind)
 section={101:'Follows',102:'Cheers',103:'Subs',104:'ReSubs',105:'GiftSubs',106:'GiftBombs',107:'Raided',112:'RewardRedemptions',116:'GoalContributions',118:'GameUpdates',162:'Pyramids'}.get(original)
 manager=getattr(getattr(engine,'studio',None),'services',None)
 if section is None and (original!=133 or manager is None):return
 options=manager.settings['credits'] if manager else None
 value=credits(engine);changed=False
 identity=args.get('eventSubMessageId',args.get('messageId',args.get('redemptionId')))
 if section and (options is None or section in options['events']):
  items=value.setdefault('Events',{}).setdefault(section,[])
  if not identity or not any(isinstance(item,dict) and item.get('creditEventId')==identity for item in items):
   row=copy.deepcopy(args)
   if identity:row['creditEventId']=identity
   items.append(row);changed=True
 if options:
  import time
  login=str(args.get('userName',args.get('userLogin','')));name=str(args.get('user',login));key=str(args.get('userId') or login.casefold())
  if original==133 and key:
   sections=[r for r in options['presentRoles'] if r in args.get('roles',[])]
   groups=getattr(getattr(engine,'services',None),'config',{}).get('userGroups',[])
   for group in groups:
    if group['id'] in options['presentGroups'] and any(str(u).casefold() in (login.casefold(),'twitch:'+login.casefold()) for u in group.get('users',[])):sections.append('Group: '+group['name'])
   if login.casefold() in [u.casefold() for u in options['presentUsers']]:sections.append('Users')
   for selected in sections:
    rows=value.setdefault('User',{}).setdefault(selected,[])
    if not any((str(r.get('userId') or r.get('userName','').casefold()) if isinstance(r,dict) else str(r).casefold())==key for r in rows):rows.append({'user':name,'userName':login,'userId':str(args.get('userId',''))});changed=True
  event_key=str(identity) if identity else None
  if original in (102,112) and key and options['trackBits' if original==102 else 'trackRewards']:
   seen=value.setdefault('NativeTrackingIds',[])
   if event_key is None or event_key not in seen:
    if event_key:seen.append(event_key)
    if original==102:
     try:bits=int(args.get('bits',0))
     except (ValueError,TypeError,OverflowError):bits=0
     if bits>0:value.setdefault('NativeCheers',[]).append({'key':key,'user':name,'userName':login,'bits':bits,'time':time.time()});changed=True
    else:
     row=value.setdefault('NativeRewards',{}).setdefault(key,{'user':name,'userName':login,'count':0,'points':0});row['count']+=1
     try:cost=max(0,int(args.get('rewardCost',0)))
     except (ValueError,TypeError,OverflowError):cost=0
     row['points']=row.get('points',0)+cost;changed=True
 if changed:save_credits(engine,value)

async def rpc(engine,method,values):
 if method=='code_register':
  owner,name,event,categories=values
  if not all(isinstance(v,str) and v.strip() for v in (owner,name,event)) or not isinstance(categories,list) or any(not isinstance(v,str) or not v.strip() or ' · ' in v for v in categories):return False
  if ' · ' in name:return False
  records=registrations(engine)
  if event in records or any(r['name']==name and r['categories']==categories for r in records.values()):return False
  records[event]={'owner':owner,'name':name,'eventName':event,'categories':list(categories)};return True
 if method=='code_event':return trigger(engine,*values)
 if method=='credits':
  operation,*fields=values
  if operation=='reset':
   import time
   save_credits(engine,{'Custom':{},'Events':{}});engine.state.set('credits:lastReset',time.time());return None
  if operation!='add' or len(fields)!=2:raise ActionError('Unbekannter Credits-Aufruf')
  section,value=fields
  if not isinstance(section,str) or not section.strip():raise ActionError('Credits-Abschnitt fehlt')
  json.dumps(value,allow_nan=False)
  current=credits(engine);current.setdefault('Custom',{}).setdefault(section,[]).append(copy.deepcopy(value));save_credits(engine,current);return None
 raise ActionError('Unbekannter C#-Core-Dienst')
