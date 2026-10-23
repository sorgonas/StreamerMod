"""Original-style, functional context menus for the separate native edition."""
import copy
import json
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMenu,QApplication,QInputDialog
from .catalog import new_step
from .core import walk
from .editor_menus import renewed
from .next_catalog import steps,triggers


def add_catalog(menu,catalog,callback,favorites=None,favorite_label='Favorite Sub-Action'):
    categories={}
    for kind,(path,_) in catalog.items():
        parts=path.split(' · ');parent=menu;key=()
        for part in parts[:-1]:
            key+= (part,)
            if key not in categories:categories[key]=parent.addMenu(part)
            parent=categories[key]
        action=parent.addAction(parts[-1],lambda checked=False,k=kind:callback(k));action.setData(kind)
    if favorites:
        from PySide6.QtCore import Qt
        for popup in {menu,*categories.values()}:
            popup.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            def favorite_menu(position,parent=popup):
                leaf=parent.actionAt(position)
                if not leaf or leaf.menu() or not leaf.isEnabled() or not (isinstance(leaf.data(),int) or isinstance(leaf.data(),str) and leaf.data().startswith('code:')):return
                selected=leaf.data();options=QMenu(parent)
                option=options.addAction(favorite_label,lambda:favorites(selected))
                options.exec(parent.mapToGlobal(position))
            popup.customContextMenuRequested.connect(favorite_menu)
    return ordered_menu(menu)


CORE_SUBACTION_ENTRIES=['Delay','Action Queues','Actions','Arguments','Commands','C#','File I/O','File Tail','Globals','Logic','MIDI','Misc','Network','Points','Quotes','Signals','Sounds','System','Timers','Triggers','Users','Voice Control']
SUBACTION_ROOTS=['Core','Elgato','Integrations','OBS Studio','Settings','StreamerMod','Twitch','YouTube','Stream Apps']

def ordered_menu(menu,root_order=None):
    # Original uncategorized leaves precede categorized entries. Siblings then
    # follow the reference order (root/Core) or a stable alphabetical order.
    for entry in menu.actions():
        if entry.menu():ordered_menu(entry.menu(),CORE_SUBACTION_ENTRIES if entry.text()=='Core' else None)
    entries=list(menu.actions());rank={label:i for i,label in enumerate(root_order or [])}
    entries.sort(key=lambda entry:(1 if entry.menu() else 0,rank.get(entry.text(),len(rank)),entry.text().casefold()))
    for entry in entries:menu.removeAction(entry)
    for entry in entries:menu.addAction(entry)
    return menu

def subaction_catalog(menu,callback,favorite=None):
    catalog=steps();add_catalog(menu,catalog,callback,favorite)
    return ordered_menu(menu,SUBACTION_ROOTS)


def copy_node(node,kind):
    QApplication.clipboard().setText(json.dumps({'format':'streamer-linux-node-1','kind':kind,'node':node},ensure_ascii=False))


def clipboard_node(kind):
    try:
        value=json.loads(QApplication.clipboard().text())
        if isinstance(value,dict) and value.get('format')=='streamer-linux-node-1' and value.get('kind')==kind and isinstance(value.get('node'),dict) and isinstance(value['node'].get('type'),int):
            catalog=triggers() if kind=='trigger' else steps()
            if value['node']['type'] in catalog or kind=='step' and value['node']['type']==99900:return value['node']
    except (ValueError,TypeError):pass
    return None

def clipboard_triggers():
    single=clipboard_node('trigger')
    if single is not None:return [single]
    try:
        value=json.loads(QApplication.clipboard().text())
        if not isinstance(value,dict) or value.get('format')!='streamer-linux-triggers-1':return []
        nodes=value.get('nodes');catalog=triggers()
        if isinstance(nodes,list) and 0<len(nodes)<=1000 and all(isinstance(n,dict) and type(n.get('type')) is int and n['type'] in catalog for n in nodes):return nodes
    except (ValueError,TypeError):pass
    return []


