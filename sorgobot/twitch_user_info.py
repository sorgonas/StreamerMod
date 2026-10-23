"""Read-only broadcaster metadata and team membership, with isolated preview caches."""
import datetime as dt
import json,re,sqlite3,time
from contextlib import closing
from .core import ActionError,expand

ENTRIES={91600:('Add Broadcaster Information',{}),91601:('Get Team Info For Target',{'sourceType':'User','variable':'userName'})}
BROADCAST_FIELDS=('broadcastUser','broadcastUserName','broadcastUserId','broadcastUserType','broadcastIsAffiliate','broadcastIsPartner','broadcasterProfileUrl','broadcasterOfflineUrl','broadcasterCreatedAt','broadcasterDescription')
TEAM_FIELDS={'teamId':'id','teamName':'team_name','teamDisplayName':'team_display_name','teamBackgroundUrl':'background_image_url','teamBannerUrl':'banner'}

def login(value):
 if not isinstance(value,str):raise ActionError('Twitch-Login muss Text sein')
 value=value.strip().lstrip('@').casefold()
 if not re.fullmatch(r'[a-z0-9_]{1,25}',value):raise ActionError('Gültigen Twitch-Login angeben; %userName% enthält den Login')
 return value

def user_data(reply,identity,by_id=False):
 rows=reply.get('data') if isinstance(reply,dict) else None
 if not isinstance(rows,list) or len(rows)!=1 or not isinstance(rows[0],dict):raise ActionError('Twitch hat keinen eindeutigen Nutzer geliefert')
 row=rows[0]
 if not isinstance(row.get('id'),str) or not row['id'] or not isinstance(row.get('display_name'),str) or not row['display_name']:raise ActionError('Ungültige Twitch-Nutzerantwort')
 actual=login(row.get('login'))
 if (row['id'] if by_id else actual)!=identity:raise ActionError('Twitch-Nutzerantwort gehört zu einem anderen Ziel')
 return row

def teams_data(reply,identity):
 rows=reply.get('data') if isinstance(reply,dict) else None
 if not isinstance(rows,list):raise ActionError('Twitch hat keine gültige Teamliste geliefert')
 seen=set()
 for row in rows:
  if not isinstance(row,dict) or row.get('broadcaster_id')!=identity:raise ActionError('Teamantwort gehört zu einem anderen Zielnutzer')
  for key in ('id','team_name','team_display_name'):
   if not isinstance(row.get(key),str) or not row[key]:raise ActionError('Unvollständige Twitch-Teamantwort')
  for key in ('background_image_url','banner'):
   if row.get(key) is not None and not isinstance(row[key],str):raise ActionError('Ungültige Team-Bildadresse')
  if row['id'] in seen:raise ActionError('Doppelte Team-ID in Twitch-Antwort')
  seen.add(row['id'])
 return rows

class UserInfo:
 def __init__(self,io):self.io=io
 def account(self):
  cfg=self.io.config
  if not all(isinstance(cfg.get(k),str) and cfg[k] for k in ('broadcaster_id','twitch_client_id')):raise ActionError('Broadcaster-Konto unter Platforms → Twitch → Accounts einrichten')
  return cfg['broadcaster_id'],cfg['twitch_client_id']
 def session(self):return (*self.account(),self.io.config.get('twitch_token'))
 def check_session(self,before):
  if self.session()!=before:raise ActionError('Twitch-Konto während der Abfrage gewechselt; Antwort verworfen')
 def db(self):
  path=self.io.root/'state/twitch-user-info.sqlite3';path.parent.mkdir(parents=True,exist_ok=True)
  db=sqlite3.connect(path,timeout=10);db.execute('CREATE TABLE IF NOT EXISTS info_cache(account TEXT,kind TEXT,target TEXT,body TEXT,checked REAL,PRIMARY KEY(account,kind,target))');path.chmod(0o600);return db
 def cached(self,kind,target):
  # A missing cache is not an empty Twitch result and does not create a DB.
  key='|'.join(self.account())
  if not (self.io.root/'state/twitch-user-info.sqlite3').exists():raise ActionError('Kein gespeicherter Nutzerstand; Sub-Action zuerst im Live-Modus ausführen')
  path=(self.io.root/'state/twitch-user-info.sqlite3').resolve()
  with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as db:row=db.execute('SELECT body,checked FROM info_cache WHERE account=? AND kind=? AND target=?',(key,kind,target)).fetchone()
  if row is None:raise ActionError('Kein gespeicherter Stand für dieses Konto und diesen Zielnutzer')
  return json.loads(row[0]),row[1]
 def save(self,kind,target,body):
  checked=time.time()
  with closing(self.db()) as db:
   with db:db.execute('INSERT OR REPLACE INTO info_cache VALUES(?,?,?,?,?)',('|'.join(self.account()),kind,target,json.dumps(body),checked))
  return checked
 async def read(self,kind,identity,by_id=False):
  before=self.session();target=('id:' if by_id else 'login:')+identity
  if self.io.dry_run:
   body,checked=self.cached(kind,target)
  else:
   if not before[-1]:raise ActionError('Broadcaster-Konto unter Accounts anmelden')
   reply=await self.io.twitch('GET','users',params={('id' if by_id else 'login'):identity});self.check_session(before)
   user=user_data(reply,identity,by_id)
   # Store only requested public fields; no email or authorization data.
   user={key:user.get(key) for key in ('id','login','display_name','broadcaster_type','profile_image_url','offline_image_url','created_at','description')}
   body={'user':user}
   if kind=='teams':
    reply=await self.io.twitch('GET','teams/channel',params={'broadcaster_id':user['id']});self.check_session(before)
    body['teams']=teams_data(reply,user['id'])
   validate_body(kind,body,identity,by_id);checked=self.save(kind,target,body)
  validate_body(kind,body,identity,by_id)
  return body,checked

