"""Authenticated direct StreamerMod instances. No third-party relay/account."""
import asyncio,copy,hmac,ipaddress,json,platform,secrets,uuid
from collections import deque
from urllib.parse import urlsplit
from aiohttp import web,ClientError,ClientTimeout
from .core import ActionError,expand
from .youtube_auth import private_write

EVENT=97250
RESERVED={'actionid','actionname','runningactionid','actionqueuedat','__source','eventsource','nativetriggertype','eventtypeknown','eventtypemapping','instanceid','instancename','instanceos','instanceversion','eventname','signalname','signaltimeout','hasresult'}

def clean(values):
 if not isinstance(values,dict) or any(not isinstance(key,str) for key in values):raise ActionError('Remote-Argumente müssen ein JSON-Objekt sein')
 result={key:copy.deepcopy(value) for key,value in values.items() if key.casefold() not in RESERVED and not key.startswith('_')}
 try:
  if len(json.dumps(result,allow_nan=False).encode())>48000:raise ValueError()
 except (ValueError,TypeError,RecursionError):raise ActionError('Ungültige oder zu große Remote-Argumente') from None
 return result

class Signals:
 def __init__(self):self.pending=deque();self.waiters=[]
 def send(self,sender,name,data):
  for selected,expected,future in list(self.waiters):
   if expected==name and (not selected or selected==sender) and not future.done():future.set_result(data);return
  if len(self.pending)>=1000:raise ActionError('Remote-Signal-Warteschlange ist voll')
  self.pending.append((sender,name,data))
 async def wait(self,sender,name,timeout):
  for row in self.pending:
   if row[1]==name and (not sender or sender==row[0]):self.pending.remove(row);return row[2]
  future=asyncio.get_running_loop().create_future();row=(sender,name,future);self.waiters.append(row)
  try:return await asyncio.wait_for(future,timeout)
  finally:self.waiters.remove(row)
 def close(self):
  for _,_,future in self.waiters:
   if not future.done():future.cancel()
  self.pending.clear()

def validate(config):
 result=copy.deepcopy(config)
 try:result['instanceId']=str(uuid.UUID(result['instanceId']))
 except (KeyError,ValueError,TypeError,AttributeError):raise ActionError('Eigene Remote-Instanz-ID ist ungültig') from None
 if not isinstance(result.get('token'),str) or not 32<=len(result['token'])<=200:raise ActionError('Eigener Remote-Zugangsschlüssel ist ungültig')
 if type(result.get('enabled')) is not bool:raise ActionError('Remote-Aktivierung ist ungültig')
 try:ipaddress.ip_address(result['bind'])
 except (ValueError,KeyError,TypeError):raise ActionError('Remote-Bind-Adresse muss eine IP-Adresse sein') from None
 if type(result.get('port')) is not int or not 1024<=result['port']<=65535 or result['port'] in (8059,8766):raise ActionError('Remote-Port 1024–65535 wählen; 8059/8766 sind reserviert')
 if not isinstance(result.get('name'),str) or not 1<=len(result['name'].strip())<=100:raise ActionError('Instanzname fehlt oder ist zu lang')
 if not isinstance(result.get('peers'),list) or len(result['peers'])>50:raise ActionError('Höchstens 50 Remote-Instanzen möglich')
 seen=set()
 for peer in result['peers']:
  if not isinstance(peer,dict):raise ActionError('Ungültige Remote-Instanz')
  try:identity=str(uuid.UUID(peer['id']));url=urlsplit(peer['url'])
  except (KeyError,TypeError,ValueError):raise ActionError('Remote-Instanz-ID oder URL ist ungültig') from None
  if identity in seen or identity==result['instanceId']:raise ActionError('Doppelte oder eigene Remote-Instanz-ID')
  seen.add(identity)
  if url.scheme not in ('http','https') or not url.hostname or url.username or url.password or url.query or url.fragment or url.path not in ('','/'):raise ActionError('Remote-Basisadresse mit http:// oder https:// angeben')
  try:url.port
  except ValueError:raise ActionError('Ungültiger Remote-Port') from None
  if not isinstance(peer.get('token'),str) or not 32<=len(peer['token'])<=200:raise ActionError('Zugangsschlüssel der Zielinstanz fehlt')
  if not isinstance(peer.get('name'),str) or not 1<=len(peer['name'])<=100:raise ActionError('Name der Zielinstanz fehlt')
  peer['id']=identity;peer['url']=peer['url'].rstrip('/')
 return result