def editor_context(editor,trigger=False):
    if trigger:return trigger_context(editor)
    menu=QMenu(editor.host);tree=editor.triggers if trigger else editor.steps
    try:preferences=editor.host.store.read('editor.json')
    except FileNotFoundError:preferences={'favorites':[]}
    def favorite(kind):
        values=preferences.setdefault('favorites',[])
        if kind in values:values.remove(kind)
        else:values.append(kind)
        editor.host.store.save('editor.json',preferences)
    if not trigger:
        favorites_menu=menu.addMenu('Favorite Sub-Actions')
        favorite_catalog={kind:value for kind,value in steps().items() if kind in preferences.get('favorites',[])}
        add_catalog(favorites_menu,favorite_catalog,editor.add_step);favorites_menu.setEnabled(bool(favorite_catalog))
    recent_menu=menu.addMenu('Recent Sub-Actions');catalog=steps()
    for recent_kind in dict.fromkeys(k for k in preferences.get('recentSubActions',[]) if isinstance(k,int) and k in catalog):
        item=recent_menu.addAction(catalog[recent_kind][0],lambda checked=False,k=recent_kind:editor.add_step(k));item.setData(recent_kind)
    recent_menu.setEnabled(bool(recent_menu.actions()))
    subaction_catalog(menu.addMenu('Add'),editor.add_step,favorite)
    menu.addSeparator();kind='trigger' if trigger else 'step'
    nodes,index,node=editor.selected_trigger() if trigger else editor.selected()
    selected=node is not None;structural=selected and node['type'] in (99901,99902)
    if not selected:
        for action in list(menu.actions()):
            if action.isSeparator():menu.removeAction(action)
        menu.addAction('Add Group',lambda:editor.add_step(99900))
        def clear_empty():editor.value['subActions'].clear();editor.refresh()
        menu.addAction('Delete All',clear_empty).setEnabled(bool(editor.value['subActions']))
        if clipboard_node('step') is not None:
            def paste_empty():
                value=clipboard_node('step')
                if value is not None:editor.value['subActions'].append(renewed(value));editor.refresh()
            menu.addAction('Paste Sub-Action',paste_empty)
        order={'Add Group':0,'Delete All':1,'Favorite Sub-Actions':2,'Recent Sub-Actions':3,'Paste Sub-Action':4,'Add':5}
        actions=sorted(menu.actions(),key=lambda action:order[action.text()])
        for action in menu.actions():menu.removeAction(action)
        for action in actions:
            if action.text() in ('Favorite Sub-Actions','Add'):menu.addSeparator()
            menu.addAction(action)
        return menu
    def entry(label,callback,enabled=True):
        a=menu.addAction(label,callback);a.setEnabled(enabled);return a
    def save():editor.refresh()
    def duplicate():nodes.insert(index+1,renewed(node));save()
    def paste():
        value=clipboard_node(kind)
        if value is None:return
        value=renewed(value)
        if trigger:editor.value['triggers'].append(value)
        else:editor.insert_node(value)
        save()
    if trigger:entry('Test Trigger',editor.test_trigger,selected)
    entry('Edit Trigger' if trigger else 'Edit Sub-Action',editor.edit_trigger if trigger else editor.edit_step,selected)
    entry('Copy Trigger' if trigger else 'Copy Sub-Action',lambda:copy_node(node,kind),selected and not structural)
    entry('Paste Trigger' if trigger else 'Paste Sub-Action',paste,clipboard_node(kind) is not None)
    entry('Duplicate Trigger' if trigger else 'Duplicate Sub-Action',duplicate,selected and not structural)
    entry('Delete Trigger' if trigger else 'Delete Sub-Action',editor.remove_trigger if trigger else editor.remove_step,selected and not structural)
    def toggle():node['enabled']=not node.get('enabled',True);save()
    enabled=entry('Enabled',toggle,selected);enabled.setCheckable(True);enabled.setChecked(node.get('enabled',True) if selected else False)
    if not trigger:
        option=entry('Favorite Sub-Action',lambda:favorite(node['type']),selected and not structural)
        option.setCheckable(True);option.setChecked(node['type'] in preferences.get('favorites',[]) if selected else False)
    menu.addSeparator()
    if trigger:
        entry('Refresh Triggers',editor.refresh)
        def all_enabled(value):
            for t in editor.value['triggers']:t['enabled']=value
            save()
        entry('Enable All Triggers',lambda:all_enabled(True),bool(editor.value['triggers']))
        entry('Disable All Triggers',lambda:all_enabled(False),bool(editor.value['triggers']))
        def clear():editor.value['triggers'].clear();save()
        entry('Clear All Triggers',clear,bool(editor.value['triggers']))
    else:
        entry('Add Group',lambda:editor.add_step(99900))
        if selected and node['type']==90164:
            def add_case(default=False):
                from .desktop import FieldsDialog
                value=new_step(90165);value['default']=default;value['name']='Default' if default else 'Case'
                dialog=FieldsDialog('Add Case',value,editor.host)
                if dialog.exec()==dialog.DialogCode.Accepted:node['subActions'].append(dialog.value);save()
            entry('Add Case',lambda:add_case(False));entry('Add Default Case',lambda:add_case(True),not any(case.get('default') for case in node.get('subActions',[])))
        if selected and node['type']==99900:
            def rename():
                name,ok=QInputDialog.getText(editor.host,'Rename Group','Name',text=node.get('name','Group'))
                if ok and name.strip():node['name']=name.strip();save()
            entry('Rename Group',rename);entry('Delete Group',editor.remove_step)
            def randomize():node['random']=not node.get('random',False);save()
            action=entry('Random',randomize);action.setCheckable(True);action.setChecked(node.get('random',False))
        move=menu.addMenu('Move');move.setEnabled(selected and not structural)
        for label,destination in [('Up',index-1 if selected else 0),('Down',index+1 if selected else 0),('Top',0),('Bottom',len(nodes)-1 if nodes is not None else 0)]:
            def shift(checked=False,target=destination):
                if nodes is not None and 0<=target<len(nodes):nodes.insert(target,nodes.pop(index));save()
            move.addAction(label,shift).setEnabled(selected and not structural and 0<=destination<len(nodes) and destination!=index)
        groups=menu.addMenu('Move to Group');groups.setEnabled(selected and not structural)
        def visit(values,ancestors=()):
            for value in values:
                if value is node:continue
                if value['type']==99900:
                    group=groups.addAction(' / '.join((*ancestors,value.get('name','Group'))),lambda checked=False,target=value:editor.move_node(node['id'],target['id'],len(target['subActions'])))
                visit(value.get('subActions',[]),(*ancestors,value.get('name','Group')))
        visit(editor.value['subActions'])
        if selected and nodes is not editor.value['subActions']:groups.addAction('(Root)',lambda:editor.move_node(node['id'],None,len(editor.value['subActions'])))
        def weight():
            value,ok=QInputDialog.getInt(editor.host,'Weight','Weight',int(node.get('weight',1)),0,1000000)
            if ok:node['weight']=value;save()
        entry('Weight',weight,selected and not structural and (editor.value.get('random',False) or any(value.get('random',False) and value.get('subActions') is nodes for value in walk(editor.value['subActions']))))
        def clear():editor.value['subActions'].clear();save()
        entry('Delete All',clear,bool(editor.value['subActions']))
        entry('Collapse All',tree.collapseAll);entry('Expand All',tree.expandAll)
    # Documented editor commands have a stable order independent of which
    # selection-specific commands were added above.
    order=['Add Group','Delete All','Favorite Sub-Actions','Recent Sub-Actions','Add','Edit Sub-Action','Copy Sub-Action','Paste Sub-Action','Duplicate Sub-Action','Delete Sub-Action','Add Case','Add Default Case','Delete Group','Rename Group','Move to Group','Enabled','Random','Favorite Sub-Action','Weight','Move','Collapse All','Expand All']
    rank={label:i for i,label in enumerate(order)}
    entries=[a for a in menu.actions() if not a.isSeparator()]
    entries.sort(key=lambda a:rank.get(a.text(),len(rank)))
    for a in menu.actions():menu.removeAction(a)
    for a in entries:menu.addAction(a)
    return menu


