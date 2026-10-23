import uuid
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QTreeWidget,QTreeWidgetItem,QPushButton,QDialog,QInputDialog,QMessageBox
from .twitch_votes import payload
from .core import ActionError
ROLE=Qt.ItemDataRole.UserRole
class VotesPage(QWidget):
 def __init__(self,host,kind):
  super().__init__();self.host=host;self.kind=kind;self.rows={};self.pending={};self.cursor=''
  layout=QVBoxLayout(self);self.note=QLabel('Refresh lädt Twitch-Daten im Live-Modus; die Vorschau zeigt den gespeicherten Stand. Create startet nach Bestätigung sofort eine öffentliche Abstimmung.');self.note.setWordWrap(True);layout.addWidget(self.note)
  self.permissions=QLabel('');self.permissions.setWordWrap(True);layout.addWidget(self.permissions)
  self.table=QTreeWidget();self.table.setHeaderLabels(['Title','Status','Duration','Created','ID']);layout.addWidget(self.table);self.table.itemSelectionChanged.connect(self.selected)
  row=QHBoxLayout();layout.addLayout(row);self.buttons={}
  actions=[('Grant Access',lambda:host.twitch_page.login(False,['polls','predictions'])),('Refresh',self.refresh),('Next Page',lambda:self.refresh(True)),('Create',self.create)]
  actions+= [('Terminate',lambda:self.change('TERMINATED')),('Archive',lambda:self.change('ARCHIVED'))] if kind=='polls' else [('Lock',lambda:self.change('LOCKED')),('Cancel / Refund',lambda:self.change('CANCELED')),('Resolve',self.resolve)]
  for label,callback in actions:
   button=QPushButton(label);button.clicked.connect(callback);row.addWidget(button);self.buttons[label]=button
  self.details=QTreeWidget();self.details.setHeaderLabels(['Choice / Outcome','Votes / Users','Channel Points','ID']);layout.addWidget(self.details)
  self.setToolTip('Jeder Grant-Access-Knopf ergänzt gemeinsam die Rechte aller eingebauten Twitch-Funktionen für das Broadcaster-Konto.');host.runtime.result.connect(self.result);self.selected()
 def submit(self,operation,**data):
  request=uuid.uuid4().hex;self.pending[request]=(operation,data);self.host.runtime.submit('twitch_votes',requestId=request,voteKind=self.kind,operation=operation,**data)
 def current(self):
  item=self.table.currentItem();return self.rows.get(item.data(0,ROLE)) if item else None
 def selected(self):
  row=self.current();live=bool(getattr(self.host.runtime,'live',False));state=row.get('status','') if row else ''
  self.buttons['Create'].setEnabled(live);self.buttons['Next Page'].setEnabled(live and bool(self.cursor))
  for label,statuses in [('Terminate',('ACTIVE',)),('Archive',('ACTIVE','COMPLETED','TERMINATED')),('Lock',('ACTIVE',)),('Cancel / Refund',('ACTIVE','LOCKED')),('Resolve',('ACTIVE','LOCKED'))]:
   if label in self.buttons:self.buttons[label].setEnabled(live and state in statuses)
  self.details.clear()
  if row:
   for option in row.get('choices' if self.kind=='polls' else 'outcomes',[]):self.details.addTopLevelItem(QTreeWidgetItem([option['title'],str(option.get('votes' if self.kind=='polls' else 'users',0)),str(option.get('channel_points_votes' if self.kind=='polls' else 'channel_points',0)),option['id']]))
  for column in range(4):self.details.resizeColumnToContents(column)
 def refresh(self,next_page=False):self.submit('list',cursor=self.cursor if next_page else '')
 def show_rows(self,result):
  previous=self.current();identity=previous['id'] if previous else None;self.rows={r['id']:r for r in result.get('data',[])};self.cursor=result.get('pagination',{}).get('cursor','');self.table.clear()
  for row in self.rows.values():
   item=QTreeWidgetItem([row['title'],row['status'],str(row.get('duration',row.get('prediction_window',0))),row.get('started_at',row.get('created_at','')),row['id']]);item.setData(0,ROLE,row['id']);self.table.addTopLevelItem(item)
   if row['id']==identity:self.table.setCurrentItem(item)
  for col in range(5):self.table.resizeColumnToContents(col)
  self.selected();self.note.setText('Gespeicherte Vorschau; keine Twitch-Abfrage.' if result.get('preview') else 'Twitch-Daten aktualisiert.')
 def subscription_states(self,states):
  from .twitch_rewards import scopes
  granted=scopes(self.host.store.read('local.json'));manage='channel:manage:'+self.kind
  prefix='channel.poll.' if self.kind=='polls' else 'channel.prediction.'
  statuses=[kind.rsplit('.',1)[1]+': '+row['state'] for kind,row in states.items() if kind.startswith(prefix)]
  self.permissions.setText(('Verwaltungsrecht vorhanden.' if manage in granted else 'Zusätzliche Freigabe erforderlich: '+manage+'. Grant Access fordert das Gesamtpaket aller eingebauten Twitch-Funktionen an.')+(' EventSub · '+' | '.join(statuses) if statuses else ''))
 def create(self):
  if not getattr(self.host.runtime,'live',False):return
  from .desktop import FieldsDialog
  values={'title':'','options':['Yes','No'],'duration':60}
  if self.kind=='polls':values['points']=0
  dialog=FieldsDialog('Create Poll' if self.kind=='polls' else 'Create Prediction',values,self.host)
  if dialog.exec()!=QDialog.DialogCode.Accepted:return
  try:payload(self.kind,dialog.value['title'],dialog.value['options'],dialog.value['duration'],dialog.value.get('points',0))
  except ActionError as exc:QMessageBox.warning(self,'Twitch',str(exc));return
  if QMessageBox.question(self,'Start now','„'+dialog.value['title']+'“ jetzt öffentlich bei Twitch starten?')!=QMessageBox.StandardButton.Yes:return
  self.submit('create',**dialog.value)
 def change(self,status,winner=''):
  row=self.current()
  if not row:return
  text='„'+row['title']+'“: '+status+' bei Twitch ausführen?'
  if status=='RESOLVED':text+=' Die Punkte werden an das gewählte Gewinnergebnis verteilt.'
  elif status=='CANCELED':text+=' Die eingesetzten Punkte werden erstattet.'
  if QMessageBox.question(self,'Twitch',text)!=QMessageBox.StandardButton.Yes:return
  self.submit('change',id=row['id'],status=status,winner=winner)
 def resolve(self):
  row=self.current()
  if not row:return
  labels=[str(i+1)+'. '+o['title'] for i,o in enumerate(row['outcomes'])];label,ok=QInputDialog.getItem(self,'Resolve Prediction','Gewinnendes Ergebnis',labels,0,False)
  if ok:self.change('RESOLVED',row['outcomes'][labels.index(label)]['id'])
 def result(self,kind,value):
  if kind!='twitch_votes' or value.get('voteKind')!=self.kind:return
  pending=self.pending.pop(value.get('requestId'),None)
  if not pending:return
  if not value.get('success'):self.note.setText(value.get('message','Anfrage fehlgeschlagen'));return
  if pending[0]=='list':self.show_rows(value['result'])
  else:self.refresh();self.note.setText('Twitch hat die Änderung bestätigt.')
