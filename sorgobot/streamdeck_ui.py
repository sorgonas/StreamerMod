"""Connect to external OpenDeck without owning its process or installing it."""
from pathlib import Path
from PySide6.QtCore import QProcess,QTimer,QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QTreeWidget,QTreeWidgetItem
from .streamdeck_support import usb_devices,executable,install_plugin

class StreamDeckPage(QWidget):
 def __init__(self,host):
  super().__init__(host);self.host=host;self.project=Path(__file__).resolve().parents[1];self.process=None;self.install_process=None
  layout=QVBoxLayout(self);self.status=QLabel();layout.addWidget(self.status)
  hint=QLabel('OpenDeck separat installieren und starten. StreamerMod verbindet sich automatisch über das eigene Plugin. OpenDeck läuft beim Beenden von StreamerMod weiter. Geräte und Profile werden in OpenDeck verwaltet.');hint.setWordWrap(True);layout.addWidget(hint)
  self.devices=QTreeWidget();self.devices.setHeaderLabels(['Device','USB ID','USB Port','Access']);self.devices.setMaximumHeight(140);layout.addWidget(self.devices)
  row=QHBoxLayout();layout.addLayout(row)
  for title,callback in [('Aktualisieren',self.refresh),('StreamerMod-Plugin einrichten / aktualisieren',self.setup_plugin),('OpenDeck Website',lambda:QDesktopServices.openUrl(QUrl('https://github.com/nekename/OpenDeck')))]:
   button=QPushButton(title);button.clicked.connect(callback);row.addWidget(button)
  self.edit_button=QPushButton('Stream-Deck-Tasten bearbeiten\nOpenDeck öffnen');self.edit_button.setObjectName('openDeckEditor');self.edit_button.setMinimumHeight(90);self.edit_button.setStyleSheet('QPushButton {background:#783d85;color:white;font-size:19px;font-weight:600;padding:16px;border-radius:6px;}');self.edit_button.clicked.connect(self.launch);layout.addWidget(self.edit_button)
  self.message=QLabel();self.message.setWordWrap(True);layout.addWidget(self.message)
  self.bridge_status=QLabel('Plugin-Verbindung wird geprüft…');self.bridge_status.setWordWrap(True);layout.addWidget(self.bridge_status)
  info=QLabel('In OpenDeck → StreamerMod einen Action Button, Action Switch, Status Indicator oder Action Dial hinzufügen. Actions → StreamerMod → Decks steuert diese Belegungen. Seiten entsprechen OpenDeck-Profilen. Items müssen sichtbar sein.');info.setWordWrap(True);layout.addWidget(info);layout.addStretch()
  self.device_timer=QTimer(self);self.device_timer.setInterval(3000);self.device_timer.timeout.connect(self.refresh_devices);self.device_timer.start();self.refresh()
 def setup_plugin(self):
  try:install_plugin(self.project);self.message.setText('StreamerMod-Plugin aktualisiert. OpenDeck einmal neu starten. Vorhandene Profile und Belegungen bleiben erhalten.')
  except OSError:self.message.setText('Plugin konnte nicht im eigenen OpenDeck-Konfigurationsordner eingerichtet werden.')
 def update_bridge(self,value):
  state={'listening':'Aktiv','disabled':'Vorschau','unavailable':'Nicht verfügbar (Port 8059 prüfen)'}.get(value.get('state'),'Wird geprüft')
  self.bridge_status.setText(f"StreamerMod-Verbindung: {state} · {value.get('clients',0)} Plugin-Verbindung(en), {value.get('buttons',0)} sichtbare Belegung(en).")
 def refresh_devices(self):
  self.devices.clear()
  for row in usb_devices():self.devices.addTopLevelItem(QTreeWidgetItem([row['name'],row['usbId'],row['location'],'Ready' if row['accessible'] else 'USB-Zugriff / Regeln prüfen']))
 def refresh(self):
  self.refresh_devices();self.status.setText('OpenDeck separat installiert.' if executable() else 'OpenDeck separat installieren; Download und USB-Einrichtung siehe OpenDeck Website.')
 def launch(self):
  binary=executable()
  if not binary:self.message.setText('OpenDeck bitte separat installieren (OpenDeck Website).');return
  started,_=QProcess.startDetached(binary,[]);self.message.setText('OpenDeck im eigenen Fenster geöffnet.' if started else 'OpenDeck konnte nicht geöffnet werden.')
 def shutdown(self):pass # External OpenDeck always stays running.
