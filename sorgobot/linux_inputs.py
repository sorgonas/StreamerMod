"""Read-only evdev inputs and incremental MIDI decoding; no input grabbing."""
import asyncio
import time
from .core import ActionError

ALIASES={'CTRL':'LEFTCTRL','CONTROL':'LEFTCTRL','SHIFT':'LEFTSHIFT','ALT':'LEFTALT','SUPER':'LEFTMETA','META':'LEFTMETA','RETURN':'ENTER'}
MODIFIERS={'LEFTCTRL':'CTRL','RIGHTCTRL':'CTRL','LEFTSHIFT':'SHIFT','RIGHTSHIFT':'SHIFT','LEFTALT':'ALT','RIGHTALT':'ALT','LEFTMETA':'SUPER','RIGHTMETA':'SUPER'}

def key_names(keys):return {ALIASES.get(k.strip().upper(),k.strip().upper()).removeprefix('KEY_') for k in keys.split('+') if k.strip()}
def matches(kind,trigger,args):
    if kind==90240:
        wanted=key_names(trigger.get('keys',''));actual=key_names(args.get('keys',''))
        def normalize(values):return {MODIFIERS.get(k,k) for k in values}
        return bool(wanted) and normalize(wanted)==normalize(actual)
    if kind in (90241,90242):return not trigger.get('button') or trigger['button']==args.get('button')
    if kind==90243:return (not trigger.get('axis') or trigger['axis']==args.get('axis')) and int(trigger.get('minValue',-32768))<=args.get('value',0)<=int(trigger.get('maxValue',32767))
    if kind==90244:return (not trigger.get('axis') or trigger['axis']==args.get('axis')) and int(trigger.get('direction',1))==args.get('value')
    if kind==90245 and trigger.get('_originalMidiFilter'):
        if trigger.get('midiEventEnabled',True) is not True:return False
        observed=args.get('data1')
        # Original's packet Data is set only for notes/controller messages;
        # patch/pressure/pitch values are separate arguments, not its Data field.
        if trigger['_originalMidiFilter']=='definition' and args.get('commandCode') in ('PatchChange','ChannelAfterTouch','PitchWheelChange'):observed=0
        try:return trigger.get('commandCode')==args.get('commandCode') and (not trigger.get('channel') or int(trigger['channel'])==args.get('channel')) and (int(trigger.get('data1',-1))<0 or int(trigger['data1'])==observed)
        except (ValueError,TypeError):return False
    if kind==90245:
        return (not trigger.get('commandCode') or trigger['commandCode']==args.get('commandCode')) and (not trigger.get('channel') or int(trigger['channel'])==args.get('channel')) and (int(trigger.get('data1',-1))<0 or int(trigger['data1'])==args.get('data1'))
    return True

class InputDecoder:
    def __init__(self):self.pressed=set()
    def feed(self,event):
        from evdev import ecodes as e
        name=e.bytype.get(event.type,{}).get(event.code,str(event.code))
        if isinstance(name,(list,tuple)):name=next((n for n in name if n in ('BTN_SOUTH','BTN_EAST','BTN_NORTH','BTN_WEST')),name[0])
        if event.type==e.EV_KEY:
            if event.value==0:self.pressed.discard(name);return []
            if event.value!=1:return []
            self.pressed.add(name)
            if name.startswith('KEY_'):
                if name.removeprefix('KEY_') in MODIFIERS:return []
                keys='+'.join(sorted(k.removeprefix('KEY_') for k in self.pressed if k.startswith('KEY_')))
                return [(90240,{'keys':keys,'key':event.code,'hasCtrl':any('CTRL' in k for k in self.pressed),'hasShift':any('SHIFT' in k for k in self.pressed),'hasAlt':any('ALT' in k for k in self.pressed)})]
            kind=90241 if event.code in range(e.BTN_MOUSE,e.BTN_JOYSTICK) else 90242
            return [(kind,{'button':name,'buttonCode':event.code,'value':event.value})]
        if event.type==e.EV_ABS:
            return [(90244 if name.startswith('ABS_HAT') else 90243,{'axis':name,'axisCode':event.code,'value':event.value})]
        if event.type==e.EV_SYN and event.code==e.SYN_DROPPED:self.pressed.clear()
        return []

