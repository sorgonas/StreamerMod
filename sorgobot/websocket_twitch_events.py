"""Public projections of existing Twitch/Command events, independent of Action matches."""
import contextvars,copy,datetime,math,re
from urllib.parse import quote
from .core import ActionError

CHAT=contextvars.ContextVar('websocket_chat',default=None)
EVENTS={101:'Follow',120:'FirstWord',92503:'Cheer',107:'Raid',90951:'RaidSend',
 91250:'StreamOnline',91251:'StreamOffline',91252:'ViewerCountUpdate',90950:'AdRun',
 90750:'UserBanned',90751:'UserTimedOut',90752:'UserUnbanned',90753:'VipAdded',90754:'VipRemoved',90755:'ModeratorAdded',90756:'ModeratorRemoved',
 92600:'BroadcasterAuthenticated',92601:'BroadcasterChatConnected',92602:'BroadcasterChatDisconnected',92603:'BroadcasterEventSubConnected',92604:'BroadcasterEventSubDisconnected',
 92609:'BotEventSubConnected',92610:'BotEventSubDisconnected',92900:'RewardCreated',92901:'RewardUpdated',92902:'RewardDeleted',
 92607:'Whisper',92608:'BotWhisper',92702:'BetterTTVEmoteAdded',92703:'BetterTTVEmoteRemoved',92704:'SevenTVEmoteAdded',92705:'SevenTVEmoteRemoved'}
from .websocket_twitch_progress import EVENTS as PROGRESS_EVENTS
EVENTS.update(PROGRESS_EVENTS)
from .websocket_twitch_remaining import EVENTS as REMAINING_EVENTS
EVENTS.update(REMAINING_EVENTS)
TWITCH_EVENTS=['ChatMessage',*EVENTS.values(),'StreamUpdateGameOnConnect']

def base_user(args,known_roles=False):
 user={'id':args.get('userId') or None,'login':args.get('userLogin',args.get('userName')) or None,'name':args.get('user') or None,'type':'twitch'}
 roles=args.get('roles',[])
 # Values read from original 1.0.7 Twitch.Common.Enums.ViewerRole metadata.
 user['role']=next((n for role,n in [('Broadcaster',4),('Moderators',3),('VIPs',2)] if role in roles),1 if known_roles else 0)
 if known_roles:user['subscribed']='Subscribers' in roles
 return user

def owner(engine,args):
 cfg=engine.io.config
 return {'id':args.get('broadcasterUserId',cfg.get('broadcaster_id')) or None,'login':args.get('broadcasterUserName',cfg.get('twitch_login')) or None,'name':args.get('broadcasterUser',cfg.get('twitch_display_name') or cfg.get('twitch_login')) or None,'type':'twitch'}

def legacy_user(user):
 return {'userId':user['id'],'username':user['login'],'displayName':user['name'],'role':user['role'],**({'subscriber':user['subscribed']} if 'subscribed' in user else {})}

def indexed_emotes(event,args,text):
 modern=[];legacy=[];position=0
 fragments=event.get('message',{}).get('fragments',[])
 if not isinstance(fragments,list):raise ValueError('fragments')
 for part in fragments:
  word=part.get('text','');end=position+len(word)
  if part.get('type')=='emote':
   uid=part.get('emote',{}).get('id')
   if not isinstance(uid,str) or not uid:raise ValueError('emote id')
   start=len(text[:position].encode('utf-16-le'))//2;stop=start+len(word.encode('utf-16-le'))//2-1
   image='https://static-cdn.jtvnw.net/emoticons/v2/'+quote(uid,safe='')+'/default/dark/3.0'
   modern.append({'Type':'twitch','Name':word,'ImageUrl':image,'StartIndex':start,'EndIndex':stop});legacy.append({'type':'twitch','name':word,'imageUrl':image,'startIndex':start,'endIndex':stop})
  position=end
 if fragments and ''.join(p.get('text','') for p in fragments)!=text:raise ValueError('fragment text')
 third={r['name']:r for r in args.get('emotes',[]) if isinstance(r,dict) and isinstance(r.get('name'),str)}
 for match in re.finditer(r'\S+',text):
  item=third.get(match.group())
  if not item:continue
  start=len(text[:match.start()].encode('utf-16-le'))//2;stop=len(text[:match.end()].encode('utf-16-le'))//2-1
  common={'type':item.get('provider',''),'name':match.group(),'imageUrl':item.get('imageUrl'),'startIndex':start,'endIndex':stop}
  legacy.append(common);modern.append(dict(zip(('Type','Name','ImageUrl','StartIndex','EndIndex'),common.values())))
 return modern,legacy

