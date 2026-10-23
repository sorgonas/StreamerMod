"""Dedicated moderation trigger mappings; one source per overlapping action."""
import datetime as dt
import re
from .core import ActionError
from .twitch_expansion_events import Events,person,put_user,string,boolean,count
from .twitch_shared_chat import base
ENTRIES={
92400:('Moderation · Chat Cleared',{}),92401:('Moderation · Chat Message Deleted',{}),92402:('Moderation · User Untimed Out',{}),
92403:('Moderation · Blocked Terms Added',{}),92404:('Moderation · Blocked Terms Deleted',{}),92405:('Moderation · Permitted Terms Added',{}),92406:('Moderation · Permitted Terms Deleted',{}),
92407:('Shared Chat · Shared Chat Message Deleted',{}),92408:('Shared Chat · Shared Chat User Banned',{}),92409:('Shared Chat · Shared Chat User Timed Out',{}),92410:('Shared Chat · Shared Chat User Unbanned',{}),92411:('Shared Chat · Shared Chat User Untimed Out',{}),
92412:('Moderation · AutoMod Message Held',{}),92413:('Moderation · AutoMod Message Updated',{}),92414:('Moderation · Suspicious User Message',{}),92415:('Moderation · Suspicious User Update',{}),
92416:('Moderation · Unban Request Created',{}),92417:('Moderation · Unban Request Approved',{}),92418:('Moderation · Unban Request Denied',{}),
}
MOD_ACTIONS={'clear':92400,'delete':92401,'untimeout':92402,'add_blocked_term':92403,'remove_blocked_term':92404,'add_permitted_term':92405,'remove_permitted_term':92406,'shared_chat_delete':92407,'shared_chat_ban':92408,'shared_chat_timeout':92409,'shared_chat_unban':92410,'shared_chat_untimeout':92411}
TYPES={'channel.moderate':'2','automod.message.hold':'2','automod.message.update':'2','channel.suspicious_user.message':'1','channel.suspicious_user.update':'1','channel.unban_request.create':'1','channel.unban_request.resolve':'1'}
REQUIRED=[{'moderator:read:blocked_terms','moderator:manage:blocked_terms'},{'moderator:read:chat_settings','moderator:manage:chat_settings'},{'moderator:read:unban_requests','moderator:manage:unban_requests'},{'moderator:read:banned_users','moderator:manage:banned_users'},{'moderator:read:chat_messages','moderator:manage:chat_messages'},{'moderator:read:warnings','moderator:manage:warnings'},{'moderator:read:moderators'},{'moderator:read:vips'}]
NEW_RIGHTS={'moderator:read:blocked_terms','moderator:read:unban_requests','moderator:read:moderators','moderator:read:vips','moderator:manage:automod','moderator:read:suspicious_users'}
def missing(kind,granted):
 groups=REQUIRED if kind=='channel.moderate' else [{'moderator:manage:automod'}] if kind.startswith('automod.') else [{'moderator:read:suspicious_users'}] if 'suspicious_user' in kind else [{'moderator:read:unban_requests','moderator:manage:unban_requests'}]
 return [group for group in groups if not granted&group]
def subscriptions(broadcaster):
 for kind,version in TYPES.items():yield kind,version,{'broadcaster_user_id':broadcaster,'moderator_user_id':broadcaster}
def moderator(args,event,nullable=False):
 mod=person(event,'moderator_user_',nullable);args.update({'moderator.userName':mod[''],'moderator.login':mod['Name'],'moderator.id':mod['Id'],'createdByDisplayName':mod[''],'createdByUsername':mod['Name'],'createdById':mod['Id']});return mod

def text_message(args,event):
 message=event.get('message')
 if isinstance(message,dict):text=string(message,'text',True)
 elif isinstance(message,str):text=message
 else:raise ActionError('Moderationsnachricht fehlt')
 args.update(message=text,rawInput=text)
 for index,word in enumerate(text.split()):args['input'+str(index)]=word
 args.setdefault('input0','')
 return message

