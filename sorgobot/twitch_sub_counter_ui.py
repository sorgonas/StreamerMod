import uuid
from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QCheckBox,QSpinBox,QPushButton,QFormLayout,QHBoxLayout
from .twitch_subscriptions import SCOPE
from .twitch_rewards import scopes
class SubCounterPage(QWidget):
 def __init__(self,host):
  super().__init__();self.host=host;self.latest=None;self.pending={}
  layout=QVBoxLayout(self);layout.addWidget(QLabel('<b>Sub Counter – automatische Zählung</b>'));note=QLabel('Lokaler Ereigniszähler für neue Abos einschließlich Geschenkabos. Resub-Mitteilungen und abgelaufene Abos verändern ihn nicht. Den Zählerstand lesen oder setzen und die aktive Abonnentenzahl abfragen: Actions → Sub-Actions → Twitch → Sub Counter bzw. Subscribers.');note.setWordWrap(True);layout.addWidget(note)
  self.permissions=QLabel('');self.permissions.setWordWrap(True);layout.addWidget(self.permissions);self.summary=QLabel('Zähler noch nicht geladen.');layout.addWidget(self.summary)
  form=QFormLayout();layout.addLayout(form);self.enabled=QCheckBox('Neue Abos automatisch zählen');form.addRow(self.enabled);self.count=QLabel('Noch nicht geladen');form.addRow('Gespeicherter Zählerstand',self.count);self.rollover=QSpinBox();self.rollover.setRange(0,32767);self.rollover.setSpecialValueText('Kein Rollover');form.addRow('Rollover-Grenze',self.rollover)
  explanation=QLabel('Bei Erreichen der Grenze beginnt der Restzähler wieder bei 0 und löst Sub Counter Rollover aus. Eine geänderte Rollover-Grenze normalisiert den Stand auf den Rest und löst kein Ereignis aus. Die Anzahl bisheriger Rollovers bleibt erhalten.');explanation.setWordWrap(True);layout.addWidget(explanation)
  row=QHBoxLayout();layout.addLayout(row);self.refresh_button=QPushButton('Gespeicherten Stand laden');row.addWidget(self.refresh_button);self.save_button=QPushButton('Einstellungen speichern');row.addWidget(self.save_button);self.refresh_button.clicked.connect(lambda:self.submit('read'));self.save_button.clicked.connect(self.save);self.status=QLabel('');self.status.setWordWrap(True);layout.addWidget(self.status);layout.addStretch();host.runtime.result.connect(self.result);self.states({})
 def states(self,states):
  granted=SCOPE in scopes(self.host.store.read('local.json'));state=states.get('channel.subscribe',{}).get('state','noch nicht verbunden');self.permissions.setText(('Abonnenten-Leserecht vorhanden.' if granted else 'Automatische Zählung benötigt die bereits gebündelte Broadcaster-Freigabe.')+' · Neue Abos: '+state);live=bool(getattr(self.host.runtime,'live',False));self.save_button.setEnabled(live)
  for widget in (self.enabled,self.rollover):widget.setEnabled(live)
 def submit(self,operation,**fields):
  request=uuid.uuid4().hex;self.latest=request;self.pending[request]=operation;self.host.runtime.submit('twitch_sub_counter',operation=operation,requestId=request,**fields)
 def save(self):
  if not getattr(self.host.runtime,'live',False):return
  self.submit('save',rollover=self.rollover.value(),enabled=self.enabled.isChecked())
 def result(self,kind,value):
  if kind!='twitch_sub_counter':return
  operation=self.pending.pop(value.get('requestId'),None)
  if operation is None or value['requestId']!=self.latest:return
  if not value.get('success'):self.status.setText(value.get('message','Zähler konnte nicht geladen werden'));return
  row=value['result'];self.count.setText(str(row['count']));self.rollover.setValue(row['rollover']);self.enabled.setChecked(row['enabled']);self.summary.setText('Restzähler: '+str(row['count'])+' · Rollover: '+str(row['rollover'])+' · Bisherige Rollovers: '+str(row['rolloverCount']));self.status.setText('Gespeicherte Vorschau; automatische Erkennung pausiert.' if value.get('preview') else 'Einstellungen gespeichert.' if operation=='save' else 'Gespeicherter Stand geladen.')
