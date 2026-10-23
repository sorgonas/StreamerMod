"""Explicit chat UI actions reuse the existing validated Twitch adapters."""
from .core import ActionError
async def moderate(studio,data):
 from .original_websocket import mutable
 from .twitch_chat_actions import Chat,message_id,operation as chat_action,MANAGE
 mutable(studio);op=data.get('operation');row=data.get('row')
 if not isinstance(row,dict):raise ValueError('row')
 if row.get('platform','twitch')=='youtube':
  service=getattr(studio,'youtube',None)
  if service is None:raise ActionError('YouTube ist nicht eingerichtet')
  if op not in ('delete','ban','timeout'):raise ActionError('Diese Kontextaktion ist für YouTube nicht verfügbar')
  actual=next((r for r in service.messages if r['id']==row.get('id') and r.get('liveChatId')==service.live_chat()),None)
  if actual is None:raise ActionError('YouTube-Nachricht ist nicht mehr im aktuellen Livechat verfügbar')
  return await service.moderate(op,actual.get('id') if op=='delete' else actual.get('userId'),data.get('duration',60))
 if row.get('platform','twitch')!='twitch':raise ActionError('Unbekannte Chatplattform')
 if op in ('ban','timeout','unban'):
  from .twitch_moderation import Moderation
  return await Moderation(studio.io).change(op,row.get('login',''),data.get('reason',''),data.get('duration',60))
 if op in ('pin','unpin'):
  args={};await chat_action(studio.io,{'type':91802 if op=='pin' else 91805,'messageId':message_id(row.get('id'))},args);return args
 if op=='delete':
  service=Chat(studio.io);before=service.cache.session();uid=service.account(required=(MANAGE,))
  reply=await studio.io.twitch('DELETE','moderation/chat',params={'broadcaster_id':before[0],'moderator_id':uid,'message_id':message_id(row.get('id'))});service.cache.check_session(before)
  if reply!={}:raise ActionError('Unerwartete Twitch-Bestätigung')
  return True
 raise ActionError('Unbekannte Chataktion')
