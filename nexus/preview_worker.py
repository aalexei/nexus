"""Isolated preview CLI. Never open the original with Nexus's writable loader."""
import argparse
import json
import logging
import os
import sys
from pathlib import Path

from . import preview_cache


def reduce_images(connection):
    """Reduce only the private snapshot's bitmaps, retaining map geometry."""
    import base64
    from PyQt6 import QtCore, QtGui
    from . import graphics, nexusgraph

    dimensions = {}
    total_pixels = 0
    # Process one payload at a time: fetching all image JSON duplicates the
    # entire image database in Python memory before decoding even starts.
    for uid, raw in connection.execute("SELECT uid,data FROM nodes WHERE kind='ImageData'"):
        data = json.loads(raw)
        encoded = base64.b64decode(data['data'], validate=True)
        buffer = QtCore.QBuffer()
        buffer.setData(encoded)
        buffer.open(QtCore.QIODevice.OpenModeFlag.ReadOnly)
        reader = QtGui.QImageReader(buffer)
        size = reader.size()
        pixels = size.width() * size.height()
        total_pixels += pixels
        if not size.isValid() or pixels > 32_000_000 or total_pixels > 192_000_000:
            raise ValueError('Images exceed scoped preview pixel limit')
        reduced = size.scaled(1024, 1024, QtCore.Qt.AspectRatioMode.KeepAspectRatio)
        if size.width() <= 1024 and size.height() <= 1024:
            reduced = size
        reader.setScaledSize(reduced)
        image = reader.read()
        if image.isNull():
            raise ValueError('Image unavailable within scoped preview limits')
        # Some decoders ignore scaledSize. Still retain only a bounded bitmap.
        if image.size() != reduced:
            image = image.scaled(reduced, QtCore.Qt.AspectRatioMode.IgnoreAspectRatio,
                                 QtCore.Qt.TransformationMode.SmoothTransformation)
        dimensions[data['sha1']] = (size.width() / image.width(), size.height() / image.height())
        data['data'] = nexusgraph.ImageToData(image)
        connection.execute('UPDATE nodes SET data=? WHERE uid=?', (json.dumps(data), uid))
    for uid, raw in connection.execute("SELECT uid,data FROM nodes WHERE kind='Stem'"):
        data = json.loads(raw)
        changed = False
        for content in data.get('content', {}).values():
            if content.get('kind') == 'Image' and content.get('sha1') in dimensions:
                sx, sy = dimensions[content['sha1']]
                original = QtGui.QTransform(*content['frame'])
                compensation = QtGui.QTransform().scale(sx, sy)
                content['frame'] = graphics.Transform(compensation * original).tolist()
                changed = True
        if changed:
            connection.execute('UPDATE nodes SET data=? WHERE uid=?', (json.dumps(data), uid))


