"""A clean map outline with task-state controls, without internal metadata."""
import logging
import copy
from types import SimpleNamespace

from bs4 import BeautifulSoup
from PyQt6 import QtCore, QtGui, QtWidgets
from . import graphics, tasks
from .text_processing import source_summary

HINT = 'Click to locate · Enter to edit\nArrows browse and fold the outline.'


def node_title(node):
    """First readable text line, preserving inline formatting as plain text."""
    content = sorted(node.get('content', {}).values(), key=lambda value: value.get('z', 0))
    for value in content:
        if value.get('kind') != 'Text':
            continue
        title, _ = source_summary(value.get('source', ''))
        if title:
            return title
    kinds = {value.get('kind') for value in content}
    return 'Drawing' if 'Stroke' in kinds else ('Image' if 'Image' in kinds else 'Untitled')


def drawing_icon(node):
    """Render only stored strokes/images, without modifying the map or DB."""
    preview = QtWidgets.QGraphicsScene()
    stem = SimpleNamespace(node=node)
    try:
        for uid, value in node.get('content', {}).items():
            if value.get('kind') == 'Stroke':
                graphics.InkItem(uid, stem, scene=preview)
            elif value.get('kind') == 'Image':
                graphics.PixmapItem(uid, stem, scene=preview)
        if not preview.items():
            return QtGui.QIcon()
        image = QtGui.QPixmap(48, 32)
        image.fill(QtCore.Qt.GlobalColor.white)
        painter = QtGui.QPainter(image)
        try:
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
            preview.render(painter, QtCore.QRectF(2, 2, 44, 28), preview.itemsBoundingRect().adjusted(-2, -2, 2, 2))
        finally:
            painter.end()
        return QtGui.QIcon(image)
    except Exception:
        # A broken optional preview must not make a map inaccessible.
        logging.exception('Could not render a Contents thumbnail')
        return QtGui.QIcon()
    finally:
        preview.clear()


