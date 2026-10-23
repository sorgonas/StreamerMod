"""Native service controls shared by desktop pages and runtime, independent of actions."""
import asyncio,copy,hmac,json,time
from collections import deque
from aiohttp import web
from .catalog import ConfigStore
from .core import ActionError

SERVICE_PEERS=web.AppKey('streamermod-service-peers',set)

EVENTS=('Follows','Cheers','Subs','ReSubs','GiftSubs','GiftBombs','Raided','RewardRedemptions','GoalContributions','GameUpdates','Pyramids')
DEFAULTS={'process':{'autoStart':True},'voice':{'autoStart':True,'logDictation':False,'recognitionAutoStart':False,'locale':'de-DE','audioDevice':'@default','confidence':65,'mode':'dictation','engine':'whisper-base','vocabulary':'StreamerMod'},'credits':{'autoResetHours':0,'events':list(EVENTS),'presentRoles':[],'presentGroups':[],'presentUsers':[],'trackBits':False,'trackRewards':False},'websocket':{'autoStart':False,'port':8080,'endpoint':'/'},'http':{'autoStart':False,'port':7474,'originalProtocol':False},'udp':{'autoStart':False,'port':4242,'originalProtocol':False}}

def config(root):
 try:raw=ConfigStore(root).read('services.json')
 except FileNotFoundError:raw={}
 if not isinstance(raw,dict):raise ActionError('Ungültige Service-Konfiguration')
 if any(not isinstance(raw.get(key,{}),dict) for key in DEFAULTS):raise ActionError('Ungültige Service-Konfiguration')
 return {key:{**copy.deepcopy(value),**raw.get(key,{})} for key,value in DEFAULTS.items()}

def validate(section,value):
 if section not in DEFAULTS or not isinstance(value,dict) or set(value)!=set(DEFAULTS[section]):raise ActionError('Ungültige Service-Einstellungen')
 for key,default in DEFAULTS[section].items():
  item=value[key]
  if type(default) is bool and type(item) is not bool:raise ActionError('Schalter muss ein Wahrheitswert sein')
 if section in ('websocket','http','udp'):
  if type(value['port']) is not int or not 1024<=value['port']<=65535 or value['port'] in (8059,8766):raise ActionError('Port 1024–65535 wählen; 8059 und 8766 sind reserviert')
 if section=='websocket':
  path=value['endpoint']
  if not isinstance(path,str) or not path.startswith('/') or len(path)>100 or any(c in path for c in '{}?#\\') or any(c.isspace() for c in path):raise ActionError('Ungültiger WebSocket-Endpunkt')
 if section=='voice':
  from .speech_models import MODELS
  if not isinstance(value['vocabulary'],str) or len(value['vocabulary'])>1000 or any(ord(c)<32 for c in value['vocabulary']):raise ActionError('Wortschatzhinweise: höchstens 1000 Zeichen in einer Zeile')
  if value['engine'] not in ('vosk','whisper-small','whisper-base'):raise ActionError('Ungültige Spracherkennungsengine')
  if value['mode'] not in ('commands','dictation'):raise ActionError('Ungültiger Erkennungsmodus')
  if value['locale'] not in MODELS:raise ActionError('Nicht unterstützte Erkennungssprache')
  if type(value['confidence']) is not int or not 0<=value['confidence']<=100:raise ActionError('Erkennungsschwelle muss 0–100 Prozent betragen')
  if not isinstance(value['audioDevice'],str) or not value['audioDevice'] or len(value['audioDevice'])>500 or any(c in value['audioDevice'] for c in '\r\n\x00'):raise ActionError('Ungültiges Audiogerät')
 if section=='credits':
  if type(value['autoResetHours']) is not int or not 0<=value['autoResetHours']<=8760:raise ActionError('Auto Reset: 0–8760 Stunden')
  for key in ('presentRoles','presentGroups','presentUsers'):
   if not isinstance(value[key],list) or len(value[key])>1000 or any(not isinstance(v,str) or not v.strip() or len(v)>200 for v in value[key]):raise ActionError('Ungültige Credits-Nutzerauswahl')
  if any(v not in ('Editors','Moderators','Subscribers','VIPs') for v in value['presentRoles']):raise ActionError('Ungültige Credits-Rolle')
  if not isinstance(value['events'],list) or len(set(value['events']))!=len(value['events']) or any(v not in EVENTS for v in value['events']):raise ActionError('Ungültige Credits-Ereignisauswahl')
 return copy.deepcopy(value)

