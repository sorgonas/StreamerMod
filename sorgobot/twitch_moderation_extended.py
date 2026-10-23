"""Shield, warnings and suspicious users; confirmed Helix responses only."""
import re,sqlite3
from .core import ActionError,expand
from .twitch_chat_actions import Chat,text
from .twitch_user_info import UserInfo
SHIELD='moderator:manage:shield_mode'
WARN='moderator:manage:warnings'
SUSPICIOUS='moderator:manage:suspicious_users'
ENTRIES={
91900:('Shield · Get Shield Mode Status',{}),
91901:('Shield · Update Shield Mode Status',{'state':'Yes'}),
91902:('Warn User',{'userLogin':'%userName%','reason':''}),
91903:('Add Suspicious Status',{'userLogin':'%userName%','status':'ACTIVE_MONITORING'}),
91904:('Remove Suspicious Status',{'userLogin':'%userName%'}),
}
SHIELD_FIELDS=('is_active','lastActivatedAt','moderatorId','moderatorName','moderatorLogin','shieldCheckedAt')
FLAGS={91901:'shieldUpdateSuccess',91902:'warnedResult',91903:'suspiciousResult',91904:'suspiciousResult'}

def one(reply):
 rows=reply.get('data') if isinstance(reply,dict) else None
 if not isinstance(rows,list) or len(rows)!=1 or not isinstance(rows[0],dict):raise ActionError('Twitch hat die Moderationsaktion nicht eindeutig bestätigt')
 return rows[0]

def shield_row(reply):
 row=one(reply)
 if type(row.get('is_active')) is not bool or any(not isinstance(row.get(k),str) for k in ('moderator_id','moderator_login','moderator_name','last_activated_at')):raise ActionError('Ungültiger Shield-Mode-Stand von Twitch')
 return row

class Extended:
 def __init__(self,io):self.io=io;self.cache=UserInfo(io);self.chat=Chat(io)
 async def shield(self):
  before=self.cache.session()
  if self.io.dry_run:reply,checked=self.cache.cached('shield-mode','channel')
  else:
   self.chat.account(required=(SHIELD,'moderator:read:shield_mode'))
   reply=await self.io.twitch('GET','moderation/shield_mode',params={'broadcaster_id':before[0],'moderator_id':before[0]});self.cache.check_session(before)
   shield_row(reply);checked=self.cache.save('shield-mode','channel',reply)
  return shield_row(reply),checked
 async def update(self,state):
  if state not in ('Yes','No','Toggle'):raise ActionError('Shield State muss Yes, No oder Toggle sein')
  if self.io.dry_run:self.io.trace('shield_update_preview',state=state);return None
  before=self.cache.session();self.chat.account(required=(SHIELD,))
  active=state=='Yes'
  if state=='Toggle':row,_=await self.shield();self.cache.check_session(before);active=not row['is_active']
  reply=await self.io.twitch('PUT','moderation/shield_mode',{'is_active':active},params={'broadcaster_id':before[0],'moderator_id':before[0]});self.cache.check_session(before)
  row=shield_row(reply)
  if row['is_active']!=active:raise ActionError('Twitch hat den angeforderten Shield-Zustand nicht bestätigt')
  try:self.cache.save('shield-mode','channel',reply)
  except (sqlite3.Error,OSError):self.io.trace('shield_cache_error',message='Änderung bestätigt; lokaler Shield-Stand konnte nicht gespeichert werden.')
  return row
 async def user_change(self,kind,login,reason='',status='ACTIVE_MONITORING'):
  if not isinstance(login,str) or not re.fullmatch(r'[A-Za-z0-9_]{1,25}',login):raise ActionError('Gültigen Twitch-Benutzernamen oder %userName% angeben')
  login=login.lower()
  if kind==91902:reason=text(reason)
  if kind==91903 and status not in ('ACTIVE_MONITORING','RESTRICTED'):raise ActionError('Status muss ACTIVE_MONITORING oder RESTRICTED sein')
  if self.io.dry_run:self.io.trace('moderation_extended_preview',operation=ENTRIES[kind][0],userLogin=login,reason=reason,status=status);return None
  before=self.cache.session();self.chat.account(required=(WARN if kind==91902 else SUSPICIOUS,))
  user=await self.io.user(login);self.cache.check_session(before)
  if not isinstance(user,dict) or not isinstance(user.get('id'),str) or not user['id'] or user.get('login')!=login or not isinstance(user.get('display_name'),str):raise ActionError('Zielnutzer konnte nicht eindeutig aufgelöst werden')
  if user['id']==before[0]:raise ActionError('Broadcaster kann nicht Ziel dieser Moderationsaktion sein')
  params={'broadcaster_id':before[0],'moderator_id':before[0]}
  if kind==91902:
   reply=await self.io.twitch('POST','moderation/warnings',{'data':{'user_id':user['id'],'reason':reason}},params=params)
  elif kind==91903:
   reply=await self.io.twitch('POST','moderation/suspicious_users',{'user_id':user['id'],'status':status},params=params)
  else:
   params['user_id']=user['id'];reply=await self.io.twitch('DELETE','moderation/suspicious_users',params=params)
  self.cache.check_session(before);row=one(reply)
  if any(row.get(k)!=v for k,v in {'broadcaster_id':before[0],'moderator_id':before[0],'user_id':user['id']}.items()):raise ActionError('Moderationsbestätigung gehört nicht zum angeforderten Kanal oder Nutzer')
  if kind==91902:
   if row.get('reason')!=reason:raise ActionError('Warnungsgrund wurde nicht bestätigt')
  else:
   if row.get('status')!=(status if kind==91903 else 'NO_TREATMENT') or not isinstance(row.get('updated_at'),str) or not row['updated_at'] or not isinstance(row.get('types'),list) or any(not isinstance(t,str) for t in row['types']):raise ActionError('Verdächtiger-Nutzer-Status wurde nicht vollständig bestätigt')
  return user,row

async def operation(io,node,args):
 kind=node['type'];n={k:expand(v,args) for k,v in node.items()};service=Extended(io)
 if kind in FLAGS:args[FLAGS[kind]]=False
 if kind==91900:
  for key in SHIELD_FIELDS:args.pop(key,None)
  row,checked=await service.shield();args.update(is_active=row['is_active'],lastActivatedAt=row['last_activated_at'],moderatorId=row['moderator_id'],moderatorName=row['moderator_name'],moderatorLogin=row['moderator_login'],shieldCheckedAt=checked)
  if io.dry_run:args['isPreview']=True
 elif kind==91901:
  row=await service.update(n.get('state','Yes'))
  if row is None:args['isPreview']=True
  else:args['shieldUpdateSuccess']=True
 elif kind in (91902,91903,91904):
  prefix='warnedUser' if kind==91902 else 'suspiciousUser'
  for key in (prefix,prefix+'Name',prefix+'Id',prefix+'Type','lowTrustStatus','suspiciousUpdatedAt'):args.pop(key,None)
  result=await service.user_change(kind,n.get('userLogin',''),n.get('reason',''),n.get('status','ACTIVE_MONITORING'))
  if result is None:args['isPreview']=True;return
  user,row=result;args.update({prefix:user['display_name'],prefix+'Name':user['login'],prefix+'Id':user['id'],prefix+'Type':'twitch',FLAGS[kind]:True})
  if kind!=91902:args.update(lowTrustStatus=row['status'].lower(),suspiciousUpdatedAt=row['updated_at'])
 else:raise ActionError('Unbekannte Moderations-Unteraktion')
