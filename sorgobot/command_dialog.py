"""Command editor based on the supplied original Add Command screenshot."""
import copy
import re
from PySide6.QtCore import Qt,QRectF,QSize
from PySide6.QtGui import QPainter,QColor
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QGridLayout,QWidget,QLabel,QLineEdit,QPlainTextEdit,QComboBox,QTabWidget,QListWidget,QPushButton,QSpinBox,QDialogButtonBox)
from .twitch_settings import Toggle

COMMAND_STYLE='''QDialog,QWidget {background:#1d2522;font-size:14px;} QLabel {background:transparent;} QLineEdit,QPlainTextEdit,QComboBox,QListWidget,QSpinBox {background:#252f2b;border:0;border-radius:4px;padding:6px;} QComboBox::drop-down {border:0;width:25px;} QListWidget::item {min-height:24px;} QLineEdit:focus,QPlainTextEdit:focus {border-bottom:2px solid #b65bc6;} QPushButton {background:#28322e;border:0;border-radius:4px;} QTabWidget::pane {border:0;} QTabBar::tab {background:transparent;padding:8px 7px;} QTabBar::tab:selected {background:#29312e;border-radius:5px;}'''

class LeftToggle(Toggle):
    def sizeHint(self):return QSize(self.fontMetrics().horizontalAdvance(self.text())+48,25)
    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():painter.setOpacity(.45)
        painter.setPen(QColor('#eceeee'));painter.drawText(self.rect().adjusted(48,0,0,0),Qt.AlignmentFlag.AlignVCenter,self.text())
        track=QRectF(0,(self.height()-20)/2,40,20)
        painter.setPen(QColor('#b65bc6') if self.isChecked() else QColor('#a7a0ac'));painter.setBrush(QColor('#b65bc6') if self.isChecked() else QColor('#1d2522'));painter.drawRoundedRect(track,10,10)
        painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(QColor('#151419') if self.isChecked() else QColor('#c7c4ca'));painter.drawEllipse(QRectF(track.x()+(23 if self.isChecked() else 3),track.y()+3,14,14))
        if self.hasFocus():painter.setPen(QColor('#eceeee'));painter.setBrush(Qt.BrushStyle.NoBrush);painter.drawRoundedRect(track.adjusted(-2,-2,2,2),11,11)

