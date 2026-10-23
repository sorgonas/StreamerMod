"""Human-readable criteria for trigger tables."""
from .core_services import read_config

def selection(trigger,store):
    for key in ('sourceName','inputName','filterName','commandId','rewardId','sceneName','timerId','fileTailId','voiceCommandId','watcherId','processName','eventName','groupId','inputDeviceId','midiDeviceId','connectionId','scheduleId','variableName','keys','button','axis','toastId'):
        if key not in trigger:continue
        value=trigger[key]
        if not value:return 'Any'
        if key=='commandId':items=store.read('commands.json')['commands']
        elif key=='timerId':items=store.read('timers.json')
        elif key in ('fileTailId','voiceCommandId','watcherId','groupId','inputDeviceId','midiDeviceId','connectionId','scheduleId'):
            items=read_config(store.root)[{'fileTailId':'fileTails','voiceCommandId':'voiceCommands','watcherId':'fileWatchers','groupId':'userGroups','inputDeviceId':'inputDevices','midiDeviceId':'midiDevices','connectionId':'websocketConnections','scheduleId':'cronSchedules'}[key]]
        else:return str(value)
        return next((item['name'] for item in items if item['id']==value),'Missing: '+str(value))
    return 'Any'

def criteria(trigger,store):
    base=selection(trigger,store);kind=trigger['type'];details=[]
    if 94050<=kind<=94058:
        return ' / '.join(str(trigger[k]) for k in ('audioKind','audioTarget') if trigger.get(k) not in ('',None,'any')) or ('Audiodienst' if kind in (94050,94051) else 'Alle Audioziele')
    if 93050<=kind<=93058:
        parts=[]
        for key,label in [('buttonId','Button'),('deviceId','Gerät'),('state','Zustand')]:
            if trigger.get(key) not in ('',None):parts.append(label+': '+str(trigger[key]))
        if trigger.get('direction') not in (None,'','any'):parts.append({'clockwise':'Im Uhrzeigersinn','counterclockwise':'Gegen den Uhrzeigersinn'}.get(trigger['direction'],trigger['direction']))
        return ' / '.join(parts) or ('Plugin-Verbindung' if kind in (93050,93051) else 'Alle Belegungen')
    if kind==97250:return ' / '.join([trigger.get('instanceId') or 'Alle Instanzen',trigger.get('eventName') or 'Alle Ereignisse'])
    if kind==97050:return trigger.get('webhookName') or 'Alle Webhooks'
    if kind==90240:details=[trigger.get('keys','')]
    elif kind in (90241,90242):details=[trigger.get('button','')]
    elif kind==90243:details=[trigger.get('axis',''),str(trigger.get('minValue',0))+' … '+str(trigger.get('maxValue',0))]
    elif kind==90244:details=[trigger.get('axis',''),str(trigger.get('direction',0))]
    elif kind==90245:
        details=[trigger.get('commandCode') or 'Any Message']
        if trigger.get('channel'):details.append('Channel '+str(trigger['channel']))
        if trigger.get('data1',-1)>=0:details.append('Data1 '+str(trigger['data1']))
    elif kind in (90220,90221,90222,90223):details=['Persisted '+{True:'Yes',False:'No','either':'Either'}.get(trigger.get('persisted','either'),'Either')]
    return ' / '.join([base,*[d for d in details if d]])
