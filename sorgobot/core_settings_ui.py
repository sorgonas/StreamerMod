"""Native configuration pages for the additional Core services."""
import copy
import uuid
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QTreeWidget,QTreeWidgetItem,QPushButton,QInputDialog,QMessageBox
from .core_services import read_config

DEFAULTS={
'pointDefinitions':{'name':'New Points','enabled':True,'userMultipliers':{}},
'inputDevices':{'name':'New Input Device','path':'','enabled':True},
'midiDevices':{'name':'New MIDI Device','device':'','enabled':True,'listen':True,'reconnect':True},
'websocketConnections':{'name':'New WebSocket','mode':'client','url':'ws://127.0.0.1:9001/ws','port':9001,'enabled':True},
'cronSchedules':{'name':'New Schedule','expression':'*/5 * * * *','timezone':'Europe/Berlin','enabled':True},

'fileWatchers':{'name':'New File Watcher','path':'','enabled':True,'folder':True,'filter':'*','recursive':False,'readContents':False,'encoding':'utf-8'},
'fileTails':{'name':'New File Tail','path':'','enabled':True,'encoding':'utf-8','readExisting':False},
'voiceCommands':{'name':'New Voice Command','command':'','enabled':True,'location':'exact','caseSensitive':False,'actionId':''},
'userGroups':{'name':'New Group','users':[]},
}
class CoreSettingsPage(QWidget):
    def __init__(self,host,section,view_filter=None):
        super().__init__();self.host=host;self.section=section;self.view_filter=dict(view_filter or {})
        layout=QVBoxLayout(self)
        help_text={'pointDefinitions':'Persistente Punkte nach Definition, Plattform und Login. userMultipliers: JSON-Objekt mit Schlüsseln wie twitch:login. Native Regel: persönlicher Faktor × höchster konfigurierter Gruppenfaktor. Kein automatisches Sammeln; Punkte werden durch Unteraktionen vergeben. Bulk erreicht alle gespeicherten Nutzer. Only Active berücksichtigt aktuelle Anwesenheit oder kürzliche Chataktivität. Original-Import bleibt offen.', 'inputDevices':'Linux-Eingabegerät auswählen (z. B. /dev/input/by-id/…). Nur lesender Zugriff, keine Tastensperre. Der Benutzer benötigt Leserechte für dieses Gerät. Globale Key-Press-Trigger ohne Gerät nutzen das Desktop-Portal und dessen Freigabedialog.',
                   'midiDevices':'ALSA-MIDI-Gerät für Ein-/Ausgabe konfigurieren: /dev/snd/midiC…D…, hw:1,0 oder virtual. Empfangene Nachrichten lösen Core → MIDI → Message aus. listen=false deaktiviert den Empfang für reine Ausgänge. enabled=false deaktiviert den Eintrag. C#-Ausgabe nutzt die id (GUID) oder den Namen dieses Eintrags. Virtuelle Ports müssen passend verbunden werden. Reconnect gilt für Eingänge; Ausgänge werden für jede Sendetransaktion neu geöffnet und danach geschlossen.',
                   'websocketConnections':'mode client verbindet sich zu url; mode server lauscht ausschließlich auf 127.0.0.1:port/ws. Connected, Disconnected und Message unter Core → Websocket. WebSocket Send sendet an den Client oder alle verbundenen Server-Clients. C#-Clientindex: ab 0 in Listenreihenfolge; Server zählen nicht mit, deaktivierte Clients zählen mit. C#-Custom-Serverindex: nur Server ab 0, auch deaktivierte; sessionId aus Server-Triggern für gezieltes Senden/Schließen.',
                   'cronSchedules':'Cron mit fünf Feldern: Minute Stunde Tag Monat Wochentag. Beispiel */5 * * * *: alle fünf Minuten. IANA-Zeitzone, z. B. Europe/Berlin. Trigger Core → Schedule → Cron. Keine nachträgliche Ausführung verpasster Termine.','fileWatchers':'Überwacht Datei- und Ordneränderungen im Live-Modus. folder wählt einen Ordner oder eine einzelne Datei; filter begrenzt Dateinamen (z. B. *.txt). recursive schließt Unterordner ein. readContents liefert bis zu 64 KiB Text als line0, line1 usw. Trigger unter Core → File/Folder Watcher.',
                   'fileTails':'Überwacht neue vollständige Textzeilen. Aktionen mit Core → File IO → File Tail werden im Live-Modus ausgelöst. Relative Pfade beziehen sich auf next-studio.',
                   'voiceCommands':'Sprachbefehle für erkannte Texte. Der vorhandene lokale Voice-Listener kann RecognizeVoice senden. Test Text prüft die Zuordnung ohne Mikrofon; im Live-Modus führt er die zugeordnete Aktion aus.',
                   'userGroups':'Eigene Nutzergruppen für Command-Berechtigungen. users enthält Login-Namen als JSON-Liste; Plattform:login (z. B. twitch:alice) grenzt die Plattform ein. Clear Users From Group entfernt alle Mitglieder.'}[section]
        hint=QLabel(help_text);hint.setWordWrap(True);layout.addWidget(hint)
        self.columns={'fileWatchers':[('Folder','path'),('Filter','filter'),('Enabled','enabled')],
                      'fileTails':[('Name','name'),('File Path','path'),('Enabled','enabled')],
                      'voiceCommands':[('Name','name'),('Command','command'),('Location','location'),('Enabled','enabled')],
                      'midiDevices':[('Name','name'),('Device Name','device'),('Auto Open','enabled'),('Status','_status'),('Reconnect','reconnect')],
                      'websocketConnections':[('Name','name'),('Host / Endpoint','url'),('Auto Start' if self.view_filter.get('mode')=='server' else 'Auto Connect','enabled'),('Status','_status') ]}.get(section)
        if section=='midiDevices' and self.view_filter.get('listen') is False:self.columns=[column for column in self.columns if column[1]!='reconnect']
        self.table=QTreeWidget();self.table.setHeaderLabels([label for label,key in self.columns] if self.columns else ['Name','Enabled / Users','Path / Command'])
        if section=='pointDefinitions':
            self.table.setHeaderLabels(['Name','Enabled','User Multipliers']);self.table.setColumnWidth(0,320);self.table.setColumnWidth(1,100)
        layout.addWidget(self.table)
        buttons=QHBoxLayout();layout.addLayout(buttons)
        for label,callback in [('Add',lambda:self.edit(True)),('Edit',lambda:self.edit(False)),('Delete',self.remove),('Reload',lambda:self.populate())]:
            button=QPushButton(label);button.clicked.connect(callback);buttons.addWidget(button)
        if section=='voiceCommands':
            button=QPushButton('Test Text');button.clicked.connect(self.test_voice);buttons.addWidget(button)
        if section=='pointDefinitions':
            for label,callback in [('Show Balances',self.show_balances),('Set Balance',self.set_balance)]:
                button=QPushButton(label);button.clicked.connect(callback);buttons.addWidget(button)
            self.accounts=QTreeWidget();self.accounts.setHeaderLabels(['Rank','Platform','User','Points']);layout.addWidget(self.accounts)
            host.runtime.result.connect(self.points_result)
        self.bindings=None
        if section=='midiDevices' and self.view_filter.get('listen') is True:
            label=QLabel('Commands / zugeordnete Action-Trigger – zum Bearbeiten doppelt anklicken.');layout.addWidget(label)
            self.bindings=QTreeWidget();self.bindings.setHeaderLabels(['Name','Command Type','Channel','Data','Enabled']);layout.addWidget(self.bindings)
            self.table.itemSelectionChanged.connect(self.populate_bindings);self.bindings.itemDoubleClicked.connect(self.open_binding)
        self.midi_diagnostics=None
        if section=='midiDevices':
            from PySide6.QtWidgets import QPlainTextEdit
            self.midi_diagnostics=QPlainTextEdit();self.midi_diagnostics.setReadOnly(True);self.midi_diagnostics.setMaximumHeight(130);layout.addWidget(self.midi_diagnostics)
        buttons.addStretch();self.table.itemDoubleClicked.connect(lambda *_:self.edit(False));self.populate()
        from .app_shortcuts import core
        core(self)
    def populate(self,entries=None):
        identity=self.selected_id();self.table.clear()
        for value in entries if entries is not None else read_config(self.host.root)[self.section]:
            if any(value.get(key,DEFAULTS[self.section].get(key))!=expected for key,expected in self.view_filter.items()):continue
            item=QTreeWidgetItem([value['name'],str(len(value.get('users',[]))) if self.section=='userGroups' else 'Yes' if value.get('enabled',True) else 'No',value.get('path',value.get('device',value.get('expression',value.get('url',value.get('command','')))))]);
            if self.columns:
                for index,(label,key) in enumerate(self.columns):
                    value_text=value.get(key,DEFAULTS[self.section].get(key,''))
                    if self.section=='websocketConnections' and key=='url' and value.get('mode')=='server':value_text=f'ws://127.0.0.1:{value.get("port",9001)}'+(value.get('endpoint') or '/ws')
                    if key=='_status':value_text='—'
                    item.setText(index,('Yes' if value_text else 'No') if type(value_text) is bool else str(value_text))
            if self.section=='pointDefinitions':item.setText(2,str(len(value.get('userMultipliers',{}))))
            item.setData(0,Qt.ItemDataRole.UserRole,value['id']);self.table.addTopLevelItem(item)
            if value.get('migrationBlock'):
                for column in range(self.table.columnCount()):item.setToolTip(column,value['migrationBlock'])
            if value['id']==identity:self.table.setCurrentItem(item)
        self.populate_bindings()
    def update_service_status(self,states,midi_open,live,diagnostics=None):
        if self.section not in ('midiDevices','websocketConnections'):return
        for i in range(self.table.topLevelItemCount()):
            item=self.table.topLevelItem(i);identity=item.data(0,Qt.ItemDataRole.UserRole)
            if not live:status='Preview'
            elif self.section=='midiDevices':status='Open' if identity in midi_open else 'On demand' if self.view_filter.get('listen') is False else 'Closed'
            else:
                state=states.get(identity,{})
                status='Listening' if state.get('listening') else 'Connected' if state.get('connected') else 'Error' if state.get('error') else 'Stopped'
            if self.section=='midiDevices' and diagnostics and identity in diagnostics.get('errors',{}):status='Error: '+diagnostics['errors'][identity]
            item.setText(3,status)
        if self.midi_diagnostics is not None and diagnostics:
            self.midi_diagnostics.setPlainText('\n'.join(row['deviceName']+': '+str(row['message']) for row in diagnostics.get('messages',[]) if not self.selected_id() or row['deviceId']==self.selected_id()))
    def populate_bindings(self):
        if self.bindings is None:return
        self.bindings.clear();identity=self.selected_id()
        if not identity:return
        for action in self.host.document.get('actions',[]):
            for trigger in action.get('triggers',[]):
                if trigger.get('type')!=90245 or trigger.get('midiDeviceId') not in ('',None,identity):continue
                row=QTreeWidgetItem([action['name'],str(trigger.get('commandCode') or 'All'),str(trigger.get('channel') or 'All'),str(trigger.get('data1',-1)),'Yes' if action.get('enabled',True) and trigger.get('enabled',True) else 'No']);row.setData(0,Qt.ItemDataRole.UserRole,action['id']);row.setData(0,Qt.ItemDataRole.UserRole+1,trigger['id']);self.bindings.addTopLevelItem(row)
    def change_binding(self,remove=False):
        item=self.bindings.currentItem() if self.bindings is not None else None
        if item is None:return
        action=next((a for a in self.host.document['actions'] if a['id']==item.data(0,Qt.ItemDataRole.UserRole)),None)
        if action is None:return
        identity=item.data(0,Qt.ItemDataRole.UserRole+1)
        trigger=next((t for t in action['triggers'] if t['id']==identity),None)
        if trigger is None:return
        if remove:action['triggers']=[t for t in action['triggers'] if t['id']!=identity]
        else:trigger['enabled']=not trigger.get('enabled',True)
        self.host.save_actions();self.populate_bindings()
    def move_voice(self,direction):
        identity=self.selected_id()
        if not identity:return
        doc=read_config(self.host.root);values=doc['voiceCommands'];index=next((i for i,v in enumerate(values) if v['id']==identity),None)
        if index is None:return
        target={'up':index-1,'down':index+1,'top':0,'bottom':len(values)-1}[direction]
        if 0<=target<len(values) and target!=index:values.insert(target,values.pop(index));self.save(doc)
    def open_binding(self,item,*_):
        from PySide6.QtWidgets import QTreeWidgetItemIterator
        self.host.search.clear();self.host.populate_actions();self.host.navigate('actions');iterator=QTreeWidgetItemIterator(self.host.actions)
        while iterator.value():
            row=iterator.value()
            if row.data(0,Qt.ItemDataRole.UserRole)==item.data(0,Qt.ItemDataRole.UserRole):self.host.actions.setCurrentItem(row);return
            iterator+=1
    def selected_id(self):
        item=self.table.currentItem();return item.data(0,Qt.ItemDataRole.UserRole) if item else None
    def save(self,document):
        self.host.store.save('core.json',document);self.host.runtime.submit('reload');self.populate()
    def edit(self,new):
        from .desktop import FieldsDialog
        doc=read_config(self.host.root)
        value={'id':str(uuid.uuid4()),**copy.deepcopy(DEFAULTS[self.section])} if new else next((x for x in doc[self.section] if x['id']==self.selected_id()),None)
        if value is None:return
        if new:value.update(self.view_filter)
        if self.section=='midiDevices' and not value.get('listen',True):value.pop('reconnect',None)
        dialog=FieldsDialog('Core Settings',value,self.host)
        if dialog.exec()!=dialog.DialogCode.Accepted:return
        value=dialog.value
        if not value.get('name','').strip():QMessageBox.warning(self,'Name','Name is required.');return
        if self.section in ('fileTails','fileWatchers') and not value.get('path','').strip():QMessageBox.warning(self,'Path','Path is required.');return
        if self.section=='inputDevices' and not value.get('path','').startswith('/dev/input/'):
            QMessageBox.warning(self,'Input Device','Bitte einen Pfad unter /dev/input/ auswählen.');return
        if self.section=='midiDevices' and not value.get('device','').strip():
            QMessageBox.warning(self,'MIDI','MIDI-Gerät fehlt.');return
        if self.section=='websocketConnections':
            from urllib.parse import urlsplit
            if value.get('mode') not in ('client','server') or not 1<=int(value.get('port',0))<=65535:
                QMessageBox.warning(self,'WebSocket','mode client/server und Port 1–65535 erforderlich.');return
            if value['mode']=='client' and (urlsplit(value.get('url','')).scheme not in ('ws','wss') or not urlsplit(value.get('url','')).hostname):
                QMessageBox.warning(self,'WebSocket','Eine gültige ws:// oder wss:// URL eingeben.');return
        if self.section=='pointDefinitions':
            from .points import multiplier
            try:
                if not isinstance(value.get('userMultipliers'),dict):raise ValueError('userMultipliers muss ein JSON-Objekt sein')
                for key,factor in value['userMultipliers'].items():
                    if ':' not in key or key.split(':',1)[0] not in ('twitch','youtube','kick') or not key.split(':',1)[1]:raise ValueError('Multiplier-Schlüssel: Plattform:login')
                    multiplier(factor)
                normalized={k.casefold():multiplier(v) for k,v in value['userMultipliers'].items()}
                if len(normalized)!=len(value['userMultipliers']):raise ValueError('Doppelte Multiplier-Schlüssel nach Normalisierung')
                value['userMultipliers']=normalized
            except (ValueError,RuntimeError) as error:QMessageBox.warning(self,'Points',str(error));return
        if self.section=='cronSchedules':
            from croniter import croniter
            from zoneinfo import ZoneInfo
            try:
                if len(value.get('expression','').split())!=5 or not croniter.is_valid(value['expression']):raise ValueError('Fünf gültige Cron-Felder erforderlich.')
                ZoneInfo(value.get('timezone',''))
            except (ValueError,KeyError) as error:QMessageBox.warning(self,'Cron',str(error));return
        if self.section=='fileWatchers':
            import codecs
            try:codecs.lookup(value.get('encoding','utf-8'))
            except LookupError:QMessageBox.warning(self,'Encoding','Unbekannte Zeichenkodierung.');return
        if self.section=='voiceCommands' and (not value.get('command','').strip() or value.get('location') not in ('exact','start','anywhere')):QMessageBox.warning(self,'Command','Command and location (exact/start/anywhere) are required.');return
        if self.section=='userGroups' and (not isinstance(value.get('users'),list) or not all(isinstance(u,str) for u in value['users'])):QMessageBox.warning(self,'Users','Users must be a JSON list of login names.');return
        if new:doc[self.section].append(value)
        else:doc[self.section]=[value if x['id']==value['id'] else x for x in doc[self.section]]
        self.save(doc)
    def remove(self):
        identity=self.selected_id()
        if not identity:return
        doc=read_config(self.host.root);doc[self.section]=[x for x in doc[self.section] if x['id']!=identity];self.save(doc)
    def test_voice(self):
        text,ok=QInputDialog.getText(self,'Voice Control','Erkannten Text eingeben')
        if ok:self.host.runtime.submit('voice_text',text=text)

    def show_balances(self):
        identity=self.selected_id()
        if identity:self.host.runtime.submit('points_accounts',definition=identity)
    def set_balance(self):
        identity=self.selected_id()
        if not identity:return
        platform,ok=QInputDialog.getItem(self,'Points','Platform',['twitch','youtube'],0,False)
        if not ok:return
        user,ok=QInputDialog.getText(self,'Points','Login')
        if not ok or not user.strip():return
        amount,ok=QInputDialog.getText(self,'Points','New balance (whole points)')
        if not ok:return
        from .points import integer
        try:amount=integer(amount)
        except RuntimeError as error:QMessageBox.warning(self,'Points',str(error));return
        self.host.runtime.submit('points_set',definition=identity,platform=platform,user=user,amount=amount)
    def points_result(self,kind,result):
        if kind=='points_set':self.show_balances()
        if kind!='points_accounts' or result['definition']!=self.selected_id():return
        self.accounts.clear()
        for account in result['accounts']:
            self.accounts.addTopLevelItem(QTreeWidgetItem([str(account['rank']),account['platform'],account['userName'],str(account['points'])]))
