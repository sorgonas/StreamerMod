"""Explicit Windows device references mapped to current Linux audio names."""
from .original_graph import canonical,ZERO

TYPES={1:'output',7:'output',1025:'input'}

def convert(source,out):
 kind=source['type'];field='audioDeviceId' if kind==1025 else 'device';value=source.get(field)
 default=value in (None,'','Default','default',ZERO)
 if not default and not canonical(value):return ['Original-Audiogerät benötigt eine gültige GUID.']
 out.pop(field,None)
 if kind==1025:out.pop('audioDeviceName',None)
 out['audioDevice']='@default' if default else ''
 name=source.get('audioDeviceName','') if kind==1025 else ''
 out['_originalAudio']={'direction':TYPES[kind],'source':value or ZERO,'name':name if isinstance(name,str) else ''}
 return []

def apply(node,bindings):
 ref=node.get('_originalAudio')
 if ref:
  section='audioInputs' if ref['direction']=='input' else 'audioOutputs'
  node['audioDevice']=bindings.get(section,{}).get(ref['source'],node.get('audioDevice',''))

def validate(node,resources):
 ref=node.get('_originalAudio')
 if not ref:return []
 target=node.get('audioDevice')
 if not isinstance(target,str) or not target.strip() or len(target)>500 or any(ord(c)<32 for c in target):return ['Original-Audiogerät auf einen Linux-'+('Eingang' if ref['direction']=='input' else 'Ausgang')+' zuordnen.']
 if target!='@default':
  rows=[r for r in resources.get('audioDevices',[]) if r.get('kind')==ref['direction'] and r.get('name')==target]
  if len(rows)!=1:return ['Zugeordnetes Audiogerät fehlt oder ist mehrdeutig: '+target]
 node['_originalAudioTarget']=target
 return []

def export_check(node):
 if node.get('_originalAudio') and node.get('audioDevice')!=node.get('_originalAudioTarget',node.get('_baseline',{}).get('audioDevice')):
  raise ValueError('Bearbeitetes Linux-Audiogerät bitte als Linux-JSON exportieren. Das Originalformat behält die Windows-Gerätereferenz.')
