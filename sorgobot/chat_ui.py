"""Native rich chat, source-aware send, completion, and explicit context actions."""
import html,re
from urllib.parse import urlsplit
from PySide6.QtCore import Qt,QUrl,QStringListModel
from PySide6.QtGui import QImage,QTextDocument
from PySide6.QtNetwork import QNetworkAccessManager,QNetworkRequest
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QTextBrowser,QLineEdit,QPushButton,QComboBox,QMenu,QInputDialog,QLabel,QCompleter,QApplication,QScrollArea,QWidget,QLayout

CDNS={'static-cdn.jtvnw.net','cdn.betterttv.net','cdn.frankerfacez.com','cdn.7tv.app'}
def image_url(url):
 try:parsed=urlsplit(url);return parsed.scheme=='https' and parsed.hostname in CDNS and not parsed.username and not parsed.password and parsed.port in (None,443)
 except (TypeError,ValueError):return False

def message_html(row,index,emotes):
 known={**emotes,**row.get('emotes',{})};parts=[]
 for word in re.split(r'(\s+)',row.get('message','')):
  image=known.get(word)
  parts.append('<img height="26" src="'+html.escape(image,quote=True)+'" alt="'+html.escape(word,quote=True)+'"/>' if image and image_url(image) else html.escape(word))
 return '<p><small>['+('YouTube' if row.get('platform')=='youtube' else 'Twitch')+']</small> <a style="color:#b9c9ff;text-decoration:none" href="message:'+str(index)+'">'+html.escape(row.get('user',''))+'</a>: '+''.join(parts)+'</p>'

class ChatBrowser(QTextBrowser):
 def __init__(self,parent):
  super().__init__(parent);self.network=QNetworkAccessManager(self);self.images={};self.pending=set();self.setOpenLinks(False)
 def loadResource(self,kind,url):
  key=url.toString()
  if kind!=QTextDocument.ResourceType.ImageResource or not image_url(key):return None
  if key in self.images:return self.images[key]
  if key not in self.pending and len(self.pending)<12 and len(self.images)<200:
   self.pending.add(key);request=QNetworkRequest(url);request.setTransferTimeout(8000);request.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,QNetworkRequest.RedirectPolicy.ManualRedirectPolicy);reply=self.network.get(request)
   def limit():
    if reply.bytesAvailable()>2*1024*1024:reply.abort()
   reply.readyRead.connect(limit)
   def finish():
    self.pending.discard(key)
    if reply.error()==reply.NetworkError.NoError:
     data=reply.readAll();image=QImage()
     if len(data)<=2*1024*1024 and image.loadFromData(data) and image.width()*image.height()<=4000000:
      self.images[key]=image;self.document().addResource(QTextDocument.ResourceType.ImageResource,url,image);self.viewport().update()
    reply.deleteLater()
   reply.finished.connect(finish)
  return QImage()

