"""Explicit file, assembly, action and OBS mappings for import review."""
import copy,re,shutil
from pathlib import Path
from .original_graph import canonical,ZERO

PATHS={48:('path',),322:('fileName',),323:('fileName',),90003:('program','workingDir'),90012:('path',),90013:('path',),90014:('path',),90015:('path',),90016:('path',),90017:('path',),90141:('path',),90142:('path',)}
ACTION_FIELDS={4:('actionId',),90018:('actionId',),90019:('actionId',),90028:('actionId','subActionId'),90029:('actionId','subActionId'),90131:('actionId','triggerId'),90061:('codeId',)}

PATHS[90145]=('iconPath',)

def apply(node,bindings):
 result=copy.deepcopy(node)
 from .original_audio import apply as audio_apply
 audio_apply(result,bindings)
 for field in PATHS.get(node['type'],()):
  value=result.get(field)
  if isinstance(value,str):result[field]=bindings.get('files',{}).get(value,value)
 result['references']=[bindings.get('files',{}).get(r,r) for r in result.get('references',[])] if 'references' in result else result.get('references',[])
 if not result['references']:result.pop('references',None)
 if 'obsConnection' in result:result['obsConnection']=bindings.get('obs',{}).get(result['obsConnection'],result['obsConnection'])
 if node.get('_originalSemantics')=='randomUsers' and isinstance(result.get('groups',[]),list):result['groups']=[bindings.get('groups',{}).get(value,value) if isinstance(value,str) else value for value in result.get('groups',[])]
 if node.get('_originalSemantics')=='midi':result['deviceGuid']=bindings.get('midi',{}).get(result.get('deviceGuid'),result.get('deviceGuid'))
 for field in ACTION_FIELDS.get(node['type'],()):
  value=result.get(field)
  if isinstance(value,str):result[field]=bindings.get('actions',{}).get(value,value)
 return result

def problems(node):
 result=[]
 for field in PATHS.get(node['type'],()):
  value=node.get(field)
  if not isinstance(value,str) or not value:continue
  if re.match(r'^[A-Za-z]:[\\/]',value) or value.startswith('\\\\'):result.append('Windows-Pfad zuordnen: '+value)
  elif node['type']==90145 and field=='iconPath' and Path(value).is_absolute() and not any(c in value for c in ('%','$')) and not Path(value).is_file():result.append('Toast-Bilddatei fehlt: '+value)
  elif field=='program' and not any(c in value for c in ('%','$')):
   if not shutil.which(value):result.append('Linux-Programm fehlt oder muss zugeordnet werden: '+value)
 return result

def choices(document):
 from .core import walk
 from .original_references import migrate
 rows=[]
 for action in document['actions']:
  if not action.get('migrationBlock'):continue
  from .original_triggers import convert as convert_trigger
  for trigger in action.get('triggers',[]):
   converted,_=convert_trigger(trigger);connection=converted.get('obsConnection')
   if trigger.get('type')==301 and canonical(trigger.get('commandId')) not in (None,ZERO):rows.append(('voiceCommands',canonical(trigger['commandId']),action['name']+' · Dictation-Sprachbefehl',False))
   if trigger.get('type')==15001:
    device=trigger.get('midiDevice');event=trigger.get('midiEvent')
    if canonical(device) not in (None,ZERO):rows.append(('midiInputs',canonical(device),action['name']+' · MIDI-Eingang',False))
    if canonical(event) not in (None,ZERO):rows.append(('midiEvents',canonical(event),action['name']+' · MIDI-Ereignis',False))
   if connection not in (None,'','default','any',ZERO):rows.append(('obs',connection,action['name']+' · OBS-Trigger',False))
  for node in walk(action['subActions']):
   ref=node.get('_originalAudio')
   if ref and ref['source'] not in ('',ZERO,None):rows.append(('audioInputs' if ref['direction']=='input' else 'audioOutputs',ref['source'],action['name']+' · '+('Audio-Eingang' if ref['direction']=='input' else 'Audio-Ausgang')+' '+ref.get('name',''),False))
   if node.get('_originalSemantics')=='randomUsers':
    for name in node.get('groups',[]) if isinstance(node.get('groups',[]),list) else []:
     if isinstance(name,str):rows.append(('groups',name,action['name']+' · Zufallsnutzer-Gruppe',False))
   if node.get('_originalSemantics')=='midi':rows.append(('midi',node.get('deviceGuid',''),action['name']+' · MIDI-Ausgang',False))
   for field in PATHS.get(node['type'],()):
    value=node.get(field)
    if value:rows.append(('files',value,action['name']+' · '+field,node['type'] in (322,323)))
   if node['type']==90060:
    _,missing=migrate(node.get('references',[]))
    rows.extend(('files',r,action['name']+' · C# DLL',False) for r in missing)
   if node.get('obsConnection') not in (None,'','default',ZERO):rows.append(('obs',node['obsConnection'],action['name']+' · OBS',False))
   if node['type']==4:rows.append(('actions',node.get('actionId',''),action['name']+' · Run Action',False))
 return list(dict.fromkeys(rows))
