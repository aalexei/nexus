"""Task metadata and a per-map-window creation mode; text stays untouched."""
import logging
import copy
from PyQt6 import QtCore, QtGui, QtWidgets
from . import graphydb


def is_task(node):
    return node.get('todo', False) is True


TODO, DOING, DONE = 'todo', 'doing', 'done'


def state(node):
    # Existing two-state tasks need no migration or automatic DB writes.
    if is_task(node) and node.get('todo_done', False) is True:
        return DONE
    return DOING if is_task(node) and node.get('todo_state') == DOING else TODO


def done(node):
    return is_task(node) and state(node) == DONE


def doing_enabled():
    return QtCore.QSettings('Ectropy', 'Nexus').value('todoDoingEnabled', True, type=bool)


def next_state(current):
    if current == DONE:
        return TODO
    if current == DOING or not doing_enabled():
        return DONE
    return DOING


def check_state(current):
    return {TODO: QtCore.Qt.CheckState.Unchecked, DOING: QtCore.Qt.CheckState.PartiallyChecked,
            DONE: QtCore.Qt.CheckState.Checked}[current]


def draw_box(painter, rect, current):
    painter.save()
    painter.translate(rect.topLeft())
    painter.scale(rect.width() / 20, rect.height() / 20)
    border, fill = {TODO: ('#555555', '#ffffff'), DOING: ('#a16a00', '#ffe391'),
                    DONE: ('#287747', '#e2f3e8')}[current]
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    painter.setPen(QtGui.QPen(QtGui.QColor(border), 1.5))
    painter.setBrush(QtGui.QColor(fill))
    painter.drawRoundedRect(QtCore.QRectF(0, 0, 20, 20), 3, 3)
    if current == DONE:
        painter.setPen(QtGui.QPen(QtGui.QColor(border), 2.5))
        painter.drawPolyline(QtGui.QPolygonF([QtCore.QPointF(4, 10), QtCore.QPointF(8, 14), QtCore.QPointF(16, 5)]))
    elif current == DOING:
        painter.setPen(QtGui.QPen(QtGui.QColor(border), 2.5))
        painter.drawLine(QtCore.QPointF(5, 10), QtCore.QPointF(15, 10))
    painter.restore()


def export_title(stem):
    prefix = {TODO: '[ ] ', DOING: '[-] ', DONE: '[x] '}[state(stem.node)] if is_task(stem.node) else ''
    return prefix + ' '.join(stem.titles())


class TaskBox(QtWidgets.QGraphicsItem):
    def __init__(self, leaf):
        super().__init__(leaf)
        self.leaf = leaf
        self.setAcceptedMouseButtons(QtCore.Qt.MouseButton.NoButton)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.refreshTip()

    def refreshTip(self):
        current = state(self.leaf.stem.node)
        self.setToolTip(f'{current.title()} — click for {next_state(current).title()}')

    def boundingRect(self):
        return QtCore.QRectF(-2, -2, 24, 24)

    def paint(self, painter, option, widget):
        draw_box(painter, QtCore.QRectF(0, 0, 20, 20), state(self.leaf.stem.node))


class TaskDelegate(QtWidgets.QStyledItemDelegate):
    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        if index.data(QtCore.Qt.ItemDataRole.CheckStateRole) is None:
            return
        opt = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        widget = option.widget
        style = widget.style() if widget is not None else QtWidgets.QApplication.style()
        rect = style.subElementRect(QtWidgets.QStyle.SubElement.SE_ItemViewItemCheckIndicator, opt, widget)
        value = index.data(QtCore.Qt.ItemDataRole.CheckStateRole)
        current = {0: TODO, 1: DOING, 2: DONE}[value.value if isinstance(value, QtCore.Qt.CheckState) else value]
        draw_box(painter, QtCore.QRectF(rect).adjusted(1, 1, -1, -1), current)


