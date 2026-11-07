"""One inline text session per map; the popup remains the rich-content editor."""
import copy
import logging
from PyQt6 import QtCore, QtGui, QtWidgets
from . import graphydb


class InlineController(QtCore.QObject):
    modeChanged = QtCore.pyqtSignal(bool)

    def __init__(self, view):
        super().__init__(view)
        self.view = view
        self.scene = view.scene()
        settings = QtCore.QSettings('Ectropy', 'Nexus')
        self.textMode = settings.value('inlineTextMode', True, type=bool)
        self.item = None
        self._busy = False
        self._layout = False
        self.preedit = False
        self.dirty = False
        self.record = None
        self.timer = QtCore.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(1500)
        self.timer.timeout.connect(self.checkpoint)
        # The text item draws immediately. Coalesce branch layout separately so
        # pasted/fast input never traverses the map once per character.
        self.layoutTimer = QtCore.QTimer(self)
        self.layoutTimer.setSingleShot(True)
        self.layoutTimer.setInterval(16)
        self.layoutTimer.timeout.connect(self.geometry)
        self.hint = QtWidgets.QLabel(view.viewport())
        self.hint.setText('Enter: sibling · Tab: child · Shift+Enter: newline · Esc: finish')
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet('background: rgba(255,255,255,230); color: #333; padding: 6px; border-radius: 4px;')
        self.hint.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.hint.hide()
        self.showHints = settings.value('inlineTypingHints', True, type=bool)
        self.scene.selectionChanged.connect(self.selectionChanged)

    def setMode(self, enabled):
        self.finish()
        if self.item is not None:
            self.modeChanged.emit(self.textMode)
            return
        self.textMode = enabled
        if not enabled and hasattr(self.view, 'tasks'):
            self.view.tasks.setMode(False)
        QtCore.QSettings('Ectropy', 'Nexus').setValue('inlineTextMode', enabled)
        self.modeChanged.emit(enabled)

    def setHints(self, enabled):
        self.showHints = enabled
        QtCore.QSettings('Ectropy', 'Nexus').setValue('inlineTypingHints', enabled)
        self.updateHint()

    def updateHint(self):
        tasks = getattr(self.view, 'tasks', None)
        self.hint.setText('Todo mode ON · Enter: next task · Tab: child task · Cmd+Shift+T: exit' if tasks and tasks.enabled else
                          'Enter: sibling · Tab: child · Shift+Enter: newline · Esc: finish')
        self.hint.setMaximumWidth(max(100, self.view.viewport().width() - 24))
        self.hint.adjustSize()
        self.hint.move(12, max(0, self.view.viewport().height() - self.hint.height() - 12))
        self.hint.setVisible(self.item is not None and self.showHints)

    def canEdit(self, stem):
        content = list(stem.node.get('content', {}).values())
        return (self.textMode and self.scene.mode == 'edit' and not stem.node.get('iconified', False)
                and (not content or (len(content) == 1 and content[0].get('kind') == 'Text')))

    def start(self, stem):
        from . import graphics
        if not self.canEdit(stem):
            return False
        if self.item is not None and self.item.stem is stem:
            self.restoreFocus()
            return True
        self.finish(select=False)
        if not stem.node.get('content'):
            uid = graphydb.generateUUID()
            stem.node['content'] = {uid: {'kind': 'Text', 'source': '', 'font_family': 'Helvetica',
                'font_size': 14, 'color': '#000000', 'maxwidth': 360,
                'frame': graphics.Transform().tolist(), 'z': 0}}
            stem.node.save(batch=getattr(stem, '_creation_batch', None))
            stem.renew(reload=False)
        item = next((i for i in stem.leaf.childItems() if isinstance(i, graphics.TextItem)), None)
        if item is None:
            return False
        self.baseline = copy.deepcopy(stem.node.data)
        self.batch = getattr(stem, '_creation_batch', None) if getattr(stem, '_inline_new', False) else None
        self.batch = self.batch or graphydb.generateUUID()
        self.record = None
        self.dirty = False
        self.preedit = False
        self.item = item
        item._inline_controller = self
        item.mode = item.EditMode
        item.setTabChangesFocus(False)
        item.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextEditorInteraction)
        item.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, True)
        item.setCursor(QtCore.Qt.CursorShape.IBeamCursor)
        item.document().setUndoRedoEnabled(True)
        item.document().clearUndoRedoStacks()
        item.document().contentsChanged.connect(self.changed)
        self._busy = True
        self.scene.clearSelection()
        stem.setSelected(True)
        self._busy = False
        cursor = item.textCursor()
        cursor.movePosition(QtGui.QTextCursor.MoveOperation.End)
        item.setTextCursor(cursor)
        self.geometry()
        self.restoreFocus()
        self.updateHint()
        return True

    def restoreFocus(self):
        if self.item is not None:
            self.view.window().activateWindow()
            self.view.setFocus()
            self.item.setFocus()

    def changed(self):
        if self.item is None or self._layout or self._busy:
            return
        self.dirty = True
        if not self.layoutTimer.isActive():
            self.layoutTimer.start()
        self.timer.start()

    def geometry(self):
        self.layoutTimer.stop()
        if self.item is None or self._layout:
            return
        self._layout = True
        try:
            item, stem = self.item, self.item.stem
            item.setTextWidth(-1)
            limit = min(480, max(120, item.maxTextWidth))
            if item.document().idealWidth() > limit:
                item.setTextWidth(limit)
            title_rect = stem.leaf.childrenBoundingRect().adjusted(-3, -3, 3, 3)
            if title_rect != stem.leaf.titlerect:
                old_tip = stem.tip()
                stem.leaf.titlerect = title_rect
                stem.leaf.setBoundingRect()
                stem.positionLeaf()
                if stem.tip() != old_tip:
                    from .graphics import scaleRotateMove
                    # Only direct children attach to this tip. Moving their Qt
                    # parent transforms carries whole subtrees automatically;
                    # descendant labels, indexes and local tails are unchanged.
                    for child in list(stem.childStems2):
                        p = child.base()
                        child.setTransform(scaleRotateMove(float(child.node.get('scale', 1.0)),
                            child.node.get('angle', 0.0), p.x(), p.y()))
                        child.redrawTail()
            cursor = item.textCursor()
            block = cursor.block()
            line = block.layout().lineForTextPosition(cursor.positionInBlock())
            if line.isValid():
                x = line.cursorToX(cursor.positionInBlock())
                if isinstance(x, tuple):
                    x = x[0]
                block_rect = item.document().documentLayout().blockBoundingRect(block)
                caret = QtCore.QRectF(block_rect.x() + x, block_rect.y() + line.y(), 2, line.height())
                self.view.ensureVisible(item.mapRectToScene(caret), 20, 20)
        finally:
            self._layout = False

    def checkpoint(self):
        if self.layoutTimer.isActive():
            self.geometry()
        if self.item is None or not self.dirty or self._busy:
            return True
        item = self.item
        source = item.getSrc() if item.toPlainText().strip() else ''
        item['source'] = source
        node, graph = item.stem.node, item.stem.node.graph
        # Durable checkpoints, but one journal entry relative to the original
        # text: long typing sessions must not fill/trim the map's Undo history.
        previous_record = self.record
        try:
            with graph.connection:
                node.save(setchange=False)
                if self.record is not None:
                    graph.deletechange(self.record)
                    self.record = None
                node.keyChanged('content')
                old = graphydb.Node(copy.deepcopy(self.baseline), graph=graph)
                before = graph.cursor().execute('SELECT COALESCE(MAX(id),0) FROM changes').fetchone()[0]
                graph.addchange(old=old, new=node, batch=self.batch)
                after = graph.cursor().execute('SELECT COALESCE(MAX(id),0) FROM changes').fetchone()[0]
                if after != before:
                    self.record = after
                node.setChanged(False)
        except Exception as error:
            self.record = previous_record
            node.keyChanged('content')
            logging.exception('Could not save inline text')
            self.scene.statusMessage.emit(f'Text could not be saved: {error}. Keep this editor open and retry.')
            return False
        self.dirty = False
        return True

    def finish(self, select=True, keep_blank=False):
        if self.item is None or self._busy:
            return None
        self.timer.stop()
        if not self.checkpoint():
            return None
        self._busy = True
        item, stem = self.item, self.item.stem
        self.item = None
        self.preedit = False
        self.hint.hide()
        uid = stem.node['uid']
        try:
            item.document().contentsChanged.disconnect(self.changed)
            item.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.LinksAccessibleByMouse)
            item.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, False)
            parent = stem.parentStem()
            is_new = getattr(stem, '_inline_new', False)
            empty = not item.toPlainText().strip()
            if is_new and empty and parent is not None and not keep_blank:
                # The blank branch was never accepted: discard only its own
                # creation batch, leaving earlier Undo entries intact.
                stem.node.graph.deleteOutFromNodes(graphydb.NSet([stem.node]), setchange=False)
                stem.node.graph.cursor().execute('DELETE FROM changes WHERE json_extract(change, "$.batch")=?', [self.batch])
                uid = parent.node['uid']
                parent.renew()
            else:
                if not keep_blank:
                    stem._inline_new = False
                stem.renew(reload=False)
                if getattr(stem, '_keyboard_autoplace', False):
                    stem.placeBelowOverlappingLabels(batch=self.batch)
                    stem._keyboard_autoplace = False
            if select:
                self.scene.selectNodes([uid])
        finally:
            self._busy = False
        return uid

    def selectionChanged(self):
        if self.item is not None and not self._busy and not self.item.stem.isSelected():
            self.finish(select=False)

    def protectShortcut(self, event):
        if self.item is None:
            return False
        from .graphics import shortcutModifiers
        modifiers = shortcutModifiers(event)
        # Closing and Help remain available; everything else belongs to text.
        return not (modifiers == QtCore.Qt.KeyboardModifier.ControlModifier and
                    event.key() in (QtCore.Qt.Key.Key_Q, QtCore.Qt.Key.Key_W, QtCore.Qt.Key.Key_Slash))

    def handleKey(self, event):
        from .graphics import shortcutModifiers
        keys = QtCore.Qt.Key
        modifiers = shortcutModifiers(event)
        if modifiers == QtCore.Qt.KeyboardModifier.ControlModifier and event.key() == keys.Key_D:
            if not event.isAutoRepeat():
                self.view.tasks.cycleCurrent()
            event.accept()
            return True
        if modifiers == (QtCore.Qt.KeyboardModifier.ControlModifier | QtCore.Qt.KeyboardModifier.ShiftModifier) and event.key() == keys.Key_T:
            if not event.isAutoRepeat():
                self.view.tasks.setMode(not self.view.tasks.enabled)
            event.accept()
            return True
        if modifiers == QtCore.Qt.KeyboardModifier.ControlModifier and event.key() in (keys.Key_Return, keys.Key_Enter):
            if not event.isAutoRepeat():
                uid = self.finish(keep_blank=True)
                if self.item is not None:
                    event.accept()
                    return True
                selected = [s for s in self.scene.selectedItems() if hasattr(s, 'node')]
                stem = selected[0] if len(selected) == 1 else None
                if stem is not None:
                    stem.editStem(full=True)
                elif len(selected) > 1:
                    self.scene.statusMessage.emit('Select one node to open the full editor')
            event.accept()
            return True
        if self.item is None:
            if self.scene.mode == 'edit' and modifiers == QtCore.Qt.KeyboardModifier.NoModifier and event.key() == keys.Key_T:
                if not event.isAutoRepeat():
                    self.setMode(not self.textMode)
                event.accept()
                return True
            return False
        if modifiers == QtCore.Qt.KeyboardModifier.ControlModifier and event.key() == keys.Key_V:
            mime = QtWidgets.QApplication.clipboard().mimeData()
            if mime is not None and mime.hasText():
                cursor = self.item.textCursor()
                cursor.insertText(mime.text())
                self.item.setTextCursor(cursor)
            else:
                self.scene.statusMessage.emit('Use Cmd+Enter to paste images or drawings in the full editor')
            event.accept()
            return True
        if modifiers == QtCore.Qt.KeyboardModifier.ControlModifier and event.key() in (keys.Key_B, keys.Key_I, keys.Key_U):
            cursor = self.item.textCursor()
            fmt = QtGui.QTextCharFormat()
            if event.key() == keys.Key_B:
                fmt.setFontWeight(QtGui.QFont.Weight.Normal if cursor.charFormat().fontWeight() > QtGui.QFont.Weight.Normal else QtGui.QFont.Weight.Bold)
            elif event.key() == keys.Key_I:
                fmt.setFontItalic(not cursor.charFormat().fontItalic())
            else:
                fmt.setFontUnderline(not cursor.charFormat().fontUnderline())
            cursor.mergeCharFormat(fmt)
            self.item.setTextCursor(cursor)
            event.accept()
            return True
        if modifiers != QtCore.Qt.KeyboardModifier.NoModifier:
            return False
        if event.key() not in (keys.Key_Escape, keys.Key_Return, keys.Key_Enter, keys.Key_Tab):
            return False
        if self.preedit:
            return False
        if event.isAutoRepeat():
            event.accept()
            return True
        if event.key() == keys.Key_Escape:
            self.finish()
            if self.item is not None:
                event.accept()
                return True
        elif self.item.toPlainText().strip():
            child = event.key() == keys.Key_Tab
            self.finish()
            if self.item is not None:
                event.accept()
                return True  # Save failure: never create another node.
            creation = QtGui.QKeyEvent(QtCore.QEvent.Type.KeyPress,
                keys.Key_Tab if child else keys.Key_Return,
                QtCore.Qt.KeyboardModifier.NoModifier if child else QtCore.Qt.KeyboardModifier.ShiftModifier)
            self.view.navigateNode(creation)
        event.accept()
        return True
