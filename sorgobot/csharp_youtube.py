"""Original-shaped YouTube CPH API. Accounts are optional; C# strings stay literal."""
import copy,datetime as dt
from contextvars import ContextVar
BOUND_ACCOUNT=ContextVar('youtube_csharp_account',default=None)
def check_bound_account(service):
 bound=BOUND_ACCOUNT.get()
 if bound is not None and (bound[0] is not service or bound[1]!=service.auth.identity() or bound[2]!=service.bot_auth.identity()):raise ActionError('YouTube-Konto während C#-Aufruf geändert; Ergebnis prüfen')
from .core import ActionError
from .youtube_auth import YouTubeError

async def user_id(engine,service,value):
 if not isinstance(value,str) or not value.strip():raise YouTubeError('Nutzerkennung fehlt')
 from .users import store
 rows=store(engine).known('youtube');key=value.casefold()
 matches={r['userId'] for r in rows if r.get('userId') and (value==r['userId'] or key in (r['userName'].casefold(),r['displayName'].casefold()))}
 if len(matches)==1:return next(iter(matches))
 if len(matches)>1:raise YouTubeError('Nutzername ist mehrdeutig; Kanal-ID verwenden')
 # A @handle is an exact API identity; display-name search would guess a person.
 params={'part':'snippet','forHandle':value} if value.startswith('@') else {'part':'snippet','forUsername':value}
 reply=await service.request('GET','channels',params=params);items=reply.get('items',[])
 if not isinstance(items,list) or len(items)!=1 or not isinstance(items[0],dict) or not isinstance(items[0].get('id'),str):raise YouTubeError('Nutzer nicht eindeutig gefunden; Kanal-ID oder @Handle verwenden')
 return items[0]['id']

async def category(service,value):
 if not isinstance(value,str) or not value.strip():raise YouTubeError('Kategoriename fehlt')
 params={'part':'snippet','id':value} if value.isdigit() else {'part':'snippet','regionCode':'US','hl':'en_US'}
 data=await service.request('GET','videoCategories',params=params);rows=data.get('items',[])
 if not isinstance(rows,list):raise YouTubeError('Ungültige Kategorienliste')
 rows=[r for r in rows if isinstance(r,dict) and isinstance(r.get('snippet'),dict) and r['snippet'].get('assignable') is True and (r.get('id')==value or str(r['snippet'].get('title','')).casefold()==value.casefold())]
 if len(rows)!=1:raise YouTubeError('Keine eindeutige verfügbare YouTube-Kategorie')
 return rows[0]['id']

def account_model(auth):
 account=auth.account
 if not account.get('channelId') or not account.get('refresh_token'):return None
 return {'UserId':account['channelId'],'UserLogin':account['channelId'],'UserName':account.get('channelTitle','')}

async def broadcasts(service):
 current=copy.deepcopy(service.broadcast)
 if not current or service.phase not in ('connected','reconnecting'):return []
 reply=await service.request('GET','videos',params={'part':'snippet,status','id':current['id']})
 values=reply.get('items',[])
 if not isinstance(values,list):raise YouTubeError('Ungültige Videoantwort')
 row=next((r for r in values if isinstance(r,dict) and r.get('id')==current['id'] and isinstance(r.get('snippet'),dict) and r['snippet'].get('channelId')==service.auth.account.get('channelId')),None)
 if row is None:raise YouTubeError('Eigener Broadcast nicht bestätigt')
 snippet=row['snippet'];result={'Id':current['id'],'ChannelId':snippet['channelId'],'LiveChatId':current['snippet']['liveChatId'],'Status':current.get('status',{}).get('lifeCycleStatus',''),'Privacy':row.get('status',{}).get('privacyStatus',''),'Tags':copy.deepcopy(snippet.get('tags',[]))}
 for key,source in (('Title','title'),('Description','description'),('CategoryId','categoryId'),('DefaultLanguage','defaultLanguage'),('DefaultAudioLanguage','defaultAudioLanguage')):result[key]=snippet.get(source,'')
 if isinstance(snippet.get('publishedAt'),str):result['PublishedAt']=snippet['publishedAt']
 if service.monitor_started:result['MonitoredAt']=dt.datetime.fromtimestamp(service.monitor_started,dt.timezone.utc).isoformat()
 if result['CategoryId']:
  data=await service.request('GET','videoCategories',params={'part':'snippet','id':result['CategoryId']})
  items=data.get('items',[])
  match=next((r for r in items if isinstance(r,dict) and r.get('id')==result['CategoryId']),None) if isinstance(items,list) else None
  if match and isinstance(match.get('snippet'),dict):result['CategoryName']=match['snippet'].get('title','')
 return [result]

