"""Versioned project-data backups. Call mutations only with the runtime stopped."""
from contextlib import closing
from datetime import datetime,timezone
import hashlib,json,os,shutil,sqlite3,stat,tempfile,uuid,zipfile
from pathlib import Path,PurePosixPath
from .catalog import _CONFIG_LOCK,validate_action

FORMAT='streamer-linux-project-1'
MAX_BYTES=10*1024**3
MAX_FILES=100000
DB_SUFFIXES={'.db','.sqlite','.sqlite3'}
REQUIRED={'actions.json':dict,'commands.json':dict,'local.json':dict,'timers.json':list,'custom.json':dict}

class BackupError(ValueError):pass

def digest(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 return h.hexdigest()

def asset_target(root):
 path=root/'assets'
 if path.is_symlink():
  target=path.resolve()
  if target!=root.parent/'assets':raise BackupError('Medienlink zeigt außerhalb des unterstützten Projektordners.')
  return target
 return path

def persistent(path):return path.is_file() and not path.is_symlink() and (path.suffix in DB_SUFFIXES or path.suffix=='.json' and path.name!='restore-journal.private.json')

def copy_tree(source,target):
 """Materialize internal links; refuse external links and cycles."""
 source=source.resolve()
 def visit(current,out,ancestors):
  real=current.resolve()
  if not real.is_relative_to(source):raise BackupError('Externer Medien-/Bibliothekslink: '+str(current.name))
  if real in ancestors:raise BackupError('Zyklischer Verzeichnislink: '+str(current.name))
  if real.is_dir():
   out.mkdir(parents=True,exist_ok=True,mode=0o700)
   for child in sorted(real.iterdir()):visit(child,out/child.name,ancestors|{real})
  elif real.is_file():
   before=(real.stat().st_size,real.stat().st_mtime_ns);shutil.copyfile(real,out);out.chmod(0o600)
   if before!=(real.stat().st_size,real.stat().st_mtime_ns) or digest(real)!=digest(out):raise BackupError('Datei während der Sicherung verändert: '+str(current.name))
  else:raise BackupError('Nicht unterstützte Projektdatei: '+str(current.name))
 visit(source,target,set())

def check_db(path):
 try:
  with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)) as db:
   if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise BackupError('Datenbankprüfung fehlgeschlagen: '+path.name)
 except sqlite3.Error as exc:raise BackupError('Ungültige Datenbank: '+path.name) from exc

def validate_config(folder):
 try:
  docs={f.relative_to(folder).as_posix():json.loads(f.read_text(encoding='utf-8-sig')) for f in folder.rglob('*.json')}
  for name,kind in REQUIRED.items():
   if name not in docs or not isinstance(docs[name],kind):raise BackupError('Konfiguration fehlt oder ist ungültig: '+name)
  actions=docs['actions.json'].get('actions');commands=docs['commands.json'].get('commands')
  if not isinstance(actions,list) or not isinstance(commands,list):raise BackupError('Actions-/Commands-Liste fehlt.')
  ids=[]
  for action in actions:validate_action(action);ids.append(action['id'])
  if len(set(ids))!=len(ids):raise BackupError('Doppelte Action-IDs im Backup.')
  if any(not isinstance(c,dict) or not isinstance(c.get('id'),str) for c in commands):raise BackupError('Ungültiger Command im Backup.')
  return {'actions':len(actions),'commands':len(commands),'timers':len(docs['timers.json'])}
 except (OSError,ValueError,TypeError,KeyError,AttributeError) as exc:
  if isinstance(exc,BackupError):raise
  raise BackupError('Projektkonfiguration ist nicht lesbar oder ungültig.') from exc

def summary(manifest,stage):
 result=validate_config(stage/'config')
 result.update(files=len(manifest['files']),bytes=sum(x['bytes'] for x in manifest['files']),databases=sum(x['path'].startswith('state/') and Path(x['path']).suffix in DB_SUFFIXES for x in manifest['files']),created=manifest['created'],sourceRoot=manifest.get('sourceRoot',''),externalReferences=manifest.get('externalReferences',[]))
 return result

