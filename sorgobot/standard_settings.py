"""Dedicated native settings actions shared with existing credits/first-word state."""
import re
from .core import ActionError
STEPS={95000:('Pick Color',{'color':'#ffffff','resultVariable':'selectedColor'}),95001:('Reset Credits',{}),95002:('Reset First Words',{}),95003:('Set Voice Control Input',{'audioDevice':'@default'})}
ALIASES={95000:'settings/pick-color',95001:'settings/reset-credits',95002:'settings/reset-first-words',95003:'settings/set-voice-control-input'}

async def operation(io,node,args):
 kind=node['type'];engine=io.engine
 if kind==95000:
  name=node.get('resultVariable','selectedColor')
  if not isinstance(name,str) or not name.strip():raise ActionError('Ergebnisvariable fehlt.')
  args.pop(name,None);args['colorPicked']=False
  if io.dry_run:io.trace('pick_color',simulated=True);return
  request=getattr(io,'request_input',None)
  if request is None:raise ActionError('Farbauswahl benötigt die Desktopoberfläche.')
  text,accepted=await request({'kind':'color','title':'Pick Color','originalText':node.get('color','#ffffff')})
  if accepted:
   if not isinstance(text,str) or not re.fullmatch('#[a-fA-F0-9]{6}',text):raise ActionError('Farbauswahl lieferte keine gültige RGB-Farbe.')
   args[name]=text;args['colorPicked']=True
  return
 if kind==95003:
  device=node.get('audioDevice','@default')
  if not isinstance(device,str) or not device.strip() or len(device)>500 or any(ord(c)<32 for c in device):raise ActionError('Ungültiger Mikrofon-Gerätename.')
  if io.dry_run:io.trace('voice_input',device=device,simulated=True);return
  studio=getattr(engine,'studio',None);manager=getattr(studio,'services',None)
  if manager is None:raise ActionError('Spracherkennungsdienst ist nicht verfügbar.')
  args.update(await manager.set_voice_input(device));return
 if io.dry_run:io.trace('settings_reset',operation=STEPS[kind][0],simulated=True);return
 if kind==95001:
  from .csharp_core_services import rpc
  await rpc(engine,'credits',['reset']);return
 if kind==95002:
  studio=getattr(engine,'studio',None)
  if studio is None:raise ActionError('First-Words-Verwaltung ist nicht verfügbar.')
  studio.dispatcher.first_users.clear();engine.state.set('first_words_users',[]);return
 raise ActionError('Unbekannte Settings-Unteraktion.')
