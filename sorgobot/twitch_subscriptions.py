"""Read-only broadcaster subscriptions; a cached page is not a full inventory."""
import copy
from .catalog import ConfigStore
from .core import ActionError
from .twitch_rewards import scopes
SCOPE='channel:read:subscriptions'
class Subscribers:
 def __init__(self,io):self.io=io;self.store=ConfigStore(io.root)
 def key(self):return self.io.config.get('broadcaster_id','')+'|'+self.io.config.get('twitch_client_id','')
 def document(self):
  try:return self.store.read('twitch-subscribers.json')
  except FileNotFoundError:return {'accounts':{}}
 def cached(self):return copy.deepcopy(self.document().get('accounts',{}).get(self.key(),{}))
 async def list(self,cursor=''):
  if self.io.dry_run:return {**self.cached(),'data':self.cached().get('data',[]),'pagination':{},'preview':True}
  cfg=self.io.config
  if not all(cfg.get(k) for k in ('twitch_token','twitch_client_id','broadcaster_id')):raise ActionError('Broadcaster-Konto zuerst anmelden')
  if SCOPE not in scopes(cfg):raise ActionError('channel:read:subscriptions fehlt. Die gemeinsame Broadcaster-Freigabe unter Accounts ergänzt die Rechte.')
  result=await self.io.twitch('GET','subscriptions',params={'broadcaster_id':cfg['broadcaster_id'],'first':100,**({'after':cursor} if cursor else {})})
  doc=self.document();doc.setdefault('accounts',{})[self.key()]=copy.deepcopy(result);self.store.save('twitch-subscribers.json',doc);return result
async def operation(io,node,args):
 result=await Subscribers(io).list()
 if result.get('total') is None or result.get('points') is None:raise ActionError('Kein gespeicherter Abonnentenstand. Liste im Live-Modus aktualisieren.')
 args.update(subscriberCount=result['total'],subscriberPoints=result['points'])
 if result.get('preview'):args['isPreview']=True
