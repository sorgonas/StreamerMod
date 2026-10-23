"""Optional Linux integration: editable executable-to-category mappings."""
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QTableWidget,QTableWidgetItem,QHeaderView,QPushButton,QLineEdit,QMessageBox
from .catalog import ConfigStore

class GameDetectionPage(QWidget):
    def __init__(self,host):
        super().__init__(host);self.host=host;self.store=host.store
        document=self.store.read('games.json');layout=QVBoxLayout(self)
        hint=QLabel('Ordne ausführbare Prozessnamen einer Twitch-Kategorie zu. Linux- und Proton/Wine-Spiele werden unterstützt. Bei mehreren Treffern gilt die erste Zeile. Ohne Treffer wird die Rückfallkategorie verwendet.');hint.setWordWrap(True);layout.addWidget(hint)
        self.table=QTableWidget(0,2);self.table.setHorizontalHeaderLabels(['Process','Twitch Category']);self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch);layout.addWidget(self.table)
        for rule in document.get('games',[]):self.add_row(rule.get('process',''),rule.get('category',''))
        row=QHBoxLayout();layout.addLayout(row)
        for title,callback in [('Add',lambda:self.add_row()),('Delete',self.remove_row),('Move Up',lambda:self.move(-1)),('Move Down',lambda:self.move(1))]:
            button=QPushButton(title);button.clicked.connect(callback);row.addWidget(button)
        row.addStretch();row=QHBoxLayout();layout.addLayout(row);row.addWidget(QLabel('Fallback category'));self.fallback=QLineEdit(document.get('fallbackCategory','Just Chatting'));row.addWidget(self.fallback)
        hint=QLabel('Unteraktionen → Stream Apps → Game Detection → Detect Running Game liefert %detectedGame%, %currentGame% und %game%. Danach kannst du die vorhandenen Unteraktionen zum Setzen der Twitch-Kategorie und des Titels verwenden. Die Erkennung selbst ändert die Twitch-Kategorie nicht.');hint.setWordWrap(True);layout.addWidget(hint)
        row=QHBoxLayout();layout.addLayout(row)
        save=QPushButton('Save');save.clicked.connect(self.save);row.addWidget(save)
        test=QPushButton('Detect Now');test.clicked.connect(lambda:self.test());row.addWidget(test);row.addStretch()
        reload=QPushButton('Reload List');reload.clicked.connect(self.reload);row.addWidget(reload)
        self.result=QLabel('');self.result.setWordWrap(True);layout.addWidget(self.result)
        host.runtime.result.connect(self.runtime_result)
    def reload(self):
        document=self.store.read('games.json');self.table.setRowCount(0)
        for rule in document.get('games',[]):self.add_row(rule.get('process',''),rule.get('category',''))
        self.fallback.setText(document.get('fallbackCategory','Just Chatting'))

    def add_row(self,process='',category=''):
        row=self.table.rowCount();self.table.insertRow(row)
        self.table.setItem(row,0,QTableWidgetItem(process));self.table.setItem(row,1,QTableWidgetItem(category))
    def remove_row(self):
        if self.table.currentRow()>=0:self.table.removeRow(self.table.currentRow())
    def move(self,offset):
        row=self.table.currentRow();target=row+offset
        if row<0 or not 0<=target<self.table.rowCount():return
        for col in range(2):
            first=self.table.takeItem(row,col);second=self.table.takeItem(target,col);self.table.setItem(row,col,second);self.table.setItem(target,col,first)
        self.table.setCurrentCell(target,0)
    def save(self):
        rules=[]
        for row in range(self.table.rowCount()):
            process=self.table.item(row,0).text().strip();category=self.table.item(row,1).text().strip()
            if not process and not category:continue
            if not process or not category:QMessageBox.warning(self,'Game Detection','Bitte Prozess und Kategorie in jeder Zeile eintragen.');return False
            rules.append({'process':process,'category':category})
        self.store.save('games.json',{'games':rules,'fallbackCategory':self.fallback.text().strip() or 'Just Chatting'})
        self.result.setText('Saved');return True
    def test(self):
        self.host.runtime.submit('detect_game')
    def runtime_result(self,kind,result):
        if kind=='detect_game':self.result.setText(result['detectedGame']+' · '+('Process: '+result['detectedProcess']+' · '+result['categorySource'] if result['gameDetected'] else 'Fallback'))

        if kind=='detect_game' and result.get('candidates'):
            self.result.setText(self.result.text()+'\nLaufende Spielkandidaten: '+ '; '.join((c['title'] or 'Kategorie noch zuordnen')+' → '+c['process']+' ('+c['platform']+')' for c in result['candidates']))
