"""Google Desktop OAuth with PKCE, one-use loopback state and private token files."""
import asyncio,base64,copy,hashlib,hmac,json,os,re,secrets,time
from pathlib import Path
from urllib.parse import urlencode
from aiohttp import web,ClientTimeout,ClientError
from .core import ActionError
SCOPE='https://www.googleapis.com/auth/youtube.force-ssl'
TOKEN='https://oauth2.googleapis.com/token'
AUTHORIZE='https://accounts.google.com/o/oauth2/v2/auth'
API='https://www.googleapis.com/youtube/v3/'
class YouTubeError(ActionError):
 def __init__(self,reason,status=0):self.reason=reason;self.status=status;super().__init__('YouTube: '+reason)
def private_write(path,value):
 path.parent.mkdir(parents=True,exist_ok=True);temporary=path.with_name(path.name+'.'+secrets.token_hex(8)+'.tmp')
 try:
  fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
  with os.fdopen(fd,'w') as f:json.dump(value,f,ensure_ascii=False,allow_nan=False)
  temporary.replace(path)
 finally:temporary.unlink(missing_ok=True)
def read_private(path):
 try:
  value=json.loads(path.read_text())
  return value if isinstance(value,dict) else {}
 except FileNotFoundError:return {}
 except (ValueError,OSError):raise ActionError('YouTube-Konfigurationsdatei ist ungültig') from None
