"""Linux audio, notifications, MIDI and keyboard output with explicit preview mode."""
import asyncio
import os
import random
import shutil
from pathlib import Path
from .core import ActionError

async def terminate(process):
    if process.returncode is None:
        try:process.terminate()
        except ProcessLookupError:pass
        try:await asyncio.wait_for(process.wait(),2)
        except TimeoutError:process.kill();await process.wait()

async def output(engine,node,args):
    kind=node['type'];io=engine.io
    if kind in (90141,90142,90143,90144):
        sounds=getattr(io,'sounds',None)
        if sounds is None:sounds=io.sounds={}
        identity=str(node.get('playbackId','sound')).strip()
        if kind in (90143,90144):
            if io.dry_run:io.trace('sound_stop',playbackId=identity,simulated=True);return
            names=getattr(io,'sound_names',{})
            targets=[(key,process) for key,process in list(sounds.items()) if kind==90144 or key==identity or (key in names and names[key]==identity)]
            for key,process in targets:
                await terminate(process)
                if sounds.get(key) is process:sounds.pop(key,None);names.pop(key,None)
            io.trace('sound_stop',playbackId=identity,simulated=io.dry_run);return
        value=str(node.get('path','')).strip()
        if not value:raise ActionError('Sound-Pfad fehlt')
        path=Path(value).expanduser()
        if not path.is_absolute():path=io.root/path
        if kind==90142:
            if not path.is_dir():raise ActionError('Sound-Ordner fehlt')
            files=[p for p in path.iterdir() if p.is_file() and p.suffix.lower() in ('.wav','.mp3','.ogg','.flac','.m4a','.opus','.aac')]
            if not files:raise ActionError('Sound-Ordner enthält keine Audiodateien')
            path=random.choice(files)
        if not path.is_file():raise ActionError('Sound-Datei fehlt')
        volume=int(node.get('volume',100))
        if not 0<=volume<=100:raise ActionError('Sound-Lautstärke muss zwischen 0 und 100 liegen')
        io.trace('sound_play',path=str(path),playbackId=identity,simulated=io.dry_run)
        if io.dry_run:return
        binary=shutil.which('ffplay')
        if not binary:raise ActionError('Sound-Wiedergabe benötigt ffplay (ffmpeg)')
        from .audio_playback import environment
        routing=await environment(engine,node.get('audioDevice','@default'))
        if identity in sounds:await terminate(sounds[identity])
        process=await asyncio.create_subprocess_exec(binary,'-nodisp','-autoexit','-loglevel','error','-volume',str(volume),str(path),stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.PIPE,**routing)
        sounds[identity]=process
        async def finish():
            try:
                _,error=await process.communicate()
                if process.returncode not in (0,-15,-9):raise ActionError('Sound-Wiedergabe: '+error.decode(errors='replace')[-1000:])
            except asyncio.CancelledError:await terminate(process);raise
            finally:
                if sounds.get(identity) is process:sounds.pop(identity,None)
        if node.get('finishBeforeContinuing',True):await finish()
        else:
            studio=getattr(engine,'studio',None)
            if studio is None:await terminate(process);raise ActionError('Asynchrone Sound-Wiedergabe benötigt Studio-Laufzeit')
            studio.spawn(finish())
    elif kind==90145:
        io.trace('notification',title=node.get('title',''),text=node.get('text',''),simulated=io.dry_run)
        if not io.dry_run:
            studio=getattr(engine,'studio',None)
            if studio is None:raise ActionError('Benachrichtigung benötigt Studio-Laufzeit')
            await studio.notifications.show(node)
    elif kind==90146:
        from .linux_keyboard import press
        if io.dry_run:io.trace('keyboard',keys=node.get('keys'),simulated=True);return
        await press(node.get('keys',''),float(node.get('duration',100))/1000)
    else:
        messages=midi_messages(node)
        io.trace('midi',device=node.get('device',''),messages=messages,simulated=io.dry_run)
        if io.dry_run:return
        device=str(node.get('device',''))
        if not device:raise ActionError('MIDI-Gerät fehlt')
        from .midi_output import transmit
        note_off=[[0x80|(message[0]&15),message[1],0] for message in messages] if kind==90152 and node.get('sendNoteOff',True) else None
        await transmit(engine,device,messages,max(0,float(node.get('duration',500)))/1000,note_off)

def midi_messages(node):
    channel=node.get('channel',1);channels=range(16) if channel in ('',None) else [int(channel)-1]
    if any(not 0<=c<=15 for c in channels):raise ActionError('MIDI-Kanal muss 1 bis 16 sein')
    kind=node['type']
    if kind==90150:status=0xb0;data=[int(node.get('control',0)),int(node.get('value',0))]
    elif kind==90152:status=0x90;data=[int(node.get('note',60)),int(node.get('velocity',100))]
    else:
        command=node.get('command','NoteOn')
        statuses={'NoteOn':0x90,'NoteOff':0x80,'ControlChange':0xb0,'PatchChange':0xc0,'ChannelAfterTouch':0xd0,'PitchWheelChange':0xe0}
        if command not in statuses:raise ActionError('Unbekannter MIDI-Befehl')
        status=statuses[command];data=[int(node.get('data1',0))]
        if status not in (0xc0,0xd0):data.append(int(node.get('data2',0)))
    if any(not 0<=value<=127 for value in data):raise ActionError('MIDI-Daten müssen 0 bis 127 sein')
    return [[status|channel,*data] for channel in channels]