def validate_body(kind,body,identity,by_id):
 if not isinstance(body,dict):raise ActionError('Ungültiger gespeicherter Nutzerstand')
 user=user_data({'data':[body.get('user')]},identity,by_id)
 if kind=='broadcast':
  if user.get('broadcaster_type') not in ('','affiliate','partner'):raise ActionError('Unbekannter Broadcaster-Typ')
  for field in ('profile_image_url','offline_image_url','created_at','description'):
   if not isinstance(user.get(field),str):raise ActionError('Unvollständige Broadcaster-Information')
  try:
   created=dt.datetime.fromisoformat(user['created_at'].replace('Z','+00:00'))
   if created.tzinfo is None:raise ValueError()
  except ValueError:raise ActionError('Ungültiges Twitch-Konto-Erstellungsdatum') from None
 elif kind=='teams':teams_data({'data':body.get('teams')},user['id'])
 else:raise ActionError('Unbekannte Nutzerabfrage')

async def operation(io,node,args):
 kind=node['type'];args.pop('twitchUserInfoCheckedAt',None);args['twitchUserInfoFromCache']=False
 if kind==91600:
  for field in BROADCAST_FIELDS:args.pop(field,None)
  identity=UserInfo(io).account()[0];by_id=True;mode='broadcast'
 elif kind==91601:
  for field in list(args):
   if field in ('_jsonTeamData','teamCount') or any(re.fullmatch(re.escape(prefix)+r'\d+',field) for prefix in TEAM_FIELDS):args.pop(field,None)
  source=expand(node.get('sourceType','User'),args);by_id=source=='Broadcaster';mode='teams'
  if by_id:identity=UserInfo(io).account()[0]
  else:
   if source=='User':value=expand(node['userLogin'],args) if 'userLogin' in node else args.get('userName',args.get('userLogin',''))
   elif source=='From Input':value=args.get('input0','')
   elif source=='Variable':
    variable=expand(node.get('variable','userName'),args)
    if not isinstance(variable,str) or not variable:raise ActionError('Variablenname für Zielnutzer fehlt')
    value=args.get(variable,'')
   else:raise ActionError('Ungültiger Source Type')
   identity=login(value)
 else:raise ActionError('Unbekannte Twitch-Nutzer-Unteraktion')
 body,checked=await UserInfo(io).read(mode,identity,by_id);user=body['user'];values={}
 if mode=='broadcast':
  values=dict(broadcastUser=user['display_name'],broadcastUserName=user['login'],broadcastUserId=user['id'],broadcastUserType='twitch',broadcastIsAffiliate=user['broadcaster_type']=='affiliate',broadcastIsPartner=user['broadcaster_type']=='partner',broadcasterProfileUrl=user['profile_image_url'],broadcasterOfflineUrl=user['offline_image_url'],broadcasterCreatedAt=user['created_at'],broadcasterDescription=user['description'])
 else:
  rows=body['teams'];values.update(teamCount=len(rows),_jsonTeamData=json.dumps(rows,ensure_ascii=False))
  for index,row in enumerate(rows):
   for prefix,field in TEAM_FIELDS.items():values[prefix+str(index)]=row.get(field) or ''
 args.update(values,twitchUserInfoCheckedAt=checked,twitchUserInfoFromCache=io.dry_run)
 if io.dry_run:args['isPreview']=True
