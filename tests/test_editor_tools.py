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
