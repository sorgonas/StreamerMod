"""Account-scoped charity, clip URLs, follow age and a real Helix shoutout."""
import datetime as dt,re
from urllib.parse import urlsplit
from dateutil.relativedelta import relativedelta
from .core import ActionError,expand
from .twitch_user_info import UserInfo,login,user_data
from .twitch_chat_actions import Chat
ENTRIES={92000:('Charity · Get Latest Charity Campaign',{}),92001:('Clips · Get Clip Download Urls',{'clipId':'%clipId%'}),92002:('Followers · Get Follow Age Info for Target',{'sourceType':'User','variable':'userName'}),92003:('Moderation · Send Shoutout',{'userLogin':'%userName%'})}
CHARITY_FIELDS=('campaignId','charity.name','charity.description','charity.logoUrl','charity.websiteUrl','currentAmount','targetAmount','currentAmountCurrency','currentAmountDecimalPlaces','targetAmountCurrency','targetAmountDecimalPlaces')
FOLLOW_FIELDS=('isFollowing','followDate','followAgeLong','followAgeShort','followAgeDays','followAgeMinutes','followAgeSeconds','followUser','followUserName','followUserId',*('followAge.'+x for x in ('years','months','days','hours','minutes','seconds')))
def utcnow():return dt.datetime.now(dt.timezone.utc)
def rows(reply,maximum=1):
 value=reply.get('data') if isinstance(reply,dict) else None
 if not isinstance(value,list) or len(value)>maximum or any(not isinstance(row,dict) for row in value):raise ActionError('Ungültige Twitch-Abfrageantwort')
 return value

def money(value):
 if not isinstance(value,dict) or type(value.get('value')) is not int or value['value']<0 or type(value.get('decimal_places')) is not int or not 0<=value['decimal_places']<=9 or not isinstance(value.get('currency'),str) or not re.fullmatch('[A-Z]{3}',value['currency']):raise ActionError('Ungültige Charity-Geldangabe')
 return value

def charity(reply,broadcaster):
 data=rows(reply)
 if not data:return None
 row=data[0]
 if row.get('broadcaster_id')!=broadcaster:raise ActionError('Charity-Antwort gehört zu einem anderen Kanal')
 for field in ('id','charity_name','charity_description','charity_logo','charity_website'):
  if not isinstance(row.get(field),str) or field=='id' and not row[field]:raise ActionError('Unvollständige Charity-Antwort')
 if 'target_amount' not in row:raise ActionError('Charity-Zielangabe fehlt in der Antwort')
 money(row.get('current_amount'))
 if row.get('target_amount') is not None:money(row['target_amount'])
 return row

def clip_id(value):
 if not isinstance(value,str) or not re.fullmatch('[A-Za-z0-9_-]{1,200}',value):raise ActionError('Clip-ID (kein vollständiger Link) angeben')
 return value

def clip(reply,identity):
 data=rows(reply)
 if not data:return None
 row=data[0]
 if row.get('clip_id')!=identity:raise ActionError('Download-Antwort gehört zu einem anderen Clip')
 for key in ('landscape_download_url','portrait_download_url'):
  if key not in row:raise ActionError('Unvollständige Clip-Download-Antwort')
  value=row[key]
  if value is None:continue
  if not isinstance(value,str):raise ActionError('Ungültige Clip-Download-URL')
  try:parsed=urlsplit(value)
  except ValueError:raise ActionError('Ungültige Clip-Download-URL') from None
  if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password:raise ActionError('Ungültige Clip-Download-URL')
 return row

def followed(reply,identity):
 data=rows(reply)
 if not data:return None
 row=data[0]
 if row.get('user_id')!=identity:raise ActionError('Follower-Antwort gehört zu einem anderen Nutzer')
 try:
  stamp=row['followed_at'];value=dt.datetime.fromisoformat(stamp.replace('Z','+00:00'))
  if not isinstance(stamp,str) or value.tzinfo is None or value>utcnow():raise ValueError()
 except (KeyError,ValueError,AttributeError,TypeError):raise ActionError('Ungültiges Follow-Datum') from None
 return value.astimezone(dt.timezone.utc)

