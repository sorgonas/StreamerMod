import datetime as dt
import json

def parse(value):
 if not value:return None
 try:return dt.datetime.fromisoformat(value.replace('Z','+00:00'))
 except (ValueError,TypeError):return None

def variables(kind,row,now=None):
 prefix='poll' if kind=='polls' else 'prediction';result={prefix+'Id':row['id'],prefix+'.Id':row['id'],prefix+'.Title':row.get('title',''),prefix+'.Status':row.get('status','')}
 if kind=='polls':
  start=parse(row.get('started_at'));end=parse(row.get('ends_at') or row.get('ended_at'));duration=row.get('duration')
  if duration is None:duration=max(0,int((end-start).total_seconds())) if start and end else 0
  until=parse(row.get('ends_at')) or (start+dt.timedelta(seconds=duration) if start else None)
  remaining=max(0,int((until-(now or dt.datetime.now(dt.timezone.utc))).total_seconds()*1000)) if until and row.get('status','ACTIVE')=='ACTIVE' else 0
  result.update({'poll.StartedAt':row.get('started_at',''),'poll.Duration':duration,'poll.DurationRemaining':remaining,'poll.endedAt':row.get('ended_at',''),'poll.choices.count':len(row.get('choices',[])),'poll.votes':0,'poll.rewardVotes':0,'poll.totalVotes':0})
  options=[]
  for i,c in enumerate(row.get('choices',[])):
   total=c.get('votes',0);reward=c.get('channel_points_votes',0)+c.get('bits_votes',0);normal=max(0,total-reward)
   fields={'id':c['id'],'title':c['title'],'votes':normal,'rewardVotes':reward,'totalVotes':total};options.append(fields)
   result.update({f'poll.choice{i}.{k}':v for k,v in fields.items()});result['poll.votes']+=normal;result['poll.rewardVotes']+=reward;result['poll.totalVotes']+=total
  if options and row.get('status') in ('COMPLETED','TERMINATED','ARCHIVED'):
   greatest=max(c['totalVotes'] for c in options);winners=[i for i,c in enumerate(options) if c['totalVotes']==greatest]
   result['poll.winningIndices']=winners;result['poll.isTie']=len(winners)>1
   if len(winners)==1:result['poll.winningIndex']=winners[0];result.update({'poll.winningChoice.'+k:v for k,v in options[winners[0]].items()})
 else:
  result.update({'prediction.CreatedAt':row.get('created_at') or row.get('started_at',''),'prediction.PredictionWindow':row.get('prediction_window',0),'prediction.outcomes.count':len(row.get('outcomes',[]))})
  if not result['prediction.PredictionWindow']:
   start=parse(row.get('started_at'));end=parse(row.get('locks_at'))
   if start and end:result['prediction.PredictionWindow']=max(0,int((end-start).total_seconds()))
  for i,o in enumerate(row.get('outcomes',[])):
   fields={'id':o['id'],'title':o['title'],'users':o.get('users',0),'points':o.get('channel_points',0),'color':o.get('color','')}
   result.update({f'prediction.outcome{i}.{k}':v for k,v in fields.items()})
   if o['id']==row.get('winning_outcome_id'):result['prediction.winningIndex']=i;result.update({'prediction.winningOutcome.'+k:v for k,v in fields.items()})
 result[prefix+'._json']=json.dumps({k.removeprefix(prefix+'.'):v for k,v in result.items() if k.startswith(prefix+'.')},ensure_ascii=False)
 return result

def notification(kind,event):
 row=dict(event)
 if kind.startswith('channel.poll.'):
  part=kind.rsplit('.',1)[1]
  row['status']=str(row.get('status') or {'begin':'ACTIVE','progress':'ACTIVE'}.get(part,'COMPLETED')).upper()
  identity={'begin':90650,'progress':90651,'end':{'completed':90652,'terminated':90653,'archived':90654}.get(event.get('status','').lower())}.get(part)
  return (identity,variables('polls',row)) if identity else None
 if kind.startswith('channel.prediction.'):
  part=kind.rsplit('.',1)[1];row['status']=str(row.get('status') or {'begin':'ACTIVE','progress':'ACTIVE','lock':'LOCKED'}.get(part,'RESOLVED')).upper()
  identity={'begin':90660,'progress':90661,'lock':90662,'end':{'resolved':90663,'canceled':90664}.get(event.get('status','').lower())}.get(part)
  return (identity,variables('predictions',row)) if identity else None
 return None
