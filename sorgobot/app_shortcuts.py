"""Original application shortcuts scoped to their actual focused editors."""
import json
from PySide6.QtCore import Qt
from PySide6.QtGui import QShortcut,QKeySequence
from PySide6.QtWidgets import QApplication,QAbstractItemView

def bind(widget,sequence,callback):
 shortcut=QShortcut(QKeySequence(sequence),widget);shortcut.setContext(Qt.ShortcutContext.WidgetShortcut);shortcut.activated.connect(callback)
 widget._editor_shortcuts=getattr(widget,'_editor_shortcuts',[])+[shortcut]

def invoke(build,path):
 menu=build();target=menu
 try:
  for i,label in enumerate(path):
   action=next((a for a in target.actions() if a.text()==label),None)
   if action is None or not action.isEnabled():return
   if i<len(path)-1:
    target=action.menu()
    if target is None:return
   else:action.trigger()
 finally:menu.deleteLater()

def editor(editor):
 from .next_menus import editor_context
 for sequence,path in [('Delete',['Delete Sub-Action']),('Ctrl+D',['Duplicate Sub-Action']),('Ctrl+C',['Copy Sub-Action']),('Ctrl+V',['Paste Sub-Action']),('Ctrl+O',['Enabled']),('Ctrl+R',['Rename Group']),('Ctrl+Up',['Move','Up']),('Ctrl+Down',['Move','Down']),('Ctrl+Home',['Move','Top']),('Ctrl+End',['Move','Bottom'])]:
  bind(editor.steps,sequence,lambda p=path:invoke(lambda:editor_context(editor),p))
 for sequence,path in [('F5',['Test Trigger']),('Delete',['Delete Trigger']),('Ctrl+C',['Copy Trigger']),('Ctrl+V',['Paste Trigger']),('Ctrl+O',['Enabled'])]:
  bind(editor.triggers,sequence,lambda p=path:invoke(lambda:editor_context(editor,True),p))
 editor.triggers.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

def actions(window):
 from .next_menus import action_context
 from .editor_menus import renewed
 from .catalog import validate_action
 def copy():
  value=window.current_action()
  if value:
   from .original_bundles import entries
   bundles=[b for b in entries(window.document).values() if value['id'] in b['actionIds']]
   queues=[q for q in window.document.get('queues',[]) if q['id']==value.get('queue')]
   QApplication.clipboard().setText(json.dumps({'format':'streamer-linux-action-1','action':value,'originalBundles':bundles,'queues':queues,'originalResources':window.document.get('originalResources',{}),'importBindings':window.document.get('importBindings',{})},ensure_ascii=False))
 def paste():
  try:
   value=json.loads(QApplication.clipboard().text())
   if not isinstance(value,dict) or value.get('format')!='streamer-linux-action-1':return
   action=renewed(validate_action(value['action']))
   from .original_bundles import merge_native
   window.document=merge_native(window.document,{'format':'streamer-linux-actions-1','actions':[action],'queues':value.get('queues',[]),'originalBundles':value.get('originalBundles',[]),'originalResources':value.get('originalResources',{}),'importBindings':value.get('importBindings',{})})
   window.save_actions()
  except (ValueError,KeyError,TypeError):return
 for sequence,label in [('Delete','Delete'),('Ctrl+D','Duplicate'),('Ctrl+O','Enabled')]:bind(window.actions,sequence,lambda label=label:invoke(lambda:action_context(window),[label]))
 bind(window.actions,'Ctrl+C',copy);bind(window.actions,'Ctrl+V',paste)
 window.actions.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
 window._paste_action=paste;window._object_paste=ObjectPaste(window)

def commands(window):
 for sequence,label in [('Delete','Delete'),('Ctrl+R','Rename Group'),('Ctrl+C','Copy Command ID'),('Ctrl+O','Enabled')]:
  bind(window.command_table,sequence,lambda label=label:invoke(window.command_context,[label]))
 bind(window.command_table,'Ctrl+*',window.command_table.expandAll)
 bind(window.command_table,'Ctrl+-',window.command_table.collapseAll)

def timers(window,menu):
 for sequence,label in [('Delete','Delete'),('Ctrl+O','Enabled')]:
  bind(window.timer_table,sequence,lambda label=label:invoke(menu,[label]))

def core(page):
 if page.section not in ('midiDevices','voiceCommands'):return
 bind(page.table,'Delete',page.remove)
 if page.section=='voiceCommands':
  for sequence,direction in [('Ctrl+Up','up'),('Ctrl+Down','down'),('Ctrl+Home','top'),('Ctrl+End','bottom')]:
   bind(page.table,sequence,lambda d=direction:page.move_voice(d))
 if page.bindings is not None:
  bind(page.bindings,'Delete',lambda:page.change_binding(remove=True))
  bind(page.bindings,'Ctrl+O',page.change_binding)

# Typed program objects may be pasted from any non-text control in the main window.
from PySide6.QtCore import QObject,QEvent
from PySide6.QtWidgets import QLineEdit,QTextEdit,QPlainTextEdit,QAbstractSpinBox
class ObjectPaste(QObject):
 def __init__(self,window):
  super().__init__(window);self.window=window;QApplication.instance().installEventFilter(self)
 def target(self,widget):
  if widget is None or widget.window()!=self.window:return None
  current=widget
  while current and current!=self.window:
   if isinstance(current,(QLineEdit,QTextEdit,QPlainTextEdit,QAbstractSpinBox)):return None
   current=current.parentWidget()
  text=QApplication.clipboard().text()
  if len(text)>4*1024*1024:return None
  try:value=json.loads(text)
  except (ValueError,RecursionError):return None
  if not isinstance(value,dict):return None
  fmt=value.get('format');editor=getattr(self.window,'editor',None)
  if fmt=='streamer-linux-action-1':return self.window._paste_action
  if editor is None:return None
  from .next_menus import editor_context,clipboard_node,clipboard_triggers
  if clipboard_triggers():return lambda:invoke(lambda:editor_context(editor,True),['Paste Trigger'])
  if clipboard_node('step') is not None:return lambda:invoke(lambda:editor_context(editor),['Paste Sub-Action'])
  return None
 def eventFilter(self,watched,event):
  if event.type() not in (QEvent.Type.ShortcutOverride,QEvent.Type.KeyPress) or not event.matches(QKeySequence.StandardKey.Paste):return False
  callback=self.target(QApplication.focusWidget())
  if callback is None:return False
  event.accept()
  if event.type()==QEvent.Type.KeyPress:callback()
  return True
