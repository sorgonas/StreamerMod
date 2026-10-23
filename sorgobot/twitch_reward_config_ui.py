from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QTreeWidget,QTreeWidgetItem,QComboBox
from .twitch_rewards import Rewards
from types import SimpleNamespace
class RewardConfiguration(QWidget):
 reward_configuration=True
 def __init__(self,value,store):
  super().__init__();layout=QVBoxLayout(self);note=QLabel('Rewards vorher unter Twitch → Channel Point Rewards aktualisieren. Not Configured behält den aktuellen Zustand; Disable Not Configured betrifft nur bearbeitbare Rewards dieser Anwendung.');note.setWordWrap(True);layout.addWidget(note)
  table=QTreeWidget();table.setHeaderLabels(['Reward','Target State','ID']);layout.addWidget(table);self.rows=[]
  cached=Rewards(SimpleNamespace(root=store.root,config=store.read('local.json'))).cache()['rewards'] if store else []
  mapping={row['rewardId']:row for row in value};present={row['id'] for row in cached}
  for identity in mapping.keys()-present:cached.append({'id':identity,'title':identity+' (missing)','manageable':False})
  for reward in cached:
   item=QTreeWidgetItem([reward['title'],'',reward['id']]);table.addTopLevelItem(item);box=QComboBox()
   for label,state in [('Not Configured',None),('Enabled',(True,False)),('Disabled',(False,False)),('Paused',(True,True)),('Disabled & Paused',(False,True))]:box.addItem(label,state)
   configured=mapping.get(reward['id'])
   if configured:
    selected=(configured.get('is_enabled',True),configured.get('is_paused',False));index=box.findData(selected);box.setCurrentIndex(max(0,index))
   table.setItemWidget(item,1,box);self.rows.append((reward['id'],box))
  for column in range(3):table.resizeColumnToContents(column)
 def value(self):
  return [{'rewardId':identity,'is_enabled':box.currentData()[0],'is_paused':box.currentData()[1]} for identity,box in self.rows if box.currentData() is not None]
