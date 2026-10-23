"""Explicit inverse serializer for new native nodes that have an Original schema.

Options without a representation fail with a field-specific error. In particular,
Linux services and native convenience outputs are never silently dropped.
"""
import base64,copy,json
from pathlib import Path
from .original_nodes import MAP,IDENTITY,convert
ZERO='00000000-0000-0000-0000-000000000000'
SCHEMAS=json.loads(Path(__file__).with_name('original_node_schemas.json').read_text())
TRIGGER_SCHEMAS=json.loads(Path(__file__).with_name('original_trigger_schemas.json').read_text())
COMMON={'id','weight','type','parentId','enabled','subActions','index'}

def node(value,convert_child=None):
 kind=value['type']
 if kind in IDENTITY:source=kind
 elif kind==90060:source=99999
 elif kind==90314:source=321
 elif kind==90165:source=99904 if value.get('default') else 99903
 else:
  choices=[key for key,(native,_) in MAP.items() if native==kind]
  if len(choices)!=1:raise ValueError('Unteraktion '+str(kind)+' besitzt keine eindeutige Originalformat-Zuordnung.')
  source=choices[0]
 allowed=set(SCHEMAS.get(str(source),{}).get('fields',[]))|COMMON
 if source in (99903,99904):allowed|={'caseSensitive','values'}
 if source==203:allowed.add('states')
 raw={'id':value['id'],'type':source,'enabled':value.get('enabled',True),'parentId':None,'weight':value.get('weight',0)}
 if source==4:raw['runImmedately']=True
 renames={new:old for old,new in MAP.get(source,(None,{}))[1].items()}
 # Probe only the serialized enum translation, never execute source code.
 probe={**raw,'state':0,'status':0,'operator':0,'operation':0,'flipMode':0,'color':0}
 migrated,_=convert(probe) if source!=99999 else ({},[])
 renames.update(migrated.get('_fieldMap',{}))
 states=migrated.get('_stateValues',{})
 for key,item in value.items():
  if source in (1,7,1025) and key=='audioDevice':
   if item!='@default':raise ValueError('Linux-Audiogerät besitzt keine Windows-GUID; bitte Linux-JSON exportieren.')
   continue
  if key.startswith('_') or key in COMMON or key=='migrationBlock':continue
  target=renames.get(key,key)
  if key=='obsConnection':
   target='connectionId';item=ZERO if item in ('default','__local__','',None) else item
  if source==99999:
   target={'code':'byteCode','delayedStart':'delayStart','saveResult':'saveResultToVariable','resultVariable':'saveToVariable'}.get(key,target)
   if key=='code':item=base64.b64encode(item.encode()).decode()
  if 4001<=source<=4012:
   if key=='broadcastId' and item=='':continue
   if key=='pollId' and item=='':continue
   if key=='resultVariable' and item=={4005:'addResult',4006:'removeResult',4007:'inGroup'}.get(source):continue
   if key=='duration':item=str(item)
  if key in states:
   if type(item) is bool and states[key][:2]==['enabled','disabled']:item='enabled' if item else 'disabled'
   try:item=states[key].index(item)
   except ValueError:raise ValueError('Unteraktion '+str(kind)+': Zustand '+key+' ist nicht im Original darstellbar.') from None
  if key=='volume' and source in (1,7):item=float(item)/100
  if source in (99903,99904) and key=='default':continue
  if source==99903 and key=='name':continue
  if source==1024 and key=='activationLabel' and item=='Open':continue
  if source==99904 and key in ('name','values'):continue
  if source==127 and key=='ignoreCase' and item is False:continue
  if source in (99999,99998) and key=='timeout' and item==30:continue
  if 11001<=source<=11008 and key=='deviceId' and not item:continue
  if 11001<=source<=11008 and key=='state':item=str(item)
  if source in (205,206) and key=='resetToOriginal':continue
  if source==203 and key=='rewards':
   from .original_rewards import original
   raw['states']=original(item);continue
  if target not in allowed:
   raise ValueError('Unteraktion '+str(kind)+': Option „'+key+'“ hat keine Originalformat-Zuordnung. Linux-JSON erhält diese Einstellung.')
  raw[target]=copy.deepcopy(item)
 if 'subActions' in value:raw['subActions']=[(convert_child or node)(child) for child in value['subActions']]
 if source==99903:raw['caseSensitive']=not value.get('_originalCaseIgnoreCase',True)
 if source in (205,206) and value.get('resetToOriginal'):raw['title' if source==205 else 'prompt']=''
 # There is no safe general inverse for conveniences with a different output
 # contract (native file lines use arrays, original lines use indexed args).
 if migrated.get('_originalSemantics') and source not in (10,16,18,23,579):
  raise ValueError('Unteraktion '+str(kind)+' verwendet andere Ausgabewerte als das Original. Bitte Linux-JSON exportieren.')
 return raw

