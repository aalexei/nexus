"""Isolated, bounded SQLite recovery snapshots."""
from datetime import datetime, timezone
import hashlib
import logging
from pathlib import Path
import shutil
import uuid

import apsw
from bs4 import BeautifulSoup
from PyQt6 import QtCore, QtGui, QtWidgets


class SnapshotStore:
    """SQLite backups are independent databases; never copy a live DB file."""
    def __init__(self, graph, base_path=None, keep=10):
        self.graph = graph
        if base_path is None:
            base_path = Path(QtCore.QStandardPaths.writableLocation(
                QtCore.QStandardPaths.StandardLocation.GenericDataLocation)) / 'Ectropy' / 'Nexus' / 'recovery'
        identity = hashlib.sha256(str(Path(graph.path).resolve()).encode()).hexdigest()[:24]
        self.directory = Path(base_path) / identity
        self.keep = max(1, keep)
        self.last_changes = None

    def snapshots(self):
        return sorted(self.directory.glob('snapshot-*.nex'), reverse=True)

    def capture(self, force=False):
        if self.graph.path == ':memory:':
            return None
        changes = self.graph.connection.total_changes()
        if not force and changes == self.last_changes:
            return None
        self.directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
        target = self.directory / f'snapshot-{stamp}-{uuid.uuid4().hex[:8]}.nex'
        temporary = target.with_suffix('.partial')
        connection = None
        try:
            connection = apsw.Connection(str(temporary))
            with connection.backup('main', self.graph.connection, 'main') as backup:
                while not backup.done:
                    backup.step(100)
            if connection.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise RuntimeError('Recovery snapshot failed its integrity check')
            connection.close()
            connection = None
            temporary.replace(target)
            self.last_changes = changes
            # Only our finalized snapshots in this map's isolated folder expire.
            for expired in self.snapshots()[self.keep:]:
                expired.unlink()
            return target
        finally:
            if connection is not None:
                connection.close()
            if temporary.exists():
                temporary.unlink()

    def recover_copy(self, snapshot, destination):
        snapshot, destination = Path(snapshot), Path(destination)
        if snapshot not in self.snapshots():
            raise ValueError('Choose a snapshot belonging to this map')
        # Exclusive creation protects the original, snapshots, and existing files.
        with destination.open('xb') as output:
            try:
                with snapshot.open('rb') as source:
                    shutil.copyfileobj(source, output)
            except Exception:
                output.close()
                destination.unlink()
                raise
        return destination


class RecoveryManager(QtCore.QObject):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.store = SnapshotStore(owner.scene.graph)
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(5 * 60 * 1000)
        self.timer.timeout.connect(self.capture)
        self.capture()
        self.timer.start()

    def capture(self, force=False):
        try:
            return self.store.capture(force=force)
        except Exception as error:
            logging.exception('Could not create a recovery snapshot')
            self.owner.showMessage(f'Recovery snapshot failed: {error}', 10000)
            return None

    def showSnapshots(self):
        self.capture()
        dialog = QtWidgets.QDialog(self.owner)
        dialog.setWindowTitle('Recovery Snapshots — ' + Path(self.store.graph.path).name)
        dialog.resize(600, 360)
        layout = QtWidgets.QVBoxLayout(dialog)
        layout.addWidget(QtWidgets.QLabel('Up to 10 snapshots are kept for this map.\nRecover opens a new copy; your original map stays untouched.'))
        listing = QtWidgets.QListWidget()
        for path in self.store.snapshots():
            stamp = path.name.split('snapshot-', 1)[1].rsplit('-', 1)[0]
            date = datetime.strptime(stamp, '%Y%m%dT%H%M%S.%fZ').replace(tzinfo=timezone.utc).astimezone()
            item = QtWidgets.QListWidgetItem(date.strftime('%d %b %Y, %H:%M:%S %Z'))
            item.setData(QtCore.Qt.ItemDataRole.UserRole, str(path))
            item.setToolTip(str(path))
            listing.addItem(item)
        layout.addWidget(listing)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Close)
        recover = buttons.addButton('Recover Copy…', QtWidgets.QDialogButtonBox.ButtonRole.ActionRole)
        folder = buttons.addButton('Open Snapshot Folder', QtWidgets.QDialogButtonBox.ButtonRole.ActionRole)
        folder.clicked.connect(lambda: QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(self.store.directory))))
        recover.setEnabled(listing.count() > 0)
        if listing.count():
            listing.setCurrentRow(0)

        def restore():
            current = listing.currentItem()
            if current is None:
                return
            suggested = str(Path(self.store.graph.path).with_name(Path(self.store.graph.path).stem + '-recovered.nex'))
            destination, _ = QtWidgets.QFileDialog.getSaveFileName(dialog, 'Recover to a NEW map file', suggested, 'Nexus (*.nex)')
            if not destination:
                return
            destination = Path(destination).with_suffix('.nex')
            try:
                self.store.recover_copy(current.data(QtCore.Qt.ItemDataRole.UserRole), destination)
            except Exception as error:
                QtWidgets.QMessageBox.warning(dialog, 'Recovery failed', str(error) + '\nChoose a new filename; existing files cannot be replaced.')
                return
            dialog.accept()
            QtWidgets.QApplication.instance().raiseOrOpen(str(destination))

        recover.clicked.connect(restore)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()
        self.owner.activateWindow()
        self.owner.view.setFocus()