def unpack(archive,stage):
 try:
  with zipfile.ZipFile(archive) as z:
   infos=z.infolist();names=[i.filename for i in infos]
   if len(infos)>MAX_FILES or len(set(names))!=len(names):raise BackupError('Zu viele oder doppelte Archiveinträge.')
   if sum(i.file_size for i in infos)>MAX_BYTES:raise BackupError('Backup überschreitet das Größenlimit von 10 GiB.')
   if 'manifest.json' not in names or z.getinfo('manifest.json').file_size>16*1024**2:raise BackupError('Backup-Manifest fehlt oder ist zu groß.')
   for info in infos:
    path=PurePosixPath(info.filename)
    if '\\' in info.filename or path.is_absolute() or '..' in path.parts or path.as_posix()!=info.filename or info.is_dir() or stat.S_ISLNK(info.external_attr>>16):raise BackupError('Unsicherer Archiveintrag.')
    if info.filename!='manifest.json' and (len(path.parts)<2 or path.parts[0] not in ('config','state','assets','csharp-libraries')):raise BackupError('Unbekannter Projektbereich im Archiv.')
    if path.parts[0]=='state' and (len(path.parts)!=2 or not (path.suffix in DB_SUFFIXES or path.suffix=='.json') or path.name=='restore-journal.private.json'):raise BackupError('Nicht unterstützte Laufzeitdatei im Archiv.')
   manifest=json.loads(z.read('manifest.json'))
   if not isinstance(manifest,dict) or manifest.get('format')!=FORMAT or not isinstance(manifest.get('files'),list) or not isinstance(manifest.get('created'),str):raise BackupError('Unbekanntes Backupformat.')
   records={r['path']:r for r in manifest['files']}
   if len(records)!=len(manifest['files']) or set(records)!=set(names)-{'manifest.json'}:raise BackupError('Manifest und Archivinhalt stimmen nicht überein.')
   for name,record in records.items():
    info=z.getinfo(name)
    if type(record['bytes']) is not int or record['bytes']!=info.file_size:raise BackupError('Dateigröße stimmt nicht: '+name)
    target=stage/name;target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    with z.open(name) as src,target.open('xb') as dst:shutil.copyfileobj(src,dst)
    target.chmod(0o600)
    if digest(target)!=record['sha256']:raise BackupError('Prüfsumme stimmt nicht: '+name)
    if name.startswith('state/') and target.suffix in DB_SUFFIXES:check_db(target)
  for name in ('assets','csharp-libraries','state'):(stage/name).mkdir(exist_ok=True)
  return manifest,summary(manifest,stage)
 except (zipfile.BadZipFile,zipfile.LargeZipFile,KeyError,TypeError,UnicodeError,json.JSONDecodeError,OSError) as exc:
  raise BackupError('Backup beschädigt, unvollständig oder nicht lesbar.') from exc

def inspect(archive):
 with tempfile.TemporaryDirectory(prefix='studio-backup-check-') as t:
  return unpack(Path(archive),Path(t))[1]

def create(root,destination,*,quiesced=False):
 if not quiesced:raise BackupError('Für ein konsistentes Projektbackup muss die Engine angehalten sein.')
 root=Path(root).resolve();destination=Path(destination).absolute()
 if destination.exists():raise BackupError('Die Zieldatei existiert bereits; einen neuen Namen wählen.')
 destination.parent.mkdir(parents=True,exist_ok=True)
 # Never recurse into the output while capturing assets/libraries/configuration.
 for area in ('config','assets','csharp-libraries'):
  folder=asset_target(root) if area=='assets' else root/area
  if destination.resolve().is_relative_to(folder.resolve()):raise BackupError('Backup außerhalb von Konfiguration, Medien und Bibliotheken speichern.')
 partial=destination.with_name('.'+destination.name+'.'+uuid.uuid4().hex+'.partial')
 try:
  with _CONFIG_LOCK,tempfile.TemporaryDirectory(prefix='studio-backup-') as tmp:
   stage=Path(tmp)
   for name in ('config','csharp-libraries'):
    folder=root/name
    if folder.exists():copy_tree(folder,stage/name)
   assets=asset_target(root)
   if assets.exists():copy_tree(assets,stage/'assets')
   (stage/'state').mkdir()
   for db in sorted((root/'state').iterdir()):
    if not persistent(db):continue
    target=stage/'state'/db.name
    if db.suffix in DB_SUFFIXES:
     with closing(sqlite3.connect(db.resolve().as_uri()+'?mode=ro',uri=True)) as src,closing(sqlite3.connect(target)) as dst:
      src.backup(dst);dst.execute('PRAGMA journal_mode=DELETE')
     check_db(target)
    else:
     json.loads(db.read_text());shutil.copyfile(db,target)
    target.chmod(0o600)
   records=[{'path':f.relative_to(stage).as_posix(),'bytes':f.stat().st_size,'sha256':digest(f)} for f in sorted(stage.rglob('*')) if f.is_file()]
   if sum(r['bytes'] for r in records)>MAX_BYTES or len(records)>=MAX_FILES:raise BackupError('Projekt überschreitet das Backup-Größenlimit.')
   external=set()
   def references(value,key=''):
    if isinstance(value,dict):
     for k,v in value.items():references(v,k)
    elif isinstance(value,list):
     for v in value:references(v,key)
    elif isinstance(value,str) and key in ('path','file','fileName','image','references') and value.startswith('/') and '%' not in value:
     path=Path(value)
     if path.is_file() and not path.resolve().is_relative_to(root) and not path.resolve().is_relative_to(assets):external.add(value)
   for f in (stage/'config').rglob('*.json'):references(json.loads(f.read_text(encoding='utf-8-sig')))
   manifest={'format':FORMAT,'created':datetime.now(timezone.utc).isoformat(),'files':records,'sourceRoot':str(root),'externalReferences':sorted(external),'scope':'Application config, persistent state, project assets and C# libraries. External OBS/OpenDeck profiles, installed packages and arbitrary external files excluded.'}
   summary(manifest,stage)
   descriptor=os.open(partial,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
   with os.fdopen(descriptor,'wb') as stream:
    with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=3) as z:
     z.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False))
     for record in records:z.write(stage/record['path'],record['path'])
    stream.flush();os.fsync(stream.fileno())
   result=inspect(partial)
   os.link(partial,destination);partial.unlink();destination.chmod(0o600)
   return {**result,'path':str(destination)}
 except (sqlite3.Error,json.JSONDecodeError) as exc:
  raise BackupError('Projekt enthält eine ungültige Datenbank oder JSON-Laufzeitdatei.') from exc
 finally:
  partial.unlink(missing_ok=True)

