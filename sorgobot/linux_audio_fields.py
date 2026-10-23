from PySide6.QtWidgets import QComboBox
from .linux_audio import STEPS,TRIGGERS

LABELS={'audioKind':'Zielart','audioTarget':'Audio-Ziel-ID','audioDevice':'Zielgerät für Routing','audioOperation':'Lautstärkeoperation','audioVolume':'Lautstärke / Änderung (%)','audioMute':'Stummschaltung'}
HINT='@all bei Set Mute: alle aktuellen Ausgabegeräte bzw. Mikrofone (ohne Monitor-Quellen) stummschalten. Bei Toggle gilt: sind alle stumm, alle freigeben; sonst alle stummschalten. Neu angeschlossene Geräte werden erst beim nächsten Aufruf berücksichtigt. Linux Audio unter Stream Apps zeigt Geräte und aktive Anwendungen. Geräte: stabiler Gerätename oder @default. Anwendungen: Ziel-ID aus der Liste; alle passenden aktuellen Audiostreams werden angesprochen. Fehlende Ziele werden gemeldet. Set Volume: 0–100 %, adjust auch negative Änderungen; %streamDeckTicks% steuert beide Drehrichtungen. Balance bleibt bei Lautstärkeänderungen erhalten. Vorschau liest echte Audioziele, verändert sie aber nicht. Get Volume liefert %audioVolume% und %audioMuted%. Trigger prüfen Änderungen alle 2 Sekunden; schnellere Zwischenstände können fehlen.'

def host_snapshot(parent):
 seen=set()
 while parent is not None and id(parent) not in seen:
  seen.add(id(parent))
  if hasattr(parent,'audio_status'):return parent.audio_status.get('items',[])
  parent=getattr(parent,'host',None) or (parent.parent() if callable(getattr(parent,'parent',None)) else None)
 return []

def control(kind,key,value,node,parent):
 options=None;editable=False
 if key=='audioKind':
  choices=['output','input'] if kind==94004 else ['application','application-input'] if kind==94005 else ['output','input','application','application-input']
  if kind in TRIGGERS:choices=['any',*choices]
  options=[(x,x) for x in choices]
 elif key=='audioOperation':options=[('Setzen','set'),('Ändern (+/-)','adjust'),('Erhöhen','increase'),('Verringern','decrease')]
 elif key=='audioMute':options=[('Ein','on'),('Aus','off'),('Umschalten','toggle')]
 elif key in ('audioTarget','audioDevice'):
  editable=True;target_kind=node.get('audioKind','output')
  if key=='audioDevice':target_kind='output' if target_kind=='application' else 'input'
  targets=['']
  if target_kind in ('input','output','any'):targets.append('@default')
  if kind==94003 and target_kind in ('input','output'):targets.append('@all')
  if kind in STEPS and key=='audioTarget':targets.append('%audioTarget%')
  targets.extend(r['selector'] for r in host_snapshot(parent) if target_kind=='any' or r['kind']==target_kind)
  options=[(x,x) for x in dict.fromkeys(targets)]
 if options is None:return None
 box=QComboBox();box.setEditable(editable)
 for label,data in options:box.addItem(label,data)
 if editable:box.setCurrentText(str(value))
 else:
  index=box.findData(value)
  if index<0:box.addItem(str(value),value);index=box.count()-1
  box.setCurrentIndex(index)
 return box


def validate(node):
 from .core import ActionError
 kind=node['type']
 if kind not in STEPS or kind==94000:return
 if not str(node.get('audioTarget','')).strip():raise ValueError('Bitte eine Audio-Ziel-ID angeben.')
 if node.get('audioTarget')=='@all' and (kind!=94003 or node.get('audioKind') not in ('input','output')):raise ValueError('@all nur bei Set Mute für Ein-/Ausgabegeräte verwenden.')
 if kind==94005 and not str(node.get('audioDevice','')).strip():raise ValueError('Bitte ein Zielgerät oder @default angeben.')
 if kind==94002:
  import math
  raw=str(node.get('audioVolume',''))
  if raw.startswith('%') and raw.endswith('%') and len(raw)>2:return
  try:value=float(raw)
  except ValueError:raise ValueError('Lautstärke muss eine Zahl oder %variable% sein.') from None
  if not math.isfinite(value) or not (-100 if node.get('audioOperation')=='adjust' else 0)<=value<=100:raise ValueError('Lautstärke 0–100; adjust erlaubt -100 bis +100.')
