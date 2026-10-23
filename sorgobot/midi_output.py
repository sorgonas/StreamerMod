"""Scoped ALSA output transactions shared by native and CPH actions."""
import asyncio
from .core import ActionError

async def transmit(engine,device,messages,duration=0,note_off=None,check=None):
    if engine.io.dry_run:return
    if not hasattr(engine.io,'midi_output_locks'):engine.io.midi_output_locks={}
    lock=engine.io.midi_output_locks.setdefault(device,asyncio.Lock())
    async with lock:
        if getattr(getattr(engine,'studio',None),'closing',False):raise ActionError('MIDI-Laufzeit wird beendet')
        if check:check()
        from .linux_midi import RawMidi
        midi=RawMidi(device)
        try:
            try:
                for message in messages:await midi.send(message)
                if note_off:await asyncio.sleep(duration)
            finally:
                if note_off:
                    for message in note_off:await midi.send(message)
        finally:
            try:await midi.drain()
            finally:midi.close()
