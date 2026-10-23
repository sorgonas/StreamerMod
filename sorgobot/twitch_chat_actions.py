"""Chat actions via documented Helix, with explicit sender and no blind retries."""
import json,re,sqlite3
from .core import ActionError,expand
from .twitch_rewards import scopes,integer
from .twitch_user_info import UserInfo
MANAGE='moderator:manage:chat_messages'
ANNOUNCE='moderator:manage:announcements'
ENTRIES={
91800:('Clear Chat Messages',{}),
91801:('Get Pinned Chat Message',{'resultVariable':'pinnedMessage'}),
91802:('Pin Chat Message',{'messageId':'%msgId%','duration':''}),
91803:('Reply To Message',{'replyId':'%msgId%','message':'','useBot':False,'fallbackToBroadcaster':False}),
91804:('Send Announcement to Channel',{'preferredAccount':'Bot','color':'Default','message':''}),
91805:('Unpin Chat Message',{}),
91806:('Updated Pinned Chat Message Duration',{'messageId':'','duration':''}),
}
FLAGS={91800:'clearSuccess',91802:'pinSuccess',91803:'replySuccess',91804:'announcementSuccess',91805:'unpinSuccess',91806:'pinUpdateSuccess'}
PIN_FIELDS=('pinnedMessageFound','pinnedMessageId','pinnedMessageText','pinnedMessageSenderId','pinnedMessageStartsAt','pinnedMessageEndsAt')
class Unsent(ActionError):pass

def message_id(value):
 if not isinstance(value,str) or not value or value!=value.strip() or len(value)>200 or any(c.isspace() for c in value):raise ActionError('Gültige Chat-Message-ID angeben; %msgId% stammt aus dem Chatereignis')
 return value

def duration(value):
 if value is None or value=='' or isinstance(value,str) and value.casefold()=='null':return None
 result=integer(value,30)
 if result>1800:raise ActionError('Pin-Dauer zwischen 30 und 1800 Sekunden, leer bis Streamende')
 return result

def text(value):
 if not isinstance(value,str) or not value.strip() or len(value)>500:raise ActionError('Nachricht muss 1 bis 500 Zeichen enthalten')
 return value

def pin_rows(reply,broadcaster):
 rows=reply.get('data') if isinstance(reply,dict) else None
 if not isinstance(rows,list) or len(rows)>1:raise ActionError('Twitch hat keinen gültigen Pin-Stand geliefert')
 for row in rows:
  if not isinstance(row,dict) or row.get('broadcaster_id')!=broadcaster:raise ActionError('Pin-Antwort gehört zu einem anderen Kanal')
  message_id(row.get('message_id'))
  if not isinstance(row.get('message'),dict) or not isinstance(row['message'].get('text'),str) or not isinstance(row['message'].get('fragments'),list):raise ActionError('Unvollständiger Inhalt der angehefteten Nachricht')
  for field in ('sender_user_id','sender_user_login','sender_user_name','pinned_by_user_id','pinned_by_user_login','pinned_by_user_name','starts_at','updated_at'):
   if not isinstance(row.get(field),str) or not row[field]:raise ActionError('Unvollständige Pin-Metadaten')
  if row.get('ends_at') is not None and not isinstance(row['ends_at'],str):raise ActionError('Ungültige Pin-Endzeit')
 return rows

