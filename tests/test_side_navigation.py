"""Screen-side hierarchy navigation, visibility, mirroring and Shift paths."""
import unittest
from unittest import mock
import test_keyboard_navigation as navigation
from PyQt6 import QtCore, QtGui, QtWidgets
from nexus import graphydb


class SideNavigationTests(unittest.TestCase):
    setUpClass = classmethod(navigation.KeyboardNavigationTests.setUpClass.__func__)
    tearDownClass = classmethod(navigation.KeyboardNavigationTests.tearDownClass.__func__)
    setUp = navigation.KeyboardNavigationTests.setUp
    tearDown = navigation.KeyboardNavigationTests.tearDown
    node = navigation.KeyboardNavigationTests.node
    child = navigation.KeyboardNavigationTests.child
    select = navigation.KeyboardNavigationTests.select
    selected = navigation.KeyboardNavigationTests.selected
    key = navigation.KeyboardNavigationTests.key
    keys = QtCore.Qt.Key
    shift = QtCore.Qt.KeyboardModifier.ShiftModifier

    def assertOnly(self, stem):
        self.assertEqual(self.selected(), [stem])

    def test_root_both_sides_filters_first_child_and_returns_inward(self):
        right = self.child(self.root, 'Right', -150)
        left = self.child(self.root, 'Left', 150, flip=-1)
        self.select(self.root)
        self.key(self.keys.Key_Left)
        self.assertOnly(left)
        self.key(self.keys.Key_Right)
        self.assertOnly(self.root)
        self.key(self.keys.Key_Right)
        self.assertOnly(right)
        self.key(self.keys.Key_Left)
        self.assertOnly(self.root)

    def test_left_side_descendants_mirror_parent_child_and_boundary(self):
        left = self.child(self.root, 'Left', 150, flip=-1)
        nested = self.child(left, 'Further left', 0)
        self.select(self.root)
        self.key(self.keys.Key_Left)
        self.assertOnly(left)
        self.key(self.keys.Key_Left)
        self.assertOnly(nested)
        before = (self.view.horizontalScrollBar().value(), self.view.verticalScrollBar().value())
        self.key(self.keys.Key_Left)
        self.assertOnly(nested)
        self.assertEqual((self.view.horizontalScrollBar().value(), self.view.verticalScrollBar().value()), before)
        self.key(self.keys.Key_Right)
        self.assertOnly(left)
        self.key(self.keys.Key_Right)
        self.assertOnly(self.root)

    def test_shift_left_range_and_reverse_right_return_exact_path(self):
        left = self.child(self.root, 'Left', 150, flip=-1)
        nested = self.child(left, 'Further left', 0)
        self.select(self.root)
        before = self.graph.connection.total_changes()
        self.key(self.keys.Key_Left, self.shift)
        self.key(self.keys.Key_Left, self.shift)
        self.assertEqual(set(self.selected()), {self.root, left, nested})
        self.assertEqual(self.view.selection.active_uid, nested.node['uid'])
        self.key(self.keys.Key_Right, self.shift)
        self.assertEqual(set(self.selected()), {self.root, left})
        self.key(self.keys.Key_Right, self.shift)
        self.assertOnly(self.root)
        self.assertEqual(self.graph.connection.total_changes(), before)

    def test_left_collapsed_expand_then_enter_and_shift_never_expands(self):
        left = self.child(self.root, 'Left', 150, flip=-1)
        nested = self.child(left, 'Further left', 0)
        left_uid, nested_uid = left.node['uid'], nested.node['uid']
        self.select(left)
        self.key(self.keys.Key_Space)
        before = self.graph.connection.total_changes()
        self.key(self.keys.Key_Left, self.shift)
        self.assertOnly(left)
        self.assertEqual(left.childStems2, [])
        self.assertEqual(self.graph.connection.total_changes(), before)
        self.key(self.keys.Key_Left)
        self.assertOnly(left)
        self.assertEqual(len(left.childStems2), 1)
        self.key(self.keys.Key_Left)
        self.assertEqual(self.selected()[0].node['uid'], nested_uid)
        self.key(self.keys.Key_Right)
        self.assertEqual(self.selected()[0].node['uid'], left_uid)

    def test_wrong_side_does_not_expand_a_left_only_root(self):
        left = self.child(self.root, 'Left', 0, flip=-1)
        uid = left.node['uid']
        self.select(self.root)
        self.key(self.keys.Key_Space)
        before = self.graph.connection.total_changes()
        self.key(self.keys.Key_Right)
        self.assertOnly(self.root)
        self.assertEqual(self.root.childStems2, [])
        self.assertEqual(self.graph.connection.total_changes(), before)
        self.key(self.keys.Key_Left)
        self.assertOnly(self.root)
        self.key(self.keys.Key_Left)
        self.assertEqual(self.selected()[0].node['uid'], uid)

    def test_two_sided_collapsed_root_opens_only_requested_side_and_undo_is_grouped(self):
        left = self.child(self.root, 'Left', -150, flip=-1)
        lower_left = self.child(self.root, 'Lower left', 150, flip=-1)
        right = self.child(self.root, 'Right', 0)
        left_ids = {left.node['uid'], lower_left.node['uid']}
        right_uid = right.node['uid']
        self.select(self.root)
        self.key(self.keys.Key_Space)
        before = self.graph.countchanges()
        self.key(self.keys.Key_Left)
        self.assertOnly(self.root)
        self.assertEqual({s.node['uid'] for s in self.root.childStems2}, left_ids)
        self.assertTrue(self.graph.getuid(right_uid).get('hide'))
        # Two revealed children are one Undo batch, not two separate undos.
        self.scene.undo()
        self.assertEqual(self.root.childStems2, [])
        self.assertEqual(self.graph.countchanges(), before)
        self.key(self.keys.Key_Right)
        self.assertOnly(self.root)
        self.assertEqual({s.node['uid'] for s in self.root.childStems2}, {right_uid})
        self.assertTrue(all(self.graph.getuid(uid).get('hide') for uid in left_ids))

    def test_failed_expansion_rolls_back_whole_side_and_can_retry(self):
        first = self.child(self.root, 'First left', -150, flip=-1)
        second = self.child(self.root, 'Second left', 150, flip=-1)
        uids = {first.node['uid'], second.node['uid']}
        self.select(self.root)
        self.key(self.keys.Key_Space)
        before = self.graph.countchanges()
        original = graphydb.Node.save
        calls = []

        def save(node, *args, **kwargs):
            calls.append(node['uid'])
            if len(calls) == 2:
                raise OSError('disk full')
            return original(node, *args, **kwargs)

        with mock.patch.object(graphydb.Node, 'save', autospec=True, side_effect=save), self.assertLogs(level='ERROR'):
            self.key(self.keys.Key_Left)
        self.assertEqual(self.graph.countchanges(), before)
        self.assertTrue(all(self.graph.getuid(uid).get('hide') for uid in uids))
        self.assertEqual(self.root.childStems2, [])
        self.assertOnly(self.root)
        self.key(self.keys.Key_Left)
        self.assertEqual({s.node['uid'] for s in self.root.childStems2}, uids)

    def test_visible_child_preferred_when_other_children_are_hidden(self):
        visible = self.child(self.root, 'Visible right', 0)
        hidden = self.child(self.root, 'Hidden right', -150)
        hidden.node['hide'] = True
        hidden.node.save()
        self.root.renew()
        self.select(self.root)
        before = self.graph.connection.total_changes()
        self.key(self.keys.Key_Right)
        self.assertOnly(visible)
        self.assertEqual(self.graph.connection.total_changes(), before)
        self.assertTrue(self.graph.getuid(hidden.node['uid']).get('hide'))

    def test_partial_root_hidden_left_does_not_block_visible_right(self):
        right = self.child(self.root, 'Visible right', 150)
        left = self.child(self.root, 'Hidden left', -150, flip=-1)
        left_uid = left.node['uid']
        left.node['hide'] = True
        left.node.save()
        self.root.renew()
        self.select(self.root)
        before = self.graph.connection.total_changes()
        self.key(self.keys.Key_Right)
        self.assertOnly(right)
        self.assertEqual(self.graph.connection.total_changes(), before)
        self.key(self.keys.Key_Left)
        self.assertOnly(self.root)
        self.key(self.keys.Key_Left)
        self.assertOnly(self.root)  # Expand first, not select the right-hand child.
        self.key(self.keys.Key_Left)
        self.assertEqual(self.selected()[0].node['uid'], left_uid)

    def test_rotated_root_and_rotated_view_use_actual_screen_sides(self):
        child = self.child(self.root, 'Normally right', 0)
        self.root.node['angle'] = 180
        self.root.node.save()
        self.root.renew(create=False)
        self.select(self.root)
        self.key(self.keys.Key_Left)
        self.assertOnly(child)
        self.key(self.keys.Key_Right)
        self.assertOnly(self.root)
        self.view.rotate(180)
        self.key(self.keys.Key_Right)
        self.assertOnly(child)
        self.key(self.keys.Key_Left)
        self.assertOnly(self.root)

    def test_rotated_collapsed_root_expands_in_transformed_direction(self):
        child = self.child(self.root, 'Normally right', 0)
        uid = child.node['uid']
        self.root.node['angle'] = 180
        self.root.node.save()
        self.root.renew(create=False)
        self.select(self.root)
        self.key(self.keys.Key_Space)
        self.key(self.keys.Key_Left)
        self.assertOnly(self.root)
        self.key(self.keys.Key_Left)
        self.assertEqual(self.selected()[0].node['uid'], uid)

    def test_folded_back_child_does_not_steal_inward_parent_navigation(self):
        branch = self.child(self.root, 'Right branch', 150)
        folded = self.child(branch, 'Back toward root', 0, flip=-1)
        self.select(branch)
        self.key(self.keys.Key_Left)
        self.assertOnly(self.root)
        self.select(folded)
        # Its parent is now to its right, despite being on the map's right half.
        self.key(self.keys.Key_Right)
        self.assertOnly(branch)

    def test_invisible_zero_opacity_nodes_are_skipped_in_both_axes(self):
        invisible = self.child(self.root, 'Invisible right', -150)
        right = self.child(self.root, 'Visible right', 150)
        invisible.node['opacity'] = 0
        invisible.node.save()
        self.root.renew(create=False)
        self.select(self.root)
        self.key(self.keys.Key_Right)
        self.assertOnly(right)
        self.key(self.keys.Key_Up)
        self.assertNotEqual(self.selected(), [invisible])

    def test_left_navigation_from_scrollbars_and_keypad_modifiers(self):
        left = self.child(self.root, 'Left', 0, flip=-1)
        self.view.fitInView(self.scene.itemsBoundingRect().adjusted(-100, -100, 100, 100),
                            QtCore.Qt.AspectRatioMode.KeepAspectRatio)
        for widget in (self.view, self.view.viewport(), self.view.horizontalScrollBar(), self.view.verticalScrollBar()):
            self.select(self.root)
            widget.setFocus()
            event = QtGui.QKeyEvent(QtCore.QEvent.Type.KeyPress, self.keys.Key_Left,
                                   QtCore.Qt.KeyboardModifier.KeypadModifier)
            self.app.sendEvent(widget, event)
            self.assertOnly(left)


if __name__ == '__main__':
    unittest.main()
