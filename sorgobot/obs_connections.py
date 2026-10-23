"""Independent WebSocket clients, with legacy local OBS settings preserved."""
import asyncio
import copy
import math
from urllib.parse import urlsplit
from .core import ActionError

OBS_TYPES=frozenset((30,38,39,48,322,323,90005,*range(90300,90325)))

def validate(value):
    result=copy.deepcopy(value)
    if not isinstance(result.get('name'),str) or not result['name'].strip():raise ValueError('Verbindungsname fehlt')
    try:
        parsed=urlsplit(result['url']);port=parsed.port
        if parsed.scheme not in ('ws','wss') or not parsed.hostname or (port is not None and not 1<=port<=65535):raise ValueError()
        if parsed.username or parsed.password:raise ValueError()
    except (ValueError,KeyError,TypeError):raise ValueError('Gültige ws:// oder wss:// Adresse ohne eingebettetes Passwort erforderlich') from None
    try:retry=float(result.get('retryInterval',5))
    except (ValueError,TypeError):raise ValueError('Retry Interval benötigt eine Zahl') from None
    if not math.isfinite(retry) or retry<1:raise ValueError('Retry Interval muss mindestens 1 Sekunde sein')
    result['retryInterval']=retry
    if not isinstance(result.get('password',''),str):raise ValueError('Passwort muss Text sein')
    return result

def definitions(config):
    main={'id':'default','name':config.get('obs_name','Local OBS'),'url':config.get('obs_url','ws://127.0.0.1:4455'),'password':config.get('obs_password',''),'autoConnect':config.get('obs_auto_connect',True),'reconnect':config.get('obs_reconnect',True),'retryInterval':config.get('obs_retry_interval',5),'enabled':config.get('obs_enabled',True)}
    result=[validate(main)];seen={'default','any','*','','__local__'}
    for value in config.get('obsConnections',[]):
        value=validate(value);identity=value.get('id')
        if not isinstance(identity,str) or identity in seen:raise ValueError('OBS-Verbindungs-ID fehlt oder ist doppelt/reserviert')
        seen.add(identity);result.append(value)
    return result

def client_config(value):
    return {'obs_connection_id':value['id'],'obs_connection_name':value['name'],'obs_url':value['url'],'obs_password':value.get('password',''),'obs_reconnect':value.get('reconnect',True),'obs_retry_interval':value.get('retryInterval',5)}

class OBSConnections:
    def __init__(self,io,primary):
        self.io=io;self.config=io.config;self.rows={v['id']:v for v in definitions(self.config)}
        primary.config=client_config(self.rows['default'])
        self.clients={'default':primary};self.tasks={};self.force=None;self.on_event=None
        from .adapters import OBS
        for identity,row in self.rows.items():
            if identity!='default':self.clients[identity]=OBS(io.session,client_config(row))
    def default_id(self):
        desired=self.config.get('obsDefaultConnection','default')
        if desired in self.rows and self.rows[desired].get('enabled',True):return desired
        return next((i for i,r in self.rows.items() if r.get('enabled',True)),'default')
    def targets(self,selector='default',respect_force=True):
        if respect_force and self.force:selector='__local__' if self.force=='default' else self.force
        if selector=='__local__':selector='default'
        elif selector in (None,'','default'):selector=self.default_id()
        available=[i for i,row in self.rows.items() if row.get('enabled',True)]
        if selector in ('any','*'):
            if not available:raise ActionError('Keine aktive OBS-Verbindung eingerichtet')
            return available
        if selector not in available:raise ActionError('OBS-Verbindung fehlt oder ist deaktiviert')
        return [selector]
    def get(self,selector='default',respect_force=True):
        selected=self.targets(selector,respect_force)
        if len(selected)!=1:raise ActionError('Diese Abfrage benötigt eine einzelne OBS-Verbindung')
        return self.clients[selected[0]]
    def callback(self,identity):
        if self.on_event is None:return None
        def receive(kind,data):
            if self.on_event:self.on_event(kind,data,self.clients[identity].connection_arguments())
        return receive
    async def configure(self,config,on_event=None):
        updated={v['id']:v for v in definitions(config)}
        self.on_event=on_event
        from .adapters import OBS
        for identity in list(self.clients):
            old=self.rows.get(identity);new=updated.get(identity)
            if new is None or client_config(old)!=client_config(new) or old.get('enabled',True)!=new.get('enabled',True):
                await self.disconnect(identity)
                self.clients.pop(identity,None)
        self.config=config;self.rows=updated
        for identity,row in updated.items():
            if identity not in self.clients:self.clients[identity]=OBS(self.io.session,client_config(row))
            self.clients[identity].on_event=self.callback(identity)
        self.io.obs=self.clients['default']
        if self.force not in self.rows or not self.rows[self.force].get('enabled',True):self.force=None
    def connect(self,identity,spawn):
        # Here 'default' is the persistent local entry ID, not the default selector.
        if identity not in self.rows or not self.rows[identity].get('enabled',True):raise ActionError('OBS-Verbindung fehlt oder ist deaktiviert')
        task=self.tasks.get(identity)
        if task is None or task.done():self.tasks[identity]=spawn(self.clients[identity].listen())
        return self.clients[identity]
    def auto_connect(self,spawn):
        for identity,row in self.rows.items():
            if row.get('enabled',True) and row.get('autoConnect',True):self.connect(identity,spawn)
    async def disconnect(self,identity):
        task=self.tasks.pop(identity,None)
        if task:
            task.cancel();await asyncio.gather(task,return_exceptions=True)
        client=self.clients.get(identity)
        if client:client.status='offline'
    async def close(self):
        self.on_event=None
        for client in self.clients.values():client.on_event=None
        for identity in list(self.tasks):await self.disconnect(identity)
    def statuses(self):
        return {identity:{'status':client.status,'connected':client.ready.is_set(),'default':identity==self.default_id(),'forced':identity==self.force} for identity,client in self.clients.items()}
