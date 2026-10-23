"""Project-owned persistent password, kept outside public service settings."""
import json,secrets
from .catalog import ConfigStore,_CONFIG_LOCK
from .core import ActionError

FILE='websocket-auth.private.json'

def validate(password):
 if not isinstance(password,str) or not password.strip() or len(password)>256 or any(ord(c)<32 for c in password):raise ActionError('WebSocket-Passwort: 1–256 Zeichen, keine Steuerzeichen')
 return password


def password(root,create=True):
 with _CONFIG_LOCK:
  path=root/'config'/FILE
  if path.is_symlink():raise ActionError('WebSocket-Passwortdatei darf keine Verknüpfung sein')
  if not path.exists():
   if not create:return None
   value=secrets.token_urlsafe(32);save(root,value);return value
  try:
   if path.stat().st_size>8192:raise ValueError()
   value=json.loads(path.read_text())
   if not isinstance(value,dict) or value.get('version')!=1:raise ValueError()
   result=validate(value.get('password'));path.chmod(0o600);return result
  except (OSError,ValueError,TypeError,ActionError):raise ActionError('WebSocket-Passwortdatei ist ungültig; bei gestopptem Server ein neues Passwort setzen') from None


def save(root,value):
 validate(value)
 if (root/'config'/FILE).is_symlink():raise ActionError('WebSocket-Passwortdatei darf keine Verknüpfung sein')
 ConfigStore(root).save(FILE,{'version':1,'password':value})