class Chat:
 def __init__(self,io):self.io=io;self.cache=UserInfo(io)
 def account(self,bot=False,required=None):
  cfg=self.io.config;prefix='twitch_bot_' if bot else 'twitch_';uid=cfg.get('bot_id' if bot else 'broadcaster_id')
  if not cfg.get(prefix+'token') or not uid or not cfg.get('twitch_client_id') or not cfg.get('broadcaster_id'):raise Unsent(('Bot' if bot else 'Broadcaster')+'-Konto unter Twitch → Accounts anmelden')
  granted=set((cfg.get(prefix+'scopes') or '').split()) if isinstance(cfg.get(prefix+'scopes'),str) else set(cfg.get(prefix+'scopes') or [])
  if required and not granted & set(required):raise Unsent(('Bot' if bot else 'Broadcaster')+'-Freigabe fehlt: '+ ' / '.join(required)+'. Gemeinsame Anmeldung unter Twitch → Accounts verwenden.')
  return uid
 async def pinned(self):
  before=self.cache.session()
  if self.io.dry_run:reply,checked=self.cache.cached('pinned-message','channel')
  else:
   self.account(required=(MANAGE,'moderator:read:chat_messages'))
   reply=await self.io.twitch('GET','chat/pins',params={'broadcaster_id':before[0],'moderator_id':before[0]});self.cache.check_session(before)
   pin_rows(reply,before[0]);checked=self.cache.save('pinned-message','channel',{'data':reply['data']})
  return pin_rows(reply,before[0]),checked
 def invalidate(self):
  if not (self.io.root/'state/twitch-user-info.sqlite3').exists():return
  from contextlib import closing
  with closing(self.cache.db()) as db:
   with db:db.execute('DELETE FROM info_cache WHERE account=? AND kind=? AND target=?',('|'.join(self.cache.account()),'pinned-message','channel'))
 async def reply(self,parent,message,use_bot,fallback):
  if not isinstance(use_bot,bool) or not isinstance(fallback,bool):raise ActionError('Bot-Auswahl und Fallback müssen true/false sein')
  if self.io.dry_run:
   if parent is None:self.io.trace('chat',text=message,bot=use_bot,fallback=fallback,simulated=True)
   else:self.io.trace('twitch_reply_preview',replyId=parent,message=message,useBot=use_bot,fallback=fallback)
   return {'preview':True}
  before=self.cache.session()
  async def send(bot):
   uid=self.account(bot,('user:write:chat',));token_key='twitch_bot_token' if bot else 'twitch_token';sender_token=self.io.config.get(token_key)
   try:reply=await self.io.twitch('POST','chat/messages',{'broadcaster_id':before[0],'sender_id':uid,'message':message,**({'reply_parent_message_id':parent} if parent is not None else {})},bot=bot)
   except ActionError as exc:
    if re.match(r'^HTTP (401|403):',str(exc)):raise Unsent('Twitch hat den gewählten Absender abgelehnt') from None
    raise
   self.cache.check_session(before)
   if self.io.config.get(token_key)!=sender_token or self.io.config.get('bot_id' if bot else 'broadcaster_id')!=uid:raise ActionError('Absenderkonto während des Versands geändert; Status prüfen')
   data=reply.get('data') if isinstance(reply,dict) else None
   if not isinstance(data,list) or len(data)!=1 or not isinstance(data[0],dict):raise ActionError('Unklarer Versandstatus; kein automatischer zweiter Versand')
   if data[0].get('is_sent') is False:raise Unsent('Twitch hat die Antwort nicht gesendet')
   if data[0].get('is_sent') is not True:raise ActionError('Unklarer Versandstatus; kein automatischer zweiter Versand')
   identity=message_id(data[0].get('message_id'));return {'preview':False,'messageId':identity,'senderId':uid,'usedBot':bot}
  try:return await send(use_bot)
  except Unsent:
   if not use_bot or not fallback:raise
   return await send(False)

