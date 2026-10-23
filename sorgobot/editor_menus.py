"""Context-menu operations shared by the legacy and independent native editor."""
import copy
import uuid
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMenu, QApplication
from .catalog import STEPS, TRIGGERS


def renewed(node):
    value=copy.deepcopy(node)
    value['id']=str(uuid.uuid4())
    for key in ('subActions','triggers'):
        if key in value:value[key]=[renewed(child) for child in value[key]]
    return value


def bind(tree, build):
    previous=getattr(tree,'_context_callback',None)
    if previous is not None:tree.customContextMenuRequested.disconnect(previous)
    tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    def show(position):
        item=tree.itemAt(position)
        tree.setCurrentItem(item)
        build().exec(tree.viewport().mapToGlobal(position))
    tree._context_callback=show
    tree.customContextMenuRequested.connect(show)


def catalog_menu(menu, catalog, callback):
    add=menu.addMenu('Hinzufügen');categories={}
    for kind,(label,_) in catalog.items():
        category,separator,name=label.partition(' · ')
        parent=add
        if separator:
            if category not in categories:categories[category]=add.addMenu(category)
            parent=categories[category]
        parent.addAction(name if separator else label,lambda checked=False,k=kind:callback(k))
    return add


def editor_menu(editor, trigger=False):
    menu=QMenu(editor)
    catalog_menu(menu,TRIGGERS if trigger else STEPS,editor.add_trigger if trigger else editor.add_step)
    tree=editor.triggers if trigger else editor.steps
    menu.addSeparator()
    def operate(operation):
        if trigger:
            item=tree.currentItem()
            nodes=editor.value['triggers']
            index=next((i for i,n in enumerate(nodes) if item and n['id']==item.data(0,Qt.ItemDataRole.UserRole)),None)
            node=nodes[index] if index is not None else None
        else:nodes,index,node=editor.selected()
        if node is None:return
        if operation=='toggle':node['enabled']=not node.get('enabled',True)
        elif operation=='duplicate':nodes.insert(index+1,renewed(node))
        elif operation=='copy':editor.copied_node=copy.deepcopy(node)
        editor.refresh()
    for label,callback in [('Bearbeiten',editor.edit_trigger if trigger else editor.edit_step),
                           ('Aktiviert umschalten',lambda:operate('toggle')),
                           ('Duplizieren',lambda:operate('duplicate')),
                           ('Entfernen',editor.remove_trigger if trigger else editor.remove_step)]:
        action=menu.addAction(label,callback);action.setEnabled(tree.currentItem() is not None)
    if not trigger:
        menu.addAction('Kopieren',lambda:operate('copy')).setEnabled(tree.currentItem() is not None)
        def paste():
            node=renewed(editor.copied_node);nodes,index,selected=editor.selected()
            if selected and 'subActions' in selected and selected['type']!=120:selected['subActions'].append(node)
            elif nodes is not None:nodes.insert(index+1,node)
            else:editor.value['subActions'].append(node)
            editor.refresh()
        menu.addAction('Einfügen',paste).setEnabled(hasattr(editor,'copied_node'))
        menu.addAction('Nach oben',lambda:editor.move(-1)).setEnabled(tree.currentItem() is not None)
        menu.addAction('Nach unten',lambda:editor.move(1)).setEnabled(tree.currentItem() is not None)
    menu.addSeparator();menu.addAction('Alle ausklappen',tree.expandAll);menu.addAction('Alle einklappen',tree.collapseAll)
    return menu


def action_menu(window):
    menu=QMenu(window);menu.addAction('Hinzufügen',window.add_action)
    for label,callback in [('Bearbeiten',window.edit_action),('Duplizieren',window.clone_action),
                           ('Entfernen',window.delete_action),('Ausführen',window.run_action)]:
        menu.addAction(label,callback).setEnabled(window.current_action() is not None)
    def toggle():
        action=window.current_action()
        if action:action['enabled']=not action.get('enabled',True);window.save_actions()
    menu.addAction('Aktiviert umschalten',toggle).setEnabled(window.current_action() is not None)
    def copy_id():
        if window.current_action():QApplication.clipboard().setText(window.current_action()['id'])
    menu.addAction('Aktions-ID kopieren',copy_id).setEnabled(window.current_action() is not None)
    menu.addSeparator();menu.addAction('Alle ausklappen',window.actions.expandAll);menu.addAction('Alle einklappen',window.actions.collapseAll)
    return menu


def detail_menu(window,trigger=False):
    from .desktop import ActionDialog, ROLE
    action=window.current_action()
    if not action:
        menu=QMenu(window);menu.addAction('Zuerst eine Aktion auswählen').setEnabled(False);return menu
    editor=ActionDialog(action,window.store,window)
    view=window.trigger_view if trigger else window.step_view
    tree=editor.triggers if trigger else editor.steps
    identity=view.currentItem().data(0,ROLE) if view.currentItem() else None
    def select(parent):
        for i in range(parent.childCount()):
            item=parent.child(i)
            if item.data(0,ROLE)==identity:tree.setCurrentItem(item)
            select(item)
    select(tree.invisibleRootItem())
    menu=editor_menu(editor,trigger)
    # Persist after refresh, when the operation has actually updated the document.
    def persist():
        if editor.value!=action:
            window.document['actions']=[editor.value if a['id']==action['id'] else a for a in window.document['actions']]
            window.save_actions()
    refresh=editor.refresh
    def refresh_and_save():
        refresh();persist()
    editor.refresh=refresh_and_save
    menu.editor=editor
    return menu
