"""Explicit original 1.0.7 field conversions, backed by serialized class metadata.

Numeric IDs in this table are original IDs, never native catalogue positions.
"""
import copy

# original: (native, original field -> native field)
MAP={
 4001:(96000,{'text':'message','broadcast':'broadcastMode'}),4002:(96010,{'broadcast':'broadcastMode'}),4003:(96011,{'broadcast':'broadcastMode'}),4004:(96012,{'broadcast':'broadcastMode'}),
 4005:(96014,{'userLogin':'userId'}),4006:(96015,{'userLogin':'userId'}),4007:(96016,{'userLogin':'userId'}),4008:(96003,{'broadcast':'broadcastMode'}),4009:(96002,{'broadcast':'broadcastMode'}),
 4010:(96013,{}),4011:(96017,{'broadcast':'broadcastMode'}),4012:(96018,{'broadcast':'broadcastMode'}),
 5:(90015,{'file':'path','variableName':'resultVariable'}),6:(90003,{'command':'program'}),
 1006:(90014,{'file':'path','variableName':'resultVariable'}),1007:(90002,{'variableName':'resultVariable'}),1021:(90016,{'file':'path','count':'line','variableName':'resultVariable'}),1003:(90010,{'min':'minimum','max':'maximum'}),
 1026:(95002,{}),1027:(95001,{}),
 1:(90141,{'soundFile':'path','soundName':'playbackId'}),7:(90142,{'folder':'path','soundName':'playbackId'}),2:(90140,{'payload':'text'}),
 1000:(90112,{}),1037:(90110,{}),1024:(90145,{}),
 1008:(95000,{'variableName':'resultVariable'}),1012:(90146,{}),1018:(90134,{'commandId':'voiceCommandId'}),1019:(90135,{'commandId':'voiceCommandId'}),1025:(95003,{}),
 3:(90017,{'file':'path'}),8:(90130,{}),9:(90022,{}),
 1001:(90051,{'actionQueueId':'queueId'}),1004:(90019,{}),1005:(90050,{'actionQueueId':'queueId'}),
 1010:(90023,{'groupName':'group'}),1011:(90027,{'groupName':'group'}),
 1013:(90021,{'groupName':'group','variableName':'resultVariable','hasPermission':'onlyHasPermission'}),
 1014:(90025,{}),1015:(90024,{'groupName':'group'}),1016:(90018,{}),1017:(90026,{'groupName':'group'}),
 1020:(90011,{'message':'text'}),1022:(90052,{'actionQueueId':'queueId'}),
 1023:(90160,{'outputVariable':'resultVariable','autoTypeOutput':'autoType'}),
 1028:(90028,{}),1030:(90100,{}),1031:(90120,{'useArge':'includeArguments','customArgs':'arguments','queueSignal':'queue'}),
 1032:(90121,{}),1033:(90131,{}),1034:(90132,{}),1035:(90113,{}),1036:(90111,{}),
 1039:(90012,{'file':'path','variableName':'resultVariable'}),1040:(90013,{'folder':'path','variableName':'resultVariable'}),
 125:(90101,{}),126:(90102,{}),127:(90164,{}),128:(90161,{}),129:(90162,{}),130:(90163,{}),
 99903:(90165,{}),99904:(90165,{}),
 21:(91600,{}),24:(91200,{}),29:(92003,{}),
 11:(90511,{}),22:(91701,{'present':'presentOnly'}),23:(91804,{'text':'message','fallback':'fallbackToBroadcaster'}),25:(92000,{}),52:(91601,{}),203:(90516,{}),
 251:(91302,{}),252:(91303,{}),253:(91300,{}),254:(91301,{}),
 500:(90910,{}),501:(90911,{}),502:(90703,{}),503:(90704,{}),504:(90705,{}),505:(90706,{}),
 506:(91201,{}),507:(91202,{}),508:(90800,{}),509:(91102,{}),510:(91800,{}),
 511:(90700,{}),512:(90701,{}),513:(90702,{}),
 551:(91100,{}),552:(91101,{'value':'count'}),553:(91500,{}),554:(91501,{}),558:(91502,{}),
 555:(90903,{}),556:(90900,{}),557:(90901,{}),
 560:(91803,{'text':'message','fallback':'fallbackToBroadcaster'}),
 561:(90600,{}),562:(90602,{}),563:(90603,{}),565:(91902,{}),566:(90601,{}),
 567:(90611,{}),568:(90610,{'predictionWindow':'duration'}),569:(90613,{}),570:(90612,{}),571:(90614,{}),572:(90615,{}),
 573:(92001,{}),575:(91801,{}),576:(91802,{}),578:(91805,{}),579:(91903,{}),580:(91904,{}),
 19:(90902,{}),17:(91305,{}),26:(91900,{}),27:(91901,{'status':'state'}),564:(91304,{'status':'state'}),
 12:(91403,{'status':'state'}),13:(91400,{'status':'state'}),14:(91402,{'status':'state'}),28:(91401,{'status':'state'}),
 550:(91700,{'userIndex':'index'}),577:(91806,{}),
 200:(90501,{}),201:(90502,{}),202:(90505,{}),204:(90509,{}),205:(90503,{}),206:(90504,{}),207:(90510,{}),
 208:(90500,{}),209:(90514,{}),210:(90515,{}),211:(90512,{'groupName':'group'}),212:(90513,{'groupName':'group'}),
 213:(90506,{'backgroundColor':'color','random':'randomColor'}),214:(90508,{}),215:(90507,{}),
 520:(92100,{}),521:(92101,{}),522:(92102,{}),523:(92103,{}),524:(92104,{}),525:(92105,{}),526:(92106,{}),527:(92107,{}),528:(92108,{}),529:(92109,{}),530:(92110,{}),531:(92111,{}),
 33:(90312,{}),45:(90311,{}),43:(90300,{}),328:(90301,{}),49:(90310,{}),321:(90313,{}),327:(90323,{'random':'randomColor'}),
 1038:(90029,{}),10001:(90133,{}),
 # OBS: selectors are mapped separately for every native OBS type.
 31:(90318,{}),32:(90321,{}),34:(90005,{}),35:(90304,{}),36:(90308,{}),37:(90307,{'degrees':'rotation','additive':'relative'}),
 40:(90317,{}),41:(90322,{}),42:(90302,{}),44:(90324,{}),47:(90320,{}),
 46:(90315,{}),324:(90305,{}),325:(90309,{}),326:(90319,{}),329:(90316,{}),
 11001:(93000,{}),11002:(93001,{}),11004:(93002,{}),11005:(93004,{}),11006:(93005,{}),11007:(93006,{}),11008:(93003,{}),
 9001:(90152,{}),9002:(90150,{'controller':'control'}),9003:(90151,{}),
 99998:(90061,{'executeCodeId':'codeId','saveResultToVariable':'saveResult','saveToVariable':'resultVariable'}),
}
IDENTITY={4,10,15,16,18,20,30,38,39,48,50,51,120,121,122,123,124,1002,1009,322,323,99900,99901,99902}
STATE_TYPES={8,9,1001,1004,1010,1011,1022,1028,1030,1033,1019,35,40,42,44,47,200,201,211,212}
SUPPORTED=IDENTITY|{90060,90314}|{v[0] for v in MAP.values()}
REQUIRED={4:('actionId',),10:('text',),15:('title',),16:('game',),20:('userLogin','duration'),30:('sceneName','sourceName','state'),38:('sourceName','url'),39:('sourceName','text'),50:('userLogin',),51:('userLogin',),121:('variableName','destinationVariable'),122:('variableName','value'),123:('variableName','value'),1002:('value',),322:('sourceName','fileName'),323:('sourceName','fileName')}

