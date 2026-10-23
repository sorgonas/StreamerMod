"""Validated broadcaster ad and raid services. Mutations are preview-safe."""
import copy
from .catalog import ConfigStore
from .core import ActionError,expand
from .twitch_rewards import scopes,integer
DURATIONS=(30,60,90,120,150,180)
SCOPES={'schedule':'channel:read:ads','commercial':'channel:edit:commercial','snooze':'channel:manage:ads','raid_start':'channel:manage:raids','raid_cancel':'channel:manage:raids'}
def duration(value):
 seconds=integer(value,1)
 if seconds not in DURATIONS:raise ActionError('Werbung: 30, 60, 90, 120, 150 oder 180 Sekunden wählen')
 return seconds

def schedule_variables(row):
 from .twitch_polling_triggers import ad_time
 seconds=integer(row.get('preroll_free_time',0),0)
 return {'prerollFree':seconds>0,'prerollFreeSeconds':seconds,'snoozeCount':integer(row.get('snooze_count',0),0),'nextAdAt':ad_time(row.get('next_ad_at')),'lastAdAt':ad_time(row.get('last_ad_at')),'adLength':integer(row.get('duration',0),0),'snoozeRefreshAt':ad_time(row.get('snooze_refresh_at'))}
class BroadcastTools:
 def __init__(self,io):self.io=io;self.store=ConfigStore(io.root)
 def require(self,op):
  cfg=self.io.config
  if not all(cfg.get(k) for k in ('twitch_token','broadcaster_id','twitch_client_id')):raise ActionError('Broadcaster-Konto zuerst anmelden')
  if SCOPES[op] not in scopes(cfg):raise ActionError(SCOPES[op]+' fehlt. Die gemeinsame Broadcaster-Freigabe unter Accounts ergänzt die Rechte.')
 def document(self):
  try:return self.store.read('twitch-ads.json')
  except FileNotFoundError:return {'accounts':{}}
 def key(self):return self.io.config.get('broadcaster_id','')+'|'+self.io.config.get('twitch_client_id','')
 def cached(self):return copy.deepcopy(self.document().get('accounts',{}).get(self.key(),{}))
 def save(self,result):
  from datetime import datetime,timezone
  doc=self.document();doc.setdefault('accounts',{})[self.key()]={**copy.deepcopy(result),'fetchedAt':datetime.now(timezone.utc).isoformat()};self.store.save('twitch-ads.json',doc)
 def invalidate(self):
  doc=self.document();doc.setdefault('accounts',{}).pop(self.key(),None);self.store.save('twitch-ads.json',doc)
 async def schedule(self):
  if self.io.dry_run:return {**self.cached(),'preview':True}
  self.require('schedule');result=await self.io.twitch('GET','channels/ads',params={'broadcaster_id':self.io.config['broadcaster_id']})
  if not result.get('data'):raise ActionError('Twitch hat keinen Werbezeitplan geliefert')
  schedule_variables(result['data'][0]);self.save(result);return result
 async def commercial(self,length):
  length=duration(length)
  if self.io.dry_run:self.io.trace('twitch_commercial_preview',length=length);return {'preview':True}
  self.require('commercial');result=await self.io.twitch('POST','channels/commercial',{'broadcaster_id':self.io.config['broadcaster_id'],'length':length})
  if not result.get('data') or integer(result['data'][0].get('length',0),0)<=0:raise ActionError('Twitch hat die Werbeanfrage nicht bestätigt')
  self.invalidate();return result
 async def snooze(self):
  if self.io.dry_run:self.io.trace('twitch_snooze_preview');return {'preview':True}
  self.require('snooze');result=await self.io.twitch('POST','channels/ads/schedule/snooze',params={'broadcaster_id':self.io.config['broadcaster_id']})
  if not result.get('data'):raise ActionError('Twitch hat Snooze nicht bestätigt')
  self.invalidate();return result
 async def raid_start(self,login):
  if not self.io.dry_run:self.require('raid_start')
  target=await self.io.user(login)
  if target['id']==self.io.config.get('broadcaster_id'):raise ActionError('Ein Raid auf den eigenen Kanal ist nicht möglich')
  if self.io.dry_run:self.io.trace('twitch_raid_preview',operation='start',target=target['login']);return {'preview':True,'target':target}
  result=await self.io.twitch('POST','raids',params={'from_broadcaster_id':self.io.config['broadcaster_id'],'to_broadcaster_id':target['id']})
  if not result.get('data'):raise ActionError('Twitch hat den Raid-Start nicht bestätigt')
  return {**result,'target':target,'pending':True}
 async def raid_cancel(self):
  if self.io.dry_run:self.io.trace('twitch_raid_preview',operation='cancel');return {'preview':True}
  self.require('raid_cancel');await self.io.twitch('DELETE','raids',params={'broadcaster_id':self.io.config['broadcaster_id']});return {'cancelled':True}
async def operation(io,node,args):
 n={k:expand(v,args) for k,v in node.items()};t=n['type'];service=BroadcastTools(io)
 if t in (90900,90901):
  result=await service.schedule()
  if not result.get('data'):raise ActionError('Kein gespeicherter Werbezeitplan. Im Live-Modus aktualisieren.')
  args.update(schedule_variables(result['data'][0]))
 elif t==90902:
  result=await service.commercial(n['duration'])
  if result.get('data'):args.update(commercialLength=result['data'][0]['length'],commercialRetryAfter=result['data'][0].get('retry_after'))
 elif t==90903:
  args['snooze.success']=False;result=await service.snooze();args['snooze.success']=True
 elif t==90910:
  args['startRaidSuccess']=False;result=await service.raid_start(n['userLogin']);args['startRaidSuccess']=True;args['raidPending']=bool(result.get('pending'))
 elif t==90911:result=await service.raid_cancel()
 else:raise ActionError('Unbekannte Ads-/Raid-Unteraktion')
 if result.get('preview'):args['isPreview']=True
