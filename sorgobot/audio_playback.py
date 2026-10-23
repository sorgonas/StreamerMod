"""Per-player PulseAudio routing; no global default-device changes."""
import os
from .core import ActionError

async def environment(engine,target):
 if target=='@default':return {}
 if not isinstance(target,str) or not target.strip() or len(target)>500 or any(ord(c)<32 for c in target):raise ActionError('Ungültiger Audio-Ausgang.')
 audio=getattr(getattr(engine,'studio',None),'audio',None)
 if audio is None:raise ActionError('Audio-Geräteabfrage ist nicht verfügbar.')
 rows=await audio.snapshot()
 if len([r for r in rows if r.get('kind')=='output' and r.get('name')==target])!=1:raise ActionError('Gewünschter Audio-Ausgang ist nicht eindeutig verbunden: '+target)
 return {'env':{**os.environ,'SDL_AUDIODRIVER':'pulseaudio','PULSE_SINK':target}}
