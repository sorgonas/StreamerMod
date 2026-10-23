from .twitch_rewards import integer
import html
def broadcaster(event):return {'broadcasterUserId':event.get('broadcaster_user_id',''),'broadcasterUserName':event.get('broadcaster_user_login',''),'broadcasterUser':event.get('broadcaster_user_name',''),'userType':'twitch','platform':'twitch'}
def ad(event):
 seconds=integer(event.get('duration_seconds',0),0);args=broadcaster(event);args.update(adLength=seconds,adLengthMs=seconds*1000,adScheduled=event.get('is_automatic') in (True,'true'),adStartedAt=event.get('started_at',''),requesterUserId=event.get('requester_user_id',''),requesterUserName=event.get('requester_user_login',''),requesterUser=event.get('requester_user_name',''));return 90950,args

def raid(event,owner):
 if event.get('from_broadcaster_user_id')==owner:
  image=event.get('to_broadcaster_profile_image_url','');return 90951,{'userType':'twitch','platform':'twitch','raidUser':event.get('to_broadcaster_user_name',''),'raidUserName':event.get('to_broadcaster_user_login',''),'raidUserId':event.get('to_broadcaster_user_id',''),'raidUserProfileImageURL':image,'raidUserProfileImageEscaped':html.escape(image,quote=True),'viewers':event.get('viewers',0),'broadcasterUserId':owner,'broadcasterUserName':event.get('from_broadcaster_user_login',''),'broadcasterUser':event.get('from_broadcaster_user_name','')}
 if event.get('to_broadcaster_user_id')==owner:return 107,{'userType':'twitch','platform':'twitch','user':event.get('from_broadcaster_user_name',''),'userName':event.get('from_broadcaster_user_login',''),'userLogin':event.get('from_broadcaster_user_login',''),'userId':event.get('from_broadcaster_user_id',''),'viewers':event.get('viewers',0),'input0':event.get('from_broadcaster_user_login',''),'broadcasterUserId':owner,'broadcasterUserName':event.get('to_broadcaster_user_login',''),'broadcasterUser':event.get('to_broadcaster_user_name','')}
 return None

def matches(kind,node,args):
 if kind!=107:return True
 from .core import ActionError
 for field,minimum in [('rangeMin',True),('rangeMax',False)]:
  bound=node.get(field,-1)
  if bound==-1:continue
  try:
   bound=integer(bound,0);count=integer(args.get('viewers'),0)
  except ActionError:return False
  if count<bound if minimum else count>bound:return False
 return True
