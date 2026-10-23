"""On-demand public Alejo pronouns, with bounded caching and no chat polling."""
import asyncio,copy,datetime,time
from collections import OrderedDict
from .core import ActionError
from .twitch_user_info import login

BASE='https://api.pronouns.alejo.io/v1/'
FIELDS=('Subject','Object','Possessive','Pronoun','Reflexive','PastTense','CurrentTense')
# Grammatical forms of the selected primary set, never inferred from a user name.
FORMS={'hehim':('His','His','Himself','Was','Is','s'),
 'sheher':('Her','Hers','Herself','Was','Is','s'),
 'theythem':('Their','Theirs','Themself','Were','Are',''),
 'itits':('Its','Its','Itself','Was','Is','s'),
 'aeaer':('Aer','Aers','Aerself','Was','Is','s'),
 'eem':('Eir','Eirs','Emself','Was','Is','s'),
 'faefaer':('Faer','Faers','Faerself','Was','Is','s'),
 'perper':('Per','Pers','Perself','Was','Is','s'),
 'vever':('Vis','Vers','Verself','Was','Is','s'),
 'xexem':('Xyr','Xyrs','Xemself','Was','Is','s'),
 'ziehir':('Hir','Hirs','Hirself','Was','Is','s')}

def project(raw,definitions,user,stamp):
 result={**{'pronoun'+field:'' for field in FIELDS},'pronouns':'','pronounsPlain':'','pronounPluralLower':'','pronounLastCached':stamp,'userFound':False}
 if raw is not None:
  if isinstance(raw,list):
   if len(raw)!=1 or not isinstance(raw[0],dict):raise ActionError('Ungültige Pronomen-Nutzerantwort')
   raw=raw[0]
  if not isinstance(raw,dict) or not isinstance(raw.get('pronoun_id'),str) or raw.get('channel_login',raw.get('login',user)).casefold()!=user:raise ActionError('Ungültige Pronomen-Nutzerantwort')
  ids=[raw['pronoun_id']];alternate=raw.get('alt_pronoun_id')
  if alternate is not None and alternate!='':
   if not isinstance(alternate,str):raise ActionError('Ungültige alternative Pronomen')
   if alternate not in ids:ids.append(alternate)
  sets=[]
  for key in ids:
   value=definitions.get(key) if isinstance(definitions,dict) else None
   if not isinstance(value,dict) or any(not isinstance(value.get(k),str) or not value[k] or len(value[k])>100 for k in ('subject','object')):raise ActionError('Pronomen-Definition fehlt oder ist ungültig')
   sets.append(value)
  main=sets[0]
  plain=main['subject'] if main.get('singular') is True else main['subject']+'/'+main['object'] if len(sets)==1 else '/'.join(s['subject'] for s in sets)
  result.update(pronounSubject=main['subject'],pronounObject=main['object'],pronouns='('+plain+')',pronounsPlain=plain,userFound=True)
  if ids[0] in FORMS:
   forms=FORMS[ids[0]]
   result.update(dict(zip(('pronounPossessive','pronounPronoun','pronounReflexive','pronounPastTense','pronounCurrentTense','pronounPluralLower'),forms)))
 for field in FIELDS:result['pronoun'+field+'Lower']=result['pronoun'+field].lower()
 return {'userLogin':user,'pronoun':result}

async def request(studio,data):
 if data.get('platform','twitch')!='twitch':raise ActionError('Pronomen sind derzeit für Twitch angebunden')
 user=login(data.get('userLogin'))
 if not studio.live or studio.io.dry_run:raise ActionError('Pronomen-Abfrage benötigt die Live-Laufzeit')
 if not hasattr(studio,'websocket_pronouns_cache'):
  studio.websocket_pronouns_cache=OrderedDict();studio.websocket_pronouns_lock=asyncio.Lock();studio.websocket_pronouns_failures=OrderedDict()
 async with studio.websocket_pronouns_lock:
  cache=studio.websocket_pronouns_cache;failures=studio.websocket_pronouns_failures;now=time.monotonic()
  if user in cache and now-cache[user][0]<300:
   cache.move_to_end(user);return copy.deepcopy(cache[user][1])
  if user in failures and now-failures[user]<30:raise ActionError('Pronomen-Dienst vorübergehend nicht verfügbar; später erneut versuchen')
  try:
   async with asyncio.timeout(8):
    try:raw=await studio.io.http('GET',BASE+'users/'+user)
    except ActionError as exc:
     if str(exc).startswith('HTTP 404:'):raw=None
     else:raise
    if raw==[]:raw=None # Legacy no-registration response; transport errors never mean absent.
    definitions={}
    if raw is not None:
     saved=getattr(studio,'websocket_pronouns_definitions',None)
     if saved and time.monotonic()-saved[0]<3600:definitions=saved[1]
     else:
      definitions=await studio.io.http('GET',BASE+'pronouns')
      if not isinstance(definitions,dict) or not definitions or len(definitions)>1000:raise ActionError('Ungültige Pronomen-Definitionen')
      studio.websocket_pronouns_definitions=(time.monotonic(),definitions)
    result=project(raw,definitions,user,datetime.datetime.now(datetime.timezone.utc).isoformat())
  except (ActionError,TimeoutError,ValueError,TypeError,AttributeError):
   failures[user]=time.monotonic();failures.move_to_end(user)
   while len(failures)>512:failures.popitem(last=False)
   raise ActionError('Pronomen-Dienst nicht verfügbar oder Antwort ungültig; keine Pronomen übernommen') from None
  failures.pop(user,None);cache[user]=(time.monotonic(),copy.deepcopy(result));cache.move_to_end(user)
  while len(cache)>512:cache.popitem(last=False)
  return result