class Datagram(asyncio.DatagramProtocol):
 def __init__(self,owner):self.owner=owner
 def datagram_received(self,data,addr):
  if len(data)>65536 or len(self.owner.pending)>=32:return
  task=self.owner.studio.spawn(self.owner.datagram(data,addr));self.owner.pending.add(task);task.add_done_callback(self.owner.pending.discard)

class Services:
 def __init__(self,studio):
  self.studio=studio;self.settings=config(studio.root)
  for key,value in self.settings.items():validate(key,value)
  from .speech_recognition import Speech
  self.speech=Speech(studio)
  self.enabled={k:self.settings[k]['autoStart'] for k in ('process','voice')};self.runners={};self.transports={};self.errors={};self.logs={k:deque(maxlen=200) for k in ('process','voice','http','udp','websocket')};self.pending=set();self.lock=asyncio.Lock();self.closing=False
 def log(self,section,message):self.logs[section].append({'time':time.strftime('%H:%M:%S'),'message':message})
 async def start(self):
  if self.studio.live:
   if self.settings['voice']['recognitionAutoStart']:
    try:await self.control('voice',True)
    except ActionError as exc:self.speech.phase='error';self.speech.error=str(exc)
   for kind in ('http','websocket','udp'):
    if self.settings[kind]['autoStart']:
     try:await self.control(kind,True)
     except ActionError:pass # Status exposes bind failure; keep other services usable.
 def websocket_password(self):
  if not self.studio.live:raise ActionError('WebSocket-Passwort ist nur im Live-Modus verfügbar')
  from .websocket_auth import password
  return password(self.studio.root)
 async def set_websocket_password(self,value):
  async with self.lock:
   if not self.studio.live or self.closing:raise ActionError('Passwortänderung ist in dieser Laufzeit nicht verfügbar')
   if 'websocket' in self.runners:raise ActionError('WebSocket-Server vor Passwortänderung stoppen')
   from .websocket_auth import save
   save(self.studio.root,value)
  return self.status()
 async def refresh_voice(self):
  async with self.lock:
   if not self.closing:await self.speech.refresh_commands()
 async def save(self,section,value):
  if section not in DEFAULTS or not isinstance(value,dict):raise ActionError('Ungültige Service-Einstellungen')
  value=validate(section,{**self.settings[section],**value})
  async with self.lock:
   if section=='voice' and self.speech.download and any(value[k]!=self.settings[section][k] for k in ('locale','audioDevice','mode','engine','vocabulary')):raise ActionError('Modellinstallation vor dem Wechsel abschließen')
   if section=='voice' and self.speech.process and any(value[k]!=self.settings[section][k] for k in ('locale','audioDevice','mode','engine','vocabulary')):raise ActionError('Spracherkennung vor dem Wechsel von Sprache oder Gerät stoppen')
   if (section in self.runners or section in self.transports) and any(value.get(k)!=self.settings[section].get(k) for k in ('port','endpoint')):raise ActionError('Dienst vor dem Ändern der Adresse stoppen')
   document=copy.deepcopy(self.settings);document[section]=value
   # Client/server TCP listeners may not claim the same port.
   if document['http']['port']==document['websocket']['port']:raise ActionError('HTTP und WebSocket benötigen unterschiedliche TCP-Ports')
   if self.studio.live:ConfigStore(self.studio.root).save('services.json',document)
   self.settings=document
  return self.status()
 async def set_voice_input(self,device):
  """Change the local recognition input without starting an idle microphone."""
  async with self.lock:
   if not self.studio.live or self.closing:raise ActionError('Mikrofonwechsel ist in dieser Laufzeit nicht verfügbar')
   value=validate('voice',{**self.settings['voice'],'audioDevice':device})
   if not device.strip():raise ActionError('Mikrofon-Gerätename fehlt')
   if self.speech.download:raise ActionError('Modellinstallation vor dem Mikrofonwechsel abschließen')
   previous=self.settings['voice']['audioDevice']
   if device==previous:return {'voiceInputPrevious':previous,'voiceInput':device,'voiceInputChanged':False,'voiceRecognitionRestartRequested':False}
   audio=getattr(self.studio,'audio',None)
   if audio is None:raise ActionError('Audio-Geräteabfrage ist nicht verfügbar')
   rows=await audio.snapshot()
   if not any(row.get('kind')=='input' and (row.get('default') if device=='@default' else row.get('name')==device) for row in rows):raise ActionError('Gewünschtes Mikrofon ist nicht verbunden; Geräte unter Stream Apps → Linux Audio prüfen')
   running=self.speech.phase in ('starting','listening') or self.speech.process is not None
   if running:await self.speech.stop()
   document=copy.deepcopy(self.settings);document['voice']=value
   try:
    ConfigStore(self.studio.root).save('services.json',document);self.settings=document
    if running:await self.speech.start()
   except (ActionError,OSError) as exc:
    self.speech.phase='error';self.speech.error=str(exc);self.log('voice','Mikrofonwechsel fehlgeschlagen: '+str(exc));raise
   self.log('voice','Mikrofoneingang geändert: '+device)
   return {'voiceInputPrevious':previous,'voiceInput':device,'voiceInputChanged':True,'voiceRecognitionRestartRequested':running}
 def status(self):
  return {'settings':copy.deepcopy(self.settings),'live':self.studio.live,'process':{'running':bool(self.studio.live and self.enabled['process']),'logs':list(self.logs['process'])},'voice':{**self.speech.status(),'inputEnabled':self.enabled['voice'],'logs':list(self.logs['voice'])},**{k:{'running':k in self.runners or k in self.transports,'error':self.errors.get(k,''),'logs':list(self.logs[k])} for k in ('http','udp','websocket')},'clients':[{'address':peer['address'],'authenticated':peer['authenticated'],'subscriptions':sorted(source+'.'+event for source,event in peer['subscriptions'])} for ws,peer in getattr(getattr(self.studio,'main_websocket',None),'peers',{}).items() if peer.get('original') and not ws.closed]}
 async def control(self,section,running):
  if section not in ('process','voice','http','websocket','udp') or type(running) is not bool:raise ActionError('Ungültiger Dienstaufruf')
  if not self.studio.live:raise ActionError('Dienststeuerung ist nur im Live-Modus verfügbar')
  async with self.lock:
   if self.closing:raise ActionError('Dienste werden beendet')
   if section in self.enabled:
    self.enabled[section]=running
    if section=='process':
     self.studio.local_watchers.processes=None;self.log('process','Überwachung gestartet' if running else 'Überwachung gestoppt')
    else:
     if running:await self.speech.start()
     else:await self.speech.stop()
     self.log('voice','Voice-Eingang gestartet' if running else 'Voice-Eingang gestoppt')
   else:
    if running and (section in self.runners or section in self.transports):return self.status()
    await self.stop(section)
    if running:
     try:await self.listen(section);self.errors.pop(section,None)
     except (OSError,ValueError) as exc:
      self.errors[section]='Port nicht verfügbar oder ungültig';raise ActionError(self.errors[section]) from exc
  return self.status()
 async def listen(self,section):
  value=self.settings[section]
  if section=='websocket':self.websocket_password()
  if section=='udp':
   transport,_=await asyncio.get_running_loop().create_datagram_endpoint(lambda:Datagram(self),local_addr=('127.0.0.1',value['port']));self.transports[section]=transport;return
  @web.middleware
  async def guard(request,handler):
   if request.host.split(':')[0] not in ('127.0.0.1','localhost'):raise web.HTTPForbidden()
   origin=request.headers.get('Origin')
   ports={value['port']}
   if section=='websocket':ports.update((8766,self.settings['http']['port']))
   allowed={f'http://{host}:{port}' for host in ('127.0.0.1','localhost') for port in ports}
   if origin and origin not in allowed:raise web.HTTPForbidden()
   if request.headers.get('Sec-Fetch-Site')=='cross-site':raise web.HTTPForbidden()
   original=section=='http' and value.get('originalProtocol') and request.path in ('/DoAction','/ClearCredits','/ClearFirstWordsCache','/TestCredits')
   writes=request.method!='GET' or request.path in ('/ClearCredits','/ClearFirstWordsCache','/TestCredits')
   if ((writes and not original) or (section=='websocket' and 'X-Studio-Token' in request.headers)) and not hmac.compare_digest(request.headers.get('X-Studio-Token','').encode(),self.studio.token.encode()):raise web.HTTPForbidden()
   try:
    response=await handler(request);self.log(section,request.method+' '+request.path+' '+str(response.status));return response
   except ActionError as exc:raise web.HTTPBadRequest(text=str(exc)) from None
   except (ValueError,KeyError,TypeError,RecursionError):raise web.HTTPBadRequest(text='Ungültige Anfrage') from None
  app=web.Application(middlewares=[guard],client_max_size=65536)
  if section=='websocket':
   app[SERVICE_PEERS]=set()
   async def shutdown(app):await asyncio.gather(*(ws.close() for ws in list(app[SERVICE_PEERS])),return_exceptions=True)
   app.on_shutdown.append(shutdown)
   async def websocket(request):
    return await self.studio.legacy(request,original=True,authenticated='X-Studio-Token' in request.headers)
   app.router.add_get(value['endpoint'],websocket)
  else:
   app.router.add_get('/GetCredits',self.studio.get_credits);app.router.add_get('/credits',self.studio.credits_overlay)
   async def status(request):return web.json_response({'running':True,'name':'StreamerMod'})
   app.router.add_get('/api/status',status)
   app.router.add_post('/api/actions/{id}',self.studio.action)
   from .http_contracts import install
   install(app,self.studio)

  runner=web.AppRunner(app);await runner.setup()
  try:await web.TCPSite(runner,'127.0.0.1',value['port']).start()
  except BaseException:await runner.cleanup();raise
  self.runners[section]=runner
 async def datagram(self,raw,addr):
  try:
   data=json.loads(raw)
   if not isinstance(data,dict):raise ValueError()
   token=data.get('token')
   if token is not None:
    if not isinstance(token,str) or not hmac.compare_digest(token.encode(),self.studio.token.encode()):raise ValueError()
   elif not self.settings['udp']['originalProtocol']:raise ValueError()
   if data.get('request')!='DoAction':raise ValueError()
   from .server_contracts import execute
   execute(self.studio,data);self.log('udp','DoAction angenommen')
  except (ActionError,ValueError,TypeError,KeyError,UnicodeDecodeError,RecursionError):self.log('udp','Ungültiges oder nicht authentifiziertes Datagramm verworfen')

 async def stop(self,section):
  transport=self.transports.pop(section,None)
  if transport:transport.close()
  runner=self.runners.pop(section,None)
  if runner:await runner.cleanup()
 async def close(self):
  async with self.lock:
   self.closing=True
   await self.speech.close()
   for kind in ('http','websocket','udp'):await self.stop(kind)
   for task in list(self.pending):task.cancel()
   await asyncio.gather(*self.pending,return_exceptions=True)

