"""Native user inventory; registration never awards points or opens a connection."""
from datetime import datetime
from zoneinfo import ZoneInfo
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QTreeWidget,QTreeWidgetItem,QPushButton,QComboBox,QInputDialog

class UsersPage(QWidget):
    def __init__(self,host):
        super().__init__(host);self.host=host
        layout=QVBoxLayout(self)
        hint=QLabel('Gespeicherte Nutzer sind nach Plattform und Login getrennt. Chat und Anwesenheit ergänzen die Liste automatisch. Register User fügt einen Nutzer ohne Chataktivität oder Punkte hinzu. Aktiv bedeutet: aktuell anwesend oder innerhalb der letzten fünf Minuten im Chat aktiv.');hint.setWordWrap(True);layout.addWidget(hint)
        row=QHBoxLayout();layout.addLayout(row);self.platform=QComboBox()
        for label,value in [('All',''),('Twitch','twitch'),('YouTube','youtube')]:self.platform.addItem(label,value)
        row.addWidget(self.platform);self.platform.currentIndexChanged.connect(self.refresh)
        for label,callback in [('Refresh',self.refresh),('Register User',self.register)]:
            button=QPushButton(label);button.clicked.connect(callback);row.addWidget(button)
        row.addStretch();self.count=QLabel('');row.addWidget(self.count)
        self.table=QTreeWidget();self.table.setHeaderLabels(['Platform','Login','Display Name','User ID','Last Seen','Last Chat Activity','Active','Present']);layout.addWidget(self.table)
        host.runtime.result.connect(self.result)
        self.timer=QTimer(self);self.timer.setInterval(10000);self.timer.timeout.connect(lambda:self.refresh() if self.isVisible() else None);self.timer.start()
    def showEvent(self,event):super().showEvent(event);self.refresh()
    def refresh(self,*_):self.host.runtime.submit('known_users',platform=self.platform.currentData())
    def register(self):
        platform,ok=QInputDialog.getItem(self,'Register User','Platform',['twitch','youtube'],0,False)
        if not ok:return
        user,ok=QInputDialog.getText(self,'Register User','Login')
        if ok and user.strip():self.host.runtime.submit('user_register',platform=platform,user=user.strip())
    def result(self,kind,result):
        if kind=='user_register':self.refresh()
        if kind!='known_users':return
        self.table.clear();zone=ZoneInfo(self.host.store.read('local.json').get('timezone','Europe/Berlin'))
        def date(value):return datetime.fromtimestamp(value,zone).strftime('%d.%m.%Y %H:%M:%S') if value else '—'
        for user in result['users']:
            self.table.addTopLevelItem(QTreeWidgetItem([user['platform'],user['userName'],user['displayName'],user['userId'],date(user['lastSeen']),date(user['lastActive']),'Yes' if user['active'] else 'No','Yes' if user['present'] else 'No']))
        self.count.setText(f"{len(result['users'])} / {result['total']}")
        for column in range(8):self.table.resizeColumnToContents(column)
