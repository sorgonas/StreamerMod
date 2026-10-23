"""Typed CPH data/results backed by Helix and existing account-scoped services."""
import datetime as dt,json,re
from pathlib import Path
from .core import ActionError
from .csharp_twitch import identity
from .twitch_chat_actions import Chat

SCHEMA={r['name']:r for r in json.loads(Path(__file__).with_name('csharp_twitch_models.json').read_text())}
SHORT={n.rsplit('.',1)[-1]:n for n in SCHEMA}
OPERATIONS={
 'TwitchGetBroadcaster','TwitchGetBot','TwitchGetUserInfoById','TwitchGetUserInfoByLogin','TwitchGetExtendedUserInfoById','TwitchGetExtendedUserInfoByLogin','TwitchGetVips','TwitchGetMods','TwitchIsUserSubscribed',
 'TwitchGetRewards','TwitchGetPinnedMessage','GetTeamInfo','GetTeamInfoById','GetTeamInfoByLogin','GetCheermotes','SetChannelGame','TwitchGetClipDownloadUrls','CreateStreamMarker',
 'TwitchGetChannelGuestStarSettings','TwitchUpdateChannelGuestStarSettings','TwitchGetGuestStarSession','TwitchCreateGuestStarSession','TwitchEndGuestStarSession','TwitchGetGuestStarInvites','TwitchSendGuestStarInvite','TwitchDeleteGuestStarInvite','TwitchAssignGuestStarSlot','TwitchUpdateGuestStarSlot','TwitchDeleteGuestStarSlot','TwitchUpdateGuestStarSlotSettings',
}

def snake(name):return re.sub(r'(?<!^)(?=[A-Z])','_',name).lower()
ALIASES={'UserName':'display_name','UserLogin':'login','UserId':'id','LastActive':'last_active','PreviousActive':'previous_active','GroupLayout':'layout','Position':'position_seconds','InputRequired':'is_user_input_required','Paused':'is_paused','Enabled':'is_enabled','IsOurs':'manageable','TeamId':'team_id'}

def dto(name,row):
 if row is None:return None
 if not isinstance(row,dict):raise ActionError('Ungültiges Twitch-Ergebnisobjekt: '+name)
 full=SHORT.get(name,name);schema=SCHEMA[full];result={}
 if schema['baseType'] in SCHEMA:result.update(dto(schema['baseType'],row))
 for prop in schema['properties']:
  key=prop['name'];kind=prop['type'];remote=ALIASES.get(key,snake(key))
  if key in row:value=row[key]
  elif remote in row:value=row[remote]
  elif snake(key) in row:value=row[snake(key)]
  elif key=='UserName' and 'user_display_name' in row:value=row['user_display_name']
  else:continue
  if value is None:continue
  if kind.startswith('System.Collections.Generic.List`1<'):
   if not isinstance(value,list):raise ActionError('Twitch-Ergebnisliste ungültig: '+key)
   element=kind.split('<',1)[1][:-1];value=[dto(element,x) for x in value] if element in SCHEMA else value
  elif kind in SCHEMA and not SCHEMA[kind]['isEnum']:value=dto(kind,value)
  elif kind in ('System.Int32','System.Int64'):
   from .twitch_rewards import integer
   value=integer(value,-2**31 if kind.endswith('32') else -2**63)
   if kind.endswith('32') and value>2**31-1:raise ActionError('Original-Twitch-Ergebnis überschreitet Int32: '+key)
  result[key]=value
 return result

def rows(reply):
 value=reply.get('data') if isinstance(reply,dict) else None
 if not isinstance(value,list) or any(not isinstance(r,dict) for r in value):raise ActionError('Twitch hat keine gültige Ergebnisliste geliefert')
 return value

async def pages(io,endpoint,params=None,required=()):
 if io.dry_run:return []
 Chat(io).account(required=required or None);result=[];cursor=None;seen=set()
 while True:
  query={**(params or {}),'first':100}
  if cursor:query['after']=cursor
  reply=await io.twitch('GET',endpoint,params=query);result.extend(rows(reply));cursor=reply.get('pagination',{}).get('cursor')
  if not cursor:return result
  if not isinstance(cursor,str) or cursor in seen:raise ActionError('Twitch-Paginierung wiederholt sich; unvollständige Liste verworfen')
  seen.add(cursor)

async def subscribed(io,uid):
 identity(uid,'Nutzer-ID')
 if io.dry_run:return {'subscribed':False,'tier':''}
 owner=Chat(io).account(required=('channel:read:subscriptions',))
 data=rows(await io.twitch('GET','subscriptions',params={'broadcaster_id':owner,'user_id':uid}))
 if any(r.get('broadcaster_id')!=owner or r.get('user_id')!=uid for r in data):raise ActionError('Abonnementantwort gehört nicht zum angeforderten Nutzer')
 return {'subscribed':bool(data),'tier':data[0].get('tier','') if data else ''}

