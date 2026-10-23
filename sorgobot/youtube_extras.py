"""Poll lifecycle, changing gifts and own broadcast snapshots; no history replay."""
import copy,json
from collections import OrderedDict
from .core import expand
from .youtube_auth import YouTubeError
STEPS={96017:('Polls · Create Poll',{'question':'','options':['Ja','Nein'],'broadcastMode':'latest','broadcastId':''}),96018:('Polls · End Poll',{'pollId':'','broadcastMode':'latest','broadcastId':''})}
EVENT_PATHS={4012:('StatisticsUpdated','Broadcast · Statistics Updated'),4013:('BroadcastUpdated','Broadcast · Broadcast Updated'),4021:('BroadcastAdded','Broadcast · Broadcast Added'),4022:('BroadcastRemoved','Broadcast · Broadcast Removed'),4027:('PollClosed','Polls · Poll Closed'),4028:('PollStarted','Polls · Poll Started'),4029:('PollUpdated','Polls · Poll Updated'),4030:('JewelsGifted','Chat · Jewels Gifted')}
def number(value):
 if type(value) is bool:raise YouTubeError('Ungültiger Ereigniszähler')
 if isinstance(value,int):n=value
 elif isinstance(value,str) and value.isdigit() and len(value)<30:n=int(value)
 else:raise YouTubeError('Ungültiger Ereigniszähler')
 if n<0:raise YouTubeError('Negativer Ereigniszähler')
 return n
