"""YouTube producers backed by the live chat protocol, with explicit public fields."""
import copy,datetime as dt,re
from .core import ActionError
EVENTS={4001:'BroadcastStarted',4002:'BroadcastEnded',4003:'Message',4005:'UserBanned',4006:'SuperChat',4007:'SuperSticker',4008:'NewSponsor',4009:'MemberMileStone',4010:'NewSponsorOnlyStarted',4011:'NewSponsorOnlyEnded',4014:'MembershipGift',4015:'GiftMembershipReceived',4016:'FirstWords',4019:'BroadcastMonitoringStarted',4020:'BroadcastMonitoringEnded',4031:'UserTimedout',96050:'Connected',96051:'Disconnected'}
TRIGGERS={k:(path,{}) for k,path in {4001: 'Broadcast · Broadcast Started', 4002: 'Broadcast · Broadcast Ended', 4003: 'Chat · Message', 4005: 'General · User Banned', 4006: 'Chat · Super Chat', 4007: 'Chat · Super Sticker', 4008: 'General · New Sponsor', 4009: 'Membership · Member Milestone', 4010: 'General · Sponsor Only Started', 4011: 'General · Sponsor Only Ended', 4014: 'Membership · Membership Gift', 4015: 'Membership · Gift Membership Received', 4016: 'Chat · First Words', 4019: 'Broadcast · Broadcast Monitoring Started', 4020: 'Broadcast · Broadcast Monitoring Ended', 4031: 'General · User Timed Out', 96050: 'Connection · Connected', 96051: 'Connection · Disconnected'}.items()}
KINDS={'giftEvent':4030,'textMessageEvent':4003,'superChatEvent':4006,'superStickerEvent':4007,'newSponsorEvent':4008,'memberMilestoneChatEvent':4009,'membershipGiftingEvent':4014,'giftMembershipReceivedEvent':4015,'sponsorOnlyModeStartedEvent':4010,'sponsorOnlyModeEndedEvent':4011,'userBannedEvent':4005}
DETAILS={'giftDetails':('jewelsAmount','giftName','giftUrl','hasVisualEffect','comboCount','altText','language'),'superChatDetails':('amountMicros','currency','amountDisplayString','userComment','tier'),'superStickerDetails':('amountMicros','currency','amountDisplayString','tier'),'newSponsorDetails':('memberLevelName','isUpgrade'),'memberMilestoneChatDetails':('memberLevelName','memberMonth','userComment'),'membershipGiftingDetails':('giftMembershipsCount','giftMembershipsLevelName'),'giftMembershipReceivedDetails':('memberLevelName','gifterChannelId','associatedMembershipGiftingMessageId')}
def text(value,limit=1000):return value[:limit] if isinstance(value,str) else ''
def timestamp(value):
 try:
  date=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
  if date.tzinfo is None:raise ValueError()
  return date.timestamp()
 except (ValueError,AttributeError,TypeError):raise ActionError('YouTube-Ereignis ohne gültigen Zeitpunkt') from None

