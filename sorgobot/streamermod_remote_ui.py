"""Direct instance settings with private peer credentials."""
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QLineEdit,QSpinBox,QCheckBox,QPushButton,QTreeWidget,QTreeWidgetItem,QApplication
class RemotePage(QWidget):
 def __init__(self,host):
  super().__init__(host);self.host=host;self.peers=[]
  layout=QVBoxLayout(self)
  hint=QLabel('Direkte StreamerMod-Verbindung: Instanz-ID und Zugangsschlüssel der Gegenseite als Ziel eintragen. Bind-Adresse 127.0.0.1 für lokal, eigene LAN-IP für andere Rechner. HTTP im eigenen LAN, HTTPS bei vorgeschaltetem TLS-Proxy. Keine Streamer.bot-Webseitenanmeldung.');hint.setWordWrap(True);layout.addWidget(hint)
  self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status);form=QFormLayout();layout.addLayout(form)
  self.enabled=QCheckBox('Empfang aktivieren');form.addRow(self.enabled)
  self.name=QLineEdit();self.bind=QLineEdit();self.port=QSpinBox();self.port.setRange(1024,65535)
  for label,widget in [('Instanzname',self.name),('Bind-Adresse',self.bind),('Port',self.port)]:form.addRow(label,widget)
  row=QHBoxLayout();layout.addLayout(row)
  for label,callback in [('Eigene Instanz-ID kopieren',self.copy_id),('Eigenen Zugangsschlüssel kopieren',lambda:host.runtime.submit('remote_token')),('Speichern',self.save),('Aktualisieren',self.refresh)]:
   button=QPushButton(label);button.clicked.connect(callback);row.addWidget(button)
  self.tree=QTreeWidget();self.tree.setHeaderLabels(['Instanzname','Instanz-ID','Basisadresse']);self.tree.itemSelectionChanged.connect(self.select);layout.addWidget(self.tree)
  form=QFormLayout();layout.addLayout(form)
  self.peer_name=QLineEdit();self.peer_id=QLineEdit();self.peer_url=QLineEdit();self.peer_token=QLineEdit();self.peer_token.setEchoMode(QLineEdit.EchoMode.Password);self.peer_token.setPlaceholderText('Leer = gespeicherten Schlüssel beibehalten')
  for label,widget in [('Zielname',self.peer_name),('Ziel-Instanz-ID',self.peer_id),('Zieladresse (z. B. http://192.0.2.10:8060)',self.peer_url),('Ziel-Zugangsschlüssel',self.peer_token)]:form.addRow(label,widget)
  row=QHBoxLayout();layout.addLayout(row)
  for label,callback in [('Ziel hinzufügen / ändern',self.upsert),('Ausgewähltes Ziel entfernen',self.remove)]:
   button=QPushButton(label);button.clicked.connect(callback);row.addWidget(button)
 def showEvent(self,event):super().showEvent(event);self.refresh()
 def refresh(self):self.host.runtime.submit('remote_status')
 def update_status(self,value):
  settings=value.get('settings',{});self.instance_id=settings.get('instanceId','')
  self.status.setText(('Empfang aktiv' if value.get('running') else 'Empfang gestoppt')+' · '+self.instance_id+(' · '+value['error'] if value.get('error') else ''))
  self.name.setText(settings.get('name',''));self.bind.setText(settings.get('bind','127.0.0.1'));self.port.setValue(settings.get('port',8060));self.enabled.setChecked(settings.get('enabled',False))
  self.peers=value.get('peers',[]);self.tree.clear()
  for peer in self.peers:self.tree.addTopLevelItem(QTreeWidgetItem([peer['name'],peer['id'],peer['url']]))
  self.peer_token.clear()
 def copy_id(self):QApplication.clipboard().setText(getattr(self,'instance_id',''))
 def select(self):
  item=self.tree.currentItem()
  if item:self.peer_name.setText(item.text(0));self.peer_id.setText(item.text(1));self.peer_url.setText(item.text(2));self.peer_token.clear()
 def save(self):self.host.runtime.submit('remote_save',{'enabled':self.enabled.isChecked(),'name':self.name.text().strip(),'bind':self.bind.text().strip(),'port':self.port.value(),'peers':self.peers})
 def upsert(self):
  peer={'name':self.peer_name.text().strip(),'id':self.peer_id.text().strip(),'url':self.peer_url.text().strip(),'token':self.peer_token.text()};self.peers=[p for p in self.peers if p['id']!=peer['id']]+[peer];self.save()
 def remove(self):
  item=self.tree.currentItem()
  if item:self.peers=[p for p in self.peers if p['id']!=item.text(1)];self.save()
