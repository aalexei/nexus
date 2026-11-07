"""Paste clipboard images into one map node, without opening the full editor."""
import copy
import logging

from PyQt6 import QtCore, QtGui, sip
from . import graphydb


def is_external_image(mime):
    # Internal copies include a raster fallback too. They must remain branch
    # copies, not become screenshots pasted into the selected node.
    return (mime is not None and mime.hasImage()
            and not mime.hasFormat('application/x-nexus')
            and not mime.hasFormat('application/json'))


def paste_image(scene, mime, view=None, stem=None):
    from .graphics import StemItem, PixmapItem, TextItem, Transform, scaleRotateMove
    view = view or next((v for v in scene.views() if hasattr(v, 'inline')), None)
    if view is None:
        return False
    inline = view.inline
    if not view.tasks.available() or inline.preedit:
        scene.statusMessage.emit('Finish the current operation before pasting an image')
        return False
    if inline.item is not None:
        stem = inline.item.stem
    elif stem is None:
        selected = scene.selectedItems()
        stem = selected[0] if len(selected) == 1 and isinstance(selected[0], StemItem) else None
    if stem is None:
        scene.statusMessage.emit('Select one node to paste an image into it')
        return False
    if stem.node.get('iconified', False):
        scene.statusMessage.emit('Show this node\'s contents first (I), then paste the image')
        return False
    source = mime.imageData()
    if isinstance(source, QtGui.QPixmap):
        source = source.toImage()
    if not isinstance(source, QtGui.QImage) or source.isNull():
        scene.statusMessage.emit('The clipboard does not contain a usable image')
        return False
    # No scene/data mutation before text has been saved successfully. Keep the
    # live editor open until image commit, so a failed image save loses no draft.
    editing = inline.item is not None
    if editing and not inline.checkpoint():
        return False
    graph = scene.graph
    original = copy.deepcopy(stem.node.data)
    old_transform = QtGui.QTransform(stem.transform())
    old_leaf_transform = QtGui.QTransform(stem.leaf.transform())
    old_title = QtCore.QRectF(stem.leaf.titlerect)
    origin = stem.leaf.mapToScene(QtCore.QPointF())
    children = []
    for child in stem.node.outN('e.kind="Child"'):
        pos = child['pos']
        base = stem.tip() + QtCore.QPointF(stem.direction()*child.get('flip', 1)*pos[0], pos[1])
        children.append((child['uid'], stem.mapToScene(base)))
    existing = QtCore.QRectF()
    for item in stem.leaf.childItems():
        if getattr(item, 'uid', None) not in stem.node.get('content', {}):
            continue
        if isinstance(item, TextItem) and not item.toPlainText().strip():
            continue  # Don't place images below an empty text placeholder.
        existing = existing.united(stem.leaf.mapRectFromItem(item, item.boundingRect()))
    batch = inline.batch if editing and getattr(stem, '_inline_new', False) else graphydb.generateUUID()
    pasted = None
    try:
        copied, _ = graph.itemFromImage(source)
        content = copy.deepcopy(copied.nodes[0]['content'][0])
        sha = content['sha1']
        uid = graphydb.generateUUID()
        ratio = max(1.0, float(source.devicePixelRatio()))
        scale = min(1.0/ratio, 380.0/source.width(), 280.0/source.height())
        target = QtCore.QPointF(existing.left(), existing.bottom()+24) if not existing.isEmpty() else QtCore.QPointF()
        # Leave room before nearby labels where possible. A 380-unit image
        # could otherwise cover the unchanged children of a short text node.
        # Only shrink the new image; never rearrange existing map content.
        for other in scene.visibleStemsById().values():
            if other is stem:
                continue
            obstacle = stem.leaf.mapRectFromItem(other.leaf, other.leaf.boundingRect())
            bounds = existing.united(QtCore.QRectF(target,
                QtCore.QSizeF(source.width()*scale, source.height()*scale)))
            if (obstacle.left() <= existing.right()+12 or
                    obstacle.bottom() < bounds.top()-12 or obstacle.top() > bounds.bottom()+12):
                continue
            candidate = min(scale, (obstacle.left()-target.x()-24)/source.width())
            # Don't make the image unusably tiny to fit an already cramped map.
            if max(source.width(), source.height())*candidate >= min(96, max(source.width(), source.height())*scale):
                scale = candidate
        frame = QtGui.QTransform().translate(target.x(), target.y()).scale(scale, scale)
        content['frame'] = Transform(frame).tolist()
        content['z'] = max((value.get('z', 0) for value in stem.node.get('content', {}).values()), default=0) + 1
        with graph.connection:
            data = graph.findImageData(sha)
            if data is None:
                data = graph.Node('ImageData')
                data.update(copied.images[sha])
                data.save(batch=batch)
            if not any(edge.end['uid'] == data['uid'] for edge in stem.node.outE('e.kind="With"')):
                graph.Edge(stem.node, 'With', data).save(batch=batch)
            stem.node.setdefault('content', {})[uid] = content
            stem.node.keyChanged('content')
            pasted = PixmapItem(uid, stem, parent=stem.leaf)
            # Compensate node and child attachment offsets for the larger leaf.
            # Existing text/drawings keep their scene positions and transforms.
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
                stem.node['pos'] = [stem.direction()*offset.x(), offset.y()]
            else:
                stem.node['pos'] = [base.x(), base.y()]
            stem.setTransform(scaleRotateMove(float(stem.node.get('scale', 1.0)),
                stem.node.get('angle', 0.0), base.x(), base.y()))
            stem.redrawTail()
            stem.node.save(batch=batch)
            for child_uid, point in children:
                child = graph.getuid(child_uid)
                base = stem.mapFromScene(point) - stem.tip()
                child['pos'] = [stem.direction()*child.get('flip', 1)*base.x(), base.y()]
                child.save(batch=batch)
    except Exception as error:
        logging.exception('Could not paste image into node')
        if pasted is not None:
            scene.removeItem(pasted)
            sip.delete(pasted)
        stem.node.data = original
        stem.node.setChanged(False)
        stem.setTransform(old_transform)
        stem.leaf.setTransform(old_leaf_transform)
        stem.leaf.updateTaskBox()
        stem.leaf.titlerect = old_title
        stem.leaf.setBoundingRect()
        stem.positionLeaf()
        scene.update()
        scene.statusMessage.emit(f'Image could not be pasted: {error}. Your node and text are unchanged.')
        return False
    # Finish inline editing only after a successful image transaction. Mixed
    # nodes use the normal selection/full-editor flow after this point.
    stem._keyboard_autoplace = False
    if editing:
        inline.finish(select=False, keep_blank=True)
    else:
        for child in list(stem.childStems2):
            child.renew(create=False, children=False, recurse=False)
    stem._inline_new = False
    scene.selectNodes([stem.node['uid']])
    scene.mapModified.emit()
    scene.update()
    scene.statusMessage.emit('Image pasted into node · Cmd+Z / Ctrl+Z to undo')
    return True
