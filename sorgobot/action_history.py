"""Action history and pending lists follow the original columns and inspection flow."""
import json
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QTreeWidget,QTreeWidgetItem,QLineEdit,QDialog,QMenu,QPlainTextEdit,QLabel
from .editor_menus import bind
ROLE=Qt.ItemDataRole.UserRole

class HistoryPage(QWidget):
    HEADERS=['Name','State','Variables','Duration','Queue','Queued At','Started At','Completed At','Details']
    def __init__(self,host,pending=False):
        super().__init__();self.host=host;self.pending=pending;self.records=[]
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        self.filter=QLineEdit();self.filter.setPlaceholderText('Filter actions…');layout.addWidget(self.filter)
        self.summary=QLabel();self.summary.setWordWrap(True);self.summary.setTextFormat(Qt.TextFormat.PlainText);layout.addWidget(self.summary)
        self.tree=QTreeWidget();self.tree.setHeaderLabels(self.HEADERS);self.tree.setRootIsDecorated(False);layout.addWidget(self.tree)
        self.tree.itemSelectionChanged.connect(self.update_summary)
        self.filter.textChanged.connect(self.populate);bind(self.tree,self.menu);self.tree.itemDoubleClicked.connect(lambda *_:self.inspect(False))

    def update_records(self,records):
        self.records=records;self.populate()

    def populate(self):
        item=self.tree.currentItem();selected=item.data(0,ROLE) if item else None;scroll=self.tree.verticalScrollBar().value()
        self.tree.clear();term=self.filter.text().casefold()
        for record in reversed(self.records):
            if term and term not in (record['name']+' '+record.get('queue','')).casefold():continue
            state={'ok':'Completed','error':'Failed','stopped':'Stopped','cancelled':'Cancelled'}.get(record.get('status'),'Pending' if self.pending else 'Unknown')
            variables=record.get('argumentsAfter') or record.get('argumentsQueued',{})
            row=QTreeWidgetItem([record['name'],state,str(len(variables)),str(record.get('duration',0))+' ms',record.get('queue','Default'),record.get('queuedAt',''),record.get('startedAt',''),record.get('completedAt','')])
            row.setData(0,ROLE,record.get('id'));row.setToolTip(0,record.get('error',''));self.tree.addTopLevelItem(row)
            step=record.get('failedStep',{});detail=(str(step.get('name',''))+': ' if step else '')+record.get('error','');row.setText(8,detail);row.setToolTip(8,detail)
            if record.get('id')==selected:self.tree.setCurrentItem(row)
        self.tree.setColumnWidth(0,210)
        for i in range(1,8):self.tree.resizeColumnToContents(i)
        self.tree.verticalScrollBar().setValue(scroll)

    def current(self):
        item=self.tree.currentItem();return next((r for r in self.records if item and r.get('id')==item.data(0,ROLE)),None)

    def update_summary(self):
        record=self.current() or {};step=record.get('failedStep',{})
        self.summary.setText((str(step.get('name',''))+': ' if step else '')+record.get('error',''))

    def inspect(self,queued):
        record=self.current()
        if not record:return
        dialog=QDialog(self);dialog.setWindowTitle('Inspect Variables When Queued' if queued else 'Inspect Variables After Run');dialog.resize(760,500);layout=QVBoxLayout(dialog)
        tree=QTreeWidget();tree.setHeaderLabels(['Name','Type','Value']);layout.addWidget(tree)
        for key,value in record.get('argumentsQueued' if queued else 'argumentsAfter',{}).items():tree.addTopLevelItem(QTreeWidgetItem([key,type(value).__name__,json.dumps(value,ensure_ascii=False,default=str)]))
        tree.resizeColumnToContents(0);dialog.exec()

    def menu(self):
        menu=QMenu(self);record=self.current()
        menu.addAction('Inspect Variables When Queued',lambda:self.inspect(True)).setEnabled(record is not None)
        if not self.pending:
            menu.addAction('Show Error / Details',self.show_error).setEnabled(bool(record and (record.get('error') or record.get('failedStep'))))
            menu.addAction('Inspect Variables After Run',lambda:self.inspect(False)).setEnabled(record is not None)
            menu.addAction('Requeue',lambda:self.host.runtime.submit('requeue',id=record['actionId'],arguments=record.get('argumentsQueued',{}))).setEnabled(record is not None)
            menu.addSeparator();menu.addAction('Clear History',lambda:self.host.runtime.submit('clear_history'))
        return menu

    def show_error(self):
        record=self.current()
        if not record:return
        step=record.get('failedStep',{});dialog=QDialog(self);dialog.setWindowTitle('Action Details');dialog.resize(700,340);layout=QVBoxLayout(dialog);text=QPlainTextEdit();text.setReadOnly(True);layout.addWidget(text)
        text.setPlainText('\n'.join([record.get('name',''),'Status: '+record.get('status',''),'Unteraktion: '+str(step.get('name','—')),'Typ: '+str(step.get('type','—')),'Zeit: '+record.get('completedAt',record.get('time','')),'',record.get('error','Keine Fehlermeldung.')]));dialog.exec()