def render(filename, cache_directory, work_directory, large_images=False):
    before = preview_cache.signature(filename)
    cache_stamp = dict(before, profile='large-images-v1') if large_images else before
    target = preview_cache.image_path(cache_directory, cache_stamp)
    if preview_cache.valid_png(target):
        target.touch()
        preview_cache.prune(cache_directory)
        return str(target)
    size_limit = (128 if large_images else 64) * 1024 * 1024
    if sum(stamp[2] for stamp in before['stamps'] if stamp) > size_limit:
        raise ValueError('Map exceeds preview size limit')
    source = Path(before['path'])
    copied = Path(work_directory) / 'snapshot.nex'
    budget = size_limit
    for suffix, stamp in zip(('', '-wal', '-journal'), before['stamps']):
        if stamp is not None:
            with open(str(source) + suffix, 'rb') as original, open(str(copied) + suffix, 'xb') as snapshot:
                while True:
                    data = original.read(min(1024 * 1024, budget + 1))
                    if not data:
                        break
                    budget -= len(data)
                    if budget < 0:
                        raise ValueError('Map grew beyond preview size limit')
                    snapshot.write(data)
    if preview_cache.signature(filename) != before:
        raise ValueError('Map changed during snapshot')

    import apsw
    from PyQt6 import QtCore, QtGui, QtWidgets
    from . import graphics, nexusgraph, resources
    # Rendering runs with isolated preferences, never the user's QSettings.
    QtCore.QSettings.setDefaultFormat(QtCore.QSettings.Format.IniFormat)
    QtCore.QSettings.setPath(QtCore.QSettings.Format.IniFormat,
                            QtCore.QSettings.Scope.UserScope, str(Path(work_directory) / 'preferences'))
    original_settings = QtCore.QSettings

    class PreviewSettings(original_settings):
        def __init__(self, *args, **kwargs):
            # Named organization/application constructors otherwise always
            # use NativeFormat, even after setDefaultFormat(IniFormat).
            if len(args) >= 2 and isinstance(args[0], str) and isinstance(args[1], str):
                super().__init__(original_settings.Format.IniFormat,
                                 original_settings.Scope.UserScope, *args, **kwargs)
            else:
                super().__init__(*args, **kwargs)
            self.setFallbacksEnabled(False)

    QtCore.QSettings = PreviewSettings
    app = QtWidgets.QApplication([])
    app.setProperty('nexusTestMode', True)
    QtGui.QImageReader.setAllocationLimit(128 if large_images else 16)
    for name in ('et-book-roman-line-figures.ttf', 'et-book-bold-line-figures.ttf',
                 'et-book-display-italic-old-style-figures.ttf',
                 'et-book-semi-bold-old-style-figures.ttf', 'et-book-roman-old-style.ttf'):
        QtGui.QFontDatabase.addApplicationFont(':/images/' + name)
    readonly = apsw.Connection(str(copied), flags=apsw.SQLITE_OPEN_READONLY)
    readonly.setbusytimeout(200)
    graph = nexusgraph.NexusGraph(':memory:')
    try:
        # Validate schema/version before rendering. Old maps are not converted.
        version = json.loads(readonly.execute("SELECT value FROM settings WHERE key='version'").fetchone()[0])
        if not isinstance(version, (float, int)) or version < .9:
            raise ValueError('Legacy map requires opening in Nexus first')
        stems = readonly.execute("SELECT uid FROM nodes WHERE kind='Stem'").fetchall()
        if len(stems) > 2000:
            raise ValueError('Map exceeds preview node limit')
        edges = readonly.execute("SELECT startuid,enduid FROM edges WHERE kind='Child'").fetchall()
        children = {}
        for parent, child in edges:
            children.setdefault(parent, []).append(child)
        # Guard cyclic/multi-parent and very deep trees before Qt recursion.
        roots = [row[0] for row in readonly.execute("SELECT uid FROM nodes WHERE kind='Root'")]
        seen, stack = set(), [(root, 0) for root in roots]
        while stack:
            uid, depth = stack.pop()
            if uid in seen or depth > 100:
                raise ValueError('Invalid or excessively deep preview tree')
            seen.add(uid)
            stack.extend((child, depth + 1) for child in children.get(uid, []))
        disconnected = [uid for (uid,) in stems if uid not in seen]
        linked = {uid for edge in edges for uid in edge}
        # Some saved maps retain a detached leaf after removal. In the opt-in
        # profile only, ignore isolated records that the normal map loader also
        # never displays. Disconnected chains/cycles still fail validation.
        if not roots or (disconnected and
                         (not large_images or any(uid in linked for uid in disconnected))):
            raise ValueError('Map has disconnected preview nodes')
        if readonly.execute("SELECT count(*) FROM nodes WHERE kind='ImageData'").fetchone()[0] > 32:
            raise ValueError('Map exceeds preview image limit')
        # QTextDocument can resolve HTML image resources from local paths.
        # Preview only embedded ImageData; never load external HTML resources.
        import re
        for (raw,) in readonly.execute("SELECT data FROM nodes WHERE kind='Stem'"):
            data = json.loads(raw)
            for content in data.get('content', {}).values():
                if content.get('kind') == 'Text' and re.search(r'<\s*(img|object|embed)\b', content.get('source', ''), re.I):
                    raise ValueError('External HTML resources are not previewed')
        with graph.connection.backup('main', readonly, 'main') as backup:
            while not backup.done:
                backup.step(100)
        if large_images:
            reduce_images(graph.connection)
        scene = graphics.NexusScene()
        scene.graph = graph
        for node in graph.fetch('(r:Root) -(e:Child)> [n:Stem]'):
            item = graphics.StemItem(node=node, scene=scene)
            item.renew(reload=False)
        bounds = QtCore.QRectF()
        for item in scene.allChildStems():
            if item.isVisible():
                bounds = bounds.united(item.sceneBoundingRect())
            for name in ('indexText', 'openclose', 'actionWidget', 'childWidget',
                         'selectpath', 'editedpath'):
                control = getattr(item, name, None)
                if control is not None:
                    if name == 'indexText':
                        control.parentItem().hide()
                    control.hide()
        for item in scene.items():
            if isinstance(item, graphics.PixmapItem) and item.pixmap().isNull():
                raise ValueError('Image unavailable within preview limits')
        if bounds.isEmpty():
            raise ValueError('Empty map preview')
        image = QtGui.QImage(preview_cache.WIDTH, preview_cache.HEIGHT,
                             QtGui.QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(QtGui.QColor('white'))
        painter = QtGui.QPainter(image)
        try:
            painter.setRenderHints(QtGui.QPainter.RenderHint.Antialiasing |
                                   QtGui.QPainter.RenderHint.TextAntialiasing |
                                   QtGui.QPainter.RenderHint.SmoothPixmapTransform)
            bounds = bounds.adjusted(-12, -12, 12, 12)
            area = QtCore.QRectF(12, 12, preview_cache.WIDTH - 24, preview_cache.HEIGHT - 24)
            scale = min(area.width() / bounds.width(), area.height() / bounds.height())
            target_rect = QtCore.QRectF(0, 0, bounds.width() * scale, bounds.height() * scale)
            target_rect.moveCenter(area.center())
            scene.render(painter, target_rect, bounds)
        finally:
            painter.end()
        temporary = Path(work_directory) / 'thumbnail.png'
        if not image.save(str(temporary), 'PNG'):
            raise OSError('Could not write preview')
        if preview_cache.signature(filename) != before:
            raise ValueError('Map changed during rendering')
        temporary.chmod(0o600)
        temporary.replace(target)
        preview_cache.prune(cache_directory)
        scene.clear()
        return str(target)
    finally:
        readonly.close()
        graph.connection.close()
        QtCore.QSettings = original_settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('filename')
    parser.add_argument('cache_directory')
    parser.add_argument('work_directory')
    parser.add_argument('--large-images', action='store_true')
    args = parser.parse_args()
    try:
        try:
            import resource
            resource.setrlimit(resource.RLIMIT_CPU, (16, 18) if args.large_images else (8, 10))
        except (ImportError, OSError, ValueError):
            pass
        image = render(args.filename, args.cache_directory, args.work_directory, args.large_images)
        print(json.dumps({'image': image}))
        return 0
    except Exception:
        logging.exception('Map preview unavailable')
        print(json.dumps({'error': 'Preview unavailable — open the map to inspect it.'}))
        return 1


if __name__ == '__main__':
    sys.exit(main())
