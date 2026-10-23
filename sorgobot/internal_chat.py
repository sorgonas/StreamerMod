"""Correlate explicit internal sends with their EventSub echo by confirmed ID."""
import asyncio,time
from collections import OrderedDict

def state(studio):
 if not hasattr(studio,'internal_chat_state'):studio.internal_chat_state={'pending':[],'sent':OrderedDict()}
 return studio.internal_chat_state

def begin(studio,owner,sender,text):
 value=state(studio)
 if len(value['pending'])>=32:raise ValueError('Zu viele ausstehende interne Nachrichten')
 item={'owner':owner,'sender':sender,'text':text,'future':asyncio.get_running_loop().create_future()};value['pending'].append(item);return item

def finish(studio,item,identity=None):
 value=state(studio)
 if identity:
  sent=value['sent'];sent[item['owner'],item['sender'],identity]=time.monotonic()
  while len(sent)>1000:sent.popitem(last=False)
 if not item['future'].done():item['future'].set_result(identity)
 if item in value['pending']:value['pending'].remove(item)

async def matches(studio,event):
 if studio is None:return False
 value=state(studio);key=(event.get('broadcaster_user_id'),event.get('chatter_user_id'),event.get('message_id'));now=time.monotonic()
 for old,stamp in list(value['sent'].items()):
  if now-stamp>600:value['sent'].pop(old,None)
 if key in value['sent']:return True
 text=(event.get('message') or {}).get('text')
 pending=[i['future'] for i in value['pending'] if (i['owner'],i['sender'])==key[:2] and i['text']==text]
 if pending:
  try:
   identities=await asyncio.wait_for(asyncio.gather(*(asyncio.shield(f) for f in pending)),65)
   return key[2] in identities and key[2] is not None
  except TimeoutError:return False
 return False
