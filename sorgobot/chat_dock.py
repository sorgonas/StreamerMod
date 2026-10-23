"""Local OBS chat/event docks, with separate preferences and explicit one-way sync."""
import copy,hashlib,hmac,json,uuid
from aiohttp import web
from .catalog import ConfigStore
from .core import ActionError
STUDIO=web.AppKey("chat_dock_studio",object)

def key(studio):
 return hashlib.sha256(('StreamerMod local chat dock\0'+studio.services.websocket_password()).encode()).hexdigest()
def authorized(studio,request):
 if not studio.live:return False
 value=request.headers.get('X-StreamerMod-Dock-Key','')
 return len(value)==64 and hmac.compare_digest(value,key(studio))
def url(studio,events=False):
 from .original_websocket import mutable
 mutable(studio)
 return 'http://127.0.0.1:8766/chat-dock'+('?events=1' if events else '')+'#'+key(studio)
def sync(store):
 store.save('chat-dock-sync.json',{'revision':str(uuid.uuid4())})
def snapshot(studio):
 from .chat_settings import read
 from .chat_events import snapshot as events
 store=ConfigStore(studio.root)
 try:revision=store.read('chat-dock-sync.json')['revision']
 except (FileNotFoundError,ValueError,KeyError,TypeError):revision=''
 from .youtube_events import combined_messages
 return {'chat':combined_messages(studio),'events':events(studio),'settings':read(store),'revision':revision,
         'historyReset':getattr(studio,'chat_history_reset',0),'overlayReset':getattr(studio,'chat_overlay_reset',0)}
async def page(request):
 studio=request.app[STUDIO]
 return web.Response(text=(studio.webroot/'chat-dock.html').read_text(encoding='utf-8'),content_type='text/html',headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer','Content-Security-Policy':"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'unsafe-inline'; img-src https://static-cdn.jtvnw.net https://cdn.betterttv.net https://cdn.frankerfacez.com https://cdn.7tv.app; connect-src 'self'; frame-ancestors 'none'"})
async def api(request):
 studio=request.app[STUDIO]
 if not authorized(studio,request):raise web.HTTPForbidden(text='Dock-Link im Chatfenster erneut kopieren')
 headers={'Cache-Control':'no-store'}
 if request.method=='GET':return web.json_response(snapshot(studio),headers=headers)
 try:
  data=await request.json()
  if not isinstance(data,dict):raise ValueError('Dock-Anfrage')
  operation=data.get('operation')
  if operation=='send':
   from .chat_commands import send
   result=await send(studio,{**data,'internal':True})
   if isinstance(result,dict) and 'success' in result:return web.json_response(result,status=200 if result['success'] else 400,headers=headers)
  elif operation=='quick':
   from .chat_events import execute
   # Accept only a real retained chat/event row, never caller-supplied context.
   from .chat_settings import read
   quick=next((q for q in read(ConfigStore(studio.root))['quickActions'] if q['id']==data.get('quickId')),None)
   if quick is None:raise ActionError('Quick Action nicht gefunden')
   row=None
   if quick['scope']=='event':row={'id':data.get('rowId')}
   elif quick['scope']!='global':
    from .youtube_events import combined_messages
    row=next((r for r in reversed(combined_messages(studio)) if r.get('id')==data.get('rowId') and r.get('platform','twitch')==data.get('platform','twitch')),None)
    if row is None:raise ActionError('Chatnachricht ist nicht mehr verfügbar')
   if quick['scope']=='global':row={'platform':data.get('platform','twitch')}
   execute(studio,ConfigStore(studio.root),{'quickId':quick['id'],'row':row})
  else:raise ValueError('Dock-Befehl')
  return web.json_response({'success':True},headers=headers)
 except (ActionError,ValueError,TypeError,KeyError,RecursionError) as exc:
  return web.json_response({'success':False,'error':str(exc) or 'Ungültige Dock-Anfrage'},status=400,headers=headers)
def install(app,studio):
 app[STUDIO]=studio
 app.add_routes([web.get('/chat-dock',page),web.get('/api/chat-dock',api),web.post('/api/chat-dock',api)])
