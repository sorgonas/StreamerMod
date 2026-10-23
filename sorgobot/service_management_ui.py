"""Functional Linux management pages for the reference sidebar sections."""
import copy
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QWidget,QVBoxLayout,QFormLayout,QHBoxLayout,QLabel,QCheckBox,QSpinBox,QLineEdit,QPushButton,QTreeWidget,QTreeWidgetItem,QPlainTextEdit,QApplication,QMessageBox,QDialog,QComboBox,QProgressBar
from .service_management import DEFAULTS,EVENTS,config

class ServicePage(QWidget):
 def __init__(self,host,section,log_only=False):
  super().__init__(host);self.host=host;self.section=section;self.log_only=log_only;self.current={};layout=QVBoxLayout(self);self.fields={};form=QFormLayout();layout.addLayout(form)
  hints={'process':'Linux-Prozessüberwachung über /proc. Started/Stopped-Ereignisse werden für aktive Process-Trigger erfasst. Start beginnt mit einem neuen Ausgangsbestand; vorhandene Prozesse werden nicht als neu gestartet gemeldet.',
   'voice':'Integrierte Offline-Spracherkennung. Whisper bietet bessere freie Spracherkennung, benötigt auf älteren CPUs aber mehr Zeit. Nach dem Sprechen kurz pausieren und auf das Ergebnis warten; Vosk ist die schnelle Alternative für feste Befehle. Start öffnet das ausgewählte Mikrofon, Stop beendet Aufnahme und Erkennung. Nur bestätigte Äußerungen oberhalb der Konfidenzschwelle lösen Voice-Commands aus. Audio wird weder gespeichert noch an einen Cloud-Dienst gesendet. Ein externer RecognizeVoice-Texteingang bleibt kompatibel.',
   'http':'Zusätzlicher nativer HTTP-Server: GET /api/status, /GetCredits, /credits; POST /api/actions/{id} und /api/webhooks/{name} mit X-Studio-Token. Webhook: JSON-Objekt, Trigger unter Integrations → StreamerMod; Daten in webhookData, Name in webhookName. Der bestehende OBS-/Voice-Dienst auf Port 8766 bleibt unabhängig. Nur Loopback; Dateimappings unten konfigurieren; Original-Protokoll optional ohne Token, nur lokal.',
   'websocket':'Lokaler WebSocket-Server mit Original-Challenge-Anmeldung. Actions, Commands, Code-Trigger, Credits, Twitch-Konten/-Zuschauer, Variablen, Emotes und Pronomen sind angebunden. Abos für General.Custom, Sprach-, OBS-, Zitat-, Twitch- und Command-Ereignisse. Im Streamer.bot-Client das WebSocket-Passwort verwenden; es bleibt nach Programmneustarts gültig. Passwortänderung bei gestopptem Server möglich. X-Studio-Token bleibt als Header möglich. Nur Loopback; weitere Ereignisse und vollständige Original-Feldverträge sind noch offen.',
   'udp':'Nativer lokaler JSON-Eingang. Format: {"token":"…","request":"DoAction","action":{"id":"…"},"args":{}}. Nur bekannte Action-IDs, maximal 64 KiB. Kein vollständiges Original-UDP-Protokoll.'}
  hint=QLabel(hints[section]);hint.setWordWrap(True);layout.addWidget(hint)
  if not log_only:
   for key,value in DEFAULTS[section].items():
    if section=='voice' and key=='autoStart':continue
    if section=='voice' and key=='locale':
     widget=QComboBox();widget.addItem('Deutsch (de-DE)','de-DE');widget.addItem('English (en-US)','en-US')
    elif section=='voice' and key=='engine':
     widget=QComboBox();widget.addItem('Whisper Small – höhere Qualität, langsamer','whisper-small');widget.addItem('Whisper Base – schneller, etwas weniger genau','whisper-base');widget.addItem('Vosk – schnell, begrenzte Diktatqualität','vosk')
    elif section=='voice' and key=='mode':
     widget=QComboBox();widget.addItem('Freies Diktat','dictation');widget.addItem('Nur aktive exakte Commands','commands')
    elif section=='voice' and key=='audioDevice':
     widget=QComboBox();widget.addItem('Standardmikrofon','@default')
    elif type(value) is bool:widget=QCheckBox();widget.setChecked(value)
    elif type(value) is int:
     widget=QSpinBox();widget.setRange(0 if key=='confidence' else 1024,100 if key=='confidence' else 65535);widget.setValue(value);widget.setMaximumWidth(240)
     if key=='confidence':widget.setSuffix(' %')
    else:
     widget=QLineEdit(value)
     if section=='voice' and key=='vocabulary':widget.setMaxLength(1000);widget.setToolTip('Eigennamen und Fachwörter, durch Kommas getrennt. Unterstützt die Erkennung; ersetzt keine Wörter nachträglich. Aufnahme vor Änderungen stoppen.')
    self.fields[key]=widget;form.addRow({'autoStart':'Auto Start','logDictation':'Log Speech to Text Dictation','port':'Port','endpoint':'Endpoint','recognitionAutoStart':'Auto Start Listen','locale':'Locale','audioDevice':'Audio Input Device','confidence':'Confidence Threshold','mode':'Recognition Mode','originalProtocol':'Original-Protokoll ohne Token (nur lokal)','engine':'Erkennungsengine','vocabulary':'Wortschatzhinweise (Whisper)'}.get(key,key),widget)
   if section in ('http','websocket','udp'):form.addRow('Address',QLabel('127.0.0.1'))
   self.status=QLabel('Warte auf Laufzeitstatus …');form.addRow('Service Status',self.status)
   buttons=QHBoxLayout();layout.addLayout(buttons)
   self.start=QPushButton('Start');self.start.clicked.connect(lambda:host.runtime.submit('services_start',section=section,value=self.values()));buttons.addWidget(self.start)
   self.stop=QPushButton('Stop');self.stop.clicked.connect(lambda:host.runtime.submit('services_control',section=section,running=False));buttons.addWidget(self.stop)
   save=QPushButton('Save Settings');save.clicked.connect(self.save);buttons.addWidget(save)
   if section=='voice':
    self.install=QPushButton('Sprachmodell einrichten');self.install.clicked.connect(lambda:host.runtime.submit('speech_install_model',value=self.values()));buttons.addWidget(self.install)
    self.cancel_install=QPushButton('Modelldownload abbrechen');self.cancel_install.clicked.connect(lambda:host.runtime.submit('speech_cancel_model'));buttons.addWidget(self.cancel_install)
    refresh=QPushButton('Audiogeräte aktualisieren');refresh.clicked.connect(lambda:host.runtime.submit('audio_snapshot'));layout.addWidget(refresh)
    self.model_status=QLabel();layout.addWidget(self.model_status);self.level=QProgressBar();self.level.setRange(0,100);self.level.setFormat('Eingangspegel: %p%');layout.addWidget(self.level)
    self.recognized=QLabel();self.recognized.setWordWrap(True);layout.addWidget(self.recognized)
   if section in ('http','websocket','udp'):
    token=QPushButton('WebSocket-Passwort kopieren' if section=='websocket' else 'Sitzungstoken kopieren');token.clicked.connect(lambda:host.runtime.submit('services_ws_password' if section=='websocket' else 'services_token'));buttons.addWidget(token)
    if section=='websocket':
     self.password_button=QPushButton('WebSocket-Passwort ändern …');self.password_button.clicked.connect(self.change_password);layout.addWidget(self.password_button)
  self.clients=None
  if section=='websocket':self.clients=QTreeWidget();self.clients.setHeaderLabels(['Address','Subscriptions','Authenticated']);layout.addWidget(self.clients)
  if section=='http' and hasattr(host,'store') and hasattr(host,'root'):
   from .http_files_ui import HttpFiles
   self.files=HttpFiles(host);layout.addWidget(self.files)
  self.log=QPlainTextEdit();self.log.setReadOnly(True);layout.addWidget(self.log)
  clear=QPushButton('Clear Log');clear.clicked.connect(lambda:host.runtime.submit('services_clear_log',section=section));layout.addWidget(clear)
  self.loaded=False;self.voice_poll=QTimer(self);self.voice_poll.setInterval(300);self.voice_poll.timeout.connect(lambda:host.runtime.submit('services_get'))
 def showEvent(self,event):
  super().showEvent(event);self.host.runtime.submit('services_get')
  if self.section=='voice':
   self.voice_poll.start()
   if not self.log_only:self.host.runtime.submit('audio_snapshot')
 def hideEvent(self,event):
  self.voice_poll.stop();super().hideEvent(event)
 def change_password(self):
  from PySide6.QtWidgets import QInputDialog
  value,ok=QInputDialog.getText(self,'WebSocket-Passwort','Neues Passwort:',QLineEdit.EchoMode.Password)
  if ok:self.host.runtime.submit('services_ws_password_set',password=value)
 def values(self):
  return {k:w.isChecked() if isinstance(w,QCheckBox) else w.value() if isinstance(w,QSpinBox) else w.currentData() if isinstance(w,QComboBox) else w.text() for k,w in self.fields.items()}
 def save(self):
  self.host.runtime.submit('services_save',section=self.section,value=self.values())
 def update_status(self,value,force=False):
  previous=self.current.get('settings',{}).get(self.section,{})
  self.current=value;state=value.get(self.section,{});settings=value.get('settings',{}).get(self.section,{})
  # Follow an action-driven input change unless the user has an unsaved selection.
  if self.section=='voice' and self.loaded and not force and previous.get('audioDevice')!=settings.get('audioDevice'):
   box=self.fields['audioDevice'];device=settings.get('audioDevice')
   if device is not None and box.currentData()==previous.get('audioDevice'):
    index=box.findData(device)
    if index<0:box.addItem(device,device);index=box.count()-1
    box.setCurrentIndex(index)
  if not self.loaded or force:
   for key,w in self.fields.items():
    v=settings.get(key,DEFAULTS[self.section][key])
    if isinstance(w,QCheckBox):w.setChecked(v)
    elif isinstance(w,QSpinBox):w.setValue(v)
    elif isinstance(w,QComboBox):
     index=w.findData(v)
     if index<0:w.addItem(str(v),v);index=w.count()-1
     w.setCurrentIndex(index)
    else:w.setText(v)
   self.loaded=bool(settings)
  if not self.log_only:
   running=state.get('running',False);self.status.setText(('Running' if running else 'Stopped')+(' — '+state['error'] if state.get('error') else ''))
   self.start.setEnabled(value.get('live',False) and not running and state.get('phase')!='starting');self.stop.setEnabled(value.get('live',False) and (running or state.get('phase') in ('starting','error')))
   for key,w in self.fields.items():w.setEnabled(not running or self.section in ('process','voice') or key=='autoStart')
   if self.section=='websocket':self.password_button.setEnabled(value.get('live',False) and not running)
   if self.section=='voice':
    active=running or state.get('phase')=='starting'
    for key in ('locale','audioDevice','mode','engine','vocabulary'):self.fields[key].setEnabled(not active and not state.get('modelInstalling'))
    self.install.setEnabled(value.get('live',False) and not active and not state.get('modelInstalling'))
    self.cancel_install.setEnabled(bool(state.get('modelInstalling')))
    self.model_status.setText('Modell: '+('bereit' if state.get('modelReady') else 'nicht installiert')+' · '+state.get('modelProgress',''))
    self.level.setValue(state.get('level',0));self.recognized.setText('Zwischentext: '+state.get('partial','')+'\nZuletzt erkannt: '+state.get('lastText',''))
    if state.get('phase')=='starting':self.status.setText('Starting – Modell laden / Mikrofon öffnen …')
  log_text='\n'.join(row['time']+'  '+row['message'] for row in state.get('logs',[]))
  if self.log.toPlainText()!=log_text:
   bar=self.log.verticalScrollBar();position=bar.value();at_end=position>=bar.maximum();self.log.setPlainText(log_text);bar.setValue(bar.maximum() if at_end else position)
  if self.clients is not None:
   self.clients.clear()
   for row in value.get('clients',[]):self.clients.addTopLevelItem(QTreeWidgetItem([row['address'],', '.join(row.get('subscriptions',[])),'Yes' if row['authenticated'] else 'No']))

 def update_audio(self,value):
  if self.section!='voice' or self.log_only:return
  combo=self.fields['audioDevice'];selected=combo.currentData();items=[('Standardmikrofon','@default')]+[(row['label'],row['name']) for row in value.get('items',[]) if row.get('kind')=='input']
  if items==getattr(self,'audio_items',None):return
  self.audio_items=items;combo.clear()
  for label,identity in items:combo.addItem(label,identity)
  index=combo.findData(selected)
  if index<0 and selected:combo.addItem('Nicht verbunden: '+selected,selected);index=combo.count()-1
  combo.setCurrentIndex(max(0,index))

