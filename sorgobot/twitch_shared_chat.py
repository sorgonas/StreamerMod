"""Shared sessions and typed chat notices, kept apart from local sub events."""
import copy,math
from .core import ActionError
from .twitch_expansion_events import string,person,count,boolean,put_user,Events
from .twitch_subscription_events import notification as subscription_notice,matches as subscription_matches
ENTRIES={
92300:('Shared Chat · Twitch Shared Chat Session Begin',{}),92301:('Shared Chat · Twitch Shared Chat Session Update',{}),92302:('Shared Chat · Twitch Shared Chat Session End',{}),
92303:('General · Announcement',{}),92304:('Shared Chat · Shared Announcement',{}),
92305:('Shared Chat · Shared Sub',{'tiers':[]}),92306:('Shared Chat · Shared Resub',{'tiers':[],'rangeMin':-1,'rangeMax':-1}),92307:('Shared Chat · Shared Sub Gift',{'tiers':[],'anonymous':'either','monthsGifted':[],'rangeMin':-1,'rangeMax':-1}),92308:('Shared Chat · Shared Community Sub Gift',{'tiers':[],'anonymous':'either','rangeMin':-1,'rangeMax':-1}),
92309:('Shared Chat · Shared Gift Paid Upgrade',{}),92310:('Shared Chat · Shared Prime Paid Upgrade',{}),92311:('Shared Chat · Shared Pay It Forward',{}),92312:('Shared Chat · Raid',{'rangeMin':-1,'rangeMax':-1}),
92313:('Chat · Modiversary',{}),92314:('Shared Chat · Shared Modiversary',{}),92315:('Chat · Watch Streak',{'rangeMin':-1,'rangeMax':-1}),92316:('Chat · Bits Badge Tier',{}),
}
SESSIONS={'channel.shared_chat.begin':92300,'channel.shared_chat.update':92301,'channel.shared_chat.end':92302}
NOTICES={'announcement':92303,'shared_chat_announcement':92304,'shared_chat_sub':92305,'shared_chat_resub':92306,'shared_chat_sub_gift':92307,'shared_chat_community_sub_gift':92308,'shared_chat_gift_paid_upgrade':92309,'shared_chat_prime_paid_upgrade':92310,'shared_chat_pay_it_forward':92311,'shared_chat_raid':92312,'modiversary':92313,'shared_chat_modiversary':92314,'watch_streak':92315,'bits_badge_tier':92316}
SUB_KINDS={92305:90850,92306:90851,92307:90031,92308:90032,92309:90852,92310:90853,92311:90854}
def subscriptions(broadcaster):
 for kind in SESSIONS:yield kind,'1',{'broadcaster_user_id':broadcaster}

def base(event):
 broad=person(event,'broadcaster_user_');return {'platform':'twitch','userType':'twitch','broadcasterUserId':broad['Id'],'broadcasterUserName':broad['Name'],'broadcasterUser':broad['']}

def session(kind,event):
 args=base(event);host=person(event,'host_broadcaster_user_');args.update(sessionId=string(event,'session_id'),**{'host.userId':host['Id'],'host.userLogin':host['Name'],'host.userName':host['']})
 if kind!='channel.shared_chat.end':
  participants=event.get('participants')
  if not isinstance(participants,list):raise ActionError('Shared-Chat-Teilnehmerliste fehlt')
  seen=set()
  for participant in participants:
   if not isinstance(participant,dict):raise ActionError('Ungültiger Shared-Chat-Teilnehmer')
   member=person(participant,'broadcaster_user_')
   if member['Id'] in seen:raise ActionError('Doppelter Shared-Chat-Teilnehmer')
   seen.add(member['Id'])
  args['participants']=copy.deepcopy(participants)
 return SESSIONS[kind],args

def chat(event):
 message=event.get('message')
 if not isinstance(message,dict) or not isinstance(message.get('text'),str) or not isinstance(message.get('fragments'),list):raise ActionError('Chat-Hinweis ohne gültige Nachricht')
 fragments=message['fragments']
 if any(not isinstance(f,dict) or not isinstance(f.get('text'),str) or f.get('type') not in ('text','emote','mention','cheermote') for f in fragments):raise ActionError('Ungültige Chat-Hinweis-Fragmente')
 return {'message':message['text'],'messageStripped':''.join(f['text'] for f in fragments if f['type']!='emote') if fragments else message['text'],'rawInput':message['text'],'input0':'','msgId':string(event,'message_id'),'chatMessageId':string(event,'message_id'),'systemMessage':string(event,'system_message',True)}

def roles(args,badges):
 if badges is None:return
 if not isinstance(badges,list) or any(not isinstance(b,dict) or not isinstance(b.get('set_id'),str) for b in badges):raise ActionError('Ungültige Chat-Badges')
 names={b['set_id'] for b in badges};role=next((name for key,name in [('broadcaster','Broadcaster'),('moderator','Moderator'),('vip','VIP'),('subscriber','Subscriber')] if key in names),'Viewer')
 args.update(role=role,isSubscribed='subscriber' in names,roles=[label for key,label in [('broadcaster','Broadcaster'),('moderator','Moderators'),('vip','VIPs'),('subscriber','Subscribers')] if key in names])

