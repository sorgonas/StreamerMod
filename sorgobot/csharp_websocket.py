"""Original-style ordered client access to the existing native Connections service."""
import base64,binascii,copy
from .core import ActionError

async def rpc(engine,values):
    operation,index,*payload=values
    if operation not in ('connect','disconnect','connected','send_text','send_bytes'):raise ActionError('Unbekannter C#-WebSocket-Aufruf')
    if type(index) is not int:raise ActionError('WebSocket-Clientindex muss int sein')
    services=getattr(engine,'services',None)
    rows=services.config.get('websocketConnections',[]) if services else []
    if not isinstance(rows,list) or any(not isinstance(row,dict) for row in rows):raise ActionError('Ungültige WebSocket-Konfiguration')
    clients=[row for row in rows if row.get('mode','client')=='client']
    if index<0 and clients:return {'invalidIndex':True}
    if index<0 or index>=len(clients):return False if operation=='connected' else None
    item=copy.deepcopy(clients[index]);manager=getattr(getattr(engine,'studio',None),'connections',None)
    if manager is None:raise ActionError('WebSocket-Laufzeit fehlt')
    manager.definitions()  # Reject ambiguous IDs before addressing a socket.
    if operation=='connected':return manager.connected(item)
    if operation in ('connect','disconnect'):await manager.control(item,operation=='connect');return None
    # Like the original wrapper, disconnected clients do not receive buffered sends.
    if not engine.io.dry_run and not manager.connected(item):return None
    data=payload[0]
    if operation=='send_bytes':
        if not isinstance(data,str):raise ActionError('WebSocket-Bytes fehlen')
        try:data=base64.b64decode(data,validate=True)
        except (ValueError,binascii.Error):raise ActionError('Ungültige WebSocket-Binärdaten') from None
    elif not isinstance(data,str):raise ActionError('WebSocket-Text fehlt')
    await manager.send(item['id'],data)
    return None
