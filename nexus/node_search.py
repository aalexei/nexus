"""Search node text and reveal matching branches."""
from datetime import datetime, timezone
import hashlib
import logging
from pathlib import Path
import shutil
import uuid

import apsw
from bs4 import BeautifulSoup
from PyQt6 import QtCore, QtGui, QtWidgets


def node_text(node):
    return ' '.join(BeautifulSoup(item.get('source', ''), 'html.parser').get_text(' ', strip=True)
                    for item in node.get('content', {}).values() if item.get('kind') == 'Text')


class NodeSearchDialog(QtWidgets.QDialog):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.setWindowTitle('Find a Node')
        # A window-modal QDialog becomes a macOS sheet with an opaque backing
        # and a dimming layer. A floating tool window preserves real alpha.
        self.setWindowFlags(QtCore.Qt.WindowType.Tool | QtCore.Qt.WindowType.FramelessWindowHint)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowModality(QtCore.Qt.WindowModality.NonModal)
        self.resize(640, 400)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)
        self.heading = QtWidgets.QLabel('Find a Node')
        self.heading.setAccessibleName('Find a Node — drag to move search panel')
        self.heading.setCursor(QtCore.Qt.CursorShape.SizeAllCursor)
        self.heading.installEventFilter(self)
        layout.addWidget(self.heading)
        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText('Search node text, including collapsed branches…')
        self.search.setAccessibleName('Search node text')
        layout.addWidget(self.search)
        self.results = QtWidgets.QListWidget()
        self.results.setAccessibleName('Matching nodes and their parent paths')
        self.results.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        layout.addWidget(self.results)
        self.summary = QtWidgets.QLabel('Type to find a node. Enter jumps to it; Esc cancels.')
        layout.addWidget(self.summary)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Close)
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Close).setAutoDefault(False)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.search.textChanged.connect(self.find)
        self.search.returnPressed.connect(self.jump)
        self.search.installEventFilter(self)
        self.results.itemActivated.connect(self.jump)
        self.finished.connect(self.restoreFocus)
        self.refreshIndex()
        self.applyAppearance()

    def refreshIndex(self):
        current = self.results.currentItem()
        uid = current.data(QtCore.Qt.ItemDataRole.UserRole) if current is not None else None
        scroll = self.results.verticalScrollBar().value()
        self.nodes = {n['uid']: n for n in self.owner.scene.graph.fetch('[n:Stem]')}
        self.labels = {uid: node_text(n) or '(drawing / untitled node)' for uid, n in self.nodes.items()}
        self.parents = {e['enduid']: e['startuid'] for e in self.owner.scene.graph.fetch('(p) -[e:Child]> (n)')}
        self.find(self.search.text())
        for row in range(self.results.count()):
            if self.results.item(row).data(QtCore.Qt.ItemDataRole.UserRole) == uid:
                self.results.setCurrentRow(row)
                break
        self.results.verticalScrollBar().setValue(scroll)

    def applyAppearance(self):
        dark = QtWidgets.QApplication.palette().color(QtGui.QPalette.ColorRole.Window).lightness() < 128
        self.panelColor = QtGui.QColor('#24262b' if dark else '#ffffff')
        self.panelColor.setAlpha(185)
        fg, muted, input_bg = ('#f2f3f6', '#bdc2cd', 'rgba(35,38,44,235)') if dark else ('#20242b', '#525b69', 'rgba(255,255,255,235)')
        self.setStyleSheet(f'''
            QLabel, QLineEdit, QListWidget, QPushButton {{ color: {fg}; }}
            QLabel {{ background: transparent; }}
            QLineEdit {{ background: {input_bg}; border: 1px solid #879bb7; border-radius: 7px; padding: 9px; }}
            QLineEdit:focus {{ border-color: #1677ee; }}
            QListWidget {{ background: transparent; outline: none; }}
            QListWidget::item {{ padding: 8px; border-radius: 6px; }}
            QListWidget::item:selected {{ background: rgba(22,119,238,55); }}
            QPushButton {{ background: {input_bg}; border: 1px solid #879bb7; border-radius: 6px; padding: 6px 14px; }}
        ''')
        self.heading.setStyleSheet(f'color: {fg}; font-weight: 600; font-size: 16px; background: transparent;')
        self.summary.setStyleSheet(f'color: {muted}; background: transparent;')
        self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setBrush(self.panelColor)
        border = QtGui.QColor('#879bb7')
        border.setAlpha(110)
        painter.setPen(QtGui.QPen(border, 1))
        painter.drawRoundedRect(QtCore.QRectF(self.rect()).adjusted(.5, .5, -.5, -.5), 12, 12)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QtCore.QEvent.Type.ApplicationPaletteChange and hasattr(self, 'panelColor'):
            self.applyAppearance()

    def breadcrumb(self, uid):
        labels, seen = [], {uid}
        uid = self.parents.get(uid)
        while uid in self.labels and uid not in seen:
            seen.add(uid)
            labels.append(self.labels[uid][:70])
            uid = self.parents.get(uid)
        return ' › '.join(reversed(labels))

    def find(self, query):
        self.results.clear()
        words = query.casefold().split()
        if not words:
            self.summary.setText('Type to find a node. Enter jumps to it; Esc cancels.')
            return
        matches = sorted((uid for uid, label in self.labels.items()
                          if all(word in label.casefold() for word in words)),
                         key=lambda uid: (self.breadcrumb(uid).casefold(), self.labels[uid].casefold(), uid))
        for uid in matches[:200]:
            path = self.breadcrumb(uid)
            item = QtWidgets.QListWidgetItem(self.labels[uid][:150] + ('\n' + path if path else ''))
            item.setToolTip(self.labels[uid] + ('\n' + path if path else ''))
            item.setData(QtCore.Qt.ItemDataRole.UserRole, uid)
            self.results.addItem(item)
        if matches:
            self.results.setCurrentRow(0)
        self.summary.setText(f'{len(matches)} matching nodes' + (' — showing first 200' if len(matches) > 200 else '')
                             + '. ↑/↓ choose; Enter jumps; Esc cancels.')

    def eventFilter(self, watched, event):
        if watched is self.heading:
            if event.type() == QtCore.QEvent.Type.MouseButtonPress and event.button() == QtCore.Qt.MouseButton.LeftButton:
                self._dragOffset = event.globalPosition().toPoint() - self.pos()
                return True
            if event.type() == QtCore.QEvent.Type.MouseMove and event.buttons() & QtCore.Qt.MouseButton.LeftButton and hasattr(self, '_dragOffset'):
                self.move(event.globalPosition().toPoint() - self._dragOffset)
                return True
            if event.type() == QtCore.QEvent.Type.MouseButtonRelease and hasattr(self, '_dragOffset'):
                del self._dragOffset
                return True
        if watched is getattr(self, 'search', None) and event.type() == QtCore.QEvent.Type.KeyPress:
            if event.key() in (QtCore.Qt.Key.Key_Up, QtCore.Qt.Key.Key_Down):
                delta = -1 if event.key() == QtCore.Qt.Key.Key_Up else 1
                row = min(max(0, self.results.currentRow() + delta), self.results.count() - 1)
                self.results.setCurrentRow(row)
                return True
        return super().eventFilter(watched, event)

    def jump(self, *unused):
        item = self.results.currentItem()
        if item is not None:
            uid = item.data(QtCore.Qt.ItemDataRole.UserRole)
            if self.owner.scene.selectNodes([uid], reveal_hidden=True):
                self.accept()

    def restoreFocus(self, *unused):
        self.owner.view.window().activateWindow()
        self.owner.view.setFocus()
