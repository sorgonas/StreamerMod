"""Command Triggered criteria: Any, saved commands, and inline command creation."""
import copy
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QComboBox,QPushButton,QLabel,QDialogButtonBox
from .command_dialog import COMMAND_STYLE

class CommandTriggerDialog(QDialog):
    def __init__(self,trigger,host,new=True):
        super().__init__(host);self.host=host;self.value=copy.deepcopy(trigger)
        title='Command Cooldown' if trigger['type']==402 else 'Command Triggered'
        self.setWindowTitle(('Add' if new else 'Edit')+' Trigger - Core > Commands > '+title);self.setFixedSize(596,104);self.setStyleSheet(COMMAND_STYLE)
        layout=QVBoxLayout(self);layout.setContentsMargins(15,9,15,12);layout.setSpacing(9)
        row=QHBoxLayout();row.addWidget(QLabel('Command'));self.commands=QComboBox();self.commands.setMinimumHeight(36);row.addWidget(self.commands,1);layout.addLayout(row)
        footer=QHBoxLayout();self.create_button=QPushButton('Create Command');self.create_button.setMinimumHeight(32);self.create_button.clicked.connect(self.create_command);footer.addWidget(self.create_button);footer.addStretch();layout.addLayout(footer)
        self.populate(trigger.get('commandId',''))
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        for role in (QDialogButtonBox.StandardButton.Ok,QDialogButtonBox.StandardButton.Cancel):buttons.button(role).setFixedSize(95,32)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Ok');buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);footer.addWidget(buttons)

    def populate(self,identity=''):
        self.commands.clear();self.commands.addItem('Any','')
        for command in self.host.store.read('commands.json')['commands']:
            self.commands.addItem(command['name'],command['id'])
        index=self.commands.findData(identity or '')
        if index<0:
            self.commands.addItem('Missing command ('+identity+')',identity);index=self.commands.count()-1
        self.commands.setCurrentIndex(index)

    def create_command(self):
        selected=self.commands.currentData();before={c['id'] for c in self.host.store.read('commands.json')['commands']}
        self.host.command_edit(True)
        created=[c for c in self.host.store.read('commands.json')['commands'] if c['id'] not in before]
        self.populate(created[-1]['id'] if created else selected)

    def accept(self):
        self.value.update(commandId=self.commands.currentData() or '');super().accept()
