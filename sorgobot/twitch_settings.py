"""Twitch settings cards based on the supplied original screenshot."""
from PySide6.QtCore import Qt,QSize,QRectF
from PySide6.QtGui import QPainter,QColor
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QToolButton,QCheckBox,QSpinBox,QSlider,QPushButton,QScrollArea,QFrame

DEFAULTS={'twitch_emotes_bttv':True,'twitch_emotes_7tv':True,'twitch_emotes_ffz':True,'first_words_reset_hours':12,'twitch_present_viewers':True,'twitch_viewers_live':False,'twitch_viewers_interval':5,'twitch_ignore_gift_bombs':True,'twitch_pyramids':False,'twitch_pyramids_shared':False,'twitch_pyramids_minimum':2,'twitch_update_on_connect':False}

class Toggle(QCheckBox):
    def sizeHint(self):return QSize(self.fontMetrics().horizontalAdvance(self.text())+54,28)
    def hitButton(self,position):return self.rect().contains(position)
    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor('#eceeee'));painter.drawText(self.rect().adjusted(0,0,-50,0),Qt.AlignmentFlag.AlignVCenter|Qt.AlignmentFlag.AlignRight,self.text())
        track=QRectF(self.width()-40,(self.height()-20)/2,40,20)
        painter.setPen(QColor('#b65bc6') if self.isChecked() else QColor('#a7a0ac'));painter.setBrush(QColor('#b65bc6') if self.isChecked() else QColor('#39363e'));painter.drawRoundedRect(track,10,10)
        painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(QColor('#151419') if self.isChecked() else QColor('#c7c4ca'));painter.drawEllipse(QRectF(track.x()+(23 if self.isChecked() else 3),track.y()+3,14,14))
        if self.hasFocus():painter.setPen(QColor('#eceeee'));painter.setBrush(Qt.BrushStyle.NoBrush);painter.drawRoundedRect(track.adjusted(-2,-2,2,2),11,11)

