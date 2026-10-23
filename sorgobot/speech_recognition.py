"""Owned, cancellable offline recognition process with generation-checked delivery."""
import asyncio,importlib.util,json,os,signal,sys,shutil
from .core import ActionError
from .speech_models import model_path,ready,install

class Speech:
 def __init__(self,studio):
  self.studio=studio;self.process=None;self.reader=None;self.phase='stopped';self.error='';self.partial='';self.last_text='';self.level=0;self.generation=0;self.deliveries=set();self.download=None;self.progress='';self.lock=asyncio.Lock();self.started=None;self.active_grammar=None
 def settings(self):return self.studio.services.settings['voice']
 def status(self):
  return {'running':self.phase=='listening','phase':self.phase,'error':self.error,'partial':self.partial,'lastText':self.last_text,'level':self.level,'modelReady':ready(self.settings()['locale'],engine=self.settings()['engine']),'modelInstalling':bool(self.download and not self.download.done()),'modelProgress':self.progress}
 async def install_model(self):
  if not self.studio.live:raise ActionError('Modelleinrichtung ist nur im Live-Modus verfügbar')
  if self.process:raise ActionError('Spracherkennung vor der Modelleinrichtung stoppen')
  if self.download and not self.download.done():raise ActionError('Eine Modellinstallation läuft bereits')
  locale=self.settings()['locale']
  def progress(count,total):self.progress=f'{count//1024**2} MiB'+(f' / {total//1024**2} MiB' if total else '')
  self.download=asyncio.create_task(install(self.studio.session,locale,progress=progress,engine=self.settings()['engine']))
  try:await self.download;self.progress='Modell eingerichtet'
  except asyncio.CancelledError:self.progress='Einrichtung abgebrochen'
  finally:self.download=None
 async def cancel_model(self):
  task=self.download
  if task:
   task.cancel();await asyncio.gather(task,return_exceptions=True)
 def command_grammar(self):
  if self.settings()['mode']!='commands':return None
  phrases={str(row.get('command','')).strip().lower() for row in self.studio.core_services.config['voiceCommands'] if row.get('enabled',True) and row.get('location','exact')=='exact' and row.get('command','').strip()}
  if not phrases:raise ActionError('Zuerst einen aktiven exakten Voice-Command anlegen oder Freies Diktat wählen')
  if len(phrases)>200 or any(len(p)>500 for p in phrases):raise ActionError('Command-Vokabular ist zu groß')
  return sorted(phrases)+['[unk]']
 async def refresh_commands(self):
  if self.phase not in ('starting','listening') or self.settings()['mode']!='commands':return
  try:
   grammar=self.command_grammar()
   if grammar==self.active_grammar:return
   await self.stop();await self.start()
  except ActionError as exc:
   await self.stop();self.phase='error';self.error=str(exc);self.studio.services.log('voice',self.error)
 async def start(self):
  async with self.lock:
   if self.process and self.process.returncode is None:return
   if not self.studio.live:raise ActionError('Mikrofonaufnahme ist in der Vorschau gesperrt')
   if self.download and not self.download.done():raise ActionError('Modellinstallation erst abschließen')
   dependency='vosk' if self.settings()['engine']=='vosk' else 'faster_whisper'
   if importlib.util.find_spec(dependency) is None:raise ActionError('Erkennungsengine fehlt; die Python-Projektabhängigkeiten installieren')
   if not shutil.which('parec'):raise ActionError('Audioaufnahme benötigt parec (Paket pulseaudio-utils)')
   settings=self.settings()
   if not ready(settings['locale'],engine=settings['engine']):raise ActionError('Sprachmodell fehlt; zuerst über „Modell einrichten“ installieren')
   grammar=self.command_grammar();self.active_grammar=grammar
   self.generation+=1;generation=self.generation;self.phase='starting';self.error='';self.partial='';self.level=0
   self.started=asyncio.get_running_loop().create_future()
   self.started.add_done_callback(lambda f: f.exception() if not f.cancelled() else None)
   command=[sys.executable,'-m','sorgobot.speech_worker','--model',str(model_path(settings['locale'],engine=settings['engine'])),'--engine',settings['engine'],'--language',settings['locale'][:2],'--device',settings['audioDevice']]
   whisper=settings['engine'].startswith('whisper')
   if whisper:command.append('--options-stdin')
   elif grammar:command.append('--grammar-stdin')
   try:
    self.process=await asyncio.create_subprocess_exec(*command,stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,start_new_session=True,limit=65536)
    if whisper or grammar:
     options={'grammar':grammar,'vocabulary':settings['vocabulary']} if whisper else grammar
     self.process.stdin.write(json.dumps(options,ensure_ascii=False).encode()+b'\n');await self.process.stdin.drain()
    self.process.stdin.close()
    process=self.process;self.reader=asyncio.create_task(self.read(process,generation))
   except BaseException:
    await self._stop();raise
   # Model loading and microphone startup remain cancellable through Stop.
   return
 async def read(self,process,generation):
  try:
   while True:
    line=await asyncio.wait_for(process.stdout.readline(),20)
    if not line:raise ActionError('Erkennungsprozess oder Mikrofon wurde beendet')
    if generation!=self.generation:return
    message=json.loads(line)
    if not isinstance(message,dict):raise ActionError('Ungültige Erkennungsantwort')
    kind=message.get('kind')
    if kind=='ready':
     self.phase='listening'
     if self.started and not self.started.done():self.started.set_result(True)
     self.studio.services.log('voice','Mikrofonaufnahme und lokale Erkennung gestartet')
    elif kind=='processing':self.partial=str(message.get('text',''))[:1000]
    elif kind=='meter':self.level=max(0,min(100,int(message.get('level',0))))
    elif kind=='busy':self.studio.services.log('voice',str(message.get('message','Erkennung ausgelastet'))[:500])
    elif kind=='partial':self.partial=str(message.get('text',''))[:1000];self.level=max(0,min(100,int(message.get('level',0))))
    elif kind=='final':
     text=message.get('text','');confidence=message.get('confidence',0)
     if not isinstance(text,str) or not text.strip() or not isinstance(confidence,(int,float)):continue
     if confidence<self.settings()['confidence']:
      self.studio.services.log('voice',f'Erkennung unter Mindestkonfidenz verworfen ({confidence} %)');continue
     if len(self.deliveries)>=8:self.studio.services.log('voice','Spracherkennung ausgelastet; Äußerung verworfen');continue
     self.last_text=text[:10000];self.partial=''
     task=self.studio.spawn(self.deliver(self.last_text,confidence,generation));self.deliveries.add(task);task.add_done_callback(self.deliveries.discard)
    elif kind=='error':raise ActionError(str(message.get('message','Spracherkennung fehlgeschlagen'))[:500])
  except asyncio.CancelledError:
   if generation==self.generation:self.phase='stopped';self.level=0;self.partial=''
   await asyncio.shield(self.terminate(process))
   raise
  except (ActionError,OSError,ValueError,TypeError,TimeoutError) as exc:
   if generation==self.generation:
    self.phase='error';self.error='Keine Audiodaten empfangen; Mikrofon und Zugriffsrechte prüfen' if isinstance(exc,TimeoutError) else str(exc);self.level=0;self.partial='';self.studio.services.log('voice',self.error)
    if self.started and not self.started.done():self.started.set_exception(ActionError(self.error))
    await self.terminate(process)
  finally:
   if self.process is process and generation==self.generation:self.process=None
 async def deliver(self,text,confidence,generation):
  if generation!=self.generation or self.phase!='listening':return
  await self.studio.core_services.voice(text,{'speechSource':self.settings()['engine'],'speechLocale':self.settings()['locale'],'speechConfidence':confidence})
 async def terminate(self,process):
  if process.returncode is None:
   try:os.killpg(process.pid,signal.SIGTERM)
   except ProcessLookupError:pass
   try:await asyncio.wait_for(process.wait(),3)
   except TimeoutError:
    try:os.killpg(process.pid,signal.SIGKILL)
    except ProcessLookupError:pass
    await process.wait()
 async def _stop(self):
  self.generation+=1;process=self.process;reader=self.reader;self.process=None;self.reader=None
  if reader and reader is not asyncio.current_task():reader.cancel()
  if process:await self.terminate(process)
  if reader and reader is not asyncio.current_task():await asyncio.gather(reader,return_exceptions=True)
  if self.started and not self.started.done():self.started.cancel()
  self.phase='stopped';self.error='';self.partial='';self.level=0;self.last_text=''
 async def stop(self):
  async with self.lock:await self._stop()
 async def close(self):
  await self.cancel_model()
  await self.stop()
