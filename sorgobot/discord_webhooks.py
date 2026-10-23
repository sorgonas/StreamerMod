"""Discord basic webhooks with private local URL storage and confirmed delivery."""
import copy,json,re,uuid
from urllib.parse import urlsplit,parse_qsl,urlencode,urlunsplit
from aiohttp import ClientError,ClientTimeout
from .core import ActionError
from .youtube_auth import private_write

KIND=97300
DEFAULTS={'webhookName':'Discord','webhookUrl':'','content':'%rawInput%','username':'','avatarUrl':'','textToSpeech':False,'allowMentions':False}

def webhook_url(value):
 if not isinstance(value,str):raise ActionError('Discord-Webhook-URL fehlt')
 try:parts=urlsplit(value);port=parts.port
 except ValueError:raise ActionError('Ungültige Discord-Webhook-URL') from None
 if parts.scheme!='https' or parts.hostname not in ('discord.com','discordapp.com','canary.discord.com','ptb.discord.com') or port not in (None,443) or parts.username or parts.password or parts.fragment or not re.fullmatch(r'/api(?:/v\d{1,2})?/webhooks/\d{1,20}/[A-Za-z0-9_.-]{10,200}',parts.path):raise ActionError('Eine gültige HTTPS-Discord-Webhook-URL angeben')
 params=dict(parse_qsl(parts.query))
 if set(params)-{'wait','thread_id'} or 'thread_id' in params and not params['thread_id'].isdigit():raise ActionError('Ungültige Discord-Webhook-Parameter')
 params['wait']='true'
 return urlunsplit((parts.scheme,parts.netloc,parts.path,urlencode(params),''))

def private_path(root):return root/'config/discord-webhooks.private.json'

def read(root):
 path=private_path(root)
 if not path.exists():return {}
 try:
  values=json.loads(path.read_text())
  if not isinstance(values,dict) or any(not isinstance(k,str) or not isinstance(v,str) for k,v in values.items()):raise ValueError()
  return values
 except (OSError,ValueError):raise ActionError('Private Discord-Webhook-Konfiguration ist ungültig') from None

def save_url(root,node):
 """Never put the bearer secret into public action JSON or copied exports."""
 value=node.get('webhookUrl','')
 if not value:return
 webhook_url(value)
 values=read(root);identity=str(uuid.uuid4());values[identity]=value
 private_write(private_path(root),values)
 node['_discordWebhookId']=identity;node['webhookUrl']=''

def resolve(root,node):
 value=node.get('webhookUrl') or read(root).get(node.get('_discordWebhookId',''),'')
 return webhook_url(value)

def payload(node):
 content=node.get('content','')
 if not isinstance(content,str) or not 1<=len(content)<=2000:raise ActionError('Discord-Inhalt: 1–2000 Zeichen erforderlich')
 for field in ('textToSpeech','allowMentions'):
  if type(node.get(field,False)) is not bool:raise ActionError('Ungültige Discord-Option')
 result={'content':content,'tts':node.get('textToSpeech',False),'allowed_mentions':{'parse':['users','roles','everyone'] if node.get('allowMentions') else []}}
 username=node.get('username','');avatar=node.get('avatarUrl','')
 if not isinstance(username,str) or len(username)>80:raise ActionError('Discord-Benutzername: höchstens 80 Zeichen')
 if username:result['username']=username
 if avatar:
  try:url=urlsplit(avatar)
  except (TypeError,ValueError):raise ActionError('Ungültige Discord-Avatar-URL') from None
  if url.scheme not in ('http','https') or not url.hostname or url.username or url.password:raise ActionError('Discord-Avatar benötigt eine HTTP(S)-URL')
  result['avatar_url']=avatar
 return result

async def operation(io,node,args):
 if io.dry_run:
  io.trace('discord_webhook',simulated=True);args['discordPreview']=True;return
 body=payload(node);url=resolve(io.root,node)
 io.trace('discord_webhook',simulated=False)
 try:
  async with io.session.post(url,json=body,timeout=ClientTimeout(total=15),allow_redirects=False) as response:
   if response.status==429:raise ActionError('Discord-Rate-Limit erreicht; keine automatische Wiederholung')
   if response.status>=300:raise ActionError('Discord-Webhook abgewiesen (HTTP '+str(response.status)+')')
   try:result=await response.json()
   except (ClientError,ValueError):raise ActionError('Discord hat keine Nachrichten-ID bestätigt; nicht automatisch wiederholen') from None
   if not isinstance(result,dict) or not isinstance(result.get('id'),str) or not result['id']:raise ActionError('Discord hat keine Nachrichten-ID bestätigt; nicht automatisch wiederholen')
 except (ClientError,TimeoutError):raise ActionError('Discord-Verbindung fehlgeschlagen; Ergebnis prüfen, nicht automatisch wiederholen') from None
 args['messageId']=result['id'];args['discordPreview']=False
