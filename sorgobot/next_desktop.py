"""Independent native edition; shares tested adapters, never imports user actions."""
import argparse
import copy
import json
import os
import subprocess
import sys
from pathlib import Path
from PySide6.QtCore import Qt, QLockFile, QTimer
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTreeWidget, QTreeWidgetItem, QLineEdit, QLabel, QMessageBox, QFrame, QToolButton, QDialog, QDialogButtonBox, QComboBox, QCheckBox, QFormLayout, QFileDialog, QHeaderView, QMenu)
from PySide6.QtGui import QColor
from .catalog import ConfigStore, STEPS, TRIGGERS, new_action, validate_action
from .desktop import MainWindow, ActionDialog, FieldsDialog, buttons, ROLE
from .editor_menus import bind, action_menu, editor_menu, catalog_menu, renewed
from .next_catalog import steps as available_steps, triggers as available_triggers
from .next_menus import editor_context,add_catalog,action_context
from .subaction_tree import SubActionTree
from .platform_twitch import TwitchPage
from .action_history import HistoryPage
from .branding import NAME, ICON, configure as configure_branding


def initialize(root, source):
    root=Path(root);source=Path(source)
    (root/'config').mkdir(parents=True,exist_ok=True);(root/'state').mkdir(exist_ok=True)
    store=ConfigStore(root)
    from .fresh_project import documents
    defaults=documents()
    for name,value in defaults.items():
        if not (root/'config'/name).exists():store.save(name,value)


def original_menu(menu):
    labels={'Hinzufügen':'Add','Bearbeiten':'Edit','Duplizieren':'Duplicate','Entfernen':'Delete','Ausführen':'Test Action',
            'Aktiviert umschalten':'Enabled','Aktions-ID kopieren':'Copy Action ID','Alle ausklappen':'Expand All','Alle einklappen':'Collapse All',
            'Kopieren':'Copy Sub-Action','Einfügen':'Paste Sub-Action','Nach oben':'Move Up','Nach unten':'Move Down',
            'Ablauf':'Core','Variablen':'Arguments / Variables','Audio':'Audio','Netzwerk':'Network','Kamera':'Camera','Kommentar':'Comment'}
    for action in menu.actions():
        action.setText(labels.get(action.text(),action.text()))
        if action.menu():original_menu(action.menu())
    return menu


class ActionProperties(QDialog):
    """Action properties belong in a modal dialog, as in the original app."""
    def __init__(self,action,window):
        super().__init__(window);self.value=copy.deepcopy(action)
        self.setWindowTitle('Edit Action' if action.get('name') else 'Add Action');self.setMinimumWidth(560)
        layout=QVBoxLayout(self);form=QFormLayout();layout.addLayout(form)
        row=QWidget();rl=QHBoxLayout(row);rl.setContentsMargins(0,0,0,0)
        self.name=QLineEdit(action.get('name',''));self.name.setPlaceholderText('Enter a unique Action name...')
        self.enabled=QCheckBox('Enabled');self.enabled.setChecked(action.get('enabled',True));rl.addWidget(self.name);rl.addWidget(self.enabled)
        form.addRow('Name',row)
        if action.get('migrationBlock'):
            self.enabled.setChecked(False);self.enabled.setEnabled(False)
            notice=QLabel('Import noch nicht ausführbar: '+action['migrationBlock']);notice.setWordWrap(True);notice.setTextFormat(Qt.TextFormat.PlainText);form.addRow('Migration',notice)
            from PySide6.QtWidgets import QPushButton
            review=QPushButton('Import prüfen und zum Testen freigeben …')
            def open_review():
                self.reject();QTimer.singleShot(0,lambda:window.review_import(action['id']))
            review.clicked.connect(open_review);form.addRow('',review)
        self.group=QComboBox();self.group.setEditable(True);self.group.addItems(sorted({a.get('group','') for a in window.document['actions']}));self.group.setCurrentText(action.get('group',''));form.addRow('Group',self.group)
        self.queue=QComboBox();self.queue.addItem('Default',None)
        for q in window.document.get('queues',[]):self.queue.addItem(q['name'],q['id'])
        if action.get('migrationBlock') and action.get('queue') and self.queue.findData(action['queue'])<0:
            name=next((q.get('name','Importierte Queue') for b in window.document.get('originalBundles',[]) for q in b.get('envelope',{}).get('data',{}).get('queues',[]) if q.get('id')==action['queue']),'Importierte Queue')
            self.queue.addItem(name+' (Import)',action['queue'])
        self.queue.setCurrentIndex(max(0,self.queue.findData(action.get('queue'))));form.addRow('Queue',self.queue)
        self.options={}
        for key,label in [('random','Random Action'),('concurrent','Concurrent'),('alwaysRun','Always Run (even if Queue is Paused)'),('excludeHistory','Exclude from Action Queue Pending/History')]:
            option=QCheckBox(label);option.setChecked(action.get(key,False));self.options[key]=option

            form.addRow('',option)
        box=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);box.accepted.connect(self.accept);box.rejected.connect(self.reject);layout.addWidget(box)

    def accept(self):
        self.value.update(name=self.name.text().strip(),group=self.group.currentText(),queue=self.queue.currentData(),enabled=self.enabled.isChecked())
        self.value.update({key:option.isChecked() for key,option in self.options.items()})
        try:validate_action(self.value)
        except ValueError as exc:QMessageBox.warning(self,'Action',str(exc));return
        super().accept()


