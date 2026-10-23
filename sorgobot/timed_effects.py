"""Timed channel-point building blocks: overlapping audio leases and keyguard IPC."""
import asyncio,copy,json,math,re,time,uuid
from pathlib import Path
from .core import ActionError
from .linux_audio import identity,KINDS,variables

STEPS={
97400:('Core · System · Keyboard · Block Letter Temporarily',{'letter':'A','duration':30,'keyboardLayout':'de','waitForFinish':False}),
97401:('Core · System · Keyboard · Release Blocked Letters Early',{}),
97500:('Core · System · Linux Audio · Mute Temporarily',{'audioKind':'input','audioTarget':'@default','duration':30,'waitForFinish':False}),
97501:('Core · System · Linux Audio · Restore Temporary Mutes Early',{}),
}

def duration(value):
 if type(value) is bool:raise ActionError('Dauer muss 1–600 Sekunden betragen')
 try:result=float(value)
 except (TypeError,ValueError):raise ActionError('Dauer muss 1–600 Sekunden betragen') from None
 if not math.isfinite(result) or not 1<=result<=600:raise ActionError('Dauer muss 1–600 Sekunden betragen')
 return result

def letter_key(letter,layout):
 if not isinstance(letter,str) or not re.fullmatch('[A-Za-z]',letter):raise ActionError('Genau einen Buchstaben A–Z oder a–z auswählen')
 if layout not in ('de','us'):raise ActionError('Tastaturlayout de oder us auswählen')
 key=letter.lower()
 return {'y':'z','z':'y'}.get(key,key) if layout=='de' else key

class KeyGuard:
 def __init__(self,path=Path('/run/streamermod-keyguard/control.sock')):self.path=path;self.owner=str(uuid.uuid4())
 async def request(self,op,**values):
  try:
   reader,writer=await asyncio.wait_for(asyncio.open_unix_connection(str(self.path),limit=8192),3)
   try:
    writer.write(json.dumps({'op':op,'owner':self.owner,**values}).encode()+b'\n');await writer.drain()
    reply=json.loads(await asyncio.wait_for(reader.readline(),5))
   finally:writer.close();await writer.wait_closed()
  except (OSError,TimeoutError,ValueError,asyncio.IncompleteReadError):raise ActionError('Tastensperrdienst nicht erreichbar. Einmalige Systemeinrichtung prüfen; keine automatische Wiederholung.') from None
  if not isinstance(reply,dict) or not reply.get('ok'):raise ActionError(reply.get('error','Tastensperre abgewiesen') if isinstance(reply,dict) else 'Ungültige Antwort des Tastensperrdienstes')
  return reply

