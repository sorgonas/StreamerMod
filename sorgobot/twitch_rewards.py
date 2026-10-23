"""Helix rewards with ownership checks and account-scoped local baselines."""
import copy
import re
from decimal import Decimal,InvalidOperation
from .catalog import ConfigStore
from .core import ActionError
ENDPOINT='channel_points/custom_rewards'
READ={'channel:read:redemptions','channel:manage:redemptions'}
MANAGE='channel:manage:redemptions'
BOOLS=('is_enabled','is_paused','is_user_input_required','is_max_per_stream_enabled','is_max_per_user_per_stream_enabled','is_global_cooldown_enabled','should_redemptions_skip_request_queue')
LIMITS={'max_per_stream':'is_max_per_stream_enabled','max_per_user_per_stream':'is_max_per_user_per_stream_enabled','global_cooldown_seconds':'is_global_cooldown_enabled'}
FIELDS=('title','prompt','cost','background_color',*BOOLS,*LIMITS)
def scopes(config):
 value=config.get('twitch_scopes',[])
 return set(value.split() if isinstance(value,str) else value or [])
def integer(value,minimum=0):
 try:
  number=Decimal(str(value))
  if isinstance(value,bool) or not number.is_finite() or number!=number.to_integral_value() or not minimum<=number<=2**63-1:raise ValueError()
  return int(number)
 except (ValueError,InvalidOperation):raise ActionError('Ganzzahl außerhalb des zulässigen Bereichs') from None
def validate(payload,create=False):
 if not isinstance(payload,dict) or set(payload)-set(FIELDS):raise ActionError('Unbekannte Reward-Felder')
 value=copy.deepcopy(payload)
 if create and not {'title','cost'}<=value.keys():raise ActionError('Titel und Kosten fehlen')
 for key,maximum in [('title',45),('prompt',200)]:
  if key in value:
   if not isinstance(value[key],str) or len(value[key])>maximum or (key=='title' and not value[key].strip()):raise ActionError(f'{key}: maximal {maximum} Zeichen; Titel darf nicht leer sein')
 if 'cost' in value:value['cost']=integer(value['cost'],1)
 if 'background_color' in value and not re.fullmatch(r'#[0-9a-fA-F]{6}',str(value['background_color'])):raise ActionError('Farbe benötigt #RRGGBB')
 for key in BOOLS:
  if key in value and not isinstance(value[key],bool):raise ActionError(f'{key} muss true/false sein')
 for key,enabled in LIMITS.items():
  if key in value:value[key]=integer(value[key],1)
  if value.get(enabled) is True and key not in value:raise ActionError(f'{key} fehlt für aktiviertes Limit')
 if create and 'is_paused' in value:raise ActionError('Pausieren erst nach dem Erstellen möglich')
 return value
def editable(reward):
 result={key:reward[key] for key in FIELDS if key in reward}
 if not result.get('background_color'):result.pop('background_color',None)
 for key,enabled in LIMITS.items():
  setting=reward.get('global_cooldown_setting' if key=='global_cooldown_seconds' else key+'_setting',{})
  result[enabled]=bool(setting.get('is_enabled',False))
  if result[enabled]:result[key]=setting[key]
 return result
def variables(reward):
 result={'rewardId':reward['id'],'rewardTitle':reward.get('title',''),'rewardName':reward.get('title',''),'rewardCost':reward.get('cost',0),'rewardPrompt':reward.get('prompt',''),'rewardBackgroundColor':reward.get('background_color',''),'rewardEnabled':bool(reward.get('is_enabled')),'rewardPaused':bool(reward.get('is_paused')),'rewardSkipRequestQueue':bool(reward.get('should_redemptions_skip_request_queue')),'rewardIsOurs':bool(reward.get('manageable'))}
 for key,name in [('max_per_stream','rewardMaxPerStream'),('max_per_user_per_stream','rewardMaxPerUserPerStream'),('global_cooldown_seconds','rewardGlobalCooldown')]:
  setting=reward.get('global_cooldown_setting' if key=='global_cooldown_seconds' else key+'_setting',{})
  result[name]=setting.get(key,0) if setting.get('is_enabled') else 0
 return result
