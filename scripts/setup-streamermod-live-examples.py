#!/usr/bin/env python3
"""Add named native alert examples, preserving existing actions and OBS sources."""
import asyncio,json,sys,uuid,shutil
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import aiohttp
from sorgobot.adapters import OBS
from sorgobot.next_catalog import triggers
from sorgobot.catalog import ConfigStore,new_action,new_step,validate_action
ROOT=Path(__file__).resolve().parents[1]
from sorgobot.catalog import PROMPTS
PROMPT_SPEC={label:{'kind':key,'instructions':PROMPTS[key][1],'data':''} for label,key in [('Willkommen','welcome'),('Follow','follow'),('Raid','raid'),('Abo','subscription')]}
ALERT='StreamerMod – Alerts';TEXT='StreamerMod – Alerttext';SCENE='StreamerMod – Funktionstest'
async def setup():
 store=ConfigStore(ROOT/'next-studio');cfg=store.read('local.json');doc=store.read('actions.json');
 if not cfg.get('channel'):raise ValueError('Bitte zuerst ein eigenes Twitch-Konto einrichten.')
 backup=ROOT/'state/live-examples-before-20261022';backup.mkdir(exist_ok=True)
 for name in ('actions.json','commands.json'):
  target=backup/name
  if not target.exists():shutil.copy2(store.root/'config'/name,target)
 async with aiohttp.ClientSession() as ses:
  o=OBS(ses,cfg);task=asyncio.create_task(o.listen());await asyncio.wait_for(o.ready.wait(),10)
  try:
   scenes={r['sceneName'] for r in (await o.call('GetSceneList'))['scenes']};inputs={r['inputName'] for r in (await o.call('GetInputList'))['inputs']}
   for name in (ALERT,SCENE):
    if name not in scenes:await o.call('CreateScene',sceneName=name)
   async def source(scene,name,kind,settings,enabled=True):
    if name not in inputs:
     await o.call('CreateInput',sceneName=scene,inputName=name,inputKind=kind,inputSettings=settings,sceneItemEnabled=enabled);inputs.add(name)
    return (await o.call('GetSceneItemId',sceneName=scene,sourceName=name))['sceneItemId']
   await source(SCENE,'StreamerMod – Testhintergrund','color_source_v3',{'color':4280814608,'width':1280,'height':720})
   title=await source(SCENE,'StreamerMod – Testtitel','text_ft2_source_v2',{'text':'STREAMERMOD | FUNKTIONSTEST','font':{'face':'DejaVu Sans','size':38,'style':'Bold'},'color1':4294967295,'color2':4294967295})
   await o.call('SetSceneItemTransform',sceneName=SCENE,sceneItemId=title,sceneItemTransform={'positionX':65.0,'positionY':65.0})
   note=await source(SCENE,'StreamerMod – Testhinweis','text_ft2_source_v2',{'text':'Willkommen · Follow · Raid · Abo\nKI-Texte + Twitch-Chat + OBS-Alerts\n\nTEST-Ereignisse sind simuliert.\nEs werden keine echten Follows oder Abos erzeugt.','font':{'face':'DejaVu Sans','size':26,'style':'Regular'},'color1':4291611852,'color2':4291611852})
   await o.call('SetSceneItemTransform',sceneName=SCENE,sceneItemId=note,sceneItemTransform={'positionX':65.0,'positionY':155.0})
   alert=await source(ALERT,TEXT,'text_ft2_source_v2',{'text':'','font':{'face':'DejaVu Sans','size':32,'style':'Bold'},'color1':4294967295,'color2':4294967295,'word_wrap':True,'custom_width':1120,'outline':True},False)
   await o.call('SetSceneItemTransform',sceneName=ALERT,sceneItemId=alert,sceneItemTransform={'positionX':70.0,'positionY':470.0})
   for name in (SCENE,'Chat','Gaming - Live'):
    existing=(await o.call('GetSceneItemList',sceneName=name))['sceneItems']
    if not any(r['sourceName']==ALERT for r in existing):await o.call('CreateSceneItem',sceneName=name,sourceName=ALERT,sceneItemEnabled=True)
   snapshot={name:await o.call('GetSceneItemList',sceneName=name) for name in (SCENE,ALERT)}
   (ROOT/'state/live-examples-obs-20261022.json').write_text(json.dumps(snapshot,indent=2))
  finally:task.cancel();await asyncio.gather(task,return_exceptions=True)
 def step(kind,**kw):return {**new_step(kind),**kw}
 queue=next((r for r in doc.get('queues',[]) if r.get('name')=='StreamerMod – Begrüßungen'),None)
 if not queue:
  queue={'id':str(uuid.uuid4()),'name':'StreamerMod – Begrüßungen','blocking':True,'paused':False};doc.setdefault('queues',[]).append(queue)
 group='StreamerMod – Stream-Actions';ids={}
 specs=[('Willkommen',120),('Follow',101),('Raid',107),('Abo',90850)]
 prompts=store.read('prompts.json')
 for entry in PROMPT_SPEC.values():prompts.setdefault(entry['kind'],entry['instructions'])
 store.save('prompts.json',prompts)
 for label,trigger in specs:
  promptkind=PROMPT_SPEC[label]['kind'];prompt=PROMPT_SPEC[label]['data']
  name=label+' – KI & OBS'
  action=next((a for a in doc['actions'] if a['group']==group and a['name']==name),None)
  if not action:
   action=new_action(name,group);action['queue']=queue['id'];action['triggers']=[{'id':str(uuid.uuid4()),'type':trigger,'enabled':True,**triggers()[trigger][1]}]
   action['subActions']=[step(50,userLogin='%userName%'),step(90004,prompt='',promptKind=promptkind,resultVariable='alertText',autoContext=True),step(10,text='%testPrefix%%alertText%',useBot=True),step(39,sceneName=ALERT,sourceName=TEXT,text='%testPrefix%%alertText%'),step(30,sceneName=ALERT,sourceName=TEXT,state=0),step(1002,value='12000'),step(30,sceneName=ALERT,sourceName=TEXT,state=1),step(90011,text=label+' ausgeführt: %testPrefix%%alertText%')]
   validate_action(action);doc['actions'].append(action)
  ids[label]=action['id']
  testname='TEST: '+label
  if not any(a['group']=='StreamerMod – Live-Tests' and a['name']==testname for a in doc['actions']):
   a=new_action(testname,'StreamerMod – Live-Tests');a['queue']=queue['id'];a['subActions']=[step(123,variableName=k,value=v) for k,v in {'user':cfg.get('channel',''),'userName':cfg.get('channel',''),'userLogin':cfg.get('channel',''),'viewers':7,'testPrefix':'[TEST '+label+'] '}.items()]+[step(4,actionId=action['id'])];doc['actions'].append(a)
 name='Teststream vorbereiten'
 if not any(a['group']=='StreamerMod – Live-Tests' and a['name']==name for a in doc['actions']):
  a=new_action(name,'StreamerMod – Live-Tests');a['subActions']=[step(15,title='Test | StreamerMod – KI, Chat und Alerts im Praxistest'),step(16,game='Just Chatting'),step(90005,sceneName=SCENE)];doc['actions'].append(a)
 store.save('actions.json',doc)
 proof={'eventActions':ids,'tests':{a['name']:a['id'] for a in doc['actions'] if a['group']=='StreamerMod – Live-Tests'},'scene':SCENE,'alertScene':ALERT,'queue':queue['id']};(ROOT/'state/live-examples-installed-20261022.json').write_text(json.dumps(proof,indent=2));print(json.dumps(proof,ensure_ascii=False,indent=2))
if __name__=='__main__':asyncio.run(setup())
