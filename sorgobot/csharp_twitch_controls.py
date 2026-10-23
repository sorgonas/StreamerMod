"""Account-specific Twitch CPH writes; literal values and confirmed responses."""
import re
from .core import ActionError
from .csharp_twitch import identity
from .twitch_chat_actions import Chat,Unsent,text,message_id,duration,MANAGE,ANNOUNCE

OPERATIONS={
 'SendMessage','SendAction','TwitchSendAndPinMessage',
 'TwitchPinChatMessage','TwitchUnpinMessage','TwitchUpdatePinnedMessageDuration',
 'TwitchClearChatMessages','TwitchDeleteChatMessage','TwitchAnnounce','SendWhisper',
 'SetChannelTitle','SetChannelGameById','TwitchBanUser','TwitchUnbanUser','TwitchTimeoutUser',
 'TwitchAddModerator','TwitchRemoveModerator','TwitchAddVip','TwitchRemoveVip',
 'TwitchStartRaidById','TwitchStartRaidByName','TwitchSendShoutoutById','TwitchSendShoutoutByLogin',
}

def empty(reply):
 if not isinstance(reply,dict) or reply:raise ActionError('Twitch hat die Änderung nicht eindeutig bestätigt; Status vor erneutem Aufruf prüfen')

async def target(io,login):
 from .twitch_user_info import user_data,login as validate_login
 login=validate_login(login)
 return user_data(await io.twitch('GET','users',params={'login':login}),login)['id']

