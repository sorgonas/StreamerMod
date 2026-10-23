"""Original OBS argument contracts, inside IO's selected connection context."""
import json
from .core import ActionError,expand
from .obs_actions import flatten

def resolve(value,args):
 if isinstance(value,dict):return {k:resolve(v,args) for k,v in value.items()}
 if isinstance(value,list):return [resolve(v,args) for v in value]
 if isinstance(value,str) and value.startswith('%') and value.endswith('%') and value.count('%')==2:
  for key,item in args.items():
   if str(key).casefold()==value[1:-1].casefold():return item
 return expand(value,args)

async def operation(io,node,args):
 kind=node['_originalObs'];call=io.obs_call
 if kind==328:
  pool=io.obs_pool;identity=io.obs_context.get();client=pool.get() if identity is None else pool.clients[identity]
  connected=not io.dry_run and client.ready.is_set()
  args.update({'obs.isConnected':connected,'obs.isStreaming':False,'obs.isRecording':False})
  if connected:
   args['obs.isStreaming']=bool((await call('GetStreamStatus'))['outputActive'])
   args['obs.isRecording']=bool((await call('GetRecordStatus'))['outputActive'])
  return
 if kind==46:
  try:
   raw=json.loads(node.get('raw',''),parse_constant=lambda value:(_ for _ in ()).throw(ValueError(value)))
  except (ValueError,TypeError):raise ActionError('OBS Raw benötigt gültiges JSON.') from None
  raw=resolve(raw,args)
  if not isinstance(raw,dict):raise ActionError('OBS Raw benötigt ein JSON-Objekt.')
  if 'requests' in raw:
   requests=raw['requests'];halt=raw.get('haltOnFailure',False);execution=raw.get('executionType',0)
   if not isinstance(requests,list) or type(halt) is not bool or type(execution) is not int or execution not in (0,1,2):raise ActionError('Ungültige OBS-Raw-Batchoptionen.')
  else:requests=[raw]
  if any(not isinstance(r,dict) or not isinstance(r.get('requestType'),str) or not r['requestType'].strip() or not isinstance(r.get('requestData',{}),dict) for r in requests):raise ActionError('OBS Raw benötigt requestType und requestData als Objekt.')
  if 'requests' in raw:result=await io.obs_batch(requests,halt,execution)
  else:result=await call(raw['requestType'],**raw.get('requestData',{}))
  if node.get('resultsToArgs',True):
   prefix=expand(node.get('prefix',''),args)
   if not isinstance(prefix,str):raise ActionError('OBS-Raw-Präfix muss Text sein.')
   # JToken.Path uses dotted objects and bracketed array indices.
   variables={};flatten(result,prefix,variables)
   args.update({key.lstrip('.') if not prefix else key:value for key,value in variables.items()})
   args[(prefix+'.' if prefix else '')+'_json']=json.dumps(result,ensure_ascii=False,separators=(',',':'))
  return
 if kind!=324:raise ActionError('Unbekannter Original-OBS-Vertrag.')
 n=resolve(node,args);scene=n.get('sceneName') or (await call('GetCurrentProgramScene'))['currentProgramSceneName']
 source=io.config.get('source_aliases',{}).get(n.get('sourceName'),n.get('sourceName'))
 if not source:raise ActionError('OBS-Quellenname fehlt.')
 async def properties(container,name,depth=0):
  if depth>16:raise ActionError('OBS-Gruppe ist zu tief verschachtelt.')
  rows=(await call('GetSceneItemList' if depth==0 else 'GetGroupSceneItemList',sceneName=container)).get('sceneItems',[])
  entry=next((r for r in rows if r.get('sourceName')==name),None)
  if entry is None:raise ActionError('OBS-Szenenelement wurde nicht gefunden.')
  identity={'sceneName':container,'sceneItemId':entry['sceneItemId']}
  tr=(await call('GetSceneItemTransform',**identity))['sceneItemTransform']
  muted=False
  # Scenes and groups have no input mute property. Request it only for audio inputs.
  if entry.get('inputKind'):
   try:muted=bool((await call('GetInputMute',inputName=name))['inputMuted'])
   except ActionError as exc:
    if not str(exc).startswith('OBS GetInputMute (604):'):raise
  result={'name':name,'itemId':entry['sceneItemId'],'visible':bool(entry.get('sceneItemEnabled')),'locked':bool(entry.get('sceneItemLocked')),'muted':muted,
   'position':{'x':tr.get('positionX',0),'y':tr.get('positionY',0),'alignment':tr.get('alignment',0)},
   'scale':{'x':tr.get('scaleX',1),'y':tr.get('scaleY',1),'filter':None},
   'bounds':{'x':tr.get('boundsWidth',0),'y':tr.get('boundsHeight',0),'type':tr.get('boundsType','OBS_BOUNDS_NONE'),'alignment':tr.get('boundsAlignment',0)},
   'crop':{k:tr.get('crop'+k.title(),0) for k in ('left','right','top','bottom')},'rotation':tr.get('rotation',0),'status':'ok'}
  for key in ('height','width','sourceHeight','sourceWidth'):result[key]=tr.get(key,0)
  # The legacy scale filter has no OBS WebSocket 5 request. Preserve an
  # explicit unavailable value instead of manufacturing OBS_SCALE_DISABLE.
  result['compatibilityWarnings']=['scale.filter is unavailable in OBS WebSocket 5']
  if entry.get('isGroup'):
   children=(await call('GetGroupSceneItemList',sceneName=name)).get('sceneItems',[])
   result['groupChildren']=[await properties(name,c['sourceName'],depth+1) for c in children]
  return result
 result=await properties(scene,source)
 flatten(result,'props',args);args['props._json']=json.dumps(result,ensure_ascii=False,separators=(',',':'))