def message(engine,args,event=None,stamp=None):
 event=event or {};text=args.get('message','')
 if not isinstance(text,str):raise ValueError('message')
 user=base_user(args,'roles' in args and not args.get('isWhisper'));modern,emotes=indexed_emotes(event,args,text)
 badges=[{'name':b['set_id'],'version':b.get('id',''),**({'info':b['info']} if isinstance(b.get('info'),str) else {})} for b in event.get('badges',[]) if isinstance(b,dict) and isinstance(b.get('set_id'),str)]
 user['badges']=badges
 if isinstance(event.get('color'),str):user['color']=event['color']
 if isinstance(event.get('message_type'),str):
  for b in event.get('badges',[]):
   if b.get('set_id')=='subscriber' and str(b.get('info','')).isdigit():user['monthsSubscribed']=int(b['info'])
 meta={'isTest':args.get('isTest') is True,'internal':args.get('isInternal') is True}
 for source,target in [('channel_points_highlighted','isHighlighted'),('action','isMe')]:
  if 'message_type' in event:meta[target]=event['message_type']==source
 if 'channel_points_custom_reward_id' in event:meta['isCustomReward']=bool(event['channel_points_custom_reward_id'])
 first=args.get('websocketFirstObserved')
 if type(first) is bool:meta['firstMessage']=first
 mid=args.get('msgId') or args.get('whisperId')
 if mid is None and 'msgId' not in args and 'eventSubMessageId' not in args:mid=args.get('messageId')
 legacy=dict(legacy_user(user),internal=meta['internal'],msgId=mid,channel=owner(engine,args)['login'],message=text,emotes=emotes,badges=badges,isTest=meta['isTest'])
 for key in ('isMe','isHighlighted','isCustomReward','firstMessage'):
  if key in meta:legacy[key]=meta[key]
 if 'color' in user:legacy['color']=user['color']
 if 'monthsSubscribed' in user:legacy['monthsSubscribed']=user['monthsSubscribed']
 reply=event.get('reply');shared=event.get('source_broadcaster_user_id')
 body={'user':user,'text':text,'messageId':mid,'meta':meta,'anonymous':args.get('isAnonymous') is True,'emotes':modern,'isReply':isinstance(reply,dict),'isTest':meta['isTest'],'broadcaster':owner(engine,args),'createdAt':stamp or datetime.datetime.now(datetime.timezone.utc).isoformat(),'message':legacy}
 if event:
  body.update(isInSharedChat=bool(shared),isFromSharedChatGuest=bool(shared and shared!=owner(engine,args)['id']),isSharedChatHost=bool(shared and shared==owner(engine,args)['id']))
 if isinstance(reply,dict):body['reply']={out:reply.get(key) for key,out in [('parent_message_id','msgId'),('parent_user_id','userId'),('parent_user_login','userLogin'),('parent_user_name','userName'),('parent_message_body','msgBody'),('thread_message_id','threadMsgId'),('thread_user_login','threadUserLogin')]}
 if shared:body['sharedChatSource']={'id':shared,'login':event.get('source_broadcaster_user_login'),'name':event.get('source_broadcaster_user_name'),'type':'twitch'}
 legacy['isReply']=body['isReply'];legacy['isAnonymous']=body['anonymous']
 return body

def command(engine,kind,args):
 user=base_user(args,'roles' in args and not args.get('isWhisper'));body={'id':args.get('commandId'),'name':args.get('commandName'),'command':args.get('command'),'message':args.get('message'), 'user':{'id':user['id'],'name':user['login'],'display':user['name'],'role':user['role'],'type':args.get('commandSource',args.get('platform','twitch'))}}
 if 'subscribed' in user:body['user']['subscribed']=user['subscribed']
 current=CHAT.get()
 if current and current[0] is engine:
  meta=current[1].get('meta',{})
  for key,target in [('firstMessage','FirstMessage'),('firstMessageTimestamp','FirstMessageTimestamp'),('returningChatter','ReturningChatter')]:
   if key in meta:body[target]=meta[key]
 if kind==401:
  for key in ('counter','userCounter'):
   if key in args and type(args[key]) is int and args[key]>=0:body[key]=args[key]
 else:
  for key in ('cooldownLeft','globalCooldownLeft','userCooldownLeft'):
   value=args.get(key)
   if type(value) in (int,float) and math.isfinite(value):body[key]=max(0,math.ceil(value))
 return body