class ChatWindow(QDialog):
 def __init__(self,host):
  super().__init__(host);self.host=host;self.rows=[];self.emotes={};self.reply_id=None;self.pending_text=None;self.completion_prefix='';self.setWindowTitle('Chat');self.resize(760,530)
  layout=QVBoxLayout(self);self.view=ChatBrowser(self);layout.addWidget(self.view);self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu);self.view.customContextMenuRequested.connect(self.context);self.view.anchorClicked.connect(self.clicked)
  quick_area=QScrollArea();quick_area.setWidgetResizable(True);quick_area.setFixedHeight(68);quick_area.setFrameShape(quick_area.Shape.NoFrame);quick_widget=QWidget();quick_area.setWidget(quick_widget);layout.addWidget(quick_area)
  self.quick_row=QHBoxLayout(quick_widget);self.quick_row.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
  settings=QPushButton('Settings');settings.clicked.connect(self.settings);self.quick_row.addWidget(settings)
  for label,events in [('OBS Chat Dock',False),('OBS Event Dock',True)]:
   button=QPushButton(label);button.clicked.connect(lambda checked=False,e=events:self.host.runtime.submit('chat_dock_url',events=e));self.quick_row.addWidget(button)
  self.fixed_quick_buttons=self.quick_row.count()
  self.reply_label=QLabel();layout.addWidget(self.reply_label)
  row=QHBoxLayout();layout.addLayout(row);self.platform=QComboBox();self.platform.addItem('Twitch','twitch');self.platform.addItem('YouTube','youtube');self.platform.addItem('Twitch + YouTube','both');self.platform.currentIndexChanged.connect(self.target_changed);row.addWidget(self.platform);self.account=QComboBox();self.account.addItems(['Bot','Broadcaster']);row.addWidget(self.account);self.input=QLineEdit();row.addWidget(self.input,1)
  send=self.send_button=QPushButton('Send');send.clicked.connect(self.send);row.addWidget(send);self.input.returnPressed.connect(self.send)
  emoji=QPushButton('Emotes');emoji.clicked.connect(self.choose_emote);row.addWidget(emoji)
  cancel=QPushButton('Cancel Reply');cancel.clicked.connect(lambda:self.reply(None));row.addWidget(cancel)
  self.completion=QCompleter(self);self.completion.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive);self.model=QStringListModel(self);self.completion.setModel(self.model);self.input.setCompleter(self.completion)
  self.completion.activated[str].connect(self.complete);self.input.textEdited.connect(self.suggest)
  self.bound=False;self.apply_settings()
 def apply_settings(self):
  from .chat_settings import read
  self.preferences=read(self.host.store);font=self.view.font();font.setPointSize(self.preferences['fontSize']);self.view.setFont(font)
  while self.quick_row.count()>self.fixed_quick_buttons:
   item=self.quick_row.takeAt(self.fixed_quick_buttons)
   if item.widget():item.widget().deleteLater()
  for quick in self.preferences['quickActions']:
   if quick['scope']=='global':
    button=QPushButton(quick['name']);button.clicked.connect(lambda checked=False,q=quick:self.quick(q));self.quick_row.addWidget(button)
  rows=self.rows;self.rows=[];self.update_messages(rows)
 def settings(self):
  from .chat_settings_ui import ChatSettings
  if ChatSettings(self.host).exec()==QDialog.DialogCode.Accepted:self.apply_settings()
 def target_changed(self):
  self.account.setEnabled(True);self.account.setToolTip('Bot oder Broadcaster je Plattform. Ohne YouTube-Bot wird der Broadcaster verwendet.');self.reply_id=None;self.reply_label.setText('YouTube: ohne getrennten Bot als Broadcaster' if self.platform.currentData() in ('youtube','both') else '')
 def quick(self,quick,row=None):
  if row is None:row={'platform':self.platform.currentData()}
  self.host.runtime.submit('chat_quick_action',quickId=quick['id'],row=row)
 def showEvent(self,event):
  super().showEvent(event)
  if not self.bound:self.host.runtime.result.connect(self.on_result);self.bound=True
  self.host.runtime.submit('chat_emotes')
 def update_messages(self,rows):
  if rows==self.rows:return
  self.rows=rows[-self.preferences['historyLimit']:];bar=self.view.verticalScrollBar();at_end=bar.value()>=bar.maximum();old=bar.value()
  self.view.setHtml(''.join(message_html(r if self.preferences['showEmotes'] else {**r,'emotes':{}},i,self.emotes if self.preferences['showEmotes'] else {}) for i,r in enumerate(self.rows)));bar.setValue(bar.maximum() if at_end else old)
 def on_result(self,kind,value):
  if kind=='chat_dock_url':
   QApplication.clipboard().setText(value);self.reply_label.setText('Dock-Link kopiert. In OBS unter Docks → Benutzerdefinierte Browser-Docks einfügen.')
  if kind=='chat_send':
   if value.get('success'):
    if self.input.text().strip()==self.pending_text:self.input.clear();self.reply(None)
    self.reply_label.setText('Sent')
   else:
    self.reply_label.setText(value.get('error','Send failed'))
    if value.get('partial'):
     failed=[p for p,r in value.get('results',{}).items() if not r.get('success')]
     if len(failed)==1:self.platform.setCurrentIndex(self.platform.findData(failed[0]));self.reply_label.setText(value.get('error','')+' · Sendeziel auf den fehlgeschlagenen Kanal umgestellt.')
   self.pending_text=None;self.send_button.setEnabled(True)
  if kind=='chat_emotes':
   self.emotes={r['name']:r['imageUrl'] for rows in value.get('emotes',{}).values() for r in rows if isinstance(r,dict) and isinstance(r.get('imageUrl'),str) and image_url(r['imageUrl'])}
   rows=self.rows;self.rows=[];self.update_messages(rows)
 def suggest(self,text):
  self.completion_prefix=text.rsplit(' ',1)[0]+' ' if ' ' in text else ''
  token=text.rsplit(' ',1)[-1];names=[]
  if text.startswith('/action '):
   self.completion_prefix='/action ';token=text[len('/action '):];names=[a['name'] for a in getattr(self.host,'document',{}).get('actions',[]) if a.get('enabled',True) and not a.get('migrationBlock')]
  elif token.startswith(':'):names=[':'+name for name in self.emotes]
  elif token.startswith('!'):names=[name for c in self.host.store.read('commands.json')['commands'] if c.get('enabled',True) and c.get('location',0)==0 and c.get('mode',0)==0 for name in c.get('command','').splitlines() if name.startswith('!')]
  elif token.startswith('@'):names=['@'+r['login'] for r in self.rows if r.get('login')]
  elif token.startswith('/'):
   from .chat_commands import COMMANDS
   names=['/'+name for name in COMMANDS if self.platform.currentData()=='twitch' or name in ('clear','clear/overlay') or name=='action' and self.platform.currentData()=='youtube']
  self.model.setStringList(sorted(set(names)));self.completion.setCompletionPrefix(token)
  if names:self.completion.complete()
 def complete(self,word):
  self.input.setText(self.completion_prefix+(word[1:] if self.completion_prefix!='/action ' and word.startswith(':') and self.input.text().rsplit(' ',1)[-1].startswith(':') else word)+' ')
 def choose_emote(self):
  name,ok=QInputDialog.getItem(self,'Emotes','Emote:',sorted(self.emotes),0,True)
  if ok and name in self.emotes:self.input.insert(name+' ')
 def reply(self,row):
  if row:self.platform.setCurrentIndex(self.platform.findData(row.get('platform','twitch')))
  self.reply_id=row.get('id') if row else None;self.reply_label.setText('Reply to '+row.get('user','') if row else '');self.input.setFocus()
 def send(self):
  text=self.input.text().strip()
  if not text or self.pending_text is not None:return
  self.pending_text=text;self.send_button.setEnabled(False)
  self.host.runtime.submit('chat_send',platform=self.platform.currentData(),message=text,internal=True,bot=self.account.currentText()=='Bot',replyId=self.reply_id)
 def clicked(self,url):
  if url.scheme()=='message':
   try:index=int(url.path())
   except ValueError:return
   if 0<=index<len(self.rows):self.menu(self.rows[index]).exec(self.view.cursor().pos())
 def context(self,position):
  anchor=self.view.anchorAt(position)
  if anchor.startswith('message:'):
   try:row=self.rows[int(anchor.split(':',1)[1])]
   except (ValueError,IndexError):return
   self.menu(row).exec(self.view.viewport().mapToGlobal(position))
  else:self.view.createStandardContextMenu().exec(self.view.viewport().mapToGlobal(position))
 def menu(self,row):
  menu=QMenu(self);menu.addAction('Copy Message',lambda:QApplication.clipboard().setText(row.get('message','')))
  youtube=row.get('platform')=='youtube'
  if not youtube:menu.addAction('Reply',lambda:self.reply(row)).setEnabled(bool(row.get('id')))
  for name,operation in [('Delete Message','delete'),('Pin Message','pin'),('Unpin Message','unpin')]:
   if youtube and operation in ('pin','unpin'):continue
   menu.addAction(name,lambda checked=False,op=operation:self.host.runtime.submit('chat_moderate',operation=op,row=row)).setEnabled(bool(row.get('id')))
  for name,operation in [('Timeout User','timeout'),('Ban User','ban'),('Unban User','unban')]:
   if youtube and operation=='unban':continue
   menu.addAction(name,lambda checked=False,op=operation:self.moderate(op,row)).setEnabled(bool(row.get('login')))
  for scope,label in [('user','User Quick Actions'),('message','Message Quick Actions')]:
   values=[q for q in self.preferences['quickActions'] if q['scope']==scope]
   if values:
    submenu=menu.addMenu(label)
    for quick in values:submenu.addAction(quick['name'],lambda checked=False,q=quick:self.quick(q,row)).setEnabled(bool(row.get('login')))
  return menu
 def moderate(self,operation,row):
  reason,ok=QInputDialog.getText(self,operation.title(),'Reason:')
  if not ok:return
  duration=60
  if operation=='timeout':
   duration,ok=QInputDialog.getInt(self,'Timeout','Seconds:',60,1,86400 if row.get('platform')=='youtube' else 1209600)
   if not ok:return
  self.host.runtime.submit('chat_moderate',operation=operation,row=row,reason=reason,duration=duration)
