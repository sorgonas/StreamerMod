"""Local authenticated StreamerMod webhooks on the managed HTTP service."""
import re
from aiohttp import web
from .core import ActionError

EVENT=97050

def install(app,studio):
 async def receive(request):
  if not studio.live:raise ActionError('Webhooks benötigen den Live-Modus')
  name=request.match_info['name']
  if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',name):raise ActionError('Ungültiger Webhook-Name')
  body=await request.json()
  if not isinstance(body,dict):raise ActionError('Webhook benötigt ein JSON-Objekt')
  # Preserve payload as data; it cannot override action/user/trigger metadata.
  await studio.dispatcher.event(EVENT,{'webhookName':name,'webhookData':body},webhookName=name)
  return web.Response(status=204)
 app.router.add_post('/api/webhooks/{name}',receive)
