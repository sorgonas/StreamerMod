"""YouTube channel information and platform-qualified native Core memberships."""
import re
from .core import expand
from .youtube_auth import YouTubeError
STEPS={96013:('User · Add Broadcaster Information',{}),96014:('User Groups · Add User to Group',{'userId':'%userId%','groupName':'','resultVariable':'addResult'}),96015:('User Groups · Remove User from Group',{'userId':'%userId%','groupName':'','resultVariable':'removeResult'}),96016:('User Groups · User in Group',{'userId':'%userId%','groupName':'','resultVariable':'inGroup'})}
async def operation(io,node,args):
 if io.dry_run:io.trace('youtube_users_preview',operation=node['type']);args['isPreview']=True;return
 engine=getattr(io,'engine',None);service=getattr(getattr(engine,'studio',None),'youtube',None)
 if service is None:raise YouTubeError('YouTube-Laufzeit fehlt')
 n={k:expand(v,args) for k,v in node.items()};kind=n['type']
 if kind==96013:
  reply=await service.request('GET','channels',params={'part':'snippet','mine':'true'})
  rows=reply.get('items',[]);owner=service.auth.account.get('channelId')
  if not isinstance(rows,list):raise YouTubeError('Ungültige Kanalantwort')
  rows=[r for r in rows if isinstance(r,dict) and r.get('id')==owner and isinstance(r.get('snippet'),dict)]
  if len(rows)!=1:raise YouTubeError('Eigener Kanal nicht eindeutig bestätigt')
  snippet=rows[0]['snippet'];name=snippet.get('title','')
  args.update(broadcastUser=name,broadcastUserName=owner,broadcastUserId=owner,broadcastUserType='youtube',broadcasterDescription=snippet.get('description',''),broadcasterCreatedAt=snippet.get('publishedAt',''),broadcasterChannelUrl='https://www.youtube.com/channel/'+owner)
  return
 uid=n.get('userId');name=n.get('groupName');variable=n.get('resultVariable')
 if not isinstance(uid,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,200}',uid):raise YouTubeError('Gültige YouTube-Kanal-ID angeben; Anzeigenamen sind nicht eindeutig')
 if not isinstance(name,str) or not name.strip():raise YouTubeError('Gruppenname fehlt')
 if not isinstance(variable,str) or not variable.strip():raise YouTubeError('Ergebnisvariable fehlt')
 from .users import store
 from .csharp_groups import rpc
 # The explicit case-sensitive channel ID is the identity, not a guessed display name.
 store(engine).remember('youtube',uid,uid)
 result=await rpc(engine,'group_user',[{96014:'add',96015:'remove',96016:'contains'}[kind],uid,'youtube',name,True])
 args[variable]=result;args[{96014:'addResult',96015:'removeResult',96016:'inGroup'}[kind]]=result
 if kind==96016:
  rows=[r for r in store(engine).known('youtube') if r['userId']==uid];row=rows[0] if rows else {}
  args.update(foundUser=row.get('displayName',uid),foundUserName=uid,foundUserId=uid,foundUserType='youtube',foundUserAvailable=bool(row.get('displayName') and row['displayName']!=uid))