def forward(engine,kind,args):
 studio=getattr(engine,'studio',None);hub=getattr(studio,'main_websocket',None)
 if hub is None:return
 try:
  if kind in (401,402):hub.publish('Command','Triggered' if kind==401 else 'Cooldown',command(engine,kind,args));return
  event=EVENTS.get(kind)
  if event is None or str(args.get('platform',args.get('userType','twitch'))).casefold()!='twitch':return
  cfg=engine.io.config
  if args.get('broadcasterUserId',cfg.get('broadcaster_id'))!=cfg.get('broadcaster_id'):return
  if kind in PROGRESS_EVENTS:
   from .websocket_twitch_progress import project
   hub.publish('Twitch',event,project(engine,kind,args));return
  if kind in REMAINING_EVENTS:
   from .websocket_twitch_remaining import project
   hub.publish('Twitch',event,project(engine,kind,args));return
  body={};user=base_user(args,'roles' in args)
  if event=='FirstWord':
   current=CHAT.get();body=copy.deepcopy(current[1]) if current and current[0] is engine else message(engine,args)
  elif event=='Follow':
   body={'broadcaster':owner(engine,args),'targetUser':user,'user_id':user['id'],'user_login':user['login'],'user_name':user['name']}
   if args.get('followedAt'):body.update(followedAt=args['followedAt'],followed_at=args['followedAt'])
  elif event=='Cheer':
   if type(args.get('bits')) is not int or args['bits']<=0:return
   body=message(engine,args);body.update(body['message']);body.update(bits=args['bits'],isAnonymous=args.get('isAnonymous') is True,hasBits=True)
  elif event in ('Whisper','BotWhisper'):
   body={'message':message(engine,args)['message']}
  elif event in ('Raid','RaidSend'):
   if type(args.get('viewers')) is not int or args['viewers']<0:return
   incoming=event=='Raid';target=user if incoming else {'id':args.get('raidUserId'),'login':args.get('raidUserName'),'name':args.get('raidUser'),'type':'twitch'}
   body={'viewers':args['viewers'],'raider':target if incoming else owner(engine,args)}
   for prefix,person in [('from_broadcaster_',target if incoming else owner(engine,args)),('to_broadcaster_',owner(engine,args) if incoming else target)]:
    body.update({prefix+'user_'+k:person[v] for k,v in [('id','id'),('login','login'),('name','name')]})
  elif kind in (92900,92901,92902):
   from .twitch_reward_lifecycle import project
   body=project(engine,args)
  elif event.startswith(('Broadcaster','BotEventSub')):
   body={'broadcaster':owner(engine,args),'userId':args.get('connectionUserId'),'userName':args.get('connectionUserName')}
   for key in ('connected','authenticated','connectionType','reason'):
    if key in args:body[key]=args[key]
  elif event.startswith(('BetterTTV','SevenTV')):body={k:args[v] for k,v in [('id','emoteId'),('name','emote'),('imageUrl','imageUrl')] if v in args}
  elif event in ('StreamOnline','StreamOffline'):
   body={'broadcaster':owner(engine,args)}
   for key in ('streamId','streamType','startedAt','game','gameId','tags'):
    if key in args:body[key]=args[key]
  elif event=='ViewerCountUpdate':
   if type(args.get('viewerCount')) is not int or args['viewerCount']<0:return
   body={'broadcaster':owner(engine,args),'viewerCount':args['viewerCount']}
  elif event=='AdRun':
   body={k:args[v] for k,v in [('length_seconds','adLength'),('timestamp','adStartedAt'),('is_automatic','adScheduled'),('requester_user_id','requesterUserId'),('requester_user_login','requesterUserName'),('requester_user_name','requesterUser')] if v in args}
  else:
   body={'broadcaster':owner(engine,args),'user':user}
   for key in ('reason','isPermanent','endsAt','duration','createdAt','createdById','createdByUsername','createdByDisplayName'):
    if key in args:body[key]=args[key]
  hub.publish('Twitch',event,body)
 except (ActionError,ValueError,TypeError,KeyError,OverflowError):engine.io.trace('websocket_event_error',event=EVENTS.get(kind,'Command'),error='Ungültige Ereignisdaten verworfen')

async def chat(events,event,args,stamp):
 engine=getattr(events.dispatcher,'engine',None);studio=getattr(engine,'studio',None);hub=getattr(studio,'main_websocket',None)
 if hub is None:return await events.dispatcher.chat(args)
 try:
  projected=dict(args,websocketFirstObserved=args.get('userName','').lower() not in events.dispatcher.first_users)
  body=message(engine,projected,event,stamp)
 except (ValueError,TypeError,KeyError):
  engine.io.trace('websocket_event_error',event='ChatMessage',error='Ungültige Chat-Metadaten verworfen');return await events.dispatcher.chat(args)
 token=CHAT.set((engine,body))
 try:
  hub.publish('Twitch','ChatMessage',body)
  await events.dispatcher.chat(args)
 finally:CHAT.reset(token)


def stream_initial(engine,args):
 hub=getattr(getattr(engine,'studio',None),'main_websocket',None)
 if hub is None or engine.io.dry_run or args.get('broadcasterUserId')!=engine.io.config.get('broadcaster_id'):return
 from .websocket_twitch_remaining import project
 hub.publish('Twitch','StreamUpdateGameOnConnect',project(engine,90030,args))
