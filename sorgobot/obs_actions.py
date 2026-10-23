"""Composable OBS WebSocket 5 actions; no camera-provider dependencies."""
import math
import random
import re
from .core import ActionError

ENTRIES = {
 90300:('Get Current Scene',{'resultVariable':'obsScene'}),
 90301:('Get Status',{'resultVariable':'obsStatus'}),
 90302:('Sources · Set Source Mute State',{'sourceName':'','state':'enabled'}),
 90303:('Sources · Set Source Volume',{'sourceName':'','volume':100.0}),
 90304:('Sources · Set Source Filter State',{'sourceName':'','filterName':'','state':'enabled'}),
 90305:('Scenes · Get Scene Item Properties',{'sceneName':'','sourceName':'','resultVariable':'obsSource'}),
 90306:('Sources · Set Source Transform',{'sceneName':'','sourceName':'','transform':{'positionX':0.0,'positionY':0.0}}),
 90307:('Sources · Rotate Source',{'sceneName':'','sourceName':'','rotation':0.0,'relative':True}),
 90308:('Sources · Flip Source',{'sceneName':'','sourceName':'','axis':'horizontal'}),
 90309:('Scenes · Hide Scene Sources',{'sceneName':''}),
 90310:('Sources · Set Media State',{'sourceName':'','state':'restart'}),
 90311:('Recording · Recording',{'state':'start'}),
 90312:('Streaming · Streaming',{'state':'start'}),
 90313:('Replay · Set Replay Buffer State',{'state':'start'}),
 90314:('Replay · Save Replay Buffer',{}),
 90315:('Raw',{'requestType':'GetVersion','requestData':{},'resultVariable':'obsResult'}),
 90316:('Create Record Chapter',{'chapterName':'%game%'}),
 90317:('Filters · Set State of a Random Filter',{'sceneName':'','sourceName':'','state':'enabled'}),
 90318:('Groups · Set Random Group Source Visible',{'sceneName':'','groupName':''}),
 90319:('Scenes · Set Random Scene Source Visible',{'sceneName':''}),
 90320:('Scenes · Set Scene Filter State',{'sceneName':'','filterName':'','state':'enabled'}),
 90321:("Sources · Hide Group's Sources",{'sceneName':'','groupName':''}),
 90322:("Sources · Hide Source's Filters",{'sceneName':'','sourceName':''}),
 90323:('Sources · Set Color Source Color',{'sceneName':'','sourceName':'','randomColor':False,'color':'#FFFFFFFF'}),
 90324:('Sources · Set Source Audio Track State',{'sceneName':'','sourceName':'','track':1,'state':'enabled'}),
}
CHOICES={
 'state':('enabled','disabled','toggle'),
 'axis':('horizontal','vertical','both'),
}

def finite(value):
 try:result=float(value)
 except (TypeError,ValueError):raise ActionError('OBS-Zahlenwert ist ungültig') from None
 if not math.isfinite(result):raise ActionError('OBS-Zahlenwert muss endlich sein')
 return result

def state(value,current):
 if value=='toggle':return not current
 if value not in ('enabled','disabled'):raise ActionError('OBS-Zustand muss enabled, disabled oder toggle sein')
 return value=='enabled'

