"""Ordered CPH access to native custom WebSocket servers."""
import copy
from .core import ActionError

async def rpc(engine,values):
    operation,*rest=values
    services=getattr(engine,'services',None)
    rows=services.config.get('websocketConnections',[]) if services else []
    if not isinstance(rows,list) or any(not isinstance(row,dict) for row in rows):raise ActionError('Ungültige WebSocket-Konfiguration')
    servers=[row for row in rows if row.get('mode')=='server']
    if operation=='names':return [row.get('name') for row in servers]
    if operation not in ('start','stop','listening','broadcast','close','close_all'):raise ActionError('Unbekannter C#-WebSocket-Serveraufruf')
    index,*payload=rest
    if type(index) is not int:raise ActionError('WebSocket-Serverindex muss int sein')
    if index<0 and servers:return {'invalidIndex':True}
    if index<0 or index>=len(servers):return False if operation=='listening' else None
    item=copy.deepcopy(servers[index]);manager=getattr(getattr(engine,'studio',None),'connections',None)
    if manager is None:raise ActionError('WebSocket-Laufzeit fehlt')
    manager.definitions()
    if operation=='listening':return manager.listening(item)
    if operation in ('start','stop'):await manager.control(item,operation=='start');return None
    data=payload[0] if payload else None;session=payload[1] if len(payload)>1 else None
    if operation=='close' and session is None:return None
    await manager.server_sessions(item,operation,data,session)
    return None
