"""Original EventType identities with explicit filter validation."""
import copy,json
from pathlib import Path
MAPPING={int(k):v for k,v in json.loads(Path(__file__).with_name('original_trigger_map.json').read_text()).items()}
BASE={'id','type','enabled','exclusions'}
FLAGS={'tiers':{'prime':1,'tier 1':2,'tier 2':4,'tier 3':8},'monthsGifted':{1:1,3:2,6:4,12:8}}

def flag_values(field,value):
 mapping=FLAGS[field];allowed=31 if field=='tiers' else 15
 if type(value) is not int or value<0 or value&~allowed:raise ValueError('Ungültige Original-Bitmaske: '+field)
 if field=='tiers' and value&16:return []
 if value==0:return ['none']
 return [key for key,bit in mapping.items() if value&bit]

def flag_original(field,values):
 if not isinstance(values,list):raise ValueError('Triggerauswahl muss eine Liste sein: '+field)
 if values==['none']:return 0
 if not values:return 16 if field=='tiers' else 15
 if any(value not in FLAGS[field] for value in values):raise ValueError('Keine Original-Flagzuordnung für '+field)
 result=0
 for value in values:result|=FLAGS[field][value]
 return result

def filter_matches(trigger,key,value):
 expected=trigger.get(key)
 if expected in (None,'','either'):return True
 if key in trigger.get('_originalIgnoreCaseFields',[]) and isinstance(expected,str) and isinstance(value,str):return expected.casefold()==value.casefold()
 return expected==value

# These filters use event arguments rather than dispatcher keyword filters.
# Their field identities and comparisons were checked against Original 1.0.7.
EXTRA_FILTERS={4016:{'username':'','isUserId':False},120:{'username':'','isUserId':False},118:{'gameOnly':False,'gameId':'','gameName':''},186:{'minutes':None},710:{'userLogon':'','platform':''},702:{'variables':{}}}

RANGE_FILTERS={4006:'amount',4007:'amount',4030:'jewelsAmount',4031:'duration',136:'duration',492:'duration',497:'months',498:'months'}

def event_matches(trigger,args):
 source=trigger.get('_originalEventFilter',trigger.get('type') if trigger.get('type') in (4006,4007,4016,4030,4031) else None)
 if extra_problems(source,trigger):return False
 def equal(a,b):return isinstance(a,str) and isinstance(b,str) and a.casefold()==b.casefold()
 def selected(value):return isinstance(value,str) and bool(value.strip())
 if source==301:
  from .original_graph import canonical
  wanted=trigger.get('voiceCommandId')
  rows=args.get('_voiceCommandMatches',[])
  rows=rows if isinstance(rows,list) else []
  return not wanted or bool(canonical(wanted)) and any(isinstance(row,dict) and canonical(row.get('id'))==canonical(wanted) for row in rows)
 if source in RANGE_FILTERS:
  import math
  low,high=trigger.get('rangeMin',-1),trigger.get('rangeMax',-1)
  if any(type(bound) not in (int,float) or not math.isfinite(bound) or bound<-1 for bound in (low,high)) or low>=0 and high>=0 and low>high:return False
  if source==492 and low<0 and high<0:return True
  value=args.get(RANGE_FILTERS[source])
  if source in (4006,4007,4030,4031) and isinstance(value,str):
   try:value=float(value)
   except ValueError:return False
  if type(value) not in (int,float) or not math.isfinite(value):return False
  return (trigger.get('rangeMin',-1)<0 or value>=trigger['rangeMin']) and (trigger.get('rangeMax',-1)<0 or value<=trigger['rangeMax'])
 if source==4016:
  expected=trigger.get('username','');actual=args.get('userId') if trigger.get('isUserId') else args.get('userLogin',args.get('userName'))
  return not selected(expected) or expected==actual
 if source==120:
  expected=trigger.get('username','')
  return not selected(expected) or equal(expected,args.get('userId') if trigger.get('isUserId') else args.get('userLogin',args.get('userName')))
 if source==118:
  if trigger.get('gameOnly') and args.get('gameUpdate') is not True:return False
  return not selected(trigger.get('gameId','')) or equal(trigger['gameId'],str(args.get('gameId','')))
 if source==186:
  minutes=trigger.get('minutes')
  return minutes is None or type(args.get('minutes')) is int and args['minutes'] in minutes
 if source==710:
  return (not selected(trigger.get('userLogon','')) or equal(trigger['userLogon'],args.get('global.userLogin',''))) and (not selected(trigger.get('platform','')) or equal(trigger['platform'],args.get('global.userType',args.get('platform',''))))
 return True

def extra_problems(source,out):
 problems=[]
 for key,default in EXTRA_FILTERS.get(source,{}).items():
  value=out.get(key,default)
  if key=='variables':
   if not isinstance(value,dict) or any(not isinstance(k,str) or not k or not isinstance(v,str) for k,v in value.items()):problems.append('Testvariablen benötigen Textnamen und Textwerte.')
  elif key=='minutes':
   if value is not None and (not isinstance(value,list) or any(type(v) is not int or not 1<=v<=5 for v in value) or len(set(value))!=len(value)):problems.append('Upcoming-Ad-Minuten benötigen eine eindeutige Liste von 1 bis 5.')
  elif value is None and isinstance(default,str):continue
  elif type(value) is not type(default):problems.append('Ungültiger Original-Triggerfilter: '+key)
 return problems