class CommandDialog(QDialog):
    def __init__(self,command,host,new=False):
        super().__init__(host);self.value=copy.deepcopy(command);self.setWindowTitle('Add Command' if new else 'Edit Command');self.resize(840,525);self.setMinimumSize(760,490);self.setStyleSheet(COMMAND_STYLE)
        outer=QVBoxLayout(self);outer.setContentsMargins(12,8,12,12);row=QHBoxLayout();row.setSpacing(10);outer.addLayout(row,1)
        left=QWidget();left.setFixedWidth(325);grid=QGridLayout(left);grid.setContentsMargins(0,0,0,0);grid.setSpacing(7);grid.setColumnStretch(1,1);row.addWidget(left,0,Qt.AlignmentFlag.AlignTop)
        header=QWidget();header_grid=QGridLayout(header);header_grid.setContentsMargins(0,0,0,0);header_grid.setSpacing(7);grid.addWidget(header,0,0,2,3)
        self.name=QLineEdit(command.get('name',''));header_grid.addWidget(QLabel('Name'),0,0);header_grid.addWidget(self.name,0,1)
        self.enabled=self.toggle('Enabled',command.get('enabled',True));header_grid.addWidget(self.enabled,0,2)
        self.mode=QComboBox();self.mode.addItem('Normal',0);self.mode.addItem('Regex',1);self.mode.setCurrentIndex(self.mode.findData(command.get('mode',0)));header_grid.addWidget(QLabel('Mode'),1,0);header_grid.addWidget(self.mode,1,1)
        self.include=self.toggle('Include',command.get('include',False));header_grid.addWidget(self.include,1,2)
        grid.addWidget(QLabel('Command(s)'),2,0,1,2);grid.addWidget(QLabel('Location'),2,2)
        self.command=QPlainTextEdit(command.get('command',''));self.command.setFixedHeight(76);grid.addWidget(self.command,3,0,2,2)
        self.location=QComboBox()
        for name,kind in [('Start',0),('Exact',1),('Anywhere',2)]:self.location.addItem(name,kind)
        self.location.setCurrentIndex(self.location.findData(command.get('location',0)));grid.addWidget(self.location,3,2)
        hint=QLabel('Put each command\nprefix on its own\nline');grid.addWidget(hint,4,2)
        self.group=QComboBox();self.group.setEditable(True);self.group.addItem('');self.group.addItems(sorted({c.get('group','') for c in host.store.read('commands.json')['commands'] if c.get('group')}));self.group.setCurrentText(command.get('group',''));grid.addWidget(QLabel('Group'),5,0);grid.addWidget(self.group,5,1,1,2)
        tabs=QTabWidget();grid.addWidget(tabs,6,0,1,3)
        options=QWidget();option_layout=QVBoxLayout(options);option_layout.setContentsMargins(3,3,0,0);option_layout.setSpacing(0);self.options={}
        for key,label,default in [('ignoreBotAccount','Ignore Bot Account',True),('ignoreInternalMessages','Ignore Internal Messages',True),('persistUserCounter','Persist per User Counter',False),('persistCounter','Persist Counter',False),('caseSensitive','Case Sensitive',False)]:
            toggle=self.toggle(label,command.get(key,default));self.options[key]=toggle;option_layout.addWidget(toggle)
        option_layout.addStretch();tabs.addTab(options,'Options')
        cooldowns=QWidget();cool_layout=QGridLayout(cooldowns);self.cooldowns={}
        for i,(key,label) in enumerate([('globalCooldown','Global Cooldown'),('userCooldown','User Cooldown')]):
            spin=QSpinBox();spin.setRange(0,2147483647);spin.setValue(int(command.get(key,0)));spin.setSuffix(' s');self.cooldowns[key]=spin;cool_layout.addWidget(QLabel(label),i,0);cool_layout.addWidget(spin,i,1)
        cool_layout.setRowStretch(2,1);tabs.addTab(cooldowns,'Cooldowns')
        sources=QWidget();source_layout=QVBoxLayout(sources);source_layout.setContentsMargins(3,3,0,0);self.sources={}
        for key,label in [('twitch_message','Twitch Message'),('youtube_message','YouTube Message'),('twitch_whisper','Twitch Whisper'),('twitch_bot_whisper','Twitch Bot Whisper'),('twitch_shared_chat','Twitch Shared Chat'),('twitch_subscription','Twitch Subscription Message'),('twitch_resubscription','Twitch Re-subscription Message')]:
            from .command_state import SOURCES
            values=command.get('sources',{});checked=values.get(key,values.get('twitch_message',True) if key=='twitch_shared_chat' else key=='twitch_message') if isinstance(values,dict) else type(values) is int and bool(values&SOURCES[key][1])
            toggle=self.toggle(label,checked);self.sources[key]=toggle

            source_layout.addWidget(toggle)
        source_layout.addStretch();tabs.addTab(sources,'Sources')
        self.mode.currentIndexChanged.connect(lambda:self.location.setEnabled(self.mode.currentData()==0));self.location.setEnabled(self.mode.currentData()==0)
        right=QVBoxLayout();row.addLayout(right,1);right.addWidget(QLabel('<b>Permissions</b>'))
        grant=QHBoxLayout();grant.addWidget(QLabel('Grant Type'));self.grant=QComboBox();self.grant.addItem('Allow (all, or only those)','allow');self.grant.addItem('Deny (all, or only those)','deny');self.grant.setCurrentIndex(1 if command.get('permissionMode','allow')=='deny' else 0);grant.addWidget(self.grant,1);right.addLayout(grant)
        permission_tabs=QTabWidget();right.addWidget(permission_tabs,1)
        self.available=QListWidget();self.groups=QListWidget();self.users=QListWidget()
        mapping={'Moderators':'Moderators','Subscribers':'Subscribers','VIPs':'VIPs','Ignore Me':'IgnoreMe','Streamer':'Broadcaster'}
        for label,role in mapping.items():
            item_list=self.groups if role in command.get('permittedGroups',[]) else self.available;item_list.addItem(label);item_list.item(item_list.count()-1).setData(Qt.ItemDataRole.UserRole,role)
        for role in command.get('permittedGroups',[]):
            if role not in mapping.values():self.groups.addItem(role);self.groups.item(self.groups.count()-1).setData(Qt.ItemDataRole.UserRole,role)
        group_page=QWidget();group_layout=QGridLayout(group_page);group_layout.setContentsMargins(4,0,0,0);group_layout.addWidget(QLabel('<b>Available</b>'),0,0,alignment=Qt.AlignmentFlag.AlignHCenter);self.allowed_label=QLabel('<b>Allowed</b>');group_layout.addWidget(self.allowed_label,0,2,alignment=Qt.AlignmentFlag.AlignHCenter);group_layout.addWidget(self.available,1,0);group_layout.addWidget(self.groups,1,2)
        arrows=QVBoxLayout();arrows.addStretch()
        for label,source,destination in [('>>',self.available,self.groups),('<<',self.groups,self.available)]:
            button=QPushButton(label);button.setFixedWidth(42);button.clicked.connect(lambda checked=False,s=source,d=destination:self.transfer(s,d));arrows.addWidget(button)
        arrows.addStretch();group_layout.addLayout(arrows,1,1);permission_tabs.addTab(group_page,'Group Permissions')
        user_page=QWidget();user_layout=QVBoxLayout(user_page);self.users.addItems([str(u) for u in command.get('permittedUsers',[])]);user_layout.addWidget(self.users);user_row=QHBoxLayout();self.user_input=QLineEdit();self.user_input.setPlaceholderText('Twitch login / youtube:Kanal-ID');user_row.addWidget(self.user_input);add=QPushButton('Add');remove=QPushButton('Remove');user_row.addWidget(add);user_row.addWidget(remove);user_layout.addLayout(user_row);add.clicked.connect(self.add_user);remove.clicked.connect(lambda:self.users.takeItem(self.users.currentRow()));permission_tabs.addTab(user_page,'User Permissions')
        self.grant.currentIndexChanged.connect(lambda:self.allowed_label.setText('<b>Denied</b>' if self.grant.currentData()=='deny' else '<b>Allowed</b>'));self.grant.currentIndexChanged.emit(self.grant.currentIndex())
        self.error=QLabel('');self.error.setStyleSheet('color:#ee9999');outer.addWidget(self.error)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        for role in (QDialogButtonBox.StandardButton.Ok,QDialogButtonBox.StandardButton.Cancel):buttons.button(role).setFixedSize(65,32)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Ok');buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);outer.addWidget(buttons)
        self.name.setFocus()
    def toggle(self,label,checked):
        toggle=LeftToggle(label);toggle.setChecked(checked);return toggle
    def transfer(self,source,destination):
        if source.currentRow()>=0:destination.addItem(source.takeItem(source.currentRow()))
    def add_user(self):
        text=self.user_input.text().strip().lstrip('@')
        key=lambda value:value if value.startswith('youtube:') else value.casefold()
        if text and key(text) not in [key(self.users.item(i).text()) for i in range(self.users.count())]:self.users.addItem(text)
        self.user_input.clear()
    def accept(self):
        name=self.name.text().strip();command=self.command.toPlainText().strip()
        if not name or not command:self.error.setText('Name and Command(s) are required.');return
        if self.mode.currentData()==1:
            try:re.compile(command.replace('(?i)',''),0 if self.options['caseSensitive'].isChecked() else re.I)
            except re.error as error:self.error.setText('Invalid Regex: '+str(error));return
        self.value.update(name=name,command=command,enabled=self.enabled.isChecked(),include=self.include.isChecked(),mode=self.mode.currentData(),location=self.location.currentData(),group=self.group.currentText().strip(),permissionMode=self.grant.currentData(),permittedGroups=[self.groups.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.groups.count())],permittedUsers=[self.users.item(i).text() for i in range(self.users.count())],sources={key:toggle.isChecked() for key,toggle in self.sources.items()})
        self.value.update({key:toggle.isChecked() for key,toggle in self.options.items()});self.value.update({key:spin.value() for key,spin in self.cooldowns.items()});super().accept()
