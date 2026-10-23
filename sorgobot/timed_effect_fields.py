from PySide6.QtWidgets import QComboBox
from .linux_audio_fields import control as audio_control
LABELS={'letter':'Buchstabe (A–Z / a–z)','duration':'Dauer (Sekunden, 1–600)','keyboardLayout':'Tastaturlayout','waitForFinish':'Action bis zur Freigabe warten lassen','audioKind':'Zielart','audioTarget':'Audio-Ziel (@default / @all / Gerätename)'}
def control(kind,key,value,node,parent):
 if key in ('letter','duration'):
  box=QComboBox();box.setEditable(True)
  for item in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' if key=='letter' else [str(value)]:box.addItem(item)
  box.setCurrentText(str(value));return box
 if key=='keyboardLayout' or key=='audioKind':
  box=QComboBox()
  for label,data in [('Deutsch (Y/Z berücksichtigt)','de'),('US / QWERTY','us')] if key=='keyboardLayout' else [('Mikrofon / Eingabe','input'),('Systemton / Ausgabe','output')]:box.addItem(label,data)
  box.setCurrentIndex(max(0,box.findData(value)));return box
 if key=='audioTarget':return audio_control(94003,key,value,node,parent)
 return None
