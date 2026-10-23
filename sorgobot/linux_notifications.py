"""Freedesktop notifications with action activation on the session bus."""
import asyncio
from dbus_next.aio import MessageBus
from dbus_next import Message,MessageType
from .core import ActionError

class Notifications:
    def __init__(self,studio):self.studio=studio;self.bus=None;self.pending={}
    async def connect(self):
        if self.bus:return
        self.bus=await MessageBus().connect();self.bus.add_message_handler(self.signal)
        reply=await self.bus.call(Message(destination='org.freedesktop.DBus',path='/org/freedesktop/DBus',interface='org.freedesktop.DBus',member='AddMatch',signature='s',body=["type='signal',interface='org.freedesktop.Notifications'"]))
        if reply.message_type==MessageType.ERROR:raise ActionError(str(reply.body))
    def signal(self,message):
        if message.message_type!=MessageType.SIGNAL or message.interface!='org.freedesktop.Notifications':return
        if message.member=='NotificationClosed':self.pending.pop(message.body[0],None)
        if message.member=='ActionInvoked':
            identity,action=message.body;args=self.pending.get(identity)
            if args:self.studio.engine.core_events.emit(90251,dict(args,activationAction=action),toastId=args['toast.id'])
    async def show(self,node):
        await self.connect()
        text=str(node.get('text',''))
        if node.get('attribution'):text+='\n'+str(node['attribution'])
        reply=await self.bus.call(Message(destination='org.freedesktop.Notifications',path='/org/freedesktop/Notifications',interface='org.freedesktop.Notifications',member='Notify',signature='susssasa{sv}i',body=['Sorgobot',0,str(node.get('iconPath') or ''),str(node.get('title','Sorgobot')),text,['default',str(node.get('activationLabel','Open'))],{},5000]))
        if reply.message_type==MessageType.ERROR:raise ActionError('Desktop-Benachrichtigung: '+str(reply.body))
        self.pending[reply.body[0]]={'toast.id':str(node.get('toastId','')),'toast.title':str(node.get('title','')),'toast.message':str(node.get('text',''))}
    def close(self):
        if self.bus:self.bus.disconnect();self.bus=None
        self.pending.clear()
