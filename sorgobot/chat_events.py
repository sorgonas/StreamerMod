"""Account-bound Quick Action contexts from validated public event projections."""
import copy,uuid
from .core import ActionError

def owner(studio,platform='Twitch'):
 if platform=='YouTube':
  auth=getattr(getattr(studio,'youtube',None),'auth',None);return auth.identity() if auth else ('','')
 return (studio.io.config.get('broadcaster_id',''),studio.io.config.get('twitch_client_id',''))
def person(data):
 for field in ('user','targetUser','raider','message'):
  user=data.get(field)
  if isinstance(user,dict) and any(user.get(k) for k in ('id','userId','login','username','name','displayName')):
   return {'id':user.get('id') or user.get('userId') or '', 'login':user.get('login') or user.get('username') or '', 'name':user.get('name') or user.get('displayName') or ''}
 return {'id':data.get('user_id') or data.get('userId') or '', 'login':data.get('user_login') or data.get('userName') or '', 'name':data.get('user_name') or (data.get('user') if isinstance(data.get('user'),str) else '') or data.get('userName') or ''}
def capture(studio,packet):
 event=packet['event'];data=packet['data']
 if event['source'] not in ('Twitch','YouTube') or event['type'] in ('ChatMessage','Message') or not isinstance(data,dict):return
 rows=getattr(studio,'chat_event_contexts',None)
 if rows is None:rows=studio.chat_event_contexts={}
 identity=str(uuid.uuid4());user=person(data)
 row={'id':identity,'time':packet['timeStamp'],'platform':event['source'],'type':event['type'],'user':str(user.get('name') or user.get('displayName') or user.get('login') or '')}
 rows[identity]={'owner':owner(studio,event['source']),'row':row,'data':copy.deepcopy(data)}
 while len(rows)>300:rows.pop(next(iter(rows)))
def snapshot(studio):
 return [copy.deepcopy(item['row']) for item in getattr(studio,'chat_event_contexts',{}).values() if item['owner']==owner(studio,item['row']['platform'])]
def arguments(studio,quick,row):
 identity=row.get('id') if isinstance(row,dict) else None
 item=getattr(studio,'chat_event_contexts',{}).get(identity)
 if item is None or item['owner']!=owner(studio,item['row']['platform']):raise ActionError('Ereignis ist nicht mehr verfügbar')
 args=copy.deepcopy(quick['args']);args.update(copy.deepcopy(item['data']))
 user=person(item['data'])
 if isinstance(user,dict):args.update(user=user.get('name') or '',userName=user.get('login') or '',userLogin=user.get('login') or '',userId=user.get('id') or '')
 platform=item['row']['platform'].lower()
 args.update(platform=platform,userType=platform,isInternal=True,quickActionScope='event',eventType=item['row']['type'],eventId=identity,eventData=copy.deepcopy(item['data']))
 return args

def execute(studio,store,data):
 from .chat_settings import read,arguments as chat_arguments
 from .server_contracts import execute as run
 quick=next((q for q in read(store)['quickActions'] if q['id']==data.get('quickId')),None)
 if quick is None:raise ActionError('Quick Action nicht gefunden')
 values=arguments(studio,quick,data.get('row')) if quick['scope']=='event' else chat_arguments(quick,data.get('row'))
 run(studio,{'action':{'id':quick['actionId']},'args':values})
 return True
