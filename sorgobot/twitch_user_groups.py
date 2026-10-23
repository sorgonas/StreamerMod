"""Twitch-scoped membership in the existing local Core user groups."""
import copy
import re
from .catalog import _CONFIG_LOCK
from .core import ActionError,expand
from .core_services import read_config
from .users import PLATFORMS

ENTRIES={
    91500:('Add User To Group',{'userLogin':'%userName%','groupName':''}),
    91501:('Remove User From Group',{'userLogin':'%userName%','groupName':''}),
    91502:('User in Group',{'userLogin':'%userName%','groupName':''}),
}
FLAGS={91500:'addResult',91501:'removeResult',91502:'inGroup'}

def group(groups,name):
    matches=[g for g in groups if str(g.get('name','')).strip().casefold()==name.casefold()]
    if not matches:raise ActionError('Nutzergruppe nicht gefunden. Unter Core Services → User Groups anlegen.')
    if len(matches)!=1:raise ActionError('Gruppenname ist mehrdeutig. Unter Core Services → User Groups eindeutig benennen.')
    target=matches[0]
    if not isinstance(target.get('users',[]),list) or not all(isinstance(u,str) for u in target.get('users',[])):raise ActionError('Ungültige Nutzergruppen-Mitglieder')
    return target

def member(names,login):
    return any(value.strip().casefold() in (login,'twitch:'+login) for value in names)

def removed(names,login):
    result=[]
    for value in names:
        key=value.strip().casefold()
        if key=='twitch:'+login:continue
        if key==login:
            # Old bare logins match all three platforms. Restricting a removal
            # to Twitch must not remove membership on YouTube or Kick.
            for platform in PLATFORMS:
                entry=platform+':'+login
                if platform!='twitch' and not any(u.strip().casefold()==entry for u in [*result,*names]):result.append(entry)
        else:result.append(value)
    return result

def cached_user(engine,login):
    db=engine.state.db
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='known_users'").fetchone():return {}
    row=db.execute('SELECT user_id,display_name FROM known_users WHERE platform=? AND user=?',('twitch',login)).fetchone()
    return {'id':row[0],'display_name':row[1],'login':login} if row else {}

async def operation(engine,node,args):
    kind=node['type'];flag=FLAGS[kind];args[flag]=False
    if kind==91502:
        for key in ('foundUser','foundUserName','foundUserId','foundUserType'):args[key]=''
        args['foundUserAvailable']=False
    raw=expand(node.get('userLogin',''),args);name=expand(node.get('groupName',''),args)
    if not isinstance(raw,str) or not isinstance(name,str):raise ActionError('User Login und Group Name müssen Text sein')
    login=raw.strip().lstrip('@').casefold();name=name.strip()
    if not re.fullmatch(r'[a-z0-9_]{1,25}',login):raise ActionError('Gültigen Twitch-Login angeben; %userName% ist der Login, %user% der Anzeigename')
    if not name:raise ActionError('Group Name darf nicht leer sein')
    io=engine.io;services=getattr(engine,'services',None)
    if services is None:raise ActionError('Nutzergruppen-Dienst ist nicht verfügbar')
    # Validate the group before looking up a user. Recheck after the await,
    # because settings or another Action can have changed in the meantime.
    with _CONFIG_LOCK:group(read_config(io.root)['userGroups'],name)
    if io.dry_run:
        args['isPreview']=True
        if kind!=91502:
            io.trace('twitch_user_group_preview',operation=ENTRIES[kind][0],groupName=name,userLogin=login);return
        user=cached_user(engine,login)
    else:
        user=await io.user(login)
        if not user.get('id') or str(user.get('login','')).casefold()!=login:raise ActionError('Twitch hat keinen passenden Zielnutzer geliefert')
    with _CONFIG_LOCK:
        groups=read_config(io.root)['userGroups'];target=group(groups,name);names=list(target.get('users',[]));included=member(names,login) or bool(user.get('id') and 'twitch:id:'+str(user['id']) in names)
        if kind==91502:
            args.update(inGroup=included,foundUser=user.get('display_name') or login,foundUserName=login,foundUserId=user.get('id',''),foundUserType='twitch',foundUserAvailable=bool(user.get('id')))
            return
        if kind==91500:
            if included:return
            names.append('twitch:'+login)
        else:
            if not included:return
            from .users import remove_membership
            names=remove_membership(names,'twitch',login,str(user.get('id','')))
        # set_entry uses the same reentrant config lock. Reading latest members
        # here avoids lost updates across awaited user lookups in this process.
        services.config['userGroups']=copy.deepcopy(groups)
        services.set_entry('userGroups',target['id'],{'users':names})
        args[flag]=True
