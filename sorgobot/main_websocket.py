"""Authenticated event subscriptions for the verified native WebSocket subset."""
import asyncio
import datetime
import json
import secrets,hmac,base64,uuid
from .core import ActionError


def event_packet(operation,data):
    if operation=='string':
        if data is not None and not isinstance(data,str):raise ActionError('WebSocket-Broadcast benötigt Text')
        raw=json.dumps({'data':data},ensure_ascii=False,separators=(',',':'))
    elif operation=='json':
        if not isinstance(data,str):raise ActionError('WebSocket-Broadcast benötigt ein JSON-Objekt')
        def invalid_constant(value):raise ValueError(value)
        try:
            # Validate only; retain numeric precision and JSON tokens in the wire payload.
            value=json.loads(data,parse_float=str,parse_int=str,parse_constant=invalid_constant)
            if not isinstance(value,dict):raise ValueError()
        except (ValueError,RecursionError):raise ActionError('WebSocket-Broadcast benötigt ein gültiges JSON-Objekt') from None
        raw=data
    else:raise ActionError('Unbekannter WebSocket-Broadcast')
    header=json.dumps({'timeStamp':datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='microseconds'),'event':{'source':'General','type':'Custom'}},separators=(',',':'))
    packet=header[:-1]+',"data":'+raw+'}'
    if len(packet.encode('utf-8'))>65536:raise ActionError('WebSocket-Ereignis überschreitet 64 KiB')
    return packet


async def broadcast_rpc(engine,values):
    if len(values)!=2:raise ActionError('Ungültiger WebSocket-Broadcast')
    operation,data=values;packet=event_packet(operation,data)
    if engine.io.dry_run:
        engine.io.trace('websocket_broadcast',format=operation,size=len(packet.encode('utf-8')),simulated=True);return None
    hub=getattr(getattr(engine,'studio',None),'main_websocket',None)
    if hub is None:raise ActionError('Haupt-WebSocket-Laufzeit fehlt')
    await hub.broadcast(packet)
    return None


from .websocket_twitch_events import TWITCH_EVENTS
ORIGINAL_EVENTS={'General':['Custom'],'SpeechToText':['Dictation','Command'],'Twitch':TWITCH_EVENTS,'Command':['Triggered','Cooldown'],
 'Obs':['Connected','Disconnected','Event','SceneChanged','StreamingStarted','StreamingStopped','RecordingStarted','RecordingStopped','VendorEvent'],
 'Quote':['Added','Show']}
from .websocket_core_events import CATEGORIES
ORIGINAL_EVENTS.update(CATEGORIES)
from .youtube_events import EVENTS as YOUTUBE_EVENTS
ORIGINAL_EVENTS['YouTube']=list(YOUTUBE_EVENTS.values())

