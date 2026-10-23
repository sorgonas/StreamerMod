"""Validated Helix polls/predictions; preview never sends a Twitch request."""
import copy
from .catalog import ConfigStore
from .core import ActionError
from .twitch_rewards import integer,scopes
KINDS=('polls','predictions')
def payload(kind,title,options,duration,points=0):
 if kind not in KINDS:raise ActionError('Unbekannter Abstimmungstyp')
 limit=60 if kind=='polls' else 45
 if not isinstance(title,str) or not title.strip() or len(title)>limit:raise ActionError(f'Titel benötigt 1–{limit} Zeichen')
 if isinstance(options,str):options=options.splitlines()
 if not isinstance(options,list) or not 2<=len(options)<=(5 if kind=='polls' else 10):raise ActionError('Polls benötigen 2–5 Optionen, Predictions 2–10')
 if any(not isinstance(s,str) or not s.strip() or len(s)>25 for s in options):raise ActionError('Jede Option benötigt 1–25 Zeichen')
 if len({s.casefold() for s in options})!=len(options):raise ActionError('Optionen müssen unterschiedliche Titel haben')
 seconds=integer(duration,15 if kind=='polls' else 30)
 if seconds>1800:raise ActionError('Dauer maximal 1800 Sekunden')
 result={'title':title,'choices' if kind=='polls' else 'outcomes':[{'title':s} for s in options],'duration' if kind=='polls' else 'prediction_window':seconds}
 if kind=='polls':
  points=integer(points,0)
  if points>1000000:raise ActionError('Zusatzstimme maximal 1000000 Punkte')
  result['channel_points_voting_enabled']=points>0
  if points:result['channel_points_per_vote']=points
 return result
class Votes:
 def __init__(self,io,kind):
  if kind not in KINDS:raise ActionError('Unbekannter Abstimmungstyp')
  self.io=io;self.kind=kind;self.store=ConfigStore(io.root)
 def key(self):return self.io.config.get('broadcaster_id','')+'|'+self.io.config.get('twitch_client_id','')
 def document(self):
  try:return self.store.read('twitch-votes.json')
  except FileNotFoundError:return {'accounts':{}}
 def cached(self):return self.document().get('accounts',{}).get(self.key(),{}).get(self.kind,[])
 def save(self,rows):
  doc=self.document();doc.setdefault('accounts',{}).setdefault(self.key(),{})[self.kind]=copy.deepcopy(rows);self.store.save('twitch-votes.json',doc)
 def require(self,write=False):
  cfg=self.io.config
  if not cfg.get('twitch_token') or not cfg.get('broadcaster_id') or not cfg.get('twitch_client_id'):raise ActionError('Broadcaster-Konto zuerst anmelden')
  allowed={'channel:manage:'+self.kind} if write else {'channel:read:'+self.kind,'channel:manage:'+self.kind}
  if not scopes(cfg)&allowed:raise ActionError('Berechtigung fehlt: channel:'+('manage:' if write else 'read:')+self.kind+'. Freigabe über Grant Access auf der Twitch-Seite ergänzen.')
 async def request(self,method,body=None,params=None):
  if self.io.dry_run:raise ActionError('Echte Twitch-Abstimmungen sind nur im Live-Modus verfügbar')
  self.require(method!='GET')
  if method!='GET':body={'broadcaster_id':self.io.config['broadcaster_id'],**(body or {})}
  else:params={'broadcaster_id':self.io.config['broadcaster_id'],**(params or {})}
  return await self.io.twitch(method,self.kind,body,params=params)
 async def list(self,cursor=''):
  if self.io.dry_run:return {'data':self.cached(),'preview':True,'pagination':{}}
  result=await self.request('GET',params={'first':20,**({'after':cursor} if cursor else {})});self.save(result.get('data',[]));return result
 async def find(self,identity='',include_locked=True):
  if not identity:
   rows=(await self.list())['data'];return next((r for r in rows if r['status']=='ACTIVE' or (self.kind=='predictions' and include_locked and r['status']=='LOCKED')),None)
  if self.io.dry_run:rows=self.cached()
  else:rows=(await self.request('GET',params={'id':identity}))['data']
  row=next((r for r in rows if r['id']==identity),None)
  if row is None:raise ActionError('Ausgewählte Abstimmung wurde nicht gefunden')
  return row
 async def create(self,title,options,duration,points=0):
  body=payload(self.kind,title,options,duration,points)
  if self.io.dry_run:self.io.trace('twitch_vote_preview',voteKind=self.kind,operation='create',payload=body);return {'data':[],'preview':True}
  result=await self.request('POST',body)
  if not result.get('data'):raise ActionError('Twitch hat das Erstellen nicht bestätigt')
  self.save(result['data']);return result
 async def change(self,identity,status,winner=''):
  allowed=('TERMINATED','ARCHIVED') if self.kind=='polls' else ('LOCKED','RESOLVED','CANCELED')
  if status not in allowed:raise ActionError('Ungültiger Zielzustand')
  if not self.io.dry_run:self.require(True)
  row=await self.find(identity)
  if row is None:raise ActionError('Keine aktive Abstimmung vorhanden')
  current=row['status']
  valid=current=='ACTIVE' or (self.kind=='polls' and status=='ARCHIVED' and current in ('COMPLETED','TERMINATED')) or (self.kind=='predictions' and current=='LOCKED' and status in ('RESOLVED','CANCELED'))
  if not valid:raise ActionError('Abstimmung ist nicht mehr im benötigten Zustand. Liste aktualisieren.')
  body={'id':row['id'],'status':status}
  if status=='RESOLVED':
   if winner not in {o['id'] for o in row['outcomes']}:raise ActionError('Gewinnendes Ergebnis gehört nicht zu dieser Prediction')
   body['winning_outcome_id']=winner
  if self.io.dry_run:self.io.trace('twitch_vote_preview',voteKind=self.kind,operation='change',payload=body);return {'data':[],'preview':True}
  result=await self.request('PATCH',body)
  if not result.get('data'):raise ActionError('Twitch hat die Zustandsänderung nicht bestätigt')
  self.save(result['data']);return result