class Remote:
 def __init__(self,studio):
  self.studio=studio;self.path=studio.root/'config/streamermod-remote.private.json'
  self.config={'enabled':True,'bind':'127.0.0.1','port':8060,'name':'StreamerMod','instanceId':str(uuid.uuid4()),'token':secrets.token_urlsafe(32),'peers':[]}
  if self.path.exists():self.config=validate(json.loads(self.path.read_text()))
  self.runner=None;self.error='';self.signals=Signals();self.seen=deque(maxlen=2048);self.tasks=set();self.lock=asyncio.Lock()
 def status(self):
  return {'running':self.runner is not None,'error':self.error,'settings':{key:copy.deepcopy(value) for key,value in self.config.items() if key not in ('token','peers')},'peers':[{key:value for key,value in peer.items() if key!='token'} for peer in self.config['peers']]}
 async def start(self):
  if not self.studio.live:return
  if not self.path.exists():private_write(self.path,self.config)
  if not self.config['enabled']:return
  @web.middleware
  async def guard(request,handler):
   if request.headers.get('Origin') or request.headers.get('Sec-Fetch-Site')=='cross-site':raise web.HTTPForbidden()
   token=request.headers.get('X-StreamerMod-Token','')
   if not hmac.compare_digest(token.encode(),self.config['token'].encode()):raise web.HTTPForbidden()
   try:return await handler(request)
   except (ActionError,ValueError,TypeError,KeyError,RecursionError):raise web.HTTPBadRequest(text='Ungültige Remote-Anfrage') from None
  app=web.Application(middlewares=[guard],client_max_size=65536)
  async def info(request):return web.json_response(self.identity())
  app.router.add_get('/remote/info',info);app.router.add_post('/remote/event',self.receive)
  runner=web.AppRunner(app,access_log=None);await runner.setup()
  try:await web.TCPSite(runner,self.config['bind'],self.config['port']).start()
  except (OSError,ValueError):
   await runner.cleanup();self.error='Remote-Adresse/Port nicht verfügbar';return
  self.runner=runner;self.error=''
 def identity(self):return {'instanceId':self.config['instanceId'],'instanceName':self.config['name'],'instanceOs':platform.system().lower(),'instanceVersion':'StreamerMod-direct-1'}
 async def save(self,value):
  if not self.studio.live:raise ActionError('Remote-Einstellungen nur im Live-Modus speichern')
  async with self.lock:
   candidate={**self.config,**{key:value[key] for key in ('enabled','bind','port','name') if key in value}}
   if 'peers' in value:
    if not isinstance(value['peers'],list):raise ActionError('Remote-Ziele müssen eine Liste sein')
    previous={peer['id']:peer for peer in self.config['peers']};candidate['peers']=copy.deepcopy(value['peers'])
    for peer in candidate['peers']:
     if isinstance(peer,dict) and not peer.get('token'):peer['token']=previous.get(peer.get('id'),{}).get('token','')
   candidate=validate(candidate);old=self.config
   await self.stop_listener();self.config=candidate
   try:
    await self.start()
    if candidate['enabled'] and not self.runner:raise ActionError(self.error)
    private_write(self.path,candidate)
   except (ActionError,OSError):
    await self.stop_listener();self.config=old;await self.start();raise
  return self.status()
 async def receive(self,request):
  data=await request.json()
  if not isinstance(data,dict):raise ActionError('Objekt fehlt')
  identity=str(uuid.UUID(data['id']));sender=data['sender'];sender_id=str(uuid.UUID(sender['instanceId']))
  if sender_id==self.config['instanceId']:raise ActionError('Remote-Selbstschleife abgewiesen')
  if identity in self.seen:raise web.HTTPConflict(text='Remote-Ereignis bereits empfangen')
  kind=data['kind'];name=data['name'];values=clean(data.get('arguments',{}))
  if kind not in ('signal','trigger') or not isinstance(name,str) or not 1<=len(name)<=200:raise ActionError('Ungültiges Remote-Ereignis')
  for key in ('instanceName','instanceOs','instanceVersion'):
   if not isinstance(sender.get(key),str) or len(sender[key])>100:raise ActionError('Ungültige Instanzdaten')
  if len(self.tasks)>=100:raise web.HTTPServiceUnavailable(text='Remote-Eingang ausgelastet')
  metadata={key:sender[key] for key in ('instanceName','instanceOs','instanceVersion')};metadata['instanceId']=sender_id
  if kind=='signal':self.signals.send(sender_id,name,{'values':values,'metadata':metadata})
  else:
   async def dispatch():
    try:await self.studio.dispatcher.event(EVENT,{**values,**metadata,'eventName':name},instanceId=sender_id,eventName=name)
    except Exception:self.studio.io.trace('remote_event_error',message='Remote-Action fehlgeschlagen')
   task=asyncio.create_task(dispatch());self.tasks.add(task);task.add_done_callback(self.tasks.discard)
  self.seen.append(identity);return web.Response(status=204)
 async def send(self,kind,node,args):
  selected=node.get('instanceId','');peers=[peer for peer in self.config['peers'] if not selected or peer['id']==selected]
  if not peers:raise ActionError('Zielinstanz unter Integrations → StreamerMod Remote einrichten')
  name=node.get('signalName' if kind=='signal' else 'eventName','')
  if not isinstance(name,str) or not 1<=len(name)<=200:raise ActionError('Remote-Signal-/Ereignisname fehlt')
  extra=node.get('arguments',{})
  if not isinstance(extra,dict):raise ActionError('Remote-Argumente müssen ein JSON-Objekt sein')
  values=clean({**(args if node.get('includeArguments') else {}),**{key:expand(value,args) for key,value in extra.items()}})
  body={'id':str(uuid.uuid4()),'sender':self.identity(),'kind':kind,'name':name,'arguments':values}
  # Validate all destinations before writing; never retry an ambiguous write.
  for peer in peers:
   try:
    async with self.studio.session.get(peer['url']+'/remote/info',headers={'X-StreamerMod-Token':peer['token']},timeout=ClientTimeout(total=8),allow_redirects=False) as response:
     if response.status!=200 or (await response.json())['instanceId']!=peer['id']:raise ActionError('Remote-Identität oder Zugang stimmt nicht')
   except (ClientError,TimeoutError,ValueError,KeyError):raise ActionError('Zielinstanz nicht erreichbar oder ungültig') from None
  for peer in peers:
   try:
    async with self.studio.session.post(peer['url']+'/remote/event',json=body,headers={'X-StreamerMod-Token':peer['token']},timeout=ClientTimeout(total=8),allow_redirects=False) as response:
     if response.status!=204:raise ActionError('Remote-Ereignis abgewiesen; bereits erreichte Ziele nicht automatisch wiederholen')
   except (ClientError,TimeoutError):raise ActionError('Remote-Ergebnis unklar; nicht automatisch wiederholen') from None
  args['remoteSent']=len(peers)
 async def stop_listener(self):
  if self.runner:await self.runner.cleanup();self.runner=None
 async def close(self):
  await self.stop_listener();self.signals.close()
  for task in list(self.tasks):task.cancel()
  if self.tasks:await asyncio.gather(*list(self.tasks),return_exceptions=True)

async def operation(io,node,args):
 if io.dry_run:io.trace('streamermod_remote',operation=node['type'],simulated=True);return
 remote=getattr(getattr(getattr(io,'engine',None),'studio',None),'remote',None)
 if remote is None:raise ActionError('Remote-Laufzeit nicht verfügbar')
 if node['type'] in (97200,97201):return await remote.send('signal' if node['type']==97200 else 'trigger',node,args)
 name=node.get('signalName','')
 if not name:raise ActionError('Remote-Signalname fehlt')
 try:timeout=float(node.get('timeout') or 30000)
 except (TypeError,ValueError):raise ActionError('Ungültige Remote-Wartezeit') from None
 if not 0<timeout<=300000:raise ActionError('Remote-Wartezeit: 1–300000 ms')
 try:result=await remote.signals.wait(node.get('instanceId',''),name,timeout/1000)
 except TimeoutError:args['signalTimeout']=True;return
 for key,value in result['values'].items():
  if node.get('overwrite',True) or key not in args:args[key]=value
 args.update(result['metadata'],signalName=name,signalTimeout=False,hasResult=bool(result['values']))