def parse(item,channel,broadcast,chat):
 if not isinstance(item,dict) or not isinstance(item.get('snippet'),dict):raise ActionError('Ungültige YouTube-Nachricht')
 snippet=item['snippet'];kind=snippet.get('type');native=KINDS.get(kind)
 if native is None:return None
 if snippet.get('liveChatId')!=chat:raise ActionError('YouTube-Nachricht gehört zu einem anderen Livechat')
 identity=text(item.get('id'),500)
 if not identity:raise ActionError('YouTube-Nachrichten-ID fehlt')
 stamp=timestamp(snippet.get('publishedAt'));author=item.get('authorDetails') or {}
 if not isinstance(author,dict):raise ActionError('Ungültiger YouTube-Absender')
 uid=text(author.get('channelId') or snippet.get('authorChannelId'),200);name=text(author.get('displayName'),200)
 if author.get('channelId') and snippet.get('authorChannelId') and author['channelId']!=snippet['authorChannelId']:raise ActionError('Widersprüchlicher YouTube-Absender')
 for field in ('textMessageDetails','userBannedDetails'):
  if field in snippet and not isinstance(snippet[field],dict):raise ActionError('Ungültige YouTube-Nachrichtendetails')
 if native==4003 and not uid:raise ActionError('YouTube-Nachricht ohne Kanal-ID')
 roles=[label for field,label in [('isChatOwner','Broadcaster'),('isChatModerator','Moderators'),('isChatSponsor','Subscribers')] if author.get(field) is True and (label!='Broadcaster' or uid==channel)]
 message=text((snippet.get('textMessageDetails') or {}).get('messageText') if native==4003 else snippet.get('displayMessage'),2000)
 args={'platform':'youtube','userType':'youtube','commandSource':'youtube','commandType':'message','userId':uid,'userName':uid,'userLogin':uid,'user':name,'roles':roles,'message':message,'rawInput':message,'msgId':identity,'messageId':identity,'youtubeChannelId':channel,'broadcastId':broadcast,'broadcast.id':broadcast,'liveChatId':chat,'publishedAt':snippet['publishedAt'],'isInternal':False}
 for detail,fields in DETAILS.items():
  value=snippet.get(detail)
  if isinstance(value,dict):args[detail]={k:copy.deepcopy(value[k]) for k in fields if k in value and isinstance(value[k],(str,int,bool))}
 if native in (4006,4007):
  details=args.get('superChatDetails' if native==4006 else 'superStickerDetails',{})
  if 'amountMicros' in details:
   from .youtube_extras import number
   args['amount']=number(details['amountMicros'])/1000000
 if native==4030:
  from .youtube_extras import number
  details=args.get('giftDetails')
  if not isinstance(details,dict) or 'jewelsAmount' not in details:raise ActionError('Geschenkdetails fehlen')
  for key in ('jewelsAmount','comboCount'):
   if key in details:details[key]=number(details[key])
 if native==4005:
  value=snippet.get('userBannedDetails') or {};target=value.get('bannedUserDetails') or {};temporary=value.get('banType')=='temporary';native=4031 if temporary else 4005
  if not isinstance(target,dict):raise ActionError('Ungültiges YouTube-Moderationsziel')
  args.update(targetUserId=text(target.get('channelId'),200),targetUser=text(target.get('displayName'),200),banType='temporary' if temporary else 'permanent')
  if temporary:args['duration']=text(str(value.get('banDurationSeconds','')),30)
 row={'id':identity,'platform':'youtube','user':name,'login':uid,'userId':uid,'message':message,'roles':roles,'emotes':{},'publishedAt':snippet['publishedAt'],'receivedAt':stamp,'liveChatId':chat}
 return native,args,row,stamp

def forward(engine,kind,args):
 if kind not in EVENTS or engine.io.dry_run:return
 hub=getattr(getattr(engine,'studio',None),'main_websocket',None)
 if hub is None:return
 keys=('platform','userType','userId','userName','user','roles','message','messageId','youtubeChannelId','broadcastId','broadcast.id','liveChatId','publishedAt','isInternal','targetUserId','targetUser','banType','duration','title','isInitialState','broadcast','reason','statistics','pollId','question','options','status','jewelsAmount','comboCount','isUpdate','amount',*DETAILS)
 hub.publish('YouTube',EVENTS[kind],{key:copy.deepcopy(args[key]) for key in keys if key in args})

def combined_messages(studio,limit=1000):
 twitch=getattr(getattr(studio,'twitch',None),'messages',[]);youtube=getattr(getattr(studio,'youtube',None),'messages',[])
 return copy.deepcopy(sorted([*twitch,*youtube],key=lambda row:row.get('receivedAt',0))[-limit:])

from .youtube_extras import EVENT_PATHS
for kind,(name,path) in EVENT_PATHS.items():
 EVENTS[kind]=name
 TRIGGERS[kind]=(path,{})

for _kind in (4006,4007,4030,4031):TRIGGERS[_kind][1].update(rangeMin=-1,rangeMax=-1)
TRIGGERS[4016][1].update(username='',isUserId=False)
