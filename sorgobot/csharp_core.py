"""Native Core services exposed to the C# RPC host."""
import asyncio,copy,contextvars,uuid
from .core import ActionError
from .queue_controls import queue_operation,queue_states

_queued_chain=contextvars.ContextVar('csharp_queued_chain',default=())

def resolve_action(engine,identity,by_id=False):
 if not isinstance(identity,str) or not identity:return None
 if by_id:return engine.actions.get(identity)
 matches=[a for a in engine.actions.values() if a.get('name')==identity]
 if len(matches)>1:raise ActionError('Aktionsname ist nicht eindeutig; ActionById verwenden')
 return matches[0] if matches else None

def action_data(engine):
 queues={q['id']:q for q in engine.document.get('queues',[])};result=[]
 for action in engine.actions.values():
  queue_id=action.get('queue');queue=queues.get(queue_id)
  if queue_id is not None and queue is None:raise ActionError('Action verweist auf eine fehlende Queue')
  try:identity=str(uuid.UUID(action['id']));qid=str(uuid.UUID(queue_id)) if queue_id is not None else str(uuid.UUID(int=0))
  except (ValueError,TypeError,AttributeError):raise ActionError('GetActions benötigt gültige Action-/Queue-GUIDs; Altformat zuerst migrieren') from None
  result.append({'Id':identity,'Name':action['name'],'Enabled':action.get('enabled',True),'Group':action.get('group',''),
   'Queue':queue['name'] if queue else 'Default','QueueId':qid})
 return result

def queue_control(engine,name,paused,clear=False,all_queues=False):
 states=queue_states(engine)
 if all_queues:
  targets=states
 else:
  matches=[s for s in states if ('Default' if s['id'] is None else next(q['name'] for q in engine.document.get('queues',[]) if q['id']==s['id']))==name]
  if len(matches)!=1:raise ActionError('Queue-Name fehlt oder ist nicht eindeutig')
  targets=matches
 # ResumeAll(clear) clears only paused queues, per the original contract.
 if clear:
  for target in targets:
   if not all_queues or target['paused']:engine.clear_queue(target['id'])
 for target in targets:queue_operation(engine,{'type':90051,'queueId':target['id'],'state':'pause' if paused else 'resume'})

async def run_action(engine,identity,arguments,immediately,by_id=False):
 action=resolve_action(engine,identity,by_id)
 if action is None or not action.get('enabled',True) or action.get('migrationBlock'):return {'success':False}
 if not isinstance(arguments,dict):raise ActionError('C# Action-Argumente müssen ein Objekt sein')
 ancestry=(*_queued_chain.get(),*engine.stack.get())
 if action['id'] in ancestry or len(ancestry)>=20:raise ActionError('Zyklischer Aktionsaufruf')
 studio=getattr(engine,'studio',None)
 if studio and studio.closing:return {'success':False}
 if immediately:
  from .action_context import merge_child
  return {'success':True,'arguments':merge_child(arguments,await engine.run(action['id'],arguments))}
 payload=copy.deepcopy(arguments)
 async def queued():
  token=_queued_chain.set(ancestry)
  try:await engine.run(action['id'],payload)
  finally:_queued_chain.reset(token)
 if studio:studio.spawn(queued())
 else:
  tasks=getattr(engine,'csharp_tasks',None)
  if tasks is None:tasks=engine.csharp_tasks=set()
  task=asyncio.create_task(queued(),context=contextvars.Context());tasks.add(task)
  def done(task):
   tasks.discard(task)
   if not task.cancelled() and task.exception():engine.io.trace('csharp_queued_action_error',error=str(task.exception()))
  task.add_done_callback(done)
 return {'success':True}

async def rpc(engine,method,values):
 if method=='actions_list':return action_data(engine)
 if method=='action_exists':return resolve_action(engine,values[0]) is not None
 if method=='action_enabled':
  action=resolve_action(engine,values[0],values[1])
  if action is None:raise ActionError('Zielaktion nicht gefunden')
  action['enabled']=values[2];return True
 if method=='queue_control':queue_control(engine,*values);return True
 if method=='globals_clear':
  from .core_operations import operation
  await operation(engine,{'type':90102 if values[0] else 90101,'platform':'All'},{});return True
 if method=='run':return await run_action(engine,values[0],values[1],values[2],values[3])
 raise ActionError('Unbekannte C# Core-Methode')