class YouTubeOAuth:
 def __init__(self,studio,role='broadcaster'):
  self.studio=studio;self.root=Path(studio.root);self.client_path=self.root/'config/youtube-client.private.json';self.account_path=self.root/('config/youtube-bot.private.json' if role=='bot' else 'config/youtube-account.private.json')
  self.client=read_private(self.client_path);self.account=read_private(self.account_path);self.pending=None;self.epoch=0;self.refresh_lock=asyncio.Lock();self.login_lock=asyncio.Lock();self.state='saved' if self.account.get('refresh_token') else 'disconnected'
 def mutable(self):
  from .original_websocket import mutable
  mutable(self.studio)
 def identity(self):return self.epoch,self.account.get('channelId','')
 def status(self):return {'state':self.state,'configured':bool(self.client.get('client_id')),'channelId':self.account.get('channelId',''),'channelTitle':self.account.get('channelTitle',''),'connected':self.state=='valid'}
 async def configure(self,value):
  self.mutable()
  if not isinstance(value,dict) or not isinstance(value.get('installed'),dict):raise ActionError('Google-Client-JSON einer Desktop-App auswählen')
  raw=value['installed'];client=raw.get('client_id');secret=raw.get('client_secret')
  if not isinstance(client,str) or not re.fullmatch(r'[A-Za-z0-9_-]+\.apps\.googleusercontent\.com',client) or not isinstance(secret,str) or not 1<=len(secret)<=500:raise ActionError('Ungültiger Google-Desktop-Client')
  if self.account and client!=self.client.get('client_id'):raise ActionError('Vor einem Wechsel des Google-Clients zuerst das YouTube-Konto abmelden')
  await self.cancel();self.client={'client_id':client,'client_secret':secret};private_write(self.client_path,self.client);return self.status()
 async def token_request(self,data):
  try:
   async with self.studio.session.post(TOKEN,data=data,timeout=ClientTimeout(total=25)) as response:
    value=await response.json()
    if response.status!=200 or not isinstance(value,dict):
     reason=value.get('error') if isinstance(value,dict) else ''
     raise YouTubeError(reason if reason in ('invalid_grant','invalid_client','access_denied') else 'Anmeldung fehlgeschlagen',response.status)
    if not isinstance(value.get('access_token'),str) or not value['access_token'] or type(value.get('expires_in')) is not int or value['expires_in']<=0:raise YouTubeError('Ungültige Token-Antwort')
    if not isinstance(value.get('scope',SCOPE),str) or SCOPE not in value.get('scope',SCOPE).split():raise YouTubeError('Die YouTube-Chatfreigabe fehlt')
    return value
  except (ValueError,TypeError,ClientError,TimeoutError):raise YouTubeError('Anmeldedienst nicht erreichbar oder Antwort ungültig') from None
 async def access_token(self,force=False):
  self.mutable()
  async with self.refresh_lock:
   if not self.account.get('refresh_token'):raise YouTubeError('Zuerst das YouTube-Konto anmelden')
   if not force and self.account.get('access_token') and self.account.get('expires_at',0)>time.time()+60:return self.account['access_token']
   before=self.identity();saved=copy.deepcopy(self.account)
   try:value=await self.token_request({'client_id':self.client['client_id'],'client_secret':self.client['client_secret'],'refresh_token':saved['refresh_token'],'grant_type':'refresh_token'})
   except YouTubeError:
    if before==self.identity():self.state='error'
    raise
   if before!=self.identity():raise YouTubeError('Konto während der Anmeldung geändert')
   self.account.update(access_token=value['access_token'],expires_at=time.time()+value['expires_in'],refresh_token=value.get('refresh_token',saved['refresh_token']))
   private_write(self.account_path,self.account);self.state='valid';return self.account['access_token']
 async def begin(self):
  self.mutable()
  if not self.client.get('client_id'):raise ActionError('Zuerst unter YouTube → Einrichtung die Google-Desktop-Client-JSON importieren')
  await self.cancel();state=secrets.token_urlsafe(32);verifier=secrets.token_urlsafe(64)
  pending={'state':state,'verifier':verifier,'epoch':self.epoch,'expires':time.monotonic()+600,'future':asyncio.get_running_loop().create_future()};self.pending=pending
  app=web.Application(client_max_size=8192)
  async def callback(request):
   if request.remote not in ('127.0.0.1','::1') or self.pending is not pending or pending['future'].done() or not hmac.compare_digest(request.query.get('state','').encode(),state.encode()):raise web.HTTPBadRequest(text='Ungültige oder abgelaufene Anmeldung')
   code=request.query.get('code','');error=request.query.get('error','')
   if not code and not error:raise web.HTTPBadRequest(text='Anmeldeantwort fehlt')
   pending['future'].set_result({'code':code,'error':error})
   return web.Response(text='YouTube-Anmeldung empfangen. Du kannst zu StreamerMod zurückkehren.',headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer','Content-Security-Policy':"default-src 'none'"})
  app.router.add_get('/oauth/youtube',callback);runner=web.AppRunner(app,access_log=None);await runner.setup()
  try:
   site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
  except BaseException:await runner.cleanup();self.pending=None;raise
  pending['runner']=runner;pending['redirect']='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1])+'/oauth/youtube'
  challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
  return {'state':'pending','url':AUTHORIZE+'?'+urlencode({'client_id':self.client['client_id'],'redirect_uri':pending['redirect'],'response_type':'code','scope':SCOPE,'state':state,'code_challenge':challenge,'code_challenge_method':'S256','access_type':'offline','prompt':'consent select_account'})}
 async def poll(self):
  self.mutable()
  async with self.login_lock:
   pending=self.pending
   if not pending:return {'state':'cancelled'}
   if time.monotonic()>pending['expires']:await self.cancel();return {'state':'error','message':'YouTube-Anmeldung ist abgelaufen'}
   if not pending['future'].done():return {'state':'pending'}
   result=pending['future'].result()
   if result['error']:await self.cancel();return {'state':'error','message':'YouTube-Anmeldung wurde nicht freigegeben'}
   try:
    value=await self.token_request({'client_id':self.client['client_id'],'client_secret':self.client['client_secret'],'code':result['code'],'code_verifier':pending['verifier'],'redirect_uri':pending['redirect'],'grant_type':'authorization_code'})
    async with self.studio.session.get(API+'channels',params={'part':'snippet','mine':'true'},headers={'Authorization':'Bearer '+value['access_token']},timeout=ClientTimeout(total=20)) as response:
     data=await response.json()
     if response.status!=200:raise YouTubeError('YouTube-Kanal konnte nicht geprüft werden',response.status)
    rows=data.get('items',[]) if isinstance(data,dict) else []
    if not isinstance(rows,list) or len(rows)!=1 or not isinstance(rows[0],dict) or not isinstance(rows[0].get('snippet',{}),dict) or not isinstance(rows[0].get('id'),str) or not rows[0]['id']:raise YouTubeError('Bei Google genau den gewünschten YouTube-Kanal auswählen')
    if self.pending is not pending or pending['epoch']!=self.epoch:raise YouTubeError('Anmeldung wurde inzwischen geändert')
    refresh=value.get('refresh_token')
    if not isinstance(refresh,str) or not refresh:raise YouTubeError('Google hat keine dauerhafte Freigabe geliefert; erneut anmelden')
    self.account={'access_token':value['access_token'],'refresh_token':refresh,'expires_at':time.time()+value['expires_in'],'channelId':rows[0]['id'],'channelTitle':str(rows[0].get('snippet',{}).get('title',''))[:200]}
    private_write(self.account_path,self.account);self.epoch+=1;self.state='valid'
    return {**self.status(),'state':'connected'}
   except (ValueError,TypeError,ClientError,TimeoutError):raise YouTubeError('Kanalprüfung nicht erreichbar oder Antwort ungültig') from None
   finally:
    if self.pending is pending:await self.cancel()
 async def cancel(self):
  pending=self.pending;self.pending=None
  if pending:
   if not pending['future'].done():pending['future'].cancel()
   if pending.get('runner'):await pending['runner'].cleanup()
 async def forget(self):
  self.mutable();await self.cancel();self.epoch+=1;self.account={};self.state='disconnected';self.account_path.unlink(missing_ok=True);return self.status()