class TaskController(QtCore.QObject):
    modeChanged = QtCore.pyqtSignal(bool)

    def __init__(self, view):
        super().__init__(view)
        self.view = view
        self.scene = view.scene()
        self.enabled = False  # Session-local: never leak into another/reopened map.

    def available(self):
        owner = self.view.window()
        dialog = getattr(owner, 'editDialog', None)
        resize = getattr(self.view, 'contentResize', None)
        return (self.scene.mode == 'edit' and (dialog is None or not dialog.isVisible())
                and (resize is None or resize.state is None))

    def convertSelected(self, stem, current=TODO):
        """Set/remove task metadata atomically without disturbing live text."""
        from .graphics import scaleRotateMove
        graph = self.scene.graph
        inline = self.view.inline
        editing = inline.item is not None and inline.item.stem is stem
        if editing and not inline.checkpoint():
            return False
        original = copy.deepcopy(stem.node.data)
        original_transform = QtGui.QTransform(stem.transform())
        geometry_changed = is_task(stem.node) != (current is not None)
        origin = stem.leaf.mapToScene(QtCore.QPointF())
        children = []
        for child in stem.node.outN('e.kind="Child"') if geometry_changed else ():
            pos = child['pos']
            base = stem.tip() + QtCore.QPointF(stem.direction()*child.get('flip', 1)*pos[0], pos[1])
            children.append((child['uid'], stem.mapToScene(base)))
        # While a brand-new node is being entered, its metadata belongs to
        # creation. Otherwise Undo could delete the node before an older
        # standalone task-change record and later restore an orphan.
        batch = inline.batch if editing and getattr(stem, '_inline_new', False) else graphydb.generateUUID()
        try:
            node = graph.getuid(stem.node['uid'])
            if node is None:
                raise ValueError('The selected note no longer exists')
            # Preview the existing task geometry to compensate for the checkbox
            # added to the left. Do not rewrite text/image/stroke content.
            for key, value in (('todo', True), ('todo_done', current == DONE), ('todo_state', current)):
                if current is None:
                    stem.node.discard(key)
                    node.discard(key)
                else:
                    stem.node[key] = value
                    node[key] = value
            if geometry_changed:
                stem.leaf.updateTaskBox()
                stem.leaf.titlerect = stem.leaf.childrenBoundingRect().adjusted(-3, -3, 3, 3)
                stem.leaf.setBoundingRect()
                stem.positionLeaf()
                displacement = origin - stem.leaf.mapToScene(QtCore.QPointF())
                parent = stem.parentStem()
                base = stem.mapToScene(QtCore.QPointF()) + displacement
                if parent is not None:
                    base = parent.mapFromScene(base)
                    offset = base - parent.tip()
                    node['pos'] = [stem.direction()*offset.x(), offset.y()]
                else:
                    node['pos'] = [base.x(), base.y()]
                stem.setTransform(scaleRotateMove(float(stem.node.get('scale', 1.0)),
                    stem.node.get('angle', 0.0), base.x(), base.y()))
            with graph.connection:
                node.save(batch=batch)
                for uid, point in children:
                    child = graph.getuid(uid)
                    base = stem.mapFromScene(point) - stem.tip()
                    child['pos'] = [stem.direction()*child.get('flip', 1)*base.x(), base.y()]
                    child.save(batch=batch)
        except Exception as error:
            logging.exception('Could not cycle task state')
            if editing:
                for key in ('todo', 'todo_done', 'todo_state', 'pos'):
                    if key in original:
                        stem.node[key] = original[key]
                    else:
                        stem.node.discard(key)
                stem.node.setChanged(False)
                stem.setTransform(original_transform)
                stem.leaf.updateTaskBox()
                stem.leaf.titlerect = stem.leaf.childrenBoundingRect().adjusted(-3, -3, 3, 3)
                stem.leaf.setBoundingRect()
                stem.positionLeaf()
            else:
                stem.renew()
            if stem.leaf.taskbox is not None:
                stem.leaf.taskbox.refreshTip()
            self.scene.statusMessage.emit(f'Task change could not be saved: {error}. The node was left unchanged.')
            return False
        if editing:
            # A later text checkpoint must not fold this independent task
            # operation into the text session's Undo record.
            for key in ('todo', 'todo_done', 'todo_state', 'pos'):
                if key in node:
                    stem.node[key] = copy.deepcopy(node[key])
                    inline.baseline[key] = copy.deepcopy(node[key])
                else:
                    stem.node.discard(key)
                    inline.baseline.pop(key, None)
            stem.node.setChanged(False)
            for child in list(stem.childStems2) if geometry_changed else ():
                child.renew(create=False, children=False, recurse=False)
            stem.leaf.update()
            for item in stem.leaf.childItems():
                if isinstance(item, TaskBox):
                    item.refreshTip()
                item.update()
            inline.updateHint()
        elif geometry_changed:
            stem.renew()
        else:
            # Status-only cycling must retain the cheap checkbox-click path:
            # no subtree rebuilding, content parsing, or position changes.
            stem.node.renew()
            for item in stem.leaf.childItems():
                if isinstance(item, TaskBox):
                    item.refreshTip()
                item.update()
        self.scene.mapModified.emit()
        return True

    def cycleCurrent(self):
        if not self.available() or self.view.inline.preedit:
            return False
        from .graphics import StemItem
        inline = self.view.inline
        selected = self.scene.selectedItems()
        stem = inline.item.stem if inline.item is not None else (
            selected[0] if len(selected) == 1 and isinstance(selected[0], StemItem) else None)
        if stem is None:
            self.scene.statusMessage.emit('Select one node to cycle its task state')
            return False
        current = None if not is_task(stem.node) else state(stem.node)
        target = TODO if current is None else (
            None if current == DONE else next_state(current))
        if not self.convertSelected(stem, target):
            return False
        self.scene.statusMessage.emit(f'Node: {target.title() if target else "Note"} · Todo creation mode unchanged')
        return True

    def setMode(self, enabled):
        inline = self.view.inline
        if not self.available() or inline.preedit:
            self.modeChanged.emit(self.enabled)
            return False
        if enabled and not inline.textMode:
            inline.setMode(True)
            if inline.item is not None:
                self.modeChanged.emit(self.enabled)
                return False
        self.enabled = bool(enabled)
        self.modeChanged.emit(self.enabled)
        inline.updateHint()
        self.scene.statusMessage.emit('Todo mode ON — Enter adds a task; Tab adds a child task' if self.enabled else
                                      'Todo mode OFF — new nodes are regular notes; existing tasks stay tasks')
        return True

    def setDone(self, uid, checked):
        return self.setState(uid, DONE if checked else TODO)

    def setDoingEnabled(self, enabled):
        QtCore.QSettings('Ectropy', 'Nexus').setValue('todoDoingEnabled', bool(enabled))
        for stem in self.scene.visibleStemsById().values():
            box = getattr(stem.leaf, 'taskbox', None)
            if box is not None:
                box.refreshTip()
        self.scene.statusMessage.emit('Doing state enabled: Todo → Doing → Done' if enabled else
                                      'Doing state disabled: Todo → Done; existing progress is kept')

    def cycle(self, uid):
        node = self.scene.graph.getuid(uid)
        return self.setState(uid, next_state(state(node))) if node is not None and is_task(node) else False

    def setState(self, uid, current):
        if current not in (TODO, DOING, DONE):
            raise ValueError('Unknown task state')
        if not self.available() or self.view.inline.preedit:
            return False
        inline = self.view.inline
        if inline.item is not None:
            if inline.item.stem.node['uid'] == uid and not inline.item.toPlainText().strip():
                self.scene.statusMessage.emit('Type a task before checking it.')
                return False
            inline.finish(select=False)
            if inline.item is not None:
                return False
        node = self.scene.graph.getuid(uid)
        if node is None or not is_task(node):
            return False
        if state(node) == current:
            return True
        try:
            with self.scene.graph.connection:
                node['todo_done'], node['todo_state'] = current == DONE, current
                node.save(batch=graphydb.generateUUID(), setchange=True)
        except Exception as error:
            logging.exception('Could not save task completion')
            self.scene.statusMessage.emit(f'Task status could not be saved: {error}. Retry.')
            return False
        stem = self.scene.visibleStemsById().get(uid)
        if stem is not None:
            stem.node['todo_done'], stem.node['todo_state'] = current == DONE, current
            stem.node.setChanged(False)
            stem.leaf.update()  # No subtree refresh or font/HTML mutation.
            for item in stem.leaf.childItems():
                if isinstance(item, TaskBox):
                    item.refreshTip()
                item.update()
        self.scene.mapModified.emit()
        self.scene.statusMessage.emit(f'Task: {current.title()} · Cmd+Z / Ctrl+Z to undo')
        return True

    def hit(self, point):
        """At least a 24px screen hit target, even for shrunken branches."""
        if not self.available():
            return None
        if isinstance(self.view.itemAt(point), QtWidgets.QGraphicsTextItem):
            return None
        candidates = []
        for uid, stem in self.scene.visibleStemsById().items():
            box = getattr(stem.leaf, 'taskbox', None)
            if box is None or not box.isVisible() or box.effectiveOpacity() <= 0:
                continue
            rect = self.view.viewportTransform().mapRect(box.sceneBoundingRect())
            rect = rect.united(QtCore.QRectF(rect.center().x() - 12, rect.center().y() - 12, 24, 24))
            if rect.contains(QtCore.QPointF(point)):
                # Expanded targets must not steal clicks intended for text.
                if any(isinstance(item, QtWidgets.QGraphicsTextItem) and
                       self.view.viewportTransform().mapRect(item.sceneBoundingRect()).contains(QtCore.QPointF(point))
                       for item in stem.leaf.childItems()):
                    continue
                delta = rect.center() - QtCore.QPointF(point)
                candidates.append((delta.x() ** 2 + delta.y() ** 2, uid))
        return min(candidates)[1] if candidates else None