class InlineEditor(ActionDialog):
    """Reuse editing operations; only the two list views enter the main window."""
    def __init__(self,action,window):
        self.host=window;self.loading=True
        super().__init__(action,window.store,window)
        # This dialog is a controller, never shown or embedded as a form.
        self.triggers.setParent(window.trigger_card);window.trigger_layout.addWidget(self.triggers)
        previous=self.steps;self.steps=SubActionTree(self);previous.deleteLater()
        self.steps.itemDoubleClicked.connect(self.edit_step)
        self.steps.setParent(window.step_card);window.step_layout.addWidget(self.steps)
        from .app_shortcuts import editor as bind_editor
        bind_editor(self)
        self.loading=False;self.refresh()
        bind(self.triggers,lambda:editor_context(self,True))
        bind(self.steps,lambda:editor_context(self))

    def refresh(self):
        super().refresh()
        self.triggers.setHeaderLabels(['Source','Type','Enabled','Criteria'])
        for i,t in enumerate(self.value['triggers']):
            category,_,name=TRIGGERS.get(t['type'],(str(t['type']),{}))[0].partition(' · ')
            if t['type']==90255 and t.get('codeTriggerName'):category='Custom';name=' · '.join([*t.get('categories',[]),t['codeTriggerName']])
            item=self.triggers.topLevelItem(i)
            item.setText(0,category);item.setText(1,name or category);item.setText(2,'Yes' if t.get('enabled',True) else 'No')
            from .trigger_labels import criteria
            item.setText(3,criteria(t,self.host.store))
        for i,width in enumerate((120,180,65)):self.triggers.setColumnWidth(i,width)
        self.steps.setHeaderHidden(True);self.steps.setColumnCount(1)
        def describe(nodes,parent):
            for i,node in enumerate(nodes):
                item=parent.child(i);label=available_steps().get(node['type'],STEPS.get(node['type'],(str(node['type']),{})))[0]
                detail=node.get('prompt',node.get('text',node.get('value',node.get('sceneName',node.get('name','')))))
                if node['type']==90004:
                    from .ai_fields import prompt_label
                    detail='Benutzerdefiniert' if node.get('promptKind')=='__custom__' else prompt_label(node.get('promptKind','chat'))
                item.setText(0,label+('  —  '+str(detail) if detail else ''))
                flags=item.flags()
                if node['type'] not in (99900,99901,99902,90161,90164,90165):flags &= ~Qt.ItemFlag.ItemIsDropEnabled
                if node['type'] in (99901,99902):flags &= ~Qt.ItemFlag.ItemIsDragEnabled
                item.setFlags(flags)
                if not node.get('enabled',True):item.setForeground(0,QColor('#ef7777'))
                elif node['type']==1009:item.setForeground(0,QColor('#55b99e'))
                describe(node.get('subActions',[]),item)
        describe(self.value['subActions'],self.steps.invisibleRootItem())
        self.steps.header().setStretchLastSection(True)
        if not self.loading:self.persist()

    def selected_trigger(self):
        item=self.triggers.currentItem();nodes=self.value['triggers']
        if item is None and self.triggers.selectedItems():item=self.triggers.selectedItems()[0]
        for index,node in enumerate(nodes):
            if item and node['id']==item.data(0,ROLE):return nodes,index,node
        return None,None,None

    def remember_trigger(self,kind):
        try:preferences=self.host.store.read('editor.json')
        except FileNotFoundError:preferences={}
        recent=preferences.get('recentTriggers',[]);preferences['recentTriggers']=[kind,*[k for k in recent if k!=kind]][:10]
        self.host.store.save('editor.json',preferences)

    def add_trigger(self,kind=None):
        if kind is None or kind is False:return self.host.search_catalog(True)
        if isinstance(kind,str) and kind.startswith('code:'):
            import uuid
            from .csharp_core_services import catalog
            choices=catalog({},getattr(self.host,'code_triggers',[]))
            if kind not in choices:return
            self.value['triggers'].append({'id':str(uuid.uuid4()),'type':90255,'enabled':True,**copy.deepcopy(choices[kind][1])});self.refresh();self.remember_trigger(kind);return
        if kind in (401,402):
            import uuid
            from .command_trigger import CommandTriggerDialog
            trigger={'id':str(uuid.uuid4()),'type':kind,'enabled':True,'commandId':''}
            dialog=CommandTriggerDialog(trigger,self.host)
            if dialog.exec()!=QDialog.DialogCode.Accepted:return
            self.value['triggers'].append(dialog.value);self.refresh()
        else:
            before=len(self.value['triggers']);super().add_trigger(kind)
            if len(self.value['triggers'])==before:return
        self.remember_trigger(kind)

    def edit_trigger(self,*_):
        nodes,index,trigger=self.selected_trigger()
        if not trigger:return
        if trigger['type'] not in (401,402):return super().edit_trigger()
        from .command_trigger import CommandTriggerDialog
        dialog=CommandTriggerDialog(trigger,self.host,new=False)
        if dialog.exec()==QDialog.DialogCode.Accepted:nodes[index]=dialog.value;self.refresh()

    def insert_node(self,node):
        nodes,index,selected=self.selected()
        if selected and selected['type'] in (99900,99901,99902,90161,90165):selected['subActions'].append(node)
        elif selected and selected['type']==90164:
            if node['type']!=90165:return
            selected['subActions'].append(node)
        elif nodes is not None:nodes.insert(index+1,node)
        else:self.value['subActions'].append(node)

    def add_step(self,kind=None):
        from .catalog import new_step
        from PySide6.QtWidgets import QInputDialog
        if kind is None or kind is False:return self.host.search_catalog(False)
        label,defaults=('Add Group',STEPS[99900][1]) if kind==99900 else available_steps()[kind]
        node=new_step(kind);node.update(copy.deepcopy(defaults))
        if 'actionId' in node:
            actions=self.host.document['actions']
            if not actions:return
            names=[a['name']+'  ('+a['id'][:8]+')' for a in actions]
            name,ok=QInputDialog.getItem(self.host,'Select Action','Action',names,0,False)
            if not ok:return
            node['actionId']=actions[names.index(name)]['id']
        from .desktop import step_dialog
        dialog=step_dialog(label,node,self.host)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            self.insert_node(dialog.value);self.refresh()
            if kind in available_steps():
                try:preferences=self.host.store.read('editor.json')
                except FileNotFoundError:preferences={}
                recent=preferences.get('recentSubActions',[])
                preferences['recentSubActions']=[kind,*dict.fromkeys(k for k in recent if isinstance(k,int) and k!=kind and k in available_steps())][:10]
                self.host.store.save('editor.json',preferences)

    def move_node(self,identity,parent_id,index):
        def find(nodes):
            for i,node in enumerate(nodes):
                if node['id']==identity:return nodes,i,node
                found=find(node.get('subActions',[]))
                if found:return found
        found=find(self.value['subActions'])
        if not found or found[2]['type'] in (99901,99902):return False
        old,old_index,node=found
        def contains(value,target):return value['id']==target or any(contains(child,target) for child in value.get('subActions',[]))
        if parent_id and contains(node,parent_id):return False
        def parent(nodes):
            for n in nodes:
                if n['id']==parent_id:return n
                found=parent(n.get('subActions',[]))
                if found:return found
        target=parent(self.value['subActions']) if parent_id else None
        if parent_id and (target is None or target['type'] not in (99900,99901,99902,90161,90164,90165)):return False
        if target and target['type']==90164 and node['type']!=90165:return False
        if node['type']==90165 and (not target or target['type']!=90164):return False
        destination=target['subActions'] if target else self.value['subActions']
        if destination is old and index>old_index:index-=1
        old.pop(old_index);destination.insert(max(0,min(index,len(destination))),node);self.refresh();return True

    def test_trigger(self):
        _,_,trigger=self.selected_trigger()
        if trigger:
            self.host.runtime.submit('test_trigger',id=self.value['id'],triggerId=trigger['id'])

    def persist_metadata(self,*_):
        name=self.name.text().strip()
        if name:self.value.update(name=name,group=self.group.text(),enabled=self.enabled.isChecked(),queue=self.queue.currentData());self.persist()

    def persist(self):
        window=self.host
        original=next((a for a in window.document['actions'] if a['id']==self.value['id']),None)
        if original==self.value:return
        window.document['actions']=[copy.deepcopy(self.value) if a['id']==self.value['id'] else a for a in window.document['actions']]
        window.store.save('actions.json',window.document)
        if hasattr(window,'runtime'):window.runtime.submit('reload')
        window.update_action_rows();window.statusBar().showMessage('Saved',3000)


