"""Explicit official offline model installation; no implicit downloads on microphone start."""
import hashlib,json,os,stat,tempfile,zipfile
from pathlib import Path,PurePosixPath
import aiohttp
from .core import ActionError

HOME=Path(__file__).resolve().parents[1]/'runtime/speech-models'
MODELS={'de-DE':('vosk-model-small-de-0.15','https://alphacephei.com/vosk/models/vosk-model-small-de-0.15.zip'),
        'en-US':('vosk-model-small-en-us-0.15','https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip')}
REQUIRED=('am/final.mdl','conf/model.conf')
SHA256={'de-DE':'b7e53c90b1f0a38456f4cd62b366ecd58803cd97cd42b06438e2c131713d5e43'}

def digest(path):
 with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

MAX_ARCHIVE=100*1024**2;MAX_UNPACKED=400*1024**2

WHISPER_REVISION='536b0662742c02347bc0e980a01041f333bce120'
WHISPER_FILES=('config.json','model.bin','tokenizer.json','vocabulary.txt','README.md')
WHISPER_SHA256='3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671'
WHISPER={'whisper-small':('faster-whisper-small',WHISPER_REVISION,WHISPER_SHA256),'whisper-base':('faster-whisper-base','ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66','d01c3014881c9c6f3133c182f3d2887eb6ca1c789a7538c5c007196857a0a6a9')}

def model_path(locale,home=HOME,engine='vosk'):
 if locale not in MODELS:raise ActionError('Sprachmodell nicht unterstützt')
 return Path(home)/(WHISPER[engine][0] if engine in WHISPER else MODELS[locale][0])

def ready(locale,home=HOME,engine='vosk'):
 path=model_path(locale,home,engine)
 if engine in WHISPER:return all((path/name).is_file() and (path/name).stat().st_size>0 for name in WHISPER_FILES[:-1])
 return all((path/name).is_file() and (path/name).stat().st_size>0 for name in REQUIRED)

def extract(archive,destination,locale):
 name,url=MODELS[locale];total=0;seen=set()
 with zipfile.ZipFile(archive) as z:
  if len(z.infolist())>2000:raise ActionError('Zu viele Modelldateien')
  for info in z.infolist():
   path=PurePosixPath(info.filename)
   if path.is_absolute() or '..' in path.parts or '\\' in info.filename or not path.parts or path.parts[0]!=name or stat.S_ISLNK(info.external_attr>>16) or info.filename in seen or path.as_posix()!=info.filename.rstrip('/'):raise ActionError('Ungültiger Modellarchivpfad')
   seen.add(info.filename);total+=info.file_size
   if total>MAX_UNPACKED:raise ActionError('Modellarchiv ist zu groß')
  z.extractall(destination)
 path=Path(destination)/name
 if not ready(locale,destination):raise ActionError('Modellarchiv ist unvollständig')
 checksum=digest(archive)
 if locale in SHA256 and checksum!=SHA256[locale]:raise ActionError('Prüfsumme des Sprachmodells stimmt nicht überein')
 files={str(p.relative_to(path)):digest(p) for p in path.rglob('*') if p.is_file()}
 (path/'streamermod-model.json').write_text(json.dumps({'source':url,'archiveSha256':checksum,'license':'Apache-2.0','files':files},indent=2)+'\n')
 return path

async def install(session,locale,home=HOME,progress=None,engine='vosk'):
 if engine in WHISPER:return await install_whisper(session,home,progress,engine)
 import fcntl
 home=Path(home);home.mkdir(parents=True,exist_ok=True);target=model_path(locale,home)
 with (home/'.install.lock').open('a') as lock:
  try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:raise ActionError('Eine Modellinstallation läuft bereits') from None
  if ready(locale,home):return target
  if target.exists():raise ActionError('Unvollständigen Modellordner zuerst entfernen oder umbenennen')
  with tempfile.TemporaryDirectory(prefix='.model-',dir=home) as temp:
   archive=Path(temp)/'model.zip';count=0
   try:
    timeout=aiohttp.ClientTimeout(total=300,sock_read=20)
    async with session.get(MODELS[locale][1],timeout=timeout) as response:
     if response.status!=200:raise ActionError('Sprachmodell konnte nicht heruntergeladen werden')
     length=response.content_length
     if length and length>MAX_ARCHIVE:raise ActionError('Modellarchiv ist zu groß')
     with archive.open('xb') as stream:
      async for chunk in response.content.iter_chunked(256*1024):
       count+=len(chunk)
       if count>MAX_ARCHIVE:raise ActionError('Modellarchiv ist zu groß')
       stream.write(chunk)
       if progress:progress(count,length)
    path=extract(archive,temp,locale);os.rename(path,target)
   except (aiohttp.ClientError,TimeoutError,zipfile.BadZipFile,OSError) as exc:raise ActionError('Modellinstallation fehlgeschlagen; Verbindung und freien Speicher prüfen') from exc
  return target

async def install_whisper(session,home=HOME,progress=None,engine='whisper-small'):
 import fcntl
 home=Path(home);home.mkdir(parents=True,exist_ok=True);target=model_path('de-DE',home,engine);name,revision,checksum=WHISPER[engine]
 with (home/'.install.lock').open('a') as lock:
  try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:raise ActionError('Eine Modellinstallation läuft bereits') from None
  if ready('de-DE',home,engine):return target
  if target.exists():raise ActionError('Unvollständigen Modellordner zuerst entfernen oder umbenennen')
  with tempfile.TemporaryDirectory(prefix='.whisper-',dir=home) as temp:
   path=Path(temp)/name;path.mkdir();count=0
   try:
    for filename in WHISPER_FILES:
     url=f'https://huggingface.co/Systran/{name}/resolve/{revision}/{filename}'
     async with session.get(url,timeout=aiohttp.ClientTimeout(total=1200,sock_read=30)) as response:
      if response.status!=200:raise ActionError('Whisper-Modell konnte nicht heruntergeladen werden')
      with (path/filename).open('xb') as stream:
       async for chunk in response.content.iter_chunked(256*1024):
        count+=len(chunk)
        if count>600*1024**2:raise ActionError('Whisper-Modell ist zu groß')
        stream.write(chunk)
        if progress:progress(count,(465 if engine=='whisper-small' else 142)*1024**2)
    if digest(path/'model.bin')!=checksum:raise ActionError('Whisper-Modellprüfsumme stimmt nicht überein')
    (path/'streamermod-model.json').write_text(json.dumps({'source':'Systran/'+name,'revision':revision,'license':'MIT','files':{name:digest(path/name) for name in WHISPER_FILES}},indent=2)+'\n')
    os.rename(path,target)
   except (aiohttp.ClientError,TimeoutError,OSError) as exc:raise ActionError('Whisper-Installation fehlgeschlagen; Verbindung und Speicher prüfen') from exc
  return target
