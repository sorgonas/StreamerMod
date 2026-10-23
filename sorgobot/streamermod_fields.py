"""Editable local IDs and profile choices, including offline configurations."""
from PySide6.QtWidgets import QComboBox
from .streamdeck_fields import control as deck_control
from .streamermod_decks import profile_snapshot
LABELS={'buttonId':'Item / Button ID','deviceId':'OpenDeck-Gerät (leer = automatisch)','state':'Zustand (0/1)','title':'Titel','description':'Beschreibung','duration':'Dauer (ms)','image':'Bild: Datei / URL / SVG','iconName':'Iconify-Name (optional)','color':'Farbe','value':'Wert / Rechenoperation','page':'OpenDeck-Profil oder Seitennummer ab 1','instanceId':'Remote-Instanz-ID (leer = alle/beliebig)','signalName':'Signalname','eventName':'Ereignisname','includeArguments':'Aktuelle Argumente mitsenden','arguments':'Zusätzliche Argumente (JSON)','overwrite':'Vorhandene Variablen überschreiben','timeout':'Timeout (ms)'}
def control(kind,key,value,parent):
 if 97101<=kind<=97106 and key in ('buttonId','deviceId','state'):
  # Reuse established editable IDs, without interpreting the new IDs as triggers.
  return deck_control(93000,key,value,parent)
 if key in ('timeout','duration'):
  box=QComboBox();box.setEditable(True);box.addItem(str(value));box.setCurrentText(str(value));return box
 choices=[]
 if 97100<=kind<=97109 and key=='deviceId':choices=['']+[r['deviceId'] for r in profile_snapshot()]
 elif kind==97109 and key=='page':choices=[p for row in profile_snapshot() for p in row['pages']]
 elif 97200<=kind<=97250 and key=='instanceId':
  host=parent
  while host is not None:
   if hasattr(host,'remote_status'):
    choices=['']+[p['id'] for p in host.remote_status.get('peers',[])];break
   host=getattr(host,'host',None) or (host.parent() if callable(getattr(host,'parent',None)) else None)
  if not choices:choices=['']
 else:return None
 box=QComboBox();box.setEditable(True)
 for item in dict.fromkeys(choices):box.addItem(item)
 box.setCurrentText(str(value));return box
