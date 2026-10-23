"""CPH MIDI endpoints and Original 1.0.7 channel message conventions."""
import copy
import uuid
from .core import ActionError
from .midi_output import transmit


def definitions(engine):
    services=getattr(engine,'services',None)
    rows=services.config.get('midiDevices',[]) if services else []
    if not isinstance(rows,list):raise ActionError('Ungültige MIDI-Konfiguration')
    result=[];seen=set()
    for row in rows:
        try:
            if not isinstance(row,dict) or not isinstance(row.get('name'),str):raise ValueError()
            identity=str(uuid.UUID(row['id']))
            if identity in seen:raise ValueError()
        except (ValueError,TypeError,KeyError,AttributeError):raise ActionError('MIDI-Einträge benötigen eindeutige GUID-IDs und Namen') from None
        seen.add(identity);result.append((identity,row))
    return result

async def rpc(engine,method,values):
    rows=definitions(engine)
    if method=='midi_devices':return [{'id':identity,'name':row['name']} for identity,row in rows]
    if method!='midi_send' or len(values)!=7:raise ActionError('Ungültiger C#-MIDI-Aufruf')
    identity,command,channel,data1,data2,duration,noteoff=values
    if any(type(value) is not int for value in (command,channel,data1,data2,duration)) or type(noteoff) is not bool:raise ActionError('Ungültige MIDI-Datentypen')
    if not (0<=command<=255 and 1<=channel<=16 and 0<=data1<=127 and 0<=data2<=127):return None
    try:identity=str(uuid.UUID(identity))
    except (ValueError,TypeError,AttributeError):raise ActionError('Ungültige MIDI-Geräte-ID') from None
    row=next((row for key,row in rows if key==identity),None)
    if row is None or not row.get('enabled',True):return None
    item=copy.deepcopy(row);device=item.get('device','')
    if not isinstance(device,str) or not device.strip():raise ActionError('MIDI-Gerät fehlt')
    if command not in (128,144,176,192,208,224):return None
    if duration<0:raise ActionError('MIDI-Dauer darf nicht negativ sein')
    status=command|(channel-1)
    # Original's PitchWheelChangeEvent receives only data1, ignoring data2.
    message=[status,data1,0] if command==224 else [status,data1] if command in (192,208) else [status,data1,data2]
    off=[[0x80|(channel-1),data1,0]] if command==144 and noteoff else None
    engine.io.trace('midi',device=device,messages=[message],simulated=engine.io.dry_run)
    if engine.io.dry_run:return None
    def check():
        if not any(key==identity and current==item for key,current in definitions(engine)):raise ActionError('MIDI-Konfiguration während des Aufrufs geändert')
    await transmit(engine,device,[message],duration/1000,off,check)
    return None
