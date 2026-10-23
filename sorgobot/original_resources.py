"""Stage dependencies disabled, then persist all import files with rollback."""
import copy
from .catalog import _CONFIG_LOCK

def stage(document,envelope):
 staged={};issues=[]
 for section in ('commands','timers'):
  rows=[]
  for raw in envelope['data'].get(section,[]):
   issues=[];row=copy.deepcopy(raw);row['enabled']=False
   if not isinstance(row.get('name'),str) or not row['name'].strip():raise ValueError('Original-Abhängigkeit ohne Namen: '+section)
   if section=='commands':
    if not isinstance(row.get('command'),str) or not row['command'].strip():raise ValueError('Importierter Command enthält keinen Befehlstext.')
    for field in ('permittedUsers','permittedGroups'):
     if not isinstance(row.get(field,[]),list):raise ValueError('Ungültige Command-Berechtigungsliste.')
    if any(not isinstance(v,str) for v in row.get('permittedGroups',[])):raise ValueError('Ungültige Command-Gruppenrechte.')
    row['ignoreInternalMessages']=row.pop('ignoreInternal',True)
    grant=row.pop('grantType',0)
    if grant not in (0,1):issues.append('Command-Rechtemodus ist unbekannt: '+str(grant))
    row['permissionMode']='deny' if grant==1 else 'allow'
    if any(not isinstance(u,str) for u in row.get('permittedUsers',[])):issues.append('Command-Nutzerrechte benötigen eine ID-/Login-Zuordnung.')
    if row.get('regexExplicitCapture'):issues.append('Regex Explicit Capture muss für diesen Command gesondert migriert werden.')
    if type(row.get('sources',1)) is not int or row.get('sources',1)&~31:issues.append('Command enthält Quellen außerhalb des Twitch-Umfangs.')
   else:
    for key in ('interval','upperInterval','lines'):
     if type(row.get(key,0)) is not int or row.get(key,0)<0:issues.append('Timer enthält einen ungültigen Wert: '+key)
    row.setdefault('interval',60);row.setdefault('upperInterval',row['interval']);row.setdefault('lines',0);row.setdefault('repeat',True);row.setdefault('randomInterval',False)
   row['_importProblems']=list(issues)
   if issues:row['migrationBlock']='Original-Abhängigkeit: '+'; '.join(issues)
   rows.append(row)
  staged[section]=rows
 sockets=[]
 from urllib.parse import urlsplit
 for section,mode in (('websocketClients','client'),('websocketServers','server')):
  for raw in envelope['data'].get(section,[]):
   if not isinstance(raw.get('name'),str) or not raw['name'].strip():raise ValueError('Original-WebSocket ohne Namen.')
   row={'id':raw['id'],'name':raw['name'],'mode':mode,'enabled':False};problems=[]
   if mode=='client':
    endpoint=raw.get('endpoint','')
    if not isinstance(endpoint,str):raise ValueError('Original-WebSocket-Adresse muss Text sein.')
    parsed=urlsplit(endpoint)
    if parsed.scheme not in ('ws','wss') or not parsed.hostname:raise ValueError('Original-WebSocket-Client benötigt eine ws:// oder wss:// Adresse.')
    row.update(url=endpoint,reconnect=raw.get('reconnectOnDisconnect',True),retryInterval=raw.get('retryInterval',3),enableCompression=raw.get('enableCompression',False))
    if raw.get('tlsProtocols',0):problems.append('Explizite Windows-TLS-Auswahl muss geprüft werden.')
   else:
    port=raw.get('port');endpoint=raw.get('endpoint') or '/'
    if type(port) is not int or not 1<=port<=65535 or not isinstance(endpoint,str) or not endpoint.startswith('/'):raise ValueError('Ungültiger Original-WebSocket-Server.')
    row.update(port=port,endpoint=endpoint,url='ws://127.0.0.1:'+str(port)+endpoint)
    if raw.get('address') not in (None,'','127.0.0.1','localhost'):problems.append('Original-Serveradresse ist nicht lokal; Bind-Adresse prüfen.')
   if raw.get('messageQueue'):problems.append('Original-WebSocket-Message-Queue benötigt eine gesonderte Zuordnung.')
   row['_importProblems']=problems
   if problems:row['migrationBlock']='Original-WebSocket: '+'; '.join(problems)
   sockets.append(row)
 staged['websocketConnections']=sockets
 document.setdefault('pendingOriginalResources',{})
 for section,rows in staged.items():
  document['pendingOriginalResources'].setdefault(section,[]).extend(rows)
  document.setdefault('originalResources',{}).setdefault(section,[]).extend(copy.deepcopy(rows))

def commit(store,document,save_actions):
 """Caller owns the document. Never mutate the live document on failed writes."""
 pending=document.get('pendingOriginalResources',{})
 if not any(pending.values()):return save_actions()
 with _CONFIG_LOCK:
  updates={};before={}
  for section,rows in pending.items():
   if section=='websocketConnections':
    from .core_services import read_config
    name='core.json';value=read_config(store.root);target=value['websocketConnections']
   else:name=section+'.json';value=store.read(name);target=value['commands'] if section=='commands' else value
   existing={r['id'].casefold():r for r in target}
   for row in rows:
    if row['id'].casefold() in existing:
     if existing[row['id'].casefold()]!=row:raise ValueError('Importierte '+section+'-ID kollidiert mit einem vorhandenen Eintrag.')
    else:target.append(copy.deepcopy(row));existing[row['id'].casefold()]=row
   updates[name]=value
  for name in (*updates,'actions.json'):
   path=store.root/'config'/name;before[name]=path.read_bytes() if path.exists() else None
  document.pop('pendingOriginalResources',None)
  try:
   for name,value in updates.items():store.save(name,value)
   return save_actions()
  except BaseException:
   document['pendingOriginalResources']=pending
   for name,data in before.items():
    path=store.root/'config'/name
    if data is None:path.unlink(missing_ok=True)
    else:temp=path.with_suffix('.rollback');temp.write_bytes(data);temp.replace(path)
   raise
