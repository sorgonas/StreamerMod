"""Documented WebSocket handshake and the first verified request contracts."""
import base64,datetime,hashlib,platform,uuid
from importlib.metadata import version,PackageNotFoundError
from .core import ActionError,walk
AUTH_TIMEOUT=15


def authentication(password,salt,challenge):
 secret=base64.b64encode(hashlib.sha256((password+salt).encode()).digest()).decode()
 return base64.b64encode(hashlib.sha256((secret+challenge).encode()).digest()).decode()


def info(studio):
 try:release=version('sorgobot-linux')
 except PackageNotFoundError:release='0.1.0'
 return {'instanceId':str(uuid.uuid5(uuid.NAMESPACE_URL,studio.root.as_uri())),'name':'StreamerMod','version':release,'os':platform.system().lower(),'osVersion':platform.release(),'mode':'ui','darkMode':True,'source':'websocketServer'}


def hello(studio,peer):
 result={'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat(),'session':peer['session'],'request':'Hello','info':info(studio)}
 if not peer['authenticated']:result['authentication']={'salt':peer['salt'],'challenge':peer['challenge']}
 return result


async def request(studio,data):
 operation=data.get('request');response={'id':data.get('id'),'status':'ok'}
 if operation=='GetInfo':return dict(response,info=info(studio))
 if operation=='GetActions':
  actions=[{'id':a['id'],'name':a['name'],'enabled':a.get('enabled',True),'group':a.get('group') or 'None','subaction_count':sum(1 for _ in walk(a.get('subActions',[]))),'trigger_count':len(a.get('triggers',[]))} for a in studio.engine.actions.values()]
  return dict(response,count=len(actions),actions=actions)
 if operation=='GetBroadcaster':
  from .websocket_twitch import broadcaster
  return dict(response,**await broadcaster(studio))
 if operation=='GetActiveViewers':
  from .websocket_twitch import viewers
  rows=viewers(studio);return dict(response,count=len(rows),viewers=rows)
 if operation=='TwitchGetEmotes':
  from .websocket_emotes import catalogue
  try:return dict(response,**await catalogue(studio))
  except TimeoutError:raise ActionError('Emote-Abfrage hat das Zeitlimit überschritten') from None
 if operation=='GetUserPronouns':
  from .websocket_pronouns import request as pronouns
  return dict(response,**await pronouns(studio,data))
 if operation in ('GetGlobals','GetGlobal','TwitchGetUserGlobals','TwitchGetUserGlobal'):
  from .websocket_variables import request as variables
  return dict(response,**variables(studio.engine,data))
 if operation=='GetCommands':
  from .websocket_data import commands
  rows=commands(studio.engine);return dict(response,count=len(rows),commands=rows)
 if operation=='GetCodeTriggers':
  from .csharp_core_services import snapshot
  rows=[{'name':r['name'],'eventName':r['eventName'],'category':'/'.join(['Custom',*r['categories']])} for r in snapshot(studio.engine)]
  return dict(response,count=len(rows),triggers=rows)
 if operation=='ExecuteCodeTrigger':
  from .csharp_core_services import registrations,trigger
  event=data.get('triggerName');args=data.get('args',{})
  if not isinstance(event,str) or not event.strip() or not isinstance(args,dict):raise ValueError('trigger/args')
  if event not in registrations(studio.engine):raise ActionError('Code-Trigger ist nicht registriert')
  mutable(studio);trigger(studio.engine,event,args);return response
 if operation=='GetCredits':
  from .websocket_data import credits
  return dict(response,**credits(studio.engine))
 if operation=='ClearCredits':
  from .csharp_core_services import rpc
  mutable(studio);await rpc(studio.engine,'credits',['reset']);return response
 if operation=='TestCredits':
  mutable(studio)
  from .server_contracts import test_credits
  from .websocket_data import credits
  test_credits(studio.engine);return dict(response,**credits(studio.engine))
 if operation=='SendMessage':
  from .server_contracts import send_message
  await send_message(studio,data);return response
 if operation=='DoAction':
  from .server_contracts import execute
  execute(studio,data);return response

 return None


def mutable(studio):
 if not studio.live or studio.io.dry_run or studio.closing:raise ActionError('Schreiboperation ist in dieser Laufzeit nicht verfügbar')
