"""Own-plugin item rendering and confirmed OpenDeck profile navigation."""
import asyncio,json,os,re
from pathlib import Path
from urllib.parse import quote
from .core import ActionError
from .streamdeck_bridge import integer

def profile_root():
 return Path(os.environ.get('XDG_CONFIG_HOME') or Path.home()/'.config')/'opendeck/profiles'

def profile_snapshot(root=None):
 root=Path(root) if root else profile_root();result=[]
 for folder in sorted(root.iterdir()) if root.exists() else []:
  if not folder.is_dir() or folder.is_symlink():continue
  try:
   selected=json.loads((root/(folder.name+'.json')).read_text())['selected_profile']
   pages=sorted((str(p.relative_to(folder))[:-5] for p in folder.rglob('*.json') if not p.is_symlink()),key=str.casefold)
   result.append({'deviceId':folder.name,'selected':selected,'pages':pages})
  except (OSError,ValueError,KeyError):continue
 return result

async def navigate(io,node,args,root=None):
 from .streamdeck_support import executable,running
 if not running():raise ActionError('OpenDeck separat starten; Seitenwechsel benötigt den laufenden Host')
 rows=profile_snapshot(root);device=node.get('deviceId') or args.get('streamDeckDeviceId')
 if not device:
  if len(rows)!=1:raise ActionError('Für den Seitenwechsel ein eindeutiges OpenDeck-Gerät auswählen')
  device=rows[0]['deviceId']
 row=next((r for r in rows if r['deviceId']==device),None)
 if row is None or not row['pages']:raise ActionError('Keine OpenDeck-Profile für dieses Gerät vorhanden')
 pages=row['pages'];current=row['selected'];kind=node['type']
 if kind==97109:
  requested=str(node.get('page',''))
  target=requested if requested in pages else pages[int(requested)-1] if requested.isascii() and requested.isdigit() and 1<=int(requested)<=len(pages) else None
  if target is None:raise ActionError('OpenDeck-Seite: Profilname oder Seitennummer ab 1 auswählen')
 else:
  if current not in pages:raise ActionError('Aktuelles OpenDeck-Profil ist nicht bekannt')
  target=pages[(pages.index(current)+(1 if kind==97107 else -1))%len(pages)]
 binary=executable()
 if not binary:raise ActionError('OpenDeck separat installieren und starten')
 # Only the host CLI can switch profiles: ordinary plugins are intentionally
 # forbidden to issue switchProfile in OpenDeck 2.14.1.
 await asyncio.wait_for(io.process(binary,'--process-message',json.dumps({'event':'switchProfile','device':device,'profile':target})),8)
 for _ in range(30):
  selected=next((r['selected'] for r in profile_snapshot(root) if r['deviceId']==device),None)
  if selected==target:args.update(deckPage=target,deckDeviceId=device);return
  await asyncio.sleep(.1)
 raise ActionError('OpenDeck hat den Profilwechsel nicht bestätigt; Gerät und laufendes OpenDeck prüfen')

async def operation(io,node,args):
 from .streamermod_catalog import STEPS
 if io.dry_run:io.trace('streamermod_deck',operation=STEPS[node['type']][0],simulated=True);return
 if node['type'] in (97107,97108,97109):return await navigate(io,node,args)
 bridge=getattr(getattr(getattr(io,'engine',None),'studio',None),'streamdeck',None)
 if bridge is None or bridge.state!='listening':raise ActionError('OpenDeck-Plugin-Verbindung ist nicht verfügbar')
 kind=node['type'];payload={};device=node.get('deviceId','')
 if kind==97100:
  duration=integer(node.get('duration',3000),30000)
  if duration<100:raise ActionError('Benachrichtigungsdauer: 100–30000 ms')
  payload={'title':str(node.get('title',''))[:300],'description':str(node.get('description',''))[:1000],'duration':duration}
  await bridge.send_custom('deckNotify',payload,device=device);return
 if kind==97103:return await bridge.send({**node,'type':93002})
 if kind==97106:return await bridge.send({**node,'type':93006})
 payload['state']=integer(node.get('state',0))
 if kind==97101:payload['background']=await bridge.background(node)
 elif kind==97102:
  image=node.get('image','');name=node.get('iconName','')
  if name:
   if not re.fullmatch(r'[a-z0-9-]+:[a-z0-9-]+',name):raise ActionError('Iconname z. B. mdi:home angeben')
   image='https://api.iconify.design/'+name.replace(':','/')+'.svg?color='+quote(str(node.get('color','white')),safe='')
  payload['icon']=await bridge.background({**node,'image':image,'color':'transparent'}) if image else ''
 elif kind==97104:payload['title']=str(node.get('title',''))[:4000]
 elif kind==97105:payload['value']=str(node.get('value',''))[:4000]
 await bridge.send_custom('deckUpdate',payload,button=node.get('buttonId'),device=device)
