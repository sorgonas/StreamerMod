"""Documented C# Commands API using the native dispatcher and usage records."""
import asyncio,copy,uuid
from .core import ActionError
from .catalog import ConfigStore,_CONFIG_LOCK
from .command_state import platform,usage,SOURCES,count,identity

UNKNOWN_DATE='0001-01-01T00:00:00'

def dispatcher(engine):
 result=getattr(engine,'dispatcher',None)
 if result is None:raise ActionError('Command-Laufzeit ist nicht verfügbar')
 return result

def command(engine,cid):
 def canonical(value):
  try:return str(uuid.UUID(value))
  except (ValueError,AttributeError,TypeError):return value
 matches=[c for c in dispatcher(engine).commands if canonical(c['id'])==canonical(cid)]
 if len(matches)!=1:raise ActionError('Command-ID fehlt oder ist nicht eindeutig')
 return matches[0]

def update(engine,target,fields):
 if not engine.io.dry_run:
  with _CONFIG_LOCK:
   store=ConfigStore(engine.io.root);doc=store.read('commands.json');saved=[c for c in doc['commands'] if c['id']==target['id']]
   if len(saved)!=1:raise ActionError('Gespeicherter Command fehlt oder ist nicht eindeutig')
   saved[0].update(fields);store.save('commands.json',doc)
 target.update(fields)

def commands_list(engine):
 result=[]
 for c in dispatcher(engine).commands:
  try:guid=str(uuid.UUID(c['id']))
  except (ValueError,AttributeError,TypeError):raise ActionError('GetCommands benötigt gültige Command-GUIDs; Altformat zuerst migrieren') from None
  mode=c.get('mode',0)
  if mode not in (0,1):raise ActionError('Ungültiger Command-Modus')
  raw=c.get('command','');sources=c.get('sources',{})
  if isinstance(sources,dict):
   if any(enabled for key,enabled in sources.items() if key not in SOURCES):raise ActionError('Aktive Command-Source ohne bestätigte Originalzuordnung')
   selected=list(dict.fromkeys(label for key,(label,_) in SOURCES.items() if sources.get(key,key=='twitch_message')))
  elif type(sources) is int:
   supported=sum({bit for _,bit in SOURCES.values()})
   if sources<0 or sources&~supported:raise ActionError('Unbekannte Command-Source-Bits')
   selected=list(dict.fromkeys(label for label,bit in SOURCES.values() if sources&bit))
  else:raise ActionError('Ungültige Command-Sources')
  result.append({'Id':guid,'Name':c.get('name',''),'Enabled':c.get('enabled',True),'Group':c.get('group',''),'Mode':mode,
   'Commands':[s.strip() for s in raw.splitlines() if s.strip()] if mode==0 else [],'RegexCommand':raw if mode==1 else '',
   'CaseSensitive':c.get('caseSensitive',False),'Sources':selected})
 return result

def known(engine,p,uid=None,login=None):
 db=engine.state.db
 if not db.execute("SELECT 1 FROM sqlite_master WHERE name='known_users'").fetchone():return None
 rows=db.execute('SELECT user_id,user,display_name FROM known_users WHERE platform=? AND '+('user_id=?' if uid is not None else 'user=?'),(p,uid if uid is not None else login)).fetchall()
 return {'id':rows[0][0],'login':rows[0][1],'display':rows[0][2]} if len(rows)==1 else None