class ContentsPanel(QtWidgets.QWidget):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.items = {}
        self._signature = None
        self._topology = None
        self._content = {}
        self._tasks = {}
        self._syncing = False
        self._stopped = False
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setItemDelegate(tasks.TaskDelegate(self.tree))
        self.tree.setColumnCount(1)
        self.tree.setIndentation(18)
        self.tree.setIconSize(QtCore.QSize(48, 32))
        self.tree.setTextElideMode(QtCore.Qt.TextElideMode.ElideRight)
        self.tree.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tree.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tree.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.setExpandsOnDoubleClick(False)
        self.tree.setAccessibleName('Contents: map nodes in parent and child order')
        self.tree.installEventFilter(self)
        layout.addWidget(self.tree)
        self.hint = QtWidgets.QLabel(HINT)
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)
        self.tree.itemSelectionChanged.connect(self.selectOnMap)
        self.tree.itemActivated.connect(self.editNode)
        self.tree.itemChanged.connect(self.taskChanged)
        # The controller forwards external scene changes and emits once after
        # a complete keyboard selection, including active-node-only changes.
        owner.view.selection.activeChanged.connect(self.syncSelection)
        owner.scene.changed.connect(self.scheduleRefresh)
        self.refreshTimer = QtCore.QTimer(self)
        self.refreshTimer.setSingleShot(True)
        self.refreshTimer.timeout.connect(self.refresh)
        # DB saves can happen before any graphics refresh (e.g. text edits).
        # Check a cheap SQLite change counter, not the full tree, while idle.
        self.pollTimer = QtCore.QTimer(self)
        self.pollTimer.setInterval(250)
        self.pollTimer.timeout.connect(self.refresh)
        self.pollTimer.start()
        self.refresh()

    def sizeHint(self):
        # Prefer a compact sidebar without imposing a maximum: users may drag
        # it wider. Long instructions must not determine its initial width.
        return QtCore.QSize(260, 380)

    def stop(self):
        if self._stopped:
            return
        self._stopped = True
        self.pollTimer.stop()
        self.refreshTimer.stop()
        self.tree.blockSignals(True)
        self.owner.view.selection.activeChanged.disconnect(self.syncSelection)
        self.owner.scene.changed.disconnect(self.scheduleRefresh)

    def available(self):
        if self._stopped:
            return False
        dialog = getattr(self.owner, 'editDialog', None)
        return self.owner.scene.mode == 'edit' and (dialog is None or not dialog.isVisible())

    def scheduleRefresh(self, *unused):
        if not self._stopped and self.pollTimer.isActive() and not self.refreshTimer.isActive():
            self.refreshTimer.start(0)

    def refresh(self):
        if self._stopped:
            return
        available = self.available()
        self.tree.setEnabled(available)
        self.hint.setText(HINT
                          if available else 'Return to map editing to use Contents.')
        if self._syncing:
            self.scheduleRefresh()
            return
        graph = self.owner.scene.graph
        signature = (graph.connection.total_changes(), tasks.doing_enabled())
        if signature == self._signature:
            return
        nodes = {n['uid']: n for n in graph.fetch('[n:Stem]')}
        roots = {n['uid'] for n in graph.fetch('[r:Root]')}
        children = {}
        for edge in graph.fetch('(p) -[e:Child]> (n)'):
            if edge['enduid'] in nodes:
                children.setdefault(edge['startuid'], []).append(edge['enduid'])
        order = lambda uid: (nodes[uid].get('pos', [0, 0])[1], uid)
        root_nodes = sorted({uid for root in roots for uid in children.get(root, [])}, key=order)
        children = {uid: sorted(values, key=order) for uid, values in children.items()}
        topology = (tuple(root_nodes), tuple(sorted((uid, tuple(values)) for uid, values in children.items())))
        if topology == self._topology:
            # Preserve rows, folding, selection and scroll while editing text.
            # Metadata-only saves need neither HTML parsing nor thumbnails.
            blocker = QtCore.QSignalBlocker(self.tree)
            for uid, item in self.items.items():
                content = nodes[uid].get('content', {})
                if content != self._content.get(uid):
                    self.updateItem(item, nodes[uid])
                elif (self._tasks.get(uid) != (tasks.is_task(nodes[uid]), tasks.state(nodes[uid])) or
                      bool(item.flags() & QtCore.Qt.ItemFlag.ItemIsUserTristate) != tasks.doing_enabled() and tasks.is_task(nodes[uid])):
                    self.updateTask(item, nodes[uid])
            self._signature = signature
            del blocker
            return
        expanded = {uid: item.isExpanded() for uid, item in self.items.items()}
        current = self.tree.currentItem()
        current_uid = current.data(0, QtCore.Qt.ItemDataRole.UserRole) if current else None
        scroll = self.tree.verticalScrollBar().value()
        blocker = QtCore.QSignalBlocker(self.tree)
        self.tree.clear()
        self.items = {}
        self._content = {}
        self._tasks = {}
        stack = [(uid, None) for uid in reversed(root_nodes)]
        while stack:
            uid, parent = stack.pop()
            if uid in self.items:
                continue  # Protect against damaged cyclic/duplicate edges.
            node = nodes[uid]
            item = QtWidgets.QTreeWidgetItem()
            item.setData(0, QtCore.Qt.ItemDataRole.UserRole, uid)
            self.updateItem(item, node)
            if parent is None:
                self.tree.addTopLevelItem(item)
            else:
                parent.addChild(item)
            self.items[uid] = item
            item.setExpanded(expanded.get(uid, parent is None))
            stack.extend((child, item) for child in reversed(children.get(uid, [])))
        if current_uid in self.items:
            self.tree.setCurrentItem(self.items[current_uid])
        self._signature = signature
        self._topology = topology
        self.syncSelection(expand=False)
        self.tree.verticalScrollBar().setValue(scroll)
        del blocker

    def updateItem(self, item, node):
        title = node_title(node)
        item.setText(0, title)
        item.setToolTip(0, title)
        has_text = any(value.get('kind') == 'Text' and
                       source_summary(value.get('source', ''))[1]
                       for value in node.get('content', {}).values())
        item.setIcon(0, QtGui.QIcon() if has_text else drawing_icon(node))
        # Copy: node content may subsequently be changed in place by an editor.
        self._content[node['uid']] = copy.deepcopy(node.get('content', {}))
        self.updateTask(item, node)

    def updateTask(self, item, node):
        task, current = tasks.is_task(node), tasks.state(node)
        checked = current == tasks.DONE
        self._tasks[node['uid']] = (task, current)
        flags = item.flags()
        item.setFlags(flags | QtCore.Qt.ItemFlag.ItemIsUserCheckable if task else
                      flags & ~QtCore.Qt.ItemFlag.ItemIsUserCheckable)
        flags = item.flags()
        item.setFlags(flags | QtCore.Qt.ItemFlag.ItemIsUserTristate if task and tasks.doing_enabled() else
                      flags & ~QtCore.Qt.ItemFlag.ItemIsUserTristate)
        item.setData(0, QtCore.Qt.ItemDataRole.CheckStateRole,
                     tasks.check_state(current) if task else None)
        font = item.font(0)
        font.setStrikeOut(checked)
        item.setFont(0, font)
        color = '#777777' if checked else '#946200' if task and current == tasks.DOING else None
        item.setForeground(0, QtGui.QBrush(QtGui.QColor(color)) if color else QtGui.QBrush())
        if task:
            item.setToolTip(0, item.text(0) + ' — ' + current.title())
            item.setData(0, QtCore.Qt.ItemDataRole.AccessibleTextRole, item.text(0) + ' — ' + current.title())
        else:
            item.setToolTip(0, item.text(0))
            item.setData(0, QtCore.Qt.ItemDataRole.AccessibleTextRole, None)

    def taskChanged(self, item, column):
        if self._stopped or self._syncing or column != 0:
            return
        uid = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if uid not in self._tasks or not self._tasks[uid][0]:
            return
        current = {QtCore.Qt.CheckState.Unchecked: tasks.TODO, QtCore.Qt.CheckState.PartiallyChecked: tasks.DOING,
                   QtCore.Qt.CheckState.Checked: tasks.DONE}[item.checkState(0)]
        if current == self._tasks[uid][1]:
            return
        if self.available() and self.owner.view.tasks.setState(uid, current):
            self.refresh()
        else:
            blocker = QtCore.QSignalBlocker(self.tree)
            item.setCheckState(0, tasks.check_state(self._tasks[uid][1]))
            del blocker

    def syncSelection(self, *unused, expand=True):
        if self._stopped or self._syncing:
            return
        selected = {item.node['uid'] for item in self.owner.scene.selectedItems()
                    if isinstance(item, graphics.StemItem)} & self.items.keys()
        current_selected = {item.data(0, QtCore.Qt.ItemDataRole.UserRole)
                            for item in self.tree.selectedItems()}
        active = self.owner.view.selection.active_uid
        current = self.tree.currentItem()
        current_uid = current.data(0, QtCore.Qt.ItemDataRole.UserRole) if current else None
        target_uid = active if active in selected else (current_uid if current_uid in selected else
                                                       min(selected) if selected else None)
        moved = target_uid is not None and current_uid != target_uid
        added = selected - current_selected
        blocker = QtCore.QSignalBlocker(self.tree)
        if moved:
            self.tree.setCurrentItem(self.items[target_uid], 0,
                                     QtCore.QItemSelectionModel.SelectionFlag.NoUpdate)
        for uid in current_selected ^ selected:
            self.items[uid].setSelected(uid in selected)
        for uid in added | ({target_uid} if moved else set()):
            item = self.items[uid]
            if expand:
                parent = item.parent()
                while parent is not None:
                    parent.setExpanded(True)
                    parent = parent.parent()
        if target_uid is not None and expand and (moved or added):
            self.tree.scrollToItem(self.items[target_uid])
        del blocker

    def selectOnMap(self):
        if self._syncing:
            return
        if not self.available():
            self.syncSelection()
            return
        uids = [item.data(0, QtCore.Qt.ItemDataRole.UserRole) for item in self.tree.selectedItems()]
        self._syncing = True
        try:
            self.owner.view.inline.finish(select=False)
            if uids:
                self.owner.scene.selectNodes(uids, reveal_hidden=True, focus=False)
            else:
                self.owner.scene.clearSelection()
        finally:
            self._syncing = False
        self.scheduleRefresh()

    def editNode(self, *unused):
        if not self.available():
            return
        item = self.tree.currentItem()
        if item is None:
            return
        uid = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        self._syncing = True
        try:
            self.owner.view.inline.finish(select=False)
            self.owner.scene.selectNodes([uid], reveal_hidden=True, focus=False)
        finally:
            self._syncing = False
        stem = next((s for s in self.owner.scene.allChildStems() if s.node['uid'] == uid), None)
        if stem is not None:
            stem._keyboard_view = self.owner.view
            stem.editStem()
            self.refresh()

    def eventFilter(self, watched, event):
        if watched is self.tree and event.type() == QtCore.QEvent.Type.KeyPress:
            if graphics.shortcutModifiers(event) == QtCore.Qt.KeyboardModifier.NoModifier:
                if event.key() in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter):
                    if not event.isAutoRepeat():
                        self.editNode()
                    return True
        return super().eventFilter(watched, event)
