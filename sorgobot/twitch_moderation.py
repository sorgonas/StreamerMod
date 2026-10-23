"""Broadcaster moderation. Preview validates locally and cannot write to Twitch."""
from .core import ActionError,expand
from .twitch_rewards import scopes,integer
from .catalog import ConfigStore
ENDPOINTS={'bans':'moderation/banned','vips':'channels/vips','moderators':'moderation/moderators'}
READ={'bans':{'moderation:read','moderator:manage:banned_users'},'vips':{'channel:read:vips','channel:manage:vips'},'moderators':{'moderation:read','channel:manage:moderators'}}
WRITE={'bans':'moderator:manage:banned_users','vips':'channel:manage:vips','moderators':'channel:manage:moderators'}
EVENT_SCOPES={'channel.ban':{'channel:moderate'},'channel.unban':{'channel:moderate'},'channel.vip.add':READ['vips'],'channel.vip.remove':READ['vips'],'channel.moderator.add':{'moderation:read'},'channel.moderator.remove':{'moderation:read'}}
OPERATIONS={20:'timeout',90700:'ban',90701:'unban',90702:'untimeout',90703:'add_vip',90704:'remove_vip',90705:'add_moderator',90706:'remove_moderator'}
def validate(op,reason='',duration=60):
 if op not in OPERATIONS.values():raise ActionError('Unbekannte Moderationsaktion')
 if not isinstance(reason,str) or len(reason)>500:raise ActionError('Grund maximal 500 Zeichen')
 if op=='timeout':
  seconds=integer(duration,0)
  if seconds>1209600:raise ActionError('Timeout maximal 1209600 Sekunden (14 Tage)')
  return seconds
 return None
class Moderation:
 def __init__(self,io):self.io=io;self.store=ConfigStore(io.root)
 def require(self,kind,write=False):
  cfg=self.io.config
  if kind not in ENDPOINTS:raise ActionError('Unbekannte Moderationsliste')
  if not all(cfg.get(k) for k in ('twitch_token','broadcaster_id','twitch_client_id')):raise ActionError('Broadcaster-Konto zuerst anmelden')
  if not scopes(cfg)&({WRITE[kind]} if write else READ[kind]):raise ActionError('Twitch-Freigabe fehlt. Die gemeinsame Broadcaster-Freigabe unter Accounts ergänzt die Rechte.')
 def document(self):
  try:return self.store.read('twitch-moderation.json')
  except FileNotFoundError:return {'accounts':{}}
 def key(self):return self.io.config.get('broadcaster_id','')+'|'+self.io.config.get('twitch_client_id','')
 async def list(self,kind,cursor=''):
  if kind not in ENDPOINTS:raise ActionError('Unbekannte Moderationsliste')
  doc=self.document()
  if self.io.dry_run:return {'data':doc.get('accounts',{}).get(self.key(),{}).get(kind,[]),'pagination':{},'preview':True}
  self.require(kind)
  result=await self.io.twitch('GET',ENDPOINTS[kind],params={'broadcaster_id':self.io.config['broadcaster_id'],'first':100,**({'after':cursor} if cursor else {})})
  doc.setdefault('accounts',{}).setdefault(self.key(),{})[kind]=result.get('data',[]);self.store.save('twitch-moderation.json',doc);return result
 async def change(self,op,login,reason='',duration=60):
  seconds=validate(op,reason,duration);kind='vips' if 'vip' in op else 'moderators' if 'moderator' in op else 'bans'
  if not self.io.dry_run:self.require(kind,True)
  user=await self.io.user(login)
  if not self.io.dry_run and user['id']==self.io.config['broadcaster_id']:raise ActionError('Broadcaster kann nicht Ziel dieser Moderationsaktion sein')
  if self.io.dry_run:
   self.io.trace('twitch_moderation_preview',operation=op,userLogin=user['login'],reason=reason,duration=seconds);return {'preview':True,'user':user}
  params={'broadcaster_id':self.io.config['broadcaster_id']};body=None
  if kind=='bans':
   params['moderator_id']=self.io.config['broadcaster_id'];endpoint='moderation/bans'
   if op in ('ban','timeout'):
    method='POST';body={'data':{'user_id':user['id'],'reason':reason}}
    if op=='timeout' and seconds:body['data']['duration']=seconds
   else:
    method='DELETE';params['user_id']=user['id']
    if op=='untimeout':
     found=await self.io.twitch('GET',ENDPOINTS['bans'],params={'broadcaster_id':params['broadcaster_id'],'user_id':user['id']})
     rows=found.get('data',[])
     if not rows or not rows[0].get('expires_at'):raise ActionError('Kein aktiver Timeout gefunden. Dauerhafte Sperren werden mit Unban aufgehoben.')
  else:endpoint=ENDPOINTS[kind];method='POST' if op.startswith('add_') else 'DELETE';params['user_id']=user['id']
  result=await self.io.twitch(method,endpoint,body,params=params)
  if method=='POST' and kind=='bans' and not result.get('data'):raise ActionError('Twitch hat die Sperre nicht bestätigt')
  # Cached lists become stale after a confirmed write.
  doc=self.document();doc.setdefault('accounts',{}).setdefault(self.key(),{}).pop(kind,None);self.store.save('twitch-moderation.json',doc)
  return {'user':user,'response':result,'preview':False}
async def operation(io,node,args):
 op=OPERATIONS[node['type']];n={k:expand(v,args) for k,v in node.items()};login=n.get('userLogin','')
 if not login:
  source=n.get('sourceType','User')
  if source=='User':login=args.get('userName',args.get('userLogin',''))
  elif source=='From Input':login=args.get('input0','')
  elif source=='Variable':login=args.get(n.get('variable','userName'),'')
  else:raise ActionError('Ungültiger Benutzereingang')
 prefix,flag={'ban':('bannedUser','banResult'),'timeout':('timedOutUser','timeoutResult'),'unban':('unbannedUser','unbanResult'),'untimeout':('unTimedOutUser','unTimedOutResult')}.get(op,('targetUser','success'))
 args[flag]=False
 result=await Moderation(io).change(op,login,n.get('reason',''),n.get('duration',60));u=result['user']
 args.update({prefix:u['display_name'],prefix+'Name':u['login'],prefix+'Id':u['id'],prefix+'Type':'twitch',flag:True})
 if result['preview']:args['isPreview']=True
