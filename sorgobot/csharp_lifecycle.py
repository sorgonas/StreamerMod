"""One managed CPHInline instance per code node; bounded cleanup and serialized calls."""
import asyncio,contextvars,json,copy
from .core import ActionError,walk

_active=contextvars.ContextVar('csharp_active_instances',default=())

def signature(node):return node.get('code',''),tuple(node.get('references',[]))

def timeout(value):
 try:value=float(value)
 except (TypeError,ValueError):raise ActionError('C# Timeout muss zwischen 0 und 600 Sekunden liegen') from None
 if not 0<value<=600:raise ActionError('C# Timeout muss zwischen 0 und 600 Sekunden liegen')
 return value

class Worker:
 def __init__(self,engine,node,dll):
  self.engine=engine;self.identity=node['id'];self.signature=signature(node);self.dll=dll
  self.process=None;self.stderr_task=None;self.owner=None;self.dead=False
 async def start(self):
  from .csharp import dotnet_path,dotnet_env
  self.process=await asyncio.create_subprocess_exec(dotnet_path(),str(self.dll),env=dotnet_env(),stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,limit=1024*1024)
  self.drain_stderr()
 def drain_stderr(self):
  if self.stderr_task and not self.stderr_task.done():return
  async def drain():
   tail=b''
   while chunk:=await self.process.stderr.read(4096):tail=(tail+chunk)[-8192:]
   return tail
  self.stderr_task=asyncio.create_task(drain())
 async def exchange(self,operation,arguments=None,method=None,limit=30):
  if self.dead or self.process.returncode is not None:raise ActionError('C#-Instanz wurde beendet')
  self.owner=asyncio.current_task();self.drain_stderr()
  async def session():
   packet={'operation':operation,'arguments':arguments or {},'codeId':self.identity}
   if method:packet['method']=method
   self.process.stdin.write((json.dumps(packet,default=str)+'\n').encode());await self.process.stdin.drain()
   while True:
    raw=await self.process.stdout.readline()
    if not raw:
     await self.kill('Prozessende');raise ActionError('C#-Prozess wurde ohne Ergebnis beendet')
    packet=json.loads(raw)
    if packet.get('type')=='rpc':
     from .csharp import rpc
     try:reply={'result':await rpc(self.engine,packet['method'],packet.get('values',[]))}
     except Exception as error:reply={'error':str(error)}
     self.process.stdin.write((json.dumps(reply,default=str)+'\n').encode());await self.process.stdin.drain()
    elif packet.get('type')=='error':raise ActionError('C#-'+operation+': '+str(packet.get('error')))
    elif packet.get('type')=={'init':'ready','invoke':'done','dispose':'disposed'}[operation]:return packet
    else:raise ActionError('Ungültige C#-Bridge-Antwort')
  try:
   return await asyncio.wait_for(session(),limit)
  except TimeoutError:
   await self.kill('Zeitlimit');raise ActionError('C#-Ausführung überschreitet das Zeitlimit') from None
  except asyncio.CancelledError:
   await self.kill('Abbruch');raise
  except (BrokenPipeError,ConnectionError,ValueError):
   await self.kill('Protokollfehler');raise ActionError('C#-Instanz/Protokoll wurde unterbrochen') from None
  finally:self.owner=None
 async def kill(self,reason=None):
  from .csharp import stop_process
  if self.dead:return
  self.dead=True
  from .csharp_core_services import unregister
  unregister(self.engine,self.identity)
  if reason:self.engine.io.trace('csharp_dispose_skipped',codeId=self.identity,reason=reason)
  if self.process:await stop_process(self.process)
  if self.stderr_task:
   await asyncio.gather(self.stderr_task,return_exceptions=True)
 async def close(self):
  if self.dead:return
  if not self.process:await self.kill();return
  if self.owner and self.owner is not asyncio.current_task():
   owner=self.owner;owner.cancel();await asyncio.gather(owner,return_exceptions=True)
  if self.dead:return
  token=_active.set((*_active.get(),self.identity))
  try:await self.exchange('dispose',limit=3)
  except (ActionError,OSError) as error:self.engine.io.trace('csharp_dispose_error',codeId=self.identity,error=str(error))
  finally:_active.reset(token);await self.kill()

class Instances:
 def __init__(self,engine):
  self.engine=engine;self.workers={};self.locks={};self.owners={};self.closing=False;self.generation=0;self.definitions={}
 def check(self,identity):
  if not isinstance(identity,str) or not identity:raise ActionError('C#-Code-ID fehlt')
  if self.closing or getattr(getattr(self.engine,'studio',None),'closing',False):raise ActionError('C#-Laufzeit wird beendet')
  if identity in _active.get():raise ActionError('Zyklischer C#-Instanzaufruf; dieselbe Codeinstanz ist bereits aktiv')
 def lock(self,identity):return self.locks.setdefault(identity,asyncio.Lock())
 async def _load(self,node):
  from .csharp import compile_code
  identity=node['id'];generation=self.generation
  dll=await compile_code(self.engine.io.root,node.get('code',''),node.get('references',[]))
  if self.closing or getattr(getattr(self.engine,'studio',None),'closing',False):raise ActionError('C#-Laufzeit wird beendet')
  if generation!=self.generation and (identity not in self.definitions or signature(node)!=signature(self.definitions[identity])):raise ActionError('C#-Definition während der Kompilierung geändert oder entfernt')
  worker=self.workers.get(identity)
  if worker and not worker.dead and worker.process.returncode is None and worker.dll==dll:return worker
  if worker:await worker.close();self.workers.pop(identity,None)
  worker=Worker(self.engine,node,dll);self.workers[identity]=worker
  try:await worker.start();await worker.exchange('init',limit=timeout(node.get('timeout',30)))
  except BaseException:
   await worker.close();self.workers.pop(identity,None);raise
  return worker
 async def call(self,node,method=None,arguments=None,limit=30):
  node=copy.deepcopy(node);identity=node.get('id');self.check(identity)
  async with self.lock(identity):
   self.check(identity);self.owners[identity]=asyncio.current_task()
   token=_active.set((*_active.get(),identity))
   try:
    worker=await self._load(node)
    return await worker.exchange('invoke',arguments,method,limit) if method else worker.dll
   finally:_active.reset(token);self.owners.pop(identity,None)
 async def prepare(self,node):return await self.call(node)
 async def invoke(self,node,method,arguments,limit):return await self.call(node,method,arguments,limit)
 async def reconcile(self):
  nodes={n['id']:n for a in self.engine.actions.values() for n in walk(a.get('subActions',[])) if n.get('type')==90060}
  self.generation+=1;self.definitions=copy.deepcopy(nodes)
  for identity,worker in list(self.workers.items()):
   node=nodes.get(identity)
   if node and signature(node)==worker.signature:continue
   async with self.lock(identity):
    if self.workers.get(identity) is worker:await worker.close();self.workers.pop(identity,None)
 async def close(self):
  if self.closing:return
  self.closing=True
  owners={task for task in self.owners.values() if task is not asyncio.current_task()}
  for task in owners:task.cancel()
  await asyncio.gather(*owners,return_exceptions=True)
  await asyncio.gather(*(worker.close() for worker in list(self.workers.values())),return_exceptions=True)
  self.workers.clear()

def instances(engine):
 if not hasattr(engine,'csharp_instances'):engine.csharp_instances=Instances(engine)
 return engine.csharp_instances
