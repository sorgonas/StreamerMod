"""Read-only public variable contracts, separated from runtime bookkeeping."""
import copy,json
from .core import ActionError
from .csharp_globals import entries,known,UNKNOWN_WRITE


def options(data):
 persisted=data.get('persisted',True)
 if type(persisted) is not bool:raise ValueError('persisted')
 return persisted


def variable_name(value,optional=False):
 if optional and value is None:return None
 if not isinstance(value,str) or not value or len(value)>1000:raise ValueError('variable')
 return value


def row(name,value,stamp):
 # Preserve JSON types and real write timestamps, never stringify arbitrary objects.
 try:json.dumps(value,allow_nan=False)
 except (ValueError,TypeError,RecursionError):raise ActionError('Variablenwert ist kein gültiger JSON-Wert') from None
 return {'name':name,'value':copy.deepcopy(value),'lastWrite':stamp or UNKNOWN_WRITE}


def global_rows(engine,persisted):
 if persisted:
  rows=engine.state.db.execute('SELECT kv.key,kv.value,w.last_write FROM kv JOIN variable_writes w ON kv.key=w.key WHERE w.is_global=1 ORDER BY kv.key')
  return {name:row(name,json.loads(value),stamp) for name,value,stamp in rows}
 stamps=getattr(engine,'variable_session_writes',{})
 return {name:row(name,value,stamps.get(name)) for name,value in sorted(engine.session_globals.items())}


def request(engine,data):
 op=data['request'];persisted=options(data)
 if op in ('GetGlobals','GetGlobal'):
  values=global_rows(engine,persisted)
  if op=='GetGlobal':
   name=variable_name(data.get('variable'))
   if name not in values:raise ActionError('Globale Variable nicht gefunden')
   return {'variable':values[name],'variables':{name:values[name]},'count':1}
  return {'variables':values,'count':len(values)}
 name=variable_name(data.get('variable'),optional=True);uid=None
 if op=='TwitchGetUserGlobal':
  uid=data.get('userId')
  if not isinstance(uid,str) or not uid:raise ValueError('userId')
 result=[]
 for key,value,stamp in sorted(entries(engine,persisted),key=lambda r:r[0]):
  platform,user,var=key
  if platform!='twitch' or name is not None and var!=name or uid is not None and user!=uid:continue
  meta=known(engine,uid=user)
  result.append(dict(row(var,value,stamp),userId=user,userLogin=meta['login'] if meta else '',userName=meta['display_name'] if meta else '',platform='twitch'))
 if op=='TwitchGetUserGlobal' and name is not None and not result:raise ActionError('Nutzervariable nicht gefunden')
 response={'variables':result,'count':len(result)}
 if uid is not None and name is not None and len(result)==1:response['variable']=result[0]
 return response