def timeout_duration(expires_at,occurred_at):
 """Original 1.0.7: rounded expiry minus EventSub message timestamp.

 This is the remaining duration at Twitch's send time, not a separately
 reported configured duration. Never substitute our receive time or clock.
 """
 def timestamp(value):
  if not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,9})?(?:Z|[+-]\d\d:\d\d)',value):raise ValueError('Invalid timestamp')
  parsed=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
  delta=parsed-dt.datetime(1970,1,1,tzinfo=dt.timezone.utc)
  fraction=re.search(r'\.(\d+)',value)
  ticks=((delta.days*86400+delta.seconds)*1000000+delta.microseconds)*10
  return ticks+(int(fraction[1][6]) if fraction and len(fraction[1])>6 else 0)
 try:
  seconds=(timestamp(expires_at)-timestamp(occurred_at))/10000000
  return round(seconds) if 0<=seconds<=2147483647 else None
 except (ValueError,TypeError,OverflowError):return None

def variables(kind,event,occurred_at=''):
 if kind not in TYPES:return None
 args=base(event)
 if kind=='channel.moderate':
  action=event.get('action');trigger=MOD_ACTIONS.get(action)
  if trigger is None:return None # Ban, VIP, warning etc use existing dedicated subscriptions.
  mod=moderator(args,event);args.update(createdAt=occurred_at,createdAtSource='eventsub' if occurred_at else 'unknown')
  shared=action.startswith('shared_chat_');source=event.get('source_broadcaster_user_id')
  if shared:
   origin=person(event,'source_broadcaster_user_')
   if origin['Id']==args['broadcasterUserId']:return None
   args.update({'source.userId':origin['Id'],'source.userLogin':origin['Name'],'source.userName':origin['']},fromSharedChat=True)
  elif source and source!=args['broadcasterUserId']:return None
  if action=='clear':put_user(args,mod)
  elif trigger in (92403,92404,92405,92406):
   terms=event.get('automod_terms')
   if not isinstance(terms,dict) or terms.get('action')!=('add' if action.startswith('add_') else 'remove') or terms.get('list')!=('blocked' if 'blocked' in action else 'permitted') or not isinstance(terms.get('terms'),list) or any(not isinstance(t,str) for t in terms['terms']):raise ActionError('Wortlistenänderung widerspricht dem Ereignistyp')
   args.update(termCount=len(terms['terms']),fromAutomod=boolean(terms,'from_automod'),moderatorUsername=mod['Name'],moderatorDisplayName=mod[''])
   for index,term in enumerate(terms['terms']):args['term.'+str(index)]=term;args['term['+str(index)+']']=term;args['term.['+str(index)+']']=term
  else:
   body=event.get(action)
   if not isinstance(body,dict):raise ActionError('Moderationsaktion ohne passende Nutzerdaten')
   put_user(args,person(body,'user_'))
   if action.endswith('delete'):args.update(targetMessageId=string(body,'message_id'),message=string(body,'message_body',True))
   if action.endswith(('ban','timeout')) and not action.endswith(('unban','untimeout')):
    reason=body.get('reason')
    if reason is not None and not isinstance(reason,str):raise ActionError('Ungültiger Moderationsgrund')
    args['reason']=reason
   if action=='shared_chat_timeout':
    args['endsAt']=string(body,'expires_at')
    args['duration']=timeout_duration(args['endsAt'],occurred_at)
    args['durationSource']='eventsub_timestamp' if args['duration'] is not None else 'unknown'
  return trigger,args
 if kind.startswith('automod.message.'):
  put_user(args,person(event,'user_'));text_message(args,event);message_id=string(event,'message_id');args.update(messageId=message_id,msgId=message_id,heldAt=string(event,'held_at'))
  detail=event.get('automod')
  if detail is not None:
   if not isinstance(detail,dict):raise ActionError('Ungültige AutoMod-Kategorie')
   args.update(category=string(detail,'category'),level=count(detail,'level'))
  elif 'category' in event:args.update(category=string(event,'category'),level=count(event,'level'))
  if event.get('blocked_term') is not None:
   if not isinstance(event['blocked_term'],dict) or not isinstance(event['blocked_term'].get('terms_found'),list):raise ActionError('Ungültige gesperrte AutoMod-Begriffe')
   args['blockedTermsFound']=event['blocked_term']['terms_found']
  if 'reason' in event:args['automodReason']=string(event,'reason')
  if kind.endswith('.update'):
   status=string(event,'status')
   if status not in ('approved','denied','expired'):raise ActionError('Ungültiger AutoMod-Status')
   args['status']=status;moderator(args,event,True)
  return (92412 if kind.endswith('.hold') else 92413),args
 if 'suspicious_user' in kind:
  put_user(args,person(event,'user_'));status=string(event,'low_trust_status')
  if status not in ('none','no_treatment','active_monitoring','restricted'):raise ActionError('Ungültiger verdächtiger Nutzerstatus')
  args['lowTrustStatus']='no_treatment' if status=='none' else status
  if kind.endswith('.update'):moderator(args,event);return 92415,args
  text_message(args,event);args['msgId']=string(event['message'],'message_id')
  for key in ('types','shared_ban_channel_ids'):
   values=event.get(key)
   if not isinstance(values,list) or any(not isinstance(v,str) for v in values):raise ActionError('Ungültige verdächtige Nutzermerkmale')
   args[{'types':'suspiciousTypes','shared_ban_channel_ids':'sharedBanChannelIds'}[key]]=values
  args['banEvasionEvaluation']=string(event,'ban_evasion_evaluation');return 92414,args
 put_user(args,person(event,'user_'));args['unbanRequestId']=string(event,'id')
 if kind.endswith('.create'):args.update(text=string(event,'text',True),createdAt=string(event,'created_at'));return 92416,args
 status=string(event,'status')
 if status not in ('approved','denied'):return None
 moderator(args,event);args.update(message=string(event,'resolution_text',True),createdAt=occurred_at,createdAtSource='eventsub' if occurred_at else 'unknown')
 return (92417 if status=='approved' else 92418),args

