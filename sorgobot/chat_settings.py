"""Persistent native chat preferences and explicit Action shortcuts."""
import copy,json,uuid
DEFAULTS={'fontSize':14,'historyLimit':100,'showEmotes':True,'quickActions':[]}
def validate(value):
 if not isinstance(value,dict):raise ValueError('Chat settings must be an object')
 out={**copy.deepcopy(DEFAULTS),**copy.deepcopy(value)}
 for key,low,high in [('fontSize',8,36),('historyLimit',20,1000)]:
  if type(out[key]) is not int or not low<=out[key]<=high:raise ValueError(key+': '+str(low)+'–'+str(high))
 if type(out['showEmotes']) is not bool:raise ValueError('showEmotes')
 if not isinstance(out['quickActions'],list) or len(out['quickActions'])>100:raise ValueError('Up to 100 Quick Actions')
 seen=set()
 for row in out['quickActions']:
  if not isinstance(row,dict) or not isinstance(row.get('id'),str) or row['id'] in seen:raise ValueError('Quick Action ID')
  seen.add(row['id'])
  if not isinstance(row.get('name'),str) or not 1<=len(row['name'].strip())<=80:raise ValueError('Quick Action name')
  if row.get('scope') not in ('global','user','message','event'):raise ValueError('Quick Action scope')
  if not isinstance(row.get('actionId'),str) or not row['actionId']:raise ValueError('Action required')
  if not isinstance(row.get('args'),dict):raise ValueError('Arguments must be a JSON object')
  if len(json.dumps(row['args'],allow_nan=False))>65536:raise ValueError('Arguments too large')
 return out
def read(store):
 try:return validate(store.read('chat.json'))
 except (FileNotFoundError,ValueError,TypeError):return copy.deepcopy(DEFAULTS)
def arguments(quick,row):
 platform=row.get('platform','twitch') if isinstance(row,dict) else 'twitch'
 if platform not in ('twitch','youtube','both') or platform=='both' and quick['scope']!='global':raise ValueError('Quick Action platform')
 args=copy.deepcopy(quick['args']);args.update(platform=platform,userType=platform,isInternal=True,quickActionScope=quick['scope'])
 if quick['scope']!='global':
  if not isinstance(row,dict) or not row.get('login'):raise ValueError('A chat user is required')
  args.update(user=row.get('user',''),userId=row.get('userId',''),userName=row['login'],userLogin=row['login'],roles=list(row.get('roles',[])))
 if quick['scope']=='message':args.update(message=row.get('message',''),rawInput=row.get('message',''),msgId=row.get('id',''))
 return args