class MainWebsocket:
    def __init__(self,studio):self.studio=studio;self.peers={};self.closing=False;self.outbox=asyncio.Queue(maxsize=100);self.publisher=None
    def register(self,ws,original=False,authenticated=True,address=''):
        if self.closing or len(self.peers)>=64:return False
        peer={'custom':False,'subscriptions':set(),'lock':asyncio.Lock(),'original':original,'authenticated':authenticated,'address':address,'session':str(uuid.uuid4())}
        if original and not authenticated:
            from .original_websocket import authentication
            peer['salt']=base64.b64encode(secrets.token_bytes(24)).decode();peer['challenge']=base64.b64encode(secrets.token_bytes(24)).decode()
            password=self.studio.services.websocket_password()
            peer['expected']=[authentication(value,peer['salt'],peer['challenge']) for value in (password,self.studio.token)]
        self.peers[ws]=peer;return True
    def authenticate(self,ws,data):
        peer=self.peers[ws];value=data.get('authentication')
        valid=peer['authenticated'] or (isinstance(value,str) and any(hmac.compare_digest(value.encode(),expected.encode()) for expected in peer.get('expected',[])))
        if valid:peer['authenticated']=True;peer.pop('expected',None)
        return {'id':data.get('id'),'status':'ok' if valid else 'error',**({} if valid else {'error':'Authentifizierung fehlgeschlagen'})}
    def unregister(self,ws):self.peers.pop(ws,None)
    async def send(self,ws,data):
        peer=self.peers.get(ws)
        if peer is None:return
        async with peer['lock']:
            if not ws.closed:
                if isinstance(data,str):await ws.send_str(data)
                else:await ws.send_json(data)
    def request(self,ws,data):
        operation=data.get('request');response={'id':data.get('id'),'status':'ok'}
        if operation=='GetEvents':return dict(response,events={key:list(types) for key,types in ORIGINAL_EVENTS.items()} if self.peers[ws].get('original') else {'general':['Custom']})
        if operation not in ('Subscribe','UnSubscribe'):return None
        if self.peers[ws].get('original'):return self.subscribe(ws,data)
        events=data.get('events')
        if not isinstance(events,dict) or not events:raise ValueError('events')
        for source,types in events.items():
            if source.lower() not in ('general','*') or not isinstance(types,list) or not types or any(t not in ('Custom','*') for t in types):
                return dict(response,status='error',error='Nur General.Custom wird unterstützt')
        self.peers[ws]['custom']=operation=='Subscribe'
        return dict(response,events={'General':['Custom']} if operation=='Subscribe' else ['Custom'])
    def subscribe(self,ws,data):
        events=data.get('events');selected=set()
        if not isinstance(events,dict) or not events:raise ValueError('events')
        categories={key.casefold():key for key in ORIGINAL_EVENTS}
        for source,types in events.items():
            if not isinstance(source,str) or not isinstance(types,list) or not types or any(not isinstance(t,str) for t in types):raise ValueError('events')
            sources=list(ORIGINAL_EVENTS) if source=='*' else [categories[source.casefold()]] if source.casefold() in categories else []
            if not sources:raise ValueError('source')
            for kind in types:
                matches={(category,event) for category in sources for event in ORIGINAL_EVENTS[category] if kind in ('*',event)}
                if not matches:raise ValueError('event')
                selected.update(matches)
        peer=self.peers[ws];adding=data['request']=='Subscribe'
        if adding:peer['subscriptions'].update(selected)
        else:peer['subscriptions'].difference_update(selected)
        peer['custom']=('General','Custom') in peer['subscriptions']
        if not adding:
            removed=list(dict.fromkeys(kind for source,types in ORIGINAL_EVENTS.items() for kind in types if (source,kind) in selected))
            return {'id':data['id'],'status':'ok','events':removed}
        returned={source:[kind for kind in ORIGINAL_EVENTS[source] if (source,kind) in selected] for source in ORIGINAL_EVENTS if any(s==source for s,_ in selected)}
        return {'id':data.get('id'),'status':'ok','events':returned if adding else list(dict.fromkeys(kind for kinds in returned.values() for kind in kinds))}
    async def emit(self,source,kind,data):
        if not self.studio.live or self.studio.io.dry_run or self.closing:return
        if kind not in ORIGINAL_EVENTS.get(source,[]):raise ActionError('WebSocket-Ereignis ist nicht freigegeben')
        packet=json.dumps({'timeStamp':datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='microseconds'),'event':{'source':source,'type':kind},'data':data},ensure_ascii=False,allow_nan=False,separators=(',',':'))
        if len(packet.encode())>65536:raise ActionError('WebSocket-Ereignis überschreitet 64 KiB')
        await self.broadcast(packet,source,kind)
    def publish(self,source,kind,data):
        """Bounded, ordered delivery of native notifications without blocking actions."""
        if self.closing or not self.studio.live or self.studio.io.dry_run:return
        recipients=[ws for ws,peer in self.peers.items() if peer['authenticated'] and peer['original'] and (source,kind) in peer['subscriptions'] and not ws.closed]
        try:
            if kind not in ORIGINAL_EVENTS.get(source,[]):raise ValueError()
            packet=json.dumps({'timeStamp':datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='microseconds'),'event':{'source':source,'type':kind},'data':data},ensure_ascii=False,allow_nan=False,separators=(',',':'))
            if len(packet.encode())>65536:raise ValueError()
            from .chat_events import capture
            capture(self.studio,json.loads(packet))
            if not recipients:return
            self.outbox.put_nowait((packet,source,kind,recipients))
        except (ValueError,TypeError,RecursionError,asyncio.QueueFull):
            self.studio.io.trace('websocket_event_error',source=source,event=kind,error='Ereignis ungültig, zu groß oder Warteschlange voll');return
        if self.publisher is None or self.publisher.done():self.publisher=self.studio.spawn(self.drain())
    async def drain(self):
        while not self.outbox.empty() and not self.closing:
            packet,source,kind,recipients=self.outbox.get_nowait()
            try:await self.broadcast(packet,source,kind,recipients)
            finally:self.outbox.task_done()
    async def broadcast(self,packet,source='General',kind='Custom',recipients=None):
        if self.closing:raise ActionError('Haupt-WebSocket-Laufzeit wird beendet')
        # Snapshot recipients: a reconnect never inherits another socket's subscription.
        recipients=[ws for ws,peer in self.peers.items() if (recipients is None or ws in recipients) and ((source,kind) in peer['subscriptions'] if peer.get('original') else source=='General' and kind=='Custom' and peer['custom']) and peer['authenticated'] and not ws.closed]
        async def deliver(ws):
            try:await asyncio.wait_for(self.send(ws,packet),3)
            except (ConnectionError,RuntimeError,TimeoutError):
                self.unregister(ws)
                try:await asyncio.wait_for(ws.close(),1)
                except (ConnectionError,RuntimeError,TimeoutError):pass
        await asyncio.gather(*(deliver(ws) for ws in recipients))
    async def close(self,app=None):
        self.closing=True
        if self.publisher:
            self.publisher.cancel();await asyncio.gather(self.publisher,return_exceptions=True)
        while not self.outbox.empty():self.outbox.get_nowait();self.outbox.task_done()
        peers=list(self.peers);self.peers.clear()
        await asyncio.gather(*(ws.close() for ws in peers),return_exceptions=True)
