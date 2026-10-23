"""Group selection for the existing Twitch Add Random Users sub-action."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QListWidget,QListWidgetItem
from .twitch_random_groups import BUILTINS

class GroupSelection(QWidget):
 random_group_selection=True
 def __init__(self,value,store):
  super().__init__();layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
  self.list=QListWidget();self.list.setMinimumHeight(110);layout.addWidget(self.list)
  groups=[]
  if store:
   from .core_services import read_config
   groups=read_config(store.root)['userGroups']
  available=[*BUILTINS,*(r['name'] for r in groups if r['name'].casefold() not in BUILTINS)]
  selected={name.casefold():name for name in value}
  # Preserve saved names, including currently missing groups, for review/mapping.
  names=list(dict.fromkeys([*selected,*(name.casefold() for name in available)]));display={name.casefold():name for name in available}
  for key in names:
   name=selected.get(key,display.get(key,key));label=name+(' (nicht eingerichtet)' if key not in display else '')
   item=QListWidgetItem(label);item.setData(Qt.ItemDataRole.UserRole,name);item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable);item.setCheckState(Qt.CheckState.Checked if key in selected else Qt.CheckState.Unchecked);self.list.addItem(item)
  note=QLabel('Leere Auswahl: alle Kandidaten. Include From: Mitglieder aufnehmen; sonst ausschließen. Eigene Gruppen unter Core Services → User Groups. Die Vorschau nutzt zuvor gespeicherte Twitch-Rollen.');note.setWordWrap(True);layout.addWidget(note)
 def value(self):
  return [self.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list.count()) if self.list.item(i).checkState()==Qt.CheckState.Checked]
