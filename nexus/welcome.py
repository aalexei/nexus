"""Welcome screen and shared, path-based recent-map history."""
import shutil
import sys
import tempfile
from pathlib import Path
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtSvgWidgets import QSvgWidget
from . import map_finder, map_preview


def settings():
    return QtCore.QSettings('Ectropy', 'Nexus')


def normalize(path):
    return str(Path(path).expanduser().resolve())


def paths(value):
    if isinstance(value, str):
        value = [value]
    return list(dict.fromkeys(normalize(p) for p in (value or []) if isinstance(p, str) and p))


def history():
    store = settings()
    recent = paths(store.value('recentFileList', []))
    pinned = paths(store.value('pinnedMaps', []))
    # Remove stale ephemeral history, not real maps or ordinary moved files.
    temporary_roots = (Path(tempfile.gettempdir()).resolve(), Path('/private/var/folders'), Path('/private/tmp'))
    def stale_temporary(p):
        path = Path(p)
        return not path.exists() and any(root == path or root in path.parents for root in temporary_roots)
    recent = [p for p in recent if not stale_temporary(p) or p in pinned]
    store.setValue('recentFileList', recent)
    store.setValue('pinnedMaps', pinned)
    return recent, pinned


def record_recent(path):
    recent, _ = history()
    app = QtWidgets.QApplication.instance()
    if app is not None and app.property('nexusTestMode'):
        return
    path = normalize(path)
    settings().setValue('recentFileList', [path] + [p for p in recent if p != path][:9])


