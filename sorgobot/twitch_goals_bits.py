"""Goals, Cheers and redemptions; one provider source per semantic event."""
import copy
from dateutil.parser import isoparse
from .core import ActionError
from .twitch_expansion_events import Events,person,put_user,string,boolean,count
from .twitch_shared_chat import base
ENTRIES={
92500:('Channel Goal · Goal Begin',{}),92501:('Channel Goal · Goal Progress',{}),92502:('Channel Goal · Goal End',{}),
92503:('Chat · Cheer',{'rangeMin':-1,'rangeMax':-1}),
92504:('Channel Power Ups · Power Up Redemption',{'powerUpType':''}),
92505:('Channel Power Ups · Custom Power Up Redemption',{'customPowerUpId':''}),
92506:('Channel Reward · Automatic Reward Redemption',{'rewardType':''}),
}
TYPES={'channel.goal.begin':'1','channel.goal.progress':'1','channel.goal.end':'1','channel.cheer':'1','channel.bits.use':'1','channel.custom_power_up_redemption.add':'1','channel.channel_points_automatic_reward_redemption.add':'2'}
GOALS={'channel.goal.begin':92500,'channel.goal.progress':92501,'channel.goal.end':92502}
POWER_TYPES=('message_effect','celebration','gigantify_an_emote')
POINT_TYPES=('send_highlighted_message','random_sub_emote_unlock','chosen_sub_emote_unlock','chosen_modified_sub_emote_unlock','single_message_bypass_sub_mode')
REWARD_TYPES=POINT_TYPES+POWER_TYPES
ALIASES={92500:'twitch/channel-goal/goal-begin',92501:'twitch/channel-goal/goal-progress',92502:'twitch/channel-goal/goal-end',92503:'twitch/chat/cheer',92504:'twitch/channel-power-ups/power-up-redemption',92505:'twitch/channel-power-ups/custom-power-up-redemption',92506:'twitch/channel-reward/automatic-reward-redemption'}
def required(kind):
 if kind in GOALS:return {'channel:read:goals'}
 if kind=='channel.channel_points_automatic_reward_redemption.add':return {'channel:read:redemptions','channel:manage:redemptions'}
 return {'bits:read'}
def subscriptions(broadcaster):
 for kind,version in TYPES.items():yield kind,version,{'broadcaster_user_id':broadcaster}
def timestamp(event,key):
 value=string(event,key)
 try:
  parsed=isoparse(value)
  if parsed.tzinfo is None:raise ValueError()
 except (ValueError,OverflowError):raise ActionError('Ungültiger Twitch-Zeitstempel: '+key) from None
 return value

def text(args,message):
 if message is None:return
 if isinstance(message,str):raw=message;stripped=raw
 elif isinstance(message,dict):
  raw=string(message,'text',True);fragments=message.get('fragments')
  if not isinstance(fragments,list) or any(not isinstance(f,dict) or not isinstance(f.get('text'),str) or f.get('type') not in ('text','emote','cheermote','mention') for f in fragments):raise ActionError('Ungültige Bits-/Reward-Nachricht')
  stripped=''.join(f['text'] for f in fragments if f['type']!='emote') if fragments else raw
 else:raise ActionError('Ungültige Bits-/Reward-Nachricht')
 args.update(message=raw,rawInput=raw,userInput=raw,messageStripped=stripped,input0='')
 for index,word in enumerate(raw.split()):args['input'+str(index)]=word

def emote(args,value,prefix):
 if value is None:return
 if not isinstance(value,dict):raise ActionError('Ungültiges Reward-Emote')
 args[prefix+'Id']=string(value,'id')
 if value.get('name') is not None:args[prefix+'Name']=string(value,'name')
 # A delivery ID is never treated as a chat message ID or emote ID.

