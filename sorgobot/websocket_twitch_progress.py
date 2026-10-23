"""Allowlisted subscription/reward/vote/train projections over existing triggers."""
import contextvars,copy

DELIVERY=contextvars.ContextVar('twitch_native_delivery',default=None)
EVENTS={90850:'Sub',90851:'ReSub',90031:'GiftSub',90032:'GiftBomb',90852:'GiftPaidUpgrade',90853:'PrimePaidUpgrade',90854:'PayItForward',
 112:'RewardRedemption',90550:'RewardRedemptionUpdated',
 90650:'PollCreated',90651:'PollUpdated',90652:'PollCompleted',90653:'PollTerminated',90654:'PollArchived',
 90660:'PredictionCreated',90661:'PredictionUpdated',90662:'PredictionLocked',90663:'PredictionCompleted',90664:'PredictionCanceled',
 91050:'HypeTrainStart',91051:'HypeTrainUpdate',91052:'HypeTrainLevelUp',91053:'HypeTrainEnd'}
SUBS={90850,90851,90031,90032,90852,90853,90854}
VOTES=set(range(90650,90655))|set(range(90660,90665))
TRAINS=set(range(91050,91054))

def fields(source,keys):
 if not isinstance(source,dict):raise ValueError('event object')
 result={key:copy.deepcopy(source[key]) for key in keys if key in source}
 if any(isinstance(value,(dict,list)) for value in result.values()):raise ValueError('event scalar')
 return result

def rows(source,keys):
 if not isinstance(source,list):raise ValueError('event rows')
 if any(not isinstance(row,dict) for row in source):raise ValueError('event row')
 return [fields(row,keys) for row in source]

def observed(engine,kind,args):
 d=DELIVERY.get()
 if not d or not d['active'] or d['engine'] is not engine or args.get('isTest'):return {},''
 event=d['event'];family=d['kind']
 valid=(kind in SUBS and family=='channel.chat.notification' and args.get('chatMessageId')==event.get('message_id') or
  kind in VOTES and family.startswith(('channel.poll.','channel.prediction.')) and args.get('pollId',args.get('predictionId'))==event.get('id') or
  kind in TRAINS and family.startswith('channel.hype_train.') and args.get('hypeTrainId')==event.get('id') or
  kind in (112,90550) and family.startswith('channel.channel_points_custom_reward_redemption.') and args.get('redemptionId')==event.get('id'))
 return (event,d['stamp']) if valid else ({},'')

def sub(kind,args,event):
 body={};notice=event.get(event.get('notice_type'),{}) if event else {}
 if not isinstance(notice,dict):raise ValueError('subscription')
 # Keep the original platform chat ID, never the EventSub delivery ID.
 if args.get('chatMessageId'):body['messageId']=args['chatMessageId']
 for target,key in {'message':'message','text':'message','systemMessage':'systemMessage','isAnonymous':'anonymous','shareStreak':'streakShared','cumulativeMonths':'cumulative','streakMonths':'monthStreak','durationMonths':'multiMonthDuration','monthsGifted':'monthsGifted','totalSubsGifted':'totalSubsGifted','fromSubBomb':'fromGiftBomb','gifts':'gifts','totalGifts':'totalGifts','recipientUserId':'recipientId','recipientUsername':'recipientUserName','recipientDisplayName':'recipientUser'}.items():
  if key in args and args[key] is not None:body[target]=args[key]
 if 'sub_tier' in notice:body['subTier']=notice['sub_tier']
 elif args.get('tier') in ('tier 1','tier 2','tier 3'):body['subTier']={'tier 1':'1000','tier 2':'2000','tier 3':'3000'}[args['tier']]
 if 'is_prime' in notice:body['isPrime']=notice['is_prime']
 if args.get('tier')=='prime':body['isPrime']=True
 for key,target in [('is_gift','isGift'),('gifter_is_anonymous','gifterIsAnonymous')]:
  if key in notice:body[target]=notice[key]
 if kind==90031:body['recipient']={'id':args.get('recipientId'),'login':args.get('recipientUserName'),'name':args.get('recipientUser'),'type':'twitch'}
 if 'gifter_user_id' in notice and not notice.get('gifter_is_anonymous'):
  body['gifter']={'id':notice['gifter_user_id'],'login':notice.get('gifter_user_login'),'name':notice.get('gifter_user_name'),'type':'twitch'}
 if event.get('message') is not None:
  if not isinstance(event['message'],dict):raise ValueError('subscription message')
  fragments=event['message'].get('fragments',[])
  body['parts']=rows(fragments,('type','text'))
 return body

