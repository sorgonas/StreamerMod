"""Account-free defaults for a new installation; never copy another user's setup."""
from copy import deepcopy
from .catalog import PROMPTS

def local_defaults():
 return {'channel':'','bots':[],'obs_url':'ws://127.0.0.1:4455','obs_password':'','obs_enabled':False,'obs_auto_connect':False,'obsConnections':[],
 'twitch_client_id':'','twitch_token':'','twitch_bot_token':'','twitch_refresh_token':'','twitch_bot_refresh_token':'','broadcaster_id':'','bot_id':'','twitch_login':'','twitch_bot_login':'','twitch_scopes':[],'twitch_bot_scopes':[],
 'ai_provider':'local','llm_provider':'local','llm_url':'','llm_key':'','llm_model':'','vision_model':'','openai_key':'','openai_model':'','bridge_enabled':False,'reply_probability':0,'reply_to_broadcaster':False,
 'tts_voice':'de','keyboard_device':'','microphone':'','headset':'','camera_enabled':False,'camera_device':'0','source_aliases':{},'own3d_token':'','own3d_effects':{},'voice_url':'','voice_token':'','summary_token':'','webhooks':{}}

def documents():
 from .service_management import DEFAULTS
 services=deepcopy(DEFAULTS)
 for value in services.values():
  if 'autoStart' in value:value['autoStart']=False
 return {'actions.json':{'actions':[],'queues':[]},'commands.json':{'commands':[]},'timers.json':[], 'custom.json':{},'games.json':{'games':[],'fallbackCategory':'Just Chatting'},'core.json':{},'services.json':services,'youtube.json':{'autoConnect':False,'broadcastId':''},'local.json':local_defaults(),'prompts.json':{k:v[1] for k,v in PROMPTS.items()}}