def variables(kind,event):
 if kind not in TYPES:return []
 args=base(event)
 if kind in GOALS:
  args.update({'goal.id':string(event,'id'),'goal.type':string(event,'type'),'goal.description':string(event,'description',True),'goal.currentAmount':count(event,'current_amount'),'goal.targetAmount':count(event,'target_amount'),'goal.startedAt':timestamp(event,'started_at')})
  if kind.endswith('.end'):args.update({'goal.endedAt':timestamp(event,'ended_at'),'goal.isAchieved':boolean(event,'is_achieved')})
  return [(GOALS[kind],args)]
 if kind=='channel.cheer':
  anonymous=boolean(event,'is_anonymous')
  if anonymous:
   if any(event.get('user_'+key) is not None for key in ('id','login','name')):raise ActionError('Anonymer Cheer enthält widersprüchliche Nutzerdaten')
   args.update(userId=None,userLogin=None,userName=None,user='Anonymous')
  else:put_user(args,person(event,'user_'))
  bits=count(event,'bits')
  if bits==0:raise ActionError('Cheer ohne Bits')
  args.update(bits=bits,isAnonymous=anonymous);text(args,string(event,'message',True));return [(92503,args)]
 if kind=='channel.bits.use' and event.get('type') in ('cheer','custom_power_up'):
  return [] # Dedicated Cheer/custom-redemption subscriptions cover these, including anonymity/IDs.
 put_user(args,person(event,'user_'))
 if kind=='channel.bits.use':
  if event.get('type')!='power_up':raise ActionError('Unbekannter Bits-Ereignistyp')
  power=event.get('power_up')
  if not isinstance(power,dict) or power.get('type') not in POWER_TYPES:raise ActionError('Ungültiges Power-up')
  bits=count(event,'bits')
  if bits==0:raise ActionError('Power-up ohne Bits')
  args.update(bits=bits,powerUpType=power['type'],rewardType=power['type'],rewardCost=bits,rewardCostUnit='bits')
  text(args,event.get('message'));emote(args,power.get('emote'),'gigantifiedEmote' if power['type']=='gigantify_an_emote' else 'powerUpEmote')
  if power.get('message_effect_id') is not None:args['messageEffectId']=string(power,'message_effect_id')
  # Streamer.bot's automatic reward trigger also covers default Bits power-ups.
  return [(92504,args),(92506,copy.deepcopy(args))]
 args.update(redemptionId=string(event,'id'),redeemedAt=timestamp(event,'redeemed_at'))
 if kind=='channel.custom_power_up_redemption.add':
  reward=event.get('custom_power_up')
  if not isinstance(reward,dict):raise ActionError('Custom Power-up fehlt')
  status=string(event,'status')
  if status not in ('unknown','unfulfilled','fulfilled','canceled'):raise ActionError('Ungültiger Power-up-Status')
  args.update(customPowerUpId=string(reward,'id'),rewardId=string(reward,'id'),rewardTitle=string(reward,'title'),rewardPrompt=string(reward,'prompt',True),bits=count(reward,'bits'),status=status,userInput=string(event,'user_input',True),rewardCostUnit='bits')
  args['rewardCost']=args['bits'];text(args,args['userInput']);return [(92505,args)]
 reward=event.get('reward')
 if not isinstance(reward,dict) or reward.get('type') not in POINT_TYPES:raise ActionError('Ungültige automatische Kanalpunkte-Belohnung')
 args.update(rewardType=reward['type'],rewardCost=count(reward,'channel_points'),rewardCostUnit='channel_points')
 text(args,event.get('message'));emote(args,reward.get('emote'),'unlockedEmote');return [(92506,args)]

def ingest(io,kind,event,identity):
 if io.dry_run or not isinstance(event,dict) or event.get('broadcaster_user_id')!=io.config.get('broadcaster_id'):return []
 mapped=variables(kind,event);result=[]
 for trigger,args in mapped:
  committed=Events(io).commit(kind+':'+str(trigger),identity,trigger,args)
  if committed:result.append(committed)
 return result

def matches(kind,node,args):
 if kind not in ENTRIES:return True
 if kind==92503:
  low=node.get('rangeMin',-1);high=node.get('rangeMax',-1);value=args.get('bits')
  if any(type(v) is not int or v< -1 for v in (low,high)) or low>=0 and high>=0 and low>high:raise ActionError('Cheer-Range benötigt ganze Zahlen ab 0 oder -1 für leer')
  if type(value) is not int:return False
  return value==high if low<0 and high>=0 else (low<0 or value>=low) and (high<0 or value<=high)
 key={92504:'powerUpType',92505:'customPowerUpId',92506:'rewardType'}.get(kind)
 if key:
  selected=node.get(key,'')
  if not isinstance(selected,str):raise ActionError('Ungültiger Reward-Filter')
  return not selected or args.get(key)==selected
 return True

