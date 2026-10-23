"""Original clip overloads normalized by the C# bridge to named filter values."""
import asyncio,datetime as dt,math
from .core import ActionError
from .csharp_twitch import identity
from .csharp_twitch_data import dto,rows
from .twitch_chat_actions import Chat

OPERATIONS={'CreateClip','GetAllClips','GetClips','GetClipsForUser','GetClipsForUserById','GetClipsForGame'}

def stamp(value):
 try:
  parsed=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
  if parsed.tzinfo is None:raise ValueError()
  return parsed.astimezone(dt.timezone.utc)
 except (AttributeError,TypeError,ValueError):raise ActionError('Clip-Zeitraum benötigt gültige Datumswerte mit Zeitzone') from None

async def operation(io,name,args):
 if name=='CreateClip':return await create(io,*args)
 from .twitch_rewards import integer
 fields=args[0];query={};count=integer(fields['count'],0) if 'count' in fields else None
 if count==0:return []
 if name=='GetClipsForGame':query['game_id']=str(integer(fields['gameId'],1))
 elif name in ('GetClipsForUser','GetClipsForUserById'):
  if name=='GetClipsForUser' and 'userId' not in fields:
   from .twitch_user_info import login
   login=login(fields.get('username',fields.get('userName')))
   if io.dry_run:return []
   from .csharp_twitch_controls import target
   query['broadcaster_id']=await target(io,login)
  else:
   raw=fields['userId'];query['broadcaster_id']=str(integer(raw,1)) if type(raw) is int else identity(raw,'Nutzer-ID')
 else:query['broadcaster_id']=identity(io.config.get('broadcaster_id'),'Broadcaster-ID')
 if fields.get('isFeatured') is not None:query['is_featured']='true' if fields['isFeatured'] else 'false'
 start=end=None
 if 'duration' in fields:
  seconds=fields['duration']
  if type(seconds) not in (int,float) or not math.isfinite(seconds) or seconds<=0:raise ActionError('Clip-Dauerfilter muss positiv und endlich sein')
  end=dt.datetime.now(dt.timezone.utc)
  try:start=end-dt.timedelta(seconds=seconds)
  except OverflowError:raise ActionError('Clip-Zeitraum ist zu groß') from None
 elif 'start' in fields:start=stamp(fields['start']);end=stamp(fields['end'])
 if start:
  if end<=start:raise ActionError('Clip-Ende muss nach dem Anfang liegen')
  query.update(started_at=start.isoformat(),ended_at=end.isoformat())
 if io.dry_run:return []
 Chat(io).account();result=[];cursor=None;seen=set();ids=set()
 while True:
  params={**query,'first':100 if count is None else min(100,count-len(result))}
  if cursor:params['after']=cursor
  reply=await io.twitch('GET','clips',params=params)
  for row in rows(reply):
   uid=identity(row.get('id'),'Clip-ID')
   if uid in ids:continue
   if 'broadcaster_id' in query and row.get('broadcaster_id')!=query['broadcaster_id'] or 'game_id' in query and str(row.get('game_id'))!=query['game_id']:raise ActionError('Clip-Antwort gehört nicht zum angeforderten Kanal/Spiel')
   ids.add(uid);result.append(dto('ClipData',row))
   if count is not None and len(result)==count:return result
  cursor=reply.get('pagination',{}).get('cursor')
  if not cursor:return result
  if not isinstance(cursor,str) or cursor in seen:raise ActionError('Clip-Paginierung wiederholt sich; unvollständiges Ergebnis verworfen')
  seen.add(cursor)

async def create(io,title=None,duration=30):
 if type(duration) is not int or not 5<=duration<=60:raise ActionError('Clip-Dauer muss zwischen 5 und 60 Sekunden liegen')
 if title is not None and (not isinstance(title,str) or not title.strip() or len(title)>140):raise ActionError('Clip-Titel benötigt 1–140 Zeichen oder null')
 if io.dry_run:io.trace('twitch_clip_preview',title=title,duration=duration);return None
 owner=Chat(io).account(required=('clips:edit',));query={'broadcaster_id':owner,'duration':duration}
 if title is not None:query['title']=title
 reply=rows(await io.twitch('POST','clips',params=query))
 if len(reply)!=1:raise ActionError('Twitch hat die Clip-Erstellung nicht eindeutig bestätigt')
 uid=identity(reply[0].get('id'),'Clip-ID')
 # Only read retries: never issue a second creation request after uncertain state.
 for attempt in range(10):
  values=rows(await io.twitch('GET','clips',params={'id':uid}))
  if values:
   if len(values)!=1 or values[0].get('id')!=uid or values[0].get('broadcaster_id')!=owner:raise ActionError('Erstellter Clip konnte nicht passend bestätigt werden')
   return dto('ClipData',values[0])
  if attempt<9:await asyncio.sleep(.5)
 raise ActionError('Clip '+uid+' wurde angelegt, ist aber noch nicht abrufbar; vor erneuter Erstellung Status prüfen')
