"""Saved prompt selection for AI actions; configuration stays in central settings."""
from .catalog import PROMPTS

def configuration(parent):
 seen=set();pending=[parent]
 while pending:
  host=pending.pop()
  if host is None or id(host) in seen:continue
  seen.add(id(host));store=getattr(host,'store',None)
  if store is not None:
   result={}
   for name,key in [('local.json','settings'),('prompts.json','prompts')]:
    try:result[key]=store.read(name)
    except (OSError,ValueError):result[key]={}
   return result
  pending.extend([getattr(host,'host',None),host.parent() if hasattr(host,'parent') else None])
 return {'settings':{},'prompts':{}}

def prompt_label(key):
 return {'stream_welcome':'Stream: Willkommen','stream_follow':'Stream: Follow','stream_raid':'Stream: Raid','stream_subscription':'Stream: Abo'}.get(key,PROMPTS.get(key,(key,''))[0])

def prompt_box(value,parent):
 from PySide6.QtWidgets import QComboBox
 box=QComboBox();saved=configuration(parent)['prompts']
 for key in dict.fromkeys([*PROMPTS,*saved]):
  if key in saved:box.addItem(prompt_label(key),key)
 box.addItem('Benutzerdefiniert','__custom__')
 # Preserve legacy/default selections and explicitly identify a missing template.
 if box.findData(value)<0:box.addItem(PROMPTS.get(value,(str(value),''))[0]+' (nicht gespeichert)',value)
 box.setCurrentIndex(box.findData(value));return box

LABELS={'promptKind':'Gespeicherter Prompt','prompt':'Eigener Prompt','resultVariable':'Antwortvariable','limit':'Maximale Antwortlänge (Zeichen)','provider':'Abweichender KI-Anbieter'}