def example(kind,config,node=None):
 event={'broadcaster_user_id':config.get('broadcaster_id') or 'test-broadcaster','broadcaster_user_login':config.get('twitch_login') or 'testbroadcaster','broadcaster_user_name':'Test Broadcaster','user_id':'test-user','user_login':'testuser','user_name':'Test User'}
 at='2026-10-14T12:00:00Z';node=node or {}
 if kind in GOALS.values():
  source=next(k for k,v in GOALS.items() if v==kind);event.update(id='test-goal',type='subscription',description='Test goal',current_amount=100,target_amount=200,started_at=at,ended_at=at,is_achieved=True)
 elif kind==92503:
  source='channel.cheer';value=node.get('rangeMin',-1);maximum=node.get('rangeMax',-1);event.update(is_anonymous=False,bits=value if type(value) is int and value>0 else maximum if type(maximum) is int and maximum>0 else 100,message='Cheer100 Test cheer')
 elif kind==92505:
  source='channel.custom_power_up_redemption.add';event.update(id='test-redemption',redeemed_at=at,status='unfulfilled',user_input='Test custom power-up',custom_power_up={'id':node.get('customPowerUpId') or 'test-power-up','title':'Test Power-up','bits':100,'prompt':'Test prompt'})
 elif kind==92504 or node.get('rewardType') in POWER_TYPES:
  source='channel.bits.use';power_type=node.get('powerUpType') or node.get('rewardType') or 'gigantify_an_emote';event.update(type='power_up',bits=100,message={'text':'Test emote','fragments':[]},power_up={'type':power_type,'emote':{'id':'test-emote','name':'TestEmote'}})
 else:
  source='channel.channel_points_automatic_reward_redemption.add';event.update(id='test-redemption',redeemed_at=at,reward={'type':node.get('rewardType') or 'send_highlighted_message','channel_points':100,'emote':None},message={'text':'Test reward','fragments':[]})
 return next(args for trigger,args in variables(source,event) if trigger==kind)

class PowerUpList:
 """Account-bound inventory used by the trigger editor, without reward writes."""
 def __init__(self,io):
  from .twitch_user_info import UserInfo
  self.io=io;self.cache=UserInfo(io)
 def cached(self):
  return self.cache.cached('custom-power-ups',self.cache.account()[0])[0]
 async def read(self):
  before=self.cache.session();owner=before[0]
  if self.io.dry_run:return self.cached()
  if 'bits:read' not in set(self.io.config.get('twitch_scopes',[])):raise ActionError('bits:read fehlt für die Custom-Power-up-Auswahl')
  reply=await self.io.twitch('GET','bits/custom_power_ups',params={'broadcaster_id':owner});self.cache.check_session(before)
  rows=reply.get('data') if isinstance(reply,dict) else None
  if not isinstance(rows,list) or len(rows)>50:raise ActionError('Ungültige Custom-Power-up-Liste')
  result=[];seen=set()
  for row in rows:
   if not isinstance(row,dict) or row.get('broadcaster_id')!=owner:raise ActionError('Custom-Power-up-Antwort gehört zu einem anderen Konto')
   identity=string(row,'id');title=string(row,'title');bits=count(row,'bits')
   if identity in seen:raise ActionError('Doppelte Custom-Power-up-ID')
   seen.add(identity);result.append({'id':identity,'title':title,'bits':bits})
  self.cache.save('custom-power-ups',owner,result);return result

def confirmed(kind,version,condition,reply):
 rows=reply.get('data') if isinstance(reply,dict) else None
 if not isinstance(rows,list) or len(rows)!=1 or not isinstance(rows[0],dict):return False
 row=rows[0];actual=row.get('condition')
 if not isinstance(actual,dict):return False
 actual=dict(actual)
 # Twitch canonicalizes an omitted optional reward filter to an empty string.
 if kind=='channel.custom_power_up_redemption.add' and actual.get('reward_id')=='' and 'reward_id' not in condition:actual.pop('reward_id')
 return row.get('type')==kind and row.get('version')==version and row.get('status')=='enabled' and actual==condition
