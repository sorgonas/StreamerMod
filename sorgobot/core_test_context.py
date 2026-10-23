"""Representative Core test arguments. Never reads files or captures hardware."""
from pathlib import Path
from .core import ActionError

def examples(trigger,config):
    kind=trigger['type'];result={}
    sections={'watcherId':'fileWatchers','fileTailId':'fileTails','voiceCommandId':'voiceCommands','groupId':'userGroups','inputDeviceId':'inputDevices','midiDeviceId':'midiDevices','connectionId':'websocketConnections','scheduleId':'cronSchedules'}
    chosen={}
    for key,section in sections.items():
        if key not in trigger:continue
        identity=trigger[key];items=config.get(section,[])
        item=next((v for v in items if v['id']==identity),None) if identity else next((v for v in items if v.get('enabled',True)),None)
        if identity and item is None:raise ActionError('Der im Trigger ausgewählte Eintrag wurde gelöscht: '+section)
        chosen[key]=item or {'id':'','name':'Test'}
        result[key]=chosen[key]['id']
    if kind in (90210,90211,90212,90213):
        item=chosen['watcherId'];path=Path(item.get('path','/tmp'))
        file=path/'test.txt' if item.get('folder',True) else path
        folder=file.parent;change={90210:'Changed',90211:'Created',90212:'Deleted',90213:'Renamed'}[kind]
        result.update(changeType=change,watcherName=item['name'],watcherFolder=str(folder),watcherFilter=item.get('filter','*'),fullPath=str(file),fileName=file.name,isDirectory=False)
        if kind==90213:result.update(oldFilename='old-test.txt',oldFullPath=str(folder/'old-test.txt'))
        if kind in (90210,90211):
            result.update(fileSize=9,empty=False)
            if item.get('readContents'):result.update(lineCount=1,line0='Test text',lineEscaped0='Test%20text',contentTruncated=False)
    elif kind==90200:
        item=chosen['fileTailId'];result.update(fileTailName=item['name'],filePath=item.get('path',''),line='Test text',fileLine='Test text',rawInput='Test text')
    elif kind in (90214,90215):
        name=trigger.get('processName') or 'test-process';result.update(processId=0,parentProcessId=0,executable=name,name=name,fullPath='/test/'+name,path='/test',processNames=[name])
    elif kind in (90220,90221,90222,90223):
        name=trigger.get('variableName') or 'testVariable';persisted=trigger.get('persisted');persisted=True if persisted=='either' else bool(persisted)
        result.update({'variableName':name,'global.name':name,'global.oldValue':None if kind==90220 else 'old','global.newValue':None if kind==90221 else 'new','global.persisted':persisted,'persisted':persisted,'global.lastWrite':'2000-01-01T00:00:00+00:00'})
    elif kind in (90230,90231,90232,90233,90234):
        result['groupName']=chosen['groupId']['name']
        if kind in (90233,90234):result.update(users=['testuser'],userCount=1)
    elif kind==90240:
        from .linux_inputs import key_names
        names=key_names(trigger.get('keys',''));result.update(hasCtrl=any('CTRL' in n for n in names),hasShift=any('SHIFT' in n for n in names),hasAlt=any('ALT' in n for n in names),key=0)
    elif kind in (90241,90242):result['value']=1
    elif kind in (90243,90244):result['value']=int(trigger.get('direction',1)) if kind==90244 else int(trigger.get('minValue',0))
    elif kind==90245:
        from .linux_inputs import MidiDecoder
        command=trigger.get('commandCode') or 'NoteOn';channel=int(trigger.get('channel') or 1);note=int(trigger.get('data1',-1));note=60 if note<0 else note
        statuses={'NoteOn':0x90,'NoteOff':0x80,'ControlChange':0xb0,'KeyAfterTouch':0xa0,'PatchChange':0xc0,'ChannelAfterTouch':0xd0,'PitchWheelChange':0xe0}
        if command not in statuses:raise ActionError('Unbekannter MIDI-Befehl im Test')
        status=statuses[command]|(channel-1);raw=[status,note]+([] if command in ('PatchChange','ChannelAfterTouch') else [100])
        result.update(MidiDecoder().feed(bytes(raw))[0]);result.update(deviceName=chosen['midiDeviceId']['name'],name=chosen['midiDeviceId']['name'])
    elif kind==90250:result.update(clipboardText='Test text',clipboardContent='Test text',clipboardTruncated=False,rawInput='Test text')
    elif kind==90251:result.update({'toast.id':trigger.get('toastId',''),'toast.title':'Test','toast.message':'Test notification','activationAction':'default'})
    elif kind in (90201,90252,90253):
        result.update(voiceText='Test text',rawInput='Test text',message='Test text')
        if kind==90201:result['voiceCommandName']=chosen['voiceCommandId']['name']
        if kind==90252 and trigger.get('_originalEventFilter')==301:
            command=chosen.get('voiceCommandId',{})
            if command.get('id'):
                rest='Test text' if command.get('location')=='start' else ''
                text=command.get('command','Test text')+(' '+rest if rest else '')
                result.update(voiceText=text,rawInput=text,message=text,_voiceCommandMatches=[{'id':command['id'],'name':command['name'],'command':command.get('command',''),'input':rest}])
        if kind==90253:result.update(logLevel='info',logMessage='Test text')
    elif kind in (90203,90204,90254):result.update(quote='Test quote',quoteId=0,quoteUser='testuser',quoteUserId='',quoteGame='',quotePlatform='twitch',quoteTime='',quoteTimestamp='')
    elif kind in (90260,90261,90262,90263,90264,90265):
        result.update(connectionName=chosen['connectionId']['name'],clientId='test-client')
        if kind in (90263,90264,90265):result['sessionId']='test-client'
        if kind in (90262,90265):result.update(message='Test message',rawInput='Test message')
    elif kind==90270:result.update(scheduleName=chosen['scheduleId']['name'],scheduledAt='2000-01-01T00:00:00+00:00')
    return result
