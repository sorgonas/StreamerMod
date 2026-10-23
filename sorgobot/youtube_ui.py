"""YouTube platform accounts and broadcast selection; Actions stay in their editors."""
import json
from pathlib import Path
from PySide6.QtCore import QTimer,QUrl,Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QComboBox,QCheckBox,QFileDialog,QGroupBox
class YouTubePage(QWidget):
 def __init__(self,host):
  super().__init__(host);self.host=host;self.polling=False;self.busy=False;self.last_broadcasts=None;self.settings_loaded=False;self.login_role='broadcaster'
  layout=QVBoxLayout(self);self.account=QLabel('YouTube wird geprüft…');self.account.setWordWrap(True);self.account.setTextFormat(Qt.TextFormat.PlainText);layout.addWidget(self.account)
  row=QHBoxLayout();layout.addLayout(row)
  self.login_button=QPushButton('Login');self.login_button.clicked.connect(self.login);row.addWidget(self.login_button)
  self.forget_button=QPushButton('Forget');self.forget_button.clicked.connect(lambda:host.runtime.submit('youtube_forget'));row.addWidget(self.forget_button)
  setup=QPushButton('Google-Desktop-Client importieren…');setup.clicked.connect(self.setup);row.addWidget(setup)
  self.bot_account=QLabel('YouTube-Bot: nicht angemeldet');self.bot_account.setTextFormat(Qt.TextFormat.PlainText);layout.addWidget(self.bot_account)
  bot_row=QHBoxLayout();layout.addLayout(bot_row)
  self.bot_login=QPushButton('Bot Login');self.bot_login.clicked.connect(lambda:self.login('bot'));bot_row.addWidget(self.bot_login)
  self.bot_forget=QPushButton('Bot abmelden');self.bot_forget.clicked.connect(lambda:host.runtime.submit('youtube_bot_forget'));bot_row.addWidget(self.bot_forget)
  self.state=QLabel('');self.state.setWordWrap(True);layout.addWidget(self.state)
  row=QHBoxLayout();layout.addLayout(row);row.addWidget(QLabel('Broadcast:'));self.broadcast=QComboBox();row.addWidget(self.broadcast,1)
  self.refresh_button=QPushButton('Aktualisieren');self.refresh_button.clicked.connect(lambda:host.runtime.submit('youtube_broadcasts'));row.addWidget(self.refresh_button)
  self.auto=QCheckBox('YouTube beim Programmstart automatisch verbinden');self.auto.setChecked(False);layout.addWidget(self.auto)
  row=QHBoxLayout();layout.addLayout(row)
  self.save_button=QPushButton('Auswahl speichern');self.save_button.clicked.connect(lambda:host.runtime.submit('youtube_configure',broadcast=self.broadcast.currentData() or '',auto=self.auto.isChecked()));row.addWidget(self.save_button)
  self.connect_button=QPushButton('Verbinden');self.connect_button.clicked.connect(lambda:host.runtime.submit('youtube_connect'));row.addWidget(self.connect_button)
  self.disconnect_button=QPushButton('Trennen');self.disconnect_button.clicked.connect(lambda:host.runtime.submit('youtube_disconnect'));row.addWidget(self.disconnect_button)
  note=QLabel('YouTube ist optional. Ein eigener Bot-Kanal ist nicht erforderlich: Ohne Bot können Nachrichten als Broadcaster gesendet werden. Twitch und YouTube können gleichzeitig verbunden sein. Im Chat ist das Sendeziel einzeln oder gemeinsam wählbar. Commands können beide Nachrichtenquellen verwenden. Bei mehreren aktiven YouTube-Broadcasts bitte einen auswählen. YouTube zeigt hier beobachtete Chatteilnehmer; eine vollständige Liste stiller Zuschauer ist nicht verfügbar.');note.setWordWrap(True);layout.addWidget(note)
  help_box=QGroupBox('Einmalige Google-Einrichtung');help_layout=QVBoxLayout(help_box)
  help_text=QLabel('<ol><li>In der <a style="color:#8ab4f8" href="https://console.cloud.google.com/">Google Cloud Console</a> ein Projekt für StreamerMod anlegen.</li><li><a style="color:#8ab4f8" href="https://console.cloud.google.com/apis/library/youtube.googleapis.com">YouTube Data API v3</a> aktivieren.</li><li>Unter Google Auth Platform App-Name und Zielgruppe einrichten. Im Testmodus das eigene Google-Konto als Testnutzer hinzufügen.</li><li>Unter Clients einen OAuth-Client vom Typ <b>Desktop-App</b> erstellen und dessen JSON herunterladen.</li><li>Die Datei oben importieren, dann mit Login den gewünschten YouTube-Kanal im Browser auswählen und die gemeinsame Chatfreigabe bestätigen.</li></ol>Für einen getrennten Bot anschließend „Bot Login“ wählen und dessen eigenen YouTube-Kanal auswählen. Falls er ein anderes Google-Konto verwendet, dieses im Testmodus ebenfalls als Testnutzer zulassen. Das Programm legt kein Google-Konto an. Die Anmeldung erfolgt im normalen Browser. Das Passwort wird nicht in StreamerMod eingegeben. Bei Google-Projekten im Testmodus kann die dauerhafte Freigabe zeitlich begrenzt sein.');help_text.setWordWrap(True);help_text.setOpenExternalLinks(True);help_layout.addWidget(help_text);layout.addWidget(help_box);layout.addStretch()
  self.timer=QTimer(self);self.timer.setInterval(1500);self.timer.timeout.connect(self.poll)
  host.runtime.result.connect(self.on_result)
 def setup(self):
  path,_=QFileDialog.getOpenFileName(self,'Google-Desktop-Client importieren','','JSON (*.json)')
  if not path:return
  try:
   if Path(path).stat().st_size>65536:raise ValueError('Datei ist zu groß')
   value=json.loads(Path(path).read_text(encoding='utf-8-sig'))
  except (ValueError,OSError) as exc:self.state.setText('Client-Datei konnte nicht gelesen werden: '+str(exc));return
  self.host.runtime.submit('youtube_setup',value=value)
 def login(self,role='broadcaster'):
  if not getattr(self.host.runtime,'booted',True):return
  if type(role) is bool:role='broadcaster'
  if self.timer.isActive():self.host.runtime.submit('youtube_bot_login_cancel' if self.login_role=='bot' else 'youtube_login_cancel');return
  self.login_role=role
  self.busy=True;self.login_button.setEnabled(False);self.host.runtime.submit('youtube_bot_login' if role=='bot' else 'youtube_login')
 def poll(self):
  if self.polling:return
  self.polling=True;self.host.runtime.submit('youtube_bot_login_poll' if self.login_role=='bot' else 'youtube_login_poll')
 def update_status(self,value):
  if not value:return
  if not self.settings_loaded:self.auto.setChecked(value.get('autoConnect',False));self.settings_loaded=True
  account=value.get('account',{});title=account.get('channelTitle') or account.get('channelId')
  bot=value.get('botAccount',{});bot_title=bot.get('channelTitle') or bot.get('channelId')
  self.bot_account.setText('YouTube-Bot: '+bot_title if bot_title else 'YouTube-Bot: nicht angemeldet (optional)');self.bot_forget.setEnabled(bool(bot_title));self.bot_login.setEnabled(not self.busy)
  self.account.setText('YouTube-Kanal: '+title if title else 'YouTube: noch nicht angemeldet')
  self.login_button.setEnabled(not self.busy);self.forget_button.setEnabled(bool(title));self.connect_button.setEnabled(bool(title));self.refresh_button.setEnabled(bool(title));self.save_button.setEnabled(bool(title));self.disconnect_button.setEnabled(value.get('state') !='disconnected')
  if not self.timer.isActive():
   labels={'disconnected':'Getrennt','connecting':'Verbindung wird aufgebaut','connected':'Livechat verbunden','waiting':'Angemeldet; warte auf einen aktiven Broadcast','select_broadcast':'Mehrere aktive Broadcasts – bitte einen auswählen','reconnecting':'Chatverbindung wird wiederhergestellt','quota_exceeded':'YouTube-API-Kontingent erschöpft; automatischer späterer Versuch','error':'YouTube-Verbindung fehlgeschlagen'}
   self.state.setText(labels.get(value.get('state'),'')+(' · '+value['error'] if value.get('error') else ''))
  rows=value.get('broadcasts',[])
  if rows!=self.last_broadcasts:
   selected=self.broadcast.currentData() if self.last_broadcasts is not None else value.get('selectedBroadcast','');self.last_broadcasts=rows;self.broadcast.clear();self.broadcast.addItem('Automatisch: genau ein aktiver Broadcast','')
   for row in rows:self.broadcast.addItem(row.get('snippet',{}).get('title',row['id'])+' · '+row.get('status',{}).get('lifeCycleStatus',''),row['id'])
   index=self.broadcast.findData(selected)
   if selected and index<0:self.broadcast.addItem('Gespeicherter Broadcast: '+selected,selected);index=self.broadcast.count()-1
   self.broadcast.setCurrentIndex(max(0,index))
 def on_result(self,kind,value):
  if not kind.startswith('youtube_'):return
  self.polling=False;self.busy=False;self.login_button.setEnabled(True)
  if value.get('state')=='error' and 'message' in value:self.state.setText(value['message']);self.timer.stop();self.login_button.setText('Login');return
  if kind in ('youtube_login','youtube_login_poll','youtube_bot_login','youtube_bot_login_poll') and value.get('state')=='pending':
   self.timer.start();self.login_button.setText('Login abbrechen');self.state.setText('Google-Anmeldung im Browser bestätigen.')
   if value.get('url'):QDesktopServices.openUrl(QUrl(value['url']))
   return
  if kind.startswith(('youtube_login','youtube_bot_login')):self.timer.stop();self.login_button.setText('Login')
  self.host.runtime.submit('youtube_status') if kind!='youtube_status' else self.update_status(value)
