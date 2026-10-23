"""Keep original bundle provenance across delete, reimport, clone and native JSON."""
import copy,hashlib,json

def key(envelope):return hashlib.sha256(json.dumps(envelope,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

def entries(document):
 values=document.get('originalBundles',[])
 if not isinstance(values,list):raise ValueError('Ungültige Originalpaket-Liste im Import.')
 groups={}
 for value in values:
  if not isinstance(value,dict) or not isinstance(value.get('envelope'),dict) or not isinstance(value['envelope'].get('data'),dict) or not isinstance(value['envelope']['data'].get('actions'),list):raise ValueError('Originalpaket enthält keine gültigen Action-Daten.')
  if not isinstance(value.get('actionIds'),list) or any(not isinstance(i,str) for i in value['actionIds']):raise ValueError('Ungültige Action-Zuordnung im Originalpaket.')
  fingerprint=key(value['envelope'])
  if fingerprint not in groups:groups[fingerprint]=copy.deepcopy(value)
  else:groups[fingerprint]['actionIds']=list(dict.fromkeys(groups[fingerprint]['actionIds']+value['actionIds']))
 return groups

def matches(action,groups):
 original=action.get('_original');pinned=action.get('_originalBundleKey')
 result=[]
 for fingerprint,bundle in groups.items():
  if pinned and pinned!=fingerprint:continue
  if isinstance(original,dict):
   if any(raw==original for raw in bundle['envelope']['data']['actions']):result.append(fingerprint)
  elif action['id'] in bundle['actionIds']:result.append(fingerprint)
 return result

def normalize(document):
 """Mutate an already-owned document; preserve inactive envelopes losslessly."""
 groups=entries(document);owners={fingerprint:[] for fingerprint in groups}
 for action in document['actions']:
  found=matches(action,groups)
  if len(found)==1:action['_originalBundleKey']=found[0]
  for fingerprint in found:owners[fingerprint].append(action['id'])
 for fingerprint,bundle in groups.items():bundle['actionIds']=owners[fingerprint]
 document['originalBundles']=list(groups.values())
 return document

def resolve(document,identity):
 action=next((a for a in document['actions'] if a['id']==identity),None)
 if action is None:raise ValueError('Die importierte Action existiert nicht mehr.')
 groups=entries(document);found=matches(action,groups)
 if not found:raise ValueError('Die Originaldaten dieser Action wurden nicht mit übernommen. Bitte den Originalexport oder einen vollständigen StreamerMod-Export importieren.')
 if len(found)>1:raise ValueError('Mehrere unterschiedliche Originalpakete passen zu dieser Action. Die Herkunft muss eindeutig zugeordnet werden.')
 return groups[found[0]]

def merge_native(existing,incoming):
 from .catalog import validate_action
 if not isinstance(incoming,dict) or incoming.get('format')!='streamer-linux-actions-1' or not isinstance(incoming.get('actions'),list):raise ValueError('Nur Exporte dieser Linux-Version unterstützt.')
 result=copy.deepcopy(existing);actions=copy.deepcopy(incoming['actions']);identities={a['id'].casefold() for a in result['actions']}
 for action in actions:
  validate_action(action)
  if action['id'].casefold() in identities:raise ValueError('Aktions-IDs bereits vorhanden; Import würde vorhandene Aktionen überschreiben.')
  identities.add(action['id'].casefold())
 result['actions'].extend(actions)
 queues={q['id']:q for q in result.get('queues',[])}
 for queue in incoming.get('queues',[]):
  if queue['id'] in queues:
   if any(queues[queue['id']].get(k)!=queue.get(k) for k in ('name','blocking')):raise ValueError('Importierte Queue kollidiert mit einer vorhandenen Queue.')
  else:result.setdefault('queues',[]).append(copy.deepcopy(queue));queues[queue['id']]=queue
 result.setdefault('originalBundles',[]).extend(copy.deepcopy(incoming.get('originalBundles',[])))
 for section,rows in incoming.get('originalResources',{}).items():
  if section not in ('commands','timers','websocketConnections') or not isinstance(rows,list):raise ValueError('Ungültige Original-Abhängigkeiten.')
  target=result.setdefault('originalResources',{}).setdefault(section,[])
  for row in rows:
   found=next((r for r in target if r['id'].casefold()==row['id'].casefold()),None)
   if found is not None:
    if found!=row:raise ValueError('Unterschiedliche Original-Abhängigkeiten mit derselben ID.')
   else:
    target.append(copy.deepcopy(row));result.setdefault('pendingOriginalResources',{}).setdefault(section,[]).append(copy.deepcopy(row))
 if incoming.get('importBindings'):
  for section,values in incoming['importBindings'].items():
   if section=='obsTargets':continue
   target=result.setdefault('importBindings',{}).setdefault(section,{})
   for source,value in values.items():
    if source in target and target[source]!=value:raise ValueError('Widersprüchliche Import-Zuordnung: '+source)
    target[source]=copy.deepcopy(value)
 return normalize(result)
