"""Host-account Guest Star actions; current sessions and explicit partial updates."""
import sqlite3,re
from contextlib import closing
from .core import ActionError,expand
from .twitch_rewards import integer
from .twitch_user_info import UserInfo,login,user_data
from .twitch_chat_actions import Chat
READ='channel:read:guest_star';WRITE='channel:manage:guest_star'
LAYOUTS=('TILED_LAYOUT','SCREENSHARE_LAYOUT','HORIZONTAL_LAYOUT','VERTICAL_LAYOUT')
ENTRIES={
92100:('Get Channel Guest Star Settings',{}),
92101:('Update Channel Guest Star Settings',{'moderatorSendLiveEnabled':'','slotCount':'','browserSourceAudioEnabled':'','groupLayout':'','regenerateBrowserSources':False}),
92102:('Get Guest Star Session',{}),
92103:('Create Guest Star Session',{}),
92104:('End Guest Star Session',{'sessionId':''}),
92105:('Get Guest Star Invites',{'sessionId':''}),
92106:('Send Guest Star Invite',{'userLogin':'%userName%','sessionId':''}),
92107:('Delete Guest Star Invite',{'userLogin':'%userName%','sessionId':''}),
92108:('Assign Guest Star Slot',{'userLogin':'%userName%','slot':1,'sessionId':''}),
92109:('Update Guest Star Slot',{'sourceSlot':1,'destinationSlot':2,'sessionId':''}),
92110:('Delete Guest Star Slot',{'userLogin':'%userName%','slot':1,'sessionId':''}),
92111:('Update Guest Star Slot Settings',{'slot':1,'audioEnabled':'','videoEnabled':'','live':'','volume':'','sessionId':''}),
}
def bounded(value,low,high):
 result=integer(value,low)
 if result>high:raise ActionError(f'Wert muss zwischen {low} und {high} liegen')
 return result

def boolean(value):
 if type(value) is not bool:raise ActionError('True, False oder Unverändert wählen')
 return value

def identity(value):
 if not isinstance(value,str) or not re.fullmatch('[A-Za-z0-9_-]{1,200}',value):raise ActionError('Ungültige Guest-Star-Sitzungs-ID')
 return value

def data(reply,maximum=None):
 rows=reply.get('data') if isinstance(reply,dict) else None
 if not isinstance(rows,list) or any(not isinstance(row,dict) for row in rows) or maximum is not None and len(rows)>maximum:raise ActionError('Ungültige Guest-Star-Antwort')
 return rows

def settings(reply):
 rows=data(reply,1)
 if not rows:raise ActionError('Guest-Star-Kanaleinstellungen fehlen')
 row=rows[0]
 for key in ('is_moderator_send_live_enabled','is_browser_source_audio_enabled'):boolean(row.get(key))
 if type(row.get('slot_count')) is not int:raise ActionError('Ungültige Guest-Star-Slotanzahl')
 bounded(row['slot_count'],0,6)
 raw=row.get('layout',row.get('group_layout'))
 layout={'TILED':'TILED_LAYOUT','SCREENSHARE':'SCREENSHARE_LAYOUT','HORIZONTAL':'HORIZONTAL_LAYOUT','VERTICAL':'VERTICAL_LAYOUT'}.get(raw,raw) if isinstance(raw,str) else None
 if layout not in LAYOUTS or not isinstance(row.get('browser_source_token'),str):raise ActionError('Unvollständige Guest-Star-Kanaleinstellungen')
 return {**row,'layout':layout}

def sessions(reply,broad):
 rows=data(reply,1)
 for row in rows:
  identity(row.get('id'));guests=row.get('guests')
  if not isinstance(guests,list) or not guests:raise ActionError('Guest-Star-Sitzung ohne gültigen Host')
  seen=set();hosts=0
  for guest in guests:
   if not isinstance(guest,dict):raise ActionError('Ungültiger Guest-Star-Gast')
   slot=guest.get('slot_id',guest.get('id'))
   if not isinstance(slot,str) or slot not in ('0','1','2','3','4','5','6','SCREENSHARE') or slot in seen:raise ActionError('Ungültiger oder doppelter Guest-Star-Slot')
   seen.add(slot)
   if slot=='0':
    if guest.get('user_id')!=broad:raise ActionError('Guest-Star-Sitzung gehört zu einem anderen Host')
    hosts+=1
   for key in ('user_id','user_login','user_display_name','assigned_at'):
    if not isinstance(guest.get(key),str) or not guest[key]:raise ActionError('Unvollständige Guest-Star-Gastdaten')
   boolean(guest.get('is_live'))
   if type(guest.get('volume')) is not int:raise ActionError('Ungültige Guest-Star-Lautstärke')
   bounded(guest['volume'],0,100)
   for key in ('audio_settings','video_settings'):
    media=guest.get(key)
    if not isinstance(media,dict):raise ActionError('Guest-Star-Medieneinstellungen fehlen')
    for flag in ('is_available','is_host_enabled','is_guest_enabled'):boolean(media.get(flag))
  if hosts!=1:raise ActionError('Guest-Star-Host konnte nicht bestätigt werden')
 return rows