class QuotesPage(QWidget):
 def __init__(self,host):
  super().__init__(host);self.host=host;layout=QVBoxLayout(self);self.rows=[];self.search=QLineEdit();self.search.setPlaceholderText('Filter');self.search.textChanged.connect(self.populate);layout.addWidget(self.search)
  self.table=QTreeWidget();self.table.setHeaderLabels(['ID','Timestamp','User','Platform','Category','Quote']);self.table.setColumnWidth(0,70);self.table.setColumnWidth(1,210);self.table.setColumnWidth(5,450);self.table.itemDoubleClicked.connect(lambda *_:self.edit(False));layout.addWidget(self.table)
  buttons=QHBoxLayout();layout.addLayout(buttons)
  for label,callback in [('Add',lambda:self.edit(True)),('Edit',lambda:self.edit(False)),('Delete',self.remove),('Reload',lambda:host.runtime.submit('quotes_get'))]:
   button=QPushButton(label);button.clicked.connect(callback);buttons.addWidget(button)
  from .app_shortcuts import bind
  bind(self.table,'Delete',self.remove)
 def showEvent(self,event):super().showEvent(event);self.host.runtime.submit('quotes_get')
 def update_rows(self,rows):self.rows=copy.deepcopy(rows);self.populate()
 def populate(self,*_):
  self.table.clear();query=self.search.text().casefold()
  for row in self.rows:
   values=[str(row.get(k,'')) for k in ('quoteId','quoteTimestamp','quoteUser','quotePlatform','quoteGame','quote')]
   if query and query not in ' '.join(values).casefold():continue
   item=QTreeWidgetItem(values);item.setData(0,Qt.ItemDataRole.UserRole,row);self.table.addTopLevelItem(item)
 def selected(self):
  item=self.table.currentItem();return copy.deepcopy(item.data(0,Qt.ItemDataRole.UserRole)) if item else None
 def edit(self,new):
  from .desktop import FieldsDialog
  original=None if new else self.selected()
  if not new and original is None:return
  value={'quote':'','user':'','userId':'','platform':'twitch','currentGame':''} if new else {'quote':original['quote'],'user':original.get('quoteUser',''),'userId':original.get('quoteUserId',''),'platform':original.get('quotePlatform',''),'currentGame':original.get('quoteGame','')}
  dialog=FieldsDialog('Quote',value,self)
  if dialog.exec()!=QDialog.DialogCode.Accepted:return
  self.host.runtime.submit('quotes_add' if new else 'quotes_edit',value=dialog.value,original=original)
 def remove(self):
  row=self.selected()
  if row and QMessageBox.question(self,'Delete Quote',f'Zitat {row["quoteId"]} löschen?',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)==QMessageBox.StandardButton.Yes:self.host.runtime.submit('quotes_delete',original=row)