class TwitchSettings(QScrollArea):
    def __init__(self,host):
        super().__init__();self.host=host;self.controls={};self.setWidgetResizable(True);self.setFrameShape(QFrame.Shape.NoFrame)
        container=QWidget();self.setWidget(container);layout=QVBoxLayout(container);layout.setContentsMargins(0,0,0,0);layout.setSpacing(6)
        container.setStyleSheet('QFrame#twitchSection {background:#302e35;border-radius:3px;} QFrame#twitchRow {background:#3b3841;border-radius:3px;} QWidget#twitchSectionBody,QWidget#twitchInterval {background:transparent;} QLabel {background:transparent;} QToolButton#sectionToggle {background:transparent;border:0;} QSpinBox {background:#504b55;border:0;border-radius:3px;padding:5px;min-width:125px;} QSlider::groove:horizontal {background:#a29da5;height:4px;} QSlider::handle:horizontal {background:#b65bc6;width:12px;margin:-4px 0;border-radius:6px;}')
        def header(title,description,enabled=None):
            section=QFrame();section.setObjectName('twitchSection');outer=QVBoxLayout(section);top=QHBoxLayout();outer.addLayout(top)
            text=QLabel('<b>'+title+'</b><br>'+description);text.setWordWrap(True);top.addWidget(text,1)
            if enabled:top.addWidget(self.toggle(enabled,'Ignored' if enabled=='twitch_ignore_gift_bombs' else 'Enabled','Enabled' if enabled=='twitch_ignore_gift_bombs' else 'Disabled'))
            body=QWidget();body.setObjectName('twitchSectionBody');bodylayout=QVBoxLayout(body);bodylayout.setContentsMargins(5,6,5,5);outer.addWidget(body)
            arrow=QToolButton();arrow.setObjectName('sectionToggle');arrow.setCheckable(True);arrow.setChecked(True);arrow.setArrowType(Qt.ArrowType.UpArrow);top.addWidget(arrow)
            def expand(checked):body.setVisible(checked);arrow.setArrowType(Qt.ArrowType.UpArrow if checked else Qt.ArrowType.DownArrow)
            arrow.toggled.connect(expand);layout.addWidget(section);return bodylayout
        def row(target,title,description,control):
            card=QFrame();card.setObjectName('twitchRow');line=QHBoxLayout(card);line.setContentsMargins(16,10,16,10);label=QLabel('<b>'+title+'</b><br>'+description);label.setWordWrap(True);line.addWidget(label,1);line.addWidget(control);target.addWidget(card)
        emotes=header('Emote Handlers','Configure third party emote handling')
        for title,provider,key in [('BetterTTV','BetterTTV','twitch_emotes_bttv'),('SevenTV','Seven TV','twitch_emotes_7tv'),('FrankerFaceZ','FrankerFaceZ','twitch_emotes_ffz')]:row(emotes,title,'Whether to handle '+provider+' emotes',self.toggle(key))
        first=header('First Words','Configure the first words cache')
        self.first_hours=self.number('first_words_reset_hours',0,8760,' hours');row(first,'Auto Reset Cache','Clear the cache on startup if the time since last startup exceeds the given interval',self.first_hours)
        reset=QPushButton('↻ Reset');reset.clicked.connect(lambda:host.runtime.submit('first_words_reset'));row(first,'Reset','Manually reset the cache',reset)
        viewers=header('Present Viewers','Keep track of active viewers in chat','twitch_present_viewers');row(viewers,'Live Update','Whether or not to use realtime data from Twitch, or artificial data',self.toggle('twitch_viewers_live','Live','Artificial'))
        interval=QWidget();interval.setObjectName('twitchInterval');interval.setMinimumWidth(150);il=QVBoxLayout(interval);self.interval_label=QLabel('');self.interval_label.setWordWrap(True);il.addWidget(self.interval_label);slider=QSlider(Qt.Orientation.Horizontal);slider.setRange(1,10);slider.setTickPosition(QSlider.TickPosition.TicksBelow);slider.setTickInterval(1);il.addWidget(slider);self.controls['twitch_viewers_interval']=slider;slider.valueChanged.connect(lambda value:self.update_interval_label());row(viewers,'Update Interval','Defaults to 5 minutes to balance accuracy and performance',interval)
        gifts=header('Gift Bombs','Whether or not to ignore Gift Subs from Gift Bombs','twitch_ignore_gift_bombs')
        # Gift Bombs and Stream Update have no expandable detail rows in the reference.
        section=layout.itemAt(layout.count()-1).widget();section.findChild(QToolButton).hide();gifts.parentWidget().hide()
        pyramids=header('Pyramids','Keep track of users that create pyramids in your chat','twitch_pyramids');row(pyramids,'Shared Chat Participation','Whether or not shared chat will be able to participate in creating/breaking Pyramids',self.toggle('twitch_pyramids_shared'))
        row(pyramids,'Minimum Width','The minimum number of emotes required before starting to track a pyramid',self.number('twitch_pyramids_minimum',2,100,' emotes'))
        empty=header('Stream Update on Connect','Automatically run the Stream Update trigger when connecting to Twitch','twitch_update_on_connect');section=layout.itemAt(layout.count()-1).widget();section.findChild(QToolButton).hide();empty.parentWidget().hide();layout.addStretch()
        self.refresh()
        for control in self.controls.values():
            (control.toggled if isinstance(control,QCheckBox) else control.valueChanged).connect(self.save)

    def toggle(self,key,on='Enabled',off='Disabled'):
        control=Toggle();control.toggled.connect(lambda state:control.setText(on if state else off));self.controls[key]=control;return control
    def number(self,key,minimum,maximum,suffix):
        control=QSpinBox();control.setRange(minimum,maximum);control.setSuffix(suffix);self.controls[key]=control;return control
    def refresh(self):
        cfg=self.host.store.read('local.json')
        for key,control in self.controls.items():
            control.blockSignals(True)
            if isinstance(control,QCheckBox):
                control.setChecked(bool(cfg.get(key,DEFAULTS[key])));control.setText(('Live' if control.isChecked() else 'Artificial') if key=='twitch_viewers_live' else ('Ignored' if control.isChecked() else 'Enabled') if key=='twitch_ignore_gift_bombs' else 'Enabled' if control.isChecked() else 'Disabled')
            else:control.setValue(int(cfg.get(key,DEFAULTS[key])))
            control.blockSignals(False)
        self.update_interval_label()
    def update_interval_label(self):
        value=self.controls['twitch_viewers_interval'].value()
        self.interval_label.setText(('Update every '+str(value)+' minute(s)') if self.controls['twitch_viewers_live'].isChecked() else ('Activity window: '+str(value)+' minute(s); check every minute'))
    def save(self):
        self.update_interval_label()
        changes={key:control.isChecked() if isinstance(control,QCheckBox) else control.value() for key,control in self.controls.items()}
        self.host.store.update('local.json',changes);self.host.runtime.submit('reload')