def get_counter(engine,user,p,cid,by_id):
 c=command(engine,cid);cid=c['id'];d=dispatcher(engine);p=platform(p)
 if not isinstance(user,str) or not user:raise ActionError('Command-Nutzer fehlt')
 if not by_id:user=user.casefold()
 rows=[r for r in usage(d).rows(cid,bool(c.get('persistUserCounter'))) if r['platform']==p]
 info=known(engine,p,uid=user) if by_id else known(engine,p,login=user)
 if by_id:matches=[r for r in rows if r['user_id']==user]
 elif info and info['id']:matches=[r for r in rows if r['user_id']==info['id']]
 else:matches=[r for r in rows if r['login']==user]
 if len(matches)>1:raise ActionError('Command-Nutzerzuordnung ist mehrdeutig; ById verwenden')
 row=matches[0] if matches else None
 if row is None and info is None:return None
 login=row['login'] if row else info['login'];legacy=d.command_user_counts.get(cid,{}).get(login,0)
 return {'UserId':row['user_id'] if row else info['id'],'UserLogin':login,'UserName':row['display'] if row else info['display'],'Platform':p,
  'Count':count(row['count']) if row else 0,'Source':row['source'] if row else 0,'LastUsed':row['last_used'] if row else UNKNOWN_DATE,
  'LastUsedKnown':bool(row),'LegacyUnassignedCount':count(legacy),'UserInfoAvailable':bool((row['user_id'] and row['login'] and row['display']) if row else (info['id'] and info['login'] and info['display']))}

def seconds(value,signed=False):
 if type(value) is not int or not (-2147483648 if signed else 0)<=value<=2147483647:raise ActionError('Cooldown-Zeit liegt außerhalb des unterstützten 32-Bit-Bereichs' if signed else 'Cooldown-Dauer benötigt nichtnegative Sekunden im 32-Bit-Bereich')
 return value

def cooldown(engine,op,cid,user=None,p=None,amount=None):
 c=command(engine,cid);cid=c['id'];d=dispatcher(engine);now=asyncio.get_running_loop().time()
 if amount is not None:amount=seconds(amount,signed=True)
 if user is not None:
  if not isinstance(user,str) or not user:raise ActionError('Command-Nutzer-ID fehlt')
  targets=[(cid,identity(platform(p),user))]
 elif op.startswith('all_'):targets=[key for key in d.cooldowns if key[0]==cid and key[1]!='*' and (op.endswith('remove') or d.cooldowns[key]>now)]
 else:targets=[(cid,'*')]
 for key in targets:
  if op.endswith('remove'):d.cooldowns.pop(key,None)
  elif op.endswith('reset'):d.cooldowns[key]=now+seconds(c.get('userCooldown' if key[1]!='*' else 'globalCooldown',0))
  elif op.endswith('add'):
   expires=d.cooldowns.get(key,0)
   if expires>now:d.cooldowns[key]=expires+amount
  else:raise ActionError('Unbekannte Cooldown-Operation')
 return True

async def rpc(engine,method,values):
 if method=='commands_list':return commands_list(engine)
 if method=='command_enabled':update(engine,command(engine,values[0]),{'enabled':values[1]});return True
 if method=='command_duration':
  cid,field,value=values
  if field not in ('globalCooldown','userCooldown'):raise ActionError('Unbekannte Cooldown-Dauer')
  update(engine,command(engine,cid),{field:seconds(value)});return True
 if method=='command_cooldown':return cooldown(engine,*values)
 if method=='command_counter':
  c=command(engine,values[0]);return count(dispatcher(engine).command_counts.get(c['id'],0))
 if method=='command_user_counter':return get_counter(engine,*values)
 if method=='command_reset_counter':
  cid=values[0];c=command(engine,cid);cid=c['id'];d=dispatcher(engine)
  if c.get('persistCounter'):engine.state.set('command_counter:'+cid,0)
  d.command_counts[cid]=0;return True
 if method=='command_reset_users':
  cid,user,p,mode=values;d=dispatcher(engine)
  if user is not None and (not isinstance(user,str) or not user):raise ActionError('Command-Nutzer-ID fehlt')
  if mode is not None and type(mode) is not bool:raise ActionError('Persistenzmodus muss bool sein')
  if cid is None:
   if not isinstance(user,str) or not user:raise ActionError('Command-Nutzer-ID fehlt')
   p=platform(p)
   usage(d).reset_many(d.commands,p,user,mode)
  else:usage(d).reset_many([command(engine,cid)],platform(p) if p is not None else None,user,mode)
  return True
 raise ActionError('Unbekannte C#-Command-Methode')
