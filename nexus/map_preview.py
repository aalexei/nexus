"""Non-interactive hover thumbnails, isolated rendering and idle-save warming."""
import json
import re
import tempfile
import time
import uuid
from pathlib import Path

from PyQt6 import QtCore, QtGui, QtWidgets, sip
from . import preview_cache


class PreviewService(QtCore.QObject):
    ready = QtCore.pyqtSignal(object)

    def __init__(self, directory=None, parent=None):
        super().__init__(parent)
        if directory is None:
            directory = Path(QtCore.QStandardPaths.writableLocation(
                QtCore.QStandardPaths.StandardLocation.GenericCacheLocation)) / 'Ectropy' / 'Nexus' / 'map-previews-v1'
        self.directory = Path(directory)
        self.active = self.pending = None
        self.cooldown = {}
        self.stopping = False

    def largeImagesEnabled(self, path):
        # Exact local opt-ins only; neither a basename nor a whole folder grants
        # larger limits. Worker still validates paths and rejects symlinks.
        allowed = QtCore.QSettings('Ectropy', 'Nexus').value('previewLargeImageMaps', [])
        return isinstance(allowed, (list, tuple)) and str(Path(path).absolute()) in allowed

    def request(self, path, token):
        self.pending = (path, token)
        if self.active is not None:
            self.cancel(self.active['token'])
        else:
            self._startPending()

    def prefetch(self, path):
        if self.active is not None or self.pending is not None or self.stopping:
            return False
        self.request(path, 'warm-' + uuid.uuid4().hex)
        return True

    def _startPending(self):
        if self.pending is None or self.stopping:
            return
        path, token = self.pending
        self.pending = None
        if self.cooldown.get(path, 0) > time.monotonic():
            self.ready.emit({'path': path, 'token': token, 'image': '', 'error': 'Preview unavailable'})
            return
        temporary = None
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            self.directory.chmod(0o700)
            temporary = tempfile.TemporaryDirectory(prefix='.render-', dir=str(self.directory))
            process = QtCore.QProcess(self)
            process.setWorkingDirectory(str(Path(__file__).resolve().parent.parent))
            environment = QtCore.QProcessEnvironment.systemEnvironment()
            environment.insert('QT_QPA_PLATFORM', 'offscreen')
            process.setProcessEnvironment(environment)
            job = {'path': path, 'token': token, 'process': process, 'temporary': temporary,
                   'cancelled': False, 'done': False, 'stdout': bytearray(), 'error': ''}
            self.active = job
            process.readyReadStandardOutput.connect(lambda: self._readOutput(job))
            process.readyReadStandardError.connect(lambda: process.readAllStandardError())
            process.finished.connect(lambda code, status: self._finish(job, code))
            process.errorOccurred.connect(lambda error: self._processError(job, error))
            timer = QtCore.QTimer(process)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda: self._timeout(job))
            large_images = self.largeImagesEnabled(path)
            timer.start(20000 if large_images else 10000)
            import sys
            arguments = ['-m', 'nexus.preview_worker', path, str(self.directory), temporary.name]
            if large_images:
                arguments.append('--large-images')
            process.start(sys.executable, arguments)
        except (OSError, RuntimeError) as error:
            if temporary is not None:
                temporary.cleanup()
            self.active = None
            self.ready.emit({'path': path, 'token': token, 'image': '', 'error': 'Preview cache unavailable'})

    def _readOutput(self, job):
        job['stdout'].extend(bytes(job['process'].readAllStandardOutput()))
        if len(job['stdout']) > 8192:
            job['error'] = 'Preview unavailable'
            job['process'].kill()

    def _timeout(self, job):
        if not job['done']:
            job['error'] = 'Preview timed out'
            job['process'].kill()

    def _processError(self, job, error):
        if error == QtCore.QProcess.ProcessError.FailedToStart:
            self._finish(job, -1)

    def _finish(self, job, code):
        if job['done']:
            return
        job['done'] = True
        self._readOutput(job)
        result = {'path': job['path'], 'token': job['token'], 'image': '', 'error': 'Preview unavailable'}
        try:
            data = json.loads(job['stdout']) if code == 0 else {}
            if not isinstance(data, dict):
                raise ValueError('Invalid preview response')
            image = Path(data.get('image', ''))
            if (image.parent == self.directory and re.fullmatch(r'thumb-[0-9a-f]{64}\.png', image.name)
                    and preview_cache.valid_png(image)):
                result.update(image=str(image), error='')
        except (ValueError, OSError, TypeError):
            pass
        if job['error']:
            result['error'] = job['error']
        try:
            job['temporary'].cleanup()
        except OSError:
            # An inaccessible cache cleanup must not abort a Qt callback.
            import logging
            logging.warning('Could not clean temporary preview directory')
        job['process'].deleteLater()
        if self.active is job:
            self.active = None
        if not job['cancelled'] and not self.stopping:
            if result['error']:
                self.cooldown[job['path']] = time.monotonic() + 5
                if len(self.cooldown) > 128:
                    self.cooldown.pop(next(iter(self.cooldown)))
            self.ready.emit(result)
        self._startPending()

    def cancel(self, token):
        if self.pending is not None and self.pending[1] == token:
            self.pending = None
        job = self.active
        if job is not None and job['token'] == token:
            job['cancelled'] = True
            process = job['process']
            process.terminate()
            QtCore.QTimer.singleShot(200, lambda: process.kill()
                                    if not sip.isdeleted(process) and process.state() != QtCore.QProcess.ProcessState.NotRunning else None)

    def stop(self):
        self.stopping = True
        self.pending = None
        if self.active is not None:
            job = self.active
            job['cancelled'] = True
            job['process'].kill()
            job['process'].waitForFinished(500)
            self._finish(job, -1)