class Rewards:
 def __init__(self,io):self.io=io;self.store=ConfigStore(io.root)
 def key(self):return self.io.config.get('broadcaster_id','')+'|'+self.io.config.get('twitch_client_id','')
 def document(self):
  try:return self.store.read('rewards.json')
  except FileNotFoundError:return {'accounts':{}}
 def cache(self):return self.document().get('accounts',{}).get(self.key(),{'rewards':[],'originals':{},'groups':{}})
 def save(self,value):
  doc=self.document();doc.setdefault('accounts',{})[self.key()]=value;self.store.save('rewards.json',doc)
 def require(self,write=False):
  cfg=self.io.config
  if not cfg.get('twitch_token') or not cfg.get('broadcaster_id') or not cfg.get('twitch_client_id'):raise ActionError('Broadcaster-Konto zuerst anmelden und validieren')
  needed={MANAGE} if write else READ
  if not scopes(cfg)&needed:raise ActionError('Twitch-Berechtigung fehlt: '+(MANAGE if write else 'channel:read:redemptions')+'. Broadcaster über Login erneut freigeben.')
 async def request(self,method,endpoint=ENDPOINT,body=None,params=None):
  if self.io.dry_run:raise ActionError('Echte Reward-Verwaltung ist nur im Live-Modus verfügbar')
  self.require(method!='GET')
  try:return await self.io.twitch(method,endpoint,body,params={'broadcaster_id':self.io.config['broadcaster_id'],**(params or {})})
  except ActionError as exc:
   if str(exc).startswith('HTTP 403'):raise ActionError('Twitch verweigert Reward-Zugriff: Ersteller-Anwendung und Affiliate/Partner-Status prüfen') from None
   if str(exc).startswith('HTTP 404'):raise ActionError('Reward/Einlösung nicht vorhanden oder bereits abgeschlossen. Liste aktualisieren.') from None
   raise
 async def list(self):
  if self.io.dry_run:return {'data':self.cache()['rewards'],'preview':True}
  all_rows=(await self.request('GET')).get('data',[])
  managed={r['id'] for r in (await self.request('GET',params={'only_manageable_rewards':'true'})).get('data',[])}
  cache=self.cache();rows=[]
  for row in all_rows:
   row=copy.deepcopy(row);row['manageable']=row['id'] in managed;row['group']=cache['groups'].get(row['id'],'');rows.append(row)
   if row['manageable']:cache['originals'].setdefault(row['id'],editable(row))
  cache['rewards']=rows;self.save(cache)
  return {'data':rows,'preview':False}
 async def get(self,identity,managed=False):
  if not identity:raise ActionError('Reward-ID fehlt')
  rows=(await self.list())['data'];row=next((r for r in rows if r['id']==identity),None)
  if row is None:
   if self.io.dry_run:return {'id':identity,'title':'Preview Reward','prompt':'','cost':1,'is_enabled':True,'manageable':True}
   raise ActionError('Reward wurde nicht gefunden')
  if managed and not row.get('manageable'):raise ActionError('Reward gehört zu einer anderen Twitch-Anwendung und kann hier nicht geändert werden')
  return row
 async def create(self,payload):
  payload=validate(payload,True)
  result=await self.request('POST',body=payload)
  if not result.get('data'):raise ActionError('Twitch hat keinen erstellten Reward bestätigt')
  row=result['data'][0];cache=self.cache();cache['originals'][row['id']]=editable(row);self.save(cache);return result
 async def update(self,identity,payload):
  payload=validate(payload)
  if not payload:raise ActionError('Keine Reward-Änderung angegeben')
  await self.get(identity,True)
  if self.io.dry_run:self.io.trace('twitch_reward_preview',rewardId=identity,changes=payload);return {'data':[],'preview':True}
  self.require(True);result=await self.request('PATCH',body=payload,params={'id':identity})
  if not result.get('data'):raise ActionError('Twitch hat die Reward-Änderung nicht bestätigt')
  return result
 async def delete(self,identity):
  await self.get(identity,True);await self.request('DELETE',params={'id':identity})
  cache=self.cache();cache['rewards']=[r for r in cache['rewards'] if r['id']!=identity];cache['groups'].pop(identity,None);cache['originals'].pop(identity,None);self.save(cache);return True
 async def redemptions(self,identity,status='UNFULFILLED',cursor=''):
  if status not in ('UNFULFILLED','FULFILLED','CANCELED'):raise ActionError('Ungültiger Einlösungsstatus')
  await self.get(identity,True)
  return await self.request('GET',ENDPOINT+'/redemptions',params={'reward_id':identity,'status':status,'first':50,'sort':'OLDEST',**({'after':cursor} if cursor else {})})
 async def redeem(self,identity,redemption,status):
  if status not in ('FULFILLED','CANCELED') or not redemption:raise ActionError('Einlösungs-ID oder Status ungültig')
  await self.get(identity,True)
  if self.io.dry_run:self.io.trace('twitch_redemption_preview',rewardId=identity,redemptionId=redemption,status=status);return {'data':[],'preview':True}
  result=await self.request('PATCH',ENDPOINT+'/redemptions',{'status':status},{'reward_id':identity,'id':redemption})
  if not result.get('data'):raise ActionError('Twitch hat den Einlösungsstatus nicht bestätigt')
  return result
 def group(self,identity,name):
  cache=self.cache()
  if not any(r['id']==identity for r in cache['rewards']):raise ActionError('Reward zuerst aktualisieren')
  cache['groups'][identity]=str(name).strip()
  for row in cache['rewards']:
   if row['id']==identity:row['group']=str(name).strip()
  self.save(cache);return True
