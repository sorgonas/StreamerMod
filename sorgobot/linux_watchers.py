"""Linux inotify file events and /proc process lifecycle snapshots."""
import asyncio
import ctypes
import ctypes.util
import fnmatch
import os
from pathlib import Path
import struct
from urllib.parse import quote
from .core import ActionError
from .game_detection import process_name

# Linux inotify flags; MOVED_FROM/TO cookies pair real rename events.
MODIFY=2;ATTRIB=4;CLOSE_WRITE=8;MOVED_FROM=64;MOVED_TO=128;CREATE=256;DELETE=512;DELETE_SELF=1024;MOVE_SELF=2048;ISDIR=0x40000000;IGNORED=0x8000;OVERFLOW=0x4000
MASK=ATTRIB|CLOSE_WRITE|MOVED_FROM|MOVED_TO|CREATE|DELETE|DELETE_SELF|MOVE_SELF
KINDS={'Changed':90210,'Created':90211,'Deleted':90212,'Renamed':90213}

class FileWatcher:
    def __init__(self,root,definition):
        self.definition=definition.copy();self.root=Path(root)
        self.path=Path(definition['path']).expanduser()
        if not self.path.is_absolute():self.path=self.root/self.path
        self.path=self.path.resolve();self.directory=bool(definition.get('folder',True));self.watch_root=self.path if self.directory else self.path.parent
        self.lib=ctypes.CDLL(ctypes.util.find_library('c'),use_errno=True)
        self.lib.inotify_init1.argtypes=[ctypes.c_int];self.lib.inotify_init1.restype=ctypes.c_int
        self.lib.inotify_add_watch.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_uint32];self.lib.inotify_add_watch.restype=ctypes.c_int
        self.fd=self.lib.inotify_init1(os.O_NONBLOCK|os.O_CLOEXEC);self.directories={};self.moves={};self.closed=False
        if self.fd<0:raise OSError(ctypes.get_errno(),os.strerror(ctypes.get_errno()))
        try:self.add_tree(self.watch_root)
        except BaseException:self.close();raise
    def add_tree(self,path):
        self.add_directory(path)
        if self.directory and self.definition.get('recursive'):
            # Do not follow symlinks outside the selected directory.
            for directory,dirs,_ in os.walk(path):
                dirs[:]=[d for d in dirs if not (Path(directory)/d).is_symlink()]
                self.add_directory(Path(directory))
    def add_directory(self,path):
        if path.is_symlink():return
        wd=self.lib.inotify_add_watch(self.fd,os.fsencode(path),MASK)
        if wd<0:raise OSError(ctypes.get_errno(),os.strerror(ctypes.get_errno()),str(path))
        self.directories[wd]=path
    def matches(self,path):
        if not self.directory:return path==self.path
        pattern=self.definition.get('filter','*') or '*'
        return fnmatch.fnmatchcase(path.name,pattern)
    def event(self,kind,path,old=None,isdir=False):
        if not self.matches(path) and not (old and self.matches(old)):return None
        args={'changeType':kind,'watcherId':self.definition['id'],'watcherName':self.definition['name'],'watcherFilter':self.definition.get('filter','*'),'watcherFolder':str(self.watch_root),'fileName':path.name,'fullPath':str(path),'isDirectory':isdir}
        if old:args.update(oldFilename=old.name,oldFullPath=str(old))
        if kind in ('Created','Changed') and not isdir:
            try:
                args['fileSize']=path.stat().st_size;args['empty']=args['fileSize']==0
                if self.definition.get('readContents',False):
                    with path.open('rb') as stream:data=stream.read(65537)
                    args['contentTruncated']=len(data)>65536;lines=data[:65536].decode(self.definition.get('encoding','utf-8'),errors='replace').splitlines()
                    args['lineCount']=len(lines)
                    for i,line in enumerate(lines):args['line'+str(i)]=line;args['lineEscaped'+str(i)]=quote(line,safe='')
            except OSError as error:args['fileReadError']=str(error)
        return KINDS[kind],args
    def read_events(self):
        result=[];now=asyncio.get_running_loop().time()
        while True:
            try:data=os.read(self.fd,256*1024)
            except BlockingIOError:break
            if not data:break
            offset=0
            while offset<len(data):
                wd,mask,cookie,length=struct.unpack_from('iIII',data,offset);offset+=16
                name=os.fsdecode(data[offset:offset+length].split(b'\0',1)[0]);offset+=length
                if mask&OVERFLOW:raise ActionError('Dateiwächter-Ereignispuffer übergelaufen; Änderungen können fehlen')
                directory=self.directories.get(wd)
                if mask&IGNORED:self.directories.pop(wd,None);continue
                if directory is None:continue
                path=directory/name if name else directory;isdir=bool(mask&ISDIR) or not name
                if mask&MOVED_FROM:
                    self.moves[cookie]=(now,path,isdir);continue
                old=self.moves.pop(cookie,None) if mask&MOVED_TO else None
                if mask&MOVED_TO and old:
                    event=self.event('Renamed',path,old[1],isdir)
                    if isdir:
                        # inotify keeps watches on renamed inodes; update their paths.
                        for key,watched in list(self.directories.items()):
                            if watched==old[1] or watched.is_relative_to(old[1]):self.directories[key]=path/watched.relative_to(old[1])
                elif mask&(CREATE|MOVED_TO):event=self.event('Created',path,isdir=isdir)
                elif mask&(DELETE|DELETE_SELF):event=self.event('Deleted',path,isdir=isdir)
                elif mask&(CLOSE_WRITE|ATTRIB):event=self.event('Changed',path,isdir=isdir)
                else:event=None
                if isdir and mask&(CREATE|MOVED_TO) and self.directory and self.definition.get('recursive'):
                    try:self.add_tree(path)
                    except FileNotFoundError:pass
                if event:result.append(event)
        # Moves out of the watched tree become Deleted; matching moves become Renamed.
        for cookie,(stamp,path,isdir) in list(self.moves.items()):
            if now-stamp>=.1:
                self.moves.pop(cookie);event=self.event('Deleted',path,isdir=isdir)
                if event:result.append(event)
                if isdir:
                    for key,watched in list(self.directories.items()):
                        if watched==path or watched.is_relative_to(path):
                            self.lib.inotify_rm_watch(self.fd,key);self.directories.pop(key,None)
        return result
    def close(self):
        if not self.closed:os.close(self.fd);self.closed=True


