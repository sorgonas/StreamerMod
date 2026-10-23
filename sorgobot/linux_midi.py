"""Native ALSA RawMIDI through the system libasound, without development packages."""
import asyncio
import ctypes as c
import ctypes.util
import errno
from pathlib import Path
from .core import ActionError

def devices():return [str(path) for path in sorted(Path('/dev/snd').glob('midiC*D*'))]

class RawMidi:
    def __init__(self,device):
        library=c.util.find_library('asound')
        if not library:raise ActionError('ALSA libasound fehlt')
        self.lib=c.CDLL(library);self.handle=c.c_void_p()
        self.lib.snd_rawmidi_open.argtypes=[c.c_void_p,c.POINTER(c.c_void_p),c.c_char_p,c.c_int];self.lib.snd_rawmidi_open.restype=c.c_int
        self.lib.snd_rawmidi_write.argtypes=[c.c_void_p,c.c_void_p,c.c_size_t];self.lib.snd_rawmidi_write.restype=c.c_ssize_t
        self.lib.snd_rawmidi_drain.argtypes=[c.c_void_p];self.lib.snd_rawmidi_drain.restype=c.c_int
        self.lib.snd_rawmidi_close.argtypes=[c.c_void_p];self.lib.snd_rawmidi_close.restype=c.c_int
        self.lib.snd_strerror.argtypes=[c.c_int];self.lib.snd_strerror.restype=c.c_char_p
        import re
        match=re.fullmatch(r'/dev/snd/midiC(\d+)D(\d+)',device)
        if match:device='hw:'+match[1]+','+match[2]
        result=self.lib.snd_rawmidi_open(None,c.byref(self.handle),device.encode(),1) # ALSA nonblocking
        if result<0:raise ActionError('MIDI-Gerät kann nicht geöffnet werden: '+self.lib.snd_strerror(result).decode())
    async def send(self,message):
        data=bytes(message);deadline=asyncio.get_running_loop().time()+3
        while data:
            result=self.lib.snd_rawmidi_write(self.handle,data,len(data))
            if result==-errno.EAGAIN or result==0:
                if asyncio.get_running_loop().time()>=deadline:raise ActionError('MIDI-Gerät antwortet nicht')
                await asyncio.sleep(.01);continue
            if result<0:raise ActionError('MIDI-Ausgabe: '+self.lib.snd_strerror(result).decode())
            data=data[result:]
    async def drain(self):
        deadline=asyncio.get_running_loop().time()+3
        while True:
            result=self.lib.snd_rawmidi_drain(self.handle)
            if result==0:return
            if result==-errno.EAGAIN:
                if asyncio.get_running_loop().time()>=deadline:raise ActionError('MIDI-Ausgabe wurde nicht vollständig übertragen')
                await asyncio.sleep(.01);continue
            raise ActionError('MIDI-Ausgabe: '+self.lib.snd_strerror(result).decode())
    def close(self):
        if self.handle:self.lib.snd_rawmidi_close(self.handle);self.handle=None

class RawMidiInput(RawMidi):
    def __init__(self,device):
        library=c.util.find_library('asound')
        if not library:raise ActionError('ALSA libasound fehlt')
        self.lib=c.CDLL(library);self.handle=c.c_void_p()
        self.lib.snd_rawmidi_open.argtypes=[c.POINTER(c.c_void_p),c.c_void_p,c.c_char_p,c.c_int];self.lib.snd_rawmidi_open.restype=c.c_int
        self.lib.snd_rawmidi_read.argtypes=[c.c_void_p,c.c_void_p,c.c_size_t];self.lib.snd_rawmidi_read.restype=c.c_ssize_t
        self.lib.snd_rawmidi_close.argtypes=[c.c_void_p];self.lib.snd_rawmidi_close.restype=c.c_int
        self.lib.snd_strerror.argtypes=[c.c_int];self.lib.snd_strerror.restype=c.c_char_p
        import re
        match=re.fullmatch(r'/dev/snd/midiC(\d+)D(\d+)',device)
        if match:device='hw:'+match[1]+','+match[2]
        result=self.lib.snd_rawmidi_open(c.byref(self.handle),None,device.encode(),1)
        if result<0:raise ActionError('MIDI-Eingang: '+self.lib.snd_strerror(result).decode())
    def read(self):
        data=c.create_string_buffer(4096);result=self.lib.snd_rawmidi_read(self.handle,data,len(data))
        if result==-errno.EAGAIN:return b''
        if result<0:raise ActionError('MIDI-Eingang: '+self.lib.snd_strerror(result).decode())
        return data.raw[:result]
