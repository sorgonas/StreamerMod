"""Public projections for existing native Twitch event producers.

Every family has its own field allowlist; internal Action arguments never escape.
Original enum names are verified, exact original payload parity is a separate check.
"""
import copy,math,re
EVENTS={90030: 'StreamUpdate', 90033: 'PyramidSuccess', 90034: 'PyramidBroken', 91150: 'SubCounterRollover', 91450: 'ChatEmoteModeOn', 91451: 'ChatEmoteModeOff', 91452: 'ChatFollowerModeOn', 91453: 'ChatFollowerModeOff', 91454: 'ChatFollowerModeChanged', 91455: 'ChatSlowModeOn', 91456: 'ChatSlowModeOff', 91457: 'ChatSlowModeChanged', 91458: 'ChatSubscriberModeOn', 91459: 'ChatSubscriberModeOff', 91460: 'ChatUniqueModeOn', 91461: 'ChatUniqueModeOff', 92200: 'ShieldModeBegin', 92201: 'ShieldModeEnd', 92202: 'WarnedUser', 92203: 'WarningAcknowledged', 92204: 'ShoutoutCreated', 92205: 'ShoutoutReceived', 92206: 'CharityStarted', 92207: 'CharityProgress', 92208: 'CharityCompleted', 92209: 'CharityDonation', 92210: 'GuestStarSessionBegin', 92211: 'GuestStarSessionEnd', 92212: 'GuestStarGuestUpdate', 92213: 'GuestStarSettingsUpdate', 92300: 'SharedChatSessionBegin', 92301: 'SharedChatSessionUpdate', 92302: 'SharedChatSessionEnd', 92303: 'Announcement', 92304: 'SharedChatAnnouncement', 92305: 'SharedChatSub', 92306: 'SharedChatResub', 92307: 'SharedChatSubGift', 92308: 'SharedChatCommunitySubGift', 92309: 'SharedChatGiftPaidUpgrade', 92310: 'SharedChatPrimePaidUpgrade', 92311: 'SharedChatPayItForward', 92312: 'SharedChatRaid', 92313: 'Modiversary', 92314: 'SharedModiversary', 92315: 'WatchStreak', 92316: 'BitsBadgeTier', 92400: 'ChatCleared', 92401: 'ChatMessageDeleted', 92402: 'UserUntimedOut', 92403: 'BlockedTermsAdded', 92404: 'BlockedTermsDeleted', 92405: 'PermittedTermsAdded', 92406: 'PermittedTermsDeleted', 92407: 'SharedChatMessageDeleted', 92408: 'SharedChatUserBanned', 92409: 'SharedChatUserTimedout', 92410: 'SharedChatUserUnbanned', 92411: 'SharedChatUserUntimedout', 92412: 'AutoModMessageHeld', 92413: 'AutoModMessageUpdate', 92414: 'SuspiciousUserMessage', 92415: 'SuspiciousUserUpdate', 92416: 'UnbanRequestCreated', 92417: 'UnbanRequestApproved', 92418: 'UnbanRequestDenied', 92500: 'GoalBegin', 92501: 'GoalProgress', 92502: 'GoalEnd', 92504: 'PowerUpRedemption', 92505: 'CustomPowerUpRedemption', 92506: 'AutomaticRewardRedemption', 92700: 'UpcomingAd', 92701: 'PresentViewers', 92800: 'RaidStart', 92801: 'RaidCancelled'}
MODE_FIELDS=('emoteMode','followerMode','slowMode','subscriberMode','uniqueMode','followerModeDuration','slowModeWaitTime','occurredAt')
MOD_FIELDS=('reason','endsAt','createdAt','createdAtSource','createdById','createdByUsername','createdByDisplayName','moderator.id','moderator.login','moderator.userName','moderatorUsername','moderatorDisplayName','fromSharedChat','source.userId','source.userLogin','source.userName','fromAutomod','termCount','targetMessageId','message','msgId','heldAt','category','level','automodReason','lowTrustStatus','banEvasionEvaluation','unbanRequestId','text','status')
NOTICE_FIELDS=('chatMessageId','sourceMessageId','message','systemMessage','fromSharedChat','source.userId','source.userLogin','source.userName','anonymous','announceColor','tier','cumulative','monthStreak','streakShared','multiMonthDuration','monthsGifted','totalSubsGifted','fromGiftBomb','gifts','totalGifts','recipientId','recipientUserName','recipientUser','viewerCount','profileImageUrl','modiversaryMonths','months','watchStreak','copoReward','watchStreakId','bitsBadgeTier')
EXPANSION_FIELDS=('moderatorId','moderatorLogin','moderatorName','startedAt','endedAt','moderator.userName','moderator.login','moderator.id','reason','viewerCount','targetUserId','targetUserLogin','targetUserDisplayName','cooldownEndsAt','targetCooldownEndsAt','sessionId','moderatorUserName','moderatorUserLogin','moderatorUserId','guestUserName','guestUserLogin','guestUserId','slotId','state','hostVideoEnabled','hostAudioEnabled','hostVolume','isModeratorSendLiveEnabled','slotCount','isBrowserSourceAudioEnabled','groupLayout')
CHARITY_FIELDS=tuple('charity.'+key for key in ('id','name','description','logo','website','campaignId','donationId','startedAt','stoppedAt'))+tuple('charity.'+prefix+'.'+key for prefix in ('amount','currentAmount','targetAmount') for key in ('value','valueMinor','currency','decimalPlaces'))
GOAL_FIELDS=tuple('goal.'+key for key in ('id','type','description','currentAmount','targetAmount','startedAt','endedAt','isAchieved'))
POWER_FIELDS=('bits','powerUpType','rewardType','rewardCost','rewardCostUnit','messageEffectId','redemptionId','redeemedAt','customPowerUpId','rewardId','rewardTitle','rewardPrompt','status','userInput','message','gigantifiedEmoteId','gigantifiedEmoteName','powerUpEmoteId','powerUpEmoteName','unlockedEmoteId','unlockedEmoteName')
RAID_FIELDS=('raidUserId','raidUserName','raidUser','viewers','raidTargetInfoAvailable','raidEventSource','createdAt','createdAtSource','moderatorUser','moderatorUserId','moderatorUserName','raidUserProfileImageURL')

