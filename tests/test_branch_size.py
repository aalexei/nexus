"""Child sizing, explicit whole-map migration, Undo and dialog safeguards."""
import math
import unittest
from unittest import mock

import pr_test_support as navigation
from PyQt6 import QtCore, QtWidgets, QtTest
from nexus import branch_size, graphics, graphydb, nexusgraph


class BranchSizeTests(navigation.MapTestCase):
    setUpClass = classmethod(navigation.MapTestCase.setUpClass.__func__)
    tearDownClass = classmethod(navigation.MapTestCase.tearDownClass.__func__)
    setUp = navigation.MapTestCase.setUp
    tearDown = navigation.MapTestCase.tearDown
    node = navigation.MapTestCase.node
    child = navigation.MapTestCase.child
    select = navigation.MapTestCase.select

    def new_child(self, parent):
        point = parent.tip() + QtCore.QPointF(200 * parent.direction(), 100)
        parent.drawBud(point)
        parent.newStem(point)
        return self.opened[-1]

    def test_legacy_map_keeps_shrinking_and_rotation_does_not_corrupt_child_size(self):
        self.assertIsNone(branch_size.map_ratio(self.graph))
        first = self.new_child(self.root)
        self.assertEqual(first.node['scale'], graphics.CONFIG['child_scale'])
        first.node['angle'] = 90
        first.node.save()
        first.renew()
        second = self.new_child(first)
        self.assertEqual(second.node['scale'], first.node['scale'])
        self.assertGreater(second.node['scale'], 0)

    def test_new_nodes_use_map_ratio_without_resizing_existing_nodes(self):
        first = self.new_child(self.root)
        existing = self.new_child(first)
        before = {s.node['uid']: s.node['scale'] for s in (self.root, first, existing)}
        self.assertTrue(branch_size.apply_ratio(self.scene, 1.0))
        self.assertEqual(branch_size.map_ratio(self.graph), 1.0)
        self.assertEqual({s.node['uid']: s.node['scale'] for s in (self.root, first, existing)}, before)
        second = self.new_child(first)
        third = self.new_child(second)
        fourth = self.new_child(third)
        for stem in (second, third, fourth):
            self.assertEqual(stem.node['scale'], 1.0)
            transform = stem.sceneTransform()
            self.assertAlmostEqual(math.hypot(transform.m11(), transform.m12()), first.node['scale'])
        self.assertEqual(self.new_child(self.root).node['scale'], graphics.CONFIG['child_scale'])

    def test_explicit_resize_includes_hidden_nodes_preserves_layout_and_undoes_together(self):
        first = self.child(self.root, 'First')
        second = self.child(first, 'Second')
        hidden = self.child(second, 'Hidden')
        first.node['scale'] = 0.6
        second.node['scale'] = 0.4
        hidden.node['scale'] = 0.3
        for stem in (first, second, hidden):
            stem.node.save()
        self.root.renew()
        second.openclose.toggleVisibilities()
        ids = [s.node['uid'] for s in (self.root, first, second, hidden)]
        before = {uid: {k: v for k, v in self.graph.getuid(uid).data.items() if k != 'mtime'} for uid in ids}
        self.select(second)
        zoom = self.view.transform()
        scroll = (self.view.horizontalScrollBar().value(), self.view.verticalScrollBar().value())
        self.graph.clearchanges()
        self.assertTrue(branch_size.apply_ratio(self.scene, 1.0, resize_existing=True))
        for uid in ids:
            current = self.graph.getuid(uid)
            expected = dict(before[uid])
            if uid in (second.node['uid'], hidden.node['uid']):
                expected['scale'] = 1.0
            self.assertEqual({k: v for k, v in current.data.items() if k != 'mtime'}, expected)
        self.assertIn('hide', self.graph.getuid(hidden.node['uid']))
        self.assertEqual(self.view.transform(), zoom)
        self.assertEqual((self.view.horizontalScrollBar().value(), self.view.verticalScrollBar().value()), scroll)
        self.assertTrue(second.isSelected())
        self.undo_map()
        self.assertIsNone(branch_size.map_ratio(self.graph))
        for uid in ids:
            self.assertEqual({k: v for k, v in self.graph.getuid(uid).data.items() if k != 'mtime'}, before[uid])

    def test_setting_persists_in_this_map_and_undo_refreshes_creation_policy(self):
        self.graph.clearchanges()
        branch_size.apply_ratio(self.scene, 0.85)
        other = nexusgraph.NexusGraph(self.graph.path)
        try:
            self.assertEqual(branch_size.map_ratio(other), 0.85)
        finally:
            other.close()
        self.undo_map()
        self.assertIsNone(branch_size.map_ratio(self.graph))
        first = self.new_child(self.root)
        self.assertEqual(self.new_child(first).node['scale'], graphics.CONFIG['child_scale'])

    def test_noop_invalid_and_presentation_do_not_write(self):
        branch_size.apply_ratio(self.scene, 1.0, resize_existing=True)
        before = self.graph.connection.total_changes()
        self.assertFalse(branch_size.apply_ratio(self.scene, 1.0, resize_existing=True))
        self.assertEqual(self.graph.connection.total_changes(), before)
        for value in (0, -1, 2.01, float('nan'), float('inf'), 'bad', None, True):
            with self.assertRaises(ValueError):
                branch_size.apply_ratio(self.scene, value)
        self.assertEqual(self.graph.connection.total_changes(), before)
        self.scene.mode = 'presentation'
        self.assertFalse(branch_size.apply_ratio(self.scene, 0.85, resize_existing=True))
        self.assertEqual(self.graph.connection.total_changes(), before)

    def test_save_failure_rolls_back_setting_and_nodes_without_changing_graphics(self):
        first = self.child(self.root, 'First')
        second = self.child(first, 'Second')
        second.node['scale'] = 0.5
        second.node.save()
        second.renew()
        save = graphydb.Node.save
        def fail(node, *args, **kwargs):
            if node['uid'] == second.node['uid']:
                raise RuntimeError('Temporary save failure')
            return save(node, *args, **kwargs)
        with mock.patch.object(graphydb.Node, 'save', fail):
            with self.assertRaisesRegex(RuntimeError, 'save failure'):
                branch_size.apply_ratio(self.scene, 1.0, resize_existing=True)
        self.assertIsNone(branch_size.map_ratio(self.graph))
        self.assertEqual(self.graph.getuid(second.node['uid'])['scale'], 0.5)
        self.assertEqual(second.node['scale'], 0.5)
        self.assertEqual(second.transform().m11(), 0.5)

    def test_dialog_cancel_custom_presets_apply_and_reopen(self):
        self.owner = QtWidgets.QWidget()
        self.owner.scene, self.owner.view = self.scene, self.view
        dialog = branch_size.ChildSizeDialog(self.owner)
        try:
            before = self.graph.connection.total_changes()
            self.assertTrue(dialog.existing.isChecked())
            dialog.choosePreset(2)
            self.assertEqual(dialog.percent.value(), 100)
            dialog.percent.setValue(92)
            self.assertEqual(dialog.presets.currentText(), 'Custom')
            dialog.reject()
            self.assertEqual(self.graph.connection.total_changes(), before)
            dialog.accept()
            self.assertEqual(branch_size.map_ratio(self.graph), 0.92)
            dialog.refresh()
            self.assertEqual(dialog.percent.value(), 92)
            self.undo_map()
            dialog.refresh()
            self.assertEqual(dialog.percent.value(), graphics.CONFIG['child_scale'] * 100)
        finally:
            self.owner.deleteLater()
            self.app.processEvents()

    def test_default_dialog_apply_resizes_visible_labels_even_if_ratio_already_saved(self):
        first = self.child(self.root, 'First')
        second = self.child(first, 'Second label')
        third = self.child(second, 'Third label')
        for stem in (first, second, third):
            stem.node['scale'] = 0.5
            stem.node.save()
        self.root.renew()
        # Reproduce the reported failure: 100% was already saved for future
        # nodes, but the existing graph still had shrinking local transforms.
        branch_size.apply_ratio(self.scene, 1.0)
        before = [stem.leaf.sceneBoundingRect().width() for stem in (second, third)]
        self.select(second)
        zoom = self.view.transform()
        owner = QtWidgets.QWidget()
        owner.scene, owner.view = self.scene, self.view
        dialog = branch_size.ChildSizeDialog(owner)
        messages = []
        self.scene.statusMessage.connect(messages.append)
        try:
            self.assertTrue(dialog.existing.isChecked())
            self.assertEqual(dialog.percent.value(), 100)
            self.assertIn('2 existing', dialog.summary.text())
            self.assertEqual(dialog.applyButton.text(), 'Apply to map')
            dialog.applyButton.click()  # No checkbox manipulation required.
            self.app.processEvents()
            after = [stem.leaf.sceneBoundingRect().width() for stem in (second, third)]
            self.assertAlmostEqual(after[0], before[0] * 2)
            self.assertAlmostEqual(after[1], before[1] * 4)
            self.assertEqual(self.view.transform(), zoom)
            self.assertTrue(second.isSelected())
            self.assertIn('Resized 2', messages[-1])
            self.undo_map()
            self.assertEqual(branch_size.map_ratio(self.graph), 1.0)
            for stem, width in zip((second, third), before):
                self.assertAlmostEqual(stem.leaf.sceneBoundingRect().width(), width)
        finally:
            owner.deleteLater()
            self.app.processEvents()

    def test_new_nodes_only_and_noop_have_explicit_dialog_feedback(self):
        first = self.child(self.root, 'First')
        second = self.child(first, 'Second')
        second.node['scale'] = 0.5
        second.node.save()
        self.root.renew()
        width = second.leaf.sceneBoundingRect().width()
        owner = QtWidgets.QWidget()
        owner.scene, owner.view = self.scene, self.view
        dialog = branch_size.ChildSizeDialog(owner)
        messages = []
        self.scene.statusMessage.connect(messages.append)
        try:
            dialog.choosePreset(2)
            dialog.existing.setChecked(False)
            self.assertEqual(dialog.applyButton.text(), 'Save for new nodes')
            self.assertIn('will not be resized', dialog.summary.text())
            dialog.accept()
            self.assertEqual(second.leaf.sceneBoundingRect().width(), width)
            self.assertIn('current graph unchanged', messages[-1])
            dialog.refresh()
            self.assertTrue(dialog.existing.isChecked())
            dialog.accept()
            self.assertGreater(second.leaf.sceneBoundingRect().width(), width)
            dialog.refresh()
            self.assertIn('already have this ratio', dialog.summary.text())
            before = self.graph.connection.total_changes()
            dialog.accept()
            self.assertEqual(self.graph.connection.total_changes(), before)
            self.assertIn('no resizing needed', messages[-1])
        finally:
            owner.deleteLater()
            self.app.processEvents()

    def test_shallow_map_explains_why_existing_nodes_will_not_resize(self):
        self.child(self.root, 'First level only')
        owner = QtWidgets.QWidget()
        owner.scene, owner.view = self.scene, self.view
        dialog = branch_size.ChildSizeDialog(owner)
        messages = []
        self.scene.statusMessage.connect(messages.append)
        try:
            dialog.choosePreset(2)
            self.assertIn('No deeper nodes to resize', dialog.summary.text())
            self.assertEqual(dialog.applyButton.text(), 'Save ratio')
            dialog.accept()
            self.assertIn('first-level branches stay unchanged', messages[-1])
        finally:
            owner.deleteLater()
            self.app.processEvents()

    def test_dialog_enter_applies_and_escape_cancels_without_writing(self):
        owner = QtWidgets.QWidget()
        owner.scene, owner.view = self.scene, self.view
        dialog = branch_size.ChildSizeDialog(owner)
        try:
            owner.show()
            dialog.show()
            dialog.activateWindow()
            dialog.percent.setFocus()
            dialog.percent.selectAll()
            self.app.processEvents()
            QtTest.QTest.keyClicks(dialog.percent, '100')
            QtTest.QTest.keyClick(dialog.percent, QtCore.Qt.Key.Key_Return)
            self.app.processEvents()
            self.assertFalse(dialog.isVisible())
            self.assertEqual(branch_size.map_ratio(self.graph), 1.0)
            dialog.refresh()
            dialog.show()
            dialog.percent.setValue(85)
            before = self.graph.connection.total_changes()
            QtTest.QTest.keyClick(dialog.percent, QtCore.Qt.Key.Key_Escape)
            self.app.processEvents()
            self.assertFalse(dialog.isVisible())
            self.assertEqual(self.graph.connection.total_changes(), before)
            self.assertEqual(branch_size.map_ratio(self.graph), 1.0)
        finally:
            owner.hide()
            owner.deleteLater()
            self.app.processEvents()


if __name__ == '__main__':
    unittest.main()