class MapDelegate(QtWidgets.QStyledItemDelegate):
    pinRequested = QtCore.pyqtSignal(str)
    trashRequested = QtCore.pyqtSignal(str)

    def actionAt(self, rect, point):
        if QtCore.QRect(rect.right() - 31, rect.top(), 32, rect.height()).contains(point):
            return 'trash'
        if QtCore.QRect(rect.right() - 63, rect.top(), 32, rect.height()).contains(point):
            return 'pin'
        return None

    def editorEvent(self, event, model, option, index):
        types = QtCore.QEvent.Type
        if event.type() not in (types.MouseButtonPress, types.MouseButtonRelease, types.MouseButtonDblClick):
            return super().editorEvent(event, model, option, index)
        if event.button() != QtCore.Qt.MouseButton.LeftButton:
            return super().editorEvent(event, model, option, index)
        action = self.actionAt(option.rect, event.position().toPoint())
        path = index.data(QtCore.Qt.ItemDataRole.UserRole)
        if event.type() == types.MouseButtonPress:
            self._pressedAction = (path, action) if action else None
        elif event.type() == types.MouseButtonDblClick and action:
            # A second click on a control must not activate/open the row.
            self._pressedAction = None
            return True
        elif event.type() == types.MouseButtonRelease:
            pressed = getattr(self, '_pressedAction', None)
            self._pressedAction = None
            if action and pressed == (path, action):
                (self.trashRequested if action == 'trash' else self.pinRequested).emit(path)
                return True
        if action:
            return True
        return super().editorEvent(event, model, option, index)

    def helpEvent(self, event, view, option, index):
        action = self.actionAt(option.rect, event.pos())
        if action:
            tooltip = 'Move map to Trash…' if action == 'trash' else (
                'Unstar map' if index.data(QtCore.Qt.ItemDataRole.UserRole + 2) else 'Star map')
            QtWidgets.QToolTip.showText(event.globalPos(), tooltip, view.viewport())
            return True
        return super().helpEvent(event, view, option, index)

    def sizeHint(self, option, index):
        return QtCore.QSize(260, 28)

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        selected = bool(option.state & QtWidgets.QStyle.StateFlag.State_Selected)
        rect = option.rect.adjusted(3, 3, -3, -3)
        if selected:
            painter.setPen(QtGui.QPen(option.palette.highlight().color(), 1))
            color = option.palette.highlight().color()
            color.setAlpha(24)
            painter.setBrush(color)
            painter.drawRoundedRect(QtCore.QRectF(rect), 5, 5)
        secondary = option.palette.text().color()
        secondary.setAlpha(140)
        painter.setPen(QtGui.QPen(secondary, 1))
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        x, y = rect.left() + 10, rect.center().y() - 7
        page = QtGui.QPainterPath(QtCore.QPointF(x, y))
        for px, py in ((x + 7, y), (x + 11, y + 4), (x + 11, y + 14), (x, y + 14), (x, y)):
            page.lineTo(px, py)
        painter.drawPath(page)
        painter.drawLine(x + 7, y, x + 7, y + 4)
        painter.drawLine(x + 7, y + 4, x + 11, y + 4)
        painter.setPen(option.palette.text().color())
        font = QtGui.QFont(option.font)
        font.setWeight(QtGui.QFont.Weight.Normal)
        painter.setFont(font)
        area = rect.adjusted(32, 0, -68, 0)
        area.setWidth(max(80, int(area.width() * .53)))
        painter.drawText(area, QtCore.Qt.AlignmentFlag.AlignVCenter,
                         QtGui.QFontMetrics(font).elidedText(index.data(), QtCore.Qt.TextElideMode.ElideRight, area.width()))
        font.setWeight(QtGui.QFont.Weight.Normal)
        font.setPointSizeF(max(10, option.font.pointSizeF() - 1))
        painter.setFont(font)
        secondary = option.palette.text().color()
        secondary.setAlpha(180)
        painter.setPen(secondary)
        area = QtCore.QRect(area.right() + 14, rect.top(), max(0, rect.right() - area.right() - 82), rect.height())
        painter.drawText(area, QtCore.Qt.AlignmentFlag.AlignVCenter,
                         QtGui.QFontMetrics(font).elidedText(index.data(QtCore.Qt.ItemDataRole.UserRole + 1),
                             QtCore.Qt.TextElideMode.ElideMiddle, area.width()))
        painter.setPen(option.palette.text().color())
        painter.drawText(QtCore.QRect(option.rect.right() - 63, rect.top(), 32, rect.height()), QtCore.Qt.AlignmentFlag.AlignCenter,
                         '★' if index.data(QtCore.Qt.ItemDataRole.UserRole + 2) else '☆')
        cx, cy = option.rect.right() - 16, rect.center().y()
        painter.setPen(QtGui.QPen(secondary, 1.2))
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(QtCore.QRectF(cx - 4, cy - 3, 8, 10), 1, 1)
        painter.drawLine(cx - 6, cy - 5, cx + 6, cy - 5)
        painter.drawLine(cx - 2, cy - 7, cx + 2, cy - 7)
        painter.drawLine(cx - 1, cy - 1, cx - 1, cy + 4)
        painter.drawLine(cx + 1, cy - 1, cx + 1, cy + 4)
        painter.restore()


class NewOrOpenDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._mode = 'recent'
        self._tabState = {mode: {'query': '', 'selected': None, 'scroll': 0}
                          for mode in ('recent', 'mac', 'starred')}
        self._sources, self._jobs, self._notices = {}, {}, {}
        self._trashedPaths = set()
        self._indexStarted = False
        # Capture the job collection, not the dialog, so destruction cancels
        # workers without keeping a deleted GUI object alive in a lambda.
        jobs = self._jobs
        self.destroyed.connect(lambda: [job.cancel() for job in jobs.values()])
        self.setWindowTitle('Nexus')
        self.setModal(True)
        self.setAcceptDrops(True)
        self.resize(820, 470)
        self.setMinimumSize(680, 420)
        self.setFont(QtWidgets.QApplication.font())
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        body = QtWidgets.QHBoxLayout()
        body.setSpacing(8)
        outer.addLayout(body, 1)
        hero = QtWidgets.QFrame()
        hero.setObjectName('hero')
        hero.setMinimumWidth(220)
        body.addWidget(hero, 2)
        left = QtWidgets.QVBoxLayout(hero)
        left.setContentsMargins(12, 24, 12, 12)
        illustration = QSvgWidget(str(Path(__file__).with_name('welcome-branches.svg')))
        illustration.setFixedHeight(280)
        left.addWidget(illustration)
        actions = QtWidgets.QHBoxLayout()
        self.newButton = self.button('New Map', self.newmap, actions, primary=True)
        self.openButton = self.button('Open Map…', self.openmap, actions)
        self.openButton.setObjectName('secondary')
        left.addStretch()
        tip = QtWidgets.QLabel('Drop a map here to open')
        tip.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        tip.setObjectName('dropTip')
        tip.setWordWrap(True)
        left.addWidget(tip)
        left.addSpacing(8)
        left.addLayout(actions)
        content = QtWidgets.QWidget()
        content.setMinimumWidth(360)
        body.addWidget(content, 3)
        right = QtWidgets.QVBoxLayout(content)
        right.setContentsMargins(20, 22, 20, 12)
        right.setSpacing(12)
        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText('Search maps or folders…')
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName('Search recent and pinned maps')
        self.search.installEventFilter(self)
        right.addWidget(self.search)
        library = QtWidgets.QHBoxLayout()
        self.tabs = QtWidgets.QTabBar()
        self.tabs.addTab('Recent')
        self.tabs.addTab('On This Mac')
        self.tabs.addTab('Starred')
        self.tabs.setExpanding(False)
        self.tabs.setDrawBase(False)
        self.tabs.setAccessibleName('Map library tabs')
        library.addWidget(self.tabs)
        library.addStretch()
        self.resumeButton = self.button('Continue →', self.resume, library)
        self.resumeButton.setObjectName('resume')
        right.addLayout(library)
        self.macControls = QtWidgets.QWidget()
        macLayout = QtWidgets.QHBoxLayout(self.macControls)
        macLayout.setContentsMargins(0, 0, 0, 0)
        self.folderButton = self.button('Search a folder…', self.chooseSearchFolder, macLayout)
        macLayout.addStretch()
        self.refreshButton = self.button('Refresh', self.refreshDiscovery, macLayout)
        self.macControls.hide()
        right.addWidget(self.macControls)
        self.listWidget = QtWidgets.QListWidget()
        self.listWidget.setAccessibleName('Recent and pinned maps')
        delegate = MapDelegate(self.listWidget)
        delegate.pinRequested.connect(self.pin)
        delegate.trashRequested.connect(self.trashMap)
        self.listWidget.setItemDelegate(delegate)
        self.listWidget.setMouseTracking(True)
        self.listWidget.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.listWidget.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.listWidget.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.listWidget.customContextMenuRequested.connect(self.contextMenu)
        self.listWidget.itemActivated.connect(self.recentFileOpen)
        right.addWidget(self.listWidget, 1)
        self.empty = QtWidgets.QLabel('No recent maps yet. Create a map or open one to begin.')
        self.empty.setWordWrap(True)
        right.addWidget(self.empty)
        self.discoveryStatus = QtWidgets.QLabel()
        self.discoveryStatus.setObjectName('muted')
        self.discoveryStatus.setWordWrap(True)
        self.discoveryStatus.hide()
        right.addWidget(self.discoveryStatus)
        self.message = QtWidgets.QLabel()
        self.message.setWordWrap(True)
        self.message.hide()
        right.addWidget(self.message)
        footer = QtWidgets.QHBoxLayout()
        footer.setContentsMargins(0, 4, 0, 0)
        right.addLayout(footer)
        self.button('Recover a map…', self.recover, footer)
        footer.addStretch()
        self.button('Quit', self.reject, footer)
        self.search.textChanged.connect(self.filter)
        self.tabs.currentChanged.connect(self.switchTab)
        self.search.returnPressed.connect(self.openSelected)
        for sequence, callback in (('Ctrl+N', self.newmap), ('Ctrl+O', self.openmap), ('Ctrl+F', self.search.setFocus)):
            shortcut = QtGui.QShortcut(QtGui.QKeySequence(sequence), self)
            shortcut.activated.connect(callback)
        self.refresh()
        geometry = settings().value('welcomeGeometry')
        if isinstance(geometry, QtCore.QByteArray):
            self.restoreGeometry(geometry)
        self.clampGeometry()
        self.applyAppearance()
        self.search.setFocus()
        self.preview = map_preview.HoverPreview(self)

    def applyAppearance(self):
        dark = self.palette().color(QtGui.QPalette.ColorRole.Window).lightness() < 128
        bg, fg, muted, line, card = ('#242528', '#eceef2', '#a5a8b0', '#404248', '#303b4d') if dark else ('#ffffff', '#20232a', '#7c828d', '#e4e6eb', '#edf4ff')
        self.setStyleSheet(f'''
            QDialog {{ background: {bg}; }}
            QLabel, QPushButton, QLineEdit, QListWidget {{ color: {fg}; font-size: 13px; }}
            QLabel#heading {{ font-size: 26px; font-weight: 600; }}
            QLabel#muted, QLabel#eyebrow {{ color: {muted}; }}
            QLabel#eyebrow {{ font-size: 10px; font-weight: 600; letter-spacing: 1.5px; }}
            QFrame#hero {{ background: {bg}; }}
            QFrame#hero QLabel {{ color: {muted}; border: none; }}
            QFrame#hero QLabel#brand {{ font-size: 46px; font-weight: 600; letter-spacing: -2px; }}
            QFrame#hero QLabel#dropTip {{ color: {muted}; font-size: 11px; }}
            QPushButton {{ padding: 9px 12px; border: 1px solid transparent; border-radius: 8px; background: transparent; }}
            QPushButton:hover {{ background: {card}; }}
            QPushButton:focus {{ border: 1px solid #498ef4; }}
            QPushButton#primary {{ background: #1677ee; color: white; padding: 9px 24px; }}
            QPushButton#primary:hover {{ background: #348bf5; }}
            QPushButton#secondary {{ border: 1px solid {line}; padding: 9px 24px; }}
            QPushButton#resume {{ color: #3188fa; padding: 2px 8px; }}
            QPushButton:disabled {{ color: {muted}; }}
            QLineEdit {{ background: {bg}; padding: 8px; border: 1px solid {line}; border-radius: 6px; selection-background-color: #1677ee; selection-color: white; }}
            QLineEdit:focus {{ border-color: #498ef4; }}
            QListWidget {{ background: transparent; outline: none; }}
            QTabBar::tab {{ color: {muted}; padding: 5px 8px; background: transparent; border-bottom: 2px solid transparent; }}
            QTabBar::tab:selected {{ color: {fg}; border-bottom-color: #1677ee; }}
        ''')
        palette = self.listWidget.palette()
        palette.setColor(QtGui.QPalette.ColorRole.Text, QtGui.QColor(fg))
        palette.setColor(QtGui.QPalette.ColorRole.Highlight, QtGui.QColor('#498ef4'))
        self.listWidget.setPalette(palette)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QtCore.QEvent.Type.PaletteChange, QtCore.QEvent.Type.ApplicationPaletteChange) and hasattr(self, 'listWidget') and not getattr(self, '_styling', False):
            self._styling = True
            try:
                self.applyAppearance()
            finally:
                self._styling = False

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'resumePath'):
            self.updateResumeText()

    def updateResumeText(self):
        self.resumeButton.setText('Continue →')

    def button(self, text, callback, layout, primary=False):
        button = QtWidgets.QPushButton(text)
        button.setAutoDefault(False)
        if primary:
            button.setObjectName('primary')
        button.clicked.connect(callback)
        layout.addWidget(button)
        return button

    def clampGeometry(self):
        screens = QtGui.QGuiApplication.screens()
        screen = next((s for s in screens if s.availableGeometry().contains(self.geometry().center())), self.screen())
        area = screen.availableGeometry().adjusted(12, 12, -12, -12)
        self.resize(min(self.width(), area.width()), min(self.height(), area.height()))
        self.move(max(area.left(), min(self.x(), area.right() - self.width() + 1)),
                  max(area.top(), min(self.y(), area.bottom() - self.height() + 1)))

    def refresh(self):
        self.recent, self.pinned = history()
        self.resumePath = next((p for p in self.recent if Path(p).is_file()), None)
        self.updateResumeText()
        self.resumeButton.setToolTip(self.resumePath or 'Open or create a map to enable Resume')
        self.resumeButton.setEnabled(self.resumePath is not None)
        if self._mode == 'mac':
            self.renderMac(preserve=True)
            return
        selected = self.currentPath()
        self.listWidget.clear()
        for path in (self.pinned if self._mode == 'starred' else self.recent):
            p = Path(path)
            item = QtWidgets.QListWidgetItem(p.stem)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, path)
            location = p.parent.name
            if not p.is_file():
                location = 'Moved or missing · ' + location
            item.setData(QtCore.Qt.ItemDataRole.UserRole + 1, location)
            item.setData(QtCore.Qt.ItemDataRole.UserRole + 2, path in self.pinned)
            item.setToolTip(path + '\nStar to keep · Bin to move to Trash · Right-click for more')
            self.listWidget.addItem(item)
        self.filter()
        self.restoreList(selected)

    def filter(self, *unused):
        if self._mode == 'mac':
            self.renderMac()
            return
        query = self.search.text().casefold().split()
        count = 0
        for i in range(self.listWidget.count()):
            item = self.listWidget.item(i)
            hidden = not all(q in item.data(QtCore.Qt.ItemDataRole.UserRole).casefold() for q in query)
            item.setHidden(hidden)
            count += not hidden
        self.empty.setText('No matching maps.' if query else (
            'No starred maps yet. Click a star beside a map to keep it here.' if self._mode == 'starred'
            else 'No recent maps yet. Create a map or open one to begin.'))
        self.empty.setVisible(count == 0)

    def currentPath(self):
        item = self.listWidget.currentItem()
        return item.data(QtCore.Qt.ItemDataRole.UserRole) if item is not None else None

    def restoreList(self, path, scroll=0):
        visible = [self.listWidget.item(i) for i in range(self.listWidget.count())
                   if not self.listWidget.item(i).isHidden()]
        selected = next((item for item in visible
                         if item.data(QtCore.Qt.ItemDataRole.UserRole) == path), None)
        if selected is not None or visible:
            self.listWidget.setCurrentItem(selected or visible[0])
        self.listWidget.verticalScrollBar().setValue(scroll)

    def switchTab(self, index):
        self._tabState[self._mode] = {'query': self.search.text(),
                                     'selected': self.currentPath(),
                                     'scroll': self.listWidget.verticalScrollBar().value()}
        self._mode = ('recent', 'mac', 'starred')[index]
        state = self._tabState[self._mode]
        blocker = QtCore.QSignalBlocker(self.search)
        self.search.setText(state['query'])
        del blocker
        self.search.setPlaceholderText('Fuzzy-find map filenames…' if index == 1 else (
            'Search starred maps or folders…' if index == 2 else 'Search maps or folders…'))
        self.search.setAccessibleName('Fuzzy search map filenames on this Mac' if index == 1 else 'Search ' + self._mode + ' maps')
        self.listWidget.setAccessibleName('Maps on this Mac' if index == 1 else self._mode.title() + ' maps')
        self.macControls.setVisible(index == 1)
        self.discoveryStatus.hide()
        self.resumeButton.setVisible(index == 0)
        self.message.hide()
        self.refresh()
        self.restoreList(state['selected'], state['scroll'])
        self.search.setFocus()
        if index == 1 and not self._indexStarted:
            self._indexStarted = True
            self.startDiscovery('spotlight')

    def renderMac(self, preserve=False):
        selected = self.currentPath() if preserve else None
        scroll = self.listWidget.verticalScrollBar().value() if preserve else 0
        entries = {}
        for source in self._sources.values():
            entries.update((entry['path'], entry) for entry in source
                           if entry['path'] not in self._trashedPaths)
        matches = map_finder.ranked_maps(entries.values(), self.search.text())
        self.listWidget.clear()
        for entry in matches[:500]:
            item = QtWidgets.QListWidgetItem(entry['name'])
            item.setData(QtCore.Qt.ItemDataRole.UserRole, entry['path'])
            item.setData(QtCore.Qt.ItemDataRole.UserRole + 1, entry['folder'])
            item.setData(QtCore.Qt.ItemDataRole.UserRole + 2, entry['path'] in self.pinned)
            item.setToolTip(entry['path'] + '\nEnter to open · Right-click to show in Finder')
            self.listWidget.addItem(item)
        self.restoreList(selected, scroll)
        searching = bool(self._jobs)
        self.empty.setText('Searching for maps…' if searching else
                          'No matching maps. Try another filename or Search a folder…')
        self.empty.setVisible(not matches)
        notice = ' '.join(dict.fromkeys(value for value in self._notices.values() if value))
        if len(matches) > 500:
            notice += ('\n' if notice else '') + 'Showing the first 500 matches. Refine the filename search.'
        self.refreshButton.setText('Searching…' if searching else 'Refresh')
        self.discoveryStatus.setText(notice)
        self.discoveryStatus.setVisible(self._mode == 'mac' and bool(notice))

    def startDiscovery(self, scope):
        previous = self._jobs.get(scope)
        if previous is not None:
            previous.cancel()
        recovery = Path(QtCore.QStandardPaths.writableLocation(
            QtCore.QStandardPaths.StandardLocation.GenericDataLocation)) / 'Ectropy' / 'Nexus' / 'recovery'
        job = map_finder.DiscoveryJob(scope, excluded=(recovery,))
        self._jobs[scope] = job
        self._notices.pop(scope, None)
        job.signals.finished.connect(self.discoveryFinished)
        QtCore.QThreadPool.globalInstance().start(job)
        if self._mode == 'mac':
            self.renderMac(preserve=True)

    @QtCore.pyqtSlot(object)
    def discoveryFinished(self, result):
        current = self._jobs.get(result['scope'])
        if current is None or current.token != result['token']:
            return
        del self._jobs[result['scope']]
        if result['cancelled']:
            return
        if not result['error']:
            self._sources[result['scope']] = [entry for entry in result['entries']
                                             if entry['path'] not in self._trashedPaths]
        self._notices[result['scope']] = result['error'] or result['notice']
        if self._mode == 'mac':
            self.renderMac(preserve=True)

    def chooseSearchFolder(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, 'Search a folder for Nexus maps')
        if folder:
            self.startDiscovery(normalize(folder))

    def refreshDiscovery(self):
        # Explicit Refresh can discover a map restored from Trash; old jobs
        # are superseded by new request tokens below.
        self._trashedPaths.clear()
        for scope in set(self._sources) | {'spotlight'} | set(self._jobs):
            self.startDiscovery(scope)

    def eventFilter(self, watched, event):
        if watched is self.search and event.type() == QtCore.QEvent.Type.KeyPress and event.key() in (QtCore.Qt.Key.Key_Up, QtCore.Qt.Key.Key_Down):
            self.listWidget.setFocus()
            item = next((self.listWidget.item(i) for i in range(self.listWidget.count()) if not self.listWidget.item(i).isHidden()), None)
            if item is not None:
                self.listWidget.setCurrentItem(item)
            return True
        return super().eventFilter(watched, event)

    def openSelected(self):
        item = self.listWidget.currentItem()
        if item is None or item.isHidden():
            item = next((self.listWidget.item(i) for i in range(self.listWidget.count()) if not self.listWidget.item(i).isHidden()), None)
        if item is not None:
            self.recentFileOpen(item)

    def keyPressEvent(self, event):
        if event.key() in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter):
            item = self.listWidget.currentItem()
            if item is None or item.isHidden():
                item = next((self.listWidget.item(i) for i in range(self.listWidget.count()) if not self.listWidget.item(i).isHidden()), None)
            if item is not None:
                self.recentFileOpen(item)
            return
        if event.key() in (QtCore.Qt.Key.Key_Up, QtCore.Qt.Key.Key_Down) and self.search.hasFocus():
            self.listWidget.setFocus()
            item = next((self.listWidget.item(i) for i in range(self.listWidget.count()) if not self.listWidget.item(i).isHidden()), None)
            if item is not None:
                self.listWidget.setCurrentItem(item)
            return
        super().keyPressEvent(event)

    def run(self, callback):
        if self.result() == QtWidgets.QDialog.DialogCode.Accepted:
            return
        try:
            window = callback()
            if window is not None:
                self.accept()
        except Exception as error:
            self.message.setText('Could not open the map: ' + str(error))
            self.message.show()

    def recentFileOpen(self, item):
        path = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if not Path(path).is_file():
            if self._mode != 'mac':
                self.locate(path)
            else:
                self.message.setText('This map has moved or disappeared. Refresh or search its folder again.')
                self.message.show()
            return
        self.run(lambda: QtWidgets.QApplication.instance().raiseOrOpen(path))

    def resume(self):
        if self.resumePath:
            self.run(lambda: QtWidgets.QApplication.instance().raiseOrOpen(self.resumePath))

    def newmap(self):
        self.run(QtWidgets.QApplication.instance().dialogNew)

    def openmap(self):
        self.run(QtWidgets.QApplication.instance().dialogOpen)

    def pin(self, path):
        path = normalize(path)
        pinned = self.pinned.copy()
        pinned.remove(path) if path in pinned else pinned.append(path)
        settings().setValue('pinnedMaps', pinned)
        self.refresh()

    def remove(self, path, unstar=False):
        path = normalize(path)
        settings().setValue('recentFileList', [p for p in self.recent if p != path])
        if unstar:
            settings().setValue('pinnedMaps', [p for p in self.pinned if p != path])
        self.refresh()

    def trashError(self, text):
        self.message.setText(text)
        self.message.show()

    def trashTarget(self, path):
        candidate = Path(path).expanduser()
        # Rows contain resolved paths. Do not follow a new symlink planted
        # since discovery, or accept folders/non-map targets.
        if candidate.is_symlink() or candidate.suffix.casefold() not in map_finder.EXTENSIONS or not candidate.is_file():
            raise OSError('This map is missing or its path has changed. Refresh or locate it first.')
        known = set(self.recent) | set(self.pinned)
        known.update(entry['path'] for source in self._sources.values() for entry in source)
        canonical = normalize(path)
        if canonical not in known:
            raise OSError('This map is no longer in the library. Refresh before trying again.')
        app = QtWidgets.QApplication.instance()
        window_list = getattr(app, 'windowList', None)
        for window in window_list() if callable(window_list) else []:
            graph = getattr(getattr(window, 'scene', None), 'graph', None)
            if graph is not None and normalize(graph.path) == canonical:
                raise OSError('Close this map in Nexus before moving it to Trash.')
        stat = candidate.stat()
        return canonical, (stat.st_dev, stat.st_ino)

    def confirmTrash(self, path):
        box = QtWidgets.QMessageBox(self)
        box.setWindowTitle('Move map to Trash')
        box.setIcon(QtWidgets.QMessageBox.Icon.Warning)
        box.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        box.setText('Move “' + Path(path).name + '” to Trash?')
        box.setInformativeText(path + '\n\nYou can restore this map from macOS Trash.')
        move = box.addButton('Move to Trash', QtWidgets.QMessageBox.ButtonRole.DestructiveRole)
        cancel = box.addButton(QtWidgets.QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(cancel)
        box.setEscapeButton(cancel)
        box.exec()
        return box.clickedButton() is move

    def trashMap(self, path):
        try:
            canonical, identity = self.trashTarget(path)
            if not self.confirmTrash(canonical):
                return
            checked, current_identity = self.trashTarget(canonical)
            if checked != canonical or current_identity != identity:
                raise OSError('The file changed while confirmation was open. Please try again.')
            success, destination = QtCore.QFile.moveToTrash(canonical)
            if not success:
                raise OSError('Could not move the map to Trash. The library has not been changed.')
        except (OSError, RuntimeError, ValueError) as error:
            self.trashError(str(error))
            return
        self._trashedPaths.add(canonical)
        for scope in self._sources:
            self._sources[scope] = [entry for entry in self._sources[scope] if entry['path'] != canonical]
        self.remove(canonical, unstar=True)
        self.trashError('Moved “' + Path(canonical).name + '” to Trash. You can restore it from Trash.')

    def locate(self, old):
        old = normalize(old)
        new, _ = QtWidgets.QFileDialog.getOpenFileName(self, 'Locate ' + Path(old).name,
            str(Path(old).parent), 'Nexus maps (*.nex *.nexus);;All files (*)')
        if not new:
            return
        new = normalize(new)
        settings().setValue('recentFileList', paths([new if p == old else p for p in self.recent]))
        settings().setValue('pinnedMaps', paths([new if p == old else p for p in self.pinned]))
        self.refresh()

    def contextMenu(self, point):
        item = self.listWidget.itemAt(point)
        if item is None:
            return
        path = item.data(QtCore.Qt.ItemDataRole.UserRole)
        menu = self.mapContextMenu(path)
        menu.exec(self.listWidget.viewport().mapToGlobal(point))

    def mapContextMenu(self, path):
        menu = QtWidgets.QMenu(self)
        menu.addAction('Unstar map' if path in self.pinned else 'Star map', lambda: self.pin(path))
        menu.addAction('Show in Finder', lambda: self.showInFinder(path))
        menu.addAction('Move to Trash…', lambda: self.trashMap(path))
        if not Path(path).is_file():
            menu.addAction('Locate file…', lambda: self.locate(path))
        if self._mode == 'recent':
            menu.addAction('Remove from Recent (keep file)', lambda: self.remove(path))
        return menu

    def showInFinder(self, path):
        if sys.platform == 'darwin':
            QtCore.QProcess.startDetached('/usr/bin/open', ['-R', path])
        else:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(Path(path).parent)))

    def recover(self):
        base = Path(QtCore.QStandardPaths.writableLocation(QtCore.QStandardPaths.StandardLocation.GenericDataLocation)) / 'Ectropy' / 'Nexus' / 'recovery'
        source, _ = QtWidgets.QFileDialog.getOpenFileName(self, 'Choose a recovery snapshot', str(base), 'Nexus snapshots (*.nex)')
        if not source:
            return
        destination, _ = QtWidgets.QFileDialog.getSaveFileName(self, 'Save recovered map as a NEW file', '', 'Nexus maps (*.nex)')
        if not destination:
            return
        try:
            snapshot = Path(source).resolve()
            if base.resolve() not in snapshot.parents or not snapshot.name.startswith('snapshot-'):
                raise ValueError('Choose an existing Nexus recovery snapshot')
            with open(source, 'rb') as original:
                with open(destination, 'xb') as output:
                    try:
                        shutil.copyfileobj(original, output)
                    except Exception:
                        output.close()
                        Path(destination).unlink()
                        raise
        except Exception as error:
            self.message.setText('Recovery could not be saved: ' + str(error))
            self.message.show()
            return
        self.run(lambda: QtWidgets.QApplication.instance().raiseOrOpen(destination))

    def help(self):
        QtWidgets.QMessageBox.information(self, 'Welcome shortcuts', '↑/↓: select a map\nEnter: open selected map\nCmd+N: new map\nCmd+O: open map\nCmd+F: search\nEsc: close welcome\n\nInside a map, Cmd+/ shows all shortcuts.')

    def dropPaths(self, mime):
        return [u.toLocalFile() for u in mime.urls() if u.isLocalFile() and
                Path(u.toLocalFile()).is_file() and Path(u.toLocalFile()).suffix.lower() in ('.nex', '.nexus')]

    def dragEnterEvent(self, event):
        if self.dropPaths(event.mimeData()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        files = self.dropPaths(event.mimeData())
        if files:
            event.acceptProposedAction()
            self.run(lambda: QtWidgets.QApplication.instance().raiseOrOpen(files[0]))

    def done(self, result):
        self.preview.clear()
        for job in self._jobs.values():
            job.cancel()
        self._jobs.clear()
        settings().setValue('welcomeGeometry', self.saveGeometry())
        super().done(result)
