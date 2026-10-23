"""Native PulseAudio/PipeWire controls; no Wave Link protocol emulation."""
import asyncio,copy,json,math,os,shutil
from .core import ActionError

KINDS={'output':('sinks','sink'),'input':('sources','source'),'application':('sink-inputs','sink-input'),'application-input':('source-outputs','source-output')}
STEPS={
94000:('List Audio Devices and Applications',{}),
94001:('Get Volume',{'audioKind':'output','audioTarget':'@default'}),
94002:('Set Volume',{'audioKind':'output','audioTarget':'@default','audioOperation':'set','audioVolume':'50'}),
94003:('Set Mute',{'audioKind':'output','audioTarget':'@default','audioMute':'toggle'}),
94004:('Set Default Device',{'audioKind':'output','audioTarget':'@default'}),
94005:('Move Application to Device',{'audioKind':'application','audioTarget':'','audioDevice':'@default'}),
}
TRIGGERS={94050:('Connected',{}),94051:('Disconnected',{})}
for kind,label in [(94052,'Volume Changed'),(94053,'Mute Changed'),(94054,'Device Added'),(94055,'Device Removed'),(94056,'Application Started'),(94057,'Application Stopped'),(94058,'Default Device Changed')]:TRIGGERS[kind]=(label,{'audioKind':'any','audioTarget':''})

def identity(row):return (row['kind'],row['index'],row['name'],row.get('client'),row.get('processId'))

def variables(row):
 return {'audioKind':row.get('kind',''),'audioTarget':row.get('selector',''),'audioName':row.get('label',''),'audioDeviceName':row.get('name',''),'audioIndex':row.get('index',-1),'audioVolume':row.get('volume',0),'audioMuted':row.get('mute',False),'audioDefault':row.get('default',False),'audioChannels':copy.deepcopy(row.get('channels',[]))}

def matches(kind,trigger,args):
 if kind not in TRIGGERS:return True
 wanted=trigger.get('audioKind','any');target=trigger.get('audioTarget','')
 if wanted not in ('any','',args.get('audioKind')):return False
 if not target:return True
 if target=='@default':return bool(args.get('audioDefault'))
 return str(target).casefold() in {str(args.get(key,'')).casefold() for key in ('audioTarget','audioDeviceName','audioName')}

async def command(*arguments):
 binary=shutil.which('pactl')
 if not binary:raise ActionError('Linux-Audio benötigt pactl (Paket pulseaudio-utils).')
 env=dict(os.environ,LC_ALL='C.UTF-8')
 process=await asyncio.create_subprocess_exec(binary,*map(str,arguments),stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,env=env)
 try:
  output,error=await asyncio.wait_for(process.communicate(),5)
 except BaseException:
  if process.returncode is None:
   try:process.kill()
   except ProcessLookupError:pass
  await process.wait();raise
 if process.returncode:raise ActionError('Audiodienst hat die Anfrage abgewiesen oder ist nicht erreichbar.')
 if len(output)>8*1024**2:raise ActionError('Audioantwort ist zu groß.')
 return output.decode('utf-8')

async def request(*arguments):
 try:return json.loads(await command('--format=json',*arguments))
 except (json.JSONDecodeError,UnicodeError):raise ActionError('pactl liefert keine gültigen JSON-Audiodaten.') from None

def normalize(kind,rows,default=''):
 if not isinstance(rows,list):raise ActionError('Ungültige Audioliste.')
 result=[]
 for item in rows:
  if not isinstance(item,dict):raise ActionError('Ungültige Audioquelle.')
  index=item.get('index');props=item.get('properties') or {};volumes=item.get('volume') or {}
  if type(index) is not int or index<0 or not isinstance(props,dict) or not isinstance(volumes,dict):raise ActionError('Ungültige Audioquelle.')
  if any(not isinstance(v,dict) or 'value' not in v for v in volumes.values()):raise ActionError('Ungültiger Audiokanal.')
  if item.get('client') is not None and not isinstance(item['client'],(str,int)):raise ActionError('Ungültiger Audio-Client.')
  channels=[v['value'] for v in volumes.values()]
  if any(type(v) is not int or v<0 for v in channels):raise ActionError('Ungültiger Audiokanal.')
  device=kind in ('output','input');name=item.get('name','') if device else str(props.get('application.process.binary') or props.get('application.name') or index)
  if device:
   if not isinstance(name,str) or not name:raise ActionError('Audiogerätename fehlt.')
   selector=name;label=item.get('description') or name
  else:
   appid=props.get('application.id') or props.get('pipewire.access.portal.app_id')
   selector='id:'+str(appid) if appid else 'binary:'+str(props['application.process.binary']) if props.get('application.process.binary') else 'name:'+str(props.get('application.name') or index)
   label=props.get('application.name') or name
  result.append({'kind':kind,'index':index,'name':str(name),'selector':selector,'label':str(label),'volume':round(max(channels,default=0)/65536*100,3),'mute':bool(item.get('mute')),'channels':channels,'default':device and name==default,'client':item.get('client'),'processId':str(props.get('application.process.id','')),'deviceIndex':item.get('sink') if kind=='application' else item.get('source')})
 return result