def convert(node):
 source=node['type'];out={k:copy.deepcopy(v) for k,v in node.items() if not k.startswith('_')};issues=[]
 if source not in IDENTITY and source not in MAP:return out,['Noch keine Ausführungsmigration für Unteraktion '+str(source)]
 fieldmap={}
 required={3:('file','text'),4:('actionId',),8:('timerId','state'),9:('commandId','state'),1004:('actionId','state'),1028:('actionId','subActionId','state'),1033:('actionId','triggerId','state'),1038:('actionId','subActionId','weight'),6:('command',),1007:('url',),5:('file',),1006:('file',),1021:('file','count'),1:('soundFile',),7:('folder',)}
 if any(field not in node for field in required.get(source,())):issues.append('Original-Pflichtfelder fehlen bei Unteraktion '+str(source))
 if source in MAP:
  target,renames=MAP[source];out['type']=target
  from .next_catalog import STEPS
  for key,value in STEPS.get(target,('',{}))[1].items():out.setdefault(key,copy.deepcopy(value))
  for old,new in renames.items():
   if old in node:out[new]=out.pop(old)
   fieldmap[new]=old
 if source==4001:
  for field in ('useBot','fallback'):
   out[field]=node.get(field,False)
   if type(out[field]) is not bool:issues.append('YouTube-Kontoauswahl benötigt bool: '+field)
 if source in (4001,4002,4003,4004,4008,4009,4011,4012):
  mode=node.get('broadcast',0);modes=['all','latest','variable']
  if type(mode) is int and mode in range(3):out['broadcastMode']=modes[mode];out['_stateValues']={'broadcastMode':modes}
  else:issues.append('Unbekannte YouTube-Broadcast-Auswahl.')
 if source in (1001,1005,1022) and out.get('queueId') in ('','00000000-0000-0000-0000-000000000000'):out['queueId']=None
 if source in STATE_TYPES:
  value=node.get('state')
  states=('pause','resume') if source==1001 else ('paused','unpaused','toggle') if source in (201,212) else ('enabled','disabled','toggle')
  if type(value) is int and value in range(len(states)):out['state']=states[value];out['_stateValues']={'state':list(states)}
  else:issues.append('Ungültiger Original-Zustand bei Unteraktion '+str(source))
 if source in (33,45):
  choices=('start','stop') if source==33 else ('start','stop','pause','resume');value=node.get('state')
  if type(value) is int and value in range(len(choices)):out['state']=choices[value];out['_stateValues']={'state':list(choices)}
  else:issues.append('Unbekannter OBS-Ausgabezustand.')
 if source==1008:
  try:
   channels=[int(node.get(key,255)) for key in ('alpha','red','green','blue')]
   if any(not 0<=v<=255 for v in channels):raise ValueError()
   out['color']='#'+''.join(f'{v:02x}' for v in channels[1:]);out['_originalSemantics']='pickColor'
  except (TypeError,ValueError):issues.append('Ungültige Original-Farbkanäle.')
 if source==1012:
  from .original_keyboard import sequence
  try:out['keys']=sequence(node['key'],node.get('modifiers',0))
  except (ValueError,KeyError) as exc:issues.append(str(exc))
 if source in (1,7,1025):
  from .original_audio import convert as audio_convert
  issues.extend(audio_convert(node,out))
 if source==1018:out['_originalSemantics']='voiceCommand'
 if source in (12,13,14,28,27,564):
  value=node.get('status')
  choices=('Yes','No','Toggle') if source==27 else ('enabled','disabled','toggle') if source==564 else (True,False)
  if type(value) is int and value in range(len(choices)):out['state']=choices[value];out['_stateValues']={'state':list(choices)}
  elif type(value) is bool and source in (12,13,14,28):out['state']=value
  else:issues.append('Unbekannter Twitch-Modus-Zustand.')
 if source==579:
  choices=('ACTIVE_MONITORING','RESTRICTED');value=node.get('status',0)
  if type(value) is int and value in range(len(choices)):
   out['status']=choices[value];out['_stateValues']={'status':list(choices)}
  else:issues.append('Ungültiger Original-Suspicious-Status: erwartet 0 (Actively Monitoring) oder 1 (Restricted).')
  out['_originalSemantics']='suspiciousStatus'
 if source in (202,207):
  choices=('none','add','subtract','multiply','divide');value=node.get('operator',0)
  if type(value) is int and value in range(5):out['operator']=choices[value];out['_stateValues']={'operator':list(choices)}
  else:issues.append('Unbekannter Reward-Kostenoperator.')
 if source in (205,206):out['resetToOriginal']=not bool(node.get('title' if source==205 else 'prompt'))
 if source==49:
  choices=('play','pause','restart','stop','next','previous');value=node.get('state')
  if type(value) is int and value in range(6):out['state']=choices[value];out['_stateValues']={'state':list(choices)}
  else:issues.append('Ungültiger OBS-Medienzustand.')
 if source==321:
  choices=('start','stop','save');value=node.get('state')
  if type(value) is int and value in range(3):
   out['state']=choices[value];out['_stateValues']={'state':list(choices)}
   if value==2:out['type']=90314
  else:issues.append('Ungültiger OBS-Replay-Zustand.')
 if source in (5,6,1006,1007,1021,1003):
  out['_originalSemantics']={5:'randomLine',6:'program',1006:'lines',1007:'fetch',1021:'line',1003:'random'}[source]
 if source==6 and (type(node.get('waitForExit',0)) not in (int,float) or node.get('waitForExit',0)<0):issues.append('Ungültige Programm-Wartezeit.')
 if source==36:
  modes=('horizontal','vertical','both');mode=node.get('flipMode')
  if type(mode) is int and mode in range(3):out['axis']=modes[mode];fieldmap['axis']='flipMode';out['_stateValues']={'axis':list(modes)}
  else:issues.append('Ungültige OBS-Spiegelungsachse.')
 if source in (46,324,328):
  out['_originalObs']=source
  for key in (('requestType','requestData','resultVariable') if source==46 else ('resultVariable',)):out.pop(key,None)
 if source==48:out.setdefault('quality',-1)
 if source==11:
  states=('FULFILLED','CANCELED');value=node.get('status')
  if type(value) is int and value in range(2):out['status']=states[value];out['_stateValues']={'status':list(states)}
  else:issues.append('Ungültiger Redemption-Zustand.')
  out.setdefault('rewardId','%rewardId%');out.setdefault('redemptionId','%redemptionId%')
 if source==22:
  from .twitch_random_groups import validate
  from .core import ActionError
  if 'present' not in node:out['presentOnly']=True
  if type(out.get('presentOnly')) is not bool:issues.append('Present Only muss true/false sein.')
  try:validate(out)
  except ActionError as exc:issues.append(str(exc))
  out['_originalSemantics']='randomUsers'
 if source==23:
  choices=('Random','Blue','Green','Orange','Purple');value=node.get('color',0)
  if type(value) is int and value in range(5):out['color']=choices[value];out['_stateValues']={'color':list(choices)}
  else:issues.append('Ungültige Ankündigungsfarbe.')
  out['_originalSemantics']='announce'
  out.pop('preferredAccount',None)
 if source==52:out['sourceType']='User'
 if source==203:
  from .original_rewards import convert as reward_states
  try:out['rewards']=reward_states(node.get('states',{}))
  except ValueError as exc:issues.append(str(exc))
  out.pop('states',None)
 if source in (9001,9002,9003):
  out['_originalSemantics']='midi'
  out.pop('device',None)
  if source==9003:
   commands={128:'NoteOff',144:'NoteOn',176:'ControlChange',192:'PatchChange',208:'ChannelAfterTouch',224:'PitchWheelChange'}
   if type(node.get('command')) is int and node['command'] in commands:out['command']=commands[node['command']]
   else:issues.append('Original-MIDI-Befehl benötigt eine geprüfte Zuordnung.')
 if source in (121,122):
  out['_originalSemantics']='globalGet' if source==121 else 'globalSet'
  if node.get('source',0) not in (0,1,2) or node.get('destination',0) not in (0,1,2):issues.append('Unbekannter Global-Quell-/Zielmodus.')
 if source in (99903,99904):
  out['default']=source==99904;out.setdefault('values',[])
  if source==99903:out['_originalCaseIgnoreCase']=not node.get('caseSensitive',False)
 if source==4:
  if type(node.get('runImmedately',True)) is not bool:issues.append('Run Immediately muss true/false sein.')
  elif not node.get('runImmedately',True):out['_originalSemantics']='queuedAction'
 if source==16 and node.get('source',0)!=0:issues.append('Kategorie über Game-ID benötigt eine gesonderte Zuordnung.')
 if source==18:out['_originalSemantics']='clip'
 if source==10:out['_originalSemantics']='message'
 if source==16:
  out['_originalSemantics']='game'
  if node.get('source',0) in (0,1):issues=[p for p in issues if not p.startswith('Kategorie über')]
 if source==2:out.setdefault('host','255.255.255.255')
 if source==1000:
  mode=node.get('quoteType',0)
  if mode in (0,1):out['selection']='random' if mode==0 else 'specific'
  else:issues.append('Unbekannter Quote-Auswahlmodus.')
 if source==1037:out['text']='%'+node.get('quoteVariable','quote')+'%';out['_originalSemantics']='addQuote'
 if source in (1,7):
  out['volume']=float(node.get('volume',1))*100;out['_scaleValues']={'volume':100}
  out['_originalSemantics']='sound'
 if source==1024:
  for key in ('iconPath','attribution'):
   if node.get(key) is not None and not isinstance(node[key],str):issues.append('Toast-Option benötigt Text: '+key)
   out[key]=node.get(key) or ''
 if source in (502,503,504,505):out.update(sourceType='User',variable='userName')
 if source==128:
  operations=('equals','notEquals','greaterThan','lessThan');op=node.get('operation')
  if type(op) is int and op in range(4):out['operator']=operations[op];fieldmap['operator']='operation';out['_stateValues']={'operator':list(operations)}
  else:issues.append('Unbekannter While-Vergleich.')
 if source==99998 and node.get('runOnUiThread'):issues.append('C#-Ausführung auf dem Windows-UI-Thread ist unter Linux nicht verfügbar.')
 if source==1031 and not isinstance(out.get('arguments'),dict):issues.append('Signal-Argumente müssen ein JSON-Objekt sein.')
 if fieldmap:out['_fieldMap']=fieldmap
 return out,issues

