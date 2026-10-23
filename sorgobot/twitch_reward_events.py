"""Persistent native counters; only an observed redemption add increments them."""
import re
from urllib.parse import quote
from .twitch_rewards import Rewards,variables
class Counters:
 def __init__(self,engine):
  self.engine=engine;self.db=engine.state.db
  self.db.executescript('''CREATE TABLE IF NOT EXISTS reward_totals(account TEXT,reward TEXT,total INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(account,reward));
CREATE TABLE IF NOT EXISTS reward_user_totals(account TEXT,reward TEXT,user TEXT,total INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(account,reward,user));
CREATE TABLE IF NOT EXISTS reward_observed(account TEXT,redemption TEXT,PRIMARY KEY(account,redemption));''')
  self.db.execute('CREATE TABLE IF NOT EXISTS cph_reward_times(account TEXT,reward TEXT,user TEXT,stamp TEXT,PRIMARY KEY(account,reward,user))')
  self.db.execute('CREATE TABLE IF NOT EXISTS cph_points_spent(account TEXT,user TEXT,total INTEGER,PRIMARY KEY(account,user))')
 def get(self,account,reward,user):
  row=self.db.execute('SELECT total FROM reward_totals WHERE account=? AND reward=?',(account,reward)).fetchone();total=row[0] if row else 0
  row=self.db.execute('SELECT total FROM reward_user_totals WHERE account=? AND reward=? AND user=?',(account,reward,user)).fetchone();return total,row[0] if row else 0
 def add(self,account,reward,user,redemption,stamp=None,cost=0):
  with self.db:
   changed=self.db.execute('INSERT OR IGNORE INTO reward_observed VALUES(?,?)',(account,redemption)).rowcount
   if not changed:return None
   self.db.execute('INSERT INTO reward_totals VALUES(?,?,1) ON CONFLICT(account,reward) DO UPDATE SET total=total+1',(account,reward))
   self.db.execute('INSERT INTO reward_user_totals VALUES(?,?,?,1) ON CONFLICT(account,reward,user) DO UPDATE SET total=total+1',(account,reward,user))
   from .csharp_twitch_counters import record
   stamp=record(self.engine,account,reward,user,stamp,cost)
  from .csharp_twitch_counters import session_add
  session_add(self.engine,account,reward,user,stamp)
  return self.get(account,reward,user)
 def reset(self,account,reward,users=False):
  with self.db:
   self.db.execute('DELETE FROM '+('reward_user_totals' if users else 'reward_totals')+' WHERE account=? AND reward=?',(account,reward))
   self.db.execute('DELETE FROM cph_reward_times WHERE account=? AND reward=? AND '+("user!=''" if users else "user=''"),(account,reward))
  values=getattr(self.engine,'cph_reward_session',{})
  for key in list(values):
   if key[:2]==(account,reward) and bool(key[2])==bool(users):values.pop(key,None)
def store(engine):
 if not hasattr(engine,'reward_counters'):engine.reward_counters=Counters(engine)
 return engine.reward_counters

def arguments(io,event):
 reward=event['reward'];raw=event.get('user_input','') or ''
 args={'redemptionId':event['id'],'rewardId':reward['id'],'rewardName':reward.get('title',''),'rewardTitle':reward.get('title',''),'rewardPrompt':reward.get('prompt',''),'rewardCost':reward.get('cost',0),'rewardStatus':event.get('status','UNFULFILLED').lower(),'rawInput':raw,'userInput':raw,'rawInputEscaped':re.escape(raw),'rawInputUrlEncoded':quote(raw,safe=''),'input0':raw.split()[0] if raw else ''}
 cached=next((r for r in Rewards(io).cache()['rewards'] if r['id']==reward['id']),None)
 args['rewardDetailsKnown']=cached is not None
 if cached:
  info=variables(cached)
  args.update(skipsQueue=info['rewardSkipRequestQueue'],requiresUserInput=cached.get('is_user_input_required',False),maxPerStream=info['rewardMaxPerStream'],maxPerUserPerStream=info['rewardMaxPerUserPerStream'],globalCooldown=info['rewardGlobalCooldown'],backgroundColor=info['rewardBackgroundColor'])
 return args
