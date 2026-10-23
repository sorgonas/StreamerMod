"""Authenticated loopback bridge for our OpenDeck plugin (not the proprietary plugin protocol)."""
import asyncio
import base64
import copy
import html
import json
import os
from pathlib import Path
import re
import secrets
import uuid
from aiohttp import web,WSMsgType,ClientTimeout,ClientError
from .core import ActionError

STEPS={
93000:('Set Title',{'buttonId':'%streamDeckButtonId%','title':'','state':0}),
93001:('Set Background',{'buttonId':'%streamDeckButtonId%','image':'','color':'#000000','state':0}),
93002:('Set State',{'buttonId':'%streamDeckButtonId%','state':0}),
93003:('Set Value',{'buttonId':'%streamDeckButtonId%','value':'0'}),
93004:('Show Alert',{'buttonId':'%streamDeckButtonId%'}),
93005:('Show OK',{'buttonId':'%streamDeckButtonId%'}),
93006:('Toggle State',{'buttonId':'%streamDeckButtonId%'}),
}
for _,defaults in STEPS.values():defaults['deviceId']=''
TRIGGERS={93050:('Stream Deck Connected',{}),93051:('Stream Deck Disconnected',{}),93052:('Stream Deck Info',{'buttonId':'','deviceId':''})}
INPUTS={'keyDown':93053,'keyUp':93054,'dialRotate':93055,'dialDown':93056,'dialUp':93057,'touchTap':93058}
for name,kind in INPUTS.items():TRIGGERS[kind]=('Inputs · '+{'keyDown':'Key Down','keyUp':'Key Up','dialRotate':'Dial Rotate','dialDown':'Dial Press','dialUp':'Dial Release','touchTap':'Touch Tap'}[name],{'buttonId':'','deviceId':'','state':'','direction':'any'} if name=='dialRotate' else {'buttonId':'','deviceId':'','state':''})

def finite(value):
    try:json.dumps(value,allow_nan=False)
    except (TypeError,ValueError):raise ActionError('Ungültige Stream-Deck-Daten') from None

def integer(value,maximum=1):
    if type(value) is bool:raise ActionError('Ungültiger Stream-Deck-Zustand')
    try:number=int(value)
    except (ValueError,TypeError):raise ActionError('Ungültiger Stream-Deck-Zustand') from None
    if str(number)!=str(value) or not 0<=number<=maximum:raise ActionError('Stream-Deck-Zustand außerhalb des Bereichs')
    return number

def matches(kind,trigger,args):
    if kind not in TRIGGERS:return True
    if not all(not trigger.get(field) or trigger[field]==args.get('streamDeck'+label) for field,label in [('buttonId','ButtonId'),('deviceId','DeviceId')]):return False
    state=trigger.get('state','')
    if state not in ('',None) and str(state)!=str(args.get('streamDeckState')):return False
    direction=trigger.get('direction','any')
    ticks=args.get('streamDeckTicks',0)
    return direction in ('any','',None) or direction=='clockwise' and ticks>0 or direction=='counterclockwise' and ticks<0