class NextWindow(MainWindow):
    def event_context(self,position):
        item=self.event_table.itemAt(position)
        if item is None:return
        identity=item.data(0,ROLE)
        from .chat_settings import read
        menu=QMenu(self)
        for quick in read(self.store)['quickActions']:
            if quick['scope']=='event':menu.addAction(quick['name'],lambda checked=False,q=quick:self.runtime.submit('chat_quick_action',quickId=q['id'],row={'id':identity}))
        if menu.isEmpty():menu.addAction('Configure Event Quick Actions…',self.chat_dialog.settings)
        menu.exec(self.event_table.viewport().mapToGlobal(position))

    def __init__(self,root,live=False,obs_test=False):
        super().__init__(root,live,obs_test);self.search.clear()
        from PySide6.QtGui import QIcon
        self.setWindowTitle(NAME+' — '+self.mode_label);self.setWindowIcon(QIcon(str(ICON)));self.resize(1440,900)
        self.menuBar().hide()
        # Keep adapter/settings pages but rebuild the desktop shell from the reference.
        central=self.centralWidget();layout=central.layout()
        banner=layout.takeAt(0).widget();banner.deleteLater()
        layout.setContentsMargins(0,0,0,0);layout.setSpacing(0)
        self.tabs.setParent(None);self.tabs.tabBar().hide();self.tabs.setObjectName('content')
        toolbar=QWidget();toolbar.setObjectName('toolbar');tools=QHBoxLayout(toolbar);tools.setContentsMargins(4,2,10,2);tools.setSpacing(0)
        def tool(label,callback):
            b=QToolButton();b.setObjectName('tool');b.setText(label);b.clicked.connect(callback);tools.addWidget(b);return b
        tool('☷  Menu',lambda:self.sidebar.setVisible(not self.sidebar.isVisible()))
        tool('▣  Save',self.save_actions);tool('⇥  Import',self.import_actions);tool('⇤  Export',self.export_actions)
        tool('Logs',self.open_logs)
        from PySide6.QtGui import QShortcut,QKeySequence,QDesktopServices
        from PySide6.QtCore import QUrl
        self.app_shortcuts=[]
        for sequence,callback in [('Ctrl+S',self.save_actions),('Ctrl+Alt+I',self.import_actions),('Ctrl+Alt+E',self.export_actions),('Ctrl+Alt+C',self.open_chat),('Ctrl+Alt+V',self.show_globals),('Ctrl+Alt+L',self.open_logs),('F1',lambda:QDesktopServices.openUrl(QUrl('https://docs.streamer.bot/guide')))]:
            shortcut=QShortcut(QKeySequence(sequence),self);shortcut.activated.connect(callback);self.app_shortcuts.append(shortcut)

        tool('▣  Backup',self.open_backup);tool('▢  Chat',self.open_chat);tool('▤  Event Feed',lambda:self.navigate('feed'))
        tool('{x}  Global Variables',self.show_globals)
        tools.addStretch();self.voice_indicator=QLabel('MIC aus');self.voice_indicator.setContentsMargins(8,0,8,0);tools.addWidget(self.voice_indicator);self.connection_status=QLabel(self.mode_label+'  ●');tools.addWidget(self.connection_status);layout.addWidget(toolbar)
        body=QWidget();bl=QHBoxLayout(body);bl.setContentsMargins(0,0,0,0);bl.setSpacing(0)
        self.sidebar=QWidget();self.sidebar.setObjectName('sidebar');self.sidebar.setFixedWidth(268);sl=QVBoxLayout(self.sidebar);sl.setContentsMargins(4,7,4,6)
        brand=QWidget();brand.setObjectName('brand');brand_row=QHBoxLayout(brand);brand_row.setContentsMargins(10,0,10,6)
        mark=QLabel();mark.setPixmap(QIcon(str(ICON)).pixmap(40,40));brand_row.addWidget(mark)
        name=QLabel(NAME);name.setObjectName('brandName');brand_row.addWidget(name);brand_row.addStretch();sl.addWidget(brand)
        from PySide6.QtWidgets import QAbstractItemView
        self.navigation=QTreeWidget();self.navigation.setObjectName('navigation');self.navigation.setHeaderHidden(True);self.navigation.setIndentation(19);self.navigation.setRootIsDecorated(True);self.navigation.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel);sl.addWidget(self.navigation)
        self.routes={};self.nav_items={}
        def entry(label,route=None,parent=None,disabled=False):
            item=QTreeWidgetItem([label]);(parent or self.navigation.invisibleRootItem()).addChild(item)
            if route:item.setData(0,ROLE,route);self.nav_items[route]=item
            if disabled:item.setDisabled(True);item.setToolTip(0,'Noch nicht implementiert')
            return item
        self.routes['actions']=0;self.routes['commands']=1;self.routes['timers']=2;self.routes['ai']=3;self.routes['settings']=4;self.routes['obs']=5;self.routes['history']=6
        home=self.page('Home');self.home_status=QTreeWidget();self.home_status.setHeaderLabels(['Status','Value']);home.addWidget(self.home_status);home.addStretch();self.routes['home']=self.tabs.count()-1
        self.make_queues();self.routes['queues']=self.tabs.count()-1
        twitch_layout=self.page('Twitch');self.twitch_page=TwitchPage(self);twitch_layout.addWidget(self.twitch_page);self.routes['twitch']=self.tabs.count()-1
        pending_layout=self.page('Pending Actions');self.pending_page=HistoryPage(self,pending=True);pending_layout.addWidget(self.pending_page);self.routes['pending']=self.tabs.count()-1
        viewers=self.page('Viewers');self.viewer_status=QLabel('Waiting for Twitch chat presence…');self.viewer_status.setWordWrap(True);viewers.addWidget(self.viewer_status);self.viewer_table=QTreeWidget();self.viewer_table.setHeaderLabels(['Name','Login','Platform','Roles','Last Active']);viewers.addWidget(self.viewer_table);self.routes['viewers']=self.tabs.count()-1
        feed=self.page('Event Feed');self.event_table=QTreeWidget();self.event_table.setHeaderLabels(['Time','Platform','Event','User']);self.event_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu);self.event_table.customContextMenuRequested.connect(self.event_context);feed.addWidget(self.event_table);self.routes['feed']=self.tabs.count()-1
        about=self.page('About');text=QLabel(NAME+' – native Streaming-Automation für Linux.\nImplementierte Integrationen: OBS, Local LLM und OpenAI; Twitch OAuth mit eigener Public-Client-ID.\nVollständige Streamer.bot-Funktionsgleichheit ist noch nicht erreicht.');text.setWordWrap(True);about.addWidget(text);about.addStretch();self.routes['about']=self.tabs.count()-1
        entry('⌂  Home','home');entry('♙  Viewers','viewers')
        aq=entry('ϟ  Actions & Queues');entry('ϟ  Actions','actions',aq);entry('◉  Queues','queues',aq);entry('▤  Pending Actions','pending',aq);entry('◷  Action History','history',aq)
        entry('⌘  Commands','commands');platforms=entry('▣  Platforms');entry('▣  Twitch','twitch',platforms);entry('▣  YouTube','youtube',platforms)
        from .youtube_ui import YouTubePage
        youtube_layout=self.page('YouTube');self.youtube_page=YouTubePage(self);youtube_layout.addWidget(self.youtube_page);self.routes['youtube']=self.tabs.count()-1
        from .game_detection_ui import GameDetectionPage
        game_layout=self.page('Game Detection');self.game_detection_page=GameDetectionPage(self);game_layout.addWidget(self.game_detection_page);self.routes['game_detection']=self.tabs.count()-1
        apps=entry('◧  Stream Apps');entry('◉  OBS Studio','obs',apps)
        from .linux_audio_ui import AudioPage
        audio_layout=self.page('Linux Audio');self.audio_page=AudioPage(self);audio_layout.addWidget(self.audio_page);self.routes['audio']=self.tabs.count()-1;entry('Linux Audio','audio',apps)
        from .streamdeck_ui import StreamDeckPage
        deck_layout=self.page('Stream Deck / OpenDeck');self.streamdeck_page=StreamDeckPage(self);deck_layout.addWidget(self.streamdeck_page);self.routes['streamdeck']=self.tabs.count()-1;entry('Stream Deck / OpenDeck','streamdeck',apps)
        from .core_settings_ui import CoreSettingsPage
        integrations=entry('◈  Integrations');entry('AI','ai',integrations)
        from .streamermod_remote_ui import RemotePage
        remote_layout=self.page('StreamerMod Remote');self.remote_page=RemotePage(self);remote_layout.addWidget(self.remote_page);self.routes['remote']=self.tabs.count()-1;entry('StreamerMod Remote','remote',integrations)
        core_group=entry('◈  Services');self.core_pages={};self.service_pages={}
        from .service_management_ui import ServicePage,QuotesPage
        def service_page(section,label,parent,route=None,log_only=False):
            route=route or section;page_layout=self.page(label);page=ServicePage(self,section,log_only);page_layout.addWidget(page);self.service_pages[route]=page;self.routes[route]=self.tabs.count()-1;entry(label,route,parent)
        def core_page(section,label,parent,route=None,view_filter=None):
            route=route or section
            core_layout=self.page(label);self.core_pages[route]=CoreSettingsPage(self,section,view_filter);core_layout.addWidget(self.core_pages[route]);self.routes[route]=self.tabs.count()-1;entry(label,route,parent)
        core_page('fileWatchers','File/Folder Watcher',core_group)
        entry('◷  Timers','timers',core_group)
        core_page('fileTails','File Tails',core_group)
        service_page('process','Process Watcher',core_group)
        from .users_ui import UsersPage
        users_layout=self.page('Known Users');self.users_page=UsersPage(self);users_layout.addWidget(self.users_page);self.routes['knownUsers']=self.tabs.count()-1;
        from .credits_ui import CreditsPage
        credits_layout=self.page('Credits');self.credits_page=CreditsPage(self);credits_layout.addWidget(self.credits_page);self.routes['credits']=self.tabs.count()-1;entry('Credits','credits',core_group)
        quotes_layout=self.page('Quotes');self.quotes_page=QuotesPage(self);quotes_layout.addWidget(self.quotes_page);self.routes['quotes']=self.tabs.count()-1;entry('Quotes','quotes',core_group)
        entry('Known Users','knownUsers',core_group);entry('Game Detection','game_detection',core_group)
        for section,label in [('pointDefinitions','Points'),('userGroups','User Groups'),('inputDevices','Input Devices'),('cronSchedules','Cron Schedules')]:core_page(section,label,core_group)
        midi=entry('♬  MIDI');core_page('midiDevices','MIDI In',midi,'midiIn',{'listen':True});core_page('midiDevices','MIDI Out',midi,'midiOut',{'listen':False})
        voice=entry('◉  Voice Control');service_page('voice','Settings',voice,'voiceSettings');core_page('voiceCommands','Commands',voice);service_page('voice','Log',voice,'voiceLog',True)
        servers=entry('◈  Servers/Clients')
        service_page('websocket','WebSocket Server',servers);service_page('http','HTTP Server',servers);service_page('udp','UDP Server',servers)
        core_page('websocketConnections','Custom WebSocket Servers',servers,'websocketServers',{'mode':'server'})
        core_page('websocketConnections','Custom WebSocket Clients',servers,'websocketClients',{'mode':'client'})
        self.routes['midiDevices']=self.routes['midiIn'];self.routes['websocketConnections']=self.routes['websocketClients']
        entry('⚙  Settings','settings').setHidden(True);entry('ⓘ  About','about');self.navigation.collapseAll();aq.setExpanded(True)
        self.navigation.currentItemChanged.connect(lambda item,old:self.navigate(item.data(0,ROLE)) if item and item.data(0,ROLE) else None)
        self.settings_button=QToolButton();self.settings_button.setObjectName('sidebarSettings');self.settings_button.setText('⚙  Settings');self.settings_button.setCheckable(True);self.settings_button.clicked.connect(lambda:self.navigate('settings'));sl.addWidget(self.settings_button)
        sl.addWidget(QLabel('  Linux  ·  '+self.mode_label));bl.addWidget(self.sidebar);bl.addWidget(self.tabs,1);layout.addWidget(body,1)
        self.navigate('actions')

    def update_voice_indicator(self,value):
        voice=value.get('voice',{});phase=voice.get('phase','stopped')
        self.voice_indicator.setText({'listening':'● MIC an','starting':'◌ MIC startet','error':'MIC Fehler'}.get(phase,'MIC aus'))
        self.voice_indicator.setStyleSheet('color:'+('#ff716b' if phase=='listening' else '#e5bf69' if phase in ('starting','error') else '#b1b5b5'))
        self.voice_indicator.setToolTip(voice.get('error') or ('Lokale Mikrofonaufnahme läuft' if phase=='listening' else 'Keine integrierte Mikrofonaufnahme'))

    def open_backup(self):
        from .project_backup_ui import BackupDialog
        if getattr(self,'backup_dialog',None) is not None:
            self.backup_dialog.raise_();return
        self.backup_dialog=BackupDialog(self)
        try:self.backup_dialog.exec()
        finally:self.backup_dialog.deleteLater();self.backup_dialog=None

    def closeEvent(self,event):
        if getattr(getattr(self,'backup_dialog',None),'busy',False):
            self.statusBar().showMessage('Projektoperation läuft; bitte den Abschluss abwarten.');event.ignore();return
        super().closeEvent(event)
        # OpenDeck is independent and stays running after StreamerMod closes.

    def page(self,name):
        layout=super().page(name);layout.setContentsMargins(12,10,12,12);layout.setSpacing(10)
        if name not in ('Actions','Queues'):
            title=QLabel({'Befehle':'Commands','Timer':'Timers','KI / Prompts':'AI','Verbindungen / Geräte':'Settings','OBS / Chat':'OBS Studio','Verlauf / Diagnose':'Action History'}.get(name,name));title.setObjectName('pageTitle');layout.addWidget(title)
        return layout

    def make_connections(self):
        from PySide6.QtWidgets import QPlainTextEdit,QTabWidget,QPushButton
        layout=self.page('Verbindungen / Geräte');self.settings_tabs=QTabWidget();layout.addWidget(self.settings_tabs)
        devices=QWidget();dl=QVBoxLayout(devices);form=QFormLayout();dl.addLayout(form);self.connection_fields={};config=self.store.read('local.json')
        for key,label in [('camera_device','Camera Device'),('keyboard_device','Keyboard Device'),('tts_voice','TTS Voice'),('microphone','Microphone'),('headset','Headset')]:
            edit=QLineEdit(str(config.get(key,'')));self.connection_fields[key]=edit;form.addRow(label,edit)
        self.camera_enabled=QCheckBox('Enable local camera service');self.camera_enabled.setChecked(config.get('camera_enabled',False));form.addRow('',self.camera_enabled)
        save=QPushButton('Save device settings');save.clicked.connect(self.save_connections);dl.addWidget(save)
        preview=QPushButton('Test camera image');preview.clicked.connect(lambda:self.runtime.submit('camera_preview'));dl.addWidget(preview)
        self.camera_image=QLabel('Noch kein Kameratest');self.camera_image.setAlignment(Qt.AlignmentFlag.AlignCenter);self.camera_image.setMinimumHeight(280);dl.addWidget(self.camera_image,1);dl.addStretch();self.settings_tabs.addTab(devices,'Devices')
        self.log=QPlainTextEdit();self.log.setReadOnly(True);self.settings_tabs.addTab(self.log,'Diagnostics')

    def make_log(self):
        layout=self.page('Verlauf / Diagnose');self.history_page=HistoryPage(self);layout.addWidget(self.history_page)

    def make_commands(self):
        super().make_commands()
        layout=self.tabs.widget(self.tabs.count()-1).layout()
        # The original commands view uses context operations instead of a button bar.
        from PySide6.QtWidgets import QPushButton
        for button in self.command_table.parentWidget().findChildren(QPushButton):button.hide()
        self.command_table.setHeaderLabels(['Name','Command','Enabled','Permissions'])
        self.command_table.setIndentation(12)
        self.command_table.setHeaderLabels(['Name','Command','Enabled','Permissions'])
        bind(self.command_table,self.command_context)
        from .app_shortcuts import commands
        commands(self)

    def populate_commands(self):
        if not hasattr(self,'command_table'):return
        self.command_table.clear();groups={}
        for c in self.store.read('commands.json')['commands']:
            name=c.get('group','')
            if name not in groups:
                group=QTreeWidgetItem([name or 'None']);group.setData(0,ROLE+1,name);group.setFirstColumnSpanned(True);groups[name]=group;self.command_table.addTopLevelItem(group)
            item=QTreeWidgetItem([c['name'],c['command'],'Yes' if c.get('enabled',True) else 'No',', '.join(c.get('permittedGroups',[]))]);item.setData(0,ROLE,c['id']);groups[name].addChild(item)
        self.command_table.expandAll()
        for i in (0,1):self.command_table.resizeColumnToContents(i)

    def command_edit(self,new):
        import uuid
        from .command_dialog import CommandDialog
        document=self.store.read('commands.json');item=self.command_table.currentItem()
        command={'id':str(uuid.uuid4()),'name':'','command':'','enabled':True,'mode':0,'location':0,'permittedGroups':[],'permittedUsers':[]} if new else next((c for c in document['commands'] if item and c['id']==item.data(0,ROLE)),None)
        if command is None:return
        dialog=CommandDialog(command,self,new)
        if dialog.exec()!=QDialog.DialogCode.Accepted:return
        if new:document['commands'].append(dialog.value)
        else:document['commands']=[dialog.value if c['id']==command['id'] else c for c in document['commands']]
        self.store.save('commands.json',document);self.populate_commands();self.runtime.submit('reload')

    def command_context(self):
        from PySide6.QtWidgets import QMenu,QInputDialog
        menu=QMenu(self);doc=self.store.read('commands.json');item=self.command_table.currentItem()
        node=next((c for c in doc['commands'] if item and c['id']==item.data(0,ROLE)),None)
        def save():self.store.save('commands.json',doc);self.populate_commands();self.runtime.submit('reload')
        menu.addAction('Add',lambda:self.command_edit(True));menu.addAction('Edit',lambda:self.command_edit(False)).setEnabled(node is not None);menu.addAction('Delete',self.command_delete).setEnabled(node is not None)
        def duplicate():
            from .editor_menus import renewed
            clone=renewed(node);clone['name']+=' (Copy)';doc['commands'].append(clone);save()
        menu.addAction('Duplicate',duplicate).setEnabled(node is not None)
        def toggle():node['enabled']=not node.get('enabled',True);save()
        action=menu.addAction('Enabled',toggle);action.setEnabled(node is not None);action.setCheckable(True);action.setChecked(node.get('enabled',True) if node else False)
        def set_group():
            group,ok=QInputDialog.getText(self,'Set Group','Group',text=node.get('group',''))
            if ok:node['group']=group.strip();save()
        menu.addAction('Set Group',set_group).setEnabled(node is not None)
        parent=item.parent() if item and item.parent() else item
        def rename_group():
            old=parent.data(0,ROLE+1);group,ok=QInputDialog.getText(self,'Rename Group','Group',text=old or '')
            if ok:
                for c in doc['commands']:
                    if c.get('group','')==old:c['group']=group.strip()
                save()
        menu.addAction('Rename Group',rename_group).setEnabled(parent is not None)
        from PySide6.QtWidgets import QApplication
        menu.addAction('Copy Command ID',lambda:QApplication.clipboard().setText(node['id'])).setEnabled(node is not None)
        return menu

    def make_obs(self):
        layout=self.page('OBS / Chat')
        self.obs_connections=QTreeWidget();self.obs_connections.setHeaderLabels(['Name','Version','Host','Port','Status','Auto Connect','Reconnect']);layout.addWidget(self.obs_connections)
        self.obs_details=QLabel('');self.obs_details.setWordWrap(True);layout.addWidget(self.obs_details)
        layout.addStretch();self.populate_obs_connections()
        bind(self.obs_connections,self.obs_connection_menu);self.obs_connections.itemDoubleClicked.connect(lambda *_:self.edit_obs_connection())
        # Chat is a separate utility, no stream preview or production controls here.
        from .chat_ui import ChatWindow
        self.chat_dialog=ChatWindow(self);self.chat_view=self.chat_dialog.view;self.chat_input=self.chat_dialog.input

    def open_chat(self):self.chat_dialog.show()

    def populate_obs_connections(self,status=None):
        from urllib.parse import urlsplit
        from .obs_connections import definitions
        selected=self.obs_connections.currentItem()
        identity=selected.data(0,ROLE) if selected else None
        states=getattr(self,'obs_runtime_states',{})
        if isinstance(status,dict):states=status
        elif isinstance(status,str):states.setdefault('default',{})['status']=status
        self.obs_runtime_states=states
        config=self.store.read('local.json');self.obs_connections.clear()
        for row in definitions(config):
            if not row.get('enabled',True):continue
            address=urlsplit(row['url']);state=states.get(row['id'],{})
            label=row['name']+(' (Default)' if state.get('default',config.get('obsDefaultConnection','default')==row['id']) else '')+(' (Force)' if state.get('forced') else '')
            item=QTreeWidgetItem([label,'WebSocket v5',address.hostname or '',str(address.port or (443 if address.scheme=='wss' else 4455)),state.get('status','Not connected'),'Yes' if row.get('autoConnect',True) else 'No','Yes' if row.get('reconnect',True) else 'No'])
            item.setData(0,ROLE,row['id']);self.obs_connections.addTopLevelItem(item)
            if identity==row['id']:self.obs_connections.setCurrentItem(item)
        if not self.obs_connections.currentItem() and self.obs_connections.topLevelItemCount():self.obs_connections.setCurrentItem(self.obs_connections.topLevelItem(0))
        for i in range(7):self.obs_connections.resizeColumnToContents(i)

    def obs_save_row(self,row):
        config=self.store.read('local.json')
        if row['id']=='default':
            for key,target in [('name','obs_name'),('url','obs_url'),('password','obs_password'),('autoConnect','obs_auto_connect'),('reconnect','obs_reconnect'),('retryInterval','obs_retry_interval'),('enabled','obs_enabled')]:config[target]=row[key]
        else:
            rows=[v for v in config.get('obsConnections',[]) if v['id']!=row['id']];rows.append(row);config['obsConnections']=rows
        self.store.save('local.json',config);self.populate_obs_connections();self.runtime.submit('reload')

    def edit_obs_connection(self,new=False):
        from .obs_connections import definitions,validate
        import uuid
        rows=definitions(self.store.read('local.json'));item=self.obs_connections.currentItem()
        if new:
            value={'id':uuid.uuid4().hex,'name':'OBS','url':'ws://127.0.0.1:4455','password':'','autoConnect':False,'reconnect':True,'retryInterval':5,'enabled':True}
            if not rows[0].get('enabled',True):value=rows[0];value['enabled']=True
        elif item:value=next(row for row in rows if row['id']==item.data(0,ROLE))
        else:return
        dialog=FieldsDialog('OBS Connection · WebSocket v5',value,self)
        dialog.controls['password'][0].setEchoMode(QLineEdit.EchoMode.Password)
        if dialog.exec()!=QDialog.DialogCode.Accepted:return
        try:value=validate(dialog.value)
        except ValueError as exc:QMessageBox.warning(self,'OBS',str(exc));return
        self.obs_save_row(value)

    def obs_connection_menu(self):
        from PySide6.QtWidgets import QMenu
        from .obs_connections import definitions
        menu=QMenu(self);item=self.obs_connections.currentItem();identity=item.data(0,ROLE) if item else None
        row=next((r for r in definitions(self.store.read('local.json')) if r['id']==identity),None)
        menu.addAction('Add',lambda:self.edit_obs_connection(True))
        menu.addAction('Edit',lambda:self.edit_obs_connection()).setEnabled(row is not None)
        def delete():
            config=self.store.read('local.json')
            if identity=='default':config['obs_enabled']=False
            else:config['obsConnections']=[r for r in config.get('obsConnections',[]) if r['id']!=identity]
            if config.get('obsDefaultConnection')==identity:config.pop('obsDefaultConnection',None)
            self.store.save('local.json',config);self.populate_obs_connections();self.runtime.submit('reload')
        menu.addAction('Delete',delete).setEnabled(row is not None)
        for key,label in [('autoConnect','Auto Connect'),('reconnect','Reconnect')]:
            def toggle(checked=False,k=key):
                value=dict(row);value[k]=checked;self.obs_save_row(value)
            action=menu.addAction(label,toggle);action.setCheckable(True);action.setChecked(row.get(key,True) if row else False);action.setEnabled(row is not None)
        def default():
            config=self.store.read('local.json');config['obsDefaultConnection']=identity;self.store.save('local.json',config);self.runtime.submit('reload');self.populate_obs_connections()
        menu.addAction('Set Default',default).setEnabled(row is not None)
        action=menu.addAction('Force',lambda checked:self.runtime.submit('obs_force',connectionId=identity if checked else None));action.setCheckable(True);action.setChecked(getattr(self,'obs_runtime_states',{}).get(identity,{}).get('forced',False));action.setEnabled(row is not None)
        menu.addSeparator()
        for label,kind in [('Connect','obs_connect'),('Disconnect','obs_disconnect'),('Refresh','obs_info')]:menu.addAction(label,lambda checked=False,k=kind:self.runtime.submit(k,connectionId=identity)).setEnabled(row is not None)
        return menu

    def runtime_ready(self):
        if self.runtime.stopping:return
        self.statusBar().showMessage('Ready · '+self.mode_label);self.poll.start(4000)
        for kind in ('services_get','quotes_get','credits_get'):self.runtime.submit(kind)
        if self.tabs.currentIndex()==self.routes.get('voiceSettings'):self.runtime.submit('audio_snapshot')

    def make_timers(self):
        super().make_timers()
        from PySide6.QtWidgets import QMenu,QPushButton
        for button in self.timer_table.parentWidget().findChildren(QPushButton):button.hide()
        self.timer_table.setHeaderLabels(['Name','Enabled','Repeat','Interval','Lines'])
        def menu():
            m=QMenu(self);m.addAction('Add',lambda:self.timer_edit(True))
            doc=self.store.read('timers.json');item=self.timer_table.currentItem();node=next((t for t in doc if item and t['id']==item.data(0,ROLE)),None)
            def save():self.store.save('timers.json',doc);self.populate_timers();self.runtime.submit('reload')
            m.addAction('Edit',lambda:self.timer_edit(False)).setEnabled(node is not None)
            def delete():doc.remove(node);save()
            m.addAction('Delete',delete).setEnabled(node is not None)
            def duplicate():
                clone=renewed(node);clone['name']+=' (Copy)';doc.append(clone);save()
            m.addAction('Duplicate',duplicate).setEnabled(node is not None)
            def toggle():node['enabled']=not node.get('enabled',True);save()
            a=m.addAction('Enabled',toggle);a.setCheckable(True);a.setChecked(node.get('enabled',True) if node else False);a.setEnabled(node is not None)
            m.addAction('Copy Timer ID',lambda:QApplication.clipboard().setText(node['id'])).setEnabled(node is not None)
            return m
        bind(self.timer_table,menu)
        from .app_shortcuts import timers
        timers(self,menu)

    def populate_timers(self):
        self.timer_table.clear()
        self.timer_table.setHeaderLabels(['Name','Enabled','Repeat','Interval','Lines'])
        for timer in self.store.read('timers.json'):
            item=QTreeWidgetItem([timer['name'],'Yes' if timer.get('enabled',True) else 'No','Yes' if timer.get('repeat',True) else 'No',str(timer.get('interval',600)),str(timer.get('lines',0))]);item.setData(0,ROLE,timer['id']);self.timer_table.addTopLevelItem(item)

    def navigate(self,route):
        route={'midiDevices':'midiIn','websocketConnections':'websocketClients'}.get(route,route)
        if route in ('local','openai'):
            self.tabs.setCurrentIndex(self.routes['ai']);self.ai_settings.provider.setCurrentIndex(0 if route=='local' else 1)
        elif route=='diagnostics':self.tabs.setCurrentIndex(self.routes['settings']);self.settings_tabs.setCurrentIndex(1)
        elif route in self.routes:self.tabs.setCurrentIndex(self.routes[route])
        if hasattr(self,'settings_button'):self.settings_button.setChecked(route=='settings')
        item=self.nav_items.get('ai' if route in ('local','openai') else route)
        if item:
            parent=item.parent()
            if parent:parent.setExpanded(True)
            if self.navigation.currentItem()!=item:self.navigation.setCurrentItem(item)

    def card(self,title,placeholder):
        card=QFrame();card.setObjectName('card');layout=QVBoxLayout(card);layout.setContentsMargins(10,10,10,10);layout.setSpacing(8)
        row=QHBoxLayout();label=QLabel(title);label.setObjectName('sectionTitle');row.addWidget(label)
        search=QLineEdit();search.setPlaceholderText(placeholder);row.addWidget(search,1);layout.addLayout(row)
        return card,layout,search,label

    def make_actions(self):
        layout=self.page('Actions');layout.setContentsMargins(12,10,12,12);layout.setSpacing(10)
        title=QLabel('Actions');title.setObjectName('pageTitle');layout.addWidget(title)
        self.split=QSplitter();layout.addWidget(self.split,1)
        self.action_card,al,self.search,self.action_count=self.card('Actions (0)','Filter')
        self.actions=QTreeWidget();self.actions.setHeaderLabels(['Name','Enabled','Options','Triggers','Queue']);self.actions.setIndentation(12)
        self.actions.itemSelectionChanged.connect(self.select_action);self.actions.itemDoubleClicked.connect(self.edit_action);al.addWidget(self.actions);self.split.addWidget(self.action_card)
        right=QSplitter(Qt.Orientation.Vertical)
        self.trigger_card,self.trigger_layout,self.trigger_search,_=self.card('Triggers','Search to add trigger...')
        self.step_card,self.step_layout,self.step_search,_=self.card('Sub-Actions','Search to add sub-action...')
        right.addWidget(self.trigger_card);right.addWidget(self.step_card);right.setSizes([310,420]);self.split.addWidget(right);self.split.setSizes([620,610])
        self.editor=None;self.trigger_view=None;self.step_view=None
        self.empty_triggers=QTreeWidget();self.empty_triggers.setHeaderLabels(['Source','Type','Enabled','Criteria']);self.trigger_layout.addWidget(self.empty_triggers)
        self.empty_steps=QTreeWidget();self.empty_steps.setHeaderHidden(True);self.step_layout.addWidget(self.empty_steps)
        bind(self.empty_triggers,self.no_action_menu);bind(self.empty_steps,self.no_action_menu)
        self.run_input=QLineEdit();self.run_input.hide()
        self.search.textChanged.connect(self.populate_actions)
        self.trigger_search.returnPressed.connect(lambda:self.search_catalog(True));self.step_search.returnPressed.connect(lambda:self.search_catalog(False))
        bind(self.actions,lambda:action_context(self));self.populate_actions()
        from .app_shortcuts import actions as bind_actions
        bind_actions(self)

    def no_action_menu(self):
        from PySide6.QtWidgets import QMenu
        menu=QMenu(self);menu.addAction('Select an action first').setEnabled(False);return menu

    def search_catalog(self,trigger):
        if not self.editor:return
        from PySide6.QtWidgets import QMenu
        text=(self.trigger_search if trigger else self.step_search).text().casefold()
        from .csharp_core_services import catalog as code_catalog
        values=code_catalog(available_triggers(),getattr(self,'code_triggers',[])) if trigger else available_steps()
        catalog={k:v for k,v in values.items() if text in v[0].casefold()}
        menu=QMenu(self);add_catalog(menu,catalog,self.editor.add_trigger if trigger else self.editor.add_step)
        edit=self.trigger_search if trigger else self.step_search;menu.exec(edit.mapToGlobal(edit.rect().bottomLeft()))

    def populate_actions(self):
        current=self.current_action();identity=current['id'] if current else None
        collapsed={self.actions.topLevelItem(i).data(0,ROLE+1) for i in range(self.actions.topLevelItemCount()) if not self.actions.topLevelItem(i).isExpanded()}
        self.actions.blockSignals(True);self.actions.clear();groups={};selected=None;term=self.search.text().casefold()
        for action in self.document['actions']:
            if term and term not in (action['name']+' '+action.get('group','')).casefold():continue
            group=action.get('group') or 'None'
            if group not in groups:
                groups[group]=QTreeWidgetItem([group]);groups[group].setData(0,ROLE+1,group);self.actions.addTopLevelItem(groups[group]);groups[group].setFirstColumnSpanned(True)
                groups[group].setBackground(0,QColor('#373a3a'))
            q=next((q['name'] for q in self.document.get('queues',[]) if q['id']==action.get('queue')),'Default')
            options=' '.join(label for key,label in [('random','RA'),('concurrent','CC'),('excludeHistory','EH')] if action.get(key)) or 'None'
            item=QTreeWidgetItem([action['name'],'Yes' if action.get('enabled',True) else 'No',options,str(len(action['triggers'])),q]);item.setData(0,ROLE,action['id']);groups[group].addChild(item)
            if action['id']==identity:selected=item
        for name,item in groups.items():item.setText(0,f'{name} ({item.childCount()} actions)')
        for name,item in groups.items():item.setExpanded(name not in collapsed)
        self.actions.setColumnWidth(0,220)
        for i,w in enumerate((65,70,60,85),1):self.actions.setColumnWidth(i,w)
        self.action_count.setText(f"Actions ({len(self.document['actions'])})")
        self.actions.blockSignals(False)
        if selected:self.actions.setCurrentItem(selected)
        elif self.actions.topLevelItemCount():self.actions.setCurrentItem(self.actions.topLevelItem(0).child(0))
        else:self.select_action()

    def update_action_rows(self):
        for i in range(self.actions.topLevelItemCount()):
            group=self.actions.topLevelItem(i)
            for j in range(group.childCount()):
                item=group.child(j);action=next((a for a in self.document['actions'] if a['id']==item.data(0,ROLE)),None)
                if action:item.setText(0,action['name']);item.setText(1,'Yes' if action['enabled'] else 'No');item.setText(3,str(len(action['triggers'])))

    def select_action(self):
        if not hasattr(self,'empty_triggers'):return
        if self.editor:
            self.editor.triggers.deleteLater();self.editor.steps.deleteLater();self.editor.deleteLater();self.editor=None
        action=self.current_action();self.empty_triggers.setVisible(action is None);self.empty_steps.setVisible(action is None)
        if action:
            self.editor=InlineEditor(action,self);self.trigger_view=self.editor.triggers;self.step_view=self.editor.steps
        else:self.trigger_view=self.empty_triggers;self.step_view=self.empty_steps

    def add_action(self):
        value=new_action('', '');dialog=ActionProperties(value,self)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            self.document['actions'].append(dialog.value);self.save_actions()
            for i in range(self.actions.topLevelItemCount()):
                group=self.actions.topLevelItem(i)
                for j in range(group.childCount()):
                    if group.child(j).data(0,ROLE)==dialog.value['id']:self.actions.setCurrentItem(group.child(j));return

    def edit_action(self,*_):
        action=self.current_action()
        if not action:return
        dialog=ActionProperties(action,self)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            self.document['actions']=[dialog.value if a['id']==action['id'] else a for a in self.document['actions']];self.save_actions()

    def review_import(self,identity=None):
        action=self.current_action() if identity is None else next((a for a in self.document['actions'] if a['id']==identity),None)
        if not action:return
        from .original_migration_ui import ImportReview
        if ImportReview(self,action['id']).exec()==QDialog.DialogCode.Accepted:
            self.statusBar().showMessage('Import für manuelle Tests freigegeben. Rechtsklick → Test Action; automatische Trigger sind aus.',15000)

    def clone_action(self):
        action=self.current_action()
        if action:
            clone=renewed(action);clone['name']+=' (Copy)';self.document['actions'].append(clone);self.save_actions()

    def delete_action(self):
        identities={item.data(0,ROLE) for item in self.actions.selectedItems()}
        identities.discard(None)
        if not identities:return
        self.document['actions']=[a for a in self.document['actions'] if a['id'] not in identities]
        self.save_actions()

    def save_actions(self,preserve_queue_state=True):
        from .original_bundles import normalize
        normalize(self.document)
        if preserve_queue_state:
            saved=self.store.read('actions.json')
            for key in ('paused','blocking'):
                self.document[key]=saved.get(key,False)
            existing={q['id']:q for q in saved.get('queues',[])}
            for queue in self.document.get('queues',[]):
                if queue['id'] in existing:
                    for key in ('paused','blocking'):queue[key]=existing[queue['id']].get(key,False)
        from .original_resources import commit
        commit(self.store,self.document,lambda:super(NextWindow,self).save_actions())

    def make_queues(self):
        layout=self.page('Queues');title=QLabel('Queues');title.setObjectName('pageTitle');layout.addWidget(title)
        self.queues=QTreeWidget();self.queues.setHeaderLabels(['Name','Pending Count','Completed Count','Paused','Blocking']);layout.addWidget(self.queues)
        bind(self.queues,self.queue_menu);self.populate_queues()

    def populate_queues(self,pending=None,history=None):
        pending=pending or [];history=history or []
        counts=getattr(self,'queue_counts',{})
        item=self.queues.currentItem();selected=item.data(0,ROLE) if item else None;self.queues.clear()
        for queue in [{'id':None,'name':'Default','blocking':self.document.get('blocking',False),'paused':self.document.get('paused',False)},*self.document.get('queues',[])]:
            identity=queue['id'];queue={**queue,**getattr(self,'runtime_queue_states',{}).get(identity,{})};row=QTreeWidgetItem([queue['name'],str(sum(r.get('queueId')==identity for r in pending)),str(counts.get(identity,0)),'Yes' if queue.get('paused') else 'No','Yes' if queue.get('blocking') else 'No']);row.setData(0,ROLE,identity);self.queues.addTopLevelItem(row)
            if identity==selected:self.queues.setCurrentItem(row)
        for i in range(5):self.queues.resizeColumnToContents(i)

    def queue_menu(self):
        from PySide6.QtWidgets import QMenu,QInputDialog
        import uuid
        menu=QMenu(self);item=self.queues.currentItem();identity=item.data(0,ROLE) if item else None;selected=item is not None
        for state in getattr(self,'runtime_queue_states',{}).values():
            target=self.document if state['id'] is None else next((q for q in self.document.get('queues',[]) if q['id']==state['id']),None)
            if target is not None:
                for key in ('paused','blocking'):target[key]=state.get(key,False)
        node=next((q for q in self.document.get('queues',[]) if q['id']==identity),None)
        def save():
            self.runtime_queue_states={};self.save_actions(preserve_queue_state=False);self.populate_queues()
        def add():
            name,ok=QInputDialog.getText(self,'Add Queue','Name')
            if ok and name.strip():self.document.setdefault('queues',[]).append({'id':str(uuid.uuid4()),'name':name.strip(),'blocking':False,'paused':False});save()
        menu.addAction('Add',add)
        def toggle(key):
            value=not effective.get(key,False)
            if node:node[key]=value
            else:self.document[key]=value
            self.runtime_queue_states={}
            save()
        effective=getattr(self,'runtime_queue_states',{}).get(identity,node or self.document)
        paused=effective.get('paused',False)
        menu.addAction('Resume' if paused else 'Pause',lambda:toggle('paused')).setEnabled(selected)
        blocking=menu.addAction('Blocking',lambda:toggle('blocking'));blocking.setCheckable(True);blocking.setChecked(effective.get('blocking',False));blocking.setEnabled(selected)
        menu.addAction('Clear',lambda:self.runtime.submit('queue_clear',id=identity)).setEnabled(selected)
        def pause_all(value):
            self.document['paused']=value
            for q in self.document.get('queues',[]):q['paused']=value
            save()
        menu.addSeparator();menu.addAction('Pause All Queues',lambda:pause_all(True));menu.addAction('Resume All Queues',lambda:pause_all(False))
        return menu

    def export_actions(self):
        path,_=QFileDialog.getSaveFileName(self,'Export Actions','actions-linux.json','Linux JSON (*.json);;Original Action Bundle (*.sb)')
        if not path:return
        try:
            if Path(path).suffix.lower()=='.sb':
                from .original_exchange import export_bundle
                from .core_services import read_config
                resources={'commands':self.store.read('commands.json')['commands'],'timers':self.store.read('timers.json'),'websocketConnections':read_config(self.store.root)['websocketConnections']}
                text=export_bundle(self.document,resources=resources)
            else:text=json.dumps({'format':'streamer-linux-actions-1',**self.document},ensure_ascii=False,indent=2)
            Path(path).write_text(text,encoding='utf-8')
        except (ValueError,OSError) as exc:QMessageBox.warning(self,'Export',str(exc))

    def import_actions(self):
        path,_=QFileDialog.getOpenFileName(self,'Import Actions','','Action Exports (*.json *.sb);;All Files (*)')
        if not path:return
        try:
            from .original_exchange import import_bundle,is_original
            raw=Path(path).read_bytes()
            if Path(path).suffix.lower()=='.sb' or is_original(raw):
                existing_ids={a['id'] for a in self.document['actions']}
                resources={**self.document,'commands':self.store.read('commands.json')['commands'],'timers':self.store.read('timers.json')}
                document,warnings=import_bundle(raw,resources,collision='remap')
                document.pop('commands',None);document.pop('timers',None)
                previous=self.document;self.document=document
                try:self.save_actions()
                except Exception:self.document=previous;raise
                self.populate_commands();self.populate_timers()
                imported=[a['id'] for a in document['actions'] if a['id'] not in existing_ids]
                if len(imported)==1:self.review_import(imported[0]);return
                QMessageBox.information(self,'Originalimport','Importiert und zur Prüfung deaktiviert. Keine Original-Autostart-Action wird ausgeführt.\n\n'+'\n'.join(warnings));return
            doc=json.loads(raw.decode('utf-8-sig'))
            from .original_bundles import merge_native
            self.document=merge_native(self.document,doc)
            self.save_actions()
            if len(doc['actions'])==1 and doc['actions'][0].get('migrationBlock'):self.review_import(doc['actions'][0]['id'])
        except (ValueError,KeyError,TypeError,OSError) as exc:QMessageBox.warning(self,'Import',str(exc))

    def global_context(self):
        from PySide6.QtWidgets import QMenu,QApplication
        menu=QMenu(self);item=self.globals_tree.currentItem();name=item.data(0,ROLE) if item else None
        menu.addAction('Add',lambda:self.edit_global(True));menu.addAction('Edit',lambda:self.edit_global(False)).setEnabled(item is not None)
        menu.addAction('Delete',lambda:self.runtime.submit('global_delete',name=name)).setEnabled(item is not None)
        menu.addAction('Copy Name',lambda:QApplication.clipboard().setText(name)).setEnabled(item is not None)
        menu.addAction('Copy Value',lambda:QApplication.clipboard().setText(json.dumps(self.globals_values[name],ensure_ascii=False))).setEnabled(item is not None)
        return menu

    def edit_global(self,new):
        item=self.globals_tree.currentItem()
        if not new and not item:return
        name='' if new else item.data(0,ROLE);value='' if new else self.globals_values[name]
        dialog=FieldsDialog('Global Variable · valueJson keeps the value type',{'name':name,'valueJson':json.dumps(value,ensure_ascii=False)},self)
        if dialog.exec()!=QDialog.DialogCode.Accepted:return
        try:value=json.loads(dialog.value['valueJson'])
        except ValueError as exc:QMessageBox.warning(self,'Global Variable',str(exc));return
        updated=dialog.value['name'].strip()
        if not updated:return
        if not new and updated!=name:QMessageBox.warning(self,'Global Variable','Vorhandene Variablen behalten ihren Namen. Neue Variable separat anlegen.');return
        self.runtime.submit('global_set',name=updated,value=value)

    def open_logs(self):
        from .diagnostics import log_directory
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        folder=log_directory(self.root);folder.mkdir(parents=True,exist_ok=True);QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def show_globals(self):
        self.runtime.submit('globals')

    def update_viewer_status(self,presence,count):
        state=presence.get('state','waiting');live=presence.get('live',False)
        interval=presence.get('intervalMinutes',5)
        source=(f'Live: Twitch chat users · update every {interval} minute(s).' if live else f'Artificial: users who wrote within the last {interval} minute(s).')
        detail={'preview':'Preview: no live queries.',
                'disabled':'Presence tracking is disabled under Platforms → Twitch → Settings.',
                'error':'Last presence query failed. Check Twitch connection and permissions; retry is automatic.',
                'waiting':'Waiting for the first presence query.' if live else 'No recent chat messages observed yet.',
                'ready':f'{count} chat user(s).'}[state]
        if presence.get('checkedAt'):detail+=' Last checked: '+presence['checkedAt']+'.'
        if not live and state not in ('disabled','preview'):detail+=' Enable Live Update under Platforms → Twitch → Settings to include silent chat users.'
        self.viewer_status.setText(source+' '+detail+' Chat presence is not the stream viewer count. YouTube: only chat authors observed in the last 5 minutes are listed.')

    def on_result(self,kind,value):
        if kind=='globals':
            self.globals_values=value
            if not hasattr(self,'globals_dialog'):
                self.globals_dialog=QDialog(self);self.globals_dialog.setWindowTitle('Global Variables');self.globals_dialog.resize(750,500);layout=QVBoxLayout(self.globals_dialog)
                self.globals_tree=QTreeWidget();self.globals_tree.setHeaderLabels(['Name','Type','Value']);layout.addWidget(self.globals_tree);bind(self.globals_tree,self.global_context)
                self.globals_tree.itemDoubleClicked.connect(lambda *_:self.edit_global(False))
            self.globals_tree.clear()
            for key,val in value.items():
                item=QTreeWidgetItem([key,type(val).__name__,json.dumps(val,ensure_ascii=False,default=str)]);item.setData(0,ROLE,key);self.globals_tree.addTopLevelItem(item)
            self.globals_tree.resizeColumnToContents(0);self.globals_dialog.show();return
        if kind in ('global_set','global_delete'):self.runtime.submit('globals');return
        if kind in ('credits_get','credits_add','credits_reset'):
            self.credits_page.update_credits(value);return
        if kind.startswith('quotes_'):
            self.quotes_page.update_rows(value);return
        if kind in ('remote_status','remote_save'):
            self.remote_page.update_status(value);return
        if kind=='remote_token':
            from PySide6.QtWidgets import QApplication
            QApplication.clipboard().setText(value);self.statusBar().showMessage('Remote-Zugangsschlüssel kopiert');return
        if kind in ('services_token','services_ws_password'):
            from PySide6.QtWidgets import QApplication
            QApplication.clipboard().setText(value);self.statusBar().showMessage('WebSocket-Passwort kopiert' if kind=='services_ws_password' else 'Sitzungstoken kopiert',3000);return
        if kind.startswith('services_') or kind in ('speech_install_model','speech_cancel_model'):
            self.update_voice_indicator(value)
            for page in self.service_pages.values():page.update_status(value,force=kind=='services_save')
            self.credits_page.update_settings(value.get('settings',{}).get('credits',{}),force=kind=='services_save');return
        if kind=='audio_snapshot':
            self.audio_page.update_status(value)
            for page in self.service_pages.values():page.update_audio(value)
            return
        if kind=='status':
            self.update_voice_indicator(value.get('services',{}))
            for page in self.service_pages.values():page.update_status(value.get('services',{}))
            self.credits_page.update_settings(value.get('services',{}).get('settings',{}).get('credits',{}))
            self.audio_page.update_status(value.get('linuxAudio',{}))
            self.remote_status=copy.deepcopy(value.get('streamerModRemote',{}))
            self.streamdeck_status=copy.deepcopy(value.get('streamDeck',{}))
            self.streamdeck_page.update_bridge(self.streamdeck_status)
            self.code_triggers=copy.deepcopy(value.get('codeTriggers',[]))
            timer_states=dict(value.get('timerStates',[]))
            for i in range(self.timer_table.topLevelItemCount()):
                item=self.timer_table.topLevelItem(i);identity=item.data(0,ROLE)
                if identity in timer_states:item.setText(1,'Yes' if timer_states[identity] else 'No')
            for page in self.core_pages.values():
                entries=value.get('coreStates',{}).get(page.section)
                if entries is not None and entries!=getattr(page,'last_runtime_entries',None):
                    page.last_runtime_entries=copy.deepcopy(entries);page.populate(entries)
                page.update_service_status(value.get('connectionStates',{}),value.get('midiOpen',[]),bool(value.get('services',{}).get('live',False)),value.get('midiDiagnostics'))
            states=value.get('commandStates',[])
            if states!=getattr(self,'last_command_states',None):
                self.last_command_states=states;self.populate_commands()
                def update_states(parent):
                    for i in range(parent.childCount()):
                        item=parent.child(i);identity=item.data(0,ROLE)
                        if identity in dict(states):item.setText(2,'Yes' if dict(states)[identity] else 'No')
                        update_states(item)
                update_states(self.command_table.invisibleRootItem())
            accounts=value.get('twitchAccounts',{})
            self.twitch_page.update_accounts(accounts)
            broadcaster=accounts.get(False,{}).get('state')=='valid';bot=accounts.get(True,{}).get('state')=='valid'
            account_text='Broadcaster '+('angemeldet' if broadcaster else 'nicht bestätigt')+' / Bot '+('angemeldet' if bot else 'nicht bestätigt')
            events_text=value['twitch'] if value.get('twitchEventsActive') else 'EventSub im Testmodus pausiert'
            self.statusBar().showMessage(f"{self.mode_label} | OBS: {value['obs']} | Twitch: {account_text} · {events_text} | YouTube: {value.get('youtube',{}).get('state','disconnected')}")
            self.update_viewer_status(value.get('viewerPresence',{}),len(value.get('viewers',[])))
            self.youtube_page.update_status(value.get('youtube',{}))
            self.viewer_table.clear()
            for viewer in value.get('viewers',[]):self.viewer_table.addTopLevelItem(QTreeWidgetItem([viewer['name'],viewer['login'],viewer['platform'],', '.join(viewer['roles']),viewer['lastActive']]))
            self.event_table.clear()
            for event in reversed(value.get('events',[])):
                item=QTreeWidgetItem([event['time'],event['platform'],event['type'],event['user']]);item.setData(0,ROLE,event['id']);self.event_table.addTopLevelItem(item)
            self.home_status.clear()
            for label,result in [('Mode',self.mode_label),('OBS',value['obs']),('Twitch accounts',account_text),('Twitch EventSub',events_text),('Actions',len(self.document['actions'])),('Pending',len(value.get('pending',[]))),('Running',len(value.get('running',[]))),('History entries',len(value['history']))]:self.home_status.addTopLevelItem(QTreeWidgetItem([label,str(result)]))
            self.history_page.update_records(value['history']);self.pending_page.update_records(value.get('pending',[]))
            self.runtime_queue_states={q['id']:q for q in value.get('queueStates',[])}
            self.queue_counts=value.get('queueCounts',{})
            self.populate_queues(value.get('pending',[]),value['history'])
            self.log.setPlainText(json.dumps(value['effects'],ensure_ascii=False,indent=2))
            self.chat_dialog.update_messages(value['chat'])
            self.connection_status.setText(f"OBS: {value['obs']} | {self.mode_label} ●")
            self.populate_obs_connections(value.get('obsConnections',value['obs']))
            self.twitch_page.rewards_page.subscription_states(value.get('twitchSubscriptionStates',{}))
            for page in self.twitch_page.vote_pages.values():page.subscription_states(value.get('twitchSubscriptionStates',{}))
            self.twitch_page.sub_counter_page.states(value.get('twitchSubscriptionStates',{}))
            self.twitch_page.pyramids_page.observed(value.get('twitchPyramidCurrent',{}),value.get('twitchEventsActive',False))
        elif kind in ('twitch_validate','twitch_login','twitch_login_poll','twitch_login_cancel','twitch_forget'):self.twitch_page.auth_result(value)
        elif kind.startswith('twitch_reward'):pass # RewardsPage handles correlated responses.
        elif kind=='camera_preview':super().on_result(kind,value)
        elif kind=='obs_info':self.obs_details.setText('OBS '+str(value.get('obsVersion','—'))+' · WebSocket '+str(value.get('obsWebSocketVersion','—')))
        elif kind in ('obs_connect','obs_disconnect','obs_force'):self.populate_obs_connections(value.get('obsConnections'))
        elif kind in ('run','test_trigger'):self.statusBar().showMessage('Action completed',5000)


