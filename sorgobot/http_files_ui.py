from pathlib import Path
import uuid
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QTreeWidget,QTreeWidgetItem,QPushButton,QFileDialog,QInputDialog,QMessageBox
from .http_files import mappings,validate
from .core import ActionError

class HttpFiles(QWidget):
 def __init__(self,host):
  super().__init__(host);self.host=host;layout=QVBoxLayout(self);self.table=QTreeWidget();self.table.setHeaderLabels(['URL Path','File / Directory','Enabled']);layout.addWidget(self.table)
  buttons=QHBoxLayout();layout.addLayout(buttons)
  for text,callback in [('Add File',lambda:self.add(False)),('Add Directory',lambda:self.add(True)),('Rename URL',self.rename),('Enable / Disable',self.toggle),('Delete',self.delete)]:
   b=QPushButton(text);b.clicked.connect(callback);buttons.addWidget(b)
  self.refresh()
 def refresh(self):
  self.rows=mappings(self.host.root);self.table.clear()
  for row in self.rows:self.table.addTopLevelItem(QTreeWidgetItem([row['route'],row['path'],'Yes' if row['enabled'] else 'No']))
 def selected(self):return self.table.indexOfTopLevelItem(self.table.currentItem()) if self.table.currentItem() else -1
 def save(self):
  try:validate(self.rows);self.host.store.save('http-files.json',self.rows);self.refresh()
  except (ActionError,OSError) as exc:QMessageBox.warning(self,'HTTP Files',str(exc));self.refresh()
 def add(self,directory):
  path=QFileDialog.getExistingDirectory(self,'Directory') if directory else QFileDialog.getOpenFileName(self,'File')[0]
  if not path:return
  route,ok=QInputDialog.getText(self,'URL Path','URL Path:',text='/overlay')
  if ok:self.rows.append({'id':str(uuid.uuid4()),'route':route.rstrip('/'),'path':str(Path(path).resolve()),'directory':directory,'enabled':True});self.save()
 def rename(self):
  index=self.selected()
  if index<0:return
  route,ok=QInputDialog.getText(self,'URL Path','URL Path:',text=self.rows[index]['route'])
  if ok:self.rows[index]['route']=route.rstrip('/');self.save()
 def toggle(self):
  index=self.selected()
  if index>=0:self.rows[index]['enabled']=not self.rows[index]['enabled'];self.save()
 def delete(self):
  index=self.selected()
  if index>=0:self.rows.pop(index);self.save()