class Bridge:
    def __init__(self,studio):
        self.studio=studio;self.clients={};self.pending={};self.runner=None;self.state='disabled';self.token=secrets.token_urlsafe(32)

    def status(self):
        return {'state':self.state,'clients':len(self.clients),'buttons':sum(len(c['bindings']) for c in self.clients.values()),'bindings':[{'buttonId':b['buttonId'],'deviceId':b['deviceId'],'context':context,'controller':b.get('controller','Keypad'),'state':b['state']} for c in self.clients.values() for context,b in c['bindings'].items()],'endpoint':f"ws://127.0.0.1:{getattr(self,'port',8059)}/bridge"}

    async def start(self,port=8059,publish=True):
        if not self.studio.live:return
        app=web.Application();app.router.add_get('/bridge',self.socket)
        self.runner=web.AppRunner(app,access_log=None);await self.runner.setup()
        try:
            site=web.TCPSite(self.runner,'127.0.0.1',port);await site.start()
            self.port=site._server.sockets[0].getsockname()[1];self.state='listening'
            if publish:
                folder=Path(os.environ.get('XDG_CONFIG_HOME') or Path.home()/'.config')/'sorgobot';folder.mkdir(parents=True,exist_ok=True)
                self.discovery=folder/'streamdeck-bridge.private.json'
                descriptor=os.open(self.discovery,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
                with os.fdopen(descriptor,'w') as f:
                    os.fchmod(f.fileno(),0o600);json.dump({'endpoint':f'ws://127.0.0.1:{self.port}/bridge','token':self.token},f)
        except (OSError,ValueError):
            self.state='unavailable';await self.runner.cleanup();self.runner=None
            self.studio.io.trace('streamdeck_server_error',message='Lokale Stream-Deck-Verbindung nicht verfügbar (Port oder Konfiguration prüfen).')

    def emit(self,kind,args):
        if not self.studio.closing:self.studio.engine.core_events.emit(kind,args)

    async def socket(self,request):
        if request.remote not in ('127.0.0.1','::1') or request.headers.get('Origin'):raise web.HTTPForbidden()
        ws=web.WebSocketResponse(heartbeat=20,max_msg_size=65536);await ws.prepare(request)
        identity=uuid.uuid4().hex
        try:
            message=await asyncio.wait_for(ws.receive_json(),5)
            if not isinstance(message,dict) or not isinstance(message.get('token'),str) or not secrets.compare_digest(message['token'],self.token):
                await ws.close(code=1008,message=b'Authentication required');return ws
            client={'ws':ws,'bindings':{},'sequence':0};self.clients[identity]=client
            await ws.send_json({'op':'ready'});self.emit(93050,{'streamDeckClientId':identity})
            async for item in ws:
                if item.type!=WSMsgType.TEXT:continue
                try:
                    data=json.loads(item.data);finite(data)
                    if not isinstance(data,dict):raise ActionError('Objekt erwartet')
                    await self.receive(identity,client,data)
                except (ActionError,TypeError,ValueError,KeyError):await ws.send_json({'op':'error','message':'Stream-Deck-Anfrage ungültig oder Ziel nicht verfügbar.'})
        except (TimeoutError,ValueError,TypeError):await ws.close(code=1008)
        finally:
            client=self.clients.pop(identity,None)
            if client:
                for request_id,(owner,future) in list(self.pending.items()):
                    if owner==identity and not future.done():future.set_exception(ActionError('Stream-Deck-Verbindung unterbrochen; nicht automatisch wiederholen'))
                self.emit(93051,{'streamDeckClientId':identity})
        return ws

    async def receive(self,identity,client,data):
        op=data.get('op');ws=client['ws']
        if op=='capabilities':
            client['protocol']=2 if data.get('version')==2 else 1
            return
        if op=='actions':
            await ws.send_json({'op':'actions','actions':[{'id':a['id'],'name':a['name']} for a in self.studio.engine.actions.values()]});return
        if op=='ack':
            pair=self.pending.get(data.get('id'))
            if pair and pair[0]==identity and not pair[1].done():pair[1].set_result(data.get('ok') is True)
            return
        context=data.get('context')
        if not isinstance(context,str) or not context or len(context)>256:raise ActionError('Kontext fehlt')
        if op=='remove':client['bindings'].pop(context,None);return
        if op=='bind':
            if len(client['bindings'])>=512 and context not in client['bindings']:raise ActionError('Zu viele Tasten')
            settings=data.get('settings',{})
            if not isinstance(settings,dict) or not isinstance(settings.get('arguments',{}),dict):raise ActionError('Argumentobjekt erwartet')
            button=settings.get('buttonId') or context
            if not isinstance(button,str) or len(button)>256:raise ActionError('Ungültige Button-ID')
            device=data.get('device','')
            if not isinstance(device,str):raise ActionError('Ungültiges Gerät')
            old=client['bindings'].get(context,{})
            client['bindings'][context]={'buttonId':button,'deviceId':device,'settings':copy.deepcopy(settings),'controller':data.get('controller','Keypad'),'state':old.get('state',integer(data.get('state',0)))}
            self.emit(93052,self.arguments(identity,context,client['bindings'][context],{}));return
        if op!='input' or context not in client['bindings']:raise ActionError('Unbekannte Taste')
        sequence=data.get('sequence')
        if type(sequence) is not int or sequence<=client['sequence']:raise ActionError('Wiederholtes Eingabeereignis')
        client['sequence']=sequence
        event=data.get('event');payload=data.get('data',{})
        if event not in INPUTS or not isinstance(payload,dict):raise ActionError('Ungültige Eingabe')
        binding=client['bindings'][context];settings=binding['settings']
        if 'state' in payload:binding['state']=integer(payload['state'])
        if event=='dialRotate':
            ticks=payload.get('ticks')
            if type(ticks) is not int or not -1000<=ticks<=1000 or ticks==0:raise ActionError('Ungültige Drehschritte')
            field='clockwiseActionId' if ticks>0 else 'counterclockwiseActionId'
        else:field={'keyDown':'actionId','keyUp':'upActionId','dialDown':'actionId','dialUp':'upActionId','touchTap':'touchActionId'}[event]
        values=self.arguments(identity,context,binding,payload);values['streamDeckEvent']=event
        if event in ('keyDown','dialDown'):values['streamDeckPressed']=True
        elif event in ('keyUp','dialUp'):values['streamDeckPressed']=False
        self.emit(INPUTS[event],values)
        action=settings.get(field)
        if action:
            if not isinstance(action,str) or action not in self.studio.engine.actions:raise ActionError('Action nicht gefunden')
            from .event_context import arguments
            self.studio.spawn(self.studio.engine.run(action,arguments(INPUTS[event],values)))

    def arguments(self,identity,context,binding,payload):
        reserved={'__source','eventsource','nativetriggertype','eventtypeknown','eventtypemapping'}
        values={k:copy.deepcopy(v) for k,v in binding['settings'].get('arguments',{}).items() if not k.casefold().startswith('streamdeck') and k.casefold() not in reserved}
        values.update(streamDeckClientId=identity,streamDeckContext=context,streamDeckButtonId=binding['buttonId'],streamDeckDeviceId=binding['deviceId'],streamDeckState=binding['state'],streamDeckTicks=payload.get('ticks',0),streamDeckPressed=payload.get('pressed',False))
        return values

    async def send(self,node):
        button=node.get('buttonId')
        if not isinstance(button,str) or not button:raise ActionError('Stream-Deck-Button-ID fehlt')
        targets=[(identity,c,context,b) for identity,c in self.clients.items() for context,b in c['bindings'].items() if b['buttonId']==button and (not node.get('deviceId') or b['deviceId']==node['deviceId'])]
        if not targets:raise ActionError('Keine sichtbare Studio-Taste mit dieser Button-ID verbunden')
        kind=node['type'];payload={}
        if kind in (93000,93001,93002):payload['state']=integer(node.get('state',0))
        if kind==93000:payload['title']=str(node.get('title',''))[:4000]
        if kind==93001:payload['image']=await self.background(node)
        if kind==93003:payload['value']=str(node.get('value',''))[:4000]
        event={93000:'setTitle',93001:'setImage',93002:'setState',93003:'setValue',93004:'showAlert',93005:'showOk',93006:'setState'}[kind]
        for identity,client,context,binding in targets:
            if self.clients.get(identity) is not client or client['bindings'].get(context) is not binding:
                raise ActionError('Stream-Deck-Taste wurde während des Aufrufs geändert oder entfernt')
            values=dict(payload)
            if kind==93006:values['state']=1-binding['state']
            request_id=uuid.uuid4().hex;future=asyncio.get_running_loop().create_future();self.pending[request_id]=(identity,future)
            try:
                await client['ws'].send_json({'op':'command','id':request_id,'context':context,'event':event,'payload':values})
                if not await asyncio.wait_for(future,5):raise ActionError('OpenDeck hat den Befehl abgewiesen')
                if self.clients.get(identity) is not client or client['bindings'].get(context) is not binding:
                    raise ActionError('Stream-Deck-Taste wurde nach Versand geändert; Ergebnis prüfen, nicht automatisch wiederholen')
                if event=='setState':binding['state']=values['state']
            except TimeoutError:raise ActionError('Keine OpenDeck-Bestätigung; Ergebnis unklar, nicht automatisch wiederholen') from None
            finally:
                self.pending.pop(request_id,None)
                if not future.done():future.cancel()
                elif not future.cancelled():future.exception()

    async def background(self,node):
        image=node.get('image','');color=node.get('color') or 'transparent'
        if not isinstance(image,str) or not isinstance(color,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?|[a-zA-Z]{1,30}',color):raise ActionError('Ungültige Hintergrundfarbe')
        if image.startswith(('http://','https://')):
            try:
                async with self.studio.session.get(image,timeout=ClientTimeout(total=10)) as response:
                    if response.status!=200:raise ActionError('Hintergrundbild konnte nicht geladen werden')
                    mime=response.headers.get('Content-Type','').split(';')[0].lower()
                    if mime not in ('image/png','image/jpeg','image/svg+xml','image/webp','image/gif'):raise ActionError('URL liefert kein unterstütztes Bild')
                    raw=bytearray()
                    async for chunk in response.content.iter_chunked(65536):
                        raw.extend(chunk)
                        if len(raw)>2_000_000:raise ActionError('Bild größer als 2 MB')
                    image='data:'+mime+';base64,'+base64.b64encode(raw).decode()
            except (ClientError,TimeoutError):raise ActionError('Hintergrundbild-Abfrage fehlgeschlagen') from None
        if image and not image.startswith(('http://','https://','data:image/','<svg')):
            path=Path(image).expanduser();path=path if path.is_absolute() else self.studio.root/path
            if path.stat().st_size>2_000_000:raise ActionError('Bild größer als 2 MB')
            raw=await asyncio.to_thread(path.read_bytes)
            mime='image/svg+xml' if path.suffix.lower()=='.svg' else 'image/jpeg' if path.suffix.lower() in ('.jpg','.jpeg') else 'image/png'
            image='data:'+mime+';base64,'+base64.b64encode(raw).decode()
        elif image.startswith('<svg'):image='data:image/svg+xml;base64,'+base64.b64encode(image.encode()).decode()
        if len(image)>3_000_000:raise ActionError('Bild zu groß')
        svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="144" height="144"><rect width="144" height="144" fill="{color}"/>'
        if image:svg+=f'<image href="{html.escape(image,quote=True)}" width="144" height="144"/>'
        return svg+'</svg>'

    async def send_custom(self,event,payload,*,button=None,device=''):
        if event not in ('deckUpdate','deckNotify'):raise ActionError('Unbekannter Deck-Befehl')
        if event=='deckUpdate' and (not isinstance(button,str) or not button):raise ActionError('Item-/Button-ID fehlt')
        targets=[(identity,client,context) for identity,client in self.clients.items() for context,binding in client['bindings'].items() if (button is None or binding['buttonId']==button) and (not device or binding['deviceId']==device)]
        if not targets:raise ActionError('Keine sichtbare StreamerMod-Belegung auf dem gewünschten Deck verbunden')
        if any(client.get('protocol',1)<2 for _,client,_ in targets):raise ActionError('StreamerMod-Plugin aktualisieren und OpenDeck neu starten')
        for identity,client,context in targets:
            request_id=uuid.uuid4().hex;future=asyncio.get_running_loop().create_future();self.pending[request_id]=(identity,future)
            try:
                if self.clients.get(identity) is not client or context not in client['bindings']:raise ActionError('Deck-Belegung wurde entfernt')
                await client['ws'].send_json({'op':'command','id':request_id,'context':context,'event':event,'payload':payload})
                if not await asyncio.wait_for(future,5):raise ActionError('OpenDeck-Plugin hat den Deck-Befehl abgewiesen')
            except TimeoutError:raise ActionError('Keine Plugin-Bestätigung; Ergebnis unklar, nicht automatisch wiederholen') from None
            finally:
                self.pending.pop(request_id,None)
                if not future.done():future.cancel()
                elif not future.cancelled():future.exception()

    async def close(self):
        for client in list(self.clients.values()):await client['ws'].close()
        if self.runner:await self.runner.cleanup();self.runner=None
        self.state='disabled'
        path=getattr(self,'discovery',None)
        if path and path.exists():
            try:
                if json.loads(path.read_text()).get('token')==self.token:path.unlink()
            except (OSError,ValueError):pass

async def operation(io,node,args):
    if io.dry_run:
        io.trace('streamdeck',operation=STEPS[node['type']][0],simulated=True);return
    studio=getattr(getattr(io,'engine',None),'studio',None)
    bridge=getattr(studio,'streamdeck',None)
    if bridge is None or bridge.state!='listening':raise ActionError('Stream-Deck-Verbindung unter Stream Apps prüfen')
    await bridge.send(node)