async def operation(io,n,args):
 from .core import expand
 def resolve(value):
  if isinstance(value,dict):return {k:resolve(v) for k,v in value.items()}
  if isinstance(value,list):return [resolve(v) for v in value]
  if isinstance(value,str) and value.startswith('%') and value.endswith('%') and value.count('%')==2:
   matched=next((v for k,v in args.items() if str(k).casefold()==value[1:-1].casefold()),None)
   if matched is not None:return matched
  return expand(value,args)
 if n.get('_originalObs'):
  from .original_obs import operation as imported_obs
  return await imported_obs(io,n,args)
 n=resolve(n)
 t=n['type'];call=io.obs_call
 source=io.config.get('source_aliases',{}).get(n.get('sourceName',''),n.get('sourceName',''))
 async def scene():
  return n.get('sceneName') or (await call('GetCurrentProgramScene'))['currentProgramSceneName']
 async def item():
  name=await scene();identity=(await call('GetSceneItemId',sceneName=name,sourceName=source))['sceneItemId'];return {'sceneName':name,'sceneItemId':identity}
 def save(value,default):args[n.get('resultVariable') or default]=value
 if 'sourceName' in n and not source:raise ActionError('OBS-Quellenname fehlt')
 if t==90300:
  result=await call('GetCurrentProgramScene');args['obsSceneName']=result['currentProgramSceneName'];args['currentScene']=result['currentProgramSceneName'];save(result['currentProgramSceneName'],'obsScene')
 elif t==90301:
  stream=await call('GetStreamStatus');record=await call('GetRecordStatus');replay=await call('GetReplayBufferStatus');save({'stream':stream,'record':record,'replay':replay},'obsStatus');args.update(obsStreaming=stream['outputActive'],obsRecording=record['outputActive'],obsReplayBufferActive=replay['outputActive'])
 elif t==90302:
  current=(await call('GetInputMute',inputName=source)).get('inputMuted',False) if n['state']=='toggle' else False
  await call('SetInputMute',inputName=source,inputMuted=state(n['state'],current))
 elif t==90303:
  volume=finite(n['volume'])
  if not 0<=volume<=100:raise ActionError('OBS-Lautstärke muss zwischen 0 und 100 liegen')
  await call('SetInputVolume',inputName=source,inputVolumeMul=volume/100)
 elif t==90304:
  if not n.get('filterName'):raise ActionError('OBS-Filtername fehlt')
  current=(await call('GetSourceFilter',sourceName=source,filterName=n['filterName'])).get('filterEnabled',False) if n['state']=='toggle' else False
  await call('SetSourceFilterEnabled',sourceName=source,filterName=n['filterName'],filterEnabled=state(n['state'],current))
 elif t==90305:
  identity=await item();transform=(await call('GetSceneItemTransform',**identity)).get('sceneItemTransform',{});enabled=(await call('GetSceneItemEnabled',**identity)).get('sceneItemEnabled',False);save(dict(identity,sourceName=source,enabled=enabled,transform=transform),'obsSource')
 elif t in (90306,90307,90308):
  identity=await item()
  if t==90306:
   transform=n['transform']
   if not isinstance(transform,dict) or not transform:raise ActionError('OBS-Transform muss ein nicht leeres JSON-Objekt sein')
  else:
   current=(await call('GetSceneItemTransform',**identity)).get('sceneItemTransform',{})
   if t==90307:transform={'rotation':(finite(current.get('rotation',0)) if n.get('relative',True) else 0)+finite(n['rotation'])}
   else:
    if n['axis'] not in ('horizontal','vertical','both'):raise ActionError('OBS-Achse muss horizontal, vertical oder both sein')
    keys=('scaleX','scaleY') if n['axis']=='both' else ('scaleX',) if n['axis']=='horizontal' else ('scaleY',)
    transform={key:-finite(current.get(key,1)) for key in keys}
  await call('SetSceneItemTransform',**identity,sceneItemTransform=transform)
 elif t==90309:
  name=await scene()
  for entry in (await call('GetSceneItemList',sceneName=name)).get('sceneItems',[]):
   if entry.get('sceneItemEnabled',False):await call('SetSceneItemEnabled',sceneName=name,sceneItemId=entry['sceneItemId'],sceneItemEnabled=False)
 elif t==90310:
  actions={s:'OBS_WEBSOCKET_MEDIA_INPUT_ACTION_'+s.upper() for s in ('play','pause','stop','restart','next','previous')}
  if n['state'] not in actions:raise ActionError('Unbekannter OBS-Medienzustand')
  await call('TriggerMediaInputAction',inputName=source,mediaAction=actions[n['state']])
 elif t in (90311,90312,90313):
  target={90311:'Record',90312:'Stream',90313:'ReplayBuffer'}[t];prefix={'start':'Start','stop':'Stop','toggle':'Toggle','pause':'Pause','resume':'Resume'}
  allowed=('start','stop','toggle','pause','resume') if t==90311 else ('start','stop','toggle')
  if n['state'] not in allowed:raise ActionError('Unbekannter OBS-Ausgabezustand')
  await call(prefix[n['state']]+target)
 elif t==90314:await call('SaveReplayBuffer')
 elif t==90315:
  if not isinstance(n['requestData'],dict) or not str(n['requestType']).strip():raise ActionError('OBS Raw benötigt Request Type und JSON-Objekt')
  save(await call(n['requestType'],**n['requestData']),'obsResult')
 elif t==90316:
  if not str(n.get('chapterName','')).strip():raise ActionError('OBS-Kapitelname fehlt')
  args['success']=False
  await call('CreateRecordChapter',chapterName=n['chapterName']);args['success']=True
 elif t in (90318,90319,90321):
  if t in (90318,90321) and not n.get('groupName'):raise ActionError('OBS-Gruppenname fehlt')
  name=n['groupName'] if t in (90318,90321) else await scene()
  entries=(await call('GetGroupSceneItemList' if t in (90318,90321) else 'GetSceneItemList',sceneName=name)).get('sceneItems',[])
  if t==90321:
   for entry in entries:
    if entry.get('sceneItemEnabled'):await call('SetSceneItemEnabled',sceneName=name,sceneItemId=entry['sceneItemId'],sceneItemEnabled=False)
  else:
   args['randomSource']='';hidden=[e for e in entries if not e.get('sceneItemEnabled',False)]
   if hidden:
    selected=random.choice(hidden);await call('SetSceneItemEnabled',sceneName=name,sceneItemId=selected['sceneItemId'],sceneItemEnabled=True);args['randomSource']=selected['sourceName']
 elif t in (90317,90320,90322):
  target=await scene() if t==90320 else source
  if t==90320:
   if not n.get('filterName'):raise ActionError('OBS-Filtername fehlt')
   filters=[await call('GetSourceFilter',sourceName=target,filterName=n['filterName'])]
   filters[0]['filterName']=n['filterName']
  else:filters=(await call('GetSourceFilterList',sourceName=target)).get('filters',[])
  if t==90317 and filters:filters=[random.choice(filters)]
  for f in filters:
   enabled=False if t==90322 else state(n['state'],f.get('filterEnabled',False))
   if enabled!=f.get('filterEnabled',False):await call('SetSourceFilterEnabled',sourceName=target,filterName=f['filterName'],filterEnabled=enabled)
 elif t==90323:
  color=n.get('color','')
  if n.get('randomColor'):color='#'+format(random.randrange(2**24),'06X')+'FF'
  if not isinstance(color,str) or not re.fullmatch(r'#[0-9a-fA-F]{8}',color):raise ActionError('OBS-Farbe benötigt #RRGGBBAA')
  r,g,b,a=(int(color[i:i+2],16) for i in (1,3,5,7));encoded=r|(g<<8)|(b<<16)|(a<<24)
  await call('SetInputSettings',inputName=source,inputSettings={'color':encoded},overlay=True)
 elif t==90324:
  track=n.get('track')
  if isinstance(track,bool) or not str(track).isdigit() or not 1<=int(track)<=6:raise ActionError('OBS-Audiospur muss zwischen 1 und 6 liegen')
  tracks=dict((await call('GetInputAudioTracks',inputName=source)).get('inputAudioTracks',{}));key=str(int(track));tracks[key]=state(n['state'],tracks.get(key,False))
  await call('SetInputAudioTracks',inputName=source,inputAudioTracks=tracks)
 else:raise ActionError('Unbekannte OBS-Unteraktion')

