"""Platform/ID-scoped command usage and shared monotonic cooldown identities."""
import copy,datetime as dt
from contextlib import nullcontext
from .core import ActionError

PLATFORMS=('twitch','youtube','kick')
SOURCES={'twitch_message':('Message',1),'twitch_whisper':('Whisper',2),'twitch_bot_whisper':('BotWhisper',4),'twitch_subscription':('Resub',8),'twitch_resubscription':('Resub',8),'twitch_shared_chat':('TwitchSharedChat',16),'youtube_message':('YouTubeMessage',1024),'kick_message':('KickMessage',2097152)}

def platform(value):
 if type(value) is int and 0<=value<len(PLATFORMS):return PLATFORMS[value]
 if isinstance(value,str) and value.casefold() in PLATFORMS:return value.casefold()
 raise ActionError('Ungültige Command-Plattform')

def count(value):
 if type(value) is not int or not 0<=value<=2147483647:raise ActionError('Command-Zähler benötigt einen nichtnegativen 32-Bit-Wert')
 return value

def identity(p,user_id='',login=''):
 p=platform(p)
 if not isinstance(user_id,str) or not isinstance(login,str):raise ActionError('Command-Nutzeridentität muss Text sein')
 login=login.casefold()
 if not user_id and not login:raise ActionError('Command-Nutzer-ID oder Login fehlt')
 return p,'id:'+user_id if user_id else 'login:'+login

# Original 1.0.7 has a single Resub source bit, not a separate Sub enum.
# Native JSON can distinguish first subscriptions from renewals; the C# view
# projects either subscription-message choice onto the existing Resub flag.
def source_key(args):
 p=platform(args.get('commandSource',args.get('userType',args.get('platform','twitch'))))
 kind=args.get('commandType','message')
 if p=='twitch' and kind=='whisper':return 'twitch_bot_whisper' if str(args.get('receivingAccount','')).casefold()=='bot' else 'twitch_whisper'
 if p=='twitch' and kind=='message' and args.get('fromSharedChat'):return 'twitch_shared_chat'
 return p+'_'+kind

def source_value(args):return SOURCES.get(source_key(args),('',0))[1]

def source_enabled(sources,args):
 key=source_key(args)
 if isinstance(sources,dict):
  if key=='twitch_shared_chat' and key not in sources:return bool(sources.get('twitch_message',True))
  return bool(sources.get(key,key=='twitch_message'))
 if type(sources) is int:return bool(sources & source_value(args))
 return False

class Usage:
 def __init__(self,dispatcher):
  self.dispatcher=dispatcher;self.engine=dispatcher.engine;self.session={}
  self.engine.state.db.execute('''CREATE TABLE IF NOT EXISTS command_usage (
   command_id TEXT,platform TEXT,identity TEXT,user_id TEXT,login TEXT,display_name TEXT,
   count INTEGER,last_used TEXT,source INTEGER,PRIMARY KEY(command_id,platform,identity))''')
 def rows(self,cid,persisted):
  if not persisted:return [copy.deepcopy(row) for (command,_,_),row in self.session.items() if command==cid]
  return [dict(zip(('command','platform','identity','user_id','login','display','count','last_used','source'),r)) for r in self.engine.state.db.execute('SELECT * FROM command_usage WHERE command_id=?',(cid,))]
 def record(self,command,args):
  cid=command['id'];p,key=identity(args.get('commandSource',args.get('userType',args.get('platform','twitch'))),args.get('userId',''),args.get('userName',args.get('userLogin','')))
  persisted=bool(command.get('persistUserCounter'));row=next((r for r in self.rows(cid,persisted) if r['platform']==p and r['identity']==key),None)
  total=count(self.dispatcher.command_counts.get(cid,0)+1);user_count=count((row['count'] if row else 0)+1)
  row={'command':cid,'platform':p,'identity':key,'user_id':args.get('userId',''),'login':args.get('userName',args.get('userLogin','')).casefold(),
       'display':args.get('user',''),'count':user_count,'last_used':dt.datetime.now(dt.timezone.utc).isoformat(),'source':source_value(args)}
  db=self.engine.state.db
  if db.in_transaction:raise ActionError('Command-Nutzung benötigt eine eigene Transaktion')
  with db:
   db.execute('BEGIN IMMEDIATE')
   if command.get('persistCounter'):self.engine.state.set('command_counter:'+cid,total)
   if persisted:db.execute('INSERT OR REPLACE INTO command_usage VALUES(?,?,?,?,?,?,?,?,?)',tuple(row.values()))
  self.dispatcher.command_counts[cid]=total
  if not persisted:self.session[cid,p,key]=row
  return total,user_count
 def reset(self,command,p=None,uid=None,persisted=None):
  mode=bool(command.get('persistUserCounter')) if persisted is None else persisted
  rows=[r for r in self.rows(command['id'],mode) if (p is None or r['platform']==p) and (uid is None or r['user_id']==uid)]
  if mode:
   with nullcontext() if self.engine.state.db.in_transaction else self.engine.state.db:
    for r in rows:self.engine.state.db.execute('UPDATE command_usage SET count=0 WHERE command_id=? AND platform=? AND identity=?',(r['command'],r['platform'],r['identity']))
  else:
   for r in rows:self.session[r['command'],r['platform'],r['identity']]['count']=0
  if p is None and uid is None and mode:
   # Old login-only values remain unassigned until an explicit all-user reset.
   self.engine.state.set('command_user_counters:'+command['id'],{})
   self.dispatcher.command_user_counts[command['id']]={}

 def reset_many(self,commands,p=None,uid=None,persisted=None):
  db=self.engine.state.db
  if db.in_transaction:raise ActionError('Command-Sammelreset benötigt eine eigene Transaktion')
  before=copy.deepcopy(self.session);legacy=copy.deepcopy(self.dispatcher.command_user_counts)
  try:
   with db:
    db.execute('BEGIN IMMEDIATE')
    for c in commands:self.reset(c,p,uid,persisted)
  except BaseException:
   self.session=before;self.dispatcher.command_user_counts=legacy;raise

def usage(dispatcher):
 if not hasattr(dispatcher,'command_usage'):dispatcher.command_usage=Usage(dispatcher)
 return dispatcher.command_usage

def cooldown_key(args):
 return identity(args.get('commandSource',args.get('userType',args.get('platform','twitch'))),args.get('userId',''),args.get('userName',args.get('userLogin','')))