def trigger(value):
 from .original_triggers import MAPPING,FLAGS,flag_original
 from .next_catalog import triggers
 choices=[key for key,entry in MAPPING.items() if entry['native']==value['type']]
 if len(choices)!=1:raise ValueError('Trigger '+str(value['type'])+' besitzt keine eindeutige Originalformat-Zuordnung.')
 source=choices[0];allowed=set(TRIGGER_SCHEMAS.get(str(source),('id','type','enabled','exclusions')))
 raw={'id':value['id'],'type':source,'enabled':value.get('enabled',True),'exclusions':copy.deepcopy(value.get('exclusions',[]))}
 defaults=triggers()[value['type']][1]
 renames={'rangeMin':'min','rangeMax':'max','voiceCommandId':'commandId','midiDeviceId':'midiDevice'}
 if 'serverId' in allowed:renames['connectionId']='serverId'
 elif 'clientId' in allowed:renames['connectionId']='clientId'
 for key,item in value.items():
  if key.startswith('_') or key in ('id','type','enabled','exclusions'):continue
  target=renames.get(key,key)
  if key=='voiceCommandId' and target=='commandId' and not item:item=ZERO
  if key=='obsConnection' and 'obsId' in allowed:target='obsId';item=None if item=='any' else ZERO if item in ('default','__local__','',None) else item
  if key in FLAGS and key in allowed:item=flag_original(key,item)
  if key=='anonymous' and 'subType' in allowed:
   target='subType'
   try:item=('either','anonymous','public').index(item)
   except ValueError:raise ValueError('Original-Gift-Typ ist nicht darstellbar.') from None
  if key=='persisted' and key in allowed:
   try:item=('either',True,False).index(item)
   except ValueError:raise ValueError('Original-Persisted-Filter ist nicht darstellbar.') from None
  if target not in allowed:
   if key in defaults and item==defaults[key]:continue
   raise ValueError('Neuer Trigger: Filter „'+key+'“ benötigt eine geprüfte Originalformat-Zuordnung.')
  raw[target]=copy.deepcopy(item)
 if 'min' in allowed and 'max' in allowed and value['type']!=92503 and raw.get('min',-1)<0 and raw.get('max',-1)>=0:
  raw['min']=0
 return raw

def action(value,convert_node,convert_trigger):
 renames={'excludeHistory':'excludeFromHistory','random':'randomAction'}
 allowed=('id','name','group','enabled','queue','alwaysRun','concurrent','excludeHistory','random','excludeFromPending','collapsedGroups')
 raw={renames.get(key,key):copy.deepcopy(value[key]) for key in allowed if key in value}
 raw.setdefault('queue',None);raw.setdefault('group','');raw.setdefault('excludeFromHistory',False);raw.setdefault('excludeFromPending',False);raw.setdefault('alwaysRun',False);raw.setdefault('randomAction',False);raw.setdefault('concurrent',False);raw.setdefault('collapsedGroups',[])
 raw['triggers']=[convert_trigger(t) for t in value.get('triggers',[])]
 raw['subActions']=[convert_node(n) for n in value.get('subActions',[])]
 return raw

def dependencies(result,document,context):
 """Include explicitly referenced commands, timers and WebSocket definitions."""
 from .core import walk
 from .original_graph import canonical
 context=context or {};wanted={'commands':set(),'timers':set(),'websocketServers':set(),'websocketClients':set()}
 for action in result['data']['actions']:
  for row in [*action.get('triggers',[]),*walk(action.get('subActions',[]))]:
   for key,section in (('commandId','commands'),('timerId','timers'),('serverId','websocketServers'),('clientId','websocketClients')):
    if key=='commandId' and row.get('type') not in (9,1014,401,402):continue
    if canonical(row.get(key)):wanted[section].add(row[key])
 fields={
  'commands':set('id name enabled include mode command regexExplicitCapture location ignoreBotAccount ignoreInternal sources persistCounter persistUserCounter caseSensitive globalCooldown userCooldown group grantType permittedUsers permittedGroups'.split()),
  'timers':set('id name enabled repeat interval randomInterval upperInterval lines counter'.split()),
 }
 for section,identities in wanted.items():
  if not identities:continue
  target=result['data'].setdefault(section,[])
  for identity in identities:
   old=next((r for r in target if r.get('id')==identity),None)
   context_section='websocketConnections' if section.startswith('websocket') else section
   if old is not None and context_section not in context:continue
   rows=context.get(section,document.get(section,document.get('originalResources',{}).get(section,[])))
   if section.startswith('websocket'):
    mode='client' if section=='websocketClients' else 'server'
    rows=context.get('websocketConnections',document.get('originalResources',{}).get('websocketConnections',[]))
    source=next((r for r in rows if r.get('id')==identity and r.get('mode')==mode),None)
   else:source=next((r for r in rows if r.get('id')==identity),None)
   if source is None:
    if old is not None:continue
    raise ValueError('Originalexport: referenzierte Abhängigkeit fehlt: '+section+' '+identity)
   raw=copy.deepcopy(old) if old else {'id':identity}
   if section.startswith('websocket'):
    raw.update(name=source['name'],enabled=source.get('enabled',False),enableCompression=source.get('enableCompression',False))
    if mode=='client':raw.update(endpoint=source['url'],reconnectOnDisconnect=source.get('reconnect',True),retryInterval=source.get('retryInterval',3))
    else:raw.update(address='127.0.0.1',port=source['port'],endpoint=source.get('endpoint','/'))
   else:
    for key,item in source.items():
     if key.startswith('_') or key=='migrationBlock':continue
     mapped={'ignoreInternalMessages':'ignoreInternal','permissionMode':'grantType'}.get(key,key) if section=='commands' else key
     if key=='permissionMode':
      if item not in ('allow','deny'):raise ValueError('Unbekannter Command-Rechtemodus beim Originalexport.')
      item=int(item=='deny')
     if mapped not in fields[section]:raise ValueError('Originalexport: Option „'+key+'“ der Abhängigkeit '+section+' ist nicht darstellbar.')
     if section=='commands' and key=='permittedUsers' and item and item!=(old or {}).get('permittedUsers'):
      raise ValueError('Originalexport: Command-Nutzerrechte benötigen eine Original-ID-/Login-Zuordnung; Linux-JSON erhält die vorhandenen Rechte.')
     raw[mapped]=copy.deepcopy(item)
   if old is None:target.append(raw)
   else:old.update(raw)
