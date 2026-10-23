"""Provider-bound model inventories; a local URL is not proof of local installation."""
import json
from PySide6.QtCore import QUrl
from PySide6.QtNetwork import QNetworkAccessManager,QNetworkRequest,QNetworkReply
from PySide6.QtWidgets import QWidget,QVBoxLayout,QFormLayout,QStackedWidget,QComboBox,QLineEdit,QPushButton,QLabel,QCheckBox
from .ai_models import context,requests,inventory,identity,openai_chat,InventoryError

class AISettings(QWidget):
    def __init__(self,config,parent=None):
        super().__init__(parent);self.fields={};self.model_lists={};self.vision_lists={};self.sources={};self.pending={};self.network=QNetworkAccessManager(self)
        for provider in ('local','openai'):
            saved=config.get(provider+'_models_source',{})
            try:valid=isinstance(saved,dict) and saved.get('context')==context(provider,config)
            except ValueError:valid=False
            values=config.get(provider+'_available_models',[]) if valid else []
            self.model_lists[provider]=sorted({identity(m) for m in values if identity(m) and (provider!='openai' or openai_chat(m))}) if isinstance(values,list) else []
            vision=config.get(provider+'_available_vision_models',[]) if valid else []
            self.vision_lists[provider]=sorted({m for m in vision if m in self.model_lists[provider]}) if isinstance(vision,list) else []
            if valid:self.sources[provider]=saved
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);form=QFormLayout();self.provider=QComboBox();self.provider.addItem('Lokaler KI-Server','local');self.provider.addItem('OpenAI API (GPT)','openai');form.addRow('Anbieter',self.provider);layout.addLayout(form)
        self.pages=QStackedWidget();self.model_buttons={};self.messages={}
        for provider,fields in (('local',[('llm_url','Adresse des KI-Diensts'),('llm_key','Lokaler API-Schlüssel'),('llm_model','Modell'),('vision_model','Bildmodell')]),('openai',[('openai_key','OpenAI API-Schlüssel'),('openai_model','Modell')])):
            page=QWidget();rows=QFormLayout(page)
            for key,label in fields:
                if key.endswith('model'):
                    edit=QComboBox();edit.setEditable(True);edit.setInsertPolicy(QComboBox.InsertPolicy.NoInsert);edit.addItems(self.vision_lists[provider] if key=='vision_model' else self.model_lists[provider]);edit.setCurrentText(str(config.get(key,'')));edit.setToolTip('Modell aus dem ermittelten Bestand auswählen oder eine eigene Modell-ID eingeben. Eine manuelle ID wird nicht zur Bestandsliste hinzugefügt.')
                else:
                    edit=QLineEdit(str(config.get(key,'')))
                    if key.endswith('_key'):edit.setEchoMode(QLineEdit.EchoMode.Password)
                self.fields[key]=edit;rows.addRow(label,edit)
            button=QPushButton('Modelle laden');button.clicked.connect(lambda checked=False,p=provider:self.load_models(p));self.model_buttons[provider]=button;rows.addRow('',button)
            message=QLabel('Zuletzt ermittelte Modelle. „Modelle laden“ aktualisiert den Bestand.' if provider in self.sources else 'Modelle beim ausgewählten Anbieter laden. Die gespeicherte Modell-ID bleibt erhalten.');message.setWordWrap(True);rows.addRow('',message);self.messages[provider]=message
            if provider=='local':
                self.bridge=QCheckBox('Bestehende Viewer-Memory-/Summary-Bridge verwenden');self.bridge.setChecked(config.get('bridge_enabled',True));rows.addRow('',self.bridge)
                hint=QLabel('Die Liste zeigt den installierten Bestand des lokalen Modellservers. Ein Cloud-Angebotskatalog einer vorgeschalteten Bridge wird nicht übernommen.')
            else:hint=QLabel('Die Liste zeigt die Chat-/Textmodelle, die dein OpenAI-API-Konto meldet. Sprach-, Bild-, Embedding- und andere Spezialmodelle werden ausgeblendet.')
            hint.setWordWrap(True);rows.addRow('',hint);self.pages.addWidget(page)
        layout.addWidget(self.pages);self.provider.currentIndexChanged.connect(self.pages.setCurrentIndex);self.provider.setCurrentIndex(max(0,self.provider.findData(config.get('ai_provider','local'))));self.pages.setCurrentIndex(self.provider.currentIndex())
        for key in ('llm_url','llm_key','openai_key'):self.fields[key].textChanged.connect(lambda text,k=key:self.source_changed('openai' if k=='openai_key' else 'local'))

    def values(self):
        values={key:widget.currentText() if isinstance(widget,QComboBox) else widget.text() for key,widget in self.fields.items()};values.update(ai_provider=self.provider.currentData(),bridge_enabled=self.bridge.isChecked())
        for provider in ('local','openai'):
            values[provider+'_available_models']=list(self.model_lists[provider]);values[provider+'_available_vision_models']=list(self.vision_lists[provider]);values[provider+'_models_source']=dict(self.sources.get(provider,{}))
        return values

    def replace_models(self,provider,chat,vision):
        self.model_lists[provider]=list(chat);self.vision_lists[provider]=list(vision)
        for key in (('llm_model','vision_model') if provider=='local' else ('openai_model',)):
            combo=self.fields[key];selected=combo.currentText();combo.blockSignals(True);combo.clear();combo.addItems(vision if key=='vision_model' else chat);combo.setCurrentText(selected);combo.blockSignals(False)

    def source_changed(self,provider):
        state=self.pending.pop(provider,None);self.sources.pop(provider,None);self.replace_models(provider,[],[]);self.model_buttons[provider].setEnabled(True)
        if state and state.get('reply'):state['reply'].abort()
        self.messages[provider].setText('Adresse oder Schlüssel geändert. Modelle für diese Verbindung neu laden.')

    def load_models(self,provider):
        if provider in self.pending:return
        values=self.values();key=values['openai_key' if provider=='openai' else 'llm_key'].strip()
        try:
            if provider not in ('local','openai'):raise InventoryError('Unbekannter KI-Anbieter.')
            if provider=='openai' and not key:raise InventoryError('Bitte zuerst den OpenAI API-Schlüssel eingeben.')
            plan=requests(provider,values);fingerprint=context(provider,values)
        except ValueError as exc:self.fail(provider,str(exc));return
        state={'plan':plan,'index':0,'context':fingerprint,'key':key};self.pending[provider]=state;self.model_buttons[provider].setEnabled(False);self.messages[provider].setText('Installierte Modelle werden ermittelt …' if provider=='local' else 'OpenAI-Chatmodelle werden geladen …');self.next_request(provider,state)

    def next_request(self,provider,state):
        url,kind=state['plan'][state['index']];state['kind']=kind;state['index']+=1
        request=QNetworkRequest(QUrl(url));request.setTransferTimeout(10000);request.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,QNetworkRequest.RedirectPolicy.ManualRedirectPolicy)
        if state['key']:request.setRawHeader(b'Authorization',('Bearer '+state['key']).encode())
        if provider=='local':request.setRawHeader(b'X-Streamer-Provider',b'local')
        reply=self.network.get(request);state['reply']=reply;reply.downloadProgress.connect(lambda received,total:reply.abort() if received>4*1024*1024 else None);reply.finished.connect(lambda:self.models_finished(provider,reply,state))

    def fail(self,provider,message):
        self.sources.pop(provider,None);self.replace_models(provider,[],[]);self.messages[provider].setText(message+' Die gespeicherte Modell-ID bleibt erhalten.');self.model_buttons[provider].setEnabled(True)

    def models_finished(self,provider,reply,expected=None):
        if expected is not None and (self.pending.get(provider) is not expected or expected.get('reply') is not reply):reply.deleteLater();return
        state=self.pending.get(provider);continued=False
        try:
            if state and state['context']!=context(provider,self.values()):return
            status=reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
            if state and status in (404,405) and state['index']<len(state['plan']):
                continued=True;self.next_request(provider,state);return
            if reply.error()!=QNetworkReply.NetworkError.NoError or status!=200:
                raise InventoryError('Modellabruf fehlgeschlagen'+(' (HTTP '+str(status)+')' if status else '')+'. Adresse, Schlüssel und Verbindung prüfen.')
            raw=bytes(reply.readAll())
            if len(raw)>4*1024*1024:raise InventoryError('Die Modellantwort ist zu groß.')
            payload=json.loads(raw);kind=state['kind'] if state else 'openai' if provider=='openai' else 'compatible'
            server=bytes(reply.rawHeader('Server')).decode('ascii','ignore') if hasattr(reply,'rawHeader') else ''
            found=inventory(payload,kind,server);self.replace_models(provider,found['chat'],found['vision']);self.sources[provider]={'context':context(provider,self.values()),'source':found['source'],'visionKnown':found['visionKnown']}
            message=str(len(found['chat']))+(' installierte lokale Chatmodelle' if provider=='local' else ' OpenAI-Chatmodelle')+' ermittelt.'
            selected=self.fields['llm_model' if provider=='local' else 'openai_model'].currentText()
            if selected and selected not in found['chat']:message+=' Die gespeicherte Modell-ID ist nicht in dieser Liste enthalten.'
            if provider=='local' and not found['visionKnown']:message+=' Der Server meldet keine vollständigen Bildfähigkeiten; die Bildmodell-Liste enthält dann auch ungeprüfte installierte Modelle.'
            self.messages[provider].setText(message+' Mit „KI-Einstellungen speichern“ sichern.')
        except (ValueError,KeyError,TypeError) as error:
            self.fail(provider,str(error) if isinstance(error,InventoryError) else 'Der Dienst liefert keine gültige Modellliste.')
        finally:
            if not continued and (not state or self.pending.get(provider) is state):self.pending.pop(provider,None);self.model_buttons[provider].setEnabled(True)
            reply.deleteLater()
