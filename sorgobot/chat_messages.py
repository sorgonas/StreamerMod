"""Public chat history metadata shared with the native chat window."""
import re,time

def history_row(event,args):
 emotes={}
 for part in (event.get('message') or {}).get('fragments',[]):
  if isinstance(part,dict) and part.get('type')=='emote':
   identity=(part.get('emote') or {}).get('id','')
   if isinstance(identity,str) and re.fullmatch(r'[A-Za-z0-9_-]+',identity):emotes[part.get('text','')]='https://static-cdn.jtvnw.net/emoticons/v2/'+identity+'/default/dark/2.0'
 for row in args.get('emotes',[]):
  if isinstance(row,dict) and isinstance(row.get('name'),str) and isinstance(row.get('imageUrl'),str):emotes[row['name']]=row['imageUrl']
 return {'platform':'twitch','receivedAt':time.time(),'user':args.get('user',''),'message':args.get('message',''),'id':event.get('message_id',''),'userId':args.get('userId',''),'login':args.get('userName',''),'roles':list(args.get('roles',[])),'emotes':emotes}