class Effects:
 def __init__(self,studio,sleep=None):self.sleep=sleep or asyncio.sleep;self.studio=studio;self.audio=studio.audio;self.keyguard=KeyGuard();self.entries={};self.tasks={};self.lock=asyncio.Lock();self.closing=False;self.errors=[]
 def error(self,message):
  self.errors.append(str(message));self.errors=self.errors[-20:];self.studio.io.trace('temporary_effect_error',message=str(message))
 def status(self):
  return {'keyboardSocketPresent':self.keyguard.path.is_socket(),'audioTargets':len(self.entries),'audioLeases':len(self.tasks),'pendingRestores':sum(not row['leases'] for row in self.entries.values()),'errors':list(self.errors)}
 async def restore_entry(self,entry):
  row=entry['row'];fresh=await self.audio.current(row)
  if fresh['mute']!=entry['baseline']:
   await self.audio.execute('set-'+KINDS[row['kind']][1]+'-mute',row['index'],'1' if entry['baseline'] else '0')
   observed=await self.audio.current(row)
   if observed['mute']!=entry['baseline']:raise ActionError('Vorheriger Audiozustand wurde nicht bestätigt; Stummschaltung prüfen')
 async def release(self,lease):
  failures=[]
  async with self.lock:
   async with self.audio.lock:
    for key,entry in list(self.entries.items()):
     entry['leases'].discard(lease)
     if entry['leases']:continue
     try:await self.restore_entry(entry)
     except (ActionError,OSError,TimeoutError) as exc:failures.append(str(exc));continue
     self.entries.pop(key,None)
   self.tasks.pop(lease,None)
  if failures:raise ActionError('; '.join(failures))
 async def mute(self,node,args):
  seconds=duration(node.get('duration',30));kind=node.get('audioKind','input');target=node.get('audioTarget','@default')
  if kind not in ('input','output'):raise ActionError('Temporäre Stummschaltung benötigt Mikrofon oder Ausgabegerät')
  lease=str(uuid.uuid4());new_entries=[]
  async with self.lock:
   if self.closing or len(self.tasks)>=1000:raise ActionError('Temporäre Effekte werden beendet oder sind ausgelastet')
   selected=self.audio.select(await self.audio.snapshot(),kind,target)
   async with self.audio.lock:
    fresh_rows=[await self.audio.current(row) for row in selected]
    try:
     for row in fresh_rows:
      key=identity(row)
      if key not in self.entries:self.entries[key]={'row':copy.deepcopy(row),'baseline':row['mute'],'leases':set()};new_entries.append(key)
      entry=self.entries[key];entry['leases'].add(lease)
      await self.audio.execute('set-'+KINDS[kind][1]+'-mute',row['index'],'1')
      observed=await self.audio.current(row)
      if not observed['mute']:raise ActionError('Temporäre Stummschaltung wurde nicht bestätigt')
    except BaseException:
     for key,entry in list(self.entries.items()):
      entry['leases'].discard(lease)
      if key not in new_entries or entry['leases']:continue
      try:await self.restore_entry(entry);self.entries.pop(key,None)
      except (ActionError,OSError,TimeoutError) as exc:self.error(exc)
     raise
   async def expire():
    try:await self.sleep(seconds)
    finally:await self.release(lease)
   task=asyncio.create_task(expire());self.tasks[lease]=task
   def done(result):
    if not result.cancelled():
     exc=result.exception()
     if exc:self.error(exc)
   task.add_done_callback(done)
  args.update(temporaryEffectId=lease,temporaryDuration=seconds,temporaryEffectFinished=False,audioTargetsCount=len(selected),audioMuted=True)
  if node.get('waitForFinish'):
   try:await task
   finally:
    if task.cancelled() and lease in self.tasks:await self.release(lease)
   observed=[await self.audio.current(row) for row in selected]
   args.update(temporaryEffectFinished=True,audioMuted=observed[0]['mute'],audioResults=[variables(row) for row in observed],audioRestorePending=any(identity(row) in self.entries for row in selected))
 async def restore_all(self):
  tasks=list(self.tasks.values())
  for task in tasks:task.cancel()
  if tasks:await asyncio.gather(*tasks,return_exceptions=True)
  # Includes a lease cancelled before its task first ran, and a failed restore.
  async with self.lock:
   async with self.audio.lock:
    failures=[]
    for key,entry in list(self.entries.items()):
     entry['leases'].clear()
     try:await self.restore_entry(entry)
     except (ActionError,OSError,TimeoutError) as exc:failures.append(str(exc));continue
     self.entries.pop(key,None)
    self.tasks.clear()
  if failures:raise ActionError('; '.join(failures))
 async def close(self):
  self.closing=True
  try:await self.restore_all()
  except (ActionError,OSError,TimeoutError) as exc:self.error(exc)
  if self.keyguard.path.is_socket():
   try:await self.keyguard.request('release')
   except ActionError as exc:self.error(exc)

async def operation(io,node,args):
 kind=node['type']
 if io.dry_run:io.trace('temporary_effect',operation=kind,simulated=True);return
 effects=getattr(getattr(getattr(io,'engine',None),'studio',None),'temporary_effects',None)
 if effects is None:raise ActionError('Laufzeit für temporäre Effekte fehlt')
 if kind==97500:return await effects.mute(node,args)
 if kind==97501:await effects.restore_all();return
 if kind==97401:await effects.keyguard.request('release');return
 seconds=duration(node.get('duration',30));letter=node.get('letter','A');key=letter_key(letter,node.get('keyboardLayout','de'))
 result=await effects.keyguard.request('lock',key=key,seconds=seconds)
 args.update(blockedLetter=letter.upper(),temporaryDuration=seconds,temporaryEffectId=result['leaseId'],temporaryEffectFinished=False)
 if node.get('waitForFinish'):
  try:await asyncio.sleep(seconds)
  finally:await effects.keyguard.request('release',leaseId=result['leaseId'])
  args['temporaryEffectFinished']=True
