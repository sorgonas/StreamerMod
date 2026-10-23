"""YouTube/Kick variable stores without fabricating users or online connections."""
import copy
from .core import ActionError
from .core_events import set_global
from .csharp_globals import name,storage,entries,mutate_many,number,UNKNOWN_WRITE


def uid(value):
    if not isinstance(value,str) or not value.strip():raise ActionError('Nutzer-ID fehlt')
    return value

def known(engine,platform,identity,by_id):
    db=engine.state.db
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='known_users'").fetchone():return None
    column='user_id' if by_id else 'user'
    records=db.execute('SELECT user_id,user,display_name FROM known_users WHERE platform=? AND '+column+'=?',(platform,identity if by_id else identity.strip().casefold())).fetchall()
    if len(records)!=1 or not records[0][0]:return None
    return records[0]

async def rpc(engine,method,values):
    platform,*values=values
    if platform not in ('youtube','kick'):raise ActionError('Ungültige Nutzerplattform')
    if method=='platform_vars_list':
        var,persisted=values;var=name(var);result=[]
        for key,value,stamp in sorted(entries(engine,persisted),key=lambda row:row[0]):
            p,user_id,variable=key
            if p!=platform or variable!=var:continue
            info=known(engine,platform,user_id,True)
            result.append({'UserId':user_id,'UserLogin':info[1] if info else '', 'UserName':info[2] if info else '', 'UserType':platform,'VariableName':var,'Value':value,'LastWrite':stamp or UNKNOWN_WRITE,'LastWriteKnown':bool(stamp),'UserInfoAvailable':bool(info)})
        return result
    if method=='platform_var':
        operation,identity,by_id,var,value,persisted=values
        if operation not in ('get','set','unset','unset_user'):raise ActionError('Ungültige Nutzeroperation')
        if operation!='unset_user':var=name(var)
        identity=uid(identity)
        if by_id:user_id=identity
        else:
            info=known(engine,platform,identity,False)
            if info is None:return None
            user_id=info[0]
        key=(platform,user_id,var)
        if operation=='get':return engine.state.get(storage(key)) if persisted else copy.deepcopy(engine.user_session_globals.get(key))
        if operation=='set':set_global(engine,var,value,persisted,user=user_id,platform=platform)
        elif operation=='unset':set_global(engine,var,persisted=persisted,delete=True,user=user_id,platform=platform)
        else:mutate_many(engine,[(key,None,True) for key,_,_ in entries(engine,persisted) if key[:2]==(platform,user_id)],persisted)
        return None
    if method=='platform_vars_bulk':
        operation,identities,var,value,persisted=values;var=name(var)
        if operation not in ('set','increment','increment_create','all_increment'):raise ActionError('Ungültige Nutzer-Sammeloperation')
        rows={key:current for key,current,_ in entries(engine,persisted) if key[0]==platform and key[2]==var}
        if operation=='all_increment':targets=list(rows)
        else:
            if not isinstance(identities,list):raise ActionError('Nutzer-IDs müssen eine Liste sein')
            targets=list(dict.fromkeys((platform,uid(value),var) for value in identities))
        if operation!='set':number(value)
        changes=[]
        for key in targets:
            if operation=='increment' and key not in rows:continue
            updated=value if operation=='set' else number(number(rows.get(key,0))+value)
            changes.append((key,updated,False))
        mutate_many(engine,changes,persisted);return None
    raise ActionError('Unbekannte Plattform-Variablenoperation')
