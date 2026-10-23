"""Confirmed EventSub reward changes; public fields only, no local Action arguments."""
from .core import ActionError
from .twitch_expansion_events import Events,string,count,person
ENTRIES={92900:('Channel Reward · Reward Created',{'rewardId':''}),92901:('Channel Reward · Reward Updated',{'rewardId':''}),92902:('Channel Reward · Reward Deleted',{'rewardId':''})}
TYPES=dict(zip(('channel.channel_points_custom_reward.add','channel.channel_points_custom_reward.update','channel.channel_points_custom_reward.remove'),ENTRIES))
ALIASES={kind:'twitch/channel-reward/'+label.split(' · ')[1].lower().replace(' ','-') for kind,(label,_) in ENTRIES.items()}
BOOLS=('is_enabled','is_paused','is_in_stock','is_user_input_required','is_max_per_stream_enabled','is_max_per_user_per_stream_enabled','is_global_cooldown_enabled','should_redemptions_skip_request_queue')
NUMBERS=('cost','max_per_stream','max_per_user_per_stream','global_cooldown_seconds')
TEXTS=('id','title','prompt','background_color')

def reward(event):
 if not isinstance(event,dict):raise ActionError('Reward-Ereignis fehlt')
 result={key:string(event,key,key!='id') for key in TEXTS if key in event}
 for key in ('id','title','prompt'):result[key]=string(event,key,key!='id')
 result['cost']=count(event,'cost')
 for key in BOOLS:
  if key in event:
   if type(event[key]) is not bool:raise ActionError('Ungültiges Reward-Feld: '+key)
   result[key]=event[key]
 for key in NUMBERS[1:]:
  if key in event:result[key]=count(event,key)
 for key in ('redemptions_redeemed_current_stream',):
  if key in event:result[key]=count(event,key,nullable=True)
 if 'cooldown_expires_at' in event:result['cooldown_expires_at']=string(event,'cooldown_expires_at',nullable=True)
 for key in ('image','default_image'):
  if key not in event:continue
  source=event[key]
  if source is None:result[key]=None;continue
  if not isinstance(source,dict):raise ActionError('Ungültiges Reward-Bild')
  result[key]={name:string(source,name) for name in ('url_1x','url_2x','url_4x') if name in source}
 return result

def variables(event):
 owner=person(event,'broadcaster_user_');r=reward(event)
 args={'platform':'twitch','userType':'twitch','broadcasterUserId':owner['Id'],'broadcasterUserName':owner['Name'],'broadcasterUser':owner[''],'reward':r}
 for key,name in [('id','rewardId'),('title','rewardTitle'),('prompt','rewardPrompt'),('cost','rewardCost'),('background_color','rewardBackgroundColor'),('is_enabled','rewardEnabled'),('is_paused','rewardPaused')]:
  if key in r:args[name]=r[key]
 args['rewardName']=args['rewardTitle'];return args

def ingest(io,kind,event,identity):
 if kind not in TYPES or io.dry_run or not isinstance(event,dict) or event.get('broadcaster_user_id')!=io.config.get('broadcaster_id'):return None
 return Events(io).commit(kind,identity,TYPES[kind],variables(event))

def example(kind,config):
 return variables({'broadcaster_user_id':config.get('broadcaster_id') or 'test-owner','broadcaster_user_login':config.get('twitch_login') or 'testowner','broadcaster_user_name':'Test Owner','id':'test-reward','title':'Test reward','prompt':'Test prompt','cost':100,'background_color':'#123456','is_enabled':True,'is_paused':False})

def project(engine,args):
 from .websocket_twitch_events import owner
 if not isinstance(args.get('reward'),dict):raise ActionError('Reward-Daten fehlen')
 r=reward(args['reward']);result={'broadcaster':owner(engine,args),'reward':r}
 for key,name in [('id','rewardId'),('title','rewardTitle'),('title','rewardName'),('prompt','rewardPrompt'),('cost','rewardCost'),('is_enabled','rewardEnabled'),('is_paused','rewardPaused'),('background_color','rewardBackgroundColor')]:
  if key in r:result[name]=r[key]
 return result