def ingest(io,kind,event,identity,occurred_at=''):
 if io.dry_run or not isinstance(event,dict) or event.get('broadcaster_user_id')!=io.config.get('broadcaster_id'):return None
 mapped=variables(kind,event,occurred_at)
 if not mapped:return None
 return Events(io).commit(kind,identity,*mapped)

def example(kind,config,trigger=None):
 event={'broadcaster_user_id':config.get('broadcaster_id') or 'test-broadcaster','broadcaster_user_login':config.get('twitch_login') or 'testbroadcaster','broadcaster_user_name':'Test Broadcaster','moderator_user_id':'test-mod','moderator_user_login':'testmod','moderator_user_name':'Test Moderator','user_id':'test-user','user_login':'testuser','user_name':'Test User'}
 at='2026-10-14T12:00:00Z'
 if kind<=92411:
  name=next(key for key,value in MOD_ACTIONS.items() if value==kind);event['action']=name;kind_name='channel.moderate'
  if name.startswith('shared_chat_'):event.update(source_broadcaster_user_id='test-source',source_broadcaster_user_login='testsource',source_broadcaster_user_name='Test Source')
  if kind in (92403,92404,92405,92406):event['automod_terms']={'action':'add' if name.startswith('add_') else 'remove','list':'blocked' if 'blocked' in name else 'permitted','terms':['test term'],'from_automod':False}
  elif name!='clear':event[name]={'user_id':'test-user','user_login':'testuser','user_name':'Test User','message_id':'test-message','message_body':'Test text','reason':'Test reason','expires_at':'2026-10-14T12:01:00Z'}
 elif kind in (92412,92413):
  kind_name='automod.message.'+('hold' if kind==92412 else 'update');event.update(message_id='test-message',message={'text':'Test automod message','fragments':[]},automod={'category':'aggression','level':1},held_at=at,reason='automod',status='approved')
 elif kind in (92414,92415):
  kind_name='channel.suspicious_user.'+('message' if kind==92414 else 'update');event.update(low_trust_status='restricted',message={'text':'Test suspicious message','message_id':'test-message','fragments':[]},types=['manually_added'],shared_ban_channel_ids=[],ban_evasion_evaluation='unknown')
 else:
  kind_name='channel.unban_request.'+('create' if kind==92416 else 'resolve');event.update(id='test-request',text='Please unban',created_at=at,resolution_text='Test decision',status='approved' if kind==92417 else 'denied')
 if kind==92409 and trigger:
  duration=next((trigger[key] for key in ('rangeMin','rangeMax') if type(trigger.get(key)) is int and trigger[key]>=0),60)
  event['shared_chat_timeout']['expires_at']=(dt.datetime.fromisoformat(at.replace('Z','+00:00'))+dt.timedelta(seconds=duration)).isoformat()
 return variables(kind_name,event,at)[1]