class Audio:
 def __init__(self,studio,execute=command,query=request):
  self.studio=studio;self.execute=execute;self.query=query;self.lock=asyncio.Lock();self.last=None;self.connected=False
 def status(self):return {'available':self.connected,'items':copy.deepcopy(self.last or []),'polling':self.wanted()}
 def wanted(self):return any(a.get('enabled',True) and any(t.get('enabled',True) and t['type'] in TRIGGERS for t in a.get('triggers',[])) for a in self.studio.engine.actions.values())
 async def snapshot(self):
  async with self.lock:
   info=await self.query('info')
   if not isinstance(info,dict):raise ActionError('Ungültiger Audio-Serverstatus.')
   rows=[]
   lists=await asyncio.gather(*(self.query('list',plural) for plural,singular in KINDS.values()))
   for (kind,_),values in zip(KINDS.items(),lists):rows.extend(normalize(kind,values,info.get('default_sink_name' if kind=='output' else 'default_source_name','')))
   return rows
 def emit(self,kind,args):
  if self.studio.live and not self.studio.closing:self.studio.engine.core_events.emit(kind,args)
 async def refresh(self):
  try:rows=await self.snapshot()
  except (ActionError,OSError,TimeoutError):
   if self.connected:self.emit(94051,{})
   self.connected=False;self.last=None;raise
  old=self.last if self.connected else None
  if not self.connected:self.emit(94050,{})
  self.connected=True;self.last=rows
  if old is not None:
   before={identity(r):r for r in old};after={identity(r):r for r in rows}
   for key,row in before.items():
    if key not in after:self.emit(94055 if row['kind'] in ('input','output') else 94057,variables(row))
   for key,row in after.items():
    if key not in before:self.emit(94054 if row['kind'] in ('input','output') else 94056,variables(row));continue
    previous=before[key]
    if row['channels']!=previous['channels']:self.emit(94052,{**variables(row),'audioPreviousVolume':previous['volume']})
    if row['mute']!=previous['mute']:self.emit(94053,{**variables(row),'audioPreviousMuted':previous['mute']})
    if row['default'] and not previous['default']:self.emit(94058,variables(row))
  return rows
 async def run(self):
  while not self.studio.closing:
   if self.wanted():
    try:await self.refresh()
    except (ActionError,OSError,TimeoutError):pass
   await asyncio.sleep(2)
 def select(self,rows,kind,target):
  if kind not in KINDS:raise ActionError('Unbekannte Audio-Zielart.')
  if not isinstance(target,str) or not target.strip():raise ActionError('Audioziel fehlt. Unter Stream Apps → Linux Audio eine ID auswählen.')
  if target=='@all':
   selected=[r for r in rows if r['kind']==kind and (kind!='input' or not r['name'].endswith('.monitor'))]
  else:selected=[r for r in rows if r['kind']==kind and (target=='@default' and r['default'] or target!='@default' and target.casefold() in {r['selector'].casefold(),r['name'].casefold(),r['label'].casefold()})]
  if not selected:raise ActionError('Audioziel ist derzeit nicht verbunden oder spielt keinen Audiostream.')
  if target!='@all' and kind in ('input','output') and len(selected)!=1:raise ActionError('Mehrdeutiges Audiogerät; eindeutigen Gerätenamen wählen.')
  return selected
 async def current(self,row):
  plural=KINDS[row['kind']][0]
  fresh=next((r for r in normalize(row['kind'],await self.query('list',plural)) if identity(r)==identity(row)),None)
  if not fresh:raise ActionError('Audioziel wurde während des Aufrufs entfernt oder ersetzt; keine automatische Wiederholung.')
  return fresh
 async def operate(self,node,args,dry_run=False):
  kind=node['type']
  if kind==94000:
   rows=await self.snapshot();args.update(audioDevices=rows,audioDevicesCount=len(rows));return
  target_kind=node.get('audioKind','output');target=node.get('audioTarget','@default')
  if target=='@all' and (kind!=94003 or target_kind not in ('input','output')):raise ActionError('@all ist nur für die Stummschaltung aller Ein-/Ausgabegeräte vorgesehen.')
  if kind==94004 and target_kind not in ('input','output'):raise ActionError('Standardgerät muss ein Ein- oder Ausgabegerät sein.')
  if kind==94005 and target_kind not in ('application','application-input'):raise ActionError('Verschieben benötigt eine Anwendung als Audioziel.')
  if kind==94002:
   try:value=float(node.get('audioVolume',50))
   except (ValueError,TypeError):raise ActionError('Audiolautstärke muss eine Zahl sein.') from None
   if not math.isfinite(value) or not (-100 if node.get('audioOperation')=='adjust' else 0)<=value<=100:raise ActionError('Lautstärke 0–100; Änderung bei adjust von -100 bis +100.')
   if node.get('audioOperation','set') not in ('set','increase','decrease','adjust'):raise ActionError('Unbekannte Lautstärkeoperation.')
  if kind==94003 and str(node.get('audioMute','toggle')).lower() not in ('on','off','toggle'):raise ActionError('Mute muss on, off oder toggle sein.')
  rows=await self.snapshot();selected=self.select(rows,target_kind,target);device=None
  if kind==94005:device=self.select(rows,'output' if target_kind=='application' else 'input',node.get('audioDevice',''))[0]
  args.update(variables(selected[0]),audioTargetsCount=len(selected),audioResults=[variables(row) for row in selected] if kind==94001 else [])
  if kind==94001:return
  if dry_run:
   self.studio.io.trace('linux_audio',operation=STEPS[kind][0],simulated=True);return
  async with self.lock:
   mute=str(node.get('audioMute','toggle')).lower()
   if kind==94003 and target=='@all' and mute=='toggle':
    fresh_rows=[await self.current(row) for row in selected]
    mute='off' if all(row['mute'] for row in fresh_rows) else 'on'
   for row in selected:
    fresh=await self.current(row);singular=KINDS[target_kind][1]
    if kind==94002:
     old=max(fresh['channels'],default=0);percent=old/65536*100
     desired={'set':value,'increase':min(100,percent+value),'decrease':max(0,percent-value),'adjust':max(0,min(100,percent+value))}[node.get('audioOperation','set')]
     scale=desired*65536/100
     channels=[round(v/old*scale) if old else round(scale) for v in fresh['channels']]
     if not channels:raise ActionError('Audioziel hat keine einstellbaren Lautstärkekanäle.')
     await self.execute('set-'+singular+'-volume',row['index'],*channels)
    elif kind==94003:await self.execute('set-'+singular+'-mute',row['index'],{'on':'1','off':'0','toggle':'toggle'}[mute])
    elif kind==94004:
     if fresh['name'].startswith('-'):raise ActionError('Ungültiger Gerätename.')
     await self.execute('set-default-'+singular,fresh['name'])
    elif kind==94005:
     await self.current(device);await self.execute('move-'+singular,row['index'],device['index'])
    else:raise ActionError('Unbekannte Audiooperation.')
    try:observed=await self.current(row)
    except (ActionError,OSError,TimeoutError):raise ActionError('Audioauftrag gesendet, aber Status nicht bestätigt. Ergebnis prüfen; nicht automatisch wiederholen.') from None
    observed['default']=row['default']
    if kind==94004:
     info=await self.query('info');observed['default']=observed['name']==info.get('default_sink_name' if target_kind=='output' else 'default_source_name')
    args['audioResults'].append(variables(observed))
    if len(args['audioResults'])==1:args.update(variables(observed))
  args['audioApplied']=True

async def operation(io,node,args):
 studio=getattr(getattr(io,'engine',None),'studio',None)
 audio=getattr(studio,'audio',None)
 if audio is None:raise ActionError('Linux-Audiodienst ist nicht verfügbar.')
 await audio.operate(node,args,dry_run=io.dry_run)
