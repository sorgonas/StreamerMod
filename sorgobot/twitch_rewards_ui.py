"""Reward controls submit explicit operations; displaying this page performs no writes."""
import uuid
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QTreeWidget,QTreeWidgetItem,QPushButton,QComboBox,QInputDialog,QDialog,QMessageBox
from .twitch_rewards import editable,validate
from .core import ActionError
ROLE=Qt.ItemDataRole.UserRole
class RewardsPage(QWidget):
 def __init__(self,host):
  super().__init__();self.host=host;self.rows={};self.pending={};self.cursor='';self.redemption_reward=None
  layout=QVBoxLayout(self);self.note=QLabel('Refresh lädt im Live-Modus Twitch-Rewards. Änderungen sind nur für Rewards dieser Twitch-Anwendung möglich. In der Vorschau wird der zuletzt gespeicherte Stand angezeigt.');self.note.setWordWrap(True);layout.addWidget(self.note)
  self.subscriptions=QLabel('');self.subscriptions.setWordWrap(True);layout.addWidget(self.subscriptions)
  self.table=QTreeWidget();self.table.setHeaderLabels(['Title','Cost','Enabled','Paused','Manageable','Group','ID']);layout.addWidget(self.table)
  self.buttons={};row=QHBoxLayout();layout.addLayout(row)
  for label,callback in [('Refresh',self.refresh),('Create',lambda:self.edit(True)),('Edit',self.edit),('Duplicate',self.duplicate),('Delete',self.delete),('Enable / Disable',lambda:self.toggle('is_enabled')),('Pause / Unpause',lambda:self.toggle('is_paused')),('Group',self.group)]:
   button=QPushButton(label);button.clicked.connect(callback);row.addWidget(button);self.buttons[label]=button
  self.table.itemSelectionChanged.connect(self.selected);self.table.itemDoubleClicked.connect(lambda *_:self.edit())
  row=QHBoxLayout();layout.addLayout(row);row.addWidget(QLabel('Redemptions'))
  self.status=QComboBox();self.status.addItems(['UNFULFILLED','FULFILLED','CANCELED']);row.addWidget(self.status)
  self.status.currentIndexChanged.connect(self.reset_cursor)
  for label,callback in [('Load',self.load),('Next Page',lambda:self.load(True)),('Fulfill',lambda:self.redeem('FULFILLED')),('Refund',lambda:self.redeem('CANCELED'))]:
   button=QPushButton(label);button.clicked.connect(callback);row.addWidget(button);self.buttons[label]=button
  self.redemptions=QTreeWidget();self.redemptions.setHeaderLabels(['User','Input','Status','Redeemed At','ID']);layout.addWidget(self.redemptions);self.redemptions.itemSelectionChanged.connect(self.selected)
  host.runtime.result.connect(self.result);self.selected()
  from .app_shortcuts import bind
  for sequence,label in [('Delete','Delete'),('Ctrl+A','Create'),('Ctrl+D','Duplicate'),('Ctrl+O','Enable / Disable')]:bind(self.table,sequence,self.buttons[label].click)
 def subscription_states(self,states):
  rows=[('Added' if kind.endswith('.add') else 'Updated')+': '+row['state']+(' · '+row['message'] if row.get('message') else '') for kind,row in states.items() if 'channel_points_custom_reward_redemption' in kind]
  self.subscriptions.setText('Reward EventSub · '+' | '.join(rows) if rows else 'Reward EventSub: im Live-Modus nach Anmeldung verfügbar')
 def reset_cursor(self,*_):self.cursor='';self.redemptions.clear();self.selected()
 def submit(self,kind,**data):
  request=uuid.uuid4().hex;self.pending[request]=(kind,data);self.host.runtime.submit(kind,requestId=request,**data)
 def current(self):
  item=self.table.currentItem();return self.rows.get(item.data(0,ROLE)) if item else None
 def selected(self):
  reward=self.current();live=bool(getattr(self.host.runtime,'live',False));manage=bool(reward and reward.get('manageable'))
  for key in ('Edit','Delete','Enable / Disable','Pause / Unpause','Load'):self.buttons[key].setEnabled(live and manage)
  self.buttons['Create'].setEnabled(live);self.buttons['Group'].setEnabled(bool(reward));self.buttons['Next Page'].setEnabled(live and manage and bool(self.cursor) and reward['id']==self.redemption_reward)
  self.buttons['Duplicate'].setEnabled(live and bool(reward))
  item=self.redemptions.currentItem();unfulfilled=bool(item and item.text(2)=='UNFULFILLED')
  for key in ('Fulfill','Refund'):self.buttons[key].setEnabled(live and manage and unfulfilled and reward['id']==self.redemption_reward)
 def refresh(self):self.submit('twitch_rewards')
 def show_rewards(self,result):
  old=self.current();identity=old['id'] if old else None;self.rows={r['id']:r for r in result.get('data',[])};self.table.clear()
  for r in self.rows.values():
   item=QTreeWidgetItem([r['title'],str(r['cost']),'Yes' if r.get('is_enabled') else 'No','Yes' if r.get('is_paused') else 'No','Yes' if r.get('manageable') else 'No',r.get('group',''),r['id']]);item.setData(0,ROLE,r['id']);self.table.addTopLevelItem(item)
   if identity==r['id']:self.table.setCurrentItem(item)
  for column in range(7):self.table.resizeColumnToContents(column)
  self.selected();self.note.setText('Gespeicherte Vorschau; keine Twitch-Verbindung geöffnet.' if result.get('preview') else 'Twitch-Rewards aktualisiert. Manageable = mit dieser Twitch-Anwendung erstellt.')
 def duplicate(self):
  reward=self.current()
  if reward and getattr(self.host.runtime,'live',False):self.edit(True,editable(reward))
 def edit(self,new=False,seed=None):
  from .desktop import FieldsDialog
  reward=self.current()
  if not new and (not reward or not reward.get('manageable')):return
  if not getattr(self.host.runtime,'live',False):return
  payload={'title':'New Reward','prompt':'','cost':100,'background_color':'#9147FF','is_enabled':True,'is_user_input_required':False,'should_redemptions_skip_request_queue':False,'is_max_per_stream_enabled':False,'max_per_stream':1,'is_max_per_user_per_stream_enabled':False,'max_per_user_per_stream':1,'is_global_cooldown_enabled':False,'global_cooldown_seconds':60} if new else editable(reward)
  if seed is not None:
   payload.update(seed);payload['title']=(str(payload['title'])[:38]+' (Copy)')[:45]
  for key in ('max_per_stream','max_per_user_per_stream','global_cooldown_seconds'):payload.setdefault(key,1)
  dialog=FieldsDialog('Create Reward' if new else 'Edit Reward',payload,self.host)
  if dialog.exec()!=QDialog.DialogCode.Accepted:return
  try:payload=validate(dialog.value,new)
  except ActionError as exc:QMessageBox.warning(self,'Reward',str(exc));return
  self.submit('twitch_reward_create' if new else 'twitch_reward_update',payload=payload,**({} if new else {'rewardId':reward['id']}))
 def delete(self):
  reward=self.current()
  if reward and QMessageBox.question(self,'Delete Reward','Reward „'+reward['title']+'“ bei Twitch löschen? Offene Einlösungen werden dabei als abgeschlossen markiert.')==QMessageBox.StandardButton.Yes:self.submit('twitch_reward_delete',rewardId=reward['id'])
 def toggle(self,key):
  reward=self.current()
  if reward:self.submit('twitch_reward_update',rewardId=reward['id'],payload={key:not bool(reward.get(key))})
 def group(self):
  reward=self.current()
  if not reward:return
  name,ok=QInputDialog.getText(self,'Reward Group','Group (leer = keine Gruppe)',text=reward.get('group',''))
  if ok:self.submit('twitch_reward_group',rewardId=reward['id'],group=name)
 def load(self,next_page=False):
  reward=self.current()
  if reward:self.submit('twitch_reward_redemptions',rewardId=reward['id'],status=self.status.currentText(),cursor=self.cursor if next_page and self.redemption_reward==reward['id'] else '')
 def redeem(self,status):
  reward=self.current();item=self.redemptions.currentItem()
  if not reward or not item or item.text(2)!='UNFULFILLED' or reward['id']!=self.redemption_reward:return
  self.submit('twitch_reward_redeem',rewardId=reward['id'],redemptionId=item.data(0,ROLE),status=status)
 def result(self,kind,value):
  if not kind.startswith('twitch_reward'):return
  request=value.get('requestId');pending=self.pending.pop(request,None)
  if not pending:return
  if not value.get('success'):self.note.setText(value.get('message','Reward-Anfrage fehlgeschlagen'));return
  if kind=='twitch_rewards':self.show_rewards(value['result'])
  elif kind=='twitch_reward_redemptions':
   self.redemption_reward=pending[1]['rewardId'];self.cursor=value['result'].get('pagination',{}).get('cursor','');self.redemptions.clear()
   for r in value['result'].get('data',[]):
    item=QTreeWidgetItem([r.get('user_name',r.get('user_login','')),r.get('user_input',''),r['status'],r.get('redeemed_at',''),r['id']]);item.setData(0,ROLE,r['id']);self.redemptions.addTopLevelItem(item)
   self.selected();self.note.setText('Einlösungen geladen.')
  elif kind=='twitch_reward_redeem':self.load();self.note.setText('Einlösung von Twitch bestätigt.')
  else:self.refresh();self.note.setText('Änderung bestätigt; Liste wird aktualisiert.')
