#!/usr/bin/env python3
"""Provision only named StreamerMod examples while both applications are stopped."""
import argparse,copy,json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sorgobot.next_catalog import steps
from sorgobot.catalog import ConfigStore,new_action,new_step
from sorgobot.streamdeck_support import install_plugin

def setup(project,device):
 config=Path(os.environ.get('XDG_CONFIG_HOME') or Path.home()/'.config')/'opendeck';folder=config/'profiles'/device
 if not folder.is_dir():raise ValueError('OpenDeck-Geräteprofil fehlt')
 target=install_plugin(project);manifest=json.loads((target/'manifest.json').read_text());store=ConfigStore(project/'next-studio');document=store.read('actions.json');group='StreamerMod – Deck-Beispiele'
 def step(kind,**values):return {**new_step(kind),**values}
 aliases={'buttonId':'streamermod-status','deviceId':device}
 icon='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 144 144"><circle cx="72" cy="65" r="42" fill="#a970ff"/><text x="72" y="80" text-anchor="middle" font-size="46" fill="white">M</text></svg>'
 specifications={
 'Deck: Verbindung testen':[step(97101,**aliases,color='#302536'),step(97102,**aliases,image=icon),step(97104,**aliases,title='StreamerMod'),step(97105,**aliases,value='+=1'),step(97103,**aliases,state=1),step(97106,**aliases),step(97100,deviceId=device,title='StreamerMod',description='Verbunden',duration=1200)],
 'Deck: Regler +':[step(97105,buttonId='streamermod-dial',deviceId=device,value='+=1')],
 'Deck: Regler -':[step(97105,buttonId='streamermod-dial',deviceId=device,value='-=1')],
 'Deck: Nächste Seite':[step(97107,deviceId=device)],
 'Deck: Vorherige Seite':[step(97108,deviceId=device)],
 'Deck: Default-Profil':[step(97109,deviceId=device,page='Default')],
 }
 identities={}
 for name,nodes in specifications.items():
  existing=next((a for a in document['actions'] if a['group']==group and a['name']==name),None)
  if existing:identities[name]=existing['id'];continue
  action=new_action(name,group);action['subActions']=nodes;document['actions'].append(action);identities[name]=action['id']
 store.save('actions.json',document)
 template=json.loads((folder/'Default.json').read_text())
 state_template=copy.deepcopy(template['keys'][0]['states'][0])
 def instance(kind,context,settings,title):
  original=next(a for a in manifest['Actions'] if a['UUID']=='org.sorgobot.studio.'+kind)
  state={**state_template,'name':'','image':'plugins/org.sorgobot.studio.sdPlugin/icon.png','text':title,'alignment':'bottom','size':14}
  encoder={'background':'','icon':'','layout':'$A0','stack_color':'','trigger_description':{'long_touch':'','push':'Test','rotate':'Wert ändern','touch':''}} if kind=='dial' else None
  action={'controllers':original['Controllers'],'disable_automatic_states':True,'encoder':encoder,'icon':'plugins/org.sorgobot.studio.sdPlugin/icon.png','name':original['Name'],'plugin':'org.sorgobot.studio.sdPlugin','property_inspector':'plugins/org.sorgobot.studio.sdPlugin/inspector.html','states':[state,dict(state)],'supported_in_multi_actions':False,'tooltip':'StreamerMod','uuid':original['UUID'],'visible_in_action_list':True}
  return {'action':action,'children':None,'context':context,'current_state':0,'settings':settings,'states':[dict(state),dict(state)]}
 created=[]
 for name in ('StreamerMod','StreamerMod 2'):
  path=folder/(name+'.json')
  if path.exists():continue
  profile={key:[None]*len(value) if isinstance(value,list) else copy.deepcopy(value) for key,value in template.items()}
  if not profile.get('keys'):raise ValueError('Dieses Beispiel benötigt ein Deck mit Tasten')
  profile['keys'][0]=instance('button','Keypad.0.0',{'buttonId':'streamermod-status','actionId':identities['Deck: Verbindung testen']},'Test')
  for index,(label,key) in enumerate([('Default','Deck: Default-Profil'),('Zurück','Deck: Vorherige Seite'),('Weiter','Deck: Nächste Seite')],start=max(1,len(profile['keys'])-3)):
   if index<len(profile['keys']):profile['keys'][index]=instance('button',f'Keypad.{index}.0',{'actionId':identities[key]},label)
  if profile.get('sliders'):
   profile['sliders'][0]=instance('dial','Encoder.0.0',{'buttonId':'streamermod-dial','clockwiseActionId':identities['Deck: Regler +'],'counterclockwiseActionId':identities['Deck: Regler -'],'actionId':identities['Deck: Verbindung testen']},'Wert')
  path.write_text(json.dumps(profile,ensure_ascii=False,indent=2));created.append(name)
 return {'pluginVersion':manifest['Version'],'profilesCreated':created,'examples':identities,'deviceId':device}
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--device',required=True);args=parser.parse_args();print(json.dumps(setup(Path(__file__).resolve().parents[1],args.device),ensure_ascii=False,indent=2))
