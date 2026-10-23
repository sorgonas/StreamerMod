"""Keyboard shortcuts through the desktop's available Linux backend."""
import asyncio
import os
import shutil
from .core import ActionError

async def press(keys,duration):
    if not 0<=duration<=10:raise ActionError('Tastendauer muss 0 bis 10 Sekunden sein')
    names=[k.strip().upper() for k in keys.split('+') if k.strip()]
    if not names:raise ActionError('Tastenkombination fehlt')
    aliases={'CTRL':'LEFTCTRL','CONTROL':'LEFTCTRL','ALT':'LEFTALT','SHIFT':'LEFTSHIFT','SUPER':'LEFTMETA','META':'LEFTMETA','RETURN':'ENTER','ESC':'ESC','SPACE':'SPACE'}
    try:
        from evdev import UInput,ecodes
        codes=[]
        for name in names:
            code=getattr(ecodes,'KEY_'+aliases.get(name,name),None)
            if code is None:raise ActionError('Unbekannte Taste: '+name)
            codes.append(code)
        device=UInput({ecodes.EV_KEY:codes},name='Sorgobot Keyboard')
    except (ImportError,OSError):
        if os.environ.get('XDG_SESSION_TYPE')=='wayland':raise ActionError('Wayland-Tastaturausgabe benötigt Zugriff auf /dev/uinput (evdev).') from None
        binary=shutil.which('xdotool')
        if not binary:raise ActionError('Tastaturausgabe benötigt evdev/uinput oder xdotool unter X11') from None
        shortcut='+'.join({'CTRL':'ctrl','SHIFT':'shift','ALT':'alt','SUPER':'super','ENTER':'Return','ESC':'Escape'}.get(n,n.lower() if len(n)==1 else n) for n in names)
        process=await asyncio.create_subprocess_exec(binary,'keydown','--clearmodifiers',shortcut,stderr=asyncio.subprocess.PIPE)
        _,error=await process.communicate()
        if process.returncode:raise ActionError('Tastaturausgabe: '+error.decode(errors='replace'))
        try:await asyncio.sleep(duration)
        finally:
            process=await asyncio.create_subprocess_exec(binary,'keyup',shortcut);await process.wait()
        return
    try:
        for code in codes:device.write(ecodes.EV_KEY,code,1)
        device.syn();await asyncio.sleep(duration)
    finally:
        for code in reversed(codes):device.write(ecodes.EV_KEY,code,0)
        device.syn();device.close()
