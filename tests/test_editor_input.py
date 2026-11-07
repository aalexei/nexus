"""Editor input regressions for the 6 October native crash reports."""
import copy
import unittest
from types import SimpleNamespace

import pr_test_support as navigation
from PyQt6 import QtCore, QtGui, QtTest, QtWidgets, sip
from nexus import graphics


class EditorInputTests(navigation.MapTestCase):
    setUpClass = classmethod(navigation.MapTestCase.setUpClass.__func__)
    tearDownClass = classmethod(navigation.MapTestCase.tearDownClass.__func__)
    node = navigation.MapTestCase.node

    def setUp(self):
        navigation.MapTestCase.setUp(self)
        self.dialog = graphics.InputDialog()
        self.dialog.setDialog(self.root)
        self.dialog.selectmode.trigger()
        self.app.processEvents()

    tearDown = navigation.MapTestCase.tearDown

    def text_item(self):
        return next(item for item in self.dialog.scene.getItems()
                    if isinstance(item, graphics.TextItem))

    def select_legacy_handle(self):
        text = self.text_item()
        text.setSelected(True)
        handle = text.widthWidget
        # Reproduce the pre-fix selection, even after new handles are no
        # longer selectable. Every content boundary must reject helpers.
        handle.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        handle.setSelected(True)
        self.dialog.scene.setSelectionWidget()
        return text, handle

    def test_width_handle_is_not_selectable_content(self):
        handle = self.text_item().widthWidget
        self.assertFalse(handle.flags() & QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)

    def test_transform_release_ignores_selected_width_handle(self):
        text, handle = self.select_legacy_handle()
        widget = self.dialog.scene.transformationWidget
        # Older gesture state can already contain a helper at release time.
        widget.selected = [text, handle]
        before = copy.deepcopy(self.root.node['content'])
        widget.pointerReleaseEvent(SimpleNamespace())
        self.assertEqual(self.root.node['content'], before)

    def test_delete_helper_selection_preserves_owning_text(self):
        text, handle = self.select_legacy_handle()
        text.setSelected(False)
        handle.setSelected(True)
        self.dialog.deleteEvent()
        self.assertIn(text.uid, self.root.node['content'])
        self.assertEqual(self.dialog.scene.transformationWidget.selected, [])

    def test_delete_selected_text_still_works(self):
        text = self.text_item()
        text.setSelected(True)
        self.dialog.deleteEvent()
        self.assertNotIn(text.uid, self.root.node['content'])
        self.assertEqual(self.dialog.scene.transformationWidget.selected, [])

    def test_reopen_after_previous_graphics_node_deleted(self):
        node = self.root.node
        sip.delete(self.root)
        self.root = graphics.StemItem(node, scene=self.scene)
        self.root.renew()
        self.dialog.setDialog(self.root)
        self.assertIs(self.dialog.stem, self.root)
        self.assertTrue(self.dialog.isVisible())
        self.assertTrue(self.dialog.scene.getItems())

    def test_switch_node_resets_pending_pointer(self):
        handle = self.text_item().widthWidget
        self.dialog.view._itemUnder = handle
        self.dialog.view._eventstate = graphics.Mouse
        self.dialog.setDialog(self.root)
        self.assertIsNone(self.dialog.view._itemUnder)
        self.assertIsNone(self.dialog.view._event)
        self.assertEqual(self.dialog.view._eventstate, graphics.Free)

    def test_click_selected_text_then_type_with_real_mouse_events(self):
        text = self.text_item()
        text.setSelected(True)
        self.dialog.scene.setSelectionWidget()
        self.dialog.view.fitInView(self.dialog.scene.itemsBoundingRect(), QtCore.Qt.AspectRatioMode.KeepAspectRatio)
        point = self.dialog.view.mapFromScene(text.sceneBoundingRect().center())
        QtTest.QTest.mouseClick(self.dialog.view.viewport(),
                               QtCore.Qt.MouseButton.LeftButton, pos=point)
        self.dialog.textmode.trigger()
        self.dialog.activateWindow()
        self.dialog.view.setFocus()
        self.app.processEvents()
        point = self.dialog.view.mapFromScene(text.sceneBoundingRect().center())
        QtTest.QTest.mouseClick(self.dialog.view.viewport(),
                               QtCore.Qt.MouseButton.LeftButton, pos=point)
        QtTest.QTest.keyClicks(self.dialog.view.viewport(), ' added text')
        self.app.processEvents()
        self.assertIn('added text', text.toPlainText())
        self.assertEqual(self.dialog.view._eventstate, graphics.Free)
        self.assertIsNone(self.dialog.view._itemUnder)

    def test_closed_stroke_and_repeated_points_do_not_divide_by_zero(self):
        self.assertAlmostEqual(graphics.distanceToLine((3, 4), (0, 0), (0, 0)), 5)
        points = [[0, 0, .8, 0], [10, 15, .8, 1], [0, 0, .8, 2]]
        self.assertEqual(len(graphics.smoothInkPath(points)), 3)
        self.dialog.penmode.trigger()
        self.dialog.view.penPressEvent(QtCore.QPointF(20, 20))
        self.dialog.view.penMoveEvent(QtCore.QPointF(20, 20))
        self.dialog.view.penReleaseEvent(SimpleNamespace())
        stroke = next(item for item in self.dialog.scene.getItems()
                      if isinstance(item, graphics.InkItem))
        self.assertFalse(stroke.path().isEmpty())


if __name__ == '__main__':
    unittest.main()
