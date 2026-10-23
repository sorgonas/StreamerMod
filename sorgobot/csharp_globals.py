"""Typed C# globals over the existing native, platform-separated variable stores."""
import copy,json,math,re
from .core import ActionError
from .core_events import set_global,emit
from .twitch_user_info import user_data,login

UNKNOWN_WRITE='0001-01-01T00:00:00'
INTERNAL_PREFIXES=('core:','command_counter:','command_user_counters:')
INTERNAL_NAMES={'globals_imported','first_words_users','first_words_started_at','first_words_closed_at'}

def name(value):
 if not isinstance(value,str) or not value:raise ActionError('Variablenname fehlt')
 return value

def user_id(value):
 if not isinstance(value,str) or not re.fullmatch(r'[1-9][0-9]*',value):raise ActionError('Gültige numerische Twitch-Nutzer-ID erforderlich')
 return value

def storage(key):return 'core:user:'+json.dumps(key)

def entries(engine,persisted):
 if not persisted:
  stamps=getattr(engine,'variable_session_writes',{})
  return [(key,copy.deepcopy(value),stamps.get(key)) for key,value in engine.user_session_globals.items()]
 rows=[]
 for key,value,stamp in engine.state.db.execute("SELECT kv.key,kv.value,w.last_write FROM kv LEFT JOIN variable_writes w ON kv.key=w.key WHERE kv.key LIKE 'core:user:%'"):
  try:
   identity=json.loads(key[len('core:user:'):])
   if not isinstance(identity,list) or len(identity)!=3 or any(not isinstance(v,str) or not v for v in identity):raise ValueError()
   rows.append((tuple(identity),json.loads(value),stamp))
  except (ValueError,TypeError):raise ActionError('Ungültiger gespeicherter User-Variablenstand') from None
 return rows

def globals_list(engine,persisted):
 if not persisted:
  stamps=getattr(engine,'variable_session_writes',{})
  rows=[(key,copy.deepcopy(value),stamps.get(key)) for key,value in engine.session_globals.items()]
 else:
  rows=[]
  for key,value,stamp,marked in engine.state.db.execute('SELECT kv.key,kv.value,w.last_write,w.is_global FROM kv LEFT JOIN variable_writes w ON kv.key=w.key'):
   if key.startswith('core:user:') or not marked and (key.startswith(INTERNAL_PREFIXES) or key in INTERNAL_NAMES):continue
   rows.append((key,json.loads(value),stamp))
 return [{'VariableName':key,'Value':value,'LastWrite':stamp or UNKNOWN_WRITE,'LastWriteKnown':bool(stamp)} for key,value,stamp in sorted(rows,key=lambda r:r[0])]

def known(engine,uid=None,username=None):
 db=engine.state.db
 if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='known_users'").fetchone():return None
 rows=db.execute('SELECT user_id,user,display_name FROM known_users WHERE platform=? AND '+('user_id=?' if uid is not None else 'user=?'),('twitch',uid if uid is not None else username)).fetchall()
 # Renamed users can have older login rows. Never invent which login is current.
 if len(rows)!=1:return None
 return {'id':rows[0][0],'login':rows[0][1],'display_name':rows[0][2]}

async def resolve(engine,identity,by_id):
 if by_id:return user_id(identity)
 username=login(identity)
 if engine.io.dry_run:
  row=known(engine,username=username)
  if not row or not row['id']:raise ActionError('Twitch-Login in Vorschau nicht bekannt; zuerst echte Nutzerabfrage ausführen oder ById verwenden')
  return user_id(row['id'])
 before=tuple(engine.io.config.get(k) for k in ('broadcaster_id','twitch_client_id','twitch_token'))
 row=user_data(await engine.io.twitch('GET','users',params={'login':username}),username)
 if before!=tuple(engine.io.config.get(k) for k in ('broadcaster_id','twitch_client_id','twitch_token')):raise ActionError('Twitch-Konto während der Nutzerabfrage gewechselt')
 uid=user_id(row['id'])
 from .users import store
 store(engine).remember('twitch',row['login'],uid,row['display_name'])
 return uid