async def operation(io,name,args):
 auth=Chat(io)
 if name in ('SendMessage','SendAction','TwitchSendAndPinMessage'):
  message=text(args[0]);bot,fallback=args[1:] if len(args)>1 else (True,True)
  if name=='SendAction':message=text('/me '+message)
  if name=='TwitchSendAndPinMessage' and not io.dry_run:auth.account(required=(MANAGE,))
  try:result=await auth.reply(None,message,bot,fallback)
  except Unsent:
   if name!='TwitchSendAndPinMessage' and bot and not fallback:return None
   raise
  if name=='TwitchSendAndPinMessage':
   if result.get('preview'):return None
   await operation(io,'TwitchPinChatMessage',[result['messageId'],1200])
  return None
 if name in ('TwitchAddModerator','TwitchRemoveModerator','TwitchAddVip','TwitchRemoveVip'):
  from .twitch_moderation import Moderation
  op={'TwitchAddModerator':'add_moderator','TwitchRemoveModerator':'remove_moderator','TwitchAddVip':'add_vip','TwitchRemoveVip':'remove_vip'}[name]
  result=await Moderation(io).change(op,args[0]);return not result.get('preview',False)
 if name in ('SetChannelTitle','SetChannelGameById'):
  field='title' if name=='SetChannelTitle' else 'game_id';value=args[0]
  if field=='title' and (not isinstance(value,str) or not value.strip() or len(value)>140):raise ActionError('Kanaltitel benötigt 1–140 Zeichen')
  if field=='game_id' and (not isinstance(value,str) or not re.fullmatch('[0-9]+',value)):raise ActionError('Spiel-ID benötigt Ziffern; 0 entfernt die Kategorie')
  if io.dry_run:io.trace('twitch_channel_csharp_preview',field=field,value=value);return False
  from .twitch_channel_tools import ChannelTools
  service=ChannelTools(io);service.require(True)
  empty(await io.twitch('PATCH','channels',{field:value},params={'broadcaster_id':io.config['broadcaster_id']}));service.cache.save('info',{});return True
 if name in ('TwitchStartRaidById','TwitchStartRaidByName','TwitchSendShoutoutById','TwitchSendShoutoutByLogin'):
  from .twitch_user_info import login as validate_login
  by_name=name.endswith(('ByName','ByLogin'));value=validate_login(args[0]) if by_name else identity(args[0],'Ziel-ID')
  raid=name.startswith('TwitchStartRaid')
  if io.dry_run:io.trace('twitch_csharp_target_preview',operation=name,target=value);return False
  owner=auth.account(required=('channel:manage:raids' if raid else 'moderator:manage:shoutouts',))
  uid=await target(io,value) if by_name else value
  if uid==owner:raise ActionError('Der eigene Kanal kann nicht Ziel dieses Aufrufs sein')
  params={'from_broadcaster_id':owner,'to_broadcaster_id':uid}
  if not raid:params['moderator_id']=owner
  reply=await io.twitch('POST','raids' if raid else 'chat/shoutouts',params=params)
  if raid:
   rows=reply.get('data') if isinstance(reply,dict) else None
   if not isinstance(rows,list) or len(rows)!=1 or not isinstance(rows[0],dict) or not rows[0].get('created_at'):raise ActionError('Twitch hat den Raid-Start nicht bestätigt')
  else:empty(reply)
  return True
 if name in ('TwitchBanUser','TwitchUnbanUser','TwitchTimeoutUser'):
  from .twitch_moderation import validate
  from .twitch_rewards import integer
  from .twitch_user_info import login as validate_login
  login=validate_login(args[0]);timeout=name=='TwitchTimeoutUser';unban=name=='TwitchUnbanUser'
  reason='' if unban else args[2 if timeout else 1] or '';bot=args[-1]
  seconds=integer(args[1],1) if timeout else None
  validate('timeout' if timeout else 'unban' if unban else 'ban',reason,seconds if timeout else 60)
  if io.dry_run:io.trace('twitch_moderation_csharp_preview',operation=name,userLogin=login,reason=reason,duration=seconds,bot=bot);return False
  moderator=auth.account(bot,('moderator:manage:banned_users',));owner=io.config['broadcaster_id'];uid=await target(io,login)
  if uid==owner:raise ActionError('Broadcaster kann nicht Ziel dieser Moderationsaktion sein')
  params={'broadcaster_id':owner,'moderator_id':moderator}
  if unban:params['user_id']=uid;empty(await io.twitch('DELETE','moderation/bans',params=params,bot=bot))
  else:
   body={'data':{'user_id':uid,'reason':reason}}
   if timeout:body['data']['duration']=seconds
   reply=await io.twitch('POST','moderation/bans',body,params=params,bot=bot)
   rows=reply.get('data') if isinstance(reply,dict) else None
   if not isinstance(rows,list) or len(rows)!=1 or not isinstance(rows[0],dict) or any(rows[0].get(k)!=v for k,v in dict(params,user_id=uid).items()):raise ActionError('Twitch hat die Sperre nicht passend bestätigt')
  from .twitch_moderation import Moderation
  service=Moderation(io);doc=service.document();doc.setdefault('accounts',{}).setdefault(service.key(),{}).pop('bans',None);service.store.save('twitch-moderation.json',doc)
  return True
 if name=='SendWhisper':
  from .twitch_user_info import login as validate_login
  login=validate_login(args[0]);message=args[1];bot=args[2]
  if not isinstance(message,str) or not message.strip() or len(message)>10000:raise ActionError('Whisper benötigt 1–10000 Zeichen; Twitch kann je nach Empfänger eine niedrigere Grenze anwenden')
  if io.dry_run:io.trace('twitch_whisper_preview',userLogin=login,message=message,bot=bot);return False
  sender=auth.account(bot,('user:manage:whispers',));uid=await target(io,login)
  if uid==sender:raise ActionError('Whisper an das eigene Absenderkonto ist nicht möglich')
  empty(await io.twitch('POST','whispers',{'message':message},params={'from_user_id':sender,'to_user_id':uid},bot=bot));return True
 if name=='TwitchAnnounce':
  message,bot,color,fallback=args;message=text(message);color='primary' if color is None else color.lower() if isinstance(color,str) else ''
  if color not in ('primary','blue','green','orange','purple'):raise ActionError('Ungültige Ankündigungsfarbe')
  if io.dry_run:io.trace('twitch_announcement_preview',message=message,color=color,bot=bot,fallback=fallback);return None
  async def announce(selected):
   moderator=auth.account(selected,(ANNOUNCE,))
   try:reply=await io.twitch('POST','chat/announcements',{'message':message,'color':color},params={'broadcaster_id':io.config['broadcaster_id'],'moderator_id':moderator},bot=selected)
   except ActionError as exc:
    if re.match(r'^HTTP (401|403):',str(exc)):raise Unsent('Twitch hat das Ankündigungskonto abgelehnt') from None
    raise
   empty(reply)
  try:await announce(bot)
  except Unsent:
   if not bot or not fallback:raise
   await announce(False)
  return None
 if name in ('TwitchClearChatMessages','TwitchDeleteChatMessage'):
  bot=args[-1];params={}
  if name=='TwitchDeleteChatMessage':params['message_id']=message_id(args[0])
  if io.dry_run:io.trace('twitch_chat_csharp_preview',operation=name,bot=bot,**params);return False
  moderator=auth.account(bot,(MANAGE,));params.update(broadcaster_id=io.config['broadcaster_id'],moderator_id=moderator)
  empty(await io.twitch('DELETE','moderation/chat',params=params,bot=bot));auth.invalidate();return True
 if name in ('TwitchPinChatMessage','TwitchUnpinMessage','TwitchUpdatePinnedMessageDuration'):
  params={};seconds=duration(args[-1]) if args else None
  if name=='TwitchPinChatMessage':params['message_id']=message_id(args[0])
  if seconds is not None:params['duration_seconds']=seconds
  if io.dry_run:io.trace('twitch_pin_csharp_preview',operation=name,params=params);return False
  moderator=auth.account(required=(MANAGE,))
  if 'message_id' not in params:
   rows,_=await auth.pinned()
   if not rows:raise ActionError('Keine angeheftete Nachricht vorhanden')
   params['message_id']=rows[0]['message_id']
  params.update(broadcaster_id=io.config['broadcaster_id'],moderator_id=moderator)
  empty(await io.twitch({'TwitchPinChatMessage':'PUT','TwitchUnpinMessage':'DELETE','TwitchUpdatePinnedMessageDuration':'PATCH'}[name],'chat/pins',params=params));auth.invalidate();return True
 raise ActionError('Unbekannte Twitch-C#-Steuerung')