async def user(io,value,by_id,extended=False):
 from .twitch_user_info import user_data,login
 value=identity(value,'Nutzer-ID') if by_id else login(value)
 if io.dry_run:return None
 owner=Chat(io).account();raw=user_data(await io.twitch('GET','users',params={'id' if by_id else 'login':value}),value,by_id)
 uid=raw['id'];sub=await subscribed(io,uid)
 # These flags describe membership in the connected broadcaster's channel.
 auth=Chat(io);auth.account(required=('channel:manage:moderators','moderation:read'));auth.account(required=('channel:manage:vips','channel:read:vips'))
 mods=rows(await io.twitch('GET','moderation/moderators',params={'broadcaster_id':owner,'user_id':uid}));vips=rows(await io.twitch('GET','channels/vips',params={'broadcaster_id':owner,'user_id':uid}))
 if any(r.get('user_id')!=uid for r in mods+vips):raise ActionError('Rollenabfrage gehört nicht zum angeforderten Nutzer')
 result=dto('TwitchUserInfoEx' if extended else 'TwitchUserInfo',raw);result.update(IsSubscribed=sub['subscribed'],SubscriptionTier=sub['tier'],IsModerator=uid==owner or bool(mods),IsVip=bool(vips))
 engine=getattr(io,'engine',None)
 if engine is not None and engine.state.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='known_users'").fetchone():
  activity=engine.state.db.execute('SELECT last_active FROM known_users WHERE platform=? AND user_id=?',('twitch',uid)).fetchall()
  if len(activity)==1 and activity[0][0]>0:result['LastActive']=dt.datetime.fromtimestamp(activity[0][0],dt.timezone.utc).isoformat()
 if extended:
  auth.account(required=('moderator:read:followers',))
  follows=rows(await io.twitch('GET','channels/followers',params={'broadcaster_id':owner,'user_id':uid}));channels=rows(await io.twitch('GET','channels',params={'broadcaster_id':uid}))
  if any(r.get('user_id')!=uid for r in follows) or len(channels)!=1 or channels[0].get('broadcaster_id')!=uid:raise ActionError('Erweiterte Nutzerantwort gehört nicht zum angeforderten Nutzer')
  channel=channels[0];created=dt.datetime.fromisoformat(raw['created_at'].replace('Z','+00:00'))
  result.update(UserType=raw.get('type',''),IsPartner=raw.get('broadcaster_type')=='partner',IsAffiliate=raw.get('broadcaster_type')=='affiliate',IsFollowing=bool(follows),AccountAge=(dt.datetime.now(dt.timezone.utc)-created).total_seconds()/86400,Game=channel.get('game_name',''),GameId=channel.get('game_id',''),ChannelTitle=channel.get('title',''),Tags=channel.get('tags',[]))
 return result

