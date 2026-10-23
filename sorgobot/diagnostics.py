"""Small durable diagnostics: execution metadata, no argument/configuration dumps."""
import datetime,json,logging,re,os
from pathlib import Path
from logging.handlers import RotatingFileHandler
from zoneinfo import ZoneInfo

def log_directory(root):
 root=Path(root).resolve()
 return root.parent/'Logs' if root.name=='next-studio' and (root.parent/'StreamerMod').is_file() else root/'Logs'

class Diagnostics:
 def __init__(self,root,config=lambda:{}):
  self.directory=log_directory(root);self.directory.mkdir(parents=True,exist_ok=True);self.directory.chmod(0o700);self.config=config
  self.path=self.directory/('StreamerMod-'+datetime.datetime.now(ZoneInfo('Europe/Berlin')).strftime('%Y-%m-%d')+'.log')
  fd=os.open(self.path,os.O_CREAT|os.O_APPEND|os.O_WRONLY,0o600);os.close(fd)
  self.path.chmod(0o600)
  self.handler=RotatingFileHandler(self.path,maxBytes=2*1024*1024,backupCount=3,encoding='utf-8');self.handler.setFormatter(logging.Formatter('%(message)s'))
  for path in sorted(self.directory.glob('StreamerMod-*.log*'),key=lambda p:p.stat().st_mtime,reverse=True)[28:]:path.unlink(missing_ok=True)
 def clean(self,value):
  text=str(value)
  for key,secret in self.config().items():
   if any(part in key.lower() for part in ('token','password','secret','key')) and isinstance(secret,str) and secret:text=text.replace(secret,'[entfernt]')
  text=re.sub(r'(?i)\bBearer\s+[^\s"<>]+','Bearer [entfernt]',text)
  text=re.sub(r'https?://[^\s<>"\']+','[URL entfernt]',text)
  return text[:4000]
 def write(self,event,**fields):
  data={'time':datetime.datetime.now(ZoneInfo('Europe/Berlin')).isoformat(timespec='milliseconds'),'event':event}
  data.update({key:self.clean(value) for key,value in fields.items() if value is not None})
  self.handler.handle(logging.makeLogRecord({'msg':json.dumps(data,ensure_ascii=False),'levelno':logging.INFO,'levelname':'INFO'}))
 def close(self):self.handler.close()
