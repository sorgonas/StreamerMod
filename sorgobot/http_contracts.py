"""Original HTTP routes on the explicitly started local HTTP service."""
from aiohttp import web
from .core import ActionError

def public_credits(engine):
 from .csharp_core_services import credits_snapshot
 from .websocket_data import names
 raw=credits_snapshot(engine);users=raw.get('User',{})
 result={'Events':{key:names(rows) for key,rows in raw['Events'].items()},
  'HypeTrainConductor':names(raw.get('HypeTrainConductor',[])),
  'HypeTrainContributors':names(raw.get('HypeTrainContributors',[])),
  'User':{target:names(users.get(source,users.get(target,[]))) for target,source in [('Editors','Editors'),('Moderator','Moderators'),('Subscriber','Subscribers'),('VIPs','VIPs'),('Users','Users')]},
  'Custom':{key:names(rows) for key,rows in raw.get('Custom',{}).items() if isinstance(key,str) and isinstance(rows,list)},
  'TopBits':{key:names(raw.get('TopBits',{}).get(key,[])) for key in ('All','Month','Week')},
  'TopChannelRewards':names(raw.get('TopChannelRewards',[]))}
 result['User']['regulars']=names(users.get('regulars',[]))
 for key,rows in users.items():
  if isinstance(key,str) and key.startswith('Group: '):result['User'].setdefault(key[7:],names(rows))
 return result

def install(app,studio):
 from .server_contracts import execute,test_credits
 from .original_websocket import mutable
 async def actions(request):return web.json_response({'actions':[{'id':a['id'],'name':a['name']} for a in studio.engine.actions.values()]})
 async def action(request):
  execute(studio,await request.json());return web.Response(status=204)
 async def clear(request):
  mutable(studio)
  if request.path=='/ClearCredits':
   from .csharp_core_services import rpc
   await rpc(studio.engine,'credits',['reset'])
  else:studio.dispatcher.first_users.clear();studio.state.set('first_words_users',[])
  return web.Response(status=204)
 async def test(request):
  mutable(studio);test_credits(studio.engine);return web.json_response(public_credits(studio.engine))
 app.router.add_get('/GetActions',actions);app.router.add_post('/DoAction',action)
 for path in ('/ClearCredits','/ClearFirstWordsCache'):app.router.add_get(path,clear)
 app.router.add_get('/TestCredits',test)
 from .streamermod_webhooks import install as install_webhooks
 install_webhooks(app,studio)
 from .http_files import install as install_files
 install_files(app,studio)
