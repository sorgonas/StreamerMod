"""Configured WebSocket clients and localhost custom servers, with clean reload."""
import asyncio
import copy
import uuid
import aiohttp
from aiohttp import web
from .core import ActionError

class Connections:
    def __init__(self,studio):self.studio=studio;self.tasks={};self.sockets={};self.failed={};self.manual={};self.listeners={};self.lock=asyncio.Lock();self.closing=False
    def event(self,kind,item,**args):
        if kind in (90263,90264,90265) and 'clientId' in args:args['sessionId']=args['clientId']
        self.studio.engine.core_events.emit(kind,dict(args,connectionId=item['id'],connectionName=item['name']),connectionId=item['id'])
    async def receive(self,ws,item,client_id,server=False):
        self.sockets.setdefault(item['id'],{})[client_id]=ws
        self.event(90263 if server else 90260,item,clientId=client_id)
        try:
            async for msg in ws:
                if msg.type==aiohttp.WSMsgType.TEXT:self.event(90265 if server else 90262,item,clientId=client_id,message=msg.data,rawInput=msg.data)
                elif msg.type==aiohttp.WSMsgType.ERROR:break
        finally:
            self.sockets.get(item['id'],{}).pop(client_id,None)
            self.event(90264 if server else 90261,item,clientId=client_id)
    async def client(self,item):
        while True:
            try:
                async with self.studio.session.ws_connect(item['url'],heartbeat=30,max_msg_size=65536,compress=15 if item.get('enableCompression',False) else 0) as ws:
                    self.failed.pop(item['id'],None);await self.receive(ws,item,'remote')
            except (aiohttp.ClientError,TimeoutError,OSError,ValueError) as error:
                message=str(error)
                if self.failed.get(item['id'])!=message:self.studio.io.trace('websocket_error',name=item['name'],error=message);self.failed[item['id']]=message
            if not item.get('reconnect',True):
                self.manual[item['id']]=(copy.deepcopy(item),False);break
            await asyncio.sleep(max(1,float(item.get('retryInterval',3))))
    async def server(self,item):
        async def handler(request):
            ws=web.WebSocketResponse(heartbeat=30,max_msg_size=65536);await ws.prepare(request)
            await self.receive(ws,item,uuid.uuid4().hex,True);return ws
        app=web.Application();app.router.add_get(item.get('endpoint') or '/ws',handler);runner=web.AppRunner(app)
        await runner.setup()
        try:
            await web.TCPSite(runner,'127.0.0.1',int(item['port'])).start()
            self.listeners[item['id']]=copy.deepcopy(item)
            await asyncio.Future()
        finally:
            self.listeners.pop(item['id'],None)
            await runner.cleanup()
    async def server_retry(self,item):
        while True:
            try:await self.server(item)
            except (OSError,ValueError) as error:
                self.studio.io.trace('websocket_error',name=item['name'],error=str(error));await asyncio.sleep(3)
    def definitions(self):
        rows=self.studio.core_services.config.get('websocketConnections',[])
        if not isinstance(rows,list):raise ActionError('Ungültige WebSocket-Konfiguration')
        result={}
        for row in rows:
            if not isinstance(row,dict) or not isinstance(row.get('id'),str) or not row['id'] or row['id'] in result or row.get('mode','client') not in ('client','server'):raise ActionError('Ungültige oder doppelte WebSocket-Verbindung')
            result[row['id']]=row
        return result
    def wanted(self):
        definitions=self.definitions()
        for identity,(definition,_) in list(self.manual.items()):
            if definitions.get(identity)!=definition:self.manual.pop(identity)
        return {identity:item for identity,item in definitions.items() if not item.get('migrationBlock') and self.manual.get(identity,(None,item.get('enabled',True)))[1]}
    def connected(self,item):
        if self.studio.io.dry_run:return False
        managed=self.tasks.get(item['id'])
        return bool(managed and managed[0]==item and not managed[1].done() and any(not ws.closed for ws in self.sockets.get(item['id'],{}).values()))
    def listening(self,item):
        if self.studio.io.dry_run:return False
        managed=self.tasks.get(item['id'])
        return bool(managed and managed[0]==item and not managed[1].done() and self.listeners.get(item['id'])==item)
    async def server_sessions(self,item,operation,data=None,session=None):
        async with self.lock:
            if self.definitions().get(item['id'])!=item:raise ActionError('WebSocket-Konfiguration während des Aufrufs geändert')
            if not self.studio.io.dry_run and not self.listening(item):return
            if operation=='broadcast':
                if not isinstance(data,str):raise ActionError('WebSocket-Text fehlt')
                if len(data.encode('utf-8'))>65536:raise ActionError('WebSocket-Nachricht überschreitet 64 KiB')
            if session is not None and not isinstance(session,str):raise ActionError('Ungültige WebSocket-Session-ID')
            if self.studio.io.dry_run:
                self.studio.io.trace('websocket_server_'+operation,connectionId=item['id'],sessionId=session,simulated=True);return
            peers=list(self.sockets.get(item['id'],{}).items())
            for identity,ws in peers:
                if ws.closed or (session is not None and identity!=session):continue
                if operation=='broadcast':await ws.send_str(data)
                else:await ws.close()
    async def stop(self,identity):
        self.listeners.pop(identity,None)
        managed=self.tasks.pop(identity,None)
        if managed:managed[1].cancel()
        sockets=list(self.sockets.pop(identity,{}).values())
        if sockets:await asyncio.gather(*(ws.close() for ws in sockets),return_exceptions=True)
        if managed:await asyncio.gather(managed[1],return_exceptions=True)
    async def reconcile(self):
        # Called under lock by the supervisor or an explicit C# request.
        wanted=self.wanted()
        for identity,(definition,task) in list(self.tasks.items()):
            if wanted.get(identity)!=definition or task.done():await self.stop(identity)
        for identity,item in self.wanted().items():
            if identity not in self.tasks:
                definition=copy.deepcopy(item)
                async def worker(snapshot=definition):
                    if self.wanted().get(snapshot['id'])==snapshot:
                        await (self.server_retry(snapshot) if snapshot.get('mode')=='server' else self.client(snapshot))
                self.tasks[identity]=(definition,self.studio.spawn(worker()))
    async def control(self,item,connect):
        if self.studio.io.dry_run:
            self.studio.io.trace('websocket_connect' if connect else 'websocket_disconnect',connectionId=item['id'],simulated=True);return
        async with self.lock:
            if self.definitions().get(item['id'])!=item:raise ActionError('WebSocket-Konfiguration während des Aufrufs geändert')
            if self.closing or getattr(self.studio,'closing',False):
                if connect:raise ActionError('WebSocket-Laufzeit wird beendet')
                await self.stop(item['id']);return
            self.manual[item['id']]=(copy.deepcopy(item),connect)
            active=self.listening(item) if item.get('mode')=='server' else self.connected(item)
            if not connect or not active:await self.stop(item['id'])
            await self.reconcile()
    async def send(self,identity,text):
        if not isinstance(text,(str,bytes)):raise ActionError('WebSocket-Daten müssen Text oder Bytes sein')
        size=len(text.encode('utf-8')) if isinstance(text,str) else len(text)
        if size>65536:raise ActionError('WebSocket-Nachricht überschreitet 64 KiB')
        if self.studio.io.dry_run:self.studio.io.trace('websocket_send',connectionId=identity,simulated=True,binary=isinstance(text,bytes),size=size);return
        sockets=[ws for ws in self.sockets.get(identity,{}).values() if not ws.closed]
        if not sockets:raise ActionError('WebSocket-Verbindung ist nicht verbunden')
        for ws in sockets:
            if isinstance(text,bytes):await ws.send_bytes(text)
            else:await ws.send_str(text)
    async def close(self):
        async with self.lock:
            self.closing=True
            for identity in list(self.tasks):await self.stop(identity)
            for identity in list(self.sockets):await self.stop(identity)
            self.manual.clear()
    async def run(self):
        if self.studio.io.dry_run:return
        try:
            while not self.closing:
                async with self.lock:await self.reconcile()
                await asyncio.sleep(.25)
        finally:await self.close()
