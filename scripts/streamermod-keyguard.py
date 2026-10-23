#!/usr/bin/python3
"""Restricted keyd broker: one A-Z key per timed lease, never arbitrary bindings."""
import argparse,asyncio,json,os,signal,socket,stat,struct,time,uuid
from pathlib import Path
MAX_SECONDS=600

class Guard:
 def __init__(self,apply,clock=time.monotonic):self.apply=apply;self.clock=clock;self.leases={};self.active=set();self.lock=asyncio.Lock()
 async def update(self):
  wanted={row['key'] for row in self.leases.values()}
  if wanted!=self.active:
   try:await self.apply(wanted)
   except Exception:
    self.leases.clear();self.active=set()
    await self.apply(set());raise
   self.active=wanted
 async def request(self,data):
  if not isinstance(data,dict):raise ValueError('Objekt erforderlich')
  owner=str(uuid.UUID(data['owner']));op=data.get('op')
  async with self.lock:
   if op=='lock':
    key=data.get('key');duration=data.get('seconds')
    if not isinstance(key,str) or len(key)!=1 or key not in 'abcdefghijklmnopqrstuvwxyz':raise ValueError('Nur einzelne Tasten a–z erlaubt')
    if type(duration) not in (int,float) or not 1<=duration<=MAX_SECONDS:raise ValueError('Dauer 1–600 Sekunden erforderlich')
    if len(self.leases)>=512:raise ValueError('Zu viele aktive Tastensperren')
    identity=str(uuid.uuid4());self.leases[identity]={'owner':owner,'key':key,'until':self.clock()+duration};await self.update()
    return {'leaseId':identity,'key':key,'seconds':duration}
   if op=='release':
    selected=data.get('leaseId')
    self.leases={identity:row for identity,row in self.leases.items() if not (row['owner']==owner and (not selected or selected==identity))};await self.update()
   elif op!='status':raise ValueError('Unbekannter Befehl')
   return {'active':[{'key':row['key'],'remaining':max(0,row['until']-self.clock())} for row in self.leases.values() if row['owner']==owner]}
 async def tick(self):
  async with self.lock:
   self.leases={identity:row for identity,row in self.leases.items() if row['until']>self.clock()};await self.update()
 async def close(self):
  async with self.lock:self.leases.clear();await self.apply(set());self.active=set()

def release_output_keys(keys,sysroot=Path('/sys/class/input'),devroot=Path('/dev/input')):
    # Release an already held letter on keyd's own virtual device. No physical
    # keyboard is read and no key-down event can be injected through this API.
    codes={**dict(zip('qwertyuiop',range(16,26))),**dict(zip('asdfghjkl',range(30,39))),**dict(zip('zxcvbnm',range(44,51)))}
    found=False
    for event in sysroot.glob('event*'):
        try:
            if (event/'device/name').read_text().strip()!='keyd virtual keyboard':continue
            if (event/'device/id/vendor').read_text().strip().lower()!='0fac':continue
            descriptor=os.open(devroot/event.name,os.O_WRONLY|os.O_NONBLOCK)
            try:
                data=b''.join(struct.pack('@llHHi',0,0,1,codes[key],0) for key in sorted(keys))+struct.pack('@llHHi',0,0,0,0,0)
                if os.write(descriptor,data)!=len(data):raise RuntimeError('Tastenfreigabe nicht bestätigt')
            finally:os.close(descriptor)
            found=True
        except OSError:continue
    if keys and not found:raise RuntimeError('Virtuelle keyd-Tastatur ist nicht zugänglich')

async def serve(uid,path):
 async def apply(keys):
  args=[next((p for p in ('/usr/bin/keyd.rvaiya','/usr/bin/keyd','/usr/local/bin/keyd') if os.path.isfile(p)),'/usr/bin/keyd.rvaiya'),'bind','reset',*[key+'=noop' for key in sorted(keys)]]
  process=await asyncio.create_subprocess_exec(*args,stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.DEVNULL)
  try:await asyncio.wait_for(process.wait(),3)
  except BaseException:
   if process.returncode is None:process.kill();await process.wait()
   raise
  if process.returncode:raise RuntimeError('keyd hat die Tastensperre nicht übernommen')
  if keys:release_output_keys(keys)
 guard=Guard(apply);await apply(set());stopping=asyncio.Event()
 async def connection(reader,writer):
  try:
   peer=writer.get_extra_info('socket');_,peer_uid,_=struct.unpack('3i',peer.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
   if peer_uid!=uid:raise ValueError('Zugriff verweigert')
   raw=await asyncio.wait_for(reader.readline(),2)
   if len(raw)>1024:raise ValueError('Anfrage zu groß')
   result=await guard.request(json.loads(raw));reply={'ok':True,**result}
  except Exception as exc:reply={'ok':False,'error':str(exc) if isinstance(exc,(ValueError,RuntimeError)) else 'Tastensperre konnte nicht geändert werden'}
  try:writer.write(json.dumps(reply).encode()+b'\n');await writer.drain()
  finally:writer.close();await writer.wait_closed()
 path=Path(path)
 if path.exists():
  if not stat.S_ISSOCK(path.lstat().st_mode):raise RuntimeError('Socketpfad ist keine Socketdatei')
  path.unlink()
 server=await asyncio.start_unix_server(connection,str(path),limit=1024);path.chmod(0o600);os.chown(path,uid,-1)
 loop=asyncio.get_running_loop()
 for sig in (signal.SIGTERM,signal.SIGINT):loop.add_signal_handler(sig,stopping.set)
 try:
  while not stopping.is_set():
   try:await asyncio.wait_for(stopping.wait(),.1)
   except TimeoutError:await guard.tick()
 finally:server.close();await server.wait_closed();await guard.close();path.unlink(missing_ok=True)

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--uid',type=int,required=True);parser.add_argument('--socket',default='/run/streamermod-keyguard/control.sock');args=parser.parse_args()
 asyncio.run(serve(args.uid,args.socket))
