"""Shared public action/credits contracts; transport adapters do not bypass checks."""
import copy,json
from .core import ActionError

def resolve(engine,target):
 if not isinstance(target,dict):raise ValueError('action')
 identity=target.get('id');name=target.get('name')
 if identity is not None:
  if not isinstance(identity,str) or not identity:raise ValueError('action id')
  matches=[a for a in engine.actions.values() if a['id'].casefold()==identity.casefold()]
 else:
  if not isinstance(name,str) or not name:raise ValueError('action name')
  matches=[a for a in engine.actions.values() if a['name']==name]
 if len(matches)!=1:raise ActionError('Aktion nicht gefunden oder Name nicht eindeutig; ID verwenden')
 action=matches[0]
 if not action.get('enabled',True):raise ActionError('Aktion ist deaktiviert')
 if action.get('migrationBlock'):raise ActionError('Aktion benötigt eine abgeschlossene Migration')
 return action

def execute(studio,data):
 from .original_websocket import mutable
 mutable(studio)
 if not isinstance(data,dict):raise ValueError('Action-Anfrage benötigt ein JSON-Objekt')
 args=data.get('args',{})
 if not isinstance(args,dict):raise ValueError('args')
 json.dumps(args,allow_nan=False)
 action=resolve(studio.engine,data.get('action'))
 studio.spawn(studio.engine.run(action['id'],copy.deepcopy(args)))

def test_credits(engine):
 from .csharp_core_services import credits,save_credits,credits_snapshot
 value=credits(engine)
 def add(container,key):
  rows=container.setdefault(key,[]);name='StreamerMod Test '+key
  if name not in rows and not any(isinstance(r,dict) and r.get('user')==name for r in rows):rows.append(name)
 for key in ('Follows','Cheers','Subs','ReSubs','GiftSubs','GiftBombs','Raided','RewardRedemptions','GoalContributions','GameUpdates','Pyramids','HypeTrains'):add(value.setdefault('Events',{}),key)
 for key in ('Editors','Moderators','Subscribers','VIPs','Users'):add(value.setdefault('User',{}),key)
 for key in ('HypeTrainConductor','HypeTrainContributors','TopChannelRewards'):add(value,key)
 for key in ('All','Month','Week'):add(value.setdefault('TopBits',{}),key)
 save_credits(engine,value);return credits_snapshot(engine)

async def send_message(studio,data):
 from .original_websocket import mutable
 from .twitch_chat_actions import Chat,message_id
 mutable(studio)
 if data.get('platform','twitch')=='youtube':
  service=getattr(studio,'youtube',None)
  if service is None:raise ActionError('YouTube ist nicht eingerichtet')
  if data.get('replyId') is not None:raise ActionError('YouTube unterstützt hier keine Antwort-Threads')
  if type(data.get('bot',True)) is not bool or type(data.get('internal',False)) is not bool:raise ValueError('bot/internal')
  return {'messageId':await service.send(data.get('message'),internal=data.get('internal',False),use_bot=data.get('bot',True))}
 if data.get('platform','twitch')!='twitch':raise ActionError('Diese Plattform ist nicht eingerichtet')
 text=data.get('message');bot=data.get('bot',True);internal=data.get('internal',False);reply=data.get('replyId')
 if not isinstance(text,str) or not text.strip() or len(text)>500 or any(c in text for c in ('\x00','\r','\n')):raise ActionError('Chatnachricht: 1–500 Zeichen, eine Zeile')
 if type(bot) is not bool or type(internal) is not bool:raise ValueError('bot/internal')
 if reply is not None:reply=message_id(reply)
 service=Chat(studio.io);reservation=None
 if internal:
  from .internal_chat import begin
  sender=service.account(bot,('user:write:chat',));reservation=begin(studio,studio.io.config['broadcaster_id'],sender,text)
 try:
  result=await service.reply(reply,text,bot,False)
 except BaseException:
  if reservation:
   from .internal_chat import finish
   finish(studio,reservation)
  raise
 if reservation:
  from .internal_chat import finish
  finish(studio,reservation,result['messageId'])