async def add_quote(engine,service,uid,text):
 from .csharp_quotes import own_transaction,quotes,MAX_ID
 from .core_operations import quote_operation
 from .core_events import emit
 from .users import store
 if not isinstance(uid,str) or not uid or not isinstance(text,str) or not text.strip():raise YouTubeError('Kanal-ID und Zitattext angeben')
 known=[r for r in store(engine).known('youtube') if r['userId']==uid]
 if known:name=known[0]['displayName']
 else:
  reply=await service.request('GET','channels',params={'part':'snippet','id':uid});rows=reply.get('items',[])
  rows=[r for r in rows if isinstance(r,dict) and r.get('id')==uid and isinstance(r.get('snippet'),dict)] if isinstance(rows,list) else []
  if not rows:return -1
  if len(rows)!=1:raise YouTubeError('Zitatautor ist nicht eindeutig')
  name=rows[0]['snippet'].get('title','')
 own_transaction(engine);args={'userId':uid,'user':name or uid,'platform':'youtube','currentGame':''}
 with engine.state.db:
  engine.state.db.execute('BEGIN IMMEDIATE');rows=quotes(engine);identity=engine.state.get('core:quoteNextId',1)
  if type(identity) is not int or not 1<=identity<=MAX_ID or any(r['quoteId']==identity for r in rows):raise YouTubeError('Nächste Zitat-ID ungültig')
  event=quote_operation(engine,{'type':90110,'text':text},args)
 if event:emit(engine,event,args)
 return args['quoteId']

async def rpc(engine,values):
 if not isinstance(values,list) or len(values)!=2 or not isinstance(values[0],str) or not isinstance(values[1],list):raise YouTubeError('Ungültiger C#-Aufruf')
 name,args=values
 counts={'SendYouTubeMessage':4,'SendYouTubeMessageToLatestMonitored':3,'AddQuoteForYouTube':2,'YouTubeGetBroadcaster':0,'YouTubeGetBot':0,'YouTubeGetLatestMonitoredBroadcast':0,'YouTubeGetMonitoredBroadcasts':0,'YouTubeSetTitle':2,'YouTubeSetDescription':2,'YouTubeSetPrivacy':2,'YouTubeSetCategory':2,'YouTubeSetMetaData':5,'YouTubeClearTags':1,'YouTubeAddTags':2,'YouTubeRemoveTags':2,'YouTubeTimeoutUserById':3,'YouTubeTimeoutUserByName':3,'YouTubeBanUserById':2,'YouTubeBanUserByName':2}
 if name not in counts or len(args)!=counts[name]:raise YouTubeError('Unbekannte C#-Methode oder falsche Argumentzahl')
 service=getattr(getattr(engine,'studio',None),'youtube',None)
 if engine.io.dry_run:
  engine.io.trace('youtube_csharp_preview',method=name)
  return [] if name=='YouTubeGetMonitoredBroadcasts' else None if name.startswith(('Send','YouTubeGet')) else -1 if name=='AddQuoteForYouTube' else False
 if service is None:raise YouTubeError('YouTube-Laufzeit fehlt')
 identity=service.auth.identity();bot_identity=service.bot_auth.identity()
 token=BOUND_ACCOUNT.set((service,identity,bot_identity))
 try:result=await operation(engine,service,name,args)
 finally:BOUND_ACCOUNT.reset(token)
 if identity!=service.auth.identity() or bot_identity!=service.bot_auth.identity():raise YouTubeError('YouTube-Konto während C#-Aufruf geändert; Ergebnis prüfen')
 return result

async def operation(engine,service,name,args):
 if name.startswith('YouTubeSet') or name in ('YouTubeClearTags','YouTubeAddTags','YouTubeRemoveTags'):
  if not args[-1]:
   from .youtube_targets import target
   args=[*args[:-1],target(service,{}, {})]
 if name in ('YouTubeGetBroadcaster','YouTubeGetBot'):return account_model(service.bot_auth if name.endswith('Bot') else service.auth)
 if name in ('YouTubeGetLatestMonitoredBroadcast','YouTubeGetMonitoredBroadcasts'):
  rows=await broadcasts(service);return rows if name.endswith('Broadcasts') else rows[0] if rows else None
 if name in ('SendYouTubeMessage','SendYouTubeMessageToLatestMonitored'):
  from .youtube import message_lines
  for line in message_lines(args[0]):await service.send(line,internal=True,use_bot=args[1],fallback=args[2],broadcast_id=args[3] if len(args)==4 else None)
  return None
 if name=='AddQuoteForYouTube':return await add_quote(engine,service,*args)
 if name.startswith(('YouTubeTimeoutUser','YouTubeBanUser')):
  uid=await user_id(engine,service,args[0]) if name.endswith('ByName') else args[0]
  timeout=name.startswith('YouTubeTimeout');await service.moderate('timeout' if timeout else 'ban',uid,args[1] if timeout else 60,broadcast_id=args[-1]);return True
 if name=='YouTubeSetMetaData':
  cid=await category(service,args[3]);await service.set_metadata(args[4] or '',title=args[0],description=args[1],privacy=args[2],category_id=cid);return True
 if name in ('YouTubeClearTags','YouTubeAddTags','YouTubeRemoveTags'):
  await service.set_metadata(args[-1] or '',tags=[] if name=='YouTubeClearTags' else args[0],tag_mode={'YouTubeClearTags':'set','YouTubeAddTags':'add','YouTubeRemoveTags':'remove'}[name]);return True
 kwargs={
  'YouTubeSetTitle':lambda:{'title':args[0]},'YouTubeSetDescription':lambda:{'description':args[0]},'YouTubeSetPrivacy':lambda:{'privacy':args[0]}}
 if name=='YouTubeSetCategory':change={'category_id':await category(service,args[0])}
 else:change=kwargs[name]()
 await service.set_metadata(args[-1] or '',**change);return True
