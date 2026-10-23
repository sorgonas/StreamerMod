"""CPH playback on Linux, sharing the native active-process registry."""
import asyncio
from asyncio import create_subprocess_exec as launch_process
import math
import random
import shutil
import uuid
import wave
from pathlib import Path
from .core import ActionError
from .linux_core_io import terminate

EXTENSIONS={'.wav','.mp3','.ogg','.flac','.m4a','.opus','.aac'}

async def duration_ms(path):
    if path.suffix.lower()=='.wav':
        try:
            def read_wave():
                with wave.open(str(path),'rb') as sound:return sound.getnframes()/sound.getframerate()*1000
            return await asyncio.to_thread(read_wave)
        except (wave.Error,EOFError):pass
    binary=shutil.which('ffprobe')
    if not binary:raise ActionError('Sound-Dauer benötigt ffprobe (ffmpeg)')
    process=await launch_process(binary,'-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',str(path),stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
    try:
        output,_=await asyncio.wait_for(process.communicate(),10)
        try:value=float(output.decode().strip())*1000
        except ValueError:raise ActionError('Sound-Dauer kann nicht gelesen werden') from None
        if process.returncode or not math.isfinite(value) or value<0:raise ActionError('Sound-Dauer kann nicht gelesen werden')
        return value
    finally:
        if process.returncode is None:await terminate(process)

async def close_players(io):
    # Also reap a process whose background task was cancelled before its first step.
    sounds=getattr(io,'sounds',{});names=getattr(io,'sound_names',{})
    for identity,process in list(sounds.items()):
        await terminate(process)
        if sounds.get(identity) is process:sounds.pop(identity,None);names.pop(identity,None)

async def rpc(engine,method,values,*,audio_device='@default'):
    io=engine.io
    if method in ('sound_stop','sound_stop_all'):
        name=values[0] if method=='sound_stop' else None
        if name is not None and not isinstance(name,str):raise ActionError('Ungültiger Sound-Name')
        if name is not None and not name.strip():name=None
        if io.dry_run:io.trace('sound_stop',name=name,all=method=='sound_stop_all',simulated=True);return None
        sounds=getattr(io,'sounds',{});names=getattr(io,'sound_names',{})
        targets=[(identity,process) for identity,process in list(sounds.items()) if method=='sound_stop_all' or (identity in names and names[identity]==name) or (name is not None and identity==name)]
        for identity,process in targets:
            await terminate(process)
            if sounds.get(identity) is process:sounds.pop(identity,None);names.pop(identity,None)
        return None
    if method!='sound_play' or len(values)!=7:raise ActionError('Ungültiger C#-Sound-Aufruf')
    mode,value,volume,recursive,finish,name,use_filename=values
    if mode not in ('file','folder'):raise ActionError('Unbekannte Sound-Quelle')
    if value is None or not isinstance(value,str) or not value.strip():return 0.0
    path=Path(value).expanduser()
    if not path.is_absolute():path=io.root/path
    if mode=='folder':
        if not path.is_dir():return 0.0
        def candidates():return [p for p in (path.rglob('*') if recursive else path.iterdir()) if p.is_file() and p.suffix.lower() in EXTENSIONS]
        files=await asyncio.to_thread(candidates)
        if not files:return 0.0
        path=random.choice(files)
    elif not path.is_file():return 0.0
    if not isinstance(volume,(int,float)) or isinstance(volume,bool) or not math.isfinite(volume) or not 0<=volume<=1:raise ActionError('Sound-Lautstärke muss zwischen 0 und 1 liegen')
    if name is not None and not isinstance(name,str):raise ActionError('Ungültiger Sound-Name')
    # 1.0.7 overrides the file name for PlaySound; the folder wrapper discards its computed stem.
    if mode=='file' and use_filename:name=path.stem
    if name is not None and not name.strip():name=None
    duration=await duration_ms(path)
    io.trace('sound_play',path=str(path),name=name,simulated=io.dry_run)
    if io.dry_run:return duration
    studio=getattr(engine,'studio',None)
    if studio is None or getattr(studio,'closing',False):raise ActionError('Sound-Wiedergabe benötigt aktive Studio-Laufzeit')
    binary=shutil.which('ffplay')
    if not binary:raise ActionError('Sound-Wiedergabe benötigt ffplay (ffmpeg)')
    from .audio_playback import environment
    routing=await environment(engine,audio_device)
    process=await launch_process(binary,'-nodisp','-autoexit','-loglevel','error','-af','volume='+str(volume),str(path),stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.PIPE,**routing)
    identity='csharp:'+uuid.uuid4().hex
    if not hasattr(io,'sounds'):io.sounds={}
    if not hasattr(io,'sound_names'):io.sound_names={}
    io.sounds[identity]=process;io.sound_names[identity]=name
    async def completed():
        try:
            _,error=await process.communicate()
            if process.returncode not in (0,-15,-9):raise ActionError('Sound-Wiedergabe: '+error.decode(errors='replace')[-1000:])
        finally:
            if process.returncode is None:await terminate(process)
            if io.sounds.get(identity) is process:io.sounds.pop(identity,None)
            io.sound_names.pop(identity,None)
    if finish:await completed()
    else:
        job=completed()
        try:studio.spawn(job)
        except BaseException:
            job.close();await terminate(process);io.sounds.pop(identity,None);io.sound_names.pop(identity,None);raise
    return duration