def process_snapshot(proc=Path('/proc')):
    result={}
    for directory in proc.iterdir():
        if not directory.name.isdigit():continue
        try:
            stat=(directory/'stat').read_text();parts=stat[stat.rfind(')')+2:].split()
            identity=(int(directory.name),parts[19])
            command=(directory/'cmdline').read_bytes().decode(errors='replace').split('\0')
            if not command[0]:continue # Kernel threads and exited/zombie processes.
            try:executable=os.readlink(directory/'exe').removesuffix(' (deleted)')
            except OSError:executable=command[0]
            aliases={process_name(executable),process_name(command[0])}
            windows=[arg for arg in command[1:] if arg.lower().endswith('.exe') and not arg.startswith('-')]
            aliases.update(process_name(arg) for arg in windows)
            if windows:executable=windows[0].replace('\\','/')
            name=Path(executable).name
            result[identity]={'processId':identity[0],'parentProcessId':int(parts[1]),'executable':name,'fullPath':executable,'path':str(Path(executable).parent),'name':name,'processNames':sorted(aliases)}
        except (OSError,ValueError,IndexError):continue
    return result

class LocalWatchers:
    def __init__(self,studio):self.studio=studio;self.files={};self.failed={};self.processes=None;self.events=asyncio.Queue(maxsize=1000)
    def definitions(self):return self.studio.core_services.config.get('fileWatchers',[])
    def process_enabled(self):
        if hasattr(self.studio,'services') and not self.studio.services.enabled['process']:return False
        return any(a.get('enabled',True) and any(t.get('enabled',True) and t.get('type') in (90214,90215) for t in a.get('triggers',[])) for a in self.studio.engine.actions.values())
    def sync(self):
        definitions={item['id']:item for item in self.definitions() if item.get('enabled',True)}
        for identity,watcher in list(self.files.items()):
            if definitions.get(identity)!=watcher.definition or not watcher.directories:watcher.close();self.files.pop(identity)
        for identity,item in definitions.items():
            if identity in self.files:continue
            try:self.files[identity]=FileWatcher(self.studio.root,item);self.failed.pop(identity,None)
            except (OSError,ValueError) as error:
                message=str(error)
                if self.failed.get(identity)!=message:self.studio.io.trace('file_watcher_error',name=item.get('name',''),error=message);self.failed[identity]=message
    async def poll(self):
        try:
            while True:
                self.sync()
                for watcher in list(self.files.values()):
                    try:
                        for kind,args in watcher.read_events():await self.events.put((kind,args))
                    except ActionError as error:self.studio.io.trace('file_watcher_error',error=str(error))
                if self.process_enabled():
                    snapshot=await asyncio.to_thread(process_snapshot)
                    if self.processes is not None:
                        for key in self.processes.keys()-snapshot.keys():await self.events.put((90215,self.processes[key]))
                        for key in snapshot.keys()-self.processes.keys():await self.events.put((90214,snapshot[key]))
                    self.processes=snapshot
                else:self.processes=None
                await asyncio.sleep(.1)
        finally:self.close()
    async def dispatch(self):
        while True:
            kind,args=await self.events.get()
            try:
                if kind in (90214,90215):
                    if self.process_enabled():await self.studio.dispatcher.event(kind,args)
                elif any(item['id']==args['watcherId'] and item.get('enabled',True) for item in self.definitions()):await self.studio.dispatcher.event(kind,args,watcherId=args['watcherId'])
            finally:self.events.task_done()
    def close(self):
        for watcher in self.files.values():watcher.close()
        self.files.clear()