def users_list(engine,var,persisted):
 var=name(var);result=[]
 for key,value,stamp in sorted(entries(engine,persisted),key=lambda r:r[0]):
  platform,uid,variable=key
  if platform!='twitch' or variable!=var:continue
  info=known(engine,uid=uid)
  result.append({'UserId':uid,'UserLogin':info['login'] if info else '', 'UserName':info['display_name'] if info else '',
   'UserType':'twitch','VariableName':var,'Value':value,'LastWrite':stamp or UNKNOWN_WRITE,'LastWriteKnown':bool(stamp),'UserInfoAvailable':bool(info)})
 return result

def number(value):
 if type(value) not in (int,float) or isinstance(value,int) and not -(2**63)<=value<2**63 or not math.isfinite(value):raise ActionError('Increment benötigt eine endliche Zahl im unterstützten 64-Bit-Bereich')
 return value

def mutate_many(engine,changes,persisted):
 # Validate/calculate every target first. Publish events only after a successful transaction.
 events=[];db=engine.state.db
 sessions=copy.deepcopy(engine.user_session_globals);stamps=copy.deepcopy(getattr(engine,'variable_session_writes',{}))
 if db.in_transaction:raise ActionError('User-Variablen-Sammeloperation benötigt eine eigene Transaktion')
 try:
  with db:
   db.execute('BEGIN IMMEDIATE')
   for key,value,delete in changes:
    event=set_global(engine,key[2],value,persisted,delete=delete,user=key[1],platform=key[0],emit_event=False)
    if event:events.append(event)
 except BaseException:
  engine.user_session_globals.clear();engine.user_session_globals.update(sessions);engine.variable_session_writes=stamps
  raise
 for kind,args,filters in events:emit(engine,kind,args,**filters)

async def rpc(engine,method,values):
 if method=='globals_list':return globals_list(engine,values[0])
 if method=='twitch_vars_list':return users_list(engine,*values)
 if method=='all_users_unset':
  var,persisted=values;var=name(var)
  mutate_many(engine,[(key,None,True) for key,_,_ in entries(engine,persisted) if key[2]==var],persisted);return True
 if method=='twitch_var':
  operation,identity,by_id,var,value,persisted=values
  if operation!='unset_user':var=name(var)
  uid=await resolve(engine,identity,by_id);key=('twitch',uid,var)
  if operation=='get':return engine.state.get(storage(key)) if persisted else copy.deepcopy(engine.user_session_globals.get(key))
  if operation=='set':set_global(engine,var,value,persisted,user=uid);return True
  if operation=='unset':set_global(engine,var,persisted=persisted,delete=True,user=uid);return True
  if operation=='unset_user':
   mutate_many(engine,[(key,None,True) for key,_,_ in entries(engine,persisted) if key[:2]==('twitch',uid)],persisted);return True
  raise ActionError('Unbekannte Twitch-Variablenoperation')
 if method=='twitch_vars_bulk':
  operation,identities,var,value,persisted=values;var=name(var)
  if operation not in ('set','increment','increment_create','all_increment'):raise ActionError('Unbekannte Twitch-Sammeloperation')
  rows={key:current for key,current,_ in entries(engine,persisted) if key[0]=='twitch' and key[2]==var}
  if operation=='all_increment':targets=list(rows)
  else:
   if not isinstance(identities,list):raise ActionError('Twitch-Nutzer-IDs müssen eine Liste sein')
   targets=list(dict.fromkeys(('twitch',user_id(uid),var) for uid in identities))
  changes=[]
  if operation!='set':number(value)
  for key in targets:
   if operation=='increment' and key not in rows:continue
   updated=value if operation=='set' else number(number(rows.get(key,0))+value)
   changes.append((key,updated,False))
  mutate_many(engine,changes,persisted);return True
 raise ActionError('Unbekannte C#-Variablenmethode')
