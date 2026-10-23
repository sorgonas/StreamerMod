"""Channel tags, branded-content state and markers with preview/write guards."""
import asyncio,time
from .core import ActionError,expand
from .twitch_rewards import scopes
from .twitch_channel import Channel
ENTRIES={91300:('Tags · Add Channel Tag',{'tag':'Deutsch'}),91301:('Tags · Remove Channel Tag',{'tag':'Deutsch'}),91302:('Tags · Clear Channel Tags',{}),91303:('Tags · Set Channel Tags',{'tags':['Deutsch']}),91304:('Channel · Set Channel Branded Content',{'state':'enabled'}),91305:('Channel · Create Stream Marker',{'description':''})}
def tags(value):
 if not isinstance(value,list) or len(value)>10:raise ActionError('Tags benötigen eine Liste mit höchstens 10 Einträgen')
 result=[];seen=set()
 for tag in value:
  if not isinstance(tag,str) or not 1<=len(tag)<=25 or not tag.isalnum():raise ActionError('Tags: 1–25 Zeichen, keine Leer- oder Sonderzeichen')
  if tag.casefold() in seen:raise ActionError('Tags dürfen nicht doppelt vorkommen')
  seen.add(tag.casefold());result.append(tag)
 return result
def description(value):
 if not isinstance(value,str) or len(value)>140:raise ActionError('Markerbeschreibung darf höchstens 140 Zeichen enthalten')
 return value
class ChannelTools:
 def __init__(self,io):
  self.io=io;self.cache=Channel(io)
  if not hasattr(io,'channel_tools_lock'):io.channel_tools_lock=asyncio.Lock()
 def require(self,write=False):
  self.cache.key()
  if not self.io.config.get('twitch_token'):raise ActionError('Broadcaster-Konto zuerst anmelden')
  if write and 'channel:manage:broadcast' not in scopes(self.io.config):raise ActionError('Kanalverwaltungsrecht fehlt; gemeinsame Broadcaster-Freigabe verwenden')
 async def info(self):
  if self.io.dry_run:return {**self.cache.cached('info'),'preview':True}
  self.require();account=self.cache.key();cfg=self.io.config;reply=await self.io.twitch('GET','channels',params={'broadcaster_id':cfg['broadcaster_id']});row=next(iter(reply.get('data',[])),None)
  if not row or row.get('broadcaster_id')!=cfg['broadcaster_id']:raise ActionError('Twitch hat keine gültigen Kanalinformationen geliefert')
  if account!=self.cache.key():raise ActionError('Konto während der Abfrage gewechselt; Antwort verworfen')
  result={'channel':row,'checkedAt':time.time()};self.cache.save('info',result);return result
 async def change(self,op,**fields):
  if op not in ('add','remove','clear','set','branded','marker'):raise ActionError('Unbekannte Kanalverwaltungsaktion')
  if op in ('add','remove'):tag=tags([fields.get('tag')])[0]
  if op=='set':requested=tags(fields.get('tags'))
  if op=='clear':requested=[]
  if op=='marker':text=description(fields.get('description',''))
  if op=='branded':
   state=fields.get('state','')
   if state not in ('enabled','disabled','toggle'):raise ActionError('Branded Content: Enabled, Disabled oder Toggle wählen')
  async with self.io.channel_tools_lock:
   if not self.io.dry_run:self.require(True)
   account=self.cache.key()
   if op in ('add','remove') or (op=='branded' and state=='toggle'):
    current=(await self.info()).get('channel')
    if not current:raise ActionError('Kein gespeicherter Kanalstand; zuerst im Live-Modus aktualisieren')
    if op in ('add','remove'):
     existing=tags(current.get('tags'))
     if op=='add':requested=existing if any(t.casefold()==tag.casefold() for t in existing) else tags(existing+[tag])
     else:requested=[t for t in existing if t.casefold()!=tag.casefold()]
    else:
     if type(current.get('is_branded_content')) is not bool:raise ActionError('Aktueller Branded-Content-Zustand unbekannt')
     branded=not current['is_branded_content']
   if op=='branded' and state!='toggle':branded=state=='enabled'
   body={'user_id':self.io.config['broadcaster_id'],'description':text} if op=='marker' else {'is_branded_content':branded} if op=='branded' else {'tags':requested}
   if self.cache.key()!=account:raise ActionError('Konto während der Kanaländerung gewechselt')
   if self.io.dry_run:
    self.io.trace('twitch_channel_tools_preview',operation=op,body=body);return {'preview':True,'success':False}
   reply=await self.io.twitch('POST','streams/markers',body) if op=='marker' else await self.io.twitch('PATCH','channels',body,params={'broadcaster_id':self.io.config['broadcaster_id']})
   if op=='marker':
    rows=reply.get('data',[])
    if not rows or not rows[0].get('id'):raise ActionError('Twitch hat den Stream-Marker nicht bestätigt')
    return {'success':True,'marker':rows[0]}
   self.cache.save('info',{});return {'success':True,**body}
async def operation(io,node,args):
 kind=node['type'];op={91300:'add',91301:'remove',91302:'clear',91303:'set',91304:'branded',91305:'marker'}[kind]
 if kind==91304:args['success']=False
 if kind==91305:
  args['streamMarkerSuccess']=False
  for key in ('streamMarkerId','streamMarkerCreatedAt','streamMarkerDescription','streamMarkerPosition'):args.pop(key,None)
 fields={key:[expand(tag,args) for tag in value] if key=='tags' and isinstance(value,list) else expand(value,args) for key,value in node.items() if key in ('tag','tags','state','description')};result=await ChannelTools(io).change(op,**fields)
 if result.get('preview'):args['isPreview']=True;return
 if kind==91304:args['success']=True
 if kind==91305:
  row=result['marker'];args.update(streamMarkerSuccess=True,streamMarkerId=row['id'],streamMarkerCreatedAt=row.get('created_at',''),streamMarkerDescription=row.get('description',''),streamMarkerPosition=row.get('position_seconds'))
