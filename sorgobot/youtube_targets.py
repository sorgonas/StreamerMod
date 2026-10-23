"""Original 1.0.7 selector: All, Latest, From Variable (broadcast.id)."""
from .youtube_auth import YouTubeError

def target(service,node,args):
 explicit=node.get('broadcastId','')
 if explicit:
  if not isinstance(explicit,str):raise YouTubeError('Ungültige Broadcast-ID')
  return explicit
 mode=node.get('broadcastMode','latest')
 if mode=='variable':
  value=args.get('broadcast.id',args.get('broadcastId'))
  if not isinstance(value,str) or not value.strip():raise YouTubeError('Die Variable broadcast.id fehlt')
  return value
 if mode not in ('all','latest'):raise YouTubeError('Ungültige Broadcast-Auswahl')
 # This runtime monitors one broadcast. All and Latest therefore address the
 # same monitored broadcast; neither falls back to an unrelated upcoming item.
 if not service.broadcast or service.phase not in ('connected','reconnecting'):raise YouTubeError('Kein YouTube-Broadcast wird überwacht')
 return service.broadcast['id']
