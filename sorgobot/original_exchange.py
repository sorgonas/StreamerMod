"""Original SBAE/gzip action bundles, bounded decoding and lossless passthrough.

Unverified node types are preserved but block execution, never guessed by ID.
"""
import base64,copy,gzip,json,uuid
from .catalog import validate_action
MAX=16*1024*1024
VERSIONS={23,24}
RENAMES={'excludeFromHistory':'excludeHistory','randomAction':'random'}

def is_original(raw):
 """Recognize original exports independently of extension, BOM and line wrapping."""
 try:
  if isinstance(raw,str):raw=raw.encode('utf-8')
  raw=raw.removeprefix(b'\xef\xbb\xbf').strip()
  if raw.startswith(b'{'):
   value=json.loads(raw)
   return isinstance(value,dict) and 'version' in value and isinstance(value.get('data'),dict) and 'actions' in value['data']
  return base64.b64decode(b''.join(raw.split())[:8],validate=True).startswith(b'SBAE')
 except (ValueError,TypeError,UnicodeError):return False

def decode(raw):
 if isinstance(raw,str):raw=raw.encode('utf-8')
 if len(raw)>MAX:raise ValueError('Exportdatei zu groß (maximal 16 MiB)')
 raw=raw.removeprefix(b'\xef\xbb\xbf').strip()
 try:
  if raw.startswith(b'{'):text=raw
  else:
   blob=base64.b64decode(b''.join(raw.split()),validate=True)
   if not blob.startswith(b'SBAE'):raise ValueError('Kein unterstützter SBAE-Export. Geschützte oder ältere Formate bitte im Original als normalen Action-Export speichern.')
   import io
   with gzip.GzipFile(fileobj=io.BytesIO(blob[4:])) as stream:text=stream.read(MAX+1)
   if len(text)>MAX:raise ValueError('Entpackter Export zu groß')
  value=json.loads(text)
 except (OSError,UnicodeError,EOFError,RecursionError) as exc:raise ValueError('Beschädigter oder geschützter Originalexport; ungeschützten Action-Export verwenden.') from exc
 if not isinstance(value,dict) or type(value.get('version')) is not int or value['version'] not in VERSIONS or not isinstance(value.get('data'),dict) or not isinstance(value['data'].get('actions'),list):raise ValueError('Original-Exportversion oder Struktur wird noch nicht unterstützt')
 return value

def encode(value):return base64.b64encode(b'SBAE'+gzip.compress(json.dumps(value,ensure_ascii=False,separators=(',',':')).encode(),mtime=0)).decode()

def fields(node):return {k:copy.deepcopy(v) for k,v in node.items() if k not in ('subActions','_original','_baseline')}

