"""CPH UDP broadcast; payload is encoded by .NET after object.ToString()."""
import asyncio
import base64
import binascii
from socket import socket as udp_socket, AF_INET, SOCK_DGRAM, SOL_SOCKET, SO_BROADCAST
from .core import ActionError


async def broadcast(engine,values):
    if len(values)!=2:raise ActionError('UDP benötigt Port und Nutzdaten')
    port,encoded=values
    if isinstance(port,bool) or not isinstance(port,int) or not 1<=port<=65535:
        raise ActionError('UDP benötigt einen Zielport zwischen 1 und 65535')
    try:
        if not isinstance(encoded,str):raise ValueError()
        payload=base64.b64decode(encoded,validate=True)
    except (ValueError,binascii.Error):raise ActionError('Ungültige UDP-Nutzdaten') from None
    if len(payload)>65507:raise ActionError('UDP-Nachricht überschreitet 65507 Bytes')
    host='255.255.255.255'
    if engine.io.dry_run:
        engine.io.trace('udp',host=host,port=port,bytes=len(payload),simulated=True)
        return len(payload)
    def send():
        with udp_socket(AF_INET,SOCK_DGRAM) as sock:
            sock.setsockopt(SOL_SOCKET,SO_BROADCAST,1)
            sock.settimeout(3)
            return sock.sendto(payload,(host,port))
    return await asyncio.to_thread(send)
