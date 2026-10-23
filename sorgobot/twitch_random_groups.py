"""Original random-user group predicates over existing Core groups and Helix.

Original 1.0.7 reserves moderators/subscribers/vips (case insensitive).
Other names refer to local user groups. Filter the candidate pool before sampling.
"""
import copy
from .catalog import _CONFIG_LOCK
from .core import ActionError
from .core_services import read_config
from .twitch_user_info import UserInfo
from .users import members

BUILTINS=('moderators','subscribers','vips')
ROLES={
 'moderators':('moderation/moderators',('moderation:read','channel:manage:moderators')),
 'subscribers':('subscriptions',('channel:read:subscriptions',)),
 'vips':('channels/vips',('channel:read:vips','channel:manage:vips')),
}

def validate(node):
 names=node.get('groups',[])
 if not isinstance(names,list) or any(not isinstance(name,str) or not name.strip() for name in names):raise ActionError('Groups benötigt eine Liste nicht leerer Gruppennamen.')
 if type(node.get('includeFrom',False)) is not bool:raise ActionError('Include From muss true/false sein.')
 return list(dict.fromkeys(name.casefold() for name in names))

def resolve(names,groups):
 """Resolve the entire filter first, including exclusion of unknown groups."""
 from .twitch_user_groups import group
 return [(name,None if name in BUILTINS else copy.deepcopy(group(groups,name))) for name in names]

def configured(engine):
 # Follow the existing group service: previews use their in-memory sandbox;
 # live reads the latest saved groups so deletion during an await is detected.
 service=getattr(engine,'services',None)
 if engine.io.dry_run and service is not None:return copy.deepcopy(service.config['userGroups'])
 return read_config(engine.io.root)['userGroups']

async def role_ids(io,name):
 from .twitch_user_selection import normalized
 from .twitch_rewards import scopes
 cache=UserInfo(io);before=cache.session();endpoint,required=ROLES[name]
 if io.dry_run:
  body,_=cache.cached('random-user-group',name)
  if not isinstance(body,dict) or not isinstance(body.get('ids'),list) or any(not isinstance(uid,str) or not uid for uid in body['ids']):raise ActionError('Ungültiger gespeicherter Twitch-Gruppenstand.')
  return set(body['ids'])
 if not before[-1]:raise ActionError('Broadcaster-Konto unter Twitch → Accounts anmelden.')
 if not scopes(io.config).intersection(required):raise ActionError('Broadcaster-Leserecht für '+name+' fehlt: '+' / '.join(required))
 rows=[];cursor='';seen=set()
 for _ in range(1000):
  query={'broadcaster_id':before[0],'first':100}
  if cursor:query['after']=cursor
  reply=await io.twitch('GET',endpoint,params=query);cache.check_session(before)
  if not isinstance(reply,dict) or not isinstance(reply.get('data'),list) or not isinstance(reply.get('pagination'),dict):raise ActionError('Unvollständige Twitch-Gruppenliste: '+name)
  page=reply['data'];normalized(page)
  if name=='subscribers' and any(row.get('broadcaster_id')!=before[0] for row in page):raise ActionError('Abonnementliste gehört zu einem anderen Kanal.')
  rows.extend(page);cursor=reply['pagination'].get('cursor','')
  if not isinstance(cursor,str) or cursor and cursor in seen:raise ActionError('Ungültige oder wiederholte Gruppen-Paginierung.')
  if not cursor:break
  seen.add(cursor)
 else:raise ActionError('Twitch-Gruppenliste überschreitet 1000 Seiten.')
 ids={row['userId'] for row in normalized(rows)}
 # The Original ViewerRole hierarchy includes the broadcaster in moderators.
 if name=='moderators':ids.add(before[0])
 cache.save('random-user-group',name,{'ids':sorted(ids)})
 return ids

async def filter_users(engine,node,users):
 names=validate(node)
 if not names:return users
 if any(name in BUILTINS for name in names) and any(not isinstance(user.get('userId'),str) or not user['userId'] for user in users):raise ActionError('Twitch-Rollen benötigen bekannte Nutzer-IDs. Nutzerstand zuerst aktualisieren.')
 with _CONFIG_LOCK:definitions=resolve(names,configured(engine))
 if not users:return users
 roles={}
 cache=UserInfo(engine.io);before=cache.session() if any(name in BUILTINS for name in names) else None
 for name,target in definitions:
  if target is None:roles[name]=await role_ids(engine.io,name)
 if before is not None:cache.check_session(before)
 # Use current custom-group memberships after network awaits. Never interpret
 # a deleted/missing exclusion group as an empty set and select everyone.
 with _CONFIG_LOCK:definitions=resolve(names,configured(engine))
 result=[]
 for user in users:
  observed={**user,'platform':'twitch'}
  inside=any(user.get('userId') in roles[name] if target is None else bool(members(target,[observed])) for name,target in definitions)
  if inside==node.get('includeFrom',False):result.append(user)
 return result
