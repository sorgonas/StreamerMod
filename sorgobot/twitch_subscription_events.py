"""Subscription actions use chat notices once; expiration uses dedicated EventSub."""
import math
MAP={'sub':90850,'resub':90851,'sub_gift':90031,'community_sub_gift':90032,'gift_paid_upgrade':90852,'prime_paid_upgrade':90853,'pay_it_forward':90854}
TYPES=set(MAP.values())|{90855}
def tier(value,prime=False):return 'prime' if prime else {'1000':'tier 1','2000':'tier 2','3000':'tier 3'}.get(str(value),'')
def notification(event):
 notice=event.get('notice_type');trigger=MAP.get(notice)
 if trigger is None:return None
 source=event.get('source_broadcaster_user_id')
 if source and source!=event.get('broadcaster_user_id'):return None
 data=dict(event.get(notice) or {});anonymous=bool(event.get('chatter_is_anonymous',False))
 args={**data,'userType':'twitch','platform':'twitch','userId':event.get('chatter_user_id','') or '','userName':event.get('chatter_user_login','') or '','userLogin':event.get('chatter_user_login','') or '','user':event.get('chatter_user_name','') or '','anonymous':anonymous,'broadcasterUserId':event.get('broadcaster_user_id',''),'broadcasterUserName':event.get('broadcaster_user_login',''),'broadcasterUser':event.get('broadcaster_user_name',''),'systemMessage':event.get('system_message',''),'message':(event.get('message') or {}).get('text',''),'rawInput':(event.get('message') or {}).get('text',''),'input0':'','chatMessageId':event.get('message_id',''),'tier':tier(data.get('sub_tier'),data.get('is_prime',False))}
 if anonymous:args.update(userId='',userName='',userLogin='',user='Anonymous')
 if notice in ('sub','resub'):
  duration=data.get('duration_months');args.update(isMultiMonth=duration is not None and duration>1,multiMonthDuration=duration)
  # Tenure is not supplied by this endpoint; never invent it.
  if notice=='resub':args.update(cumulative=data.get('cumulative_months'),monthStreak=data.get('streak_months'),streakShared=data.get('streak_months') is not None)
 if notice=='sub_gift':args.update(recipientUser=data.get('recipient_user_name',''),recipientUserName=data.get('recipient_user_login',''),recipientId=data.get('recipient_user_id',''),totalSubsGifted=data.get('cumulative_total'),totalSubsGiftedShared=data.get('cumulative_total') is not None,monthsGifted=data.get('duration_months'),fromGiftBomb=bool(data.get('community_gift_id')))
 if notice=='community_sub_gift':args.update(gifts=data.get('total',0),totalGifts=data.get('cumulative_total'),totalGiftsShared=data.get('cumulative_total') is not None,giftBombId=data.get('id',''))
 if notice=='prime_paid_upgrade':args.update(upgradeTier=int(data.get('sub_tier') or 0),upgradeTierString=tier(data.get('sub_tier')))
 return trigger,args

def expired(event):
 return 90855,{'userType':'twitch','platform':'twitch','userId':event.get('user_id',''),'userName':event.get('user_login',''),'userLogin':event.get('user_login',''),'user':event.get('user_name',''),'tier':tier(event.get('tier')),'isGift':event.get('is_gift',False),'broadcasterUserId':event.get('broadcaster_user_id',''),'broadcasterUserName':event.get('broadcaster_user_login',''),'broadcasterUser':event.get('broadcaster_user_name','')}

def matches(trigger_type,node,args):
 if trigger_type not in TYPES:return True
 tiers=node.get('tiers',[])
 if not isinstance(tiers,list) or (tiers and args.get('tier') not in tiers):return False
 mode=node.get('anonymous','either')
 if mode not in ('either','public','anonymous'):return False
 if mode!='either' and args.get('anonymous',False)!=(mode=='anonymous'):return False
 months=node.get('monthsGifted',[])
 if not isinstance(months,list) or (months and args.get('monthsGifted') not in months):return False
 metric='gifts' if trigger_type==90032 else 'totalSubsGifted' if trigger_type==90031 else 'cumulative'
 for bound,minimum in [('rangeMin',True),('rangeMax',False)]:
  value=node.get(bound,-1)
  if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value < -1:return False
  if value>=0:
   observed=args.get(metric)
   if not isinstance(observed,(int,float)) or (observed<value if minimum else observed>value):return False
 return True
