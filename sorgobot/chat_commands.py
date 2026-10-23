"""Native chat command dispatch. Local commands never become Twitch messages."""
import re
from .core import ActionError,RenderedText
COMMANDS=('title','game','clear','clear/overlay','action','me','announce','timeout','ban','unban','mod','unmod','vip','unvip','slow','slowoff','subscribers','subscribersoff','commercial','raid','raidcancel','shoutout','unpin','clear/twitch')
def login(value):
 value=value.lstrip('@')
 if not re.fullmatch(r'[A-Za-z0-9_]{1,25}',value):raise ActionError('Gültigen Twitch-Nutzernamen angeben')
 return value

def number(value,default,low,high,choices=None):
 if not value:return default
 if not re.fullmatch(r'\d+',value):raise ActionError('Eine ganze Zahl angeben')
 result=int(value)
 if not low<=result<=high or choices and result not in choices:raise ActionError('Dauer außerhalb des zulässigen Bereichs')
 return result

async def send(studio,data):
 from .original_websocket import mutable
 from .server_contracts import send_message,execute
 mutable(studio)
 if not isinstance(data,dict):raise ValueError('Chat-Anfrage')
 text=data.get('message')
 if not isinstance(text,str) or not text.strip() or len(text)>500 or any(c in text for c in ('\x00','\r','\n')):raise ActionError('Chatnachricht: 1–500 Zeichen, eine Zeile')
 if type(data.get('bot',True)) is not bool or type(data.get('internal',False)) is not bool:raise ValueError('bot/internal')
 platform=data.get('platform','twitch')
 if platform not in ('twitch','youtube','both'):raise ActionError('Diese Plattform ist nicht eingerichtet')
 if not text.startswith('/'):
  from .multichat import send as send_targets
  return await send_targets(studio,data)
 command,_,tail=text[1:].partition(' ');tail=tail.strip()
 if command not in COMMANDS:raise ActionError('Unbekannter Chatbefehl: /'+command)
 if platform!='twitch' and command not in ('clear','clear/overlay','action'):raise ActionError('Diesen Chatbefehl unterstützt nur Twitch; Sendeziel Twitch auswählen')
 if platform=='both' and command=='action':raise ActionError('Für /action eine einzelne Ursprungsplattform auswählen')
 if command in ('clear','clear/overlay'):
  if tail:raise ActionError('Dieser Befehl hat keine Argumente')
  if command=='clear':
   studio.twitch.messages.clear()
   if getattr(studio,'youtube',None):studio.youtube.messages.clear()
  key='chat_history_reset' if command=='clear' else 'chat_overlay_reset'
  setattr(studio,key,getattr(studio,key,0)+1)
  if command=='clear/overlay':studio.main_websocket.publish('General','Custom',{'event':'streamerbot:overlay:clear'})
  return
 if command=='action':
  if not tail:raise ActionError('Action-ID oder eindeutigen Action-Namen angeben')
  target={'id':tail} if any(a['id'].casefold()==tail.casefold() for a in studio.engine.actions.values()) else {'name':tail}
  return execute(studio,{'action':target,'args':{'platform':platform,'isInternal':True}})
 if command in ('title','game','me','announce'):
  if not tail:raise ActionError('Text fehlt')
  if command=='me':return await send_message(studio,{**data,'message':'/me '+tail})
  if command=='announce':
   from .twitch_chat_actions import operation
   return await operation(studio.io,{'type':91804,'message':RenderedText(tail),'preferredAccount':'Bot' if data.get('bot',True) else 'Broadcaster','color':'Default'},{})
  from .twitch_channel_tools import ChannelTools
  ChannelTools(studio.io).require(True)
  return await studio.io.step(15 if command=='title' else 16,{'type':15 if command=='title' else 16,'title' if command=='title' else 'game':RenderedText(tail)},{})
 if command in ('ban','timeout','unban','mod','unmod','vip','unvip'):
  from .twitch_moderation import Moderation
  user,_,rest=tail.partition(' ');user=login(user);seconds=60
  if command=='timeout':
   duration,_,reason=rest.partition(' ');seconds=number(duration,60,0,1209600)
  else:reason=rest
  if command not in ('ban','timeout') and rest:raise ActionError('Dieser Befehl erwartet nur einen Nutzernamen')
  op={'mod':'add_moderator','unmod':'remove_moderator','vip':'add_vip','unvip':'remove_vip'}.get(command,command)
  return await Moderation(studio.io).change(op,user,reason,seconds)
 if command in ('slow','slowoff','subscribers','subscribersoff'):
  from .twitch_chat_modes import ChatModes
  slow=command.startswith('slow');enabled=not command.endswith('off')
  duration=number(tail,60,3,120) if command=='slow' else ''
  if command!='slow' and tail:raise ActionError('Dieser Befehl hat keine Argumente')
  return await ChatModes(studio.io).change({'type':91402 if slow else 91403,'state':enabled,'duration':duration},{})
 if command in ('commercial','raid','raidcancel'):
  from .twitch_ads_raids import BroadcastTools,DURATIONS
  service=BroadcastTools(studio.io)
  if command=='commercial':return await service.commercial(number(tail,60,30,180,DURATIONS))
  if command=='raid':return await service.raid_start(login(tail))
  if tail:raise ActionError('Dieser Befehl hat keine Argumente')
  return await service.raid_cancel()
 if command=='shoutout':
  from .twitch_queries import Queries
  return await Queries(studio.io).shoutout(login(tail))
 if tail:raise ActionError('Dieser Befehl hat keine Argumente')
 from .twitch_chat_actions import operation
 return await operation(studio.io,{'type':91805 if command=='unpin' else 91800},{})