class Queries:
 def __init__(self,io):self.io=io;self.cache=UserInfo(io);self.auth=Chat(io)
 async def read(self,kind,target,endpoint,params,required,validator):
  before=self.cache.session()
  if self.io.dry_run:body,checked=self.cache.cached(kind,target)
  else:
   self.auth.account(required=required);body=await self.io.twitch('GET',endpoint,params=params);self.cache.check_session(before)
   validator(body);checked=self.cache.save(kind,target,body)
  return validator(body),checked
 async def follow(self,identity):
  before=self.cache.session();target='login:'+identity
  if self.io.dry_run:body,checked=self.cache.cached('follow-age',target)
  else:
   self.auth.account(required=('moderator:read:followers',))
   reply=await self.io.twitch('GET','users',params={'login':identity});self.cache.check_session(before);user=user_data(reply,identity)
   reply=await self.io.twitch('GET','channels/followers',params={'broadcaster_id':before[0],'user_id':user['id']});self.cache.check_session(before)
   followed(reply,user['id']);body={'user':{k:user[k] for k in ('id','login','display_name')},'followers':reply};checked=self.cache.save('follow-age',target,body)
  if not isinstance(body,dict):raise ActionError('Ungültiger gespeicherter Follow-Stand')
  user=user_data({'data':[body.get('user')]},identity);date=followed(body.get('followers'),user['id']);return user,date,checked
 async def shoutout(self,identity):
  if self.io.dry_run:self.io.trace('shoutout_preview',userLogin=identity);return False
  before=self.cache.session();self.auth.account(required=('moderator:manage:shoutouts',))
  user=user_data(await self.io.twitch('GET','users',params={'login':identity}),identity);self.cache.check_session(before)
  if user['id']==before[0]:raise ActionError('Shoutout an den eigenen Kanal ist nicht möglich')
  reply=await self.io.twitch('POST','chat/shoutouts',params={'from_broadcaster_id':before[0],'to_broadcaster_id':user['id'],'moderator_id':before[0]});self.cache.check_session(before)
  if not isinstance(reply,dict) or reply:raise ActionError('Twitch hat den Shoutout nicht eindeutig bestätigt')
  return True

async def operation(io,node,args):
 kind=node['type'];n={k:expand(v,args) for k,v in node.items()};service=Queries(io)
 if kind==92003:
  args['shoutoutSuccess']=False;args['shoutoutSuccess']=await service.shoutout(login(n.get('userLogin','')))
  if io.dry_run:args['isPreview']=True
  return
 args['twitchQueryFromCache']=io.dry_run;args.pop('twitchQueryCheckedAt',None)
 if kind==92000:
  for key in CHARITY_FIELDS:args.pop(key,None)
  args['campaignFound']=False;broad=service.cache.account()[0]
  row,checked=await service.read('charity','channel','charity/campaigns',{'broadcaster_id':broad},('channel:read:charity',),lambda r:charity(r,broad))
  args['campaignFound']=row is not None
  if row:
   args.update({'campaignId':row['id'],'charity.name':row['charity_name'],'charity.description':row['charity_description'],'charity.logoUrl':row['charity_logo'],'charity.websiteUrl':row['charity_website'],'currentAmount':row['current_amount']['value'],'currentAmountCurrency':row['current_amount']['currency'],'currentAmountDecimalPlaces':row['current_amount']['decimal_places'],'targetAmount':row['target_amount']['value'] if row.get('target_amount') else None,'targetAmountCurrency':row['target_amount']['currency'] if row.get('target_amount') else None,'targetAmountDecimalPlaces':row['target_amount']['decimal_places'] if row.get('target_amount') else None})
 elif kind==92001:
  for key in ('clipDownloadUrls','clipLandscapeDownloadUrl','clipPortraitDownloadUrl'):args.pop(key,None)
  args['clipDownloadFound']=False;identity=clip_id(n.get('clipId',''));broad=service.cache.account()[0]
  row,checked=await service.read('clip-download',identity,'clips/downloads',{'broadcaster_id':broad,'editor_id':broad,'clip_id':identity},('channel:manage:clips',),lambda r:clip(r,identity))
  args.update(clipDownloadFound=row is not None,clipDownloadUrls=row,clipLandscapeDownloadUrl=row['landscape_download_url'] if row else None,clipPortraitDownloadUrl=row['portrait_download_url'] if row else None)
 elif kind==92002:
  # Resolve source before clearing results; a variable may refer to the preceding query.
  source=n.get('sourceType','User')
  if source=='User':target=args.get('userName',args.get('userLogin',''))
  elif source=='From Input':target=args.get('input0','')
  elif source=='Variable':target=args.get(n.get('variable','userName'),'')
  else:raise ActionError('Source Type muss User, From Input oder Variable sein')
  identity=login(target)
  for key in FOLLOW_FIELDS:args.pop(key,None)
  user,date,checked=await service.follow(identity);args.update(isFollowing=date is not None,followUser=user['display_name'],followUserName=user['login'],followUserId=user['id'])
  if date:
   now=utcnow();age=relativedelta(now,date);seconds=int((now-date).total_seconds());parts=[age.years,age.months,age.days,age.hours,age.minutes,age.seconds];names=('years','months','days','hours','minutes','seconds')
   args.update({'followDate':date.strftime('%A, %d %B %Y'),'followAgeLong':', '.join(f"{value} {name[:-1] if value==1 else name}" for value,name in zip(parts,names)),'followAgeShort':', '.join(f'{value}{name}' for value,name in zip(parts,('y','m','d','h','m','s'))),'followAgeDays':f'{seconds//86400:,}','followAgeMinutes':f'{seconds//60:,}','followAgeSeconds':f'{seconds:,}',**{'followAge.'+name:value for name,value in zip(names,parts)}})
 else:raise ActionError('Unbekannte Twitch-Unteraktion')
 args['twitchQueryCheckedAt']=checked
 if io.dry_run:args['isPreview']=True
