"""Shared observed reward counters, timestamps and channel-point spend totals."""
import datetime as dt
from .core import ActionError
from .csharp_twitch import identity
from .twitch_rewards import Rewards,integer

OPERATIONS={'TwitchGetRewardCounter','TwitchGetRewardUserCounter','TwitchGetRewardUserCounterById','TwitchGetRewardUserCounters','TwitchResetRewardCounter','TwitchResetRewardUserCounters','TwitchResetUserRewardCounters','TwitchResetUserRewardCounter','TwitchGetChannelPointsUsedByUserId','TwitchGetBitsDonatedByUserId'}

def setup(engine):
 if engine.state.db.in_transaction:raise ActionError('Reward-C#-Zähler benötigen eine eigene Transaktion')
 from .twitch_reward_events import store
 store(engine)
 if not hasattr(engine,'cph_reward_session'):engine.cph_reward_session={}

def record(engine,account,reward,user,stamp,cost):
 """Called only inside the deduplicated reward-add transaction."""
 cost=integer(cost,0)
 if stamp is not None:
  try:
   value=dt.datetime.fromisoformat(stamp.replace('Z','+00:00'))
   if value.tzinfo is None:raise ValueError()
  except (ValueError,TypeError,AttributeError):raise ActionError('Ungültiger Einlösungszeitpunkt') from None
  stamp=value.astimezone(dt.timezone.utc).isoformat()
 for uid in ('',user):
  if stamp:engine.state.db.execute('INSERT INTO cph_reward_times VALUES(?,?,?,?) ON CONFLICT(account,reward,user) DO UPDATE SET stamp=MAX(stamp,excluded.stamp)',(account,reward,uid,stamp))
 current=engine.state.db.execute('SELECT total FROM cph_points_spent WHERE account=? AND user=?',(account,user)).fetchone();total=integer((current[0] if current else 0)+cost,0)
 engine.state.db.execute('INSERT INTO cph_points_spent VALUES(?,?,?) ON CONFLICT(account,user) DO UPDATE SET total=excluded.total',(account,user,total))
 return stamp

def session_add(engine,account,reward,user,stamp):
 values=getattr(engine,'cph_reward_session',None)
 if values is None:values=engine.cph_reward_session={}
 for uid in ('',user):
  key=(account,reward,uid);old=values.get(key,{'Count':0});values[key]={'Count':old['Count']+1,'LastRedeemed':max(filter(None,(old.get('LastRedeemed'),stamp)),default=None)}

def info(engine,user):
 db=engine.state.db
 if not user or not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='known_users'").fetchone():return {}
 values=db.execute('SELECT user,display_name FROM known_users WHERE platform=? AND user_id=?',('twitch',user)).fetchall()
 return {'UserLogin':values[0][0],'UserName':values[0][1]} if len(values)==1 else {}

def counter(engine,account,reward,user,persisted):
 if persisted:
  query='SELECT total FROM reward_user_totals WHERE account=? AND reward=? AND user=?' if user else 'SELECT total FROM reward_totals WHERE account=? AND reward=?'
  values=(account,reward,user) if user else (account,reward);row=engine.state.db.execute(query,values).fetchone();value={'Count':row[0] if row else 0}
  stamp=engine.state.db.execute('SELECT stamp FROM cph_reward_times WHERE account=? AND reward=? AND user=?',(account,reward,user)).fetchone()
  if stamp:value['LastRedeemed']=stamp[0]
 else:value=dict(engine.cph_reward_session.get((account,reward,user),{'Count':0}))
 if value['Count']>2**31-1:raise ActionError('Reward-Zähler überschreitet den Original-Int32-Typ')
 if value.get('LastRedeemed') is None:value.pop('LastRedeemed',None)
 return {'UserId':user,**info(engine,user),**value}

async def operation(io,name,args):
 from .twitch_chat_actions import Chat
 from .csharp_twitch_data import rows
 if name=='TwitchGetBitsDonatedByUserId':
  uid=identity(args[0],'Nutzer-ID')
  if io.dry_run:return 0
  Chat(io).account(required=('bits:read',));values=rows(await io.twitch('GET','bits/leaderboard',params={'period':'all','user_id':uid,'count':100}));matches=[r for r in values if r.get('user_id')==uid]
  if len(matches)>1:raise ActionError('Bits-Antwort enthält den Nutzer mehrfach')
  return integer(matches[0].get('score'),0) if matches else 0
 engine=io.engine;setup(engine);account=Rewards(io).key();db=engine.state.db
 if name=='TwitchGetChannelPointsUsedByUserId':
  row=db.execute('SELECT total FROM cph_points_spent WHERE account=? AND user=?',(account,identity(args[0],'Nutzer-ID'))).fetchone();return row[0] if row else 0
 if name=='TwitchGetRewardCounter':return counter(engine,account,identity(args[0],'Reward-ID'),'',args[1])
 if name in ('TwitchGetRewardUserCounter','TwitchGetRewardUserCounterById'):
  user,reward,persisted=args;reward=identity(reward,'Reward-ID')
  if name.endswith('ById'):user=identity(user,'Nutzer-ID')
  else:
   from .csharp_platform_globals import known
   from .twitch_user_info import login
   name_login=login(user);known_user=known(engine,'twitch',name_login,False)
   if known_user:user=known_user[0]
   elif io.dry_run:return None
   else:
    from .csharp_twitch_controls import target
    user=await target(io,name_login)
  return counter(engine,account,reward,user,persisted)
 if name=='TwitchGetRewardUserCounters':
  reward,persisted=args;identity(reward,'Reward-ID')
  users=[r[0] for r in db.execute('SELECT user FROM reward_user_totals WHERE account=? AND reward=? ORDER BY user',(account,reward))] if persisted else sorted(k[2] for k in engine.cph_reward_session if k[:2]==(account,reward) and k[2])
  return [counter(engine,account,reward,u,persisted) for u in users]
 reward=user=None;scopes=(True,False)
 if name=='TwitchResetRewardCounter':reward=identity(args[0],'Reward-ID');user=''
 elif name=='TwitchResetRewardUserCounters':reward=identity(args[0],'Reward-ID')
 elif name=='TwitchResetUserRewardCounters':user=identity(args[0],'Nutzer-ID');scopes=(args[1],)
 else:reward,user=[identity(v) for v in args]
 if io.dry_run:io.trace('twitch_reward_counter_csharp_preview',operation=name,rewardId=reward,userId=user);return None
 def matches(key):return key[0]==account and (reward is None or key[1]==reward) and (key[2]==user if user is not None else bool(key[2]))
 if True in scopes:
  clauses=['account=?'];values=[account]
  if reward is not None:clauses.append('reward=?');values.append(reward)
  if user=='':table='reward_totals'
  else:
   table='reward_user_totals'
   if user is not None:clauses.append('user=?');values.append(user)
  with db:
   db.execute('DELETE FROM '+table+' WHERE '+' AND '.join(clauses),values)
   time_clauses=[*clauses];time_values=[*values]
   if user=='':time_clauses.append('user=?');time_values.append('')
   elif user is None:time_clauses.append("user!=''")
   db.execute('DELETE FROM cph_reward_times WHERE '+' AND '.join(time_clauses),time_values)
 if False in scopes:
  for key in list(engine.cph_reward_session):
   if matches(key):engine.cph_reward_session.pop(key,None)
 return None