def action_context(window):
    from PySide6.QtCore import Qt
    menu=QMenu(window);action=window.current_action();selected=action is not None
    if not selected:
        menu.addAction('Add',window.add_action)
        menu.addAction('Collapse All',window.actions.collapseAll)
        menu.addAction('Expand All',window.actions.expandAll)
        return menu
    for label,callback,enabled in [('Add',window.add_action,True),('Edit',window.edit_action,selected),('Delete',window.delete_action,selected),('Duplicate',window.clone_action,selected),('Test Action',window.run_action,selected)]:menu.addAction(label,callback).setEnabled(enabled)
    if action.get('migrationBlock'):
        next(a for a in menu.actions() if a.text()=='Test Action').setEnabled(False)
        menu.addAction('Import prüfen …',lambda:window.review_import(action['id']))
    menu.addSeparator()
    def toggle():action['enabled']=not action.get('enabled',True);window.save_actions()
    a=menu.addAction('Enabled',toggle);a.setEnabled(selected);a.setCheckable(True);a.setChecked(action.get('enabled',True) if selected else False)
    if action.get('migrationBlock'):a.setChecked(False);a.setEnabled(False)
    for key,label in [('random','Random Action (RA)'),('concurrent','Concurrent (CC)'),('excludeHistory','Exclude from History')]:
        def toggle_option(checked=False,k=key):action[k]=not action.get(k,False);window.save_actions()
        option=menu.addAction(label,toggle_option);option.setEnabled(selected);option.setCheckable(True);option.setChecked(action.get(key,False) if selected else False)
    group=menu.addMenu('Group');group.setEnabled(selected)
    def set_group(name):action['group']=name;window.save_actions()
    for name in sorted({a.get('group','') for a in window.document['actions']}):group.addAction(name or '(None)',lambda checked=False,g=name:set_group(g))
    def new_group():
        name,ok=QInputDialog.getText(window,'Set Group','Group')
        if ok:set_group(name.strip())
    group.addAction('New Group...',new_group)
    queue=menu.addMenu('Queue');queue.setEnabled(selected)
    def set_queue(identity):action['queue']=identity;window.save_actions()
    queue.addAction('Default',lambda:set_queue(None))
    for q in window.document.get('queues',[]):queue.addAction(q['name'],lambda checked=False,i=q['id']:set_queue(i))
    menu.addAction('Copy Action ID',lambda:QApplication.clipboard().setText(action['id'])).setEnabled(selected)
    menu.addSeparator();menu.addAction('Collapse All',window.actions.collapseAll);menu.addAction('Expand All',window.actions.expandAll)
    return menu


