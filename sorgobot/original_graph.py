"""Original object identity and hierarchy conversion; never rewrite executable text."""
import copy
import uuid

ZERO='00000000-0000-0000-0000-000000000000'
ID_FIELDS=frozenset(('id','parentId','actionId','subActionId','triggerId','commandId','timerId','queue','queueId','actionQueueId','codeId','executeCodeId','connectionId','serverId','clientId'))
COLLECTIONS=('actions','queues','commands','timers','websocketServers','websocketClients')

def canonical(value):
 try:return str(uuid.UUID(value))
 except (ValueError,TypeError,AttributeError):return None

def objects(value):
 if isinstance(value,dict):
  yield value
  for child in value.values():yield from objects(child)
 elif isinstance(value,list):
  for child in value:yield from objects(child)

def definitions(document):
 def nodes(rows):
  for node in rows:
   yield node
   if isinstance(node,dict):yield from nodes(node.get('subActions',[]))
 for collection in COLLECTIONS:
  rows=document.get(collection,[])
  if not isinstance(rows,list):raise ValueError('Ungültige Originalsammlung: '+collection)
  for row in rows:
   if not isinstance(row,dict):raise ValueError('Ungültiger Eintrag in '+collection)
   yield row
   if collection=='actions':
    yield from nodes(row.get('subActions',[]))
    yield from row.get('triggers',[])

def remap(envelope,existing,policy='error'):
 if policy not in ('error','remap'):raise ValueError('Ungültige Import-Konfliktbehandlung.')
 result=copy.deepcopy(envelope)
 occupied={canonical(n.get('id')) for n in definitions(existing) if n.get('id')}
 for bundle in existing.get('originalBundles',[]):
  if set(bundle.get('actionIds',[])) & {a['id'] for a in existing.get('actions',[])}:
   occupied.update(canonical(n.get('id')) for n in definitions({k:v for k,v in bundle['envelope']['data'].items() if k!='actions'}) if n.get('id'))
 owned={};mapping={}
 for node in definitions(result['data']):
   if 'id' not in node:continue
   identity=canonical(node['id'])
   if not identity:raise ValueError('Ungültige Original-ID')
   if identity in owned:raise ValueError('Doppelte Original-ID im Import')
   owned[identity]=node
   if identity in occupied:
    if policy=='error':raise ValueError('Aktions-ID bereits vorhanden; Import würde vorhandene Objekte überschreiben')
    mapping[identity]=str(uuid.uuid4())
 for node in definitions(result['data']):
   for field in ID_FIELDS & node.keys():
    identity=canonical(node[field])
    if identity in mapping:node[field]=mapping[identity]
   if isinstance(node.get('exclusions'),list):node['exclusions']=[mapping.get(canonical(value),value) for value in node['exclusions']]
 return result,mapping

def hierarchy(nodes):
 """Accept both flat parentId exports and nested lists; preserve sibling order."""
 if not isinstance(nodes,list):raise ValueError('Ungültige Unteraktionsliste')
 pool={};ordered=[];parents={};sequence=0
 def collect(rows,parent=None,depth=0):
  nonlocal sequence
  if depth>64:raise ValueError('Unteraktionsstruktur ist zu tief')
  for raw in rows:
   if not isinstance(raw,dict) or not canonical(raw.get('id')):raise ValueError('Unteraktion ohne gültige ID')
   identity=raw['id'];key=canonical(identity)
   if key in pool:raise ValueError('Doppelte Unteraktions-ID')
   claimed=raw.get('parentId')
   if claimed not in (None,'',ZERO) and not canonical(claimed):raise ValueError('Ungültige Eltern-ID einer Unteraktion')
   if parent and claimed not in (None,'',ZERO,parent):raise ValueError('Widersprüchliche Unteraktions-Elternzuordnung')
   node=copy.deepcopy(raw)
   if 'subActions' in node:node['subActions']=[]
   pool[key]=node;ordered.append((key,sequence));sequence+=1
   parents[key]=canonical(parent or claimed) if (parent or claimed) not in (None,'',ZERO) else None
   collect(raw.get('subActions',[]),identity,depth+1)
 collect(nodes)
 children={None:[]}
 for key,sequence in ordered:
  parent=parents[key]
  if parent and parent not in pool:raise ValueError('Übergeordnete Unteraktion fehlt: '+str(parent))
  children.setdefault(parent,[]).append((key,sequence))
 active=set();visited=set()
 def build(parent,depth=0):
  if depth>64:raise ValueError('Unteraktionsstruktur ist zu tief')
  result=[]
  for key,_ in sorted(children.get(parent,[]),key=lambda pair:(pool[pair[0]].get('index',pair[1]),pair[1])):
   if key in active:raise ValueError('Zyklische Unteraktionsstruktur')
   active.add(key);node=pool[key];node['parentId']=None
   nested=build(key,depth+1)
   if nested or 'subActions' in node:node['subActions']=nested
   result.append(node);active.remove(key);visited.add(key)
  return result
 result=build(None)
 if len(visited)!=len(pool):raise ValueError('Zyklische Unteraktionsstruktur')
 return result