EVENTS = {
 'SceneItemEnableStateChanged':(90350,'Sources · Source Visibility Changed',{'sceneName':''}),
 'InputMuteStateChanged':(90351,'Sources · Source Mute Changed',{'inputName':''}),
 'InputVolumeChanged':(90352,'Sources · Source Volume Changed',{'inputName':''}),
 'SourceFilterEnableStateChanged':(90353,'Filters · Filter State Changed',{'sourceName':'','filterName':''}),
 'MediaInputPlaybackStarted':(90354,'Media · Playback Started',{'inputName':''}),
 'MediaInputPlaybackEnded':(90355,'Media · Playback Ended',{'inputName':''}),
}
OUTPUT_EVENTS={
 'RecordStateChanged':{'OBS_WEBSOCKET_OUTPUT_STARTED':(90356,'Recording · Recording Started'),'OBS_WEBSOCKET_OUTPUT_STOPPED':(90357,'Recording · Recording Stopped'),'OBS_WEBSOCKET_OUTPUT_PAUSED':(90358,'Recording · Recording Paused'),'OBS_WEBSOCKET_OUTPUT_RESUMED':(90359,'Recording · Recording Resumed')},
 'ReplayBufferStateChanged':{'OBS_WEBSOCKET_OUTPUT_STARTED':(90360,'Replay · Replay Buffer Started'),'OBS_WEBSOCKET_OUTPUT_STOPPED':(90361,'Replay · Replay Buffer Stopped')},
 'ReplayBufferSaved':{'':(90362,'Replay · Replay Buffer Saved')},
}
def event(kind,data):
 if kind in EVENTS:
  identity,_,fields=EVENTS[kind];return identity,dict(data),{key:data.get(key,'') for key in fields if key!='obsConnection'}
 output=OUTPUT_EVENTS.get(kind,{}).get(data.get('outputState',''))
 if output:return output[0],dict(data),{}
 return None


CONNECTION_TRIGGERS={
 90363:('Connected',{}),90364:('Disconnected',{}),
 90365:('Event',{'eventName':'CurrentProgramSceneChanged'}),
 90366:('Vendor Event',{'vendorName':'','eventName':''}),
}

def flatten(value,prefix,result):
 if isinstance(value,dict):
  for key,item in value.items():flatten(item,prefix+'.'+str(key),result)
 elif isinstance(value,list):
  for index,item in enumerate(value):flatten(item,prefix+'['+str(index)+']',result)
 else:result[prefix]=value

def general_events(kind,data,metadata):
 if kind in ('OBSConnected','OBSDisconnected'):
  return [(90363 if kind=='OBSConnected' else 90364,dict(data),{})]
 args=dict(metadata);flatten(dict(data,event=kind),'obsEvent',args)
 events=[(90365,args,{'eventName':kind})]
 if kind=='VendorEvent':
  vendor=dict(metadata);vendor['obsVendorEvent.vendor']=data.get('vendorName','');vendor['obsVendorEvent.event']=data.get('eventType','')
  flatten(data.get('eventData',{}),'obsVendorEvent.data',vendor)
  events.append((90366,vendor,{'vendorName':data.get('vendorName',''),'eventName':data.get('eventType','')}))
 return events
