"""Public projections of existing stores; no internal settings or auth data."""
import copy


def commands(engine):
 from .csharp_commands import commands_list,dispatcher
 from .command_state import SOURCES
 original=commands_list(engine);native=dispatcher(engine).commands;bits={label:bit for label,bit in SOURCES.values()}
 return [{'id':row['Id'],'name':row['Name'],'enabled':row['Enabled'],'group':row['Group'] or None,'commands':row['Commands'] if row['Mode']==0 else [row['RegexCommand']], 'caseSensitive':row['CaseSensitive'],'ignoreInternal':item.get('ignoreInternalMessages',True),'ignoreBotAccount':item.get('ignoreBotAccount',True),'sources':sum(bits[label] for label in row['Sources'])} for row,item in zip(original,native)]


def names(rows):
 result=[]
 for row in rows:
  value=row if isinstance(row,str) else next((row.get(key) for key in ('user','displayName','name','userName','userLogin') if isinstance(row.get(key),str) and row.get(key)),None) if isinstance(row,dict) else None
  if value and value not in result:result.append(value)
 return result


def credits(engine):
 from .csharp_core_services import credits_snapshot,credits as read_credits
 raw=read_credits(engine);value=credits_snapshot(engine);users=value['User'];groups={key.removeprefix('Group: '):names(rows) for key,rows in users.items() if key.startswith('Group: ')}
 result={'events':{key.lower():names(rows) for key,rows in value['Events'].items()},'hypeTrain':{'conductors':names(value['HypeTrainConductor']),'contributors':names(value['HypeTrainContributors'])},'users':{key.lower():names(users.get(key,[])) for key in ('Editors','Moderators','Subscribers','VIPs','Users')},'groups':groups,'custom':copy.deepcopy(value.get('Custom',{})),'top':{label:names(rows) for label,rows in [('allBits',value['TopBits'].get('All',[])),('monthBits',value['TopBits'].get('Month',[])),('weekBits',value['TopBits'].get('Week',[])),('channelRewards',value['TopChannelRewards'])]}}
 result['events']['hypetrains']=names(raw.get('Events',{}).get('HypeTrains',[]));result['users']['groups']=names([name for rows in groups.values() for name in rows])
 return result
