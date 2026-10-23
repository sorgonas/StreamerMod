"""CPH user blocks, AutoMod decisions and blocked-term text lookup."""
from .core import ActionError
from .csharp_twitch import identity
from .csharp_twitch_controls import empty,target
from .csharp_twitch_data import pages,rows
from .twitch_chat_actions import Chat,message_id

OPERATIONS={'TwitchBlockUser','TwitchBlockUserById','TwitchUnblockUser','TwitchUnblockUserById','TwitchApproveAutoHeldMessage','TwitchDenyAutoHeldMessage','TwitchAddBlockedTerm','TwitchRemoveBlockedTerm','TwitchGetBlockedTerms'}

async def operation(io,name,args):
 auth=Chat(io)
 if name.startswith(('TwitchBlock','TwitchUnblock')):
  block=name.startswith('TwitchBlock');by_id=name.endswith('ById')
  from .twitch_user_info import login
  value=identity(args[0],'Nutzer-ID') if by_id else login(args[0]);params={}
  if block:
   context,reason=args[1:]
   if context not in (0,1,2) or reason not in (0,1,2,3):raise ActionError('Ungültiger Block-Kontext oder -Grund')
   if context:params['source_context']={1:'chat',2:'whisper'}[context]
   if reason:params['reason']={1:'harassment',2:'spam',3:'other'}[reason]
  if io.dry_run:io.trace('twitch_user_block_preview',operation=name,target=value);return False
  owner=auth.account(required=('user:manage:blocked_users',));uid=value if by_id else await target(io,value)
  if uid==owner:raise ActionError('Das eigene Konto kann nicht blockiert werden')
  params['target_user_id']=uid;empty(await io.twitch('PUT' if block else 'DELETE','users/blocks',params=params));return True
 if name in ('TwitchApproveAutoHeldMessage','TwitchDenyAutoHeldMessage'):
  mid=message_id(args[0]);action='ALLOW' if name.startswith('TwitchApprove') else 'DENY'
  if io.dry_run:io.trace('twitch_automod_preview',messageId=mid,action=action);return False
  uid=auth.account(required=('moderator:manage:automod',));empty(await io.twitch('POST','moderation/automod/message',{'user_id':uid,'msg_id':mid,'action':action}));return True
 owner=io.config.get('broadcaster_id');params={'broadcaster_id':owner,'moderator_id':owner}
 if name=='TwitchGetBlockedTerms':
  values=await pages(io,'moderation/blocked_terms',params,('moderator:read:blocked_terms','moderator:manage:blocked_terms'));return [identity(r.get('text'),'Blockierter Begriff') for r in values]
 term=args[0]
 if not isinstance(term,str) or not 2<=len(term)<=500 or not term.strip():raise ActionError('Blockierter Begriff benötigt 2–500 Zeichen')
 if io.dry_run:io.trace('twitch_blocked_term_preview',operation=name,term=term);return False
 auth.account(required=('moderator:manage:blocked_terms',))
 if name=='TwitchAddBlockedTerm':
  values=rows(await io.twitch('POST','moderation/blocked_terms',{'text':term},params=params))
  if len(values)!=1 or not values[0].get('id') or values[0].get('text')!=term or values[0].get('broadcaster_id')!=owner:raise ActionError('Twitch hat den blockierten Begriff nicht passend bestätigt')
 else:
  values=await pages(io,'moderation/blocked_terms',params,('moderator:manage:blocked_terms',));matches=[v for v in values if v.get('text')==term]
  if not matches:return False
  if len(matches)!=1:raise ActionError('Blockierter Begriff ist nicht eindeutig')
  params['id']=identity(matches[0].get('id'),'Begriffs-ID');empty(await io.twitch('DELETE','moderation/blocked_terms',params=params))
 return True
