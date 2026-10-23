"""Explicit, validated release of supported imports for manual testing."""
import copy,hashlib,json
from .original_references import migrate
from .catalog import validate_action
from .original_nodes import SUPPORTED,REQUIRED
ZERO='00000000-0000-0000-0000-000000000000'

def bundle_for(document,identity):
 from .original_bundles import resolve
 return resolve(document,identity)

def plan(document,identity,*,bindings=None,resources=None,_stack=()):
 bindings=bindings or {};resources=resources or {}
 action=next((a for a in document['actions'] if a['id']==identity),None)
 if not action or not action.get('migrationBlock'):raise ValueError('Diese Action hat keine offene Importsperre.')
 if len(_stack)>=20:raise ValueError('Action-Abhängigkeiten überschreiten die Laufzeittiefe von 20.')
 if identity in _stack:raise ValueError('Zyklische Action-Abhängigkeit im Originalimport.')
 bundle=bundle_for(document,identity);candidate=copy.deepcopy(action);blockers=[];notes=[];codes=[];queue=None;related={};related_queues={}
 qid=candidate.get('queue')
 if qid in (None,'',ZERO):candidate['queue']=None
 else:
  queues=[q for q in document.get('queues',[]) if q['id']==qid];originals=[q for q in bundle['envelope']['data'].get('queues',[]) if q.get('id')==qid]
  if len(queues)>1 or len(originals)>1:blockers.append('Queue-ID ist mehrfach vorhanden.')
  elif queues:
   if originals and any(queues[0].get(k)!=originals[0].get(k) for k in ('name','blocking')):blockers.append('Die vorhandene Queue unterscheidet sich vom Originalpaket.')
   if queues[0].get('paused'):blockers.append('Die zugeordnete Queue ist pausiert. Bitte zuerst unter Queues fortsetzen.')
   notes.append('Vorhandene Queue: '+str(queues[0]['name']))
  elif originals:
   q=originals[0]
   if not isinstance(q.get('name'),str) or not q['name'].strip() or type(q.get('blocking')) is not bool:blockers.append('Die Originalqueue enthält ungültige Eigenschaften.')
   else:queue={k:copy.deepcopy(q[k]) for k in ('id','name','blocking')};queue['paused']=False;notes.append('Queue wird übernommen: '+q['name'])
  else:blockers.append('Die benötigte Queue ist weder eingerichtet noch im Originalpaket enthalten.')
 def visit(nodes):
  for index,node in enumerate(nodes):
   from .original_dependencies import apply as apply_bindings,problems as dependency_problems
   from .original_nodes import refresh
   node=refresh(node)
   node=nodes[index]=apply_bindings(node,bindings)
   replaced=node.get('_baseline',{}).get('type',node.get('type'))!=node.get('type')
   if replaced:
    for marker in ('_originalSemantics','_originalObs','_importProblems','_stateValues','_fieldMap','_flagValues','_originalAudio','_originalAudioTarget'):node.pop(marker,None)
   blockers.extend(dependency_problems(node))
   if not node.get('enabled',True):continue
   from .original_audio import validate as audio_validate
   blockers.extend(audio_validate(node,resources))
   kind=node.get('type')
   for problem in node.get('_importProblems',[]):
    if problem.startswith('C#-Code enthält') and not any(old.casefold() in node.get('code','').casefold() for old in bundle.get('idMap',{})):continue
    blockers.append(problem)
   if kind not in SUPPORTED:
    from .next_catalog import steps
    if kind not in steps() or node.get('_original') and not replaced:blockers.append('Noch keine Ausführungsmigration für Unteraktion '+str(kind));continue
   if kind==91701:
    from .twitch_random_groups import validate,resolve
    from .core import ActionError
    try:resolve(validate(node),resources.get('userGroups',document.get('userGroups',[])))
    except ActionError as exc:blockers.append(str(exc))
   if node.get('_originalSemantics')=='midi':
    target=next((r for r in resources.get('midiDevices',[]) if r.get('id')==node.get('deviceGuid') and r.get('enabled',True) and r.get('device')),None)
    if target is None:blockers.append('MIDI-Gerät muss auf einen eingerichteten Linux-Ausgang zugeordnet werden: '+str(node.get('deviceGuid')))
   if node.get('parentId') is not None:blockers.append('Flache Original-Gruppenzuordnung muss zuerst migriert werden.')
   if any(key not in node for key in REQUIRED.get(kind,())):blockers.append('Pflichtfelder fehlen bei Unteraktion '+str(kind))
   if kind==90060:
    node.pop('_originalSemantics',None)
    refs,unresolved=migrate(node.get('references',[]));node['references']=refs
    # Absolute, existing DLL paths are already mapped native dependencies.
    from pathlib import Path
    unresolved=[r for r in unresolved if not (Path(r).is_absolute() and Path(r).is_file() and Path(r).suffix.casefold()=='.dll')]
    if unresolved:blockers.append('C#-Bibliotheken fehlen: '+', '.join(unresolved))
    if not isinstance(node.get('code'),str) or not node['code'].strip():blockers.append('C#-Quelltext fehlt.')
    codes.append(node)
   from .obs_connections import OBS_TYPES
   if kind in OBS_TYPES:
    if 'connectionId' in node:
     connection=node.pop('connectionId');node['obsConnection']='default' if connection in ('',ZERO) else connection
    if node.get('obsConnection','default') not in ('default','__local__',*bindings.get('obsTargets',[])):blockers.append('Die OBS-Verbindung muss auf eine eingerichtete native Verbindung zugeordnet werden.')
   if kind==30 and node.get('state') not in (0,1,2):blockers.append('Ungültiger OBS-Sichtbarkeitszustand.')
   if kind==1002:
    try:
     import math
     low=float(node.get('value',0));high=float(node.get('maxValue',low))
     if not math.isfinite(low) or low<0 or not math.isfinite(high) or node.get('random') and high<low:raise ValueError()
    except (TypeError,ValueError):blockers.append('Delay muss eine gültige nichtnegative Zahl sein.')
   if kind==4:
    target=next((a for a in document['actions'] if a['id']==node.get('actionId')),None)
    if target is None:blockers.append('Zielaction fehlt: '+str(node.get('actionId')))
    elif target.get('migrationBlock'):
     try:
      dependency=plan(document,target['id'],bindings=bindings,resources=resources,_stack=(*_stack,identity));blockers.extend(dependency['blockers']);codes.extend(dependency['codes']);related.update({a['id']:a for a in dependency['relatedActions']});related[target['id']]=dependency['action']
      for q in [dependency['queue'],*dependency['relatedQueues']]:
       if q:related_queues[q['id']]=q
      notes.append('Abhängige Action wird mitgeprüft: '+target['name'])
     except ValueError as exc:blockers.append(str(exc))
    elif not target.get('enabled',True):blockers.append('Zielaction ist deaktiviert: '+target['name'])
   if kind==90061:
    from .core import walk
    targets=[n for a in document['actions'] for n in walk(a['subActions']) if n.get('id')==node.get('codeId') and n.get('type')==90060]
    if len(targets)!=1:blockers.append('C#-Code für Execute Method fehlt oder ist nicht eindeutig.')
    else:
     target=apply_bindings(targets[0],bindings);refs,missing=migrate(target.get('references',[]));target['references']=refs
     from pathlib import Path
     if any(not (Path(r).is_file() and Path(r).suffix.casefold()=='.dll') for r in missing):blockers.append('C#-Methodenreferenzen müssen zuerst zugeordnet werden.')
     codes.append(target)
   if kind in (90050,90051,90052) and node.get('queueId') not in (None,'All'):
    qid=node['queueId'];existing=next((q for q in document.get('queues',[]) if q['id']==qid),None)
    original=next((q for q in bundle['envelope']['data'].get('queues',[]) if q.get('id')==qid),None)
    if existing is None and original and isinstance(original.get('name'),str) and type(original.get('blocking')) is bool:related_queues[qid]={'id':qid,'name':original['name'],'blocking':original['blocking'],'paused':False}
    elif existing is None:blockers.append('Queue der Unteraktion fehlt: '+str(qid))
    elif original and any(existing.get(key)!=original.get(key) for key in ('name','blocking')):blockers.append('Queue der Unteraktion unterscheidet sich vom Originalpaket.')
   if kind in (90022,90025,90130):
    section,field=('timers','timerId') if kind==90130 else ('commands','commandId')
    rows=document.get('originalResources',{}).get(section,[])+document.get(section,[])+resources.get(section,[])
    target=next((r for r in rows if r['id']==node.get(field)),None)
    if target is None:blockers.append('Benötigter '+section+'-Eintrag fehlt: '+str(node.get(field)))
    else:blockers.extend(target.get('_importProblems',[]))
   visit(node.get('subActions',[]))
 visit(candidate['subActions'])
 from .original_triggers import convert as convert_trigger
 triggers=[]
 original_triggers={t['id']:t for t in action.get('_original',{}).get('triggers',[])}
 from .next_catalog import triggers as native_triggers
 for raw_trigger in candidate['triggers']:
  source=original_triggers.get(raw_trigger['id'])
  replaced=source is None or raw_trigger.get('type')!=source.get('type') and not raw_trigger.get('_original')
  if replaced:
   trigger={k:copy.deepcopy(v) for k,v in raw_trigger.items() if not k.startswith('_')}
   if trigger.get('type') not in native_triggers():blockers.append('Unbekannter nativer Ersatztrigger: '+str(trigger.get('type')))
  else:
   trigger,issues=convert_trigger(raw_trigger);blockers.extend(issues)
  if not replaced and raw_trigger.get('type')==301 and trigger.get('voiceCommandId'):
   from .original_graph import canonical
   source_id=canonical(trigger['voiceCommandId'])
   trigger['voiceCommandId']=bindings.get('voiceCommands',{}).get(source_id,trigger['voiceCommandId'])
   found=[r for r in resources.get('voiceCommands',[]) if canonical(r.get('id'))==canonical(trigger['voiceCommandId'])]
   if len(found)!=1 or not found[0].get('command','').strip():blockers.append('Dictation-Sprachbefehl einem eingerichteten Voice Command zuordnen: '+str(source_id))
  if not replaced and raw_trigger.get('type')==15001:
   from .original_midi_events import apply as midi_trigger
   try:trigger=midi_trigger(trigger,document,resources,bindings)
   except ValueError as exc:blockers.append(str(exc))
  if 'obsConnection' in trigger:
   trigger['obsConnection']=bindings.get('obs',{}).get(trigger['obsConnection'],trigger['obsConnection'])
   if trigger['obsConnection'] not in ('default','__local__','any',*bindings.get('obsTargets',[])):blockers.append('OBS-Triggerverbindung muss zuerst zugeordnet werden.')
  if trigger['type'] in (90260,90261,90262,90263,90264,90265):
   target=next((r for r in document.get('originalResources',{}).get('websocketConnections',[])+resources.get('websocketConnections',[]) if r['id']==trigger.get('connectionId')),None)
   if target is None:blockers.append('WebSocket-Triggerverbindung muss zuerst zugeordnet werden.')
   else:blockers.extend(target.get('_importProblems',[]))
  if trigger['type'] in (401,402,701):
   section,field=('timers','timerId') if trigger['type']==701 else ('commands','commandId')
   rows=document.get('originalResources',{}).get(section,[])+document.get(section,[])+resources.get(section,[])
   target=next((r for r in rows if r['id']==trigger.get(field)),None)
   if target is None:blockers.append('Trigger-Abhängigkeit fehlt: '+field+' '+str(trigger.get(field)))
   else:blockers.extend(target.get('_importProblems',[]))
  if not replaced:
   trigger['_original']=copy.deepcopy(raw_trigger);trigger['_baseline']=copy.deepcopy(trigger);trigger['_baseline'].pop('_original',None)
  trigger['enabled']=False
  triggers.append(trigger)
 candidate['triggers']=triggers
 notes.append('Action wird für manuelle Tests aktiviert; alle automatischen Trigger bleiben ausgeschaltet.')
 candidate['_migrationReview']={'mode':'manual','automaticTriggersEnabled':False}
 candidate.pop('migrationBlock');candidate['enabled']=True;validate_action(candidate)
 fingerprints={}
 from pathlib import Path
 for code in codes:
  for reference in code.get('references',[]):
   path=Path(reference)
   if path.is_absolute() and path.is_file():
    digest=hashlib.sha256()
    with path.open('rb') as stream:
     while chunk:=stream.read(512*1024):digest.update(chunk)
    fingerprints[str(path.resolve())]=digest.hexdigest()
 signature=hashlib.sha256(json.dumps({'document':document,'bindings':bindings,'assemblies':fingerprints,'resources':resources},sort_keys=True,ensure_ascii=False).encode()).hexdigest()
 return {'action':candidate,'queue':queue,'codes':codes,'blockers':list(dict.fromkeys(blockers)),'notes':notes,'signature':signature,'relatedActions':list(related.values()),'relatedQueues':list(related_queues.values())}

def release(document,identity,signature,*,bindings=None,resources=None):
 current=plan(document,identity,bindings=bindings,resources=resources)
 if current['signature']!=signature:raise ValueError('Die Action oder Queue wurde während der Prüfung geändert. Bitte erneut prüfen.')
 if current['blockers']:raise ValueError('\n'.join(current['blockers']))
 result=copy.deepcopy(document);replacements={a['id']:a for a in [current['action'],*current['relatedActions']]};result['actions']=[replacements.get(a['id'],a) for a in result['actions']]
 from .core import walk
 approved={n['id']:n for n in current['codes']}
 for action in result['actions']:
  for node in walk(action['subActions']):
   if node.get('id') in approved:node['references']=copy.deepcopy(approved[node['id']].get('references',[]))
 for queue in [current['queue'],*current['relatedQueues']]:
  if queue and not any(q['id']==queue['id'] for q in result.get('queues',[])):result.setdefault('queues',[]).append(queue)
 return result
