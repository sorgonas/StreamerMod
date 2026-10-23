"""Audio discovery only; executable controls belong in Sub-Actions."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QPushButton,QTreeWidget,QTreeWidgetItem,QApplication

class AudioPage(QWidget):
 def __init__(self,host):
  super().__init__(host);self.host=host;layout=QVBoxLayout(self)
  label=QLabel('Native Linux-Audioziele über PipeWire/PulseAudio. Lautstärke, Mute, Standardgerät und Routing werden unter Actions → Sub-Actions → Core → System → Linux Audio eingerichtet.\nFür einen Stream-Deck-Regler: Dial Rotate als Trigger wählen; Set Volume mit adjust und %streamDeckTicks% verwenden. Eine direkte Action-Zuweisung in OpenDeck ist ebenfalls möglich.')
  label.setWordWrap(True);layout.addWidget(label)
  self.status=QLabel('Noch nicht abgefragt.');layout.addWidget(self.status)
  self.items=QTreeWidget();self.items.setHeaderLabels(['Art','Name','Ziel-ID','Lautstärke','Mute / Standard']);layout.addWidget(self.items)
  self.refresh=QPushButton('Geräte und aktive Audiostreams aktualisieren');self.refresh.clicked.connect(lambda:self.host.runtime.submit('audio_snapshot'));layout.addWidget(self.refresh)
  copy=QPushButton('Ziel-ID der Auswahl kopieren');copy.clicked.connect(self.copy_target);layout.addWidget(copy)
 def showEvent(self,event):super().showEvent(event);self.host.runtime.submit('audio_snapshot')
 def copy_target(self):
  row=self.items.currentItem()
  if row:QApplication.clipboard().setText(row.data(0,Qt.ItemDataRole.UserRole))
 def update_status(self,value):
  self.host.audio_status=value
  self.status.setText(('Audiodienst erreichbar' if value.get('available') else 'Noch nicht verbunden / nicht erreichbar')+(' · Triggerüberwachung aktiv (2 s)' if value.get('polling') else ' · Anzeige per Aktualisieren'))
  selected=self.items.currentItem().data(0,Qt.ItemDataRole.UserRole) if self.items.currentItem() else None
  self.items.clear()
  for row in value.get('items',[]):
   item=QTreeWidgetItem([row['kind'],row['label'],row['selector'],str(row['volume'])+' %',('Stumm' if row['mute'] else 'An')+(' / Standard' if row['default'] else '')]);item.setData(0,Qt.ItemDataRole.UserRole,row['selector']);self.items.addTopLevelItem(item)
   if row['selector']==selected:self.items.setCurrentItem(item)
  for index in range(3):self.items.resizeColumnToContents(index)