async def operation(io,node,args):
 kind=node['type'];n={k:expand(v,args) for k,v in node.items()};service=Chat(io)
 flag=FLAGS.get(kind)
 if flag:args[flag]=False
 if kind==91801:
  variable=n.get('resultVariable','pinnedMessage')
  if not isinstance(variable,str) or not variable:raise ActionError('Ergebnisvariablenname fehlt')
  for key in (*PIN_FIELDS,variable,'pinnedMessageCheckedAt'):args.pop(key,None)
  args['pinnedMessageFound']=False;rows,checked=await service.pinned();row=rows[0] if rows else None
  args.update({variable:row,'pinnedMessageFound':row is not None,'pinnedMessageId':row['message_id'] if row else '', 'pinnedMessageText':row['message']['text'] if row else '', 'pinnedMessageSenderId':row['sender_user_id'] if row else '', 'pinnedMessageStartsAt':row['starts_at'] if row else '', 'pinnedMessageEndsAt':row['ends_at'] if row else None,'pinnedMessageCheckedAt':checked})
  if io.dry_run:args['isPreview']=True
  return
 if kind==91803:
  for key in ('replyMessageId','replySenderId','replyUsedBot'):args.pop(key,None)
  result=await service.reply(message_id(n.get('replyId')),text(n.get('message')),n.get('useBot',False),n.get('fallbackToBroadcaster',False))
  if result['preview']:args['isPreview']=True;return
  args.update(replySuccess=True,replyMessageId=result['messageId'],replySenderId=result['senderId'],replyUsedBot=result['usedBot']);return
 if kind==91804:
  message=text(n.get('message'));preferred=n.get('preferredAccount','Bot')
  if preferred not in ('Bot','Broadcaster'):raise ActionError('Preferred Account muss Bot oder Broadcaster sein')
  if not isinstance(n.get('color','Default'),str):raise ActionError('Ankündigungsfarbe muss Text sein')
  color={'Default':'primary','Blue':'blue','Green':'green','Orange':'orange','Purple':'purple'}.get(n.get('color','Default'))
  if color is None:raise ActionError('Ankündigungsfarbe muss Default, Blue, Green, Orange oder Purple sein')
  if io.dry_run:io.trace('twitch_announcement_preview',message=message,color=color,account=preferred);args['isPreview']=True;return
  before=service.cache.session();bot=preferred=='Bot';uid=service.account(bot,(ANNOUNCE,))
  reply=await io.twitch('POST','chat/announcements',{'message':message,'color':color},params={'broadcaster_id':before[0],'moderator_id':uid},bot=bot);service.cache.check_session(before)
 else:
  params={};method='DELETE';endpoint='moderation/chat' if kind==91800 else 'chat/pins'
  if kind in (91802,91806):
   seconds=duration(n.get('duration',''));identity=n.get('messageId','')
   if identity:params['message_id']=message_id(identity)
   elif kind==91802:raise ActionError('Message Id zum Anheften fehlt')
   if seconds is not None:params['duration_seconds']=seconds
   method='PUT' if kind==91802 else 'PATCH'
  elif kind not in (91800,91805):raise ActionError('Unbekannte Chat-Unteraktion')
  if io.dry_run:io.trace('twitch_chat_preview',operation=ENTRIES[kind][0],params=params);args['isPreview']=True;return
  before=service.cache.session();uid=service.account(required=(MANAGE,))
  if kind in (91805,91806) and not params.get('message_id'):
   rows,checked=await service.pinned()
   if not rows:raise ActionError('Keine angeheftete Nachricht vorhanden')
   service.cache.check_session(before);params['message_id']=rows[0]['message_id']
  params.update(broadcaster_id=before[0],moderator_id=uid)
  reply=await io.twitch(method,endpoint,params=params);service.cache.check_session(before)
  if not isinstance(reply,dict) or reply:raise ActionError('Unerwartete Twitch-Bestätigung; Schreibstatus prüfen')
  args[flag]=True
  try:service.invalidate()
  except (sqlite3.Error,OSError):io.trace('pin_cache_invalidation_error',message='Twitch-Änderung bestätigt; lokaler Cache konnte nicht verworfen werden. Vorschau kann älteren Stand enthalten.')
  return
 if not isinstance(reply,dict) or reply:raise ActionError('Unerwartete Twitch-Bestätigung; Versandstatus prüfen')
 args[flag]=True
