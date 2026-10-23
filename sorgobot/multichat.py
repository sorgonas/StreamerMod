"""Explicit multi-platform sends; report partial delivery without retrying a write."""
from .core import ActionError
async def send(studio,data):
 from .server_contracts import send_message
 target=data.get('platform','twitch')
 if target not in ('twitch','youtube','both'):raise ActionError('Unbekanntes Chat-Sendeziel')
 if target!='both':await send_message(studio,data);return {'success':True}
 results={}
 for platform in ('twitch','youtube'):
  try:await send_message(studio,{**data,'platform':platform,'replyId':None});results[platform]={'success':True}
  except (ActionError,ValueError,OSError) as exc:results[platform]={'success':False,'error':str(exc)}
 success=all(r['success'] for r in results.values());partial=any(r['success'] for r in results.values()) and not success
 error='; '.join(p+': '+('gesendet' if r['success'] else r['error']) for p,r in results.items()) if not success else ''
 return {'success':success,'partial':partial,'results':results,'error':error}
async def operation(io,node,args):
 from .core import expand
 target=expand(node.get('chatPlatform','source'),args)
 if target=='source':target=args.get('commandSource',args.get('platform',args.get('userType','')))
 if target not in ('twitch','youtube','both'):raise ActionError('Ursprungsplattform fehlt; Twitch, YouTube oder beide auswählen')
 if io.dry_run:io.trace('multichat_preview',platform=target);args['isPreview']=True;return
 studio=getattr(getattr(io,'engine',None),'studio',None)
 if studio is None:raise ActionError('Chat-Laufzeit fehlt')
 result=await send(studio,{'platform':target,'message':expand(node.get('message',''),args),'bot':node.get('useBot',True),'internal':True})
 args['chatSendResults']=result;args['chatSendSuccess']=result['success']
 if not result['success']:raise ActionError(result['error'])