def import_bundle(raw,existing,*,collision='error'):
 from .original_graph import remap,hierarchy,objects
 source_envelope=decode(raw);original,idmap=remap(source_envelope,existing,collision);document=copy.deepcopy(existing);actions=[];warnings=[];seen=set()
 def identity(value):
  if not isinstance(value,str):raise ValueError('Original-ID fehlt')
  try:uuid.UUID(value)
  except ValueError:raise ValueError('Ungültige Original-ID') from None
  if value.casefold() in seen:raise ValueError('Doppelte Original-ID im Import')
  seen.add(value.casefold())
 def convert(node,issues,depth=0):
  if depth>64 or not isinstance(node,dict) or type(node.get('type')) is not int:raise ValueError('Ungültige oder zu tiefe Unteraktion')
  identity(node.get('id'));kind=node['type'];out={k:copy.deepcopy(v) for k,v in node.items() if not k.startswith('_')}
  original_node=original_nodes[node['id']]
  if kind==99999:
   try:source=base64.b64decode(node.get('byteCode',''),validate=True).decode('utf-8-sig')
   except (ValueError,UnicodeError):raise ValueError('Ungültiger C#-Quelltext') from None
   out.update(type=90060,code=source,delayedStart=node.get('delayStart',False),saveResult=node.get('saveResultToVariable',False),resultVariable=node.get('saveToVariable') or 'csharpResult')
   from .original_references import migrate
   out['references'],unresolved=migrate(node.get('references',[]))
   if idmap and any(old.casefold() in source.casefold() for old in idmap):out['_importProblems']=['C#-Code enthält umgeschriebene Objekt-IDs und muss angepasst werden.']
   if unresolved:issues.add(str(len(unresolved))+' nicht aufgelöste C#-Bibliotheksverweise')
   for key in ('byteCode','delayStart','saveResultToVariable','saveToVariable'):out.pop(key,None)
   issues.add('C#-Code und Bibliotheksabhängigkeiten vor Ausführung prüfen')
  else:
   from .original_nodes import convert as migrate_node
   out,problems=migrate_node(node);issues.update(problems)
   if problems:out['_importProblems']=problems
  from .obs_connections import OBS_TYPES
  if out['type'] in OBS_TYPES:
   connection=node.get('connectionId')
   if connection is not None:
    out.pop('connectionId',None)
    out['obsConnection']='default' if connection in ('','default','00000000-0000-0000-0000-000000000000') else connection
   if connection not in (None,'','default','00000000-0000-0000-0000-000000000000'):issues.add('OBS-Verbindungszuordnung prüfen: '+str(connection))
  if 'subActions' in out:
   if not isinstance(out['subActions'],list):raise ValueError('Ungültige Unteraktionsliste')
   out['subActions']=[convert(n,issues,depth+1) for n in out['subActions']]
  out['_original']=copy.deepcopy(original_node);out['_baseline']=fields(out);return out
 existing_ids={a['id'].casefold() for a in document['actions']}
 for original_action in original['data']['actions']:
  if not isinstance(original_action,dict):raise ValueError('Ungültige Original-Action')
  identity(original_action.get('id'))
  if original_action['id'].casefold() in existing_ids:raise ValueError('Aktions-ID bereits vorhanden; Import würde eine Action überschreiben')
  issues=set();action={k:copy.deepcopy(v) for k,v in original_action.items() if not k.startswith('_')}
  for source,target in RENAMES.items():
   if source in action:action[target]=action.pop(source)
  from .core import walk
  original_nodes={n['id']:n for n in walk(original_action.get('subActions',[]))}
  action['subActions']=[convert(n,issues) for n in hierarchy(original_action.get('subActions',[]))]
  for t in action.get('triggers',[]):identity(t.get('id'))
  # Queue, commands, timer and device dependencies require a reviewed migration.
  if action.get('triggers') or action.get('queue'):issues.add('Trigger-/Queue-/Command-Abhängigkeiten prüfen')
  action['_original']=copy.deepcopy(original_action);action['_baseline']=fields(action)
  action['enabled']=False;action['migrationBlock']='Originalimport: '+('; '.join(sorted(issues)) if issues else 'Import vor Ausführung prüfen')
  from .original_bundles import key
  action['_originalBundleKey']=key(original)
  action['_baseline']['enabled']=False;action['_baseline']['migrationBlock']=action['migrationBlock']
  validate_action(action);actions.append(action);warnings.append(action['name']+': '+action['migrationBlock'])
 from .original_resources import stage
 stage(document,original)
 document['actions'].extend(actions)
 document.setdefault('originalBundles',[]).append({'envelope':original,'actionIds':[a['id'] for a in actions],**({'sourceEnvelope':source_envelope,'idMap':idmap} if idmap else {})})
 from .original_bundles import normalize
 return normalize(document),warnings

