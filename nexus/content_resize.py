"""Map-only content resize handles; helpers never enter scene selection/data."""
import copy
import logging
from PyQt6 import QtCore, QtGui, QtWidgets, sip
from . import graphydb


class ContentResizeController(QtCore.QObject):
    HANDLE = 8
    HOVER_RADIUS = 14

    def __init__(self, view):
        super().__init__(view)
        self.view = view
        self.state = None
        self.ignoreRelease = False
        self.hoverPoint = None
        view.setMouseTracking(True)
        view.viewport().setMouseTracking(True)
        view.viewport().installEventFilter(self)
        view.scene().selectionChanged.connect(self.selectionChanged)

    def clearHover(self):
        if self.hoverPoint is not None:
            self.hoverPoint = None
            if self.state is None:
                self.view.viewport().setCursor(QtCore.Qt.CursorShape.OpenHandCursor)
            self.view.viewport().update()

    def eventFilter(self, watched, event):
        if event.type() in (QtCore.QEvent.Type.Leave, QtCore.QEvent.Type.Hide):
            self.clearHover()
        return False

    def visibleCorner(self):
        stem = self.target()
        if stem is None:
            return None
        if self.state is not None:
            return self.state['index']
        if self.hoverPoint is not None:
            distances = [(QtCore.QPointF(p-self.hoverPoint).manhattanLength(), i)
                         for i, p in enumerate(self.points(stem))]
            distance, index = min(distances)
            if distance <= self.HOVER_RADIUS:
                return index
        return None

    def target(self):
        from .graphics import StemItem
        scene = self.view.scene()
        if scene.mode != 'edit' or self.view.inline.item is not None:
            return None
        selected = scene.selectedItems()
        if len(selected) != 1 or not isinstance(selected[0], StemItem):
            return None
        stem = selected[0]
        if stem.node.get('iconified') or not stem.node.get('content'):
            return None
        # A popup editing the same content must retain exclusive ownership.
        owner = self.view.window()
        dialog = getattr(owner, 'editDialog', None)
        if dialog is not None and dialog.isVisible():
            return None
        return stem

    def corners(self, stem):
        rect = stem.leaf.boundingRect()
        if stem.depth == 0:
            rect = rect.adjusted(-5, -5, 5, 5)
        return [rect.topLeft(), rect.topRight(), rect.bottomRight(), rect.bottomLeft()]

    def points(self, stem):
        return [self.view.mapFromScene(stem.leaf.mapToScene(p)) for p in self.corners(stem)]

    def hit(self, point):
        stem = self.target()
        if stem is not None:
            for index, p in enumerate(self.points(stem)):
                if QtCore.QRectF(p.x()-7, p.y()-7, 14, 14).contains(QtCore.QPointF(point)):
                    return stem, index
        return None

    def paint(self, painter):
        stem = self.target()
        index = self.visibleCorner()
        if stem is None or index is None:
            return
        p = self.points(stem)[index]
        painter.save()
        painter.setWorldTransform(QtGui.QTransform())
        painter.setPen(QtGui.QPen(QtGui.QColor('#1677ee'), 1))
        painter.setBrush(QtGui.QColor('white'))
        painter.drawRect(QtCore.QRectF(p.x()-4, p.y()-4, self.HANDLE, self.HANDLE))
        painter.restore()

    def press(self, event):
        if event.button() != QtCore.Qt.MouseButton.LeftButton or event.modifiers():
            return False
        hit = self.hit(event.pos())
        if hit is None:
            return False
        stem, index = hit
        rect = stem.leaf.boundingRect()
        if rect.width() < 1 or rect.height() < 1:
            return False
        corners = self.corners(stem)
        anchor = corners[(index+2) % 4]
        direction = corners[index] - anchor
        children = []
        # Include collapsed/hidden children, not just their current graphics.
        for node in stem.node.outN('e.kind="Child"'):
            pos = node['pos']
            base = stem.tip() + QtCore.QPointF(stem.direction()*node.get('flip', 1)*pos[0], pos[1])
            children.append((node['uid'], stem.mapToScene(base)))
        self.state = dict(stem=stem, index=index, anchor=anchor,
            anchorScene=stem.leaf.mapToScene(anchor), direction=direction,
            pressPoint=QtCore.QPoint(event.pos()),
            leafScene=QtGui.QTransform(stem.leaf.sceneTransform()),
            data=copy.deepcopy(stem.node.data), children=children, factor=1.0)
        self.view.setFocus()
        self.ignoreRelease = False
        event.accept()
        return True

    def move(self, event):
        if self.state is None:
            before = self.visibleCorner()
            self.hoverPoint = QtCore.QPoint(event.pos()) if not event.buttons() else None
            if self.visibleCorner() != before:
                self.view.viewport().update()
            hit = self.hit(event.pos())
            if hit is not None and not event.buttons():
                cursor = (QtCore.Qt.CursorShape.SizeFDiagCursor if hit[1] % 2 == 0
                          else QtCore.Qt.CursorShape.SizeBDiagCursor)
                self.view.viewport().setCursor(cursor)
                return True
            return False
        if self.target() is not self.state['stem']:
            self.cancel()
            event.accept()
            return True
        state = self.state
        inverse, ok = state['leafScene'].inverted()
        if not ok:
            self.cancel()
            return True
        # Work from the actual press position, not the rounded display corner.
        # Otherwise even a click can change the scale by a fraction of a pixel.
        delta = (state['direction'] + inverse.map(self.view.mapToScene(event.pos()))
                 - inverse.map(self.view.mapToScene(state['pressPoint'])))
        vector = state['direction']
        factor = QtCore.QPointF.dotProduct(delta, vector) / QtCore.QPointF.dotProduct(vector, vector)
        # No flips, collapsed-to-zero nodes, or runaway accidental scaling.
        factor = max(0.05, min(20.0, factor))
        self.preview(factor)
        event.accept()
        return True

    def preview(self, factor):
        from .graphics import Transform, scaleRotateMove
        state = self.state
        stem = state['stem']
        scale = QtGui.QTransform.fromScale(factor, factor)
        frames = state['data']['content']
        for item in stem.leaf.childItems():
            uid = getattr(item, 'uid', None)
            if uid in frames:
                item.setTransform(Transform(*frames[uid]['frame']) * scale)
        if hasattr(stem.leaf, 'updateTaskBox'):
            stem.leaf.updateTaskBox()
        stem.leaf.titlerect = stem.leaf.childrenBoundingRect().adjusted(-3, -3, 3, 3)
        stem.leaf.setBoundingRect()
        stem.positionLeaf()
        # Keep the opposite corner fixed in scene space, including rotated maps.
        anchor = self.corners(stem)[(state['index']+2) % 4]
        displacement = state['anchorScene'] - stem.leaf.mapToScene(anchor)
        parent = stem.parentStem()
        origin = stem.mapToScene(QtCore.QPointF())
        if parent is not None:
            base = parent.mapFromScene(origin + displacement)
            offset = base - parent.tip()
            stem.node['pos'] = [stem.direction()*offset.x(), offset.y()]
        else:
            base = origin + displacement
            stem.node['pos'] = [base.x(), base.y()]
        stem.setTransform(scaleRotateMove(float(stem.node.get('scale', 1.0)),
            stem.node.get('angle', 0.0), base.x(), base.y()))
        stem.redrawTail()
        child_points = dict(state['children'])
        for child in stem.childStems2:
            point = child_points.get(child.node['uid'])
            if point is not None:
                base = stem.mapFromScene(point)
                child.setTransform(scaleRotateMove(float(child.node.get('scale', 1.0)),
                    child.node.get('angle', 0.0), base.x(), base.y()))
                child.redrawTail()
        state['factor'] = factor
        self.view.scene().update()

    def release(self, event):
        if self.state is None:
            if self.ignoreRelease:
                self.ignoreRelease = False
                event.accept()
                return True
            return False
        if event.button() != QtCore.Qt.MouseButton.LeftButton:
            event.accept()
            return True
        # Some systems coalesce the final move into mouse release.
        self.move(event)
        if self.state is None:
            self.ignoreRelease = False
            event.accept()
            return True
        state = self.state
        stem = state['stem']
        if abs(state['factor']-1.0) < 1e-6:
            self.cancel()
        else:
            graph = self.view.scene().graph
            batch = graphydb.generateUUID()
            try:
                with graph.connection:
                    node = graph.getuid(stem.node['uid'])
                    content = copy.deepcopy(state['data']['content'])
                    from .graphics import Transform
                    for item in stem.leaf.childItems():
                        uid = getattr(item, 'uid', None)
                        if uid in content:
                            content[uid]['frame'] = Transform(item.transform()).tolist()
                    node['content'] = content
                    node['pos'] = list(stem.node['pos'])
                    node.save(batch=batch)
                    for uid, point in state['children']:
                        child = graph.getuid(uid)
                        base = stem.mapFromScene(point) - stem.tip()
                        child['pos'] = [stem.direction()*child.get('flip', 1)*base.x(), base.y()]
                        child.save(batch=batch)
            except Exception:
                logging.exception('Could not save node content resize')
                self.cancel()
                QtWidgets.QMessageBox.warning(self.view, 'Resize not saved',
                    'The resize could not be saved. The original size has been restored.')
            else:
                self.state = None
                stem.renew()
                self.view.scene().mapModified.emit()
        self.view.viewport().setCursor(QtCore.Qt.CursorShape.OpenHandCursor)
        self.hoverPoint = QtCore.QPoint(event.pos())
        self.ignoreRelease = False
        self.view.viewport().update()
        event.accept()
        return True

    def cancel(self):
        if self.state is None:
            return
        stem = self.state['stem']
        self.state = None
        self.ignoreRelease = True
        self.hoverPoint = None
        if not sip.isdeleted(stem) and stem.scene() is not None:
            stem.renew()
        self.view.viewport().update()

    def selectionChanged(self):
        # A scene can outlive its views during window teardown.
        if sip.isdeleted(self.view):
            self.state = None
            return
        if self.state is not None and self.target() is not self.state['stem']:
            self.cancel()
        self.hoverPoint = None
        self.view.viewport().update()