def main():
    parser=argparse.ArgumentParser(description='Separate native Linux edition')
    base=Path(__file__).resolve().parents[1]
    parser.add_argument('--root',type=Path,default=base/'next-studio')
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--live',action='store_true')
    mode.add_argument('--preview',action='store_true',help='Vorschau ohne externe Schreibzugriffe')
    mode.add_argument('--obs-test',action='store_true')
    parser.add_argument('--allow-idle',action='store_true');parser.add_argument('--screenshot',type=Path)
    parser.add_argument('--page',choices=['actions','twitch','youtube','ai','history','queues','pointDefinitions','knownUsers','streamdeck','audio','credits','process','quotes','voiceSettings','voiceCommands','voiceLog','websocket','http','udp','websocketServers','websocketClients','midiIn','midiOut','fileWatchers','fileTails','timers'],default='actions')
    args=parser.parse_args()
    if args.live and args.obs_test:parser.error('Nur einen Betriebsmodus auswählen')
    args.root=args.root.resolve()
    (args.root/'state').mkdir(parents=True,exist_ok=True)
    app=QApplication(sys.argv[:1]);configure_branding(app);app.setStyle('Fusion')
    lock=QLockFile(str(args.root/'state/desktop.lock'))
    if not lock.tryLock(0):QMessageBox.information(None,NAME,'Diese Version ist bereits geöffnet.');return
    from .project_backup import recovery
    try:
        recovery(args.root);initialize(args.root,base)
    except Exception as exc:
        QMessageBox.critical(None,'Projekt konnte nicht geöffnet werden',str(exc));lock.unlock();return
    from .original_style import STYLE,set_palette
    set_palette(app);app.setStyleSheet(STYLE)
    window=NextWindow(args.root,args.live,args.obs_test);window.show()
    window.navigate(args.page)
    if sys.platform=='linux' and not args.allow_idle:
        keeper=subprocess.Popen(['/usr/bin/python3',str(Path(__file__).with_name('keepawake.py')),'--watch-pid',str(os.getpid())])
        app.aboutToQuit.connect(keeper.terminate)
    if args.screenshot:QTimer.singleShot(1500,lambda:window.grab().save(str(args.screenshot)))
    result=app.exec()
    if result==42:
        lock.unlock()
        os.execv(sys.executable,[sys.executable,'-m','sorgobot.next_desktop',*sys.argv[1:]])
    sys.exit(result)

if __name__=='__main__':main()
