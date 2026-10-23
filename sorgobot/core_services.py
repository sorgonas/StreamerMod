"""Runtime services backing File Tail, Voice Control and local signals."""
import asyncio
import copy
import re
from collections import defaultdict,deque
from pathlib import Path
from .catalog import ConfigStore
from .core import ActionError

DEFAULT_CONFIG={'pointDefinitions':[],'inputDevices':[],'midiDevices':[],'websocketConnections':[],'cronSchedules':[],'fileWatchers':[],'fileTails':[],'voiceCommands':[],'userGroups':[]}

def read_config(root):
    try:return {**copy.deepcopy(DEFAULT_CONFIG),**ConfigStore(root).read('core.json')}
    except FileNotFoundError:return copy.deepcopy(DEFAULT_CONFIG)

class Signals:
    def __init__(self):self.pending=defaultdict(deque);self.waiters=defaultdict(deque)
    def send(self,name,payload,queue):
        waiters=self.waiters[name]
        while waiters:
            future=waiters.popleft()
            if not future.done():future.set_result(copy.deepcopy(payload));return
        if queue:
            if len(self.pending[name])>=1000:raise ActionError('Signal-Warteschlange ist voll')
            self.pending[name].append(copy.deepcopy(payload))
    async def wait(self,name,timeout):
        if self.pending[name]:return self.pending[name].popleft()
        future=asyncio.get_running_loop().create_future();self.waiters[name].append(future)
        try:return await asyncio.wait_for(future,timeout)
        finally:
            try:self.waiters[name].remove(future)
            except ValueError:pass

