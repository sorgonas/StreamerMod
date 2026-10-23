"""Read model inventories without treating cloud catalogues as local installations."""
import hashlib,json,re
from urllib.parse import urlsplit,urlunsplit

OPENAI='https://api.openai.com/v1'
POLICY=2
class InventoryError(ValueError):pass

def base_url(value):
 if not isinstance(value,str):raise InventoryError('Adresse des KI-Diensts fehlt.')
 parsed=urlsplit(value.strip())
 try:port=parsed.port
 except ValueError:raise InventoryError('Ungültiger Port des KI-Diensts.') from None
 if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:raise InventoryError('Eine gültige http(s)-Adresse ohne Zugangsdaten oder URL-Parameter eintragen.')
 return urlunsplit((parsed.scheme,parsed.netloc,parsed.path.rstrip('/'),'',''))

def context(provider,values):
 address=OPENAI if provider=='openai' else base_url(values.get('llm_url',''))
 key=values.get('openai_key' if provider=='openai' else 'llm_key','').strip()
 return hashlib.sha256(json.dumps([POLICY,provider,address,key],ensure_ascii=True).encode()).hexdigest()

def requests(provider,values):
 if provider=='openai':return [(OPENAI+'/models','openai')]
 base=base_url(values.get('llm_url',''));parsed=urlsplit(base)
 # Preserve reverse-proxy prefixes, and never probe another host or port.
 prefix=parsed.path
 for suffix in ('/v1','/api/v1','/api/v0','/api'):
  if prefix.endswith(suffix):prefix=prefix[:-len(suffix)];break
 origin=urlunsplit((parsed.scheme,parsed.netloc,prefix,'',''))
 candidates=[(origin+'/api/v1/models','lmstudio'),(origin+'/api/v0/models','lmstudio-v0'),(origin+'/api/tags','ollama'),(base+'/models','compatible')]
 return list(dict.fromkeys(candidates))

def openai_chat(model):
 if not isinstance(model,str) or not model or '/' in model:return False
 # Fine-tuned models retain the base model identity, and come from /v1/models
 # on api.openai.com, never from a local proxy's vendor catalogue.
 base=model.split(':',2)[1] if model.startswith('ft:') and ':' in model[3:] else model
 if not re.match(r'^(?:gpt-|chatgpt-|o[1-9]\d*(?:-|$))',base):return False
 return not re.search(r'(?:^|[-_.])(?:audio|realtime|transcribe|tts|image|embedding|embeddings|moderation|search|research|codex|instruct|oss)(?:[-_.]|$)',base)

def rows(payload,key):
 if not isinstance(payload,dict) or not isinstance(payload.get(key),list):raise InventoryError('Der Dienst liefert keine gültige Modellliste.')
 if len(payload[key])>10000:raise InventoryError('Die Modellliste ist zu groß.')
 if any(not isinstance(item,dict) for item in payload[key]):raise InventoryError('Ungültiger Eintrag in der Modellliste.')
 return payload[key]

def identity(value):
 return value.strip() if isinstance(value,str) and value.strip() and len(value)<=1000 and not any(ord(c)<32 for c in value) else ''

def local_evidence(item,server):
 if item.get('downloaded') is False or item.get('installed') is False or item.get('is_remote') is True:return False
 if str(item.get('location','')).lower() in ('cloud','remote') or str(item.get('provider','')).lower() in ('openai','openrouter','anthropic','google'):return False
 name=identity(item.get('id'));owner=str(item.get('owned_by','')).lower()
 if owner in ('openai','openai-internal','system','openrouter','anthropic','google'):return False
 if owner in ('local','llama.cpp','llamacpp','lmstudio','lm-studio','ollama','vllm','tgi'):return True
 if item.get('downloaded') is True or item.get('installed') is True or name.lower().endswith('.gguf'):return True
 # A provider catalogue is not an installation inventory, even on a LAN URL.
 if 'hermeski-bridge' in server.lower() or 'openrouter' in server.lower():return False
 if any(k in item for k in ('pricing','top_provider','hugging_face_id')):return False
 return False # An opaque model ID alone does not prove local installation.

def inventory(payload,kind,server=''):
 chat=[];vision=[];unknown_vision=False
 if kind=='openai':
  chat=[identity(item.get('id')) for item in rows(payload,'data') if openai_chat(item.get('id'))]
  return {'chat':sorted(set(filter(None,chat))),'vision':[],'source':'OpenAI','visionKnown':True}
 if kind=='lmstudio':
  values=rows(payload,'models')
  for item in values:
   if item.get('type')!='llm' or item.get('downloaded') is False or item.get('installed') is False:continue
   name=identity(item.get('key'))
   if not name:continue
   chat.append(name);cap=item.get('capabilities',{})
   if isinstance(cap,dict) and cap.get('vision') is True:vision.append(name)
   elif not isinstance(cap,dict) or 'vision' not in cap:unknown_vision=True;vision.append(name)
  source='LM Studio (installiert)'
 elif kind=='lmstudio-v0':
  for item in rows(payload,'data'):
   if item.get('type') not in ('llm','vlm') or item.get('downloaded') is False or item.get('installed') is False:continue
   name=identity(item.get('id'))
   if name:chat.append(name)
   if name and item.get('type')=='vlm':vision.append(name)
  source='LM Studio (installiert)'
 elif kind=='ollama':
  for item in rows(payload,'models'):
   if item.get('remote_host') or item.get('remote_model') or item.get('is_remote') is True:continue
   name=identity(item.get('model') or item.get('name'))
   if not name:continue
   capabilities=item.get('capabilities')
   if isinstance(capabilities,list) and 'completion' not in capabilities and 'vision' not in capabilities:continue
   chat.append(name)
   if isinstance(capabilities,list):
    if 'vision' in capabilities:vision.append(name)
   else:unknown_vision=True;vision.append(name)
  source='Ollama (installiert)'
 else:
  values=rows(payload,'data')
  for item in values:
   if not local_evidence(item,server):continue
   name=identity(item.get('id'))
   if not name or str(item.get('type','')).lower() in ('embedding','embeddings','image','audio'):continue
   chat.append(name)
   cap=item.get('capabilities')
   if isinstance(cap,dict):
    if cap.get('vision') is True:vision.append(name)
    elif 'vision' not in cap:unknown_vision=True;vision.append(name)
   elif isinstance(cap,list):
    if 'vision' in cap:vision.append(name)
   else:unknown_vision=True;vision.append(name)
  if values and not chat:raise InventoryError('Die Antwort bestätigt keinen installierten lokalen Modellbestand. Ein Cloud-/Angebotskatalog wird nicht als Installation übernommen. Bei einer Bridge den lokalen Modellbestand bzw. die Adresse des lokalen Modellservers bereitstellen.')
  source='Lokaler Modellserver'
 return {'chat':sorted(set(chat)),'vision':sorted(set(vision)),'source':source,'visionKnown':not unknown_vision}
