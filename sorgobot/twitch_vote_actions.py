from .core import expand,ActionError
from .twitch_votes import Votes
from .twitch_rewards import integer
from .twitch_vote_events import variables
async def operation(io,node,args):
 t=node['type'];n={k:([expand(x,args) for x in v] if isinstance(v,list) else expand(v,args)) for k,v in node.items()};kind='polls' if t<90610 else 'predictions';service=Votes(io,kind)
 if t in (90600,90610):
  args['success']=False
  result=await service.create(n['title'],n['choices' if kind=='polls' else 'outcomes'],n['duration'],n.get('channelPointsPerVote',0))
  if result.get('preview'):args.update(success=True,isPreview=True);return
  row=result['data'][0];args.update(variables(kind,row));args['success']=True
  return
 row=await service.find(include_locked=True);args['active']=bool(row and row['status']=='ACTIVE')
 if row:args.update(variables(kind,row))
 if t in (90601,90611):return
 flag={90612:'locked',90613:'cancelled',90614:'success',90615:'success'}.get(t)
 if flag:args[flag]=False
 if not row:raise ActionError('Keine aktive Abstimmung vorhanden')
 if kind=='polls' and row['status']!='ACTIVE':raise ActionError('Keine aktive Umfrage vorhanden')
 status={90602:'TERMINATED',90603:'ARCHIVED',90612:'LOCKED',90613:'CANCELED',90614:'RESOLVED',90615:'RESOLVED'}[t];winner=''
 if t in (90614,90615):
  if t==90614:index=integer(n['winningIndex'],0)
  else:
   matches=[i for i,o in enumerate(row['outcomes']) if o['title']==n['outcomeTitle']]
   if len(matches)!=1:raise ActionError('Ergebnis-Titel fehlt oder ist nicht eindeutig')
   index=matches[0]
  if index>=len(row['outcomes']):raise ActionError('Winning Index außerhalb der Ergebnisse')
  winner=row['outcomes'][index]['id']
 result=await service.change(row['id'],status,winner)
 if result.get('preview'):args['isPreview']=True
 elif result.get('data'):args.update(variables(kind,result['data'][0]))
 if flag:args[flag]=True
