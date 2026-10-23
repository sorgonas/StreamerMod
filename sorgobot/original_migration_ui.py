"""Import review has a concrete path to manual testing; compile without execution."""
import uuid,copy,hashlib,shutil
from pathlib import Path
from PySide6.QtWidgets import QDialog,QVBoxLayout,QLabel,QPlainTextEdit,QPushButton,QHBoxLayout,QInputDialog,QFileDialog,QMessageBox
from .original_migration import plan,release
class ImportReview(QDialog):
 def __init__(self,host,identity):
  super().__init__(host);self.host=host;self.identity=identity;self.pending=None;self.remaining=[];self.checking=False;self.bindings=copy.deepcopy(host.document.get('importBindings',{}));self.setWindowTitle('Import prüfen');self.resize(670,400);layout=QVBoxLayout(self)
  self.status=QLabel('');self.status.setWordWrap(True);layout.addWidget(self.status);self.details=QPlainTextEdit();self.details.setReadOnly(True);layout.addWidget(self.details)
  row=QHBoxLayout();layout.addLayout(row);self.mapping=QPushButton('Abhängigkeiten zuordnen …');self.mapping.clicked.connect(self.map_dependency);row.addWidget(self.mapping);self.midi_config=QPushButton('Original-MIDI laden …');self.midi_config.clicked.connect(self.load_midi_config);row.addWidget(self.midi_config);self.midi_config.setVisible(any(a['id']==identity and any(t.get('type')==15001 for t in a.get('triggers',[])) for a in host.document['actions']));self.start=QPushButton('Für manuelle Tests freigeben');self.start.clicked.connect(self.check);row.addWidget(self.start);close=QPushButton('Schließen');close.clicked.connect(self.reject);row.addWidget(close)
  host.runtime.result.connect(self.on_result);host.runtime.error.connect(self.error);self.runtime_connected=True
  self.finished.connect(self.disconnect_runtime)
  try:
   self.review=plan(host.document,identity,bindings=self.bindings,resources=self.native_resources());self.status.setText('Prüfung für '+self.review['action']['name']);self.details.setPlainText('\n'.join(self.review['notes']+(['\nNoch zu beheben:']+self.review['blockers'] if self.review['blockers'] else ['\nBeim Freigeben wird C# zuerst kompiliert. Die Action wird dabei nicht ausgeführt.','Die Freigabe richtet keine KI-Dienste oder im C#-Code erwarteten globalen Variablen ein.'])));self.start.setEnabled(not self.review['blockers'])
  except (ValueError,KeyError,TypeError) as exc:self.status.setText(str(exc));self.start.setEnabled(False)
 def disconnect_runtime(self,*_):
  if not self.runtime_connected:return
  self.runtime_connected=False
  for signal,slot in [(self.host.runtime.result,self.on_result),(self.host.runtime.error,self.error)]:
   try:signal.disconnect(slot)
   except (RuntimeError,TypeError):pass
 def check(self):
  try:self.review=plan(self.host.document,self.identity,bindings=self.bindings,resources=self.native_resources())
  except (ValueError,KeyError,TypeError) as exc:self.status.setText(str(exc));return
  if self.review['blockers']:self.details.setPlainText('\n'.join(self.review['blockers']));self.start.setEnabled(False);return
  self.checking=True;self.start.setEnabled(False);self.remaining=list({n['id']:n for n in self.review['codes']}.values());self.mapping.setEnabled(False);self.midi_config.setEnabled(False);self.next_code()
 def next_code(self):
  if self.remaining:
   node=self.remaining.pop(0);self.pending=uuid.uuid4().hex;self.status.setText('C# wird kompiliert …');self.host.runtime.submit('csharp_compile',code=node['code'],references=node.get('references',[]),requestId=self.pending)
  else:
   try:
    document=release(self.host.document,self.identity,self.review['signature'],bindings=self.bindings,resources=self.native_resources());previous=self.host.document
    if self.bindings:document['importBindings']=copy.deepcopy(self.bindings)
    self.host.document=document
    try:self.host.save_actions()
    except Exception:self.host.document=previous;raise
    self.checking=False;self.status.setText('Freigegeben. Du kannst die Action jetzt über „Test Action“ ausführen. Automatische Trigger sind aus.');self.accept()
   except (ValueError,OSError) as exc:self.error(str(exc))
 def on_result(self,kind,value):
  if kind!='csharp_compile' or value.get('requestId')!=self.pending or self.pending is None:return
  self.pending=None
  if not value.get('success'):self.error(value.get('message','C# konnte nicht kompiliert werden.'));return
  self.next_code()
 def error(self,message):
  if not self.checking:return
  self.checking=False;self.pending=None;self.mapping.setEnabled(True);self.midi_config.setEnabled(True);self.status.setText(str(message));self.start.setEnabled(True)

 def load_midi_config(self):
  path,_=QFileDialog.getOpenFileName(self,'Original-MIDI-Konfiguration laden',filter='JSON (*.json);;Alle Dateien (*)')
  if not path:return
  try:
   from .original_midi_events import load_config
   with Path(path).open('rb') as stream:definitions=load_config(stream.read(16*1024*1024+1))
   self.bindings.setdefault('midiDefinitions',{}).update(definitions)
   self.review=plan(self.host.document,self.identity,bindings=self.bindings,resources=self.native_resources())
   self.details.setPlainText('MIDI-Ereignisdefinitionen geladen. Linux-Eingang über Abhängigkeiten zuordnen.\n'+'\n'.join(self.review['notes']+self.review['blockers']));self.start.setEnabled(not self.review['blockers'])
  except (OSError,ValueError,UnicodeError) as exc:self.status.setText(str(exc))

 def map_dependency(self):
  try:self._map_dependency()
  except (ValueError,OSError,KeyError,TypeError) as exc:self.status.setText(str(exc))

 def _map_dependency(self):
  from .original_dependencies import choices
  from .core import walk
  rows=choices(self.host.document)
  if not rows:self.status.setText('Keine zuordenbaren Abhängigkeiten vorhanden.');return
  labels=[description+' · '+str(value) for _,value,description,_ in rows]
  selected,ok=QInputDialog.getItem(self,'Abhängigkeit zuordnen','Originalverweis',labels,0,False)
  if not ok:return
  section,source,_,media=rows[labels.index(selected)]
  if section=='files':
   if any(node['type']==48 and node.get('path')==source for action in self.host.document['actions'] for node in walk(action['subActions'])):target,_=QFileDialog.getSaveFileName(self,'Linux-Ziel für Screenshot auswählen',filter='Bilder (*.png *.jpg *.jpeg *.bmp *.webp)')
   elif any(node.get(field)==source for action in self.host.document['actions'] for node in walk(action['subActions']) for field in (('path',) if node['type'] in (90013,90142) else ('workingDir',))):target=QFileDialog.getExistingDirectory(self,'Linux-Ordner auswählen')
   else:target,_=QFileDialog.getOpenFileName(self,'Linux-Datei auswählen')
   if not target:return
   if media:
    store=getattr(self.host,'store',None)
    if store is None:self.status.setText('Projektverzeichnis für Medien fehlt.');return
    original=Path(target);hasher=hashlib.sha256()
    with original.open('rb') as stream:
     while chunk:=stream.read(512*1024):hasher.update(chunk)
    digest=hasher.hexdigest()[:16]
    destination=store.root/'assets'/'imports'/digest/original.name;destination.parent.mkdir(parents=True,exist_ok=True)
    if destination.resolve()!=original.resolve():shutil.copy2(original,destination)
    target=str(destination.resolve())
  elif section=='obs':
   from .obs_connections import definitions
   store=getattr(self.host,'store',None)
   if store is None:self.status.setText('OBS-Konfiguration fehlt.');return
   entries=[r for r in definitions(store.read('local.json')) if r.get('enabled',True)]
   names=[r['name'] for r in entries];name,ok=QInputDialog.getItem(self,'OBS zuordnen','Native Verbindung',names,0,False)
   if not ok:return
   target=entries[names.index(name)]['id'];self.bindings['obsTargets']=[r['id'] for r in entries]
  elif section in ('audioInputs','audioOutputs'):
   direction='input' if section=='audioInputs' else 'output'
   entries=[r for r in self.native_resources().get('audioDevices',[]) if r.get('kind')==direction and r.get('name')]
   names=['Systemstandard · @default',*[r.get('label',r['name'])+' · '+r['name'] for r in entries]]
   name,ok=QInputDialog.getItem(self,'Audiogerät zuordnen','Linux-'+('Eingang' if direction=='input' else 'Ausgang'),names,0,False)
   if not ok:return
   index=names.index(name);target='@default' if index==0 else entries[index-1]['name']
  elif section=='groups':
   from .twitch_random_groups import BUILTINS
   names=list(BUILTINS)+sorted({r['name'] for r in self.native_resources().get('userGroups',[]) if r['name'].casefold() not in BUILTINS})
   target,ok=QInputDialog.getItem(self,'Nutzergruppe zuordnen','Vorhandene Gruppe oder Twitch-Rolle',names,0,False)
   if not ok:return
  elif section=='voiceCommands':
   entries=[r for r in self.native_resources().get('voiceCommands',[]) if r.get('command','').strip()]
   if not entries:self.status.setText('Zuerst unter Voice Control → Commands den passenden Sprachbefehl einrichten.');return
   names=[r['name']+' · '+r['command'] for r in entries];name,ok=QInputDialog.getItem(self,'Dictation zuordnen','Vorhandener Voice Command',names,0,False)
   if not ok:return
   target=entries[names.index(name)]['id']
  elif section=='midiEvents':
   from .original_midi_events import templates
   entries=templates(self.host.document);names=[a['name']+' · '+t.get('commandCode','Any')+' · '+t['id'] for a,t in entries]
   if not entries:self.status.setText('Original-MIDI laden oder zuerst einen nativen MIDI-Message-Trigger mit konkretem Command Type einrichten.');return
   name,ok=QInputDialog.getItem(self,'MIDI-Ereignis zuordnen','Vorhandener Message-Trigger (Filter werden kopiert)',names,0,False)
   if not ok:return
   target=entries[names.index(name)][1]['id']
  elif section in ('midi','midiInputs'):
   entries=self.native_resources().get('midiDevices',[]);entries=[r for r in entries if r.get('enabled',True) and r.get('device') and (section!='midiInputs' or r.get('listen',True))]
   direction='Linux-Eingang' if section=='midiInputs' else 'Linux-Ausgang'
   if not entries:self.status.setText('Zuerst unter MIDI Devices einen '+direction+' einrichten.');return
   names=[r['name']+' · '+r['device'] for r in entries];name,ok=QInputDialog.getItem(self,'MIDI zuordnen',direction,names,0,False)
   if not ok:return
   target=entries[names.index(name)]['id']
  else:
   entries=self.host.document['actions'];names=[a['name']+' · '+a['id'] for a in entries]
   name,ok=QInputDialog.getItem(self,'Action zuordnen','Native Zielaction',names,0,False)
   if not ok:return
   target=entries[names.index(name)]['id']
  self.bindings.setdefault(section,{})[source]=target
  try:
   self.review=plan(self.host.document,self.identity,bindings=self.bindings,resources=self.native_resources())
   self.details.setPlainText('\n'.join(self.review['notes']+self.review['blockers']))
   self.status.setText('Zuordnung übernommen. Freigabe prüft alle Abhängigkeiten erneut.');self.start.setEnabled(not self.review['blockers'])
  except (ValueError,KeyError,TypeError) as exc:self.status.setText(str(exc));self.start.setEnabled(False)

 def native_resources(self):
  store=getattr(self.host,'store',None)
  if store is None:return {}
  from .core_services import read_config
  core=read_config(store.root)
  from .linux_audio_fields import host_snapshot
  devices=sorted(({'kind':r['kind'],'name':r['name'],'label':r.get('label',r['name'])} for r in host_snapshot(self.host) if r.get('kind') in ('input','output') and r.get('name')),key=lambda r:(r['kind'],r['name']))
  return {'commands':store.read('commands.json')['commands'],'timers':store.read('timers.json'),'websocketConnections':core['websocketConnections'],'midiDevices':core['midiDevices'],'userGroups':core['userGroups'],'voiceCommands':core['voiceCommands'],'audioDevices':devices}