def write_journal(path,value):
 temp=path.with_suffix('.tmp');descriptor=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
 with os.fdopen(descriptor,'w') as f:json.dump(value,f);f.flush();os.fsync(f.fileno())
 os.replace(temp,path)

def remove(path):
 if path.is_dir() and not path.is_symlink():shutil.rmtree(path)
 else:path.unlink(missing_ok=True)

def recovery(root):
 """Finish cleanup or roll back an interrupted restore before starting the engine."""
 root=Path(root).resolve();path=root/'state/restore-journal.private.json'
 if not path.exists():return False
 try:
  value=json.loads(path.read_text())
  if not isinstance(value,dict) or value.get('phase') not in ('applying','committed') or not isinstance(value.get('plans'),list):raise ValueError()
  plans=value['plans']
  for plan in plans:
   if not isinstance(plan,dict) or not all(isinstance(plan.get(k),str) for k in ('target','stage')) or type(plan.get('existed')) is not bool:raise ValueError()
 except (ValueError,KeyError,TypeError) as exc:raise BackupError('Wiederherstellungsjournal ist beschädigt; Projekt wurde nicht verändert.') from exc
 allowed={root/'config',root/'csharp-libraries',asset_target(root)}
 for plan in plans:
  target=Path(plan['target']);stage=Path(plan['stage'])
  if target not in allowed and not (target.parent==root/'state' and (target.suffix in DB_SUFFIXES or target.suffix=='.json' or any(target.name.endswith(ext+tail) for ext in DB_SUFFIXES for tail in ('-wal','-shm','-journal'))) and target.name!='restore-journal.private.json'):raise BackupError('Wiederherstellungsjournal enthält einen ungültigen Zielpfad.')
  if stage.parent!=target.parent or not stage.name.startswith('.studio-restore-') or stage.is_symlink():raise BackupError('Ungültiges Wiederherstellungsverzeichnis.')
 if value['phase']!='committed':
  for plan in reversed(plans):
   target=Path(plan['target']);old=Path(plan['stage'])/'old'
   if old.exists() or old.is_symlink():
    remove(target);os.replace(old,target)
   elif not plan['existed']:remove(target)
 for plan in plans:remove(Path(plan['stage']))
 path.unlink();return True

def restore(root,archive,*,quiesced=False):
 if not quiesced:raise BackupError('Vor einer Wiederherstellung muss die Engine angehalten sein.')
 root=Path(root).resolve();recovery(root)
 with _CONFIG_LOCK,tempfile.TemporaryDirectory(prefix='studio-restore-check-') as tmp:
  stage=Path(tmp);manifest,result=unpack(Path(archive),stage)
  # Create a separate verified rescue archive before any replacement.
  rescue=root/'state/project-backups'/('before-restore-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]+'.slbackup')
  create(root,rescue,quiesced=True)
  targets=[(stage/'config',root/'config'),(stage/'csharp-libraries',root/'csharp-libraries'),(stage/'assets',asset_target(root))]
  state_names={f.name for f in (stage/'state').iterdir()} if (stage/'state').exists() else set()
  state_names|={f.name for f in (root/'state').iterdir() if persistent(f)}
  targets.extend((stage/'state'/name,root/'state'/name) for name in sorted(state_names))
  targets.extend((stage/'absent-sidecar',root/'state'/(name+tail)) for name in sorted(state_names) if Path(name).suffix in DB_SUFFIXES for tail in ('-wal','-shm','-journal') if (root/'state'/(name+tail)).exists())
  plans=[];journal=root/'state/restore-journal.private.json';journal_written=False
  try:
   for source,target in targets:
    if target.is_symlink():raise BackupError('Wiederherstellungsziel darf kein zusätzlicher Verzeichnislink sein.')
    slot=Path(tempfile.mkdtemp(prefix='.studio-restore-',dir=target.parent))
    plans.append({'target':str(target),'stage':str(slot),'existed':target.exists()})
    if source.exists():
     if source.is_dir():shutil.copytree(source,slot/'new')
     else:shutil.copyfile(source,slot/'new');(slot/'new').chmod(0o600)
   write_journal(journal,{'phase':'applying','plans':plans});journal_written=True
   for plan in plans:
    target=Path(plan['target']);slot=Path(plan['stage'])
    if target.exists():os.replace(target,slot/'old')
    if (slot/'new').exists():os.replace(slot/'new',target)
   write_journal(journal,{'phase':'committed','plans':plans})
  except BaseException:
   if journal_written:recovery(root)
   else:
    for plan in plans:remove(Path(plan['stage']))
   raise
  recovery(root)
  return {**result,'rescue':str(rescue),'restartRequired':True}
