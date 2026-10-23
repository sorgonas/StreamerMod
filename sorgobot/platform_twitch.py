"""Native Twitch account login and platform behavior settings."""
from PySide6.QtCore import QTimer,QUrl,Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QTabWidget,QGroupBox,QLabel,
                              QPushButton,QTreeWidget,QTreeWidgetItem,QFormLayout,QLineEdit,QDialog,
                              QDialogButtonBox,QSpinBox,QMessageBox)

class TwitchPage(QWidget):
    def __init__(self,host):
        super().__init__();self.host=host;self.login_buttons={};self.forget_buttons={};self.account_labels={};self.connect_buttons={};self.login_states={};self.polling={};self.timers={};self.account_status={}
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);self.tabs=QTabWidget();layout.addWidget(self.tabs)
        accounts=QWidget();accounts_layout=QVBoxLayout(accounts);row=QHBoxLayout();accounts_layout.addLayout(row);accounts_layout.addStretch()
        for bot,title in [(False,'Broadcaster Account'),(True,'Bot Account')]:
            box=QGroupBox(title);box.setMinimumHeight(210);bl=QVBoxLayout(box);label=QLabel('<not logged in>');self.account_labels[bot]=label;bl.addWidget(label)
            buttons=QHBoxLayout();login=QPushButton('Login');login.clicked.connect(lambda checked=False,b=bot:self.login(b));self.login_buttons[bot]=login;buttons.addWidget(login)
            forget=QPushButton('Forget');forget.clicked.connect(lambda checked=False,b=bot:host.runtime.submit('twitch_forget',bot=b));self.forget_buttons[bot]=forget;buttons.addWidget(forget);bl.addLayout(buttons)
            validate=QPushButton('Validate account');validate.clicked.connect(lambda checked=False,b=bot:self.validate_account(b));self.connect_buttons[bot]=validate;bl.addWidget(validate)
            state=QLabel('');state.setWordWrap(True);self.login_states[bot]=state;bl.addWidget(state);bl.addStretch();row.addWidget(box)
            timer=QTimer(self);timer.timeout.connect(lambda b=bot:self.poll(b));self.timers[bot]=timer;self.polling[bot]=False
        setup=QPushButton('Application Setup…');setup.clicked.connect(self.configure_application);accounts_layout.addWidget(setup)
        self.application_note=QLabel('');self.application_note.setWordWrap(True);accounts_layout.addWidget(self.application_note)
        self.full_access=QPushButton('Alle eingebauten Twitch-Funktionen freigeben (Broadcaster)');self.full_access.clicked.connect(lambda:self.login(False));accounts_layout.addWidget(self.full_access)
        self.permission_note=QLabel('');self.permission_note.setWordWrap(True);accounts_layout.addWidget(self.permission_note)
        help_box=QGroupBox('Erste Einrichtung: Noch keine eigene Twitch-Anwendung?');help_layout=QVBoxLayout(help_box)
        self.setup_help=QLabel(
            '<ol>'
            '<li>Die <a style="color:#c87cd5" href="https://dev.twitch.tv/console/apps">Twitch-Entwicklerkonsole</a> öffnen und <b>Register Your Application</b> wählen.</li>'
            '<li>Einen eindeutigen Namen vergeben, z. B. <b>Meine StreamerMod-Anwendung</b>. Als OAuth Redirect URL <code>http://localhost</code> hinzufügen. Unser Device-Anmeldefluss verwendet diese Adresse nicht.</li>'
            '<li>Kategorie <b>Chat Bot</b> und Client-Typ <b>Public</b> auswählen, dann die Anwendung erstellen.</li>'
            '<li>Unter <b>Manage</b> die <b>Client ID</b> kopieren und oben über <b>Application Setup</b> eintragen. Ein Client Secret ist nicht erforderlich.</li>'
            '<li>Mit <b>Login</b> zuerst das Broadcaster-Konto und bei Bedarf das Bot-Konto verbinden; jeweils die Freigabe im Browser bestätigen.</li>'
            '</ol>'
            'Twitch verlangt eine bestätigte E-Mail-Adresse und aktivierte Zwei-Faktor-Anmeldung. '
            '<a style="color:#c87cd5" href="https://dev.twitch.tv/docs/authentication/register-app/">Offizielle Registrierungsanleitung</a>'
        );self.setup_help.setWordWrap(True);self.setup_help.setOpenExternalLinks(True)
        self.setup_help.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        help_layout.addWidget(self.setup_help);accounts_layout.addWidget(help_box)
        accounts_layout.addWidget(QLabel('Bot Account ist optional. Beim Bot-Login im Browser das gewünschte Bot-Konto wählen.'))
        self.tabs.addTab(accounts,'Accounts')
        from .twitch_rewards_ui import RewardsPage
        self.rewards_page=RewardsPage(host);self.rewards=self.rewards_page.table;self.tabs.addTab(self.rewards_page,'Channel Point Rewards')
        from .twitch_votes_ui import VotesPage
        self.vote_pages={}
        for kind,title in [('polls','Polls'),('predictions','Predictions')]:
            page=VotesPage(host,kind);self.vote_pages[kind]=page;self.tabs.addTab(page,title)
        from .twitch_pyramids_ui import PyramidsPage
        self.pyramids_page=PyramidsPage(host);self.tabs.addTab(self.pyramids_page,'Pyramids')
        from .twitch_settings import TwitchSettings
        self.settings=TwitchSettings(host);self.first_hours=self.settings.first_hours;self.tabs.addTab(self.settings,'Settings')
        from .twitch_sub_counter_ui import SubCounterPage
        self.sub_counter_page=SubCounterPage(host)
        settings_layout=self.settings.widget().layout()
        settings_layout.insertWidget(settings_layout.count()-1,self.sub_counter_page)
        self.refresh()

    def refresh(self):
        cfg=self.host.store.read('local.json')
        self.render_accounts(cfg)
        self.settings.refresh();self.pyramids_page.settings_refresh()
        from .twitch_auth import missing_permissions,FEATURE_SCOPES,FEATURE_LABELS,PLANNED_SCOPES,PLANNED_LABELS
        from .twitch_rewards import scopes
        missing=missing_permissions(cfg);granted=scopes(cfg)
        groups=[FEATURE_LABELS[k] for k,v in FEATURE_SCOPES.items() if v-granted]+[PLANNED_LABELS[k] for k,v in PLANNED_SCOPES.items() if v-granted]
        self.full_access.setEnabled(bool(missing))
        self.permission_note.setText(('Gemeinsame Freigabe für eingebaute und angekündigte Twitch-Funktionen. Noch fehlend: '+', '.join(groups)+'.' if groups else 'Noch fehlende Rechte für Grundfunktionen.' if missing else 'Alle Rechte des gemeinsamen Twitch-Pakets vorhanden.')+' Der normale Broadcaster-Login und jeder Grant-Access-Knopf fordern dasselbe Gesamtpaket an. Anmeldung im Browser mit dem Broadcaster-Konto bestätigen.')
        client=cfg.get('twitch_client_id','');self.application_note.setText('Eigene Twitch-Anwendung: '+('Client-ID eingerichtet' if client and client not in ('Sorgonas','Sorgobot') else 'Client-ID fehlt – einmalig über Application Setup einrichten.'))

    def update_accounts(self,accounts):
        self.account_status=accounts;self.render_accounts(self.host.store.read('local.json'))

    def render_accounts(self,cfg):
        for bot in (False,True):
            login=cfg.get('twitch_bot_login' if bot else 'twitch_login','');token=cfg.get('twitch_bot_token' if bot else 'twitch_token')
            status=self.account_status.get(bot,{});valid=bool(token and status.get('state')=='valid')
            label=login or '<not logged in>'
            self.account_labels[bot].setText(label+(' · authenticated' if valid else ' · checking…' if token and status.get('state')=='checking' else ' · not validated' if token else ''))
            self.connect_buttons[bot].setEnabled(not valid);self.connect_buttons[bot].setToolTip('Konto bereits automatisch bestätigt.' if valid else 'Gespeicherte Anmeldung prüfen.' if token else 'Konto zuerst über Twitch anmelden.')
            self.forget_buttons[bot].setEnabled(bool(token))
            if not self.timers[bot].isActive() and self.login_buttons[bot].isEnabled():
                self.login_states[bot].setText('Angemeldet.' if valid else status.get('message',''))

    def validate_account(self,bot):
        cfg=self.host.store.read('local.json')
        if cfg.get('twitch_bot_token' if bot else 'twitch_token'):self.host.runtime.submit('twitch_validate',bot=bot)
        else:self.login(bot)

    def configure_application(self):
        if any(t.isActive() for t in self.timers.values()) or any(not b.isEnabled() for b in self.login_buttons.values()):
            QMessageBox.information(self,'Application Setup','Bitte die laufende Anmeldung zuerst abschließen oder abbrechen.');return False
        cfg=self.host.store.read('local.json');dialog=QDialog(self);dialog.setWindowTitle('Twitch Application Setup');dialog.resize(640,240);layout=QVBoxLayout(dialog)
        note=QLabel('Diese Linux-Anwendung benötigt eine eigene registrierte Twitch-Anwendung vom Typ Public.\nDie Client-ID ist keine Kontoanmeldung. Danach verbindet Login das gewünschte Konto im Browser.\nKein Client Secret erforderlich.');note.setWordWrap(True);layout.addWidget(note)
        form=QFormLayout();client=QLineEdit(cfg.get('twitch_client_id',''));form.addRow('Client ID',client);layout.addLayout(form)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);layout.addWidget(buttons)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            cfg=self.host.store.read('local.json');value=client.text().strip()
            if not value or value in ('Sorgonas','Sorgobot'):QMessageBox.warning(self,'Client ID','Bitte die Client-ID einer registrierten Public-Anwendung eintragen.');return False
            if value!=cfg.get('twitch_client_id') and any(cfg.get(k) for k in ('twitch_token','twitch_bot_token')):
                QMessageBox.warning(self,'Client ID','Zuerst beide vorhandenen Konten über Forget abmelden, bevor die Client-ID geändert wird.');return False
            self.host.store.update('local.json',{'twitch_client_id':value});self.host.runtime.submit('reload');self.refresh();return True
        return False

    def login(self,bot,features=None):
        if not self.host.runtime.booted:
            self.login_states[bot].setText('Programm startet noch. Bitte kurz warten.');return
        if self.timers[bot].isActive():
            self.timers[bot].stop();self.host.runtime.submit('twitch_login_cancel',bot=bot);return
        cfg=self.host.store.read('local.json')
        if not cfg.get('twitch_client_id') or cfg['twitch_client_id'] in ('Sorgonas','Sorgobot'):
            if not self.configure_application():return
        self.login_buttons[bot].setEnabled(False);self.login_states[bot].setText('Bot-Anmeldung wird vorbereitet…' if bot else 'Gemeinsame Freigabe für alle eingebauten Twitch-Funktionen wird vorbereitet…');self.host.runtime.submit('twitch_login',bot=bot,features=features or [])

    def poll(self,bot):
        if self.polling[bot]:return
        self.polling[bot]=True;self.host.runtime.submit('twitch_login_poll',bot=bot)

    def auth_result(self,result):
        bot=result['bot'];state=result.get('state','connected');self.polling[bot]=False;self.login_buttons[bot].setEnabled(True)
        if state=='pending':
            self.login_buttons[bot].setText('Cancel Login');self.timers[bot].start(int(result['interval'])*1000)
            if 'url' in result:
                self.login_states[bot].setText('Im Browser Twitch bestätigen. Code: '+result['code'])
                if not QDesktopServices.openUrl(QUrl(result['url'])):
                    self.login_states[bot].setText('Browser konnte nicht geöffnet werden.\n'+result['url']);self.login_states[bot].setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            return
        self.timers[bot].stop();self.login_buttons[bot].setText('Login')
        if state=='connected':self.account_status[bot]={'state':'valid'}
        elif state=='forgotten':self.account_status[bot]={'state':'disconnected'}
        self.refresh()
        if state=='error':self.login_states[bot].setText(result['message'])
        elif state in ('cancelled','forgotten'):self.login_states[bot].setText('Anmeldung abgebrochen.' if state=='cancelled' else '')
        else:
            self.account_labels[bot].setText(result['login']+' · authenticated')
            self.login_states[bot].setText('Angemeldet. Chat / EventSub wird im Live-Modus verbunden.' if not bot else 'Angemeldet für ausgehende Nachrichten.')

    def validated(self,result):self.auth_result(result)

    def show_rewards(self,result):self.rewards_page.show_rewards(result)
