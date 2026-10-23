"""Public account and viewer snapshots bound to the actual Twitch identities."""
import copy,datetime,time
from .core import ActionError


def identity(studio):
 return tuple(studio.io.config.get(k,'') for k in ('broadcaster_id','twitch_client_id','twitch_token','bot_id','twitch_bot_token'))


def states(studio):
 auth=getattr(studio,'twitch_auth',None)
 return auth.account_states() if auth else {False:{'state':'unverified'},True:{'state':'unverified'}}


def connected(studio):
 links=getattr(getattr(studio,'twitch',None),'connections',None)
 current=links.snapshot() if links else {}
 return bool(current.get('eventsub') or current.get('broadcasterChat'))


async def broadcaster(studio):
 from .twitch_user_info import UserInfo,user_data
 before=identity(studio);accounts=states(studio)
 if not before[0] or accounts[False]['state']!='valid':return {'platforms':{},'connected':[],'disconnected':['twitch']}
 cache=getattr(studio,'websocket_broadcaster_cache',None);key=(before,accounts[True]['state'])
 if cache and cache[0]==key and time.monotonic()-cache[1]<30:public=copy.deepcopy(cache[2])
 else:
  body,_=await UserInfo(studio.io).read('broadcast',before[0],True);user=body['user']
  public={'broadcastUser':user['display_name'],'broadcastUserName':user['login'],'broadcastUserId':user['id'],'broadcastIsAffiliate':user['broadcaster_type']=='affiliate','broadcastIsPartner':user['broadcaster_type']=='partner'}
  # Public request examples and current client types use different names.
  public.update(broadcasterIsAffiliate=public['broadcastIsAffiliate'],broadcasterIsPartner=public['broadcastIsPartner'])
  if accounts[True]['state']=='valid' and before[3]:
   bot=user_data(await studio.io.twitch('GET','users',params={'id':before[3]},bot=True),before[3],True)
   public.update(botUser=bot['display_name'],botUserName=bot['login'],botUserId=bot['id'])
  if identity(studio)!=before or states(studio)[False]['state']!='valid' or states(studio)[True]['state']!=accounts[True]['state']:raise ActionError('Twitch-Konto wurde während der Abfrage geändert')
  studio.websocket_broadcaster_cache=(key,time.monotonic(),copy.deepcopy(public))
 ready=connected(studio)
 return {'platforms':{'twitch':public},'connected':['twitch'] if ready else [],'disconnected':[] if ready else ['twitch']}


def viewers(studio):
 if not identity(studio)[0] or states(studio)[False]['state']!='valid' or not connected(studio):return []
 twitch=studio.twitch;status=twitch.features.presence_status()
 if not status['enabled']:return []
 if status['state']!='ready':raise ActionError('Aktueller Zuschauerstand ist noch nicht verfügbar')
 try:
  checked=datetime.datetime.fromisoformat(status['checkedAt'].replace('Z','+00:00'));age=datetime.datetime.now(datetime.timezone.utc).timestamp()-checked.timestamp()
  if checked.tzinfo is None or not 0<=age<=max(60,status['intervalMinutes']*120):raise ValueError()
 except (ValueError,TypeError,KeyError):raise ActionError('Zuschauerstand ist veraltet oder ungültig') from None
 from .users import members
 groups=getattr(getattr(studio,'core_services',None),'config',{}).get('userGroups',[]);result=[]
 for user in list(twitch.viewers.values()):
  uid=user.get('id');login=user.get('login')
  if not isinstance(uid,str) or not uid or not isinstance(login,str) or not login:continue
  if time.time()-user.get('seenAt',0)>max(60,status['intervalMinutes']*120):continue
  mapped={'platform':'twitch','userId':uid,'userName':login}
  value={'id':uid,'type':'twitch','login':login,'display':user.get('name') or login,'groups':[g['name'] for g in groups if members(g,[mapped])]}
  if user.get('lastActive'):value['previousActive']=user['lastActive']
  roles=user.get('roles',[])
  if user.get('rolesKnown',bool(user.get('lastActive'))):
   value['subscribed']='Subscribers' in roles;value['role']=next((name for label,name in [('Broadcaster','Broadcaster'),('Moderators','Moderator'),('VIPs','VIP'),('Subscribers','Subscriber')] if label in roles),'Viewer')
  if uid==studio.io.config.get('broadcaster_id'):value['role']='Broadcaster'
  if type(user.get('channelPointsUsed')) is int and user['channelPointsUsed']>=0:value['channelPointsUsed']=user['channelPointsUsed']
  if type(user.get('exempt')) is bool:value['exempt']=user['exempt']
  result.append(value)
 return result
