"""Keyboard selection paths; selection itself stays in the Qt scene, not the DB."""
from PyQt6 import QtCore, QtGui, QtWidgets, sip


class SelectionController(QtCore.QObject):
    activeChanged = QtCore.pyqtSignal()

    def __init__(self, view):
        super().__init__(view)
        self.view = view
        self.scene = view.scene()
        self.active_uid = None
        self.baseline = set()
        self.path = []
        self.steps = []
        self._selected = set()
        self._busy = False
        self._signature = None
        self._highlighted = None
        self._normalPen = QtGui.QPen(QtCore.Qt.GlobalColor.black, 1, QtCore.Qt.PenStyle.DashLine)
        self._activePen = QtGui.QPen(QtGui.QColor('#1769c2'), 2, QtCore.Qt.PenStyle.DashLine)
        self.scene.selectionChanged.connect(self.externalChange)
        self.externalChange()

    def items(self):
        if sip.isdeleted(self.scene):
            return {}
        return self.scene.visibleStemsById()

    def selected(self, items):
        return {stem.node['uid'] for stem in self.scene.selectedItems()
                if hasattr(stem, 'node') and items.get(stem.node['uid']) is stem}

    def reset(self):
        self.baseline = set()
        self.path = []
        self.steps = []
        self._signature = None

    def externalChange(self):
        # QGraphicsScene emits selectionChanged while its C++ destructor is
        # running; a view-owned controller can briefly outlive the scene.
        if self._busy or sip.isdeleted(self.scene):
            return
        items = self.items()
        selected = self.selected(items)
        added = selected - self._selected
        candidates = added or ({self.active_uid} if self.active_uid in selected else selected)
        self.active_uid = min(candidates, key=lambda uid:
            (items[uid].leaf.sceneBoundingRect().center().y(), uid)) if candidates else None
        self._selected = selected
        self.reset()
        self.visuals(items)
        self.activeChanged.emit()

    def clicked(self, uid):
        """Clicking an already selected node also establishes a fresh anchor."""
        self.reset()
        items = self.items()
        if uid in items and items[uid].isSelected():
            self.active_uid = uid
        self._selected = self.selected(items)
        self.visuals(items)
        self.activeChanged.emit()

    def active(self, items=None):
        items = self.items() if items is None else items
        selected = self.selected(items)
        if self.active_uid not in selected:
            self.externalChange()
        return items.get(self.active_uid)

    def visuals(self, items):
        selected = self.selected(items)
        highlighted = items.get(self.active_uid) if len(selected) > 1 and self.active_uid in selected else None
        if highlighted is self._highlighted:
            return
        for stem, pen in ((self._highlighted, self._normalPen), (highlighted, self._activePen)):
            if stem is None or sip.isdeleted(stem):
                continue
            if stem.selectpath.pen() != pen:
                # Stem bounds are derived from this child path and its pen.
                stem.prepareGeometryChange()
                stem.selectpath.setPen(pen)
        self._highlighted = highlighted

    def reveal(self, stem):
        rect = stem.leaf.sceneBoundingRect()
        visible = self.view.mapToScene(self.view.viewport().rect()).boundingRect()
        if not visible.contains(rect):
            if rect.width() > visible.width() or rect.height() > visible.height():
                rect = QtCore.QRectF(rect.center(), QtCore.QSizeF(1, 1))
            self.view.ensureVisible(rect, 20, 20)

    def apply(self, selected, active_uid, reveal=True):
        items = self.items()
        selected = set(selected) & items.keys()
        if active_uid not in selected:
            self.externalChange()
            return
        current = self.selected(items)
        changed = current != selected
        self._busy = True
        blocker = QtCore.QSignalBlocker(self.scene)
        try:
            self.active_uid = active_uid
            for uid in current ^ selected:
                items[uid].setSelected(uid in selected)
            self._selected = selected
            self.visuals(items)
            del blocker
            if changed:
                # Sidebar/inline observers see one complete selection, not a
                # transient clear followed by several individual additions.
                self.scene.selectionChanged.emit()
            self.activeChanged.emit()
        finally:
            self._busy = False
        if reveal:
            self.reveal(items[active_uid])
        self.scene.statusMessage.emit(f'{len(selected)} node(s) selected' +
            ('; branch actions include descendants' if len(selected) > 1 else ''))

    def collapse(self, reveal=True):
        stem = self.active()
        self.reset()
        if stem is not None:
            self.apply({stem.node['uid']}, stem.node['uid'], reveal=reveal)

    def available(self):
        if sip.isdeleted(self.scene) or self.scene.mode != 'edit' or getattr(getattr(self.view, 'inline', None), 'item', None) is not None:
            return False
        focus = self.scene.focusItem()
        return not (isinstance(focus, QtWidgets.QGraphicsTextItem) and
                    focus.textInteractionFlags() & QtCore.Qt.TextInteractionFlag.TextEditable)

    def protectShortcut(self, event):
        from .graphics import shortcutModifiers
        if not self.available():
            return False
        keys = QtCore.Qt.Key
        modifiers = shortcutModifiers(event)
        return (modifiers == QtCore.Qt.KeyboardModifier.ShiftModifier and
                event.key() in (keys.Key_Up, keys.Key_Down, keys.Key_Left, keys.Key_Right)) or (
                modifiers == QtCore.Qt.KeyboardModifier.NoModifier and event.key() == keys.Key_Escape
                and len(self.scene.selectedItems()) > 1)

    def handleKey(self, event):
        if not self.protectShortcut(event):
            return False
        event.accept()
        keys = QtCore.Qt.Key
        if event.key() == keys.Key_Escape:
            if not event.isAutoRepeat():
                self.collapse(reveal=False)
            return True
        items = self.items()
        stem = self.active(items)
        if stem is None:
            return True  # No selection: consume instead of letting Qt pan.
        uid = stem.node['uid']
        signature = self.scene.graph.connection.total_changes()
        if self._signature != signature or any(p not in items for p in self.path):
            self.reset()
        if not self.path:
            self.baseline = self.selected(items)
            self.path = [uid]
            self._signature = signature
        opposite = {keys.Key_Up: keys.Key_Down, keys.Key_Down: keys.Key_Up,
                    keys.Key_Left: keys.Key_Right, keys.Key_Right: keys.Key_Left}
        if self.steps and event.key() == opposite[self.steps[-1]]:
            self.path.pop()
            self.steps.pop()
        else:
            target = self.view.arrowTarget(stem, event.key(), expand=False,
                                           exclude=set(self.path))
            if target is None:
                return True
            self.path.append(target.node['uid'])
            self.steps.append(event.key())
        self.apply(self.baseline | set(self.path), self.path[-1])
        return True
