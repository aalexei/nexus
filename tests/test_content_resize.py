"""Map resize uses actual mouse events and preserves descendants and source data."""
import copy
import sys
import traceback
import unittest
from unittest import mock

import test_keyboard_navigation as navigation
from PyQt6 import QtCore, QtGui, QtTest, QtWidgets
from nexus import graphics, graphydb, nexusgraph


class ContentResizeTests(unittest.TestCase):
    setUpClass = classmethod(navigation.KeyboardNavigationTests.setUpClass.__func__)
    tearDownClass = classmethod(navigation.KeyboardNavigationTests.tearDownClass.__func__)
    setUp = navigation.KeyboardNavigationTests.setUp
    tearDown = navigation.KeyboardNavigationTests.tearDown
    node = navigation.KeyboardNavigationTests.node
    child = navigation.KeyboardNavigationTests.child
    select = navigation.KeyboardNavigationTests.select
    key = navigation.KeyboardNavigationTests.key

    def prepare(self, stem):
        self.select(stem)
        self.view.fitInView(self.scene.itemsBoundingRect().adjusted(-100, -100, 100, 100),
                            QtCore.Qt.AspectRatioMode.KeepAspectRatio)
        self.app.processEvents()
        self.graph.clearchanges()

    def drag(self, stem, factor=0.6, corner=2, cancel=False, prepared=False):
        control = self.view.contentResize
        if not prepared:
            self.prepare(stem)
        points = control.points(stem)
        start, anchor = points[corner], points[(corner+2) % 4]
        end = anchor + (start-anchor)*factor
        errors = []
        with mock.patch.object(sys, 'excepthook', lambda *args: errors.append(''.join(traceback.format_exception(*args)))):
            QtTest.QTest.mousePress(self.view.viewport(), QtCore.Qt.MouseButton.LeftButton, pos=start)
            self.assertIsNotNone(control.state)
            event = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove, QtCore.QPointF(end),
                QtCore.QPointF(self.view.viewport().mapToGlobal(end)), QtCore.Qt.MouseButton.NoButton,
                QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
            self.app.sendEvent(self.view.viewport(), event)
            if cancel:
                self.key(QtCore.Qt.Key.Key_Escape)
            QtTest.QTest.mouseRelease(self.view.viewport(), QtCore.Qt.MouseButton.LeftButton, pos=end)
            self.app.processEvents()
        self.assertFalse(errors, '\n'.join(errors))
        self.assertIsNone(control.state)

    def points_equal(self, before, after):
        for p, q in zip(before, after):
            self.assertAlmostEqual(p.x(), q.x(), places=5)
            self.assertAlmostEqual(p.y(), q.y(), places=5)

    def child_points(self, stem):
        return [stem.mapToScene(QtCore.QPointF()), stem.leaf.mapToScene(stem.leaf.boundingRect().center()),
                stem.leaf.mapToScene(stem.leaf.boundingRect().bottomRight())]

    def test_drag_resizes_content_not_branch_and_single_undo_restores(self):
        child = self.child(self.root, 'Child', 100)
        grandchild = self.child(child, 'Grandchild', 70)
        before = copy.deepcopy(self.root.node.data)
        children = {s.node['uid']: self.child_points(s) for s in [child, grandchild]}
        anchor = self.root.leaf.mapToScene(self.root.leaf.boundingRect().topLeft())
        width = self.root.leaf.childrenBoundingRect().width()
        self.drag(self.root)
        self.assertLess(self.root.leaf.childrenBoundingRect().width(), width)
        self.assertEqual(self.root.node['scale'], before['scale'])
        self.points_equal([anchor], [self.root.leaf.mapToScene(self.root.leaf.boundingRect().topLeft())])
        for s in [child, grandchild]:
            self.points_equal(children[s.node['uid']], self.child_points(s))
        batches = {item.get('batch') for _, item in self.graph.lastchanges()}
        self.assertEqual(len(batches), 1)
        self.root.renew()
        for s in [child, grandchild]:
            self.points_equal(children[s.node['uid']], self.child_points(s))
        self.scene.undo()
        self.assertEqual(self.graph.getuid(self.root.node['uid'])['content'], before['content'])
        self.assertEqual(self.graph.getuid(self.root.node['uid'])['pos'], before['pos'])
        self.assertFalse(self.graph.lastchanges())

    def test_left_facing_rotated_branch_keeps_descendants_and_proportions(self):
        stem = self.child(self.root, 'Left branch', -150, flip=-1)
        stem.node['angle'] = 25
        stem.node['scale'] = 0.8
        stem.node.save()
        stem.renew()
        child = self.child(stem, 'Nested', 30)
        before = self.child_points(child)
        item = next(i for i in stem.leaf.childItems() if isinstance(i, graphics.TextItem))
        old = QtGui.QTransform(item.transform())
        self.drag(stem, 1.5, corner=0)
        item = next(i for i in stem.leaf.childItems() if isinstance(i, graphics.TextItem))
        self.assertAlmostEqual(item.transform().m11()/old.m11(), item.transform().m22()/old.m22())
        self.points_equal(before, self.child_points(child))
        self.root.renew()
        self.points_equal(before, self.child_points(child))

    def test_hidden_child_stays_in_place_when_revealed(self):
        child = self.child(self.root, 'Hidden child', 120)
        point = child.mapToScene(QtCore.QPointF())
        child.node['hide'] = True
        child.node.save()
        self.root.renew()
        uid = child.node['uid']
        self.drag(self.root, 1.4, corner=1)
        node = self.graph.getuid(uid)
        node.discard('hide')
        node.save()
        self.root.renew()
        revealed = next(s for s in self.root.childStems2 if s.node['uid'] == uid)
        self.points_equal([point], [revealed.mapToScene(QtCore.QPointF())])

    def test_escape_and_click_without_drag_do_not_save(self):
        before = copy.deepcopy(self.root.node.data)
        self.drag(self.root, cancel=True)
        self.assertEqual(self.root.node['content'], before['content'])
        self.assertEqual(self.root.node['pos'], before['pos'])
        self.assertFalse(self.graph.lastchanges())
        self.drag(self.root, factor=1)
        self.assertFalse(self.graph.lastchanges())

    def test_mixed_content_scales_together_and_image_bytes_stay_original(self):
        image = QtGui.QImage(120, 70, QtGui.QImage.Format.Format_ARGB32)
        image.fill(QtGui.QColor('orange'))
        copied, _ = self.graph.itemFromImage(image)
        data = next(iter(copied.images.values()))
        source = self.graph.Node('ImageData')
        source.update(data)
        source.save()
        self.graph.Edge(self.root.node, 'With', source).save()
        uid = graphydb.generateUUID()
        stroke = graphydb.generateUUID()
        self.root.node['content'][uid] = {'kind': 'Image', 'sha1': source['sha1'],
            'frame': graphics.Transform(QtGui.QTransform.fromTranslate(10, 80)).tolist(), 'z': 1}
        self.root.node['content'][stroke] = {'kind': 'Stroke', 'stroke': [[0, 0], [30, 10]],
            'width': 2, 'color': '#000000', 'frame': graphics.Transform().tolist(), 'z': 2}
        self.root.node.keyChanged('content')
        self.root.node.save()
        self.root.renew()
        original = source['data']
        before = copy.deepcopy(self.root.node['content'])
        self.drag(self.root)
        factors = []
        for key, old in before.items():
            a = graphics.Transform(*old['frame'])
            b = graphics.Transform(*self.root.node['content'][key]['frame'])
            factors.append(b.m11()/a.m11())
            self.assertAlmostEqual(b.m11()/a.m11(), b.m22()/a.m22())
        self.assertTrue(all(abs(factors[0]-f) < 1e-6 for f in factors))
        self.assertEqual(self.graph.getuid(source['uid'])['data'], original)
        self.assertEqual(nexusgraph.DataToImage(original).size(), image.size())

    def test_handles_not_available_while_typing_or_multiple_selected_or_presenting(self):
        child = self.child(self.root, 'Child', 100)
        self.prepare(self.root)
        self.assertIs(self.view.contentResize.target(), self.root)
        child.setSelected(True)
        self.assertIsNone(self.view.contentResize.target())
        child.setSelected(False)
        self.scene.mode = 'presentation'
        self.assertIsNone(self.view.contentResize.target())
        self.scene.mode = 'edit'
        self.view.inline.textMode = True
        self.view.inline.start(self.root)
        self.assertIsNone(self.view.contentResize.target())
        self.view.inline.finish()

    def test_save_failure_rolls_back_entire_resize(self):
        child = self.child(self.root, 'Child', 100)
        before = copy.deepcopy(self.root.node.data)
        child_before = copy.deepcopy(child.node.data)
        save = graphydb.Node.save
        def fail(node, *args, **kwargs):
            if kwargs.get('batch') and node['uid'] == child.node['uid']:
                raise RuntimeError('test failed save')
            return save(node, *args, **kwargs)
        with mock.patch.object(graphydb.Node, 'save', fail), mock.patch.object(QtWidgets.QMessageBox, 'warning'), self.assertLogs(level='ERROR'):
            self.drag(self.root)
        self.assertEqual(self.graph.getuid(self.root.node['uid'])['content'], before['content'])
        self.assertEqual(self.graph.getuid(self.root.node['uid'])['pos'], before['pos'])
        self.assertEqual(self.graph.getuid(child.node['uid'])['pos'], child_before['pos'])
        self.assertFalse(self.graph.lastchanges())

    def test_every_corner_can_resize_without_changing_view_zoom(self):
        for corner in range(4):
            self.prepare(self.root)
            zoom = self.view.transform()
            self.drag(self.root, 1.2, corner=corner, prepared=True)
            self.assertEqual(self.view.transform(), zoom)
            self.assertIs(self.view.contentResize.target(), self.root)

    def test_handles_are_view_only_and_have_fixed_pixel_hit_area(self):
        self.prepare(self.root)
        count = len(self.scene.items())
        self.view.scale(0.4, 0.4)
        self.app.processEvents()
        point = self.view.contentResize.points(self.root)[0]
        self.assertIs(self.view.contentResize.hit(point + QtCore.QPoint(6, 0))[0], self.root)
        self.view.grab()  # Exercise foreground rendering, also on native macOS.
        self.assertEqual(len(self.scene.items()), count)
        self.assertEqual(self.scene.selectedItems(), [self.root])

    def test_window_deactivation_cancels_preview_without_saving(self):
        self.prepare(self.root)
        control = self.view.contentResize
        point = control.points(self.root)[2]
        event = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseButtonPress, QtCore.QPointF(point),
            QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.MouseButton.LeftButton,
            QtCore.Qt.KeyboardModifier.NoModifier)
        self.assertTrue(control.press(event))
        original = copy.deepcopy(self.root.node['content'])
        control.preview(0.7)
        self.app.sendEvent(self.view, QtCore.QEvent(QtCore.QEvent.Type.WindowDeactivate))
        self.assertIsNone(control.state)
        self.assertEqual(self.root.node['content'], original)
        self.assertFalse(self.graph.lastchanges())

    def hover(self, point):
        event = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove, QtCore.QPointF(point),
            QtCore.QPointF(self.view.viewport().mapToGlobal(point)), QtCore.Qt.MouseButton.NoButton,
            QtCore.Qt.MouseButton.NoButton, QtCore.Qt.KeyboardModifier.NoModifier)
        self.app.sendEvent(self.view.viewport(), event)
        self.app.processEvents()

    def test_only_nearby_corner_appears_and_hides_on_leave(self):
        self.prepare(self.root)
        control = self.view.contentResize
        self.assertIsNone(control.visibleCorner())
        points = control.points(self.root)
        self.hover(self.view.mapFromScene(self.root.leaf.sceneBoundingRect().center()))
        self.assertIsNone(control.visibleCorner())
        for i, point in enumerate(points):
            self.hover(point + QtCore.QPoint(10, 0))
            self.assertEqual(control.visibleCorner(), i)
        self.hover(QtCore.QPoint(15, 15))
        self.assertIsNone(control.visibleCorner())
        self.hover(points[0])
        self.app.sendEvent(self.view.viewport(), QtCore.QEvent(QtCore.QEvent.Type.Leave))
        self.assertIsNone(control.visibleCorner())
        self.assertFalse(self.graph.lastchanges())

    def test_active_handle_stays_visible_while_dragging_outside_view(self):
        self.prepare(self.root)
        control = self.view.contentResize
        point = control.points(self.root)[2]
        QtTest.QTest.mousePress(self.view.viewport(), QtCore.Qt.MouseButton.LeftButton, pos=point)
        self.assertEqual(control.visibleCorner(), 2)
        control.preview(0.7)
        self.app.sendEvent(self.view.viewport(), QtCore.QEvent(QtCore.QEvent.Type.Leave))
        self.assertEqual(control.visibleCorner(), 2)
        self.key(QtCore.Qt.Key.Key_Escape)
        self.assertIsNone(control.visibleCorner())
        QtTest.QTest.mouseRelease(self.view.viewport(), QtCore.Qt.MouseButton.LeftButton, pos=point)
        self.assertFalse(self.graph.lastchanges())

    def test_unselected_node_has_no_hover_handle(self):
        child = self.child(self.root, 'Unselected', 100)
        self.prepare(self.root)
        self.hover(self.view.contentResize.points(child)[0])
        self.assertIsNone(self.view.contentResize.visibleCorner())
        self.assertEqual(self.scene.selectedItems(), [self.root])
