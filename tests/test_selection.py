"""Real-key path selection, reversal, focus, and existing branch operations."""
import unittest
from unittest import mock
import test_keyboard_navigation as navigation
from PyQt6 import QtCore, QtGui, QtWidgets, QtTest
from nexus import graphics


class SelectionTests(unittest.TestCase):
    setUpClass = classmethod(navigation.KeyboardNavigationTests.setUpClass.__func__)
    tearDownClass = classmethod(navigation.KeyboardNavigationTests.tearDownClass.__func__)
    setUp = navigation.KeyboardNavigationTests.setUp
    tearDown = navigation.KeyboardNavigationTests.tearDown
    node = navigation.KeyboardNavigationTests.node
    child = navigation.KeyboardNavigationTests.child
    select = navigation.KeyboardNavigationTests.select
    selected = navigation.KeyboardNavigationTests.selected
    key = navigation.KeyboardNavigationTests.key
    shift = QtCore.Qt.KeyboardModifier.ShiftModifier
    keys = QtCore.Qt.Key

    def three(self):
        return (self.child(self.root, 'Upper', -150),
                self.child(self.root, 'Middle', 0), self.child(self.root, 'Lower', 150))

    def test_warm_selection_and_arrows_do_not_rescan_scene_membership(self):
        a, b, c = self.three()
        self.select(a)
        cached = self.scene.visibleStemsById()
        with mock.patch.object(self.scene, 'items', wraps=self.scene.items) as scan:
            self.key(self.keys.Key_Down, self.shift)
            self.key(self.keys.Key_Down, self.shift)
            self.key(self.keys.Key_Up, self.shift)
            self.assertSelection([a, b], b)
            self.assertIs(self.scene.visibleStemsById(), cached)
            # Geometry is never frozen in the membership cache.
            c.setPos(c.pos() + QtCore.QPointF(0, -1000))
            self.assertIs(self.view.arrowTarget(a, self.keys.Key_Up), c)
            self.assertEqual(scan.call_count, 0)

    def test_cached_membership_tracks_visibility_detach_reattach_and_clear(self):
        a, b, c = self.three()
        nested = self.child(b, 'Nested')
        expected = {s.node['uid'] for s in (self.root, a, b, c, nested)}
        self.assertEqual(set(self.scene.visibleStemsById()), expected)
        b.hide()
        self.assertEqual(set(self.scene.visibleStemsById()), expected - {b.node['uid'], nested.node['uid']})
        b.show()
        self.assertEqual(set(self.scene.visibleStemsById()), expected)
        self.root.hide()
        self.assertEqual(self.scene.visibleStemsById(), {})
        self.root.show()
        self.scene.removeItem(self.root)
        self.assertEqual(self.scene.visibleStemsById(), {})
        self.scene.addItem(self.root)
        self.assertEqual(set(self.scene.visibleStemsById()), expected)
        self.select(b)
        self.key(self.keys.Key_Down, self.shift)
        self.scene.clear()  # Deletes the active highlighted Qt item too.
        self.assertEqual(self.view.selection.items(), {})
        self.assertIsNone(self.view.selection.active_uid)

    def test_selection_changes_only_toggle_changed_nodes_and_outline_pens(self):
        a, b, c = self.three()
        self.select(a)
        self.view.selection.apply({a.node['uid'], b.node['uid']}, b.node['uid'], reveal=False)
        with mock.patch.object(a.selectpath, 'pen', side_effect=AssertionError('unchanged outline read')), \
             mock.patch.object(self.root.selectpath, 'pen', side_effect=AssertionError('root outline read')), \
             mock.patch.object(a, 'setSelected', side_effect=AssertionError('unchanged selection')), \
             mock.patch.object(b.selectpath, 'setPen', wraps=b.selectpath.setPen) as old_pen, \
             mock.patch.object(c.selectpath, 'setPen', wraps=c.selectpath.setPen) as new_pen, \
             mock.patch.object(c, 'setSelected', wraps=c.setSelected) as selected:
            self.view.selection.apply({a.node['uid'], b.node['uid'], c.node['uid']}, c.node['uid'], reveal=False)
            self.assertEqual(old_pen.call_count, 1)
            self.assertEqual(new_pen.call_count, 1)
            self.assertEqual(selected.call_count, 1)
            self.view.selection.apply({a.node['uid'], b.node['uid'], c.node['uid']}, c.node['uid'], reveal=False)
            self.assertEqual(new_pen.call_count, 1)
            self.assertEqual(selected.call_count, 1)

    def uids(self):
        return {s.node['uid'] for s in self.selected()}

    def assertSelection(self, stems, active):
        self.assertEqual(self.uids(), {s.node['uid'] for s in stems})
        self.assertEqual(self.view.selection.active_uid, active.node['uid'])

    def test_extend_repeat_reverse_and_selection_does_not_write_db(self):
        a, b, c = self.three()
        self.select(a)
        before = self.graph.connection.total_changes()
        zoom = self.view.transform()
        self.key(self.keys.Key_Down, self.shift)
        self.assertSelection([a, b], b)
        repeat = QtGui.QKeyEvent(QtCore.QEvent.Type.KeyPress, self.keys.Key_Down, self.shift, '', True)
        for _ in range(4):
            self.app.sendEvent(self.view, repeat)
        self.assertSelection([a, b, c], c)
        self.assertEqual(len(self.view.selection.path), 3)
        # No geometry lookup during reversal, even on an asymmetric layout.
        with mock.patch.object(self.view, 'arrowTarget', side_effect=AssertionError('reverse used geometry')):
            self.key(self.keys.Key_Up, self.shift)
            self.assertSelection([a, b], b)
            self.key(self.keys.Key_Up, self.shift)
            self.assertSelection([a], a)
        self.assertEqual(self.graph.connection.total_changes(), before)
        self.assertEqual(self.view.transform(), zoom)

    def test_baseline_mouse_selection_survives_reverse(self):
        a, b, c = self.three()
        self.select(a)
        c.setSelected(True)
        self.view.selection.clicked(a.node['uid'])
        self.key(self.keys.Key_Down, self.shift)
        self.assertSelection([a, b, c], b)
        self.key(self.keys.Key_Up, self.shift)
        self.assertSelection([a, c], a)

    def test_parent_child_reversal_uses_exact_path_not_first_child(self):
        a, b, c = self.three()
        self.select(c)
        self.key(self.keys.Key_Left, self.shift)
        self.assertSelection([c, self.root], self.root)
        self.key(self.keys.Key_Right, self.shift)
        self.assertSelection([c], c)  # First child is a, but we retrace to c.
        self.select(self.root)
        self.key(self.keys.Key_Right, self.shift)
        self.assertSelection([self.root, a], a)
        self.key(self.keys.Key_Left, self.shift)
        self.assertSelection([self.root], self.root)

    def test_shift_right_does_not_expand_collapsed_branch(self):
        a, b, c = self.three()
        self.select(self.root)
        self.key(self.keys.Key_Space)
        before = self.graph.connection.total_changes()
        self.key(self.keys.Key_Right, self.shift)
        self.assertSelection([self.root], self.root)
        self.assertEqual(self.root.childStems2, [])
        self.assertEqual(self.graph.connection.total_changes(), before)
        self.key(self.keys.Key_Right)
        self.assertSelection([self.root], self.root)
        self.key(self.keys.Key_Right, self.shift)
        self.assertEqual(len(self.selected()), 2)

    def test_plain_arrow_collapses_and_continues_from_active(self):
        a, b, c = self.three()
        self.select(a)
        self.key(self.keys.Key_Down, self.shift)
        self.key(self.keys.Key_Down)
        self.assertSelection([c], c)
        self.assertEqual(self.view.selection.path, [])

    def test_escape_intercepts_global_deselect_then_keeps_existing_single_behavior(self):
        a, b, c = self.three()
        action = QtGui.QAction('Deselect all', self.view)
        action.setShortcut('Esc')
        action.triggered.connect(self.scene.clearSelection)
        self.view.addAction(action)
        self.select(a)
        self.key(self.keys.Key_Down, self.shift)
        self.key(self.keys.Key_Escape)
        self.assertSelection([b], b)
        self.assertEqual(self.view.selection.path, [])
        self.key(self.keys.Key_Escape)
        self.assertEqual(self.uids(), set())

    def test_scrollbars_viewport_keypad_and_empty_selection_do_not_pan(self):
        a, b, c = self.three()
        self.view.fitInView(self.scene.itemsBoundingRect().adjusted(-100, -100, 100, 100),
                            QtCore.Qt.AspectRatioMode.KeepAspectRatio)
        for widget in (self.view, self.view.viewport(), self.view.horizontalScrollBar(), self.view.verticalScrollBar()):
            self.select(a)
            widget.setFocus()
            before = (self.view.horizontalScrollBar().value(), self.view.verticalScrollBar().value())
            event = QtGui.QKeyEvent(QtCore.QEvent.Type.KeyPress, self.keys.Key_Down,
                                   self.shift | QtCore.Qt.KeyboardModifier.KeypadModifier)
            self.app.sendEvent(widget, event)
            self.assertSelection([a, b], b)
            self.assertEqual((self.view.horizontalScrollBar().value(), self.view.verticalScrollBar().value()), before)
            self.scene.clearSelection()
            self.app.sendEvent(widget, event)
            self.assertEqual(self.uids(), set())
            self.assertEqual((self.view.horizontalScrollBar().value(), self.view.verticalScrollBar().value()), before)

    def test_offscreen_target_reveals_only_active_without_changing_zoom(self):
        a = self.child(self.root, 'Near', -300)
        b = self.child(self.root, 'Far', 2500)
        self.select(a)
        self.view.centerOn(a)
        zoom = self.view.transform()
        self.key(self.keys.Key_Down, self.shift)
        self.assertSelection([a, b], b)
        visible = self.view.mapToScene(self.view.viewport().rect()).boundingRect()
        self.assertTrue(visible.contains(b.leaf.sceneBoundingRect()))
        self.assertEqual(self.view.transform(), zoom)

    def test_hidden_nodes_and_multi_edit_creation_are_safe(self):
        a, b, c = self.three()
        b.hide()
        self.select(a)
        self.key(self.keys.Key_Down, self.shift)
        self.assertSelection([a, c], c)
        before = self.graph.connection.total_changes()
        messages = []
        self.scene.statusMessage.connect(messages.append)
        for key, modifier in ((self.keys.Key_Return, QtCore.Qt.KeyboardModifier.NoModifier),
                              (self.keys.Key_Tab, QtCore.Qt.KeyboardModifier.NoModifier),
                              (self.keys.Key_Return, self.shift),
                              (self.keys.Key_Return, QtCore.Qt.KeyboardModifier.ControlModifier)):
            self.key(key, modifier)
        self.assertEqual(self.opened, [])
        self.assertEqual(self.graph.connection.total_changes(), before)
        self.assertTrue(any('Select one node' in m for m in messages))


    def test_structure_changes_restart_path_and_delete_undo_resolve_ids(self):
        a, b, c = self.three()
        self.select(a)
        self.key(self.keys.Key_Down, self.shift)
        a.node['pos'] = [200, -200]
        a.node.save()
        self.root.renew(create=False)
        self.key(self.keys.Key_Down, self.shift)
        self.assertSelection([a, b, c], c)
        self.assertEqual(self.view.selection.path[0], b.node['uid'])
        self.scene.delete()
        self.assertEqual(self.view.selection.path, [])
        self.scene.undo()
        restored = self.view.selection.items()
        self.assertEqual(self.uids(), {a.node['uid'], b.node['uid'], c.node['uid']})
        self.key(self.keys.Key_Escape)
        self.assertEqual(len(self.uids()), 1)
        self.assertIn(self.view.selection.active_uid, restored)

    def test_active_outline_mouse_anchor_and_parent_child_move_once(self):
        a, b, c = self.three()
        self.select(a)
        self.key(self.keys.Key_Down, self.shift)
        self.assertEqual(b.selectpath.pen().color(), QtGui.QColor('#1769c2'))
        self.assertEqual(a.selectpath.pen().widthF(), 1)
        # Clicking an already selected node changes the active anchor, not the group.
        point = self.view.mapFromScene(a.leaf.sceneBoundingRect().center())
        QtTest.QTest.mouseClick(self.view.viewport(), QtCore.Qt.MouseButton.LeftButton, pos=point)
        self.app.processEvents()
        self.assertSelection([a, b], a)
        self.assertEqual(self.view.selection.path, [])
        self.select(self.root)
        self.key(self.keys.Key_Right, self.shift)
        root_pos, child_pos = list(self.root.node['pos']), list(a.node['pos'])
        point = self.view.mapFromScene(a.leaf.sceneBoundingRect().center())
        QtTest.QTest.mousePress(self.view.viewport(), QtCore.Qt.MouseButton.LeftButton, pos=point)
        a.moveSelected(QtCore.QPointF(30, 20))
        self.assertEqual(a.node['pos'], child_pos)
        self.assertEqual(self.root.node['pos'], [root_pos[0] + 30, root_pos[1] + 20])
        QtTest.QTest.mouseRelease(self.view.viewport(), QtCore.Qt.MouseButton.LeftButton, pos=point)

    def test_real_shift_click_resets_range_and_preserves_earlier_selection(self):
        a, b, c = self.three()
        self.select(a)
        self.key(self.keys.Key_Down, self.shift)
        point = self.view.mapFromScene(c.leaf.sceneBoundingRect().center())
        QtTest.QTest.mouseClick(self.view.viewport(), QtCore.Qt.MouseButton.LeftButton, self.shift, point)
        self.app.processEvents()
        self.assertSelection([a, b, c], c)
        self.assertEqual(self.view.selection.path, [])
        self.key(self.keys.Key_Up, self.shift)
        self.assertSelection([a, b, c], b)
        self.key(self.keys.Key_Down, self.shift)
        self.assertSelection([a, b, c], c)

    def test_copy_cut_parent_child_group_once_and_undo_restores_branch(self):
        a, b, c = self.three()
        clipboard = self.app.clipboard()
        backup = QtCore.QMimeData()
        original = clipboard.mimeData()
        if original:
            for name in original.formats():
                backup.setData(name, original.data(name))
        try:
            self.select(self.root)
            self.key(self.keys.Key_Right, self.shift)
            self.scene.copy()
            data = self.graph.mimedataToCopydata(clipboard.mimeData())
            self.assertEqual(len(data.nodes), 1)
            self.assertEqual(len(next(iter(data.nodes))['children']), 3)
            self.scene.cut()
            self.assertEqual(self.scene.allChildStems(), [])
            self.assertEqual(self.view.selection.path, [])
            self.scene.undo()
            self.assertEqual(len(self.scene.allChildStems()), 4)
            self.assertEqual(self.uids(), {self.root.node['uid']})
            self.key(self.keys.Key_Right, self.shift)
            self.assertEqual(len(self.uids()), 2)
        finally:
            clipboard.setMimeData(backup)

    def test_selection_controller_ignores_deleted_scene_during_teardown(self):
        scene = graphics.NexusScene()
        scene.graph = self.graph
        view = graphics.NexusView(scene)
        controller = view.selection
        from PyQt6 import sip
        sip.delete(scene)
        controller.externalChange()
        self.assertEqual(controller.items(), {})
        self.assertFalse(controller.available())
        sip.delete(view)


if __name__ == '__main__':
    unittest.main()