async def credit_roles(engine,args):
 """Resolve editor presence only when selected and already authorized."""
 manager=getattr(getattr(engine,'studio',None),'services',None)
 if manager is None or 'Editors' not in manager.settings['credits']['presentRoles']:return args
 settings=getattr(engine.io,'config',{})
 if 'channel:read:editors' not in settings.get('twitch_scopes',[]) or getattr(engine.io,'dry_run',True):return args
 account=(settings.get('broadcaster_id'),settings.get('twitch_token'));cache=getattr(manager,'editor_cache',None)
 now=time.monotonic()
 if cache is None or cache[0]!=account or now-cache[1]>60:
  try:
   result=await engine.io.twitch('GET','channels/editors',params={'broadcaster_id':account[0]})
   if (settings.get('broadcaster_id'),settings.get('twitch_token'))!=account:return args
   rows=result.get('data')
   if not isinstance(rows,list) or any(not isinstance(r,dict) or not isinstance(r.get('user_id'),str) for r in rows):raise ValueError()
   cache=(account,now,{row['user_id'] for row in rows});manager.editor_cache=cache
  except (ActionError,OSError,ValueError,TypeError,asyncio.TimeoutError):
   manager.editor_cache=(account,now,set());return args
 if str(args.get('userId','')) in cache[2]:return dict(args,roles=list(dict.fromkeys([*args.get('roles',[]),'Editors'])))
 return args