class Extras:
 def __init__(self,service):
  self.service=service;self.identity=None;self.polls=OrderedDict();self.gifts=OrderedDict();self.broadcasts=None;self.statistics={}
 def guard(self):
  identity=self.service.auth.identity()
  if identity!=self.identity:self.identity=identity;self.polls.clear();self.gifts.clear();self.broadcasts=None;self.statistics.clear()
 def bound(self,cache):
  while len(cache)>10000:cache.popitem(last=False)
 async def discovery(self,rows):
  self.guard();current={r['id']:copy.deepcopy(r) for r in rows};previous=self.broadcasts;self.broadcasts=current
  if previous is None:return
  for bid,row in current.items():
   args={'broadcastId':bid,'title':row['snippet'].get('title',''),'broadcast':copy.deepcopy(row)}
   if bid not in previous:await self.service.emit(4021,args)
   elif row!=previous[bid]:await self.service.emit(4013,args)
  for bid,row in previous.items():
   if bid not in current:await self.service.emit(4022,{'broadcastId':bid,'title':row['snippet'].get('title',''),'reason':'noLongerAvailable'})
 async def stats(self,bid):
  self.guard();result=await self.service.request('GET','videos',params={'part':'snippet,statistics,liveStreamingDetails','id':bid})
  rows=result.get('items',[])
  if not isinstance(rows,list):raise YouTubeError('Ungültige Videoantwort')
  row=next((r for r in rows if isinstance(r,dict) and r.get('id')==bid and r.get('snippet',{}).get('channelId')==self.service.auth.account.get('channelId')),None)
  if row is None:return
  stats={}
  for source,fields in ((row.get('statistics',{}),('viewCount','likeCount','commentCount')),(row.get('liveStreamingDetails',{}),('concurrentViewers',))):
   if not isinstance(source,dict):raise YouTubeError('Ungültige Statistik')
   for field in fields:
    if field in source:stats[field]=number(source[field])
  if not stats:return
  previous=self.statistics.get(bid);self.statistics[bid]=stats
  if previous is not None and previous!=stats:await self.service.emit(4012,{'broadcastId':bid,'statistics':copy.deepcopy(stats)})
 async def poll(self,item):
  from .youtube_events import timestamp
  self.guard();s=self.service;snippet=item.get('snippet',{});chat=s.broadcast['snippet']['liveChatId'];mid=item.get('id')
  if snippet.get('liveChatId')!=chat or not isinstance(mid,str) or not mid:raise YouTubeError('Ungültiges Umfrageziel')
  stamp=timestamp(snippet.get('publishedAt'));detail=snippet.get('pollDetails',{});metadata=detail.get('metadata',{}) if isinstance(detail,dict) else {}
  if not isinstance(metadata,dict):raise YouTubeError('Ungültige Umfragemetadaten')
  status=str(detail.get('status',metadata.get('status',''))).lower()
  if status not in ('active','closed'):raise YouTubeError('Ungültiger Umfragestatus')
  question=metadata.get('questionText');options=metadata.get('options')
  if not isinstance(question,str) or not isinstance(options,list) or not 2<=len(options)<=4:raise YouTubeError('Ungültige Umfrage')
  values=[]
  for option in options:
   if not isinstance(option,dict) or not isinstance(option.get('optionText'),str):raise YouTubeError('Ungültige Umfrageoption')
   values.append({'optionText':option['optionText'][:500],'tally':number(option.get('tally',0))})
  key=(chat,mid);previous=self.polls.get(key);payload={'pollId':mid,'question':question[:1000],'options':values,'status':status}
  if previous and previous.get('status')=='closed':return
  if previous==payload:return
  self.polls[key]=payload;self.bound(self.polls)
  if previous is None and stamp<s.monitor_started:return
  kind=4027 if status=='closed' else 4028 if previous is None or previous.get('pending') else 4029
  await s.emit(kind,{**copy.deepcopy(payload),'broadcastId':s.broadcast['id'],'liveChatId':chat,'messageId':mid,'publishedAt':snippet['publishedAt']})
 async def gift(self,args,stamp):
  self.guard();key=(args['liveChatId'],args['messageId']);details=args['giftDetails'];previous=self.gifts.get(key)
  if previous is not None and details.get('comboCount',0)<=previous.get('comboCount',0):return
  self.gifts[key]=copy.deepcopy(details);self.bound(self.gifts)
  if previous is None and stamp<self.service.monitor_started:return
  await self.service.emit(4030,{**args,'jewelsAmount':details.get('jewelsAmount',0),'comboCount':details.get('comboCount',0),'isUpdate':previous is not None})
 async def create(self,question,options,broadcast_id=None):
  chat=await self.service.chat_target(broadcast_id);self.guard()
  if not isinstance(question,str) or not question.strip() or len(question)>100 or any(c in question for c in ('\0','\r','\n')):raise YouTubeError('Umfragefrage: 1–100 Zeichen, eine Zeile')
  if not isinstance(options,list) or not 2<=len(options)<=4 or any(not isinstance(v,str) or not v.strip() or len(v)>35 or any(c in v for c in ('\0','\r','\n')) for v in options):raise YouTubeError('Umfrage: 2–4 Antworten mit je 1–35 Zeichen')
  if len({v.strip().casefold() for v in options})!=len(options):raise YouTubeError('Umfrageantworten müssen sich unterscheiden')
  reply=await self.service.request('POST','liveChat/messages',params={'part':'snippet'},body={'snippet':{'liveChatId':chat,'type':'pollEvent','pollDetails':{'metadata':{'questionText':question,'options':[{'optionText':v} for v in options]}}}})
  mid=reply.get('id')
  if not isinstance(mid,str) or not mid:raise YouTubeError('Umfragebestätigung fehlt; Ergebnis prüfen')
  self.polls[(chat,mid)]={'pollId':mid,'status':'active','pending':True};self.bound(self.polls)
  return mid
 async def end(self,mid='',broadcast_id=None):
  chat=await self.service.chat_target(broadcast_id);self.guard()
  if not isinstance(mid,str):raise YouTubeError('Ungültige Umfrage-ID')
  active=[p for (c,key),p in self.polls.items() if c==chat and p.get('status')=='active' and not p.get('closing') and (not mid or key==mid)]
  if len(active)!=1:raise YouTubeError('Keine eindeutige aktive Umfrage dieses Livechats bekannt')
  mid=active[0]['pollId'];reply=await self.service.request('POST','liveChat/messages/transition',params={'id':mid,'status':'closed','part':'snippet'})
  if reply.get('id')!=mid:raise YouTubeError('Abschlussbestätigung fehlt; Ergebnis prüfen')
  active[0]['closing']=True
  if isinstance(reply.get('snippet'),dict):await self.poll(reply)
  return mid
async def operation(io,node,args):
 if io.dry_run:io.trace('youtube_poll_preview',operation=node['type']);args['isPreview']=True;return
 service=getattr(getattr(getattr(io,'engine',None),'studio',None),'youtube',None)
 if service is None:raise YouTubeError('YouTube-Laufzeit fehlt')
 n={k:expand(v,args) for k,v in node.items()}
 from .youtube_targets import target
 args['success']=False
 bid=target(service,n,args)
 args['youtubePollId']=await service.extras.create(n.get('question',''),n.get('options'),bid) if n['type']==96017 else await service.extras.end(n.get('pollId',''),bid)
 args['pollId']=args['youtubePollId'];args['success']=True

