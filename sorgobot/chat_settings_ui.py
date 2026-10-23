"""Chat appearance and Quick Action editor, backed by existing native Actions."""
import json,uuid,copy
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QSpinBox,QCheckBox,QPushButton,QTreeWidget,QTreeWidgetItem,QDialogButtonBox,QLineEdit,QComboBox,QPlainTextEdit,QMessageBox
from .chat_settings import read,validate
class ChatSettings(QDialog):
 def __init__(self,host):
  super().__init__(host);self.host=host;self.value=read(host.store);self.setWindowTitle('Chat Settings');self.resize(680,480);layout=QVBoxLayout(self);form=QFormLayout();layout.addLayout(form)
  self.font=QSpinBox();self.font.setRange(8,36);self.font.setValue(self.value['fontSize']);form.addRow('Font size',self.font)
  self.limit=QSpinBox();self.limit.setRange(20,1000);self.limit.setValue(self.value['historyLimit']);form.addRow('Visible messages',self.limit)
  self.emotes=QCheckBox('Show emote images');self.emotes.setChecked(self.value['showEmotes']);form.addRow('',self.emotes)
  self.table=QTreeWidget();self.table.setHeaderLabels(['Quick Action','Show in','Action']);layout.addWidget(self.table);row=QHBoxLayout();layout.addLayout(row)
  self.table.setColumnWidth(0,230);self.table.setColumnWidth(1,100)
  for label,callback in [('Add',lambda:self.edit(True)),('Edit',lambda:self.edit(False)),('Delete',self.remove)]:
   button=QPushButton(label);button.clicked.connect(callback);row.addWidget(button)
  sync=QPushButton('Save and Sync Browser Docks');sync.clicked.connect(self.save_sync);layout.addWidget(sync)
  box=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);box.accepted.connect(self.accept);box.rejected.connect(self.reject);layout.addWidget(box);self.populate()
 def populate(self):
  self.table.clear();names={a['id']:a['name'] for a in self.host.document['actions']}
  for value in self.value['quickActions']:
   item=QTreeWidgetItem([value['name'],value['scope'],names.get(value['actionId'],'Missing Action')]);item.setData(0,Qt.ItemDataRole.UserRole,value['id']);self.table.addTopLevelItem(item)
 def selected(self):
  item=self.table.currentItem();return next((q for q in self.value['quickActions'] if item and q['id']==item.data(0,Qt.ItemDataRole.UserRole)),None)
 def remove(self):
  value=self.selected()
  if value:self.value['quickActions'].remove(value);self.populate()
 def edit(self,new):
  value={'id':str(uuid.uuid4()),'name':'','scope':'global','actionId':'','args':{}} if new else self.selected()
  if value is None:return
  dialog=QDialog(self);dialog.setWindowTitle('Quick Action');form=QFormLayout(dialog);name=QLineEdit(value['name']);form.addRow('Name',name)
  scope=QComboBox();scope.addItems(['global','user','message','event']);scope.setCurrentText(value['scope']);form.addRow('Show in',scope)
  action=QComboBox()
  for a in self.host.document['actions']:action.addItem(a['name'],a['id'])
  action.setCurrentIndex(max(0,action.findData(value['actionId'])));form.addRow('Action',action)
  args=QPlainTextEdit(json.dumps(value['args'],ensure_ascii=False,indent=2));form.addRow('Custom arguments (JSON)',args)
  box=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);box.accepted.connect(dialog.accept);box.rejected.connect(dialog.reject);form.addRow(box)
  if dialog.exec()!=QDialog.DialogCode.Accepted:return
  try:
   updated={**value,'name':name.text().strip(),'scope':scope.currentText(),'actionId':action.currentData(),'args':json.loads(args.toPlainText())};validate({**self.value,'quickActions':[updated]})
  except (ValueError,TypeError) as exc:QMessageBox.warning(self,'Quick Action',str(exc));return
  if new:self.value['quickActions'].append(updated)
  else:self.value['quickActions']=[updated if q['id']==value['id'] else q for q in self.value['quickActions']]
  self.populate()
 def save_sync(self):
  self.accept()
  if self.result()==QDialog.DialogCode.Accepted:self.host.runtime.submit('chat_dock_sync')
 def accept(self):
  try:self.value=validate({**self.value,'fontSize':self.font.value(),'historyLimit':self.limit.value(),'showEmotes':self.emotes.isChecked()});self.host.store.save('chat.json',self.value)
  except (OSError,ValueError,TypeError) as exc:QMessageBox.warning(self,'Chat Settings',str(exc));return
  super().accept()
