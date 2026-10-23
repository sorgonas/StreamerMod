"""Queued Core events: variable mutations and user group changes."""
import asyncio
import copy
import datetime as dt
import json
import contextvars
from contextlib import nullcontext

_depth=contextvars.ContextVar("core_event_depth",default=0)
_budget=contextvars.ContextVar("core_event_budget",default=None)

class CoreEvents:
    def __init__(self,studio):
        self.studio=studio;self.queue=asyncio.Queue(maxsize=1000)
    def emit(self,kind,args,**filters):
        budget=_budget.get()
        if budget is None:budget={'remaining':32}
        if _depth.get()>=20 or budget['remaining']<=0:
            self.studio.io.trace('core_event_error',error='Zyklische Core-Ereigniskette gestoppt');return
        budget['remaining']-=1
        try:self.queue.put_nowait((kind,copy.deepcopy(args),filters,_depth.get()+1,budget))
        except asyncio.QueueFull:self.studio.io.trace('core_event_error',error='Core-Ereigniswarteschlange ist voll')
    async def dispatch(self):
        while True:
            kind,args,filters,depth,budget=await self.queue.get()
            token=_depth.set(depth);budget_token=_budget.set(budget)
            try:await self.studio.dispatcher.event(kind,args,**filters)
            finally:_depth.reset(token);_budget.reset(budget_token);self.queue.task_done()
            await asyncio.sleep(0)

def emit(engine,kind,args,**filters):
    events=getattr(engine,'core_events',None)
    if events:events.emit(kind,args,**filters)

def set_global(engine,name,value=None,persisted=True,delete=False,user=None,platform='twitch',emit_event=True):
    if not isinstance(name,str) or not name:raise ValueError('Variablenname fehlt')
    storage=name if user is None else 'core:user:'+json.dumps((platform,user,name))
    session=engine.session_globals if user is None else engine.user_session_globals
    stamps=getattr(engine,'variable_session_writes',None)
    if stamps is None:stamps=engine.variable_session_writes={}
    key=name if user is None else (platform,user,name)
    exists=engine.state.db.execute('SELECT 1 FROM kv WHERE key=?',(storage,)).fetchone() is not None if persisted else key in session
    old=engine.state.get(storage) if persisted else session.get(key)
    stamp=dt.datetime.now(dt.timezone.utc).isoformat()
    if delete:
        if not exists:return
        if persisted:
            with nullcontext() if engine.state.db.in_transaction else engine.state.db:
                engine.state.db.execute('DELETE FROM kv WHERE key=?',(storage,))
                engine.state.db.execute('DELETE FROM variable_writes WHERE key=?',(storage,))
        else:session.pop(key,None);stamps.pop(key,None)
    else:
        if persisted:
            with nullcontext() if engine.state.db.in_transaction else engine.state.db:
                if not engine.state.db.in_transaction:engine.state.db.execute('BEGIN IMMEDIATE')
                engine.state.set(storage,value)
                engine.state.db.execute('UPDATE variable_writes SET last_write=?,is_global=? WHERE key=?',(stamp,int(user is None),storage))
        else:session[key]=copy.deepcopy(value);stamps[key]=stamp
        if exists and old==value:return
    args={'global.name':name,'global.oldValue':old,'global.newValue':None if delete else value,'global.persisted':persisted,'global.lastWrite':stamp,'variableName':name,'persisted':persisted}
    if user is not None:
        from .users import store
        platform=str(platform).casefold()
        row=store(engine).db.execute('SELECT user,display_name FROM known_users WHERE platform=? AND user_id=? ORDER BY last_seen DESC LIMIT 1',(platform,str(user))).fetchone()
        login,display=row if row else ('','')
        args.update(userId=user,platform=platform)
        args.update({'global.userId':user,'global.userType':platform,'global.userLogin':login,'global.userName':display or login})
    kind=90223 if user is not None else 90221 if delete else 90222 if exists else 90220
    filters={'variableName':name,'persisted':persisted}
    if emit_event:emit(engine,kind,args,**filters)
    return kind,args,filters

def group_changes(engine,before,after):
    old={v['id']:v for v in before};new={v['id']:v for v in after}
    for identity in old.keys()|new.keys():
        a=old.get(identity);b=new.get(identity);target=b or a
        args={'groupId':identity,'groupName':target['name']}
        if a is None:emit(engine,90230,args,groupId=identity)
        if b is None:emit(engine,90232,args,groupId=identity)
        removed=sorted(set(a.get('users',[]) if a else [])-set(b.get('users',[]) if b else []))
        added=sorted(set(b.get('users',[]) if b else [])-set(a.get('users',[]) if a else []))
        if removed:emit(engine,90234,dict(args,users=removed,userCount=len(removed)),groupId=identity)
        if added:emit(engine,90233,dict(args,users=added,userCount=len(added)),groupId=identity)
        if a and b and a.get('users') and not b.get('users'):emit(engine,90231,args,groupId=identity)