def convert(trigger):
 out={k:copy.deepcopy(v) for k,v in trigger.items() if not k.startswith('_')};entry=MAPPING.get(out.get('type'))
 if not entry:return out,['Dieser Originaltrigger benötigt noch eine geprüfte Zuordnung: '+str(out.get('type'))]
 from .next_catalog import triggers
 native,defaults=entry['native'],copy.deepcopy(triggers()[entry['native']][1])
 source=out['type']
 if source in EXTRA_FILTERS:
  defaults.update(EXTRA_FILTERS[source]);out['_originalEventFilter']=source
 if source in RANGE_FILTERS:
  defaults.update(rangeMin=-1,rangeMax=-1);out['_originalEventFilter']=source
 problems=extra_problems(source,out)
 if source==15001:
  for field in set(trigger)-BASE-{'midiDevice','midiEvent'}:
   if not field.startswith('_'):problems.append('Unbekanntes Original-MIDI-Triggerfeld: '+field)
 fieldmap={};flags=[]
 if entry['name'] in ('GlobalVariableCreated','GlobalVariableDeleted','GlobalVariableUpdated','UserGlobalVariableUpdated'):
  if 'persisted' in out:
   choices=('either',True,False);value=out['persisted']
   if type(value) is int and value in range(3):out['persisted']=choices[value];out['_stateValues']={'persisted':list(choices)}
   elif value not in choices:problems.append('Ungültiger Original-Persisted-Filter.')
  out['_originalIgnoreCaseFields']=['variableName']
 renames={key:'connectionId' for key in ('serverId','clientId')}
 if entry['name'] in ('SpeechToTextCommand','SpeechToTextDictation'):
  renames['commandId']='voiceCommandId'
  defaults['voiceCommandId']=''
  from .original_graph import canonical,ZERO
  value=out.get('commandId',ZERO)
  if not canonical(value):problems.append('Sprachbefehl-Verweis benötigt eine gültige GUID.')
  out['commandId']='' if value==ZERO else value
  if source==301:out['_originalEventFilter']=301
 if entry['name']=='MidiMessage':
  renames['midiDevice']='midiDeviceId'
  defaults['midiEvent']='00000000-0000-0000-0000-000000000000'
 for old,new in renames.items():
  if old in out:out[new]=out.pop(old);fieldmap[new]=old
 for old,new in (('min','rangeMin'),('max','rangeMax')):
  if old not in out or new not in defaults:continue
  value=out.pop(old)
  import math
  if type(value) not in (int,float) or not math.isfinite(value) or value<-1:problems.append('Ungültiger Triggerbereich: '+old)
  out[new]=value;fieldmap[new]=old
 if all(type(out.get(key,-1)) in (int,float) for key in ('rangeMin','rangeMax')) and out.get('rangeMin',-1)>=0 and out.get('rangeMax',-1)>=0 and out['rangeMin']>out['rangeMax']:problems.append('Trigger-Minimum liegt über dem Maximum.')
 # Original's Max-only setting means an exact value, not an upper bound.
 if type(out.get('rangeMin',-1)) in (int,float) and type(out.get('rangeMax',-1)) in (int,float) and out.get('rangeMin',-1)<0 and out.get('rangeMax',-1)>=0:
  out['rangeMin']=out['rangeMax'];fieldmap['rangeMin']='min'
 for field in FLAGS:
  if field not in out or field not in defaults or isinstance(out[field],list):continue
  try:out[field]=flag_values(field,out[field]);flags.append(field)
  except ValueError as exc:problems.append(str(exc))
 if 'subType' in out and 'anonymous' in defaults:
  value=out.pop('subType');choices=('either','anonymous','public')
  if type(value) is int and value in range(3):out['anonymous']=choices[value];fieldmap['anonymous']='subType';out['_stateValues']={'anonymous':list(choices)}
  else:problems.append('Ungültiger Original-Gift-Typ.')
 if entry['name'].startswith('Obs') and 'obsId' in out:
  connection=out.pop('obsId');out['obsConnection']='any' if connection is None else 'default' if connection in ('','00000000-0000-0000-0000-000000000000') else connection;fieldmap['obsConnection']='obsId'
 if entry['name'].startswith('Obs') and 'connectionId' in out:
  connection=out.pop('connectionId');out['obsConnection']='default' if connection in (None,'','00000000-0000-0000-0000-000000000000') else connection
 for field in set(out)-BASE-set(defaults):
  if field.startswith('_'):continue
  problems.append('Original-Triggerfilter noch nicht zugeordnet: '+field)
 from .original_graph import canonical
 if not isinstance(out.get('exclusions',[]),list) or any(not canonical(value) for value in out.get('exclusions',[])):problems.append('Triggerausschlüsse benötigen eine Liste gültiger Trigger-IDs.')
 out['type']=native
 for key,value in defaults.items():out.setdefault(key,copy.deepcopy(value))
 if fieldmap:out['_fieldMap']=fieldmap
 if flags:out['_flagValues']=flags
 return out,problems


def arguments(trigger,args):
 """Per-trigger dictation context; never expose the shared matching scratch data."""
 result=dict(args)
 if trigger.get('type') not in (90252,90253):return result
 matched=result.pop('_voiceCommandMatches',[])
 matched=[row for row in matched if isinstance(row,dict)] if isinstance(matched,list) else []
 if trigger.get('_originalEventFilter')!=301:return result
 from .original_graph import canonical
 wanted=trigger.get('voiceCommandId')
 chosen=next((row for row in matched if not wanted or canonical(row.get('id'))==canonical(wanted)),{})
 import math
 percent=result.get('speechConfidence',0)
 percent=max(0,min(100,percent)) if type(percent) in (int,float) and math.isfinite(percent) else 0
 result.update(spokenText=result.get('voiceText',''),spokenTextConfidence=percent/100,spokenTextConfidencePercent=percent,spokenCommand=chosen.get('command',''),spokenTextInput=chosen.get('input',result.get('voiceText','')))
 if chosen:result.update(voiceCommandId=chosen['id'],voiceCommandName=chosen['name'])
 return result