def scalar(value):
 if value is None or type(value) in (bool,int,str):return value
 if type(value) is float and math.isfinite(value):return value
 raise ValueError('Public event field must be scalar')
def select(args,keys):return {k:scalar(args[k]) for k in keys if k in args}
def strings(value):
 if not isinstance(value,list) or len(value)>1000 or any(not isinstance(v,str) for v in value):raise ValueError('Public event list')
 return list(value)
def people(value,keys):
 if not isinstance(value,list) or len(value)>10000 or any(not isinstance(v,dict) for v in value):raise ValueError('Public event users')
 return [select(v,keys) for v in value]

def project(engine,kind,args):
 from .websocket_twitch_events import base_user,owner
 body={'broadcaster':owner(engine,args),'isTest':args.get('isTest') is True}
 if any(k in args for k in ('userId','userName','userLogin')):body['user']=base_user(args,'roles' in args)
 if 91450<=kind<=91461:body.update(select(args,MODE_FIELDS))
 elif 92200<=kind<=92213:
  body.update(select(args,EXPANSION_FIELDS+CHARITY_FIELDS))
  if 'chatRulesCited' in args:body['chatRulesCited']=None if args['chatRulesCited'] is None else strings(args['chatRulesCited'])
 elif 92300<=kind<=92302:
  body.update(select(args,('sessionId','host.userId','host.userLogin','host.userName')))
  if 'participants' in args:body['participants']=people(args['participants'],('broadcaster_user_id','broadcaster_user_login','broadcaster_user_name'))
 elif 92303<=kind<=92316:body.update(select(args,NOTICE_FIELDS))
 elif 92400<=kind<=92418:
  body.update(select(args,MOD_FIELDS))
  if kind in (92403,92404,92405,92406):
   n=args.get('termCount',0)
   if type(n) is not int or not 0<=n<=1000:raise ValueError('term count')
   body['terms']=[scalar(args['term.'+str(i)]) for i in range(n)]
  for key in ('suspiciousTypes','sharedBanChannelIds'):
   if key in args:body[key]=strings(args[key])
  if 'blockedTermsFound' in args:
   body['blockedTermsFound']=people(args['blockedTermsFound'],('term_id','owner_broadcaster_user_id','owner_broadcaster_user_login','owner_broadcaster_user_name'))
 elif 92500<=kind<=92502:body.update(select(args,GOAL_FIELDS))
 elif 92504<=kind<=92506:body.update(select(args,POWER_FIELDS))
 elif kind==92700:body.update(select(args,('minutes','adLength','snoozesLeft','nextAdAt','changeSource')))
 elif kind==92701:
  body.update(select(args,('isLive','presentUsersCount','presentUsersSource')));body['users']=people(args.get('users',[]),('id','name','login','userId','userName','displayName','user','platform','userType'))
 elif kind in (92800,92801):body.update(select(args,RAID_FIELDS))
 elif kind==91150:body.update(select(args,('subCounter','rollover','rolloverCount')))
 elif kind in (90033,90034):
  body.update(select(args,('pyramidEmote','pyramidHeight','pyramidWidth','pyramidOwnerId','pyramidOwnerUsername','pyramidOwnerDisplayName')))
  if 'pyramidUsers' in args:body['pyramidUsers']=strings(args['pyramidUsers'])
 elif kind==90030:
  body.update(select(args,('title','gameId','gameName','language','is_mature')))
  if 'content_classification_labels' in args:body['content_classification_labels']=strings(args['content_classification_labels'])
 compatibility(body,kind,args)
 return body

