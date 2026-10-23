"""Allowlisted Core/Raw observers. Never serialize execution arguments wholesale."""
import copy
EVENTS={
 90210:('FileWatcher','Changed'),90211:('FileWatcher','Created'),90212:('FileWatcher','Deleted'),90213:('FileWatcher','Renamed'),90200:('FileTail','Changed'),
 90245:('Midi','Message'),90240:('Inputs','KeyPress'),90241:('Inputs','MouseClick'),90250:('System','ClipboardChanged'),
 90260:('WebsocketClient','Open'),90261:('WebsocketClient','Close'),90262:('WebsocketClient','Message'),90263:('WebsocketCustomServer','Open'),90264:('WebsocketCustomServer','Close'),90265:('WebsocketCustomServer','Message'),
 701:('Misc','TimedAction'),90040:('Misc','StreamerbotStarted'),90041:('Misc','Test'),90214:('Misc','ProcessStarted'),90215:('Misc','ProcessStopped'),90251:('Misc','ToastActivation'),
 90220:('Misc','GlobalVariableCreated'),90221:('Misc','GlobalVariableDeleted'),90222:('Misc','GlobalVariableUpdated'),90223:('Misc','UserGlobalVariableUpdated'),
 90230:('Group','Added'),90231:('Group','Cleared'),90232:('Group','Removed'),90233:('Group','UsersAdded'),90234:('Group','UsersRemoved')}
CATEGORIES={'Raw':['Action','SubAction','ActionCompleted']}
for source,event in EVENTS.values():
 if event not in CATEGORIES.setdefault(source,[]):CATEGORIES[source].append(event)

FIELDS={
 'FileWatcher':'changeType watcherId watcherName watcherFilter watcherFolder fileName fullPath isDirectory oldFilename oldFullPath fileSize empty contentTruncated lineCount fileReadError',
 'FileTail':'fileTailId fileTailName filePath fileName lines count lineCount text',
 'Midi':'midiDeviceId deviceName name commandCode commandCodeNum channel data1 data2 value valueNormal rawMessage timestamp noteNumber noteName velocity controlNumber patchNumber pitchValue',
 'Inputs':'inputDeviceId inputDeviceName keys key hasCtrl hasShift hasAlt button buttonCode value',
 'System':'clipboardText text',
 'WebsocketClient':'connectionId connectionName connectionIndex message data',
 'WebsocketCustomServer':'connectionId connectionName connectionIndex sessionId clientId message data',
 'Misc':'timerId timerName repeat interval count processId processName processNames processPath pid name toastId activationLabel',
 'Group':'groupId groupName users userCount'}

def publish(engine,source,event,body):
 hub=getattr(getattr(engine,'studio',None),'main_websocket',None)
 if hub is not None:hub.publish(source,event,body)

def forward(engine,kind,args):
 if kind not in EVENTS:return
 source,event=EVENTS[kind];body={key:copy.deepcopy(args[key]) for key in FIELDS[source].split() if key in args}
 if source in ('FileWatcher','FileTail'):
  import re
  body.update({k:copy.deepcopy(v) for k,v in args.items() if isinstance(k,str) and re.fullmatch(r'line(?:Escaped)?\d+',k)})
 if kind in (90220,90221,90222,90223):
  body['variable']={target:copy.deepcopy(args[key]) for target,key in {'name':'global.name','value':'global.newValue','previousValue':'global.oldValue','persisted':'global.persisted','lastWrite':'global.lastWrite'}.items() if key in args}
  for key in ('userId','platform'):
   if key in args:body[key]=args[key]
 publish(engine,source,event,body)

def action(engine,event,record,status=None):
 body={key:record[key] for key in ('id','actionId','name','queueId','queue','queuedAt','startedAt','completedAt','duration') if key in record}
 if status is not None:body['status']=status
 publish(engine,'Raw',event,body)

def subaction(engine,action,node):
 publish(engine,'Raw','SubAction',{'actionId':action['id'],'id':node.get('id'),'type':node['type']})
