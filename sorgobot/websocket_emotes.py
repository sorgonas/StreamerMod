"""Public Twitch emote catalogue; provider data comes from the shared runtime."""
import asyncio,copy,re,time
from urllib.parse import quote,urlsplit
from .core import ActionError
from .websocket_twitch import identity

PROVIDERS={'bttv':('bttvEmotes','BTTV'),'ffz':('ffzEmotes','FFZ'),'7tv':('sevenTvEmotes','7TV')}

def image_url(value,host):
 if isinstance(value,str) and value.startswith('//'):value='https:'+value
 parsed=urlsplit(value if isinstance(value,str) else '')
 if parsed.scheme!='https' or parsed.hostname!=host or parsed.username or parsed.password or parsed.port not in (None,443) or parsed.query or parsed.fragment:raise ActionError('Ungültige Emote-Bildadresse')
 return value

def provider_row(provider,raw):
 if not isinstance(raw,dict):raise ActionError('Ungültiges Anbieter-Emote')
 name=raw.get('name',raw.get('code'));identity=raw.get('id')
 if type(identity) not in (str,int):raise ActionError('Ungültige Anbieter-Emote-ID')
 uid=str(identity)
 if not isinstance(name,str) or not name or len(name)>256 or not re.fullmatch(r'[a-zA-Z0-9_-]+',uid):raise ActionError('Ungültiges Anbieter-Emote')
 host={'bttv':'cdn.betterttv.net','ffz':'cdn.frankerfacez.com','7tv':'cdn.7tv.app'}[provider]
 image=raw.get('imageUrl')
 if not image and provider=='ffz':
  urls=raw.get('urls',{});image=next((urls[k] for k in ('4','2','1') if k in urls),None)
 if not image and provider=='7tv' and isinstance(raw.get('data'),dict) and raw['data'].get('host'):
  from .twitch_polling_triggers import emotes
  image=emotes('7tv',{'emotes':[raw]})[0]['imageUrl']
 if not image:image={'bttv':'https://cdn.betterttv.net/emote/'+uid+'/3x','ffz':'https://cdn.frankerfacez.com/emote/'+uid+'/4','7tv':'https://cdn.7tv.app/emote/'+uid+'/4x.webp'}[provider]
 value={'name':name,'id':uid,'provider':provider,'imageUrl':image_url(image,host)}
 if type(raw.get('zeroWidth')) is bool:value['zeroWidth']=raw['zeroWidth']
 elif provider=='7tv' and isinstance(raw.get('data'),dict) and type(raw['data'].get('flags')) is int:value['zeroWidth']=bool(raw['data']['flags']&256)
 return value

def twitch_rows(reply,kind):
 if not isinstance(reply,dict) or not isinstance(reply.get('data'),list):raise ActionError('Ungültiger Twitch-Emote-Stand')
 result=[]
 for row in reply['data']:
  if not isinstance(row,dict) or not isinstance(row.get('id'),str) or not row['id'] or not isinstance(row.get('name'),str) or not row['name']:raise ActionError('Ungültiges Twitch-Emote')
  uid=quote(row['id'],safe='');tag=kind or 'twitch_'+str(row.get('emote_type','unknown'))
  result.append({'name':row['name'],'type':tag,'imageUrl':'https://static-cdn.jtvnw.net/emoticons/v2/'+uid+'/default/dark/3.0'})
 return result

async def catalogue(studio):
 io=studio.io
 if not studio.live or io.dry_run:raise ActionError('Emote-Abfrage benötigt die Live-Laufzeit')
 before=identity(studio)
 if not before[0] or not before[2]:raise ActionError('Twitch-Broadcaster anmelden')
 lock=getattr(studio,'websocket_emotes_lock',None)
 if lock is None:lock=studio.websocket_emotes_lock=asyncio.Lock()
 async with lock:
  before=identity(studio);cache=getattr(studio,'websocket_emotes_cache',None)
  scoped='user:read:emotes' in io.config.get('twitch_scopes',[])
  key=(before,scoped)
  if cache and cache[0]==key and time.monotonic()-cache[1]<300:users=copy.deepcopy(cache[2])
  else:
   async with asyncio.timeout(15):
    users=twitch_rows(await io.twitch('GET','chat/emotes/global'),'twitch_globals')
    if scoped:
     cursor=None;seen=set()
     for _ in range(100):
      params={'user_id':before[0],'broadcaster_id':before[0]}
      if cursor:params['after']=cursor
      reply=await io.twitch('GET','chat/emotes/user',params=params);users+=twitch_rows(reply,None)
      cursor=reply.get('pagination',{}).get('cursor')
      if not cursor:break
      if not isinstance(cursor,str) or cursor in seen:raise ActionError('Ungültige Twitch-Emote-Paginierung')
      seen.add(cursor)
     else:raise ActionError('Twitch-Emote-Katalog überschreitet die Seitengrenze')
    else:users+=twitch_rows(await io.twitch('GET','chat/emotes',params={'broadcaster_id':before[0]}),None)
   if identity(studio)!=before:raise ActionError('Twitch-Konto während Emote-Abfrage gewechselt')
   users=list({r['name']:r for r in users}.values());studio.websocket_emotes_cache=(key,time.monotonic(),copy.deepcopy(users))
  features=studio.twitch.features;features.set_emote_account((before[0],before[1]))
  missing=any(io.config.get('twitch_emotes_'+p,True) and (p,layer) not in features.emote_sources for p in PROVIDERS for layer in ('global','channel'))
  if (missing and not features.emote_load_checked) or (features.emote_load_checked and time.monotonic()-features.emote_load_checked>300):
   try:
    async with asyncio.timeout(12):await features.load_emotes()
   except TimeoutError:pass
  if identity(studio)!=before:raise ActionError('Twitch-Konto während Emote-Abfrage gewechselt')
  result={'userEmotes':users,'bttvEmotes':[],'ffzEmotes':[],'sevenTvEmotes':[]}
  status={'twitch':{'state':'ready','userSubscriptionsComplete':scoped,'coverage':'user' if scoped else 'global-and-channel'}}
  for provider,(field,label) in PROVIDERS.items():
   if not io.config.get('twitch_emotes_'+provider,True):status[provider]={'state':'disabled'};continue
   for layer in ('global','channel'):
    rows=features.emote_sources.get((provider,layer),{})
    status[provider+':'+layer]=copy.deepcopy(getattr(features,'emote_status',{}).get((provider,layer),{'state':'ready' if (provider,layer) in features.emote_sources else 'notLoaded'}))
    if layer=='channel' and features.polling.mode==(before[0],before[1]) and features.polling.status.get(provider,{}).get('state')=='unavailable':status[provider+':'+layer]['state']='unavailable'
    for row in rows.values():
     parsed=provider_row(provider,row);public={'name':parsed['name'],'type':label+('Global' if layer=='global' else 'Channel'),'imageUrl':parsed['imageUrl']}
     if 'zeroWidth' in parsed:public['zeroWidth']=parsed['zeroWidth']
     result[field].append(public)
   result[field]=list({r['name']:r for r in result[field]}.values())
  return {'emotes':result,'emoteStatus':status}
