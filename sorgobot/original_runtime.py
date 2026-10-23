"""Original output contracts that differ from native convenience sub-actions."""
import asyncio,json,os,random,re,shlex
from pathlib import Path
from .core import ActionError,expand
from .core_logic import typed
MAX=2*1024*1024

async def operation(engine,node,args):
 kind=node['_originalSemantics'];io=engine.io
 get=lambda key,default='':expand(node.get(key,default),args)
 if kind=='suspiciousStatus':
  from .twitch_moderation_extended import operation as moderate
  args['addSuspiciousStatusResult']=False
  await moderate(io,node,args)
  if args.get('suspiciousResult'):
   args.update(addSuspiciousStatusResult=True,user=args['suspiciousUser'],userName=args['suspiciousUserName'],userId=args['suspiciousUserId'],userType=args['suspiciousUserType'])
  return
 if kind=='queuedAction':
  from .csharp_core import run_action
  result=await run_action(engine,get('actionId'),args,False,True)
  if not result.get('success'):raise ActionError('Zielaction für verzögerten Originalaufruf fehlt oder ist deaktiviert.')
  return
 if kind=='midi':
  from .csharp_midi import definitions
  identity=node.get('deviceGuid')
  import copy
  row=next((copy.deepcopy(row) for key,row in definitions(engine) if key==identity and row.get('enabled',True) and row.get('device')),None)
  if row is None:raise ActionError('Original-MIDI-Gerät muss auf einen aktiven Linux-Ausgang zugeordnet werden.')
  command={90152:144,90150:176}.get(node['type'])
  if command is None:command={'NoteOff':128,'NoteOn':144,'ControlChange':176,'PatchChange':192,'ChannelAfterTouch':208,'PitchWheelChange':224}.get(get('command'))
  if command is None:raise ActionError('Unbekannter Original-MIDI-Befehl.')
  try:
   channels=range(1,17) if get('channel') in ('',None) else [int(get('channel'))]
   data1=int(get('note',60)) if node['type']==90152 else int(get('control',0)) if node['type']==90150 else int(get('data1',0))
   data2=int(get('velocity',100)) if node['type']==90152 else int(get('value',0)) if node['type']==90150 else int(get('data2',0))
   duration=int(get('duration',0))
  except (ValueError,TypeError):raise ActionError('MIDI-Kanal, Daten und Dauer müssen ganze Zahlen sein.') from None
  if any(not 1<=channel<=16 for channel in channels) or not 0<=data1<=127 or not 0<=data2<=127 or duration<0:raise ActionError('MIDI-Werte außerhalb des gültigen Bereichs.')
  messages=[[command|(channel-1),data1,*([] if command in (192,208) else [0 if command==224 else data2])] for channel in channels]
  off=[[128|(channel-1),data1,0] for channel in channels] if command==144 and node.get('sendNoteOff',False) else None
  io.trace('midi',device=row['device'],messages=messages,simulated=io.dry_run)
  if io.dry_run:return
  from .midi_output import transmit
  def check():
   if not any(key==identity and current==row for key,current in definitions(engine)):raise ActionError('MIDI-Zuordnung wurde während der Ausgabe geändert.')
  await transmit(engine,row['device'],messages,duration/1000,off,check);return
 if kind=='randomUsers':
  from .twitch_user_selection import operation as select
  await select(engine,node,args);return
 if kind=='announce':
  from .csharp_twitch_controls import operation as controls
  color=get('color','Random')
  # The original Random choice selects one of Twitch's four fixed colors.
  if color=='Random':color=random.choice(('blue','green','orange','purple'))
  await controls(io,'TwitchAnnounce',[get('message'),node.get('useBot',True),color,node.get('fallbackToBroadcaster',True)]);return
 if kind=='pickColor':
  prefix=node.get('resultVariable') or 'color';alpha=int(node.get('alpha',255))
  if node.get('random'):r,g,b=(random.randrange(256) for _ in range(3))
  else:
   color=node['color'].lstrip('#');r,g,b=(int(color[i:i+2],16) for i in (0,2,4))
  args.update({prefix+'.color.a':alpha,prefix+'.color.r':r,prefix+'.color.g':g,prefix+'.color.b':b,prefix+'.html':f'#{r:02X}{g:02X}{b:02X}',prefix+'.htmlalpha':f'#{alpha:02X}{r:02X}{g:02X}{b:02X}',prefix+'.obs':(alpha<<24)|(b<<16)|(g<<8)|r});return
 if kind=='voiceCommand':
  services=getattr(engine,'services',None);target=next((r for r in services.config['voiceCommands'] if r['id']==node.get('voiceCommandId')),None) if services else None
  if target is None:raise ActionError('Voice Command muss zuerst zugeordnet werden.')
  services.set_entry('voiceCommands',target['id'],{'command':get('command')});return
 if kind=='sound':
  from .csharp_sounds import rpc as sound
  result=await sound(engine,'sound_play',['folder' if node['type']==90142 else 'file',get('path'),float(node['volume'])/100,node.get('recursive',False),node.get('finishBeforeContinuing',True),get('playbackId') or None,node.get('useFileNameAsName',True)],audio_device=get('audioDevice','@default'))
  args['soundDuration']=result;return
 if kind=='addQuote':
  from .core_operations import operation as core_operation
  await core_operation(engine,{**node,'text':get('text')},args);return
 if kind=='clip':
  args['createClipSuccess']=False
  if io.dry_run:io.trace('twitch_clip_preview',simulated=True);return
  from .csharp_twitch_clips import create
  result=await create(io,get('title') or None,int(get('duration',30)))
  if result:args.update(createClipSuccess=True,createClipId=result['Id'],createClipUrl=result['Url'],createClipCreatedAt=result.get('CreatedAt'),clipDuration=result.get('Duration',0)*1000)
  return
 if kind=='game':
  args['gameSuccess']=False
  if node.get('source',0)==1:
   from .csharp_twitch_controls import operation as controls
   await controls(io,'SetChannelGameById',[get('gameId')])
   if not io.dry_run:args.update(gameSuccess=True,gameId=get('gameId'),gameName=get('game'))
  else:
   from .csharp_twitch_data import operation as data
   result=await data(io,'SetChannelGame',[get('game')])
   if result:args.update(gameSuccess=True,gameName=result.get('Name'),gameId=result.get('Id'),gameBoxArt=result.get('BoxArtUrl'))
  return
 if kind=='message':
  message=get('text')
  if not isinstance(message,str) or not message.strip():raise ActionError('Chatnachricht ist leer. Prüfe den Text und seine Variablen.')
  bot=node.get('useBot',True);fallback=node.get('fallback',True)
  if io.dry_run:io.trace('chat',text=message,bot=bot);return
  from .twitch_chat_actions import Chat,operation as chat_operation
  result=await Chat(io).reply(None,message,bot,fallback)
  if node.get('pin') and not result.get('preview'):
   await chat_operation(io,{'type':91802,'messageId':result['messageId'],'duration':None if node.get('pinToStreamEnd') else 1200},args)
  return
 if kind in ('globalGet','globalSet'):
  name=get('variableName');persisted=node.get('persisted',True)
  selection=node.get('source',0) if kind=='globalGet' else node.get('destination',0)
  user=args.get('userId') if selection==1 else args.get('targetUserId') if selection==2 else None
  platform=args.get('userType',args.get('platform','twitch'))
  if selection and not user:raise ActionError('Nutzer-ID für Original-Global fehlt')
  storage=name if user is None else 'core:user:'+json.dumps((platform,user,name))
  key=name if user is None else (platform,user,name)
  session=engine.session_globals if user is None else engine.user_session_globals
  missing=object();current=engine.state.get(storage,missing) if persisted else session.get(key,missing)
  from .core_events import set_global
  if kind=='globalGet':
   if current is missing:
    current=node.get('defaultValue')
    if current is not None:set_global(engine,name,current,persisted,user=user,platform=platform)
   args[get('destinationVariable')]=current
  else:
   value=typed(get('value'),node.get('autoType',False));mode=node.get('source',0)
   if mode:
    try:value=(0 if current is missing else int(current))+(1 if mode==1 else -1)*int(value if value not in ('',None) else 1)
    except (TypeError,ValueError):raise ActionError('Global Increment/Decrement benötigt ganze Zahlen') from None
   set_global(engine,name,value,persisted,user=user,platform=platform)
  return
 if kind=='random':
  if node.get('randomType',0)==0:args['randomNumber']=random.randint(int(get('minimum')),int(get('maximum')))
  else:
   value=random.random();args.update(randomFloat=value,randomPercent=int(value*100))
  return
 if kind=='fetch':
  name=node.get('resultVariable') or 'result'
  if io.dry_run:io.trace('http',method='GET',simulated=True);return
  import aiohttp
  try:
   async with io.session.get(get('url'),headers={k:expand(v,args) for k,v in node.get('headers',{}).items()},timeout=aiohttp.ClientTimeout(total=60)) as reply:
    if reply.status>=400:raise ActionError('HTTP '+str(reply.status)+': Zugang oder Dienst prüfen')
    chunks=[];size=0
    async for chunk in reply.content.iter_chunked(65536):
     size+=len(chunk)
     if size>MAX:raise ActionError('HTTP-Antwort überschreitet 2 MiB')
     chunks.append(chunk)
    data=b''.join(chunks)
    text=data.decode(reply.charset or 'utf-8')
    args[name]=json.loads(text) if node.get('parseAsJson') else typed(text,node.get('autoType',False))
  except (aiohttp.ClientError,TimeoutError,UnicodeError,json.JSONDecodeError):raise ActionError('Original-HTTP-Abfrage fehlgeschlagen') from None
  return
 if kind=='program':
  program=get('program');arguments=node.get('arguments',[])
  argv=shlex.split(expand(arguments,args)) if isinstance(arguments,str) else [expand(str(v),args) for v in arguments]
  if io.dry_run:io.trace('program',program=program,simulated=True);return
  env=dict(os.environ);extra=node.get('envVars') or {}
  if not isinstance(extra,dict):raise ActionError('Programm-Umgebung muss ein JSON-Objekt sein')
  env.update({str(k):str(expand(v,args)) for k,v in extra.items()})
  wait=float(get('waitForExit',0))
  if wait==0:
   proc=await asyncio.create_subprocess_exec(program,*argv,cwd=get('workingDir') or None,env=env,stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.DEVNULL,start_new_session=True)
   jobs=getattr(io,'_import_process_waiters',None)
   if jobs is None:jobs=io._import_process_waiters=set()
   task=asyncio.create_task(proc.wait());jobs.add(task);task.add_done_callback(jobs.discard);return
  proc=await asyncio.create_subprocess_exec(program,*argv,cwd=get('workingDir') or None,env=env,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
  async def capture():
   async def read(stream):
    chunks=[];size=0
    while chunk:=await stream.read(65536):
     size+=len(chunk)
     if size>MAX:raise ActionError('Programmausgabe überschreitet 2 MiB')
     chunks.append(chunk)
    return b''.join(chunks)
   stdout,stderr=await asyncio.gather(read(proc.stdout),read(proc.stderr));await proc.wait();return stdout,stderr
  try:stdout,stderr=await asyncio.wait_for(capture(),float(get('waitForExit',30)))
  except BaseException:
   if proc.returncode is None:proc.kill()
   await proc.wait();raise
  text=stdout.decode('utf-8',errors='replace');lines=text.splitlines()
  args.update(programOutput=text,outputCount=len(lines),exitCode=proc.returncode)
  for index,line in enumerate(lines):args['output'+str(index)]=line
  return
 path=Path(get('path')).expanduser()
 if not path.is_absolute():path=io.root/path
 args['fileFound']=path.is_file()
 if not args['fileFound']:return
 if path.stat().st_size>MAX:raise ActionError('Importierte Textdatei überschreitet 2 MiB')
 lines=(await asyncio.to_thread(path.read_text,encoding='utf-8-sig')).splitlines();name=node.get('resultVariable') or 'line'
 def value(text):return typed(expand(text,args) if node.get('parseVariables') else text,node.get('autoType',False))
 if kind=='lines':
  args['lineCount']=len(lines)
  for index,line in enumerate(lines):args[name+str(index)]=value(line)
 elif kind=='line':
  index=int(get('line',1))-1
  if not 0<=index<len(lines):raise ActionError('Original-Zeilennummer außerhalb der Datei (erste Zeile: 1)')
  args[name]=value(lines[index])
 elif kind=='randomLine':
  count=int(get('count',1))
  if count<1:raise ActionError('Anzahl zufälliger Zeilen muss mindestens 1 sein')
  selected=random.choices(range(len(lines)),k=count) if node.get('overwrite',False) and lines else random.sample(range(len(lines)),min(count,len(lines)))
  for index,number in enumerate(selected):
   suffix=str(index) if index else ''
   args[name+suffix]=value(lines[number]);args[name+'Number'+suffix]=number
