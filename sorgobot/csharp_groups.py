"""Original-shaped C# group API over native Core groups and observed identities."""
import copy,uuid
from .catalog import ConfigStore,_CONFIG_LOCK
from .core import ActionError
from .core_services import read_config
from .command_state import platform
from .users import members,store,remove_membership

def services(engine):
 result=getattr(engine,'services',None)
 if result is None:raise ActionError('Nutzergruppen-Dienst fehlt')
 if getattr(getattr(engine,'studio',None),'closing',False):raise ActionError('Nutzergruppen-Dienst wird geschlossen')
 return result

def group(groups,name):
 if not isinstance(name,str) or not name.strip():return None
 matches=[g for g in groups if g['name'].strip().casefold()==name.strip().casefold()]
 if len(matches)>1:raise ActionError('Gruppenname ist mehrdeutig')
 return matches[0] if matches else None

def snapshot(engine):
 service=services(engine)
 return copy.deepcopy(service.config['userGroups'])

def mutate(engine,change):
 service=services(engine)
 with _CONFIG_LOCK:
  document=read_config(engine.io.root) if not engine.io.dry_run else copy.deepcopy(service.config)
  before=copy.deepcopy(service.config['userGroups']);groups=document['userGroups']
  result=change(groups)
  if result:
   if not engine.io.dry_run:ConfigStore(engine.io.root).save('core.json',document)
   service.config['userGroups']=copy.deepcopy(groups)
   from .core_events import group_changes
   group_changes(engine,before,groups)
  return result

def observed(engine,p,user,by_id):
 rows=store(engine).known(p)
 key='userId' if by_id else 'userName'
 matches=[r for r in rows if r[key]==user]
 # Multiple historic logins can share an ID; identity remains usable, metadata doesn't.
 if by_id and matches:
  return {'platform':p,'userId':user,'userName':matches[0]['userName'] if len(matches)==1 else '', 'displayName':matches[0]['displayName'] if len(matches)==1 else ''}
 return matches[0] if len(matches)==1 else None

async def user(engine,value,p,by_id):
 p=platform(p)
 if not isinstance(value,str) or not value.strip():return None
 value=value.strip() if by_id else value.strip().lstrip('@').casefold()
 info=observed(engine,p,value,by_id)
 if info:return info
 if not by_id and p=='twitch' and not engine.io.dry_run:
  from .twitch_user_info import login,user_data
  value=login(value)
  before=tuple(engine.io.config.get(k) for k in ('broadcaster_id','twitch_client_id','twitch_token'))
  reply=await engine.io.twitch('GET','users',params={'login':value})
  if before!=tuple(engine.io.config.get(k) for k in ('broadcaster_id','twitch_client_id','twitch_token')):raise ActionError('Twitch-Konto während der Nutzerabfrage gewechselt')
  if isinstance(reply,dict) and reply.get('data')==[]:return None
  row=user_data(reply,value)
  store(engine).remember(p,row['login'],row['id'],row['display_name'])
  return observed(engine,p,row['id'],True)
 return None

def listing(engine,target):
 result=[];seen=set();known=store(engine).known()
 for token in target.get('users',[]):
  split=token.strip().split(':',2)
  if len(split)==3 and split[0] in ('twitch','youtube','kick') and split[1]=='id':
   p,_,uid=split
   if (p,uid) in seen:continue
   row=observed(engine,p,uid,True)
   result.append({'Id':uid,'Type':p,'Login':row['userName'] if row else '', 'Username':row['displayName'] if row else '', 'UserInfoAvailable':bool(row and row['userName'])})
   seen.add((p,uid))
 for row in members({'users':[t for t in target.get('users',[]) if ':id:' not in t]},known):
  key=(row['platform'],row['userId'] or 'login:'+row['userName'])
  if key in seen:continue
  seen.add(key);result.append({'Id':row['userId'],'Type':row['platform'],'Login':row['userName'],'Username':row['displayName'],'UserInfoAvailable':bool(row['userId'])})
 # Preserve unobserved legacy logins without assigning a platform or fabricated ID.
 for token in target.get('users',[]):
  if ':id:' in token:continue
  selected=members({'users':[token]},known)
  if selected:continue
  split=token.split(':',1);p,login=split if len(split)==2 and split[0] in ('twitch','youtube','kick') else ('',token)
  key=(p,'login:'+login.casefold())
  if key in seen:continue
  seen.add(key);result.append({'Id':'','Type':p,'Login':login,'Username':'','UserInfoAvailable':False})
 return result

async def rpc(engine,method,values):
 services(engine)
 if method=='groups_list':return [g['name'] for g in snapshot(engine)]
 if method=='group_exists':return group(snapshot(engine),values[0]) is not None
 if method in ('group_add','group_delete','group_clear'):
  name=values[0]
  if not isinstance(name,str) or not name.strip():return False
  name=name.strip()
  def change(groups):
   target=group(groups,name)
   if method=='group_add':
    if target:return False
    groups.append({'id':str(uuid.uuid4()),'name':name,'users':[]});return True
   if target is None:return False
   if method=='group_delete':groups.remove(target)
   else:target['users']=[]
   return True
  return mutate(engine,change)
 if method=='group_users':
  target=group(snapshot(engine),values[0]);return listing(engine,target) if target else []
 if method=='group_user':
  op,value,p,name,by_id=values
  if not isinstance(name,str) or not name.strip():return False
  name=name.strip()
  if group(snapshot(engine),name) is None and op!='add':return False
  info=await user(engine,value,p,by_id)
  if info is None:return False
  p=info['platform'];uid=info['userId'];login=info['userName']
  if op=='contains':
   target=group(snapshot(engine),name);return bool(target and members(target,[info]))
  if op not in ('add','remove'):raise ActionError('Unbekannte Gruppenoperation')
  def change(groups):
   target=group(groups,name)
   if target is None:
    if op!='add':return False
    target={'id':str(uuid.uuid4()),'name':name,'users':[]};groups.append(target)
   included=bool(members(target,[info]))
   if op=='add':
    if included:return False
    if not uid:return False
    target.setdefault('users',[]).append(p+':id:'+uid)
   else:
    if not included:return False
    target['users']=remove_membership(target.get('users',[]),p,login,uid)
   return True
  return mutate(engine,change)
 raise ActionError('Unbekannte C#-Gruppenmethode')