def compatibility(body,kind,args):
 # Aliases supported by the unmodified official client type declarations.
 aliases={}
 if kind in (92200,92201):aliases={'moderatorId':'moderator_user_id','moderatorLogin':'moderator_user_login','moderatorName':'moderator_user_name','startedAt':'started_at','endedAt':'ended_at'}
 elif kind==92204:aliases={'userId':'moderator_user_id','userName':'moderator_user_login','user':'moderator_user_name','targetUserId':'to_broadcaster_user_id','targetUserLogin':'to_broadcaster_user_login','targetUserDisplayName':'to_broadcaster_user_name','viewerCount':'viewer_count','startedAt':'started_at','cooldownEndsAt':'cooldown_ends_at','targetCooldownEndsAt':'target_cooldown_ends_at'}
 elif 92206<=kind<=92209:
  aliases={'charity.'+source:target for source,target in [('id','id'),('campaignId','campaign_id'),('donationId','id'),('name','charity_name'),('description','charity_description'),('logo','charity_logo'),('website','charity_website'),('startedAt','started_at'),('stoppedAt','stopped_at')]}
  if kind==92209:aliases.update(userId='user_id',userName='user_login',user='user_name')
  for prefix,target in [('amount','amount'),('currentAmount','current_amount'),('targetAmount','target_amount')]:
   if 'charity.'+prefix+'.valueMinor' in args:
    body[target]=None if args['charity.'+prefix+'.valueMinor'] is None else {out:scalar(args['charity.'+prefix+'.'+key]) for key,out in [('valueMinor','value'),('decimalPlaces','decimal_places'),('currency','currency')]}
 elif kind in (92303,92304):aliases={'chatMessageId':'msgId','announceColor':'announcementColor','userId':'userId','userName':'userName','user':'displayName'}
 elif kind==92400:aliases={'createdById':'created_by_user_id','createdByUsername':'created_by'}
 elif kind in (92401,92407):
  aliases={'userName':'userName'}
  if 'user' in body:body['role']=body['user']['role']
 elif kind in (90033,90034):
  aliases={'pyramidWidth':'width','pyramidEmote':'emote',('totalPyramids' if kind==90033 else 'totalPyramidsBroken'):'total'}
  if kind==90034:aliases.update(pyramidOwnerId='ownerId',pyramidOwnerUsername='ownerUsername',pyramidOwnerDisplayName='ownerDisplay')
  if 'user' in body:
   user=body['user'];body['user']={**user,'display':user['name'],'name':user['login']}
 elif kind==90030:
  aliases={'title':'status','oldTitle':'oldStatus'};owner=body['broadcaster'];body.update(channelId=owner['id'],channel=owner['login'],game={'id':args.get('gameId'),'name':args.get('gameName')})
  if 'oldGameId' in args:body['oldGame']={'id':scalar(args['oldGameId']),'name':scalar(args.get('oldGameName'))}
 body.update({target:scalar(args[source]) for source,target in aliases.items() if source in args})
