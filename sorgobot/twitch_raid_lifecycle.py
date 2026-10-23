"""Outgoing raid lifecycle from channel.moderate v2, including external commands."""
import html
from .core import ActionError
from .twitch_expansion_events import Events,person,count
from .twitch_shared_chat import base
from .twitch_user_info import user_data

ENTRIES={92800:('Raid · Raid Start',{}),92801:('Raid · Raid Cancelled',{})}
ALIASES={92800:'twitch/raid/start',92801:'twitch/raid/cancelled'}
ACTIONS={'raid':92800,'unraid':92801}

def variables(event,occurred_at=''):
 action=event.get('action')
 if action not in ACTIONS:return None
 args=base(event)
 source=event.get('source_broadcaster_user_id')
 if source and source!=args['broadcasterUserId']:return None
 body=event.get(action)
 if not isinstance(body,dict):raise ActionError('Raid-Ereignis ohne passende Zieldaten')
 target=person(body,'user_');actor=person(event,'moderator_user_')
 if target['Id']==args['broadcasterUserId']:raise ActionError('Raid-Ziel ist der eigene Kanal')
 args.update(raidUser=target[''],raidUserName=target['Name'],raidUserId=target['Id'],
  raidUserProfileImageURL='',raidUserProfileImageEscaped='',raidTargetInfoAvailable=False,
  moderatorUserId=actor['Id'],moderatorUserName=actor['Name'],moderatorUser=actor[''],
  createdAt=occurred_at,createdAtSource='eventsub' if occurred_at else 'unknown',raidEventSource='channel.moderate')
 if action=='raid':args['viewers']=count(body,'viewer_count')
 return ACTIONS[action],args

async def ingest(io,event,identity,occurred_at=''):
 if io.dry_run or not isinstance(event,dict) or event.get('broadcaster_user_id')!=io.config.get('broadcaster_id'):return None
 mapped=variables(event,occurred_at)
 if not mapped:return None
 # Claim only validated events; duplicate deliveries never repeat the action or lookup.
 before=tuple(io.config.get(k) for k in ('broadcaster_id','twitch_client_id','twitch_token'))
 mapped=Events(io).commit('channel.moderate',identity,*mapped)
 if not mapped:return None
 args=mapped[1]
 try:
  reply=await io.twitch('GET','users',params={'id':args['raidUserId']})
  target=user_data(reply,args['raidUserId'],by_id=True)
  image=target.get('profile_image_url')
  if not isinstance(image,str) or not image:raise ActionError('Raid-Profilbild fehlt')
  args.update(raidUserProfileImageURL=image,raidUserProfileImageEscaped=html.escape(image,quote=True),raidTargetInfoAvailable=True)
 except Exception:
  # The real lifecycle event remains usable if optional public metadata is unavailable.
  io.trace('raid_target_info_unavailable',target=args['raidUserId'])
 if before!=tuple(io.config.get(k) for k in ('broadcaster_id','twitch_client_id','twitch_token')):return None
 return mapped

def example(kind,config):
 action='raid' if kind==92800 else 'unraid'
 event={'broadcaster_user_id':config.get('broadcaster_id') or 'test-broadcaster',
  'broadcaster_user_login':config.get('twitch_login') or 'testbroadcaster','broadcaster_user_name':'Test Broadcaster',
  'moderator_user_id':'test-moderator','moderator_user_login':'testmod','moderator_user_name':'Test Moderator',
  'action':action,action:{'user_id':'test-target','user_login':'testtarget','user_name':'Test Target','viewer_count':12}}
 args=variables(event,'2026-10-14T12:00:00Z')[1]
 image='https://example.invalid/raid-target.png'
 args.update(raidUserProfileImageURL=image,raidUserProfileImageEscaped=html.escape(image,quote=True),raidTargetInfoAvailable=True)
 return args
