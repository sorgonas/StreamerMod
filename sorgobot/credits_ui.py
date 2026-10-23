import json,os,uuid
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QPushButton,QTreeWidget,QTreeWidgetItem,QApplication,QMessageBox,QFileDialog,QDialog,QCheckBox,QSpinBox,QFormLayout,QGroupBox,QHBoxLayout,QLineEdit,QScrollArea,QWidget
from .desktop import FieldsDialog

class CreditsPage(QWidget):
 def __init__(self,host):
  super().__init__(host);self.host=host;self.value={};layout=QVBoxLayout(self)
  label=QLabel('Credits aus tatsächlich erfassten Ereignissen und deinen eigenen Einträgen. Die OBS-Browserquelle für den nativen Abspann lautet:\nhttp://127.0.0.1:8766/credits\nDie Quelle wird im normalen Live-Modus vom Studio bereitgestellt.');label.setWordWrap(True);layout.addWidget(label)
  from .service_management import EVENTS
  settings=QFormLayout();layout.addLayout(settings);self.auto_reset=QSpinBox();self.auto_reset.setRange(0,8760);self.auto_reset.setMaximumWidth(240);self.auto_reset.setSuffix(' h (0 = off)');settings.addRow('Auto Reset',self.auto_reset)
  panels=QHBoxLayout();layout.addLayout(panels)
  events=QGroupBox('Events to Record');events_outer=QVBoxLayout(events);scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setMaximumHeight(270);contents=QWidget();event_layout=QVBoxLayout(contents);scroll.setWidget(contents);events_outer.addWidget(scroll);self.event_boxes={}
  for key in EVENTS:
   box=QCheckBox(key);box.setChecked(True);event_layout.addWidget(box);self.event_boxes[key]=box
  panels.addWidget(events,1)
  present=QGroupBox('User Present (spoke)');present_layout=QVBoxLayout(present);self.role_boxes={}
  from .catalog import ConfigStore
  self.editors_allowed='channel:read:editors' in ConfigStore(host.root).read('local.json').get('twitch_scopes',[])
  for role in ('Editors','Moderators','Subscribers','VIPs'):
   box=QCheckBox(role);present_layout.addWidget(box);self.role_boxes[role]=box
   if role=='Editors' and not self.editors_allowed:box.setEnabled(False);box.setToolTip('Benötigt die Twitch-Freigabe channel:read:editors; derzeit nicht vorhanden.')
  from .core_services import read_config
  self.groups=QTreeWidget();self.groups.setHeaderLabels(['Groups']);self.groups.setMaximumHeight(75)
  for group in read_config(host.root)['userGroups']:
   item=QTreeWidgetItem([group['name']]);item.setData(0,256,group['id']);item.setCheckState(0,Qt.CheckState.Unchecked);self.groups.addTopLevelItem(item)
  present_layout.addWidget(self.groups);self.users=QLineEdit();self.users.setPlaceholderText('Users: login1, login2');present_layout.addWidget(self.users);panels.addWidget(present,1)
  top=QGroupBox('Track Top');top_layout=QVBoxLayout(top);self.track_bits=QCheckBox('Cheer');self.track_rewards=QCheckBox('Channel Points Used');top_layout.addWidget(self.track_bits);top_layout.addWidget(self.track_rewards)
  note=QLabel('Erfasst ab Aktivierung. Bits: All sowie rollierende 30/7 Tage. Channel Points: verwendete Punkte und Anzahl Einlösungen.');note.setWordWrap(True);top_layout.addWidget(note);top_layout.addStretch();panels.addWidget(top,1)
  self.settings_loaded=False
  save_settings=QPushButton('Save Credit Settings');save_settings.clicked.connect(self.save_settings);layout.addWidget(save_settings)
  self.items=QTreeWidget();self.items.setHeaderLabels(['Bereich','Eintrag']);layout.addWidget(self.items)
  for text,callback in [('Aktualisieren',lambda:self.host.runtime.submit('credits_get')),('Eigenen Credit hinzufügen …',self.add),('Credits als JSON exportieren …',self.export),('Overlay-Adresse kopieren',lambda:QApplication.clipboard().setText('http://127.0.0.1:8766/credits')),('Credits zurücksetzen …',self.reset)]:
   button=QPushButton(text);button.clicked.connect(callback);layout.addWidget(button)
 def showEvent(self,event):super().showEvent(event);self.refresh_groups();self.host.runtime.submit('credits_get');self.host.runtime.submit('services_get')
 def refresh_groups(self):
  from .core_services import read_config
  existing={self.groups.topLevelItem(i).data(0,256):(self.groups.topLevelItem(i).text(0),self.groups.topLevelItem(i).checkState(0)) for i in range(self.groups.topLevelItemCount())}
  records=read_config(self.host.root)['userGroups']
  if [(g['id'],g['name']) for g in records]==[(key,value[0]) for key,value in existing.items()]:return
  self.groups.clear()
  for group in records:
   item=QTreeWidgetItem([group['name']]);item.setData(0,256,group['id']);item.setCheckState(0,existing.get(group['id'],('',Qt.CheckState.Unchecked))[1]);self.groups.addTopLevelItem(item)
 def save_settings(self):
  self.host.runtime.submit('services_save',section='credits',value={'autoResetHours':self.auto_reset.value(),'events':[k for k,box in self.event_boxes.items() if box.isChecked()],'presentRoles':[k for k,box in self.role_boxes.items() if box.isChecked()],'presentGroups':[self.groups.topLevelItem(i).data(0,256) for i in range(self.groups.topLevelItemCount()) if self.groups.topLevelItem(i).checkState(0)==Qt.CheckState.Checked],'presentUsers':[v.strip() for v in self.users.text().split(',') if v.strip()],'trackBits':self.track_bits.isChecked(),'trackRewards':self.track_rewards.isChecked()})
 def update_settings(self,value,force=False):
  if not value or (self.settings_loaded and not force):return
  self.auto_reset.setValue(value.get('autoResetHours',0))
  for key,box in self.event_boxes.items():box.setChecked(key in value.get('events',[]))
  for key,box in self.role_boxes.items():box.setChecked(key in value.get('presentRoles',[]))
  for i in range(self.groups.topLevelItemCount()):
   item=self.groups.topLevelItem(i);item.setCheckState(0,Qt.CheckState.Checked if item.data(0,256) in value.get('presentGroups',[]) else Qt.CheckState.Unchecked)
  self.users.setText(', '.join(value.get('presentUsers',[])));self.track_bits.setChecked(value.get('trackBits',False));self.track_rewards.setChecked(value.get('trackRewards',False))
  self.settings_loaded=True
 def update_credits(self,value):
  self.value=value;self.items.clear()
  for area in ('Custom','Events','User','TopBits'):
   for section,rows in value.get(area,{}).items():
    if not isinstance(rows,list):continue
    parent=QTreeWidgetItem([area+' / '+section,str(len(rows))+' Einträge']);self.items.addTopLevelItem(parent)
    for row in rows[:500]:parent.addChild(QTreeWidgetItem(['',row if isinstance(row,str) else json.dumps(row,ensure_ascii=False)]))
  if value.get('TopChannelRewards'):
   parent=QTreeWidgetItem(['TopChannelRewards',str(len(value['TopChannelRewards']))+' Einträge']);self.items.addTopLevelItem(parent)
   for row in value['TopChannelRewards'][:500]:parent.addChild(QTreeWidgetItem(['',json.dumps(row,ensure_ascii=False)]))
  self.items.resizeColumnToContents(0)
 def add(self):
  dialog=FieldsDialog('Eigenen Credit hinzufügen',{'section':'Mitwirkende','name':''},self)
  if dialog.exec()!=QDialog.DialogCode.Accepted:return
  if not dialog.value['section'].strip() or not dialog.value['name'].strip():QMessageBox.warning(self,'Credits','Bereich und Name dürfen nicht leer sein.');return
  self.host.runtime.submit('credits_add',section=dialog.value['section'],name=dialog.value['name'])
 def reset(self):
  if QMessageBox.question(self,'Credits zurücksetzen','Alle bisher erfassten Credits löschen?',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)==QMessageBox.StandardButton.Yes:self.host.runtime.submit('credits_reset')
 def export(self):
  filename=QFileDialog.getSaveFileName(self,'Credits exportieren','credits.json','JSON (*.json)')[0]
  if not filename:return
  path=Path(filename);temp=path.with_name('.'+path.name+'.'+uuid.uuid4().hex+'.tmp')
  try:
   descriptor=os.open(temp,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
   with os.fdopen(descriptor,'w') as f:json.dump(self.value,f,ensure_ascii=False,indent=2)
   os.replace(temp,path)
  except OSError:QMessageBox.warning(self,'Credits','Export konnte nicht gespeichert werden.')
  finally:temp.unlink(missing_ok=True)