def invites(reply):
 rows=data(reply);seen=set()
 for row in rows:
  uid=row.get('user_id')
  if not isinstance(uid,str) or not uid or uid in seen or not isinstance(row.get('invited_at'),str) or not row['invited_at'] or row.get('status') not in ('INVITED','ACCEPTED','READY'):raise ActionError('Ungültige oder doppelte Guest-Star-Einladung')
  seen.add(uid)
  for key in ('is_video_enabled','is_audio_enabled','is_video_available','is_audio_available'):boolean(row.get(key))
 return rows

def changes(kind,n):
 result={}
 if kind==92101:
  for native,remote in [('moderatorSendLiveEnabled','is_moderator_send_live_enabled'),('browserSourceAudioEnabled','is_browser_source_audio_enabled')]:
   if n.get(native,'')!='':result[remote]=boolean(n[native])
  if n.get('slotCount','')!='':result['slot_count']=bounded(n['slotCount'],1,6)
  if n.get('groupLayout','')!='':
   if n['groupLayout'] not in LAYOUTS:raise ActionError('Ungültiges Guest-Star-Layout')
   result['group_layout']=n['groupLayout']
  if boolean(n.get('regenerateBrowserSources',False)):result['regenerate_browser_sources']=True
 elif kind==92111:
  for native,remote in [('audioEnabled','is_audio_enabled'),('videoEnabled','is_video_enabled'),('live','is_live')]:
   if n.get(native,'')!='':result[remote]='true' if boolean(n[native]) else 'false'
  if n.get('volume','')!='':result['volume']=bounded(n['volume'],0,100)
 if not result:raise ActionError('Mindestens eine Guest-Star-Einstellung ändern')
 return result