def export_bundle(document,*,resources=None):
 from .original_bundles import normalize
 document=normalize(copy.deepcopy(document))
 bundles=[b for b in document.get('originalBundles',[]) if b['actionIds']]
 if not bundles:bundles=document.get('originalBundles',[])
 if not bundles:bundles=[{'actionIds':[],'envelope':{'version':24,'exportedFrom':'1.0.7','minimumVersion':'1.0.0-alpha.1','meta':{'name':'StreamerMod Export','author':'','version':'1.0.0','description':'','autoRunAction':None,'minimumVersion':None},'data':{key:[] for key in ('actions','queues','commands','timers','websocketServers','websocketClients')}}}]
 bundle={'actionIds':[aid for b in bundles for aid in b['actionIds']]}
 result=copy.deepcopy(bundles[0]['envelope']);lookup={a['id']:a for a in document['actions']}
 for additional in bundles[1:]:
  for section,rows in additional['envelope']['data'].items():
   if section=='actions':continue
   if not isinstance(rows,list):
    if result['data'].get(section)!=rows:raise ValueError('Unvereinbare Original-Paketmetadaten: '+section)
    continue
   target=result['data'].setdefault(section,[])
   for row in rows:
    matches=[r for r in target if isinstance(r,dict) and isinstance(row,dict) and r.get('id')==row.get('id')]
    if matches and row not in matches:raise ValueError('Nicht aufgelöste Paket-ID beim Rückexport: '+section)
    if row not in target:target.append(copy.deepcopy(row))
 def convert(node):
  if '_original' not in node or node.get('type')!=node.get('_baseline',{}).get('type',node.get('type')):
   from .original_writer import node as write_node
   return write_node(node,convert_child=convert)
  raw=copy.deepcopy(node['_original']);baseline=node.get('_baseline',{})
  from .original_audio import export_check
  export_check(node)
  for key,value in fields(node).items():
   if key=='audioDevice' and node.get('_originalAudio'):continue
   if baseline.get(key)==value:continue
   if key.startswith('_') or key in ('migrationBlock','code','type','parentId'):continue
   if node['_original'].get('type')==203 and key=='rewards':continue
   if node.get('_originalMidiBaseline') is not None and key in node['_originalMidiBaseline']:
    if value!=node['_originalMidiBaseline'][key]:raise ValueError('Bearbeitete MIDI-Ereignisfilter bitte als Linux-JSON exportieren; das Originalformat speichert nur den externen Ereignisverweis.')
    continue
   target=node.get('_fieldMap',{}).get(key,key)
   if node['_original'].get('type')==9003 and key=='command':
    commands={'NoteOff':128,'NoteOn':144,'ControlChange':176,'PatchChange':192,'ChannelAfterTouch':208,'PitchWheelChange':224}
    if value not in commands:raise ValueError('MIDI-Befehl besitzt keine Originalzuordnung.')
    value=commands[value]
   if key in node.get('_scaleValues',{}):value=value/node['_scaleValues'][key]
   if key in node.get('_stateValues',{}):
    try:value=node['_stateValues'][key].index(value)
    except ValueError:raise ValueError('Zustand besitzt keine Originalformat-Zuordnung') from None
   if key in node.get('_flagValues',[]):
    from .original_triggers import flag_original
    value=flag_original(key,value)
   target={'delayedStart':'delayStart','saveResult':'saveResultToVariable','resultVariable':'saveToVariable'}.get(key,key) if node.get('type')==90060 else target
   if key=='voiceCommandId' and target=='commandId' and not value:value='00000000-0000-0000-0000-000000000000'
   if key=='obsConnection':
    target=node.get('_fieldMap',{}).get(key,'connectionId')
    if value=='default':value='00000000-0000-0000-0000-000000000000'
    elif value=='any' and target=='obsId':value=None
   raw[target]=copy.deepcopy(value)
  if node.get('_originalSemantics')=='pickColor' and node.get('color')!=baseline.get('color'):
   color=node['color'].lstrip('#');raw.update(red=int(color[0:2],16),green=int(color[2:4],16),blue=int(color[4:6],16));raw.pop('color',None)
  if node['_original'].get('type')==1012 and node.get('keys')!=baseline.get('keys'):
   from .original_keyboard import original as key_original
   raw['key'],raw['modifiers']=key_original(node['keys']);raw.pop('keys',None)
  if node.get('type')==90060 and node.get('code')!=baseline.get('code'):raw['byteCode']=base64.b64encode(node['code'].encode()).decode()
  if node['_original'].get('type')==203 and node.get('rewards')!=baseline.get('rewards'):
   from .original_rewards import original
   raw['states']=original(node['rewards'])
  for removed in set(baseline)-set(fields(node)):
   if not removed.startswith('_') and removed not in ('type','code','parentId'):raw.pop(node.get('_fieldMap',{}).get(removed,removed),None)
  if 'subActions' in node:raw['subActions']=[convert(n) for n in node['subActions']]
  return raw
 def convert_trigger(trigger):
  if '_original' in trigger:return convert(trigger)
  from .original_writer import trigger as write_trigger
  return write_trigger(trigger)
 def positions(action,raw):
  from .original_graph import hierarchy
  previous={}
  def remember(rows,parent=None):
   for index,node in enumerate(rows):previous[node['id']]=(parent,index);remember(node.get('subActions',[]),node['id'])
  remember(hierarchy(action.get('_original',{}).get('subActions',[])))
  def assign(rows,native,parent=None):
   for index,(row,node) in enumerate(zip(rows,native)):
    if previous.get(node['id'])!=(parent,index):row['parentId']=parent;row['index']=index
    assign(row.get('subActions',[]),node.get('subActions',[]),node['id'])
  assign(raw['subActions'],action['subActions'])
 actions=[]
 for aid in dict.fromkeys([*bundle['actionIds'],*lookup]):
  if aid not in lookup:continue
  action=lookup[aid]
  if '_original' not in action:
   from .original_writer import action as write_action
   raw=write_action(action,convert,convert_trigger);positions(action,raw);actions.append(raw);continue
  raw=copy.deepcopy(action['_original']);baseline=action['_baseline']
  raw['id']=action['id']
  for key in ('name','group','enabled','queue','triggers','concurrent','alwaysRun','excludeHistory','random'):
   if action.get(key)!=baseline.get(key):raw[next((old for old,new in RENAMES.items() if new==key),key)]=copy.deepcopy(action.get(key))
  if action.get('triggers')!=baseline.get('triggers'):
   raw['triggers']=[convert_trigger(t) for t in action['triggers']]
  raw['subActions']=[convert(n) for n in action['subActions']]
  positions(action,raw)
  # A flat original remains flat when exported back, with real parent links.
  if any(n.get('parentId') for n in action['_original'].get('subActions',[])):
   from .original_graph import hierarchy
   from .core import walk
   def shape(nodes):return [(n['id'],shape(n.get('subActions',[]))) for n in nodes]
   def public(node):return {k:v for k,v in fields(node).items() if not k.startswith('_') and k!='parentId'}
   unchanged=shape(action['subActions'])==shape(hierarchy(action['_original']['subActions'])) and all(public(n)=={k:v for k,v in n.get('_baseline',{}).items() if not k.startswith('_') and k!='parentId'} for n in walk(action['subActions']))
   if unchanged:
    raw['subActions']=copy.deepcopy(action['_original']['subActions']);actions.append(raw);continue
   flattened=[]
   def flatten(rows,parent=None):
    for index,node in enumerate(rows):
     children=node.pop('subActions',[]);node['parentId']=parent;node['index']=index;flattened.append(node);flatten(children,node['id'])
   flatten(raw['subActions']);raw['subActions']=flattened
  actions.append(raw)
 wanted={a.get('queue') for a in actions}
 from .core import walk
 for action in actions:
  wanted.update(n.get('actionQueueId') for n in walk(action['subActions']))
 target=result['data'].setdefault('queues',[])
 for queue in document.get('queues',[]):
  if queue['id'] in wanted:
   row={k:copy.deepcopy(queue[k]) for k in ('id','name','blocking')}
   old=next((r for r in target if r['id']==row['id']),None)
   if old is not None:old.update(row)
   else:target.append(row)
 result['data']['actions']=actions
 from .original_writer import dependencies
 dependencies(result,document,resources)
 return encode(result)
