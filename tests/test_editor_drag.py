"""Real mouse release regressions for mixed editor text transforms."""
import sys
import traceback
import unittest
from unittest import mock

import pr_test_support as navigation
from PyQt6 import QtCore, QtGui, QtTest
from nexus import graphics


class EditorDragTests(navigation.MapTestCase):
    setUpClass = classmethod(navigation.MapTestCase.setUpClass.__func__)
    tearDownClass = classmethod(navigation.MapTestCase.tearDownClass.__func__)
    setUp = navigation.MapTestCase.setUp
    tearDown = navigation.MapTestCase.tearDown
    node = navigation.MapTestCase.node

    def open_editor(self):
        self.dialog = graphics.InputDialog()
        self.dialog.setDialog(self.root)
        self.dialog.selectmode.trigger()
        self.dialog.view.fitInView(self.dialog.scene.itemsBoundingRect().adjusted(-80, -80, 80, 80), QtCore.Qt.AspectRatioMode.KeepAspectRatio)
        self.app.processEvents()
        return next(item for item in self.dialog.scene.getItems() if isinstance(item, graphics.TextItem))

    def drag(self, item, delta=QtCore.QPoint(35, 20)):
        view = self.dialog.view
        start = view.mapFromScene(item.mapToScene(item.boundingRect().center()))
        end = start + delta
        exceptions = []
        with mock.patch.object(sys, 'excepthook', lambda *args: exceptions.append(''.join(traceback.format_exception(*args)))):
            QtTest.QTest.mousePress(view.viewport(), QtCore.Qt.MouseButton.LeftButton, pos=start)
            if end != start:
                event = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove, QtCore.QPointF(end),
                    QtCore.QPointF(view.viewport().mapToGlobal(end)), QtCore.Qt.MouseButton.NoButton,
                    QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
                self.app.sendEvent(view.viewport(), event)
            QtTest.QTest.mouseRelease(view.viewport(), QtCore.Qt.MouseButton.LeftButton, pos=end)
            self.app.processEvents()
        self.assertFalse(exceptions, '\n'.join(exceptions))

    def test_text_width_drag_releases_without_exception(self):
        text = self.open_editor()
        before = text.textWidth()
        self.drag(text.widthWidget)
        self.assertNotEqual(text.textWidth(), before)

    def test_text_move_releases_without_exception(self):
        text = self.open_editor()
        text.setSelected(True)
        self.dialog.scene.setSelectionWidget()
        before = text.transform()
        self.drag(self.dialog.scene.transformationWidget.overRect)
        self.assertNotEqual(text.transform(), before)

    def test_text_corner_resize_releases_without_exception(self):
        text = self.open_editor()
        text.setSelected(True)
        self.dialog.scene.setSelectionWidget()
        before = text.transform()
        self.drag(self.dialog.scene.transformationWidget.tSE)
        self.assertNotEqual(text.transform(), before)

    def test_resize_release_with_selected_width_helper_does_not_crash(self):
        text = self.open_editor()
        text.setSelected(True)
        # Reproduce the old selection pollution, even after helper selection
        # is disabled, to check the content boundary defensively.
        text.widthWidget.setFlag(text.GraphicsItemFlag.ItemIsSelectable, True)
        text.widthWidget.setSelected(True)
        self.dialog.scene.setSelectionWidget()
        self.drag(self.dialog.scene.transformationWidget.tSE, QtCore.QPoint())
        self.assertEqual(self.dialog.scene.transformationWidget.selected, [text])
