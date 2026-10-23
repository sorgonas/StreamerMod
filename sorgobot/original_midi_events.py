"""Migrate Original MIDI-event references using verified definitions or native templates."""
import copy,json
from .original_graph import canonical,ZERO
COMMANDS={128:'NoteOff',144:'NoteOn',160:'KeyAfterTouch',176:'ControlChange',192:'PatchChange',208:'ChannelAfterTouch',224:'PitchWheelChange'}
FIELDS=('commandCode','channel','data1','midiEventEnabled','midiDeviceId')

def definition(row):
 if not isinstance(row,dict) or not canonical(row.get('id')):raise ValueError('MIDI-Ereignis benötigt eine gültige ID.')
 allowed={'id','name','enabled','commandCode','channel','ignoreChannel','data1','ignoreData1'}
 if set(row)-allowed:raise ValueError('Unbekannte Original-MIDI-Ereignisfelder: '+', '.join(sorted(set(row)-allowed)))
 command=row.get('commandCode',0);channel=row.get('channel',0);data=row.get('data1',0)
 if type(command) is not int or command not in COMMANDS:raise ValueError('Ungültiger Original-MIDI-Befehl.')
 if any(type(row.get(key,False)) is not bool for key in ('enabled','ignoreChannel','ignoreData1')):raise ValueError('Ungültiger MIDI-Ereignis-Schalter.')
 if type(channel) is not int or not row.get('ignoreChannel',False) and not 1<=channel<=16:raise ValueError('MIDI-Kanal muss zwischen 1 und 16 liegen.')
 if type(data) is not int or not row.get('ignoreData1',False) and not 0<=data<=127:raise ValueError('MIDI Data1 muss zwischen 0 und 127 liegen.')
 return {'commandCode':COMMANDS[command],'channel':0 if row.get('ignoreChannel',False) else channel,'data1':-1 if row.get('ignoreData1',False) else data,'midiEventEnabled':row.get('enabled',False)}

def load_config(raw):
 if isinstance(raw,str):raw=raw.encode()
 if len(raw)>16*1024*1024:raise ValueError('MIDI-Konfiguration zu groß.')
 data=json.loads(raw.decode('utf-8-sig'))
 if not isinstance(data,dict) or not isinstance(data.get('inDevices'),list):raise ValueError('Original-MIDI-Konfiguration mit inDevices erwartet.')
 result={}
 for device in data['inDevices']:
  if not isinstance(device,dict) or not canonical(device.get('id')) or not isinstance(device.get('events'),list):raise ValueError('Ungültiger Original-MIDI-Eingang.')
  key=canonical(device['id'])
  if key in result:raise ValueError('Doppelte MIDI-Geräte-ID.')
  events={}
  for row in device['events']:
   definition(row);identity=canonical(row['id'])
   if identity in events:raise ValueError('Doppelte MIDI-Ereignis-ID.')
   events[identity]=copy.deepcopy(row)
  result[key]=events
 return result

def templates(document):
 return [(a,t) for a in document.get('actions',[]) if not a.get('migrationBlock') for t in a.get('triggers',[]) if t.get('type')==90245]

def apply(trigger,document,resources,bindings):
 out=copy.deepcopy(trigger);source=out.pop('midiEvent',ZERO)
 if not canonical(source):raise ValueError('Ungültige Original-MIDI-Ereignis-ID.')
 device=out.get('midiDeviceId','');origin=canonical(device)
 if not origin:raise ValueError('Ungültige Original-MIDI-Geräte-ID.')
 out['midiDeviceId']='' if origin==ZERO else bindings.get('midiInputs',{}).get(origin,device)
 if origin!=ZERO:
  rows=[d for d in resources.get('midiDevices',[]) if canonical(d.get('id'))==canonical(out['midiDeviceId']) and d.get('enabled',True) and d.get('listen',True) and d.get('device')]
  if len(rows)!=1:raise ValueError('Original-MIDI-Eingang einem eingerichteten Linux-Eingang zuordnen: '+origin)
  out['midiDeviceId']=rows[0]['id']
 if canonical(source)!=ZERO:
  data=bindings.get('midiDefinitions',{}).get(origin,{}).get(canonical(source))
  if data is not None:filters=definition(data)
  else:
   target=bindings.get('midiEvents',{}).get(canonical(source))
   found=[t for _,t in templates(document) if canonical(t.get('id'))==canonical(target)]
   if len(found)!=1:raise ValueError('Gespeichertes MIDI-Ereignis zuordnen oder Original-MIDI-Konfiguration laden: '+source)
   row=found[0]
   if row.get('midiDeviceId') not in ('',None,out['midiDeviceId']):raise ValueError('MIDI-Ereignis und zugeordneter Eingang gehören zu verschiedenen Geräten.')
   command=row.get('commandCode');reverse={v:k for k,v in COMMANDS.items()}
   if command not in reverse:raise ValueError('Als MIDI-Vorlage einen konkreten Command Type wählen.')
   filters=definition({'id':source,'commandCode':reverse[command],'channel':row.get('channel',0),'ignoreChannel':row.get('channel',0)==0,'data1':row.get('data1',-1),'ignoreData1':row.get('data1',-1)==-1,'enabled':row.get('midiEventEnabled',True)})
  out.update(filters);out['_originalMidiFilter']='definition' if data is not None else 'template'
 out['_originalMidiBaseline']={key:copy.deepcopy(out.get(key)) for key in FIELDS}
 return out