class GuestStar:
 def __init__(self,io):self.io=io;self.cache=UserInfo(io);self.auth=Chat(io)
 def params(self):
  broad=self.cache.account()[0];return {'broadcaster_id':broad,'moderator_id':broad}
 async def read(self,kind,target,endpoint,params,validator):
  before=self.cache.session()
  if self.io.dry_run:reply,checked=self.cache.cached('guest-star-'+kind,target)
  else:
   self.auth.account(required=(READ,WRITE));reply=await self.io.twitch('GET',endpoint,params=params);self.cache.check_session(before)
   validator(reply);checked=self.cache.save('guest-star-'+kind,target,reply)
  return validator(reply),checked
 async def session(self,requested=''):
  if requested:identity(requested)
  rows,checked=await self.read('session','channel','guest_star/session',self.params(),lambda r:sessions(r,self.cache.account()[0]))
  if not rows:raise ActionError('Keine aktive Guest-Star-Sitzung; zuerst Create Guest Star Session ausführen')
  current=rows[0]
  if requested and current['id']!=requested:raise ActionError('Angegebene Guest-Star-Sitzung ist nicht mehr aktiv')
  return current,checked
 def invalidate(self):
  if not (self.io.root/'state/twitch-user-info.sqlite3').exists():return
  with closing(self.cache.db()) as db:
   with db:db.execute("DELETE FROM info_cache WHERE account=? AND kind LIKE 'guest-star-%'",('|'.join(self.cache.account()),))
 async def mutate(self,kind,n):
  body=changes(kind,n) if kind in (92101,92111) else None
  if kind in (92108,92110,92111):slot=str(bounded(n.get('slot'),1,6))
  if kind==92109:
   source=str(bounded(n.get('sourceSlot'),1,6));destination=str(bounded(n.get('destinationSlot'),1,6))
   if source==destination:raise ActionError('Quell- und Zielslot müssen verschieden sein')
  user_login=login(n.get('userLogin','')) if kind in (92106,92107,92108,92110) else None
  requested=n.get('sessionId','')
  if requested:identity(requested)
  if self.io.dry_run:self.io.trace('guest_star_preview',operation=ENTRIES[kind][0]);return None
  before=self.cache.session();self.auth.account(required=(WRITE,));params=self.params();method='POST';endpoint='guest_star/session'
  if kind==92101:params.pop('moderator_id');method='PUT';endpoint='guest_star/channel_settings'
  elif kind==92103:
   existing,_=await self.read('session','channel',endpoint,params,lambda r:sessions(r,before[0]))
   if existing:raise ActionError('Guest-Star-Sitzung läuft bereits; keine zweite Sitzung erstellen')
   params.pop('moderator_id')
  else:
   current,_=await self.session(requested);params['session_id']=current['id']
   if kind==92104:params.pop('moderator_id');method='DELETE'
   elif kind in (92106,92107):endpoint='guest_star/invites';method='POST' if kind==92106 else 'DELETE'
   elif kind in (92108,92109,92110):
    endpoint='guest_star/slot';method={92108:'POST',92109:'PATCH',92110:'DELETE'}[kind]
    if kind==92109:params.update(source_slot_id=source,destination_slot_id=destination)
    else:params['slot_id']=slot
   elif kind==92111:endpoint='guest_star/slot_settings';method='PATCH';params.update(slot_id=slot,**body);body=None
   else:raise ActionError('Unbekannte Guest-Star-Änderung')
   if kind in (92108,92109,92110,92111):
    channel,_=await self.read('settings','channel','guest_star/channel_settings',self.params(),settings)
    slots=[slot] if kind!=92109 else [source,destination]
    if any(int(s)>channel['slot_count'] for s in slots):raise ActionError('Slot liegt außerhalb der eingerichteten Guest-Star-Slots')
   if user_login:
    user=user_data(await self.io.twitch('GET','users',params={'login':user_login}),user_login);params['guest_id']=user['id']
    if user['id']==before[0]:raise ActionError('Host darf nicht als Gast verändert werden')
  self.cache.check_session(before)
  reply=await self.io.twitch(method,endpoint,body,params=params);self.cache.check_session(before)
  result=None
  if kind in (92103,92104):
   rows=sessions(reply,before[0])
   if not rows or kind==92104 and rows[0]['id']!=params['session_id']:raise ActionError('Twitch hat die Sitzungsänderung nicht bestätigt')
   result=rows[0]
  elif not isinstance(reply,dict) or reply:raise ActionError('Twitch hat die Guest-Star-Änderung nicht eindeutig bestätigt')
  try:self.invalidate()
  except (sqlite3.Error,OSError):self.io.trace('guest_star_cache_error',message='Twitch-Änderung bestätigt; gespeicherter Guest-Star-Stand kann veraltet sein.')
  return {'session':result}

async def operation(io,node,args):
 kind=node['type'];n={k:expand(v,args) for k,v in node.items()};service=GuestStar(io)
 if kind in (92100,92102,92105):
  args.pop('guestStarCheckedAt',None);args['guestStarFromCache']=io.dry_run
  field={92100:'guestStarSettings',92102:'guestStarSession',92105:'guestStarInvites'}[kind];args.pop(field,None)
  if kind==92100:value,checked=await service.read('settings','channel','guest_star/channel_settings',service.params(),settings)
  elif kind==92102:
   args.pop('guestStarSessionId',None);args['guestStarSessionFound']=False
   rows,checked=await service.read('session','channel','guest_star/session',service.params(),lambda r:sessions(r,service.cache.account()[0]));value=rows[0] if rows else None
   args.update(guestStarSessionFound=value is not None,guestStarSessionId=value['id'] if value else '')
  else:
   current,_=await service.session(n.get('sessionId',''));params=service.params();params['session_id']=current['id']
   value,checked=await service.read('invites',current['id'],'guest_star/invites',params,invites)
  args[field]=value;args['guestStarCheckedAt']=checked
  if io.dry_run:args['isPreview']=True
 else:
  args['guestStarSuccess']=False
  if kind in (92103,92104):args.pop('guestStarSessionId',None)
  result=await service.mutate(kind,n)
  if result is None:args['isPreview']=True;return
  args['guestStarSuccess']=True
  if result['session']:args['guestStarSessionId']=result['session']['id']