def refresh(node):
 """Recheck preserved imports after an upgrade without discarding editor changes."""
 source=node.get('_original');baseline=node.get('_baseline')
 if not isinstance(source,dict) or not isinstance(baseline,dict) or source.get('type')==99999 or node.get('type')!=baseline.get('type'):return copy.deepcopy(node)
 raw=copy.deepcopy(source)
 for key,value in node.items():
  if source.get('type') in (1,7,1025) and key=='audioDevice':continue
  if key.startswith('_') or key in ('type','subActions','parentId','migrationBlock') or baseline.get(key)==value:continue
  target=node.get('_fieldMap',{}).get(key,key)
  if key in node.get('_stateValues',{}):
   try:value=node['_stateValues'][key].index(value)
   except ValueError:return copy.deepcopy(node)
  if key in node.get('_scaleValues',{}):value=value/node['_scaleValues'][key]
  if key=='obsConnection':target='connectionId';value='00000000-0000-0000-0000-000000000000' if value in ('default','__local__') else value
  if source.get('type')==203 and key=='rewards':
   from .original_rewards import original
   try:raw['states']=original(value)
   except ValueError:return copy.deepcopy(node)
   continue
  if source.get('type')==9003 and key=='command':
   value={'NoteOff':128,'NoteOn':144,'ControlChange':176,'PatchChange':192,'ChannelAfterTouch':208,'PitchWheelChange':224}.get(value,value)
  if source.get('type')==1012 and key=='keys':
   from .original_keyboard import original
   raw['key'],raw['modifiers']=original(value);continue
  if source.get('type')==1008 and key=='color':
   color=value.lstrip('#');raw.update(red=int(color[:2],16),green=int(color[2:4],16),blue=int(color[4:6],16));continue
  raw[target]=copy.deepcopy(value)
 for key in set(baseline)-set(node):
  if not key.startswith('_') and key not in ('type','subActions','parentId'):raw.pop(node.get('_fieldMap',{}).get(key,key),None)
 def prepare(raw):
  out,issues=convert(raw)
  from .obs_connections import OBS_TYPES
  if out['type'] in OBS_TYPES and 'connectionId' in out:
   connection=out.pop('connectionId');out['obsConnection']='default' if connection in ('','default','00000000-0000-0000-0000-000000000000') else connection
  out['parentId']=None
  if issues:out['_importProblems']=issues
  return out
 base=prepare(source);fresh=prepare(raw)
 from .original_exchange import fields
 fresh['_baseline']=fields(base);fresh['_original']=copy.deepcopy(source)
 if node.get('_originalAudio'):
  fresh['audioDevice']=copy.deepcopy(node.get('audioDevice',''))
  if '_originalAudioTarget' in node:fresh['_originalAudioTarget']=node['_originalAudioTarget']
 if 'subActions' in node:fresh['subActions']=copy.deepcopy(node['subActions'])
 return fresh
