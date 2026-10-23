"""Shared timer state, persistence and scheduling for native actions and C#."""
import random,uuid
from .core import ActionError
from .catalog import ConfigStore,_CONFIG_LOCK

def runtime(engine):
 studio=getattr(engine,'studio',None)
 if studio is None or not hasattr(studio,'timer_definitions'):raise ActionError('Timer-Laufzeit fehlt')
 return studio

def canonical(value):
 try:return str(uuid.UUID(value))
 except (ValueError,TypeError,AttributeError):return None

def resolve(engine,value,by_id=True,legacy=False):
 studio=runtime(engine)
 if not isinstance(value,str) or not value:return None
 key=(canonical(value) or (value if legacy else None)) if by_id else value
 if by_id and key is None:return None
 matches=[t for t in studio.timer_definitions if ((canonical(t['id']) or (t['id'] if legacy else None)) if by_id else t['name'])==key]
 if len(matches)>1:raise ActionError('Timer ist nicht eindeutig; eindeutige ID verwenden')
 return matches[0] if matches else None

def reset(studio,identity):
 studio.timer_due.pop(identity,None)
 getattr(studio,'timer_lines',{}).pop(identity,None)

def update(engine,timer,fields,restart=True):
 studio=runtime(engine)
 if not engine.io.dry_run:
  with _CONFIG_LOCK:
   store=ConfigStore(engine.io.root);doc=store.read('timers.json');matches=[t for t in doc if t['id']==timer['id']]
   if len(matches)!=1:raise ActionError('Gespeicherter Timer fehlt oder ist nicht eindeutig')
   matches[0].update(fields);store.save('timers.json',doc)
 timer.update(fields)
 if restart:reset(studio,timer['id'])

def set_enabled(engine,timer,enabled):
 update(engine,timer,{'enabled':enabled},restart=timer.get('enabled',True)!=enabled)

def tick(studio,now):
 due=studio.timer_due
 if not hasattr(studio,'timer_lines'):studio.timer_lines={}
 lines=studio.timer_lines
 wanted={t['id'] for t in studio.timer_definitions}
 for identity in set(due)|set(lines):
  if identity not in wanted:reset(studio,identity)
 for timer in studio.timer_definitions:
  identity=timer['id']
  if not timer['enabled']:reset(studio,identity);continue
  if identity not in due:
   due[identity]=now+(random.randint(min(timer['interval'],timer['upperInterval']),max(timer['interval'],timer['upperInterval'])) if timer['randomInterval'] else timer['interval'])
   lines[identity]=studio.dispatcher.message_count
  if now>=due[identity] and studio.dispatcher.message_count-lines[identity]>=timer['lines']:
   reset(studio,identity)
   if not timer['repeat']:timer['enabled']=False
   studio.spawn(studio.dispatcher.event(701,{'triggerName':'Timed Actions'},timerId=identity))

async def rpc(engine,method,values):
 studio=runtime(engine)
 if getattr(studio,'closing',False):raise ActionError('Timer-Laufzeit wird geschlossen')
 if method=='timer_enabled':
  target=resolve(engine,values[0],values[1])
  if target is not None:set_enabled(engine,target,values[2])
  return True
 if method=='timer_state':
  target=resolve(engine,values[0]);return bool(target and target.get('enabled',True))
 if method=='timer_interval':
  identity,interval=values
  if type(interval) is not int or not 0<=interval<=2147483647:return True
  target=resolve(engine,identity)
  if target is not None:
   fields={'interval':interval}
   if target.get('randomInterval') and interval>target['upperInterval']:fields={'interval':target['upperInterval'],'upperInterval':interval}
   update(engine,target,fields)
  return True
 raise ActionError('Unbekannte C#-Timer-Methode')
