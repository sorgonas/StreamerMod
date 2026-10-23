"""Global hotkeys via XDG desktop portal, including Wayland/KDE."""
import asyncio
import uuid
from dbus_next.aio import MessageBus
from dbus_next import Message,MessageType,Variant
from .core import ActionError
from .linux_inputs import key_names,MODIFIERS

DEST='org.freedesktop.portal.Desktop';PATH='/org/freedesktop/portal/desktop';IFACE='org.freedesktop.portal.GlobalShortcuts'
def preferred(keys):
    parts=[];names=key_names(keys)
    for name in sorted(names):
        if name in MODIFIERS:parts.append({'CTRL':'CTRL','SHIFT':'SHIFT','ALT':'ALT','SUPER':'LOGO'}[MODIFIERS[name]])
        else:parts.append({'ENTER':'Return','ESC':'Escape','SPACE':'space'}.get(name,name))
    return '+'.join(parts)

class Hotkeys:
    def __init__(self,studio):self.studio=studio;self.bus=None;self.session=None;self.requests={};self.shortcuts={}
    def signal(self,message):
        if message.message_type!=MessageType.SIGNAL:return
        if message.interface=='org.freedesktop.portal.Request' and message.member=='Response':
            future=self.requests.get(message.path)
            if future and not future.done():future.set_result(message.body)
        if message.interface==IFACE and message.member=='Activated' and message.body[0]==self.session:
            keys=self.shortcuts.get(message.body[1])
            if keys:
                names=key_names(keys)
                self.studio.engine.core_events.emit(90240,{'keys':keys,'inputDeviceId':'','inputDeviceName':'Desktop Portal','hasCtrl':any('CTRL' in n for n in names),'hasAlt':any('ALT' in n for n in names),'hasShift':any('SHIFT' in n for n in names)},inputDeviceId='')
    async def request(self,member,signature,body,options):
        token='sorgobot_'+uuid.uuid4().hex;options['handle_token']=Variant('s',token)
        path='/org/freedesktop/portal/desktop/request/'+self.bus.unique_name[1:].replace('.','_')+'/'+token
        future=asyncio.get_running_loop().create_future();self.requests[path]=future
        try:
            reply=await self.bus.call(Message(destination=DEST,path=PATH,interface=IFACE,member=member,signature=signature,body=body))
            if reply.message_type==MessageType.ERROR:raise ActionError(str(reply.body))
            response,results=await future
            if response!=0:raise ActionError('Hotkey-Freigabe wurde abgebrochen oder abgelehnt')
            return results
        finally:
            self.requests.pop(path,None)
            if not future.done():
                await self.bus.call(Message(destination=DEST,path=path,interface='org.freedesktop.portal.Request',member='Close'))
    async def close_session(self):
        if self.session:
            await self.bus.call(Message(destination=DEST,path=self.session,interface='org.freedesktop.portal.Session',member='Close'))
            self.session=None
        self.shortcuts={}
    async def bind(self,shortcuts):
        if self.bus is None:
            self.bus=await MessageBus().connect();self.bus.add_message_handler(self.signal)
            await self.bus.call(Message(destination='org.freedesktop.DBus',path='/org/freedesktop/DBus',interface='org.freedesktop.DBus',member='AddMatch',signature='s',body=["type='signal',sender='org.freedesktop.portal.Desktop'"]))
        await self.close_session()
        options={'session_handle_token':Variant('s','sorgobot_'+uuid.uuid4().hex)}
        results=await self.request('CreateSession','a{sv}',[options],options)
        self.session=results['session_handle'].value;options={}
        self.shortcuts={identity:keys for identity,keys,_ in shortcuts}
        rows=[[identity,{'description':Variant('s',description),'preferred_trigger':Variant('s',preferred(keys))}] for identity,keys,description in shortcuts]
        await self.request('BindShortcuts','oa(sa{sv})sa{sv}',[self.session,rows,'',options],options)
    def definitions(self):
        return tuple(sorted({(t['id'],t.get('keys',''),a['name']) for a in self.studio.engine.actions.values() if a.get('enabled',True) for t in a.get('triggers',[]) if t['type']==90240 and t.get('enabled',True) and not t.get('inputDeviceId') and t.get('keys')}))
    async def run(self):
        previous=()
        try:
            while True:
                wanted=self.definitions()
                if wanted!=previous:
                    previous=wanted
                    try:
                        if wanted:await self.bind(wanted)
                        elif self.bus:await self.close_session()
                    except (ActionError,OSError) as error:self.studio.io.trace('hotkey_error',error=str(error))
                await asyncio.sleep(.5)
        finally:
            if self.bus:
                await self.close_session();self.bus.disconnect();self.bus=None
