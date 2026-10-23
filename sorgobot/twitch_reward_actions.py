import copy
import random
from decimal import Decimal,InvalidOperation
from .core import ActionError,expand
from .twitch_rewards import Rewards,variables,integer,LIMITS

def state(value,current,positive,negative):
 if value==positive:return True
 if value==negative:return False
 if value=='toggle':return not current
 raise ActionError('Ungültiger Reward-Zustand')
def cost(current,value,operator):
 value=integer(value,1 if operator=='none' else -2**63);current=integer(current,1)
 if operator=='none':return integer(value,1)
 if operator=='add':result=current+value
 elif operator=='subtract':result=current-value
 elif operator=='multiply':result=current*value
 elif operator=='divide':
  if not value:raise ActionError('Division durch null')
  result=current//value
 else:raise ActionError('Ungültiger Kostenoperator')
 return integer(result,1)
async def operation(io,node,args):
 rewards=Rewards(io);t=node['type'];n={key:expand(value,args) for key,value in node.items()};identity=str(n.get('rewardId',''))
 if t==90516:
  configured=n.get('rewards',[])
  if not isinstance(configured,list):raise ActionError('Rewards-Konfiguration benötigt eine Liste')
  mapping={}
  from .twitch_rewards import validate
  for entry in configured:
   if not isinstance(entry,dict) or not entry.get('rewardId') or entry['rewardId'] in mapping:raise ActionError('Reward-ID fehlt oder ist doppelt')
   if set(entry)-{'rewardId','is_enabled','is_paused'}:raise ActionError('Ungültige Rewards-Konfiguration')
   payload=validate({k:v for k,v in entry.items() if k!='rewardId'})
   if not payload:raise ActionError('Reward-Zielzustand fehlt')
   mapping[entry['rewardId']]=payload
  rows=(await rewards.list())['data'];known={r['id']:r for r in rows}
  if any(identity not in known or not known[identity].get('manageable') for identity in mapping):raise ActionError('Konfiguration enthält fehlende oder fremde Rewards; keine Änderung ausgeführt')
  if n.get('disableNotConfigured'):
   for row in rows:
    if row.get('manageable') and row['id'] not in mapping:mapping[row['id']]={'is_enabled':False}
  if not io.dry_run and mapping:rewards.require(True)
  args['rewardConfigurationResults']=[]
  for identity,payload in mapping.items():
   await rewards.update(identity,payload);args['rewardConfigurationResults'].append(identity)
  return
 if t in (90514,90515):
  if not identity:raise ActionError('Reward-ID fehlt')
  if io.dry_run:io.trace('twitch_reward_counter_preview',rewardId=identity);return
  from .twitch_reward_events import store
  store(io.engine).reset(rewards.key(),identity,t==90515);return
 if t in (90512,90513):
  group=str(n.get('group','')).strip()
  if not group:raise ActionError('Reward-Gruppe fehlt')
  rows=[r for r in (await rewards.list())['data'] if r.get('group')==group]
  if not rows:raise ActionError('Reward-Gruppe ist leer oder unbekannt')
  if any(not r.get('manageable') for r in rows):raise ActionError('Gruppe enthält Rewards einer anderen Twitch-Anwendung; keine Änderung ausgeführt')
  if not io.dry_run:rewards.require(True)
  key='is_enabled' if t==90512 else 'is_paused';positive,negative=('enabled','disabled') if t==90512 else ('paused','unpaused')
  args['rewardGroupResults']=[]
  for row in rows:
   await rewards.update(row['id'],{key:state(n['state'],bool(row.get(key)),positive,negative)});args['rewardGroupResults'].append(row['id'])
  return
 if t==90511:
  await rewards.redeem(identity,str(n.get('redemptionId','')),str(n['status']).upper());return
 row=await rewards.get(identity,t!=90500)
 if t==90500:args.update(variables(row));return
 payload={}
 if t in (90501,90502):
  key='is_enabled' if t==90501 else 'is_paused';positive,negative=('enabled','disabled') if t==90501 else ('paused','unpaused')
  payload[key]=state(n['state'],bool(row.get(key)),positive,negative)
 elif t in (90503,90504,90510):
  fields=('title',) if t==90503 else ('prompt',) if t==90504 else ('title','prompt','cost')
  original=rewards.cache()['originals'].get(identity)
  if n.get('resetToOriginal'):
   if original is None:raise ActionError('Kein gespeicherter ursprünglicher Reward vorhanden; zuerst aktualisieren')
   payload={key:copy.deepcopy(original[key]) for key in fields if key in original}
  else:
   payload={key:n[key] for key in fields}
   if 'cost' in payload:payload['cost']=cost(row['cost'],payload['cost'],n.get('operator','none'))
 elif t==90505:payload['cost']=cost(row['cost'],n['cost'],n.get('operator','none'))
 elif t==90506:payload['background_color']='#'+format(random.randrange(0x1000000),'06X') if n.get('randomColor') else n['color']
 elif t in (90507,90508,90509):
  key={90507:'max_per_stream',90508:'max_per_user_per_stream',90509:'global_cooldown_seconds'}[t]
  value=integer(n['cooldown' if t==90509 else 'redeems'],-2**63 if n.get('additive') else 0)
  if n.get('additive'):value+=variables(row)[{90507:'rewardMaxPerStream',90508:'rewardMaxPerUserPerStream',90509:'rewardGlobalCooldown'}[t]]
  value=integer(value,0);payload[LIMITS[key]]=value>0
  if value>0:payload[key]=value
 else:raise ActionError('Reward-Unteraktion unbekannt')
 await rewards.update(identity,payload)