async def operation(io,name,args):
 if name=='TwitchIsUserSubscribed':return await subscribed(io,args[0])
 if name in ('TwitchGetBroadcaster','TwitchGetBot'):
  value=io.config.get('bot_id' if name.endswith('Bot') else 'broadcaster_id')
  return None if not value else await user(io,value,True)
 if name.startswith(('TwitchGetUserInfo','TwitchGetExtendedUserInfo')):return await user(io,args[0],name.endswith('ById'),'Extended' in name)
 if name in ('TwitchGetMods','TwitchGetVips'):
  moderator=name.endswith('Mods');owner=io.config.get('broadcaster_id')
  values=await pages(io,'moderation/moderators' if moderator else 'channels/vips',{'broadcaster_id':owner},('channel:manage:moderators','moderation:read') if moderator else ('channel:manage:vips','channel:read:vips'))
  return [dto('TwitchUserInfo',{'id':r.get('user_id'),'login':r.get('user_login'),'display_name':r.get('user_name'),'IsModerator':moderator,'IsVip':not moderator}) for r in values]
 if name=='TwitchGetRewards':
  from .twitch_rewards import Rewards
  return [dto('TwitchReward',r) for r in (await Rewards(io).list())['data']]
 if name=='TwitchGetPinnedMessage':
  data,_=await Chat(io).pinned()
  if not data:return None
  row=data[0];parts=[]
  for part in row['message']['fragments']:
   kind=part.get('type');value={'$part':'mention' if kind=='mention' else 'emote' if kind=='emote' else 'text','Type':kind,'Text':part.get('text','')}
   if kind=='mention':value.update(dto('TwitchMessagePartMention',part.get('mention',{})));value['$part']='mention'
   elif kind=='emote':
    emote=part.get('emote',{});value.update(Source='twitch',ImageUrl='https://static-cdn.jtvnw.net/emoticons/v2/'+str(emote.get('id',''))+'/default/dark/3.0',ZeroWidth=False);value['$part']='emote'
   else:value['$part']='text'
   parts.append(value)
  result=dto('PinnedMessageData',row);result.update(Sender=dto('TwitchUserInfo',{'id':row['sender_user_id'],'login':row['sender_user_login'],'display_name':row['sender_user_name']}),PinnedBy=dto('TwitchUserInfo',{'id':row['pinned_by_user_id'],'login':row['pinned_by_user_login'],'display_name':row['pinned_by_user_name']}),Fragments=parts);return result
 if name.startswith('GetTeamInfo'):
  from .twitch_user_info import UserInfo,login
  by_id=name.endswith('ById') or type(args[0]) is int;value=str(args[0]) if by_id else login(args[0]);body,_=await UserInfo(io).read('teams',value,by_id)
  return [dto('TeamInfo',{**r,'Id':r.get('broadcaster_id'),'Login':r.get('broadcaster_login'),'Name':r.get('broadcaster_name')}) for r in body['teams']]
 if name=='GetCheermotes':return [dto('Cheermote',r) for r in await pages(io,'bits/cheermotes',{'broadcaster_id':io.config.get('broadcaster_id')})]
 if name=='SetChannelGame':
  game=identity(args[0],'Spielname')
  if io.dry_run:io.trace('twitch_game_preview',game=game);return None
  from .twitch_channel_tools import ChannelTools
  from .csharp_twitch_controls import empty
  service=ChannelTools(io);service.require(True);values=rows(await io.twitch('GET','games',params={'name':game}))
  if len(values)!=1 or not values[0].get('id'):raise ActionError('Twitch-Spiel wurde nicht eindeutig gefunden')
  row=values[0];empty(await io.twitch('PATCH','channels',{'game_id':row['id']},params={'broadcaster_id':io.config['broadcaster_id']}));service.cache.save('info',{});return dto('GameInfo',row)
 if name=='CreateStreamMarker':
  from .twitch_channel_tools import ChannelTools
  result=await ChannelTools(io).change('marker',description=args[0]);return None if result.get('preview') else dto('StreamMarker',result['marker'])
 if name=='TwitchGetClipDownloadUrls':
  from .twitch_queries import Queries,clip_id,clip
  target=clip_id(args[0]);owner=io.config.get('broadcaster_id');value,_=await Queries(io).read('clip-download',target,'clips/downloads',{'broadcaster_id':owner,'editor_id':owner,'clip_id':target},('channel:manage:clips',),lambda r:clip(r,target));return dto('ClipDownloadData',value)
 if 'GuestStar' in name:return await guest(io,name,args)
 raise ActionError('Unbekannte Twitch-Ergebnisfunktion')

async def guest(io,name,args):
 from .twitch_guest_star import GuestStar,settings,sessions,invites
 service=GuestStar(io)
 if name=='TwitchGetChannelGuestStarSettings':value,_=await service.read('settings','channel','guest_star/channel_settings',service.params(),settings);return dto('GuestStarSettings',value)
 if name=='TwitchGetGuestStarSession':
  values,_=await service.read('session','channel','guest_star/session',service.params(),lambda r:sessions(r,service.cache.account()[0]));return dto('GuestSession',values[0]) if values else None
 if name=='TwitchGetGuestStarInvites':
  current,_=await service.session();params={**service.params(),'session_id':current['id']};values,_=await service.read('invites',current['id'],'guest_star/invites',params,invites);return [dto('GuestStarInvite',v) for v in values]
 kind,keys={
  'TwitchUpdateChannelGuestStarSettings':(92101,('moderatorSendLiveEnabled','slotCount','browserSourceAudioEnabled','groupLayout','regenerateBrowserSources')),
  'TwitchCreateGuestStarSession':(92103,()),'TwitchEndGuestStarSession':(92104,('sessionId',)),
  'TwitchSendGuestStarInvite':(92106,('userLogin',)),'TwitchDeleteGuestStarInvite':(92107,('userLogin',)),
  'TwitchAssignGuestStarSlot':(92108,('userLogin','slot')),'TwitchUpdateGuestStarSlot':(92109,('sourceSlot','destinationSlot')),
  'TwitchDeleteGuestStarSlot':(92110,('userLogin','slot')),'TwitchUpdateGuestStarSlotSettings':(92111,('slot','audioEnabled','videoEnabled','live','volume')),
 }[name]
 node={key:value for key,value in zip(keys,args) if value is not None}
 result=await service.mutate(kind,node)
 if name in ('TwitchCreateGuestStarSession','TwitchEndGuestStarSession'):return dto('GuestSession',result['session']) if result else None
 return result is not None
