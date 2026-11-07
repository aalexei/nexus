"""Editor shortcut regression tests using real Qt key delivery."""
import unittest
from unittest import mock
import pr_test_support as navigation
from PyQt6 import QtCore, QtGui, QtTest
from nexus import graphics


class EditorToolsTests(navigation.MapTestCase):
    setUpClass = classmethod(navigation.MapTestCase.setUpClass.__func__)
    tearDownClass = classmethod(navigation.MapTestCase.tearDownClass.__func__)
    setUp = navigation.MapTestCase.setUp
    tearDown = navigation.MapTestCase.tearDown
    node = navigation.MapTestCase.node

    def open_text(self):
        self.dialog = graphics.InputDialog()
        self.dialog.setDialog(self.root)
        self.dialog.textmode.trigger()
        self.dialog.activateWindow()
        self.dialog.view.setFocus()
        self.app.processEvents()
        return self.dialog.view.activeTextItem()

    def press(self, key, modifiers=QtCore.Qt.KeyboardModifier.NoModifier):
        QtTest.QTest.keyClick(self.dialog.view.viewport(), key, modifiers)
        self.app.processEvents()

    def test_escape_leaves_text_then_closes_editor(self):
        text = self.open_text()
        self.assertIsNotNone(text)
        self.assertTrue(self.dialog.modeIndicator.text().startswith('Typing'))
        QtTest.QTest.keyClicks(self.dialog.view, 'typed')
        self.press(QtCore.Qt.Key.Key_Escape)
        self.assertTrue(self.dialog.isVisible())
        self.assertIsNone(self.dialog.view.activeTextItem())
        self.assertTrue(self.dialog.modeIndicator.text().startswith('Select'))
        self.assertIn('typed', text.toPlainText())
        self.press(QtCore.Qt.Key.Key_Escape)
        self.assertFalse(self.dialog.isVisible())

    def test_cursor_reset_before_first_mouse_event_does_not_crash(self):
        # This native Qt slot is the exact frame from the crash report. With
        # an uninitialised mouse cache Qt 6.10 segfaults instead of raising.
        view = graphics.InkView(self.scene)
        try:
            QtCore.QMetaObject.invokeMethod(view, '_q_unsetViewportCursor',
                                           QtCore.Qt.ConnectionType.DirectConnection)
            self.assertTrue(view.isInteractive())
        finally:
            view.deleteLater()
            self.app.processEvents()

    def test_mouse_cache_does_not_duplicate_custom_drawing_events(self):
        text = self.open_text()
        self.press(QtCore.Qt.Key.Key_Escape)
        self.press(QtCore.Qt.Key.Key_P)
        view = self.dialog.view
        before = len(self.dialog.scene.getItems())
        start = QtCore.QPoint(80, 80)
        end = QtCore.QPoint(110, 105)
        QtTest.QTest.mousePress(view.viewport(), QtCore.Qt.MouseButton.LeftButton, pos=start)
        move = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove, QtCore.QPointF(end),
                                QtCore.QPointF(view.viewport().mapToGlobal(end)),
                                QtCore.Qt.MouseButton.NoButton,
                                QtCore.Qt.MouseButton.LeftButton,
                                QtCore.Qt.KeyboardModifier.NoModifier)
        self.app.sendEvent(view.viewport(), move)
        QtTest.QTest.mouseRelease(view.viewport(), QtCore.Qt.MouseButton.LeftButton, pos=end)
        self.app.processEvents()
        self.assertEqual(view._eventstate, graphics.Free)
        self.assertEqual(len(self.dialog.scene.getItems()), before + 1)
        self.assertIn(text, self.dialog.scene.getItems())
        self.assertEqual(sum(isinstance(item, graphics.InkItem)
                             for item in self.dialog.scene.getItems()), 1)
        self.assertTrue(view.isInteractive())

    def test_letters_are_text_then_tools(self):
        text = self.open_text()
        QtTest.QTest.keyClicks(self.dialog.view, 'tpbhe')
        self.assertIn('tpbhe', text.toPlainText())
        self.press(QtCore.Qt.Key.Key_Backspace)
        self.assertIn('tpbh', text.toPlainText())
        self.assertIn(text, self.dialog.scene.getItems())
        self.press(QtCore.Qt.Key.Key_Escape)
        self.press(QtCore.Qt.Key.Key_P)
        self.assertEqual(self.dialog.scene.mode, graphics.PenMode)
        self.assertTrue(self.dialog.modeIndicator.text().startswith('Pen'))
        self.press(QtCore.Qt.Key.Key_T)
        self.assertEqual(self.dialog.scene.mode, graphics.TextMode)
        self.assertIsNotNone(self.dialog.view.activeTextItem())
        self.assertTrue(self.dialog.modeIndicator.text().startswith('Typing'))

    def draw_stroke(self):
        view = self.dialog.view
        start, end = QtCore.QPoint(80, 80), QtCore.QPoint(110, 105)
        QtTest.QTest.mousePress(view.viewport(), QtCore.Qt.MouseButton.LeftButton, pos=start)
        move = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove, QtCore.QPointF(end),
                                QtCore.QPointF(view.viewport().mapToGlobal(end)),
                                QtCore.Qt.MouseButton.NoButton,
                                QtCore.Qt.MouseButton.LeftButton,
                                QtCore.Qt.KeyboardModifier.NoModifier)
        self.app.sendEvent(view.viewport(), move)
        QtTest.QTest.mouseRelease(view.viewport(), QtCore.Qt.MouseButton.LeftButton, pos=end)
        self.app.processEvents()
        return self.dialog.scene.strokeUndo[-1]

    def test_drawing_undo_removes_latest_stroke_and_preserves_text(self):
        self.open_text()
        QtTest.QTest.keyClicks(self.dialog.view, 'keep this')
        self.press(QtCore.Qt.Key.Key_Escape)
        self.press(QtCore.Qt.Key.Key_P)
        first = self.draw_stroke()
        self.press(QtCore.Qt.Key.Key_H)
        second = self.draw_stroke()
        self.press(QtCore.Qt.Key.Key_Z, QtCore.Qt.KeyboardModifier.ControlModifier)
        content = self.root.node['content']
        self.assertIn(first, content)
        self.assertNotIn(second, content)
        self.assertEqual(sum(isinstance(i, graphics.InkItem)
                             for i in self.dialog.scene.getItems()), 1)
        self.dialog.undoAct.trigger()
        self.assertNotIn(first, content)
        before = dict(content)
        self.press(QtCore.Qt.Key.Key_Z, QtCore.Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(content, before)
        self.assertTrue(any('keep this' in i.toPlainText()
                            for i in self.dialog.scene.getItems()
                            if isinstance(i, graphics.TextItem)))

    def test_text_undo_does_not_remove_drawing(self):
        self.open_text()
        self.press(QtCore.Qt.Key.Key_Escape)
        self.press(QtCore.Qt.Key.Key_P)
        stroke = self.draw_stroke()
        self.press(QtCore.Qt.Key.Key_T)
        text = self.dialog.view.activeTextItem()
        before = text.toPlainText()
        QtTest.QTest.keyClicks(self.dialog.view.viewport(), 'new typing')
        self.press(QtCore.Qt.Key.Key_Z, QtCore.Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(text.toPlainText(), before)
        self.assertIn(stroke, self.root.node['content'])

    def test_drawing_undo_skips_erased_strokes_and_stops_on_reopen(self):
        self.open_text()
        self.press(QtCore.Qt.Key.Key_Escape)
        self.press(QtCore.Qt.Key.Key_P)
        first, second = self.draw_stroke(), self.draw_stroke()
        item = next(i for i in self.dialog.scene.getItems() if i.uid == second)
        item.deleteNodeItem()
        self.dialog.view.undoEditor()
        self.assertNotIn(first, self.root.node['content'])
        remaining = self.draw_stroke()
        self.dialog.saveClose()
        self.dialog.setDialog(self.root)
        self.dialog.view.undoEditor()
        self.assertIn(remaining, self.root.node['content'])

    @unittest.skipUnless(graphics.platform.system() == 'Darwin', 'macOS Control key alias')
    def test_physical_control_z_undoes_stroke(self):
        self.open_text()
        self.press(QtCore.Qt.Key.Key_Escape)
        self.press(QtCore.Qt.Key.Key_P)
        stroke = self.draw_stroke()
        self.press(QtCore.Qt.Key.Key_Z, QtCore.Qt.KeyboardModifier.MetaModifier)
        self.assertNotIn(stroke, self.root.node['content'])

    def test_failed_stroke_undo_keeps_stroke_and_can_retry(self):
        self.open_text()
        self.press(QtCore.Qt.Key.Key_Escape)
        self.press(QtCore.Qt.Key.Key_P)
        stroke = self.draw_stroke()
        with mock.patch.object(self.root.node, 'save', side_effect=RuntimeError('disk error')):
            with self.assertLogs(level='ERROR'):
                self.dialog.view.undoEditor()
        self.assertIn(stroke, self.root.node['content'])
        self.assertEqual(self.dialog.scene.strokeUndo, [stroke])
        self.assertTrue(any(i.uid == stroke for i in self.dialog.scene.getItems()))
        self.dialog.view.undoEditor()
        self.assertNotIn(stroke, self.root.node['content'])

    def test_shift_enter_newline_enter_closes(self):
        text = self.open_text()
        self.press(QtCore.Qt.Key.Key_Return, QtCore.Qt.KeyboardModifier.ShiftModifier)
        self.assertIn('\n', text.toPlainText())
        self.assertTrue(self.dialog.isVisible())
        self.press(QtCore.Qt.Key.Key_Return)
        self.assertFalse(self.dialog.isVisible())

    def test_mode_indicator_tracks_drawing_tools_and_properties(self):
        self.open_text()
        self.press(QtCore.Qt.Key.Key_Escape)
        self.press(QtCore.Qt.Key.Key_H)
        self.assertTrue(self.dialog.modeIndicator.text().startswith('Highlighter'))
        self.press(QtCore.Qt.Key.Key_E)
        self.assertTrue(self.dialog.modeIndicator.text().startswith('Eraser'))
        self.dialog.propmode.trigger()
        self.assertTrue(self.dialog.modeIndicator.text().startswith('Properties'))
        self.dialog.propmode.trigger()
        self.assertTrue(self.dialog.modeIndicator.text().startswith('Eraser'))