class CoreServices:
    def __init__(self,studio):
        self.studio=studio;self.config=read_config(studio.root);self.cursors={};self.tail_events=asyncio.Queue(maxsize=1000)
        studio.engine.services=self
    def reload(self):
        from .core_events import group_changes
        updated=read_config(self.studio.root)
        group_changes(self.studio.engine,self.config['userGroups'],updated['userGroups'])
        self.config=updated;self.cursors.clear()
    def set_entry(self,section,identity,changes):
        target=next((x for x in self.config[section] if x['id']==identity),None)
        if target is None:raise ActionError('Eintrag nicht gefunden: '+section)
        if not self.studio.io.dry_run:
            store=ConfigStore(self.studio.root);document=read_config(self.studio.root)
            other=next((x for x in document[section] if x['id']==identity),None)
            if other is None:raise ActionError('Eintrag wurde inzwischen gelöscht')
            other.update(changes);store.save('core.json',document)
        before=copy.deepcopy(self.config['userGroups']) if section=='userGroups' else []
        target.update(changes)
        if section=='voiceCommands' and hasattr(self.studio,'services'):self.studio.spawn(self.studio.services.refresh_voice())
        if section=='userGroups':
            from .core_events import group_changes
            group_changes(self.studio.engine,before,self.config['userGroups'])
        if section=='fileTails':self.cursors.pop(identity,None)
        return target
    async def voice(self,text,args=None):
        management=getattr(self.studio,'services',None)
        if management:
            if not management.enabled['voice']:return
            if management.settings['voice']['logDictation']:management.log('voice',str(text)[:10000])
        context=dict(args or {},voiceText=text,rawInput=text,message=text)
        matched=list(voice_matches(self.config['voiceCommands'],text,context))
        context['_voiceCommandMatches']=[{'id':c['id'],'name':c['name'],'command':c['command'],'input':rest if c.get('location','exact')=='start' else ''} for c,rest in matched]
        await self.voice_event('Dictation',text,context);command_published=False
        from .core_events import emit
        emit(self.studio.engine,90252,context)
        if management is None or management.settings['voice']['logDictation']:
            emit(self.studio.engine,90253,dict(context,logLevel='info',logMessage=text))
        for command,remainder in voice_matches(self.config['voiceCommands'],text,context):
            if not command_published:
                await self.voice_event('Command',text,context);command_published=True
            values=dict(context,voiceCommandId=command['id'],voiceCommandName=command['name'],rawInput=remainder);values.pop('_voiceCommandMatches',None)
            if command.get('actionId'):await self.studio.engine.run(command['actionId'],values)
            await self.studio.dispatcher.event(90201,values,voiceCommandId=command['id'])
    async def voice_event(self,kind,text,context):
        hub=getattr(self.studio,'main_websocket',None)
        if hub is None:return
        import math
        score=context.get('speechConfidence',0)
        confidence=max(0,min(100,score))/100 if type(score) is int or type(score) is float and math.isfinite(score) else 0
        await hub.emit('SpeechToText',kind,{'text':str(text)[:10000],'confidence':confidence,'alternatives':None})
    async def poll_tails(self):
        while True:
            for item in list(self.config['fileTails']):
                if not item.get('enabled',True):self.cursors.pop(item['id'],None);continue
                try:
                    lines=await asyncio.to_thread(self.read_tail,item)
                    for line in lines:
                        await self.tail_events.put((item['id'],{'fileTailId':item['id'],'fileTailName':item['name'],'filePath':item['path'],'line':line,'fileLine':line,'rawInput':line}))
                except (OSError,UnicodeError,ValueError) as error:
                    self.studio.io.trace('file_tail_error',name=item.get('name',''),error=str(error))
            await asyncio.sleep(.25)
    async def dispatch_tails(self):
        while True:
            identity,args=await self.tail_events.get()
            try:
                if any(item['id']==identity and item.get('enabled',True) for item in self.config['fileTails']):
                    await self.studio.dispatcher.event(90200,args,fileTailId=identity)
            finally:self.tail_events.task_done()
    def read_tail(self,item):
        # Same descriptor for stat/read; detect rotation/truncation; dispatch only complete lines.
        path=Path(item['path']).expanduser()
        if not path.is_absolute():path=self.studio.root/path
        if not path.exists():self.cursors.pop(item['id'],None);return []
        with path.open('rb') as stream:
            import os
            stat=os.fstat(stream.fileno());signature=(stat.st_dev,stat.st_ino)
            previous=self.cursors.get(item['id'])
            if previous is None:
                self.cursors[item['id']]=(signature,stat.st_size if not item.get('readExisting') else 0,b'')
                previous=self.cursors[item['id']]
            sig,offset,partial=previous
            if sig!=signature or stat.st_size<offset:offset=0;partial=b''
            stream.seek(offset);chunk=stream.read(1024*1024);position=stream.tell()
        rows=(partial+chunk).split(b'\n');partial=rows.pop()
        if len(partial)>1024*1024:partial=b'';raise ValueError('File-Tail-Zeile überschreitet 1 MiB')
        self.cursors[item['id']]=(signature,position,partial)
        return [line.rstrip(b'\r').decode(item.get('encoding','utf-8'),errors='replace') for line in rows]


def voice_matches(commands,text,context):
    for command in list(commands):
        if not command.get('enabled',True):continue
        pattern=command.get('command','').strip()
        if not pattern:continue
        flags=0 if command.get('caseSensitive') else re.I
        location=command.get('location','exact');match_text=text;ends=None
        if context.get('speechSource') in ('whisper-base','whisper-small'):
            from .speech_whisper import normalized
            match_text,ends=normalized(text,bool(command.get('caseSensitive')))
            pattern=normalized(pattern,bool(command.get('caseSensitive')))[0]
            if not pattern:continue
        regex=re.escape(pattern)+(r'(?:\s|$)' if location=='start' else '')
        matcher={'exact':re.fullmatch,'start':re.match,'anywhere':re.search}.get(location)
        if matcher is None:raise ActionError('Unbekannte Voice-Position')
        match=matcher(regex,match_text,flags)
        if not match:continue
        end=ends[match.end()-1] if ends and match.end() else match.end()
        remainder='' if location=='exact' else text[end:].strip()
        yield command,remainder
