"""Stream Deck form choices from the latest, read-only runtime snapshot."""
from PySide6.QtWidgets import QComboBox
from .streamdeck_bridge import STEPS,TRIGGERS

LABELS={'buttonId':'Button ID','deviceId':'Gerät (optional)','title':'Titel','image':'Bild / Pfad / URL / SVG','color':'Hintergrundfarbe','state':'Zustand','value':'Wert','direction':'Drehrichtung'}

def snapshot(parent):
    seen=set()
    while parent is not None and id(parent) not in seen:
        seen.add(id(parent))
        if hasattr(parent,'streamdeck_status'):return parent.streamdeck_status.get('bindings',[])
        parent=getattr(parent,'host',None) or (parent.parent() if callable(getattr(parent,'parent',None)) else None)
    return []

def hint(kind,parent):
    count=len(snapshot(parent))
    common=f'OpenDeck → Streamer Linux Studio: {count} sichtbare Belegung(en) im letzten Status. Die Auswahlliste zeigt deren IDs; eigene IDs bleiben eingebbar.'
    if kind in STEPS:
        text=common+' Button ID: aus der Liste wählen oder %streamDeckButtonId% für die auslösende Belegung. Gerät leer = alle sichtbaren Studio-Belegungen mit dieser Button-ID; optional ein Gerät eingrenzen.'
        if kind in (93000,93001):text+=' Zustand 0/1 bestimmt die Darstellung der Taste; bei Drehreglern gilt die aktuelle Anzeige.'
        if kind in (93002,93006):text+=' Zustandswechsel (0/1) gelten nur für Tasten, nicht für Drehregler.'
        if kind==93001:text+=' Farbe z. B. #302536; Bild optional, lokale Datei relativ zum Projekt oder absolut, HTTP(S), Data-URI oder SVG. Maximal 2 MB pro Datei/Download.'
        if kind==93003:text+=' Wert: Text, Zahl oder +=1, -=1, *=2, /=2. Beispiel: +=1 erhöht den bisherigen Wert.'
        return text
    if kind in (93050,93051):return 'Meldet die Verbindung des Studio-Plugins mit der Anwendung; kein USB-An-/Absteckereignis.'
    text=common+' Leere Button-/Gerätefilter berücksichtigen alle Belegungen. IDs werden wörtlich verglichen. Direkte Action-Zuweisung im Plugin und ein passender Trigger können beide auslösen.'
    if kind==93052:text+=' Info meldet sichtbare Belegungen und Einstellungsänderungen.'
    else:text+=' Ereignisvariablen: %streamDeckButtonId%, %streamDeckDeviceId%, %streamDeckState%, %streamDeckPressed%, %streamDeckTicks%.'
    return text

def control(kind,key,value,parent):
    if key in ('buttonId','deviceId'):
        box=QComboBox();box.setEditable(True)
        values=[''] if kind in TRIGGERS or key=='deviceId' else ['%streamDeckButtonId%']
        values.extend(row.get(key,'') for row in snapshot(parent))
        for item in dict.fromkeys(values):box.addItem(item)
        box.setCurrentText(str(value))
        box.setToolTip('Leer = alle Geräte/Belegungen' if kind in TRIGGERS or key=='deviceId' else 'ID einer sichtbaren Belegung des Studio-Plugins')
        return box
    if key=='state':
        box=QComboBox();box.setEditable(kind in STEPS)
        if kind in TRIGGERS:box.addItem('Beliebig','')
        for state in (0,1):box.addItem(str(state),state)
        if box.isEditable():box.setCurrentText(str(value))
        else:
            index=box.findData(value)
            if index<0:index=box.findText(str(value))
            box.setCurrentIndex(max(0,index))
        return box
    if key=='direction':
        box=QComboBox()
        for label,item in [('Beliebig','any'),('Im Uhrzeigersinn','clockwise'),('Gegen den Uhrzeigersinn','counterclockwise')]:box.addItem(label,item)
        box.setCurrentIndex(max(0,box.findData(value)));return box
    return None

def validate(value):
    if value['type'] in STEPS:
        if not str(value.get('buttonId','')).strip():raise ValueError('Bitte eine Button-ID oder %streamDeckButtonId% angeben.')
        state=value.get('state',0)
        if str(state) not in ('0','1') and not (isinstance(state,str) and len(state)>2 and state.startswith('%') and state.endswith('%')):
            raise ValueError('Zustand muss 0, 1 oder eine %variable% sein.')
