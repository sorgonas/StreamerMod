"""Native pyramid settings and local statistics; never sends chat messages."""
import uuid
from datetime import datetime
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QCheckBox,QSpinBox,QPushButton,QTreeWidget,QTreeWidgetItem
class PyramidsPage(QWidget):
 def __init__(self,host):
  super().__init__();self.host=host;self.loading=False;self.latest=None;self.pending=set()
  layout=QVBoxLayout(self);self.note=QLabel('Emote-Pyramiden: 1, 2, 3, … und wieder zurück bis 1. Zähler werden lokal pro Kanal gespeichert. Erkennung erfolgt im Live-Modus; es werden keine Chatnachrichten gesendet.');self.note.setWordWrap(True);layout.addWidget(self.note)
  row=QHBoxLayout();layout.addLayout(row);self.enabled=QCheckBox('Pyramiden erkennen');row.addWidget(self.enabled);self.shared=QCheckBox('Shared Chat einbeziehen');row.addWidget(self.shared);row.addWidget(QLabel('Mindestbreite'));self.minimum=QSpinBox();self.minimum.setRange(2,100);row.addWidget(self.minimum)
  self.current=QLabel('Laufende Pyramide: —');self.current.setWordWrap(True);layout.addWidget(self.current);self.refresh_button=QPushButton('Gespeicherte Statistik aktualisieren');self.refresh_button.clicked.connect(self.refresh);layout.addWidget(self.refresh_button)
  self.totals=QLabel('Noch nicht geladen.');layout.addWidget(self.totals)
  self.table=QTreeWidget();self.table.setHeaderLabels(['Benutzer','Erfolge','Abbrüche','Twitch-ID']);layout.addWidget(self.table)
  self.recent=QTreeWidget();self.recent.setHeaderLabels(['Zeit (lokal)','Ergebnis','Benutzer','Starter','Emote','Breite']);layout.addWidget(self.recent)
  self.settings_refresh()
  self.enabled.toggled.connect(self.save);self.shared.toggled.connect(self.save);self.minimum.valueChanged.connect(self.save);host.runtime.result.connect(self.result)
 def settings_refresh(self):
  cfg=self.host.store.read('local.json');self.loading=True;self.enabled.setChecked(bool(cfg.get('twitch_pyramids',False)));self.shared.setChecked(bool(cfg.get('twitch_pyramids_shared',False)));self.minimum.setValue(int(cfg.get('twitch_pyramids_minimum',2)));self.loading=False
 def save(self,*_):
  if self.loading:return
  self.host.store.update('local.json',{'twitch_pyramids':self.enabled.isChecked(),'twitch_pyramids_shared':self.shared.isChecked(),'twitch_pyramids_minimum':self.minimum.value()});self.host.runtime.submit('reload');self.host.twitch_page.settings.refresh()
 def refresh(self):
  self.latest=uuid.uuid4().hex;self.pending.add(self.latest);self.host.runtime.submit('twitch_pyramids',requestId=self.latest)
 def observed(self,state,live):
  if not live:self.current.setText('Vorschau: Chat-Erkennung pausiert.');return
  if not state.get('active'):self.current.setText('Laufende Pyramide: keine.');return
  owner=state.get('owner',{});self.current.setText('Laufend: '+state['emote']+' · Zeile '+str(state['row'])+' · Breite '+str(state['width'])+' · '+('absteigend' if state['descending'] else 'aufsteigend')+' · Starter: '+(owner.get('user') or owner.get('userName') or owner.get('userId','—')))
 def result(self,kind,value):
  if kind!='twitch_pyramids' or value.get('requestId') not in self.pending:return
  self.pending.remove(value['requestId'])
  if value['requestId']!=self.latest:return
  if not value.get('success'):self.note.setText(value.get('message','Statistik konnte nicht geladen werden'));return
  data=value['result'];self.table.clear();self.recent.clear();totals=data['totals'];self.totals.setText(str(totals['success'])+' Erfolge · '+str(totals['broken'])+' Abbrüche · '+str(totals['users'])+' Nutzer mit gezählten Ergebnissen'+(' · Anzeige auf 1000 Nutzer begrenzt' if totals['users']>1000 else ''))
  for user in data['users']:self.table.addTopLevelItem(QTreeWidgetItem([user['display'] or user['login'] or user['user_id'],str(user['success']),str(user['broken']),user['user_id']]))
  for item in data['recent']:self.recent.addTopLevelItem(QTreeWidgetItem([datetime.fromtimestamp(item['time']).astimezone().strftime('%d.%m.%Y %H:%M:%S'),'Erfolg' if item['kind']==90033 else 'Abbruch',item['user'] or item['userName'] or item['userId'],item['owner'].get('user') or item['owner'].get('userName') or item['owner'].get('userId',''),item['emote'],str(item['width'])]))
  for table in (self.table,self.recent):
   for col in range(table.columnCount()):table.resizeColumnToContents(col)
  self.observed(data.get('current',{}),not data.get('preview',False));self.note.setText('Lokal gespeicherte Ergebnisse. Erfolge zählen für den abschließenden Nutzer; Abbrüche für den unterbrechenden Nutzer. Die letzten 100 Ergebnisse werden angezeigt.')