TRIGGER_ROOTS=['Core','Custom','Elgato','Integrations','OBS Studio','Twitch','YouTube']
CORE_TRIGGER_ENTRIES=['StreamerMod Started','Test','Commands','File/Folder Watcher','File I/O','Global Variables','Groups','Inputs','MIDI','Processes','Quotes','Schedule','System','Voice Control','WebSocket']

def trigger_catalog(menu,callback,favorite,code_records=()):
    from .csharp_core_services import catalog as code_catalog
    catalog=code_catalog(triggers(),code_records)
    add_catalog(menu,catalog,callback,favorite,'Favorite Trigger')
    # The shared sorter uses the sub-action Core order; the trigger Core has
    # its own independently documented order.
    ordered_menu(menu,TRIGGER_ROOTS)
    core=next(entry.menu() for entry in menu.actions() if entry.text()=='Core')
    ordered_menu(core,CORE_TRIGGER_ENTRIES)
    return menu


def trigger_context(editor):
    menu=QMenu(editor.host);nodes,index,node=editor.selected_trigger();selected=node is not None
    selected_ids={item.data(0,Qt.ItemDataRole.UserRole) for item in editor.triggers.selectedItems()}
    try:preferences=editor.host.store.read('editor.json')
    except FileNotFoundError:preferences={}
    def save():editor.refresh()
    def favorite(kind):
        values=preferences.setdefault('triggerFavorites',[])
        if kind in values:values.remove(kind)
        else:values.append(kind)
        editor.host.store.save('editor.json',preferences)
    def clear():editor.value['triggers'].clear();save()
    def enable_all(value):
        for trigger in editor.value['triggers']:trigger['enabled']=value
        save()
    for label,callback in [('Clear All Triggers',clear),('Enable All Triggers',lambda:enable_all(True)),('Disable All Triggers',lambda:enable_all(False))]:menu.addAction(label,callback).setEnabled(bool(editor.value['triggers']))
    from .csharp_core_services import catalog as code_catalog
    code_records=getattr(editor.host,'code_triggers',[])
    menu.addSeparator();catalog=code_catalog(triggers(),code_records)
    favorites=menu.addMenu('Favorite Triggers');add_catalog(favorites,{k:catalog[k] for k in dict.fromkeys(preferences.get('triggerFavorites',[])) if k in catalog},editor.add_trigger);favorites.setEnabled(bool(favorites.actions()))
    recent=menu.addMenu('Recent Triggers')
    for kind in dict.fromkeys(preferences.get('recentTriggers',[])):
        if kind in catalog:recent.addAction(catalog[kind][0],lambda checked=False,k=kind:editor.add_trigger(k))
    recent.setEnabled(bool(recent.actions()));menu.addSeparator();trigger_catalog(menu.addMenu('Add'),editor.add_trigger,favorite,code_records)
    if selected:
        menu.addSeparator();menu.addAction('Test Trigger',editor.test_trigger);menu.addAction('Edit Trigger',editor.edit_trigger)
        def copy_selected():
            values=[t for t in editor.value['triggers'] if t['id'] in selected_ids]
            if len(values)==1:copy_node(values[0],'trigger')
            elif values:QApplication.clipboard().setText(json.dumps({'format':'streamer-linux-triggers-1','nodes':values},ensure_ascii=False))
        menu.addAction('Copy Trigger',copy_selected)
        def duplicate():nodes.insert(index+1,renewed(node));save()
        def delete_selected():
            editor.value['triggers']=[t for t in editor.value['triggers'] if t['id'] not in selected_ids];save()
        menu.addAction('Duplicate Trigger',duplicate);menu.addAction('Delete Trigger',delete_selected)
        def toggle():node['enabled']=not node.get('enabled',True);save()
        option=menu.addAction('Enabled',toggle);option.setCheckable(True);option.setChecked(node.get('enabled',True))
        selector='code:'+node['eventName'] if node['type']==90255 and node.get('eventName') else node['type']
        option=menu.addAction('Favorite Trigger',lambda:favorite(selector));option.setCheckable(True);option.setChecked(selector in preferences.get('triggerFavorites',[]))
    copied=clipboard_triggers()
    if copied:
        def paste():editor.value['triggers'].extend(renewed(t) for t in copied);save()
        menu.addAction('Paste Trigger',paste)
    return menu