class MidiDecoder:
    def __init__(self):self.status=None;self.data=[];self.sysex=False
    def feed(self,chunk):
        messages=[]
        for byte in chunk:
            if byte>=0xf8:continue # realtime can interleave any message
            if byte==0xf0:self.sysex=True;self.status=None;self.data=[];continue
            if byte==0xf7:self.sysex=False;continue
            if byte&0x80:
                self.sysex=False;self.status=byte if byte<0xf0 else None;self.data=[];continue
            if self.sysex or self.status is None:continue
            self.data.append(byte);command=self.status&0xf0;needed=1 if command in (0xc0,0xd0) else 2
            if len(self.data)<needed:continue
            data=self.data;self.data=[]
            commands={0x80:'NoteOff',0x90:'NoteOn',0xa0:'KeyAfterTouch',0xb0:'ControlChange',0xc0:'PatchChange',0xd0:'ChannelAfterTouch',0xe0:'PitchWheelChange'}
            command_name='NoteOff' if command==0x90 and data[1]==0 else commands[command]
            value=data[-1];args={'commandCode':command_name,'commandCodeNum':self.status,'channel':(self.status&15)+1,'data1':data[0],'data2':data[1] if needed==2 else 0,'value':value,'valueNormal':value/127,'rawMessage':bytes([self.status,*data]).hex(),'timestamp':int(time.time()*1000)}
            if command in (0x80,0x90,0xa0):args.update(noteNumber=data[0],noteName=('C','C#','D','D#','E','F','F#','G','G#','A','A#','B')[data[0]%12]+str(data[0]//12-1),velocity=value,velocityNormal=value/127)
            if command==0xb0:args['controllerNumber']=data[0]
            if command==0xe0:args.update(value=data[0]+(data[1]<<7),valueNormal=(data[0]+(data[1]<<7))/16383)
            messages.append(args)
        return messages

class DeviceListeners:
    def __init__(self,studio):self.studio=studio;self.tasks={};self.active=set();self.errors={};from collections import deque;self.messages=deque(maxlen=100)
    async def input(self,item):
        from evdev import InputDevice
        device=InputDevice(item['path']);decoder=InputDecoder()
        try:
            async for event in device.async_read_loop():
                for kind,args in decoder.feed(event):
                    self.studio.engine.core_events.emit(kind,dict(args,inputDeviceId=item['id'],inputDeviceName=item['name']),inputDeviceId=item['id'])
        finally:device.close()
    async def midi(self,item):
        from .linux_midi import RawMidiInput
        device=RawMidiInput(item['device']);decoder=MidiDecoder();self.active.add(item['id']);self.errors.pop(item['id'],None)
        try:
            while True:
                for args in decoder.feed(device.read()):
                    self.messages.append({'deviceId':item['id'],'deviceName':item['name'],'message':dict(args)})
                    self.studio.engine.core_events.emit(90245,dict(args,midiDeviceId=item['id'],deviceName=item['name'],name=item['name']),midiDeviceId=item['id'])
                await asyncio.sleep(.01)
        finally:self.active.discard(item['id']);device.close()
    async def run_device(self,section,item):
        while True:
            try:await (self.input(item) if section=='inputDevices' else self.midi(item))
            except (OSError,ActionError) as error:
                self.errors[item['id']]=str(error);self.studio.io.trace('device_error',name=item['name'],error=str(error))
                if section=='midiDevices' and not item.get('reconnect',True):return
                await asyncio.sleep(10)
    async def run(self):
        try:
            while True:
                wanted={(section,i['id']):i for section in ('inputDevices','midiDevices') for i in self.studio.core_services.config[section] if i.get('enabled',True) and (section!='midiDevices' or i.get('listen',True))}
                for key,(definition,task) in list(self.tasks.items()):
                    if wanted.get(key)!=definition:task.cancel();await asyncio.gather(task,return_exceptions=True);self.tasks.pop(key)
                for key,item in wanted.items():
                    if key not in self.tasks:
                        import copy
                        self.tasks[key]=(copy.deepcopy(item),asyncio.create_task(self.run_device(key[0],copy.deepcopy(item))))
                await asyncio.sleep(.25)
        finally:
            tasks=[task for _,task in self.tasks.values()]
            for task in tasks:task.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)