def reward(args,event):
 body={'redemptionId':args['redemptionId'],'id':args['redemptionId'],'status':event.get('status',args.get('rewardStatus')),'userInput':args.get('userInput',''),'user_input':args.get('userInput','')}
 body['reward']={target:args[key] for target,key in {'id':'rewardId','title':'rewardTitle','prompt':'rewardPrompt','cost':'rewardCost','requiresUserInput':'requiresUserInput','skipsQueue':'skipsQueue','maxPerStream':'maxPerStream','maxPerUserPerStream':'maxPerUserPerStream','globalCooldown':'globalCooldown'}.items() if key in args}
 for key in ('counter','userCounter'):
  if key in args:body[key]=args[key]
 for key in ('user_id','user_login','user_name'):
  if key in event:body[key]=event[key]
 if 'redeemed_at' in event:body.update(redeemedAt=event['redeemed_at'],redeemed_at=event['redeemed_at'])
 return body

def vote(kind,args,event):
 poll=kind<90660;prefix='poll' if poll else 'prediction'
 body=fields(event,('id','title','status','started_at','ends_at','ended_at','locks_at','locked_at','winning_outcome_id'))
 body.update(id=args[prefix+'Id'],title=args.get(prefix+'.Title',''),status=args.get(prefix+'.Status',''))
 key='choices' if poll else 'outcomes';n=args.get(prefix+'.'+key+'.count',0)
 if type(n) is not int or not 0<=n<=100:raise ValueError('vote option count')
 if key in event:
  body[key]=rows(event[key],('id','title','votes','channel_points_votes','bits_votes') if poll else ('id','title','users','channel_points','color'))
  if not poll:
   for original,projected in zip(event[key],body[key]):
    if 'top_predictors' in original:projected['top_predictors']=rows(original['top_predictors'],('user_id','user_login','user_name','channel_points_won','channel_points_used'))
 else:
  mapping={'id':'id','title':'title','votes':'totalVotes'} if poll else {'id':'id','title':'title','users':'users','channel_points':'points','color':'color'}
  body[key]=[{target:args[f'{prefix}.{"choice" if poll else "outcome"}{i}.{source}'] for target,source in mapping.items() if f'{prefix}.{"choice" if poll else "outcome"}{i}.{source}' in args} for i in range(n)]
 if poll:
  if 'channel_points_voting' in event:body['channel_points_voting']=fields(event['channel_points_voting'],('is_enabled','amount_per_vote'))
  winners=args.get('poll.winningIndices')
  if winners is not None:body['winningIndices']=winners
  winner=args.get('poll.winningIndex')
  if type(winner) is int and 0<=winner<len(body[key]):body['winningChoice']=copy.deepcopy(body[key][winner])
  if 'poll.isTie' in args:body['isTie']=args['poll.isTie']
 else:
  winner=args.get('prediction.winningIndex')
  if type(winner) is int and 0<=winner<len(body[key]):body.update(winning_outcome=copy.deepcopy(body[key][winner]),winning_outcome_id=body[key][winner].get('id'))
 return body

def train(args,event):
 if not isinstance(args.get('hypeTrainId'),str) or not args['hypeTrainId']:raise ValueError('train id')
 body={target:args[source] for target,source in {'id':'hypeTrainId','level':'level','total':'total','started_at':'startedAt','expires_at':'expiresAt','ended_at':'endedAt','cooldown_ends_at':'cooldownEndsAt','type':'trainType'}.items() if source in args and args[source] is not None and args[source]!=''}
 # Ending payloads do not always include progress/goal. Do not invent zeroes.
 body.update(fields(event,('progress','goal','is_shared_train')))
 if 'top_contributions' in event:body['top_contributions']=rows(event['top_contributions'],('user_id','user_login','user_name','type','total'))
 if event.get('last_contribution') is not None:body['last_contribution']=fields(event['last_contribution'],('user_id','user_login','user_name','type','total'))
 if 'prevLevel' in args:body['previousLevel']=args['prevLevel']
 return body

def project(engine,kind,args):
 event,stamp=observed(engine,kind,args)
 from .websocket_twitch_events import base_user,owner
 body={'broadcaster':owner(engine,args),'isTest':args.get('isTest',False)}
 if stamp:body['createdAt']=stamp
 if kind in SUBS:
  body.update(sub(kind,args,event));user=base_user(args,'roles' in args);body.update(user=user,userId=user['id'],userName=user['login'],displayName=user['name'],role=user['role'])
 elif kind in (112,90550):body.update(reward(args,event),user=base_user(args))
 elif kind in VOTES:body.update(vote(kind,args,event))
 elif kind in TRAINS:body.update(train(args,event))
 return body
