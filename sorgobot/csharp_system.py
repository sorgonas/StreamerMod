"""Desktop CPH operations and UI custom events over existing native services."""
import copy,re,uuid
from .core import ActionError


def keys_sequence(text):
    if not isinstance(text,str):raise ActionError('KeyboardPress benötigt Text')
    result=[];modifiers=[];offset=0
    aliases={'RETURN':'ENTER','BACK':'BACKSPACE','ESCAPE':'ESC','CONTROLKEY':'CTRL','SHIFTKEY':'SHIFT','MENU':'ALT','LWIN':'SUPER','RWIN':'SUPER','PRIOR':'PAGEUP','NEXT':'PAGEDOWN'}
    while offset<len(text):
        char=text[offset];offset+=1
        if char in '^+%':
            modifier={'^':'CTRL','+':'SHIFT','%':'ALT'}[char]
            if modifier not in modifiers:modifiers.append(modifier)
            continue
        if char=='{':
            end=text.find('}',offset)
            if end<0:raise ActionError('KeyboardPress: schließende Klammer fehlt')
            key=text[offset:end].strip().upper();offset=end+1
        elif char.isascii() and char.isalnum():key=char.upper()
        elif char==' ':key='SPACE'
        else:raise ActionError('KeyboardPress: nicht unterstützte Tastensyntax')
        key=aliases.get(key,key)
        if re.fullmatch(r'D[0-9]',key):key=key[1:]
        if not (re.fullmatch(r'[A-Z0-9]|F(?:[1-9]|1[0-9]|2[0-4])',key) or key in ('ENTER','TAB','ESC','SPACE','BACKSPACE','DELETE','INSERT','HOME','END','PAGEUP','PAGEDOWN','UP','DOWN','LEFT','RIGHT','CTRL','SHIFT','ALT','SUPER','CAPSLOCK','NUMLOCK','SCROLLLOCK','PAUSE','PRINT')):raise ActionError('KeyboardPress: unbekannte Taste '+key)
        result.append('+'.join(dict.fromkeys([*modifiers,key])))
    return result

async def rpc(engine,method,values):
    if method=='legacy_user_unset':
        platform,user,var,persisted,all_vars=values
        platform=platform.casefold() if isinstance(platform,str) else ''
        if platform not in ('twitch','youtube','kick') or not isinstance(user,str) or not user.strip():return None
        from .csharp_platform_globals import known
        from .csharp_globals import entries,mutate_many,name
        if not all_vars:var=name(var)
        info=known(engine,platform,user,False)
        if info is None:return None
        mutate_many(engine,[(key,None,True) for key,_,_ in entries(engine,persisted) if key[:2]==(platform,info[0]) and (all_vars or key[2]==var)],persisted)
        return None
    if method=='auth_property':
        if len(values)!=1 or values[0] not in ('twitch_client_id','twitch_token'):raise ActionError('Unbekannte Twitch-Eigenschaft')
        value=engine.io.config.get(values[0],'')
        return value if isinstance(value,str) else ''
    if method=='reset_first_words':
        dispatcher=getattr(engine,'dispatcher',None)
        if dispatcher is None:raise ActionError('First-Words-Laufzeit fehlt')
        if engine.state.db.in_transaction:raise ActionError('First-Words-Reset benötigt eine eigene Transaktion')
        engine.state.set('first_words_users',[])
        dispatcher.first_users.clear()
        return None
    if method=='keyboard_press':
        sequence=keys_sequence(values[0])
        if engine.io.dry_run:engine.io.trace('keyboard',keys=sequence,simulated=True);return None
        if getattr(getattr(engine,'studio',None),'closing',False):raise ActionError('Desktop-Laufzeit wird beendet')
        from .linux_keyboard import press
        for keys in sequence:await press(keys,.1)
        return None
    if method=='toast':
        identity,title,message,attribution,icon=values
        if any(value is not None and not isinstance(value,str) for value in values):raise ActionError('Toast-Parameter müssen Text sein')
        node={'toastId':identity or str(uuid.uuid4()),'title':title or '','text':message or '','attribution':attribution,'iconPath':icon,'activationLabel':'Open'}
        if engine.io.dry_run:engine.io.trace('notification',title=node['title'],text=node['text'],simulated=True);return None
        studio=getattr(engine,'studio',None)
        if studio is None or getattr(studio,'closing',False):raise ActionError('Desktop-Benachrichtigung benötigt aktive Studio-Laufzeit')
        await studio.notifications.show(node);return None
    if method=='custom_event':
        event,payload=values
        if not isinstance(event,str) or not event.strip() or not isinstance(payload,dict):raise ActionError('Custom Event benötigt Name und Argumentobjekt')
        events=getattr(engine,'core_events',None)
        if events is None:raise ActionError('Custom-Event-Laufzeit fehlt')
        arguments=copy.deepcopy(payload);arguments['eventName']=event
        events.emit(90202,arguments,eventName=event)
        return None
    raise ActionError('Unbekannter Core-Desktop-Aufruf')
