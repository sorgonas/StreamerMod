"""Native Any/specific selector. Refresh stays in the trigger editor."""
import uuid
from types import SimpleNamespace
from PySide6.QtWidgets import QWidget,QVBoxLayout,QComboBox,QPushButton,QLabel
from .core import ActionError
from .twitch_goals_bits import PowerUpList
class PowerUpPicker(QWidget):
 reward_configuration=True
 def __init__(self,value,parent):
  super().__init__(parent);self.host=parent
  while self.host is not None:
   runtime=getattr(self.host,'runtime',None)
   if callable(getattr(getattr(runtime,'result',None),'connect',None)) and callable(getattr(runtime,'submit',None)):break
   self.host=self.host.parent()
  self.request=None;layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);self.box=QComboBox();layout.addWidget(self.box);self.note=QLabel();self.note.setWordWrap(True);layout.addWidget(self.note);self.refresh=QPushButton('Custom Power-ups aktualisieren');layout.addWidget(self.refresh);self.refresh.clicked.connect(self.load)
  store=getattr(parent,'store',None)
  if not store and self.host:store=getattr(self.host,'store',None)
  try:
   rows=PowerUpList(SimpleNamespace(root=store.root,config=store.read('local.json'))).cached() if store else []
   self.note.setText('Gespeicherte Twitch-Auswahl; im Live-Modus aktualisierbar.')
  except ActionError:rows=[];self.note.setText('Noch keine gespeicherte Twitch-Auswahl. Im Live-Modus aktualisieren.')
  self.populate(rows,value);self.refresh.setEnabled(bool(self.host))
  if self.host:self.host.runtime.result.connect(self.result)
 def populate(self,rows,value):
  self.box.clear();self.box.addItem('Any','')
  for row in sorted(rows,key=lambda r:(r['title'].casefold(),r['id'])):self.box.addItem(row['title']+' ('+str(row['bits'])+' Bits)',row['id'])
  if value and self.box.findData(value)<0:self.box.addItem('Gespeicherte ID: '+value,value)
  self.box.setCurrentIndex(max(0,self.box.findData(value)))
 def value(self):return self.box.currentData()
 def load(self):
  if not self.host:return
  self.request=uuid.uuid4().hex;self.refresh.setEnabled(False);self.note.setText('Lade Custom Power-ups …');self.host.runtime.submit('twitch_custom_power_ups',requestId=self.request)
 def result(self,kind,data):
  if kind!='twitch_custom_power_ups' or data.get('requestId')!=self.request:return
  self.refresh.setEnabled(True)
  if data.get('success'):self.populate(data['result'],self.value());self.note.setText('Auswahl geladen: '+str(len(data['result']))+' Custom Power-ups.')
  else:self.note.setText(data.get('message','Abfrage fehlgeschlagen'))