def service():
    app = QtWidgets.QApplication.instance()
    current = getattr(app, '_mapPreviewService', None)
    if current is None:
        current = PreviewService(parent=app)
        app._mapPreviewService = current
        app.aboutToQuit.connect(current.stop)
    return current


class HoverPreview(QtCore.QObject):
    def __init__(self, owner, renderer=None):
        super().__init__(owner)
        self.owner = owner
        self.renderer = renderer
        self.path = self.token = None
        self.timer = QtCore.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self.showPreview)
        self.watcher = QtCore.QFileSystemWatcher(self)
        self.watcher.fileChanged.connect(self.invalidate)
        self.watcher.directoryChanged.connect(self.directoryChanged)
        self.popup = QtWidgets.QFrame(owner, QtCore.Qt.WindowType.ToolTip |
                                      QtCore.Qt.WindowType.FramelessWindowHint |
                                      QtCore.Qt.WindowType.WindowDoesNotAcceptFocus)
        self.popup.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.popup.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating)
        layout = QtWidgets.QVBoxLayout(self.popup)
        layout.setContentsMargins(10, 10, 10, 8)
        self.title = QtWidgets.QLabel()
        self.title.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        self.image = QtWidgets.QLabel()
        self.image.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        self.image.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.image.setFixedSize(360, 210)
        self.caption = QtWidgets.QLabel('Last saved map')
        layout.addWidget(self.title)
        layout.addWidget(self.image)
        layout.addWidget(self.caption)
        self.popup.hide()
        owner.listWidget.viewport().installEventFilter(self)
        owner.listWidget.viewport().setMouseTracking(True)
        owner.installEventFilter(self)
        owner.listWidget.verticalScrollBar().valueChanged.connect(self.clear)
        owner.listWidget.model().modelReset.connect(self.clear)
        owner.listWidget.model().rowsRemoved.connect(self.clear)
        owner.tabs.currentChanged.connect(self.clear)
        owner.search.textChanged.connect(self.clear)

    def hover(self, path):
        if path == self.path:
            return
        self.clear()
        if path:
            self.path = path
            self.token = uuid.uuid4().hex
            self.timer.start()

    def clear(self, *unused):
        self.timer.stop()
        if self.renderer is not None and self.token is not None:
            self.renderer.cancel(self.token)
        self.path = self.token = None
        self.popup.hide()
        watched = self.watcher.files() + self.watcher.directories()
        if watched:
            self.watcher.removePaths(watched)

    def invalidate(self, *unused):
        if self.renderer is not None:
            self.renderer.cooldown.pop(self.path, None)
        self.clear()

    def directoryChanged(self, *unused):
        # The directory watcher exists for newly created WAL/journal files,
        # not for unrelated neighboring files or thumbnail-cache activity.
        if self.path:
            watched = set(self.watcher.files())
            for suffix in ('-wal', '-journal'):
                sidecar = self.path + suffix
                if sidecar not in watched and Path(sidecar).exists():
                    self.invalidate()
                    break

    def showPreview(self):
        if not self.path or not self.owner.isVisible():
            return
        if self.renderer is None:
            self.renderer = service()
        # Connect once, using a bound QObject slot so deletion disconnects it.
        if not getattr(self, '_connected', False):
            self.renderer.ready.connect(self.completed)
            self._connected = True
        self.watcher.addPaths([self.path, str(Path(self.path).parent)])
        for suffix in ('-wal', '-journal'):
            if Path(self.path + suffix).exists():
                self.watcher.addPath(self.path + suffix)
        self.title.setText(QtGui.QFontMetrics(self.title.font()).elidedText(
            Path(self.path).name, QtCore.Qt.TextElideMode.ElideMiddle, 360))
        self.image.clear()
        self.image.setText('Preparing preview…')
        self.caption.setText('Last saved map')
        self.positionPopup()
        self.popup.show()
        self.renderer.request(self.path, self.token)

    def positionPopup(self):
        self.popup.setStyleSheet('QFrame { background: #ffffff; color: #20232a; border: 1px solid #a7adb5; border-radius: 6px; } QLabel { border: none; background: transparent; }')
        self.popup.adjustSize()
        rect = self.owner.listWidget.visualItemRect(self.owner.listWidget.currentItem())
        for row in range(self.owner.listWidget.count()):
            item = self.owner.listWidget.item(row)
            if item.data(QtCore.Qt.ItemDataRole.UserRole) == self.path:
                rect = self.owner.listWidget.visualItemRect(item)
                break
        position = self.owner.listWidget.viewport().mapToGlobal(rect.topLeft())
        screen = QtGui.QGuiApplication.screenAt(position) or self.owner.screen()
        area = screen.availableGeometry().adjusted(8, 8, -8, -8)
        x = position.x() - self.popup.width() - 8
        if x < area.left():
            x = self.owner.listWidget.viewport().mapToGlobal(rect.topRight()).x() + 8
        self.popup.move(max(area.left(), min(x, area.right() - self.popup.width() + 1)),
                        max(area.top(), min(position.y(), area.bottom() - self.popup.height() + 1)))

    @QtCore.pyqtSlot(object)
    def completed(self, result):
        if result['token'] != self.token or result['path'] != self.path or not self.owner.isVisible():
            return
        pixmap = QtGui.QPixmap(result['image']) if result['image'] else QtGui.QPixmap()
        if not pixmap.isNull():
            pixmap.setDevicePixelRatio(2)
            self.image.setPixmap(pixmap)
        else:
            if result['image']:
                image = Path(result['image'])
                if image.parent == self.renderer.directory and re.fullmatch(r'thumb-[0-9a-f]{64}\.png', image.name):
                    try:
                        image.unlink()
                    except OSError:
                        pass
            self.image.setText('Preview unavailable\nOpen the map to inspect it.')

    def eventFilter(self, watched, event):
        types = QtCore.QEvent.Type
        if watched is self.owner:
            if event.type() in (types.Hide, types.Close, types.WindowDeactivate, types.Move, types.Resize):
                self.clear()
            return False
        if event.type() in (types.MouseMove, types.Enter, types.HoverMove) and hasattr(event, 'position'):
            item = self.owner.listWidget.itemAt(event.position().toPoint())
            path = None
            if item is not None:
                rect = self.owner.listWidget.visualItemRect(item)
                if self.owner.listWidget.itemDelegate().actionAt(rect, event.position().toPoint()) is None:
                    path = item.data(QtCore.Qt.ItemDataRole.UserRole)
            self.hover(path)
        elif event.type() in (types.Leave, types.MouseButtonPress, types.MouseButtonDblClick, types.Wheel):
            self.clear()
        return False


class IdlePreview(QtCore.QObject):
    """Warm once after a stable saved revision, never per character."""
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(2000)
        self.timer.timeout.connect(self.poll)
        self.last = self.sent = None
        self.changedAt = time.monotonic()
        if not QtWidgets.QApplication.instance().property('nexusTestMode'):
            self.timer.start()

    def poll(self):
        try:
            graph = self.owner.scene.graph
            changes = graph.connection.total_changes()
            if changes != self.last:
                self.last = changes
                self.changedAt = time.monotonic()
            elif changes != self.sent and time.monotonic() - self.changedAt >= 4:
                if service().prefetch(graph.path):
                    self.sent = changes
        except Exception:
            self.timer.stop()

    def stop(self):
        self.timer.stop()