def notice(event):
 name=event.get('notice_type');trigger=NOTICES.get(name)
 if trigger is None:return None
 shared=name.startswith('shared_chat_');source=event.get('source_broadcaster_user_id')
 if not shared and source and source!=event.get('broadcaster_user_id'):return None
 if shared:
  if not source:raise ActionError('Shared-Chat-Hinweis ohne Quellkanal')
  if source==event.get('broadcaster_user_id'):return None
 body=event.get(name)
 if not isinstance(body,dict):raise ActionError('Chat-Hinweistyp ohne zugehörige Daten')
 anonymous=boolean(event,'chatter_is_anonymous');args=base(event);args.update(chat(event));args['anonymous']=anonymous;args['fromSharedChat']=shared
 if anonymous:args.update(userId='',userName='',userLogin='',user='Anonymous')
 else:put_user(args,person(event,'chatter_user_'))
 if shared:
  origin=person(event,'source_broadcaster_user_');args.update({'source.userId':origin['Id'],'source.userLogin':origin['Name'],'source.userName':origin['']});args['sourceMessageId']=string(event,'source_message_id',nullable=True)
  roles(args,event.get('source_badges'))
 else:roles(args,event.get('badges'))
 if trigger in SUB_KINDS:
  regular=name.removeprefix('shared_chat_');copied=copy.deepcopy(event);data=copy.deepcopy(body)
  if 'sub_plan' in data and 'sub_tier' not in data:data['sub_tier']=data['sub_plan']
  if regular in ('sub','resub','sub_gift','community_sub_gift','prime_paid_upgrade'):
   if data.get('sub_tier') not in ('1000','2000','3000'):raise ActionError('Ungültige Shared-Chat-Abo-Stufe')
  for key in ('duration_months','cumulative_months','streak_months','cumulative_total','total'):
   if key in data and data[key] is not None:count(data,key)
  for key in ('is_prime','is_gift','gifter_is_anonymous'):
   if key in data and data[key] is not None:boolean(data,key)
  if regular=='sub_gift':
   for key in ('recipient_user_id','recipient_user_login','recipient_user_name'):string(data,key)
  if regular=='community_sub_gift':count(data,'total')
  copied.update(notice_type=regular,source_broadcaster_user_id=event['broadcaster_user_id']);copied[regular]=data
  mapped=subscription_notice(copied)
  if mapped is None:raise ActionError('Shared-Chat-Abo konnte nicht zugeordnet werden')
  args={**mapped[1],**args}
 elif trigger in (92303,92304):args['announceColor']=string(body,'color').upper()
 elif trigger==92312:
  put_user(args,person(body,'user_'));args.update(viewerCount=count(body,'viewer_count'),profileImageUrl=string(body,'profile_image_url',True))
 elif trigger in (92313,92314):args.update(modiversaryMonths=count(body,'months'),months=count(body,'months'))
 elif trigger==92315:args.update(watchStreak=count(body,'streak_count'),copoReward=count(body,'channel_points_awarded'),watchStreakId=args['msgId'])
 elif trigger==92316:args['bitsBadgeTier']=count(body,'tier')
 return trigger,args

def ingest(io,kind,event,identity):
 if io.dry_run or not isinstance(event,dict) or event.get('broadcaster_user_id')!=io.config.get('broadcaster_id'):return None
 mapped=session(kind,event) if kind in SESSIONS else notice(event)
 if mapped is None:return None
 return Events(io).commit(kind+(':'+event['notice_type'] if kind=='channel.chat.notification' else ''),identity,*mapped)

def matches(kind,trigger,args):
 if kind in SUB_KINDS:return subscription_matches(SUB_KINDS[kind],trigger,args)
 if kind in (92312,92315):
  key='viewerCount' if kind==92312 else 'watchStreak';observed=args.get(key)
  if type(observed) is not int or observed<0:return False
  for bound,lower in [('rangeMin',True),('rangeMax',False)]:
   value=trigger.get(bound,-1)
   if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<-1:return False
   if value!=-1 and (observed<value if lower else observed>value):return False
 return True

# Synthetic manual examples use the documented payload fields, not live events.
def example(kind,config,trigger=None):
 trigger=trigger or {};broad=config.get('broadcaster_id') or 'test-broadcaster';login=config.get('twitch_login') or 'testbroadcaster'
 event={'broadcaster_user_id':broad,'broadcaster_user_login':login,'broadcaster_user_name':login}
 if kind in SESSIONS.values():
  event.update(session_id='test-shared-session',host_broadcaster_user_id='test-host',host_broadcaster_user_login='testhost',host_broadcaster_user_name='Test Host',participants=[{'broadcaster_user_id':broad,'broadcaster_user_login':login,'broadcaster_user_name':login}])
  return session(next(k for k,v in SESSIONS.items() if v==kind),event)[1]
 name=next(k for k,v in NOTICES.items() if v==kind);event.update(notice_type=name,chatter_user_id='test-user',chatter_user_login='testuser',chatter_user_name='Test User',chatter_is_anonymous=False,badges=[],system_message='Manual chat notice',message_id='test-chat-id',message={'text':'Test notice','fragments':[{'type':'text','text':'Test notice'}]})
 if name.startswith('shared_chat_'):event.update(source_broadcaster_user_id='test-source',source_broadcaster_user_login='testsource',source_broadcaster_user_name='Test Source',source_message_id='test-source-id',source_badges=[])
 if kind in SUB_KINDS:
  event[name]={'sub_tier':'1000','duration_months':1,'cumulative_months':6,'streak_months':None,'total':5,'cumulative_total':10,'recipient_user_id':'test-recipient','recipient_user_login':'recipient','recipient_user_name':'Recipient'}
 elif kind in (92303,92304):event[name]={'color':'BLUE'}
 elif kind==92312:event[name]={'user_id':'test-raider','user_login':'testraider','user_name':'Test Raider','viewer_count':max(0,int(trigger.get('rangeMin',20))),'profile_image_url':''}
 elif kind in (92313,92314):event[name]={'months':12}
 elif kind==92315:event[name]={'streak_count':max(5,int(trigger.get('rangeMin',5))),'channel_points_awarded':450}
 else:event[name]={'tier':100}
 return notice(event)[1]
