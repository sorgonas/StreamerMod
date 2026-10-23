"""Drag/drop updates the action document, not just the displayed tree."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTreeWidget,QAbstractItemView
ROLE=Qt.ItemDataRole.UserRole

class SubActionTree(QTreeWidget):
    def __init__(self,editor):
        super().__init__();self.editor=editor
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction);self.setDropIndicatorShown(True)

    def startDrag(self,supportedActions):
        # QAbstractItemView.startDrag removes source rows after an accepted Move.
        # We already update and rebuild the tree in dropEvent; never delete twice.
        from PySide6.QtGui import QDrag
        item=self.currentItem()
        if item is None:return
        self.dragged_node_id=item.data(0,ROLE)
        drag=QDrag(self);drag.setMimeData(self.mimeData([item]))
        try:drag.exec(Qt.DropAction.MoveAction)
        finally:self.dragged_node_id=None

    def dropEvent(self,event):
        if event.source() is not self or not self.currentItem():event.ignore();return
        source=getattr(self,'dragged_node_id',None) or self.currentItem().data(0,ROLE);target=self.itemAt(event.position().toPoint())
        location=self.dropIndicatorPosition()
        if target is None:parent=None;index=len(self.editor.value['subActions'])
        elif location==QAbstractItemView.DropIndicatorPosition.OnItem:
            parent=target.data(0,ROLE);index=target.childCount()
        else:
            owner=target.parent();parent=owner.data(0,ROLE) if owner else None
            index=(owner.indexOfChild(target) if owner else self.indexOfTopLevelItem(target))
            if location==QAbstractItemView.DropIndicatorPosition.BelowItem:index+=1
        if self.editor.move_node(source,parent,index):event.acceptProposedAction()
        else:event.ignore()
