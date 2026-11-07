"""Stress partial-redraw regressions without opening or modifying user maps."""
import unittest
import pr_test_support as navigation
from PyQt6 import QtCore, QtGui, QtWidgets, QtTest


class PaintRegions(QtCore.QObject):
    def __init__(self, viewport):
        super().__init__(viewport)
        self.regions = []
        viewport.installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() == QtCore.QEvent.Type.Paint:
            self.regions.append(event.region().boundingRect())
        return False


class CanvasRedrawTests(unittest.TestCase):
    setUpClass = classmethod(navigation.MapTestCase.setUpClass.__func__)
    tearDownClass = classmethod(navigation.MapTestCase.tearDownClass.__func__)
    setUp = navigation.MapTestCase.setUp
    tearDown = navigation.MapTestCase.tearDown
    node = navigation.MapTestCase.node
    child = navigation.MapTestCase.child
    select = navigation.MapTestCase.select
    key = navigation.MapTestCase.key

    def test_map_uses_full_redraw_and_safe_painter_flags(self):
        self.assertEqual(self.view.viewportUpdateMode(),
                         QtWidgets.QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        flags = self.view.optimizationFlags()
        self.assertFalse(flags & QtWidgets.QGraphicsView.OptimizationFlag.DontAdjustForAntialiasing)
        self.assertFalse(flags & QtWidgets.QGraphicsView.OptimizationFlag.DontSavePainterState)

    def test_repeated_branch_drag_repaints_whole_canvas_without_duplicating_nodes(self):
        branch = self.child(self.root, 'Selected branch', -100)
        self.child(branch, 'Child one', -150)
        self.child(branch, 'Child two', 150)
        self.view.fitInView(self.scene.itemsBoundingRect().adjusted(-150, -150, 150, 150),
                            QtCore.Qt.AspectRatioMode.KeepAspectRatio)
        self.select(branch)
        self.app.processEvents()
        before_uids = {s.node['uid'] for s in self.scene.allChildStems()}
        before = list(branch.node['pos'])
        watcher = PaintRegions(self.view.viewport())
        start = self.view.mapFromScene(branch.leaf.sceneBoundingRect().center())
        QtTest.QTest.mousePress(self.view.viewport(), QtCore.Qt.MouseButton.LeftButton, pos=start)
        for step in range(1, 21):
            point = start + QtCore.QPoint(step * 3, step * 2)
            event = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove, QtCore.QPointF(point),
                                     QtCore.QPointF(self.view.viewport().mapToGlobal(point)),
                                     QtCore.Qt.MouseButton.NoButton, QtCore.Qt.MouseButton.LeftButton,
                                     QtCore.Qt.KeyboardModifier.NoModifier)
            self.app.sendEvent(self.view.viewport(), event)
            self.app.processEvents()
        QtTest.QTest.mouseRelease(self.view.viewport(), QtCore.Qt.MouseButton.LeftButton, pos=point)
        self.app.processEvents()
        self.assertNotEqual(branch.node['pos'], before)
        self.assertEqual({s.node['uid'] for s in self.scene.allChildStems()}, before_uids)
        self.assertGreater(len(watcher.regions), 5)
        self.assertTrue(all(region.contains(self.view.viewport().rect()) for region in watcher.regions))

    def test_navigation_panning_zoom_and_label_refresh_keep_full_redraw(self):
        upper = self.child(self.root, 'Upper', -1800)
        lower = self.child(self.root, 'Lower', 1800)
        self.select(upper)
        watcher = PaintRegions(self.view.viewport())
        self.app.processEvents()
        for _ in range(5):
            self.key(QtCore.Qt.Key.Key_Down)
            self.key(QtCore.Qt.Key.Key_Up)
            self.key(QtCore.Qt.Key.Key_Down, QtCore.Qt.KeyboardModifier.ControlModifier)
            self.key(QtCore.Qt.Key.Key_Up, QtCore.Qt.KeyboardModifier.ControlModifier)
            self.view.scaleView(1.05)
            self.app.processEvents()
            self.view.scaleView(1 / 1.05)
            self.app.processEvents()
        content_uid = next(iter(lower.node['content']))
        lower.node['content'][content_uid]['source'] = 'A much wider label after editing'
        lower.node.keyChanged('content')
        lower.node.save()
        lower.renew()
        self.view.centerOn(lower)
        self.app.processEvents()
        self.assertGreater(len(watcher.regions), 10)
        self.assertTrue(all(region.contains(self.view.viewport().rect()) for region in watcher.regions))
        self.assertEqual(len(self.scene.allChildStems()), 3)


if __name__ == '__main__':
    unittest.main()
