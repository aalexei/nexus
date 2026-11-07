"""Contents hierarchy, metadata hiding and real keyboard/mouse integration."""
import unittest
from unittest import mock
import test_keyboard_navigation as navigation
from PyQt6 import QtCore, QtGui, QtWidgets, QtTest
from nexus import contents, graphics, graphydb


class ContentsTests(unittest.TestCase):
    setUpClass = classmethod(navigation.KeyboardNavigationTests.setUpClass.__func__)
    tearDownClass = classmethod(navigation.KeyboardNavigationTests.tearDownClass.__func__)
    node = navigation.KeyboardNavigationTests.node
    child = navigation.KeyboardNavigationTests.child
    select = navigation.KeyboardNavigationTests.select
    selected = navigation.KeyboardNavigationTests.selected

    def setUp(self):
        navigation.KeyboardNavigationTests.setUp(self)
        self.owner = QtWidgets.QMainWindow()
        self.owner.scene, self.owner.view = self.scene, self.view
        self.owner.editDialog = None
        self.owner.setCentralWidget(self.view)
        self.panel = contents.ContentsPanel(self.owner)
        self.dock = QtWidgets.QDockWidget('Contents', self.owner)
        self.dock.setWidget(self.panel)
        self.owner.addDockWidget(QtCore.Qt.DockWidgetArea.LeftDockWidgetArea, self.dock)
        self.owner.resize(1100, 700)
        self.owner.show()
        self.owner.activateWindow()
        self.app.processEvents()

    def tearDown(self):
        self.panel.stop()
        self.owner.takeCentralWidget()
        self.owner.hide()
        self.owner.deleteLater()
        self.app.processEvents()
        navigation.KeyboardNavigationTests.tearDown(self)

    def item(self, stem):
        self.panel.refresh()
        return self.panel.items[stem.node['uid']]

    def tree_uids(self):
        return {item.data(0, QtCore.Qt.ItemDataRole.UserRole) for item in self.panel.tree.selectedItems()}

    def click(self, item):
        self.panel.tree.scrollToItem(item)
        self.app.processEvents()
        rect = self.panel.tree.visualItemRect(item)
        QtTest.QTest.mouseClick(self.panel.tree.viewport(), QtCore.Qt.MouseButton.LeftButton,
                               pos=rect.center())
        self.app.processEvents()

    def test_first_line_plain_text_titles_without_metadata(self):
        branch = self.child(self.root, '<html><head><style>p {color: red}</style></head><body><p><b>First</b> line &amp; title</p><p>Second line</p></body></html>')
        nested = self.child(branch, 'Child title\nHidden second line')
        branch.node['tags'] = ['private-metadata']
        branch.node.save()
        root_item, item, nested_item = self.item(self.root), self.item(branch), self.item(nested)
        self.assertEqual(item.text(0), 'First line & title')
        self.assertEqual(item.toolTip(0), 'First line & title')
        self.assertEqual(nested_item.text(0), 'Child title')
        self.assertIs(item.parent(), root_item)
        self.assertIs(nested_item.parent(), item)
        self.assertTrue(root_item.isExpanded())
        self.assertFalse(item.isExpanded())
        self.assertFalse(item.flags() & QtCore.Qt.ItemFlag.ItemIsEditable)
        self.assertEqual(self.panel.tree.columnCount(), 1)
        self.assertNotIn(branch.node['uid'], item.text(0))
        self.assertNotIn('private-metadata', item.text(0))
        self.assertEqual(contents.node_title({'content': {'a': {'kind': 'Text', 'source': '\n  \n'}}}), 'Untitled')

    def test_canvas_selection_expands_outline_ancestors_and_multiselection(self):
        branch = self.child(self.root, 'Branch', -150)
        nested = self.child(branch, 'Nested')
        other = self.child(self.root, 'Other', 150)
        branch_item = self.item(branch)
        branch_item.setExpanded(False)
        self.select(nested)
        self.assertTrue(branch_item.isExpanded())
        self.assertEqual(self.tree_uids(), {nested.node['uid']})
        other.setSelected(True)
        self.assertEqual(self.tree_uids(), {nested.node['uid'], other.node['uid']})
        self.scene.clearSelection()
        self.assertEqual(self.tree_uids(), set())

    def test_shift_arrow_range_keeps_outline_selection_and_active_row_in_sync(self):
        upper = self.child(self.root, 'Upper', -150)
        lower = self.child(self.root, 'Lower', 150)
        self.panel.refresh()
        self.select(upper)
        self.view.setFocus()
        QtTest.QTest.keyClick(self.view, QtCore.Qt.Key.Key_Down, QtCore.Qt.KeyboardModifier.ShiftModifier)
        self.app.processEvents()
        self.assertEqual(self.tree_uids(), {upper.node['uid'], lower.node['uid']})
        self.assertEqual(self.panel.tree.currentItem().data(0, QtCore.Qt.ItemDataRole.UserRole), lower.node['uid'])
        self.assertTrue(self.view.hasFocus())
        QtTest.QTest.keyClick(self.view, QtCore.Qt.Key.Key_Up, QtCore.Qt.KeyboardModifier.ShiftModifier)
        self.app.processEvents()
        self.assertEqual(self.tree_uids(), {upper.node['uid']})
        self.assertEqual(self.view.selection.active_uid, upper.node['uid'])

    def test_mouse_selects_canvas_preserves_zoom_and_outline_keyboard_focus(self):
        near = self.child(self.root, 'Near', -150)
        far = self.child(self.root, 'Far', 2500)
        self.view.centerOn(near)
        zoom = self.view.transform()
        self.click(self.item(far))
        self.assertEqual(self.selected(), [far])
        self.assertTrue(self.panel.tree.hasFocus())
        self.assertEqual(self.view.transform(), zoom)
        visible = self.view.mapToScene(self.view.viewport().rect()).boundingRect()
        self.assertTrue(visible.contains(far.leaf.sceneBoundingRect()))
        QtTest.QTest.keyClick(self.panel.tree, QtCore.Qt.Key.Key_Up)
        self.app.processEvents()
        self.assertEqual(self.selected(), [near])
        self.assertTrue(self.panel.tree.hasFocus())

    def test_fold_arrows_only_fold_outline_and_do_not_write_map(self):
        branch = self.child(self.root, 'Branch')
        nested = self.child(branch, 'Nested')
        item = self.item(branch)
        self.click(item)
        self.select(branch)
        before = self.graph.connection.total_changes()
        QtTest.QTest.keyClick(self.panel.tree, QtCore.Qt.Key.Key_Right)
        self.app.processEvents()
        self.assertTrue(item.isExpanded())
        QtTest.QTest.keyClick(self.panel.tree, QtCore.Qt.Key.Key_Left)
        self.app.processEvents()
        self.assertFalse(item.isExpanded())
        self.assertEqual(self.graph.connection.total_changes(), before)
        self.assertIs(nested.parentStem(), branch)
        self.assertTrue(nested.isVisible())

    def test_hidden_nodes_remain_listed_and_only_selected_path_is_revealed(self):
        branch = self.child(self.root, 'Parent')
        target = self.child(branch, 'Hidden target', -150)
        sibling = self.child(branch, 'Other hidden child', 150)
        target_uid, sibling_uid = target.node['uid'], sibling.node['uid']
        branch.openclose.toggleVisibilities()
        self.root.openclose.toggleVisibilities()
        zoom = self.view.transform()
        self.panel.refresh()
        branch_item = self.panel.items[branch.node['uid']]
        branch_item.setExpanded(True)
        self.assertIn(target_uid, self.panel.items)
        self.click(self.panel.items[target_uid])
        self.assertEqual({s.node['uid'] for s in self.selected()}, {target_uid})
        self.assertEqual(self.view.transform(), zoom)
        self.assertIn('hide', self.graph.getuid(sibling_uid))
        self.assertNotIn('hide', self.graph.getuid(target_uid))

    def test_enter_opens_existing_editor_and_closing_restores_map_focus(self):
        branch = self.child(self.root, 'Branch')
        self.dialog = graphics.InputDialog()
        self.owner.editDialog = self.dialog
        self.scene.showEditDialog.connect(self.dialog.setDialog)
        self.click(self.item(branch))
        QtTest.QTest.keyClick(self.panel.tree, QtCore.Qt.Key.Key_Return)
        self.app.processEvents()
        self.assertTrue(self.dialog.isVisible())
        self.assertIs(self.dialog.stem, branch)
        self.assertFalse(self.panel.tree.isEnabled())
        self.dialog.saveClose()
        self.panel.refresh()
        self.app.processEvents()
        self.assertTrue(self.panel.tree.isEnabled())
        self.assertEqual(self.selected(), [branch])
        self.assertTrue(self.view.hasFocus())

    def test_live_changes_delete_undo_and_reorder_preserve_outline_state(self):
        upper = self.child(self.root, 'Upper', -150)
        lower = self.child(self.root, 'Lower', 150)
        self.child(upper, 'Nested')
        upper_item = self.item(upper)
        upper_item.setExpanded(True)
        uid = next(iter(upper.node['content']))
        upper.node['content'][uid]['source'] = 'Renamed\nDetails'
        upper.node.keyChanged('content')
        upper.node.save()
        self.panel.pollTimer.timeout.emit()
        self.assertEqual(self.panel.items[upper.node['uid']].text(0), 'Renamed')
        self.assertTrue(self.panel.items[upper.node['uid']].isExpanded())
        self.select(lower)
        self.scene.reorderBranch(-1)
        self.panel.refresh()
        self.assertEqual(self.item(self.root).child(0).data(0, QtCore.Qt.ItemDataRole.UserRole), lower.node['uid'])
        self.scene.delete()
        self.panel.refresh()
        self.assertNotIn(lower.node['uid'], self.panel.items)
        self.scene.undo()
        self.panel.refresh()
        self.assertIn(lower.node['uid'], self.panel.items)
        self.assertEqual(self.tree_uids(), {lower.node['uid']})

    def test_text_updates_only_changed_row_and_metadata_does_not_parse_titles(self):
        upper = self.child(self.root, 'Upper', -150)
        self.child(self.root, 'Lower', 150)
        self.child(upper, 'Nested')
        item = self.item(upper)
        item.setExpanded(True)
        self.select(upper)
        rows = dict(self.panel.items)
        current = self.panel.tree.currentItem()
        upper.node['opacity'] = 0.7
        upper.node.save()
        with mock.patch.object(contents, 'node_title', side_effect=AssertionError('metadata parsed title')):
            self.panel.refresh()
        content_uid = next(iter(upper.node['content']))
        upper.node['content'][content_uid]['source'] = 'Renamed'
        upper.node.keyChanged('content')
        upper.node.save()
        with mock.patch.object(contents, 'node_title', wraps=contents.node_title) as title:
            self.panel.refresh()
            self.assertEqual(title.call_count, 1)
        self.assertEqual(self.panel.items, rows)
        self.assertIs(self.panel.tree.currentItem(), current)
        self.assertEqual(item.text(0), 'Renamed')
        self.assertTrue(item.isExpanded())
        self.assertEqual(self.tree_uids(), {upper.node['uid']})

    def test_keyboard_selection_syncs_once_without_clearing_unchanged_rows(self):
        upper = self.child(self.root, 'Upper', -150)
        lower = self.child(self.root, 'Lower', 150)
        upper_item, lower_item = self.item(upper), self.item(lower)
        self.select(upper)
        with mock.patch.object(self.panel.tree, 'clearSelection', side_effect=AssertionError('selection cleared')), \
             mock.patch.object(upper_item, 'setSelected', side_effect=AssertionError('unchanged row selected')), \
             mock.patch.object(lower_item, 'setSelected', wraps=lower_item.setSelected) as select, \
             mock.patch.object(self.panel.tree, 'selectedItems', wraps=self.panel.tree.selectedItems) as read:
            self.view.selection.apply({upper.node['uid'], lower.node['uid']}, lower.node['uid'], reveal=False)
            self.assertEqual(select.call_count, 1)
            self.assertEqual(read.call_count, 1)
        self.assertEqual(self.tree_uids(), {upper.node['uid'], lower.node['uid']})
        self.assertIs(self.panel.tree.currentItem(), lower_item)

    def test_incremental_drawing_preview_changes_and_text_clears_icon(self):
        branch = self.child(self.root, '')
        branch.node['content'] = {'stroke': {'kind': 'Stroke', 'stroke': [[0, 0], [20, 20]],
            'frame': graphics.Transform().tolist(), 'width': 3, 'color': '#ff0000', 'z': 0}}
        branch.node.keyChanged('content')
        branch.node.save()
        item = self.item(branch)
        self.assertFalse(item.icon(0).isNull())
        old_icon = item.icon(0).cacheKey()
        branch.node['content']['stroke']['color'] = '#0000ff'
        branch.node.keyChanged('content')
        branch.node.save()
        self.panel.refresh()
        self.assertIs(self.item(branch), item)
        self.assertNotEqual(item.icon(0).cacheKey(), old_icon)
        branch.node['content']['text'] = {'kind': 'Text', 'source': 'Label',
            'frame': graphics.Transform().tolist(), 'z': 1}
        branch.node.keyChanged('content')
        branch.node.save()
        self.panel.refresh()
        self.assertTrue(item.icon(0).isNull())
        self.assertEqual(item.text(0), 'Label')

    def test_drawing_thumbnail_including_collapsed_nodes_does_not_write_database(self):
        branch = self.child(self.root, '')
        branch.node['content'] = {
            graphydb.generateUUID(): {'kind': 'Text', 'source': '<p><br/></p>', 'frame': graphics.Transform().tolist(), 'z': 0},
            graphydb.generateUUID(): {'kind': 'Stroke', 'stroke': [[0, 0], [20, 20], [50, 10]],
                                     'frame': graphics.Transform().tolist(), 'width': 3, 'color': '#ff0000', 'z': 1}}
        branch.node.save()
        self.root.openclose.toggleVisibilities()
        before = self.graph.connection.total_changes()
        self.panel.refresh()
        item = self.panel.items[branch.node['uid']]
        self.assertEqual(item.text(0), 'Drawing')
        self.assertFalse(item.icon(0).isNull())
        self.assertEqual(self.graph.connection.total_changes(), before)

    def test_presentation_disables_navigation_and_stop_disconnects_callbacks(self):
        self.scene.mode = 'presentation'
        self.panel.refresh()
        self.assertFalse(self.panel.tree.isEnabled())
        before = self.graph.connection.total_changes()
        self.panel.editNode()
        self.assertEqual(self.opened, [])
        self.assertEqual(self.graph.connection.total_changes(), before)
        self.scene.mode = 'edit'
        self.panel.refresh()
        self.assertTrue(self.panel.tree.isEnabled())
        self.panel.stop()
        self.assertFalse(self.panel.pollTimer.isActive())
        self.assertFalse(self.panel.refreshTimer.isActive())
        self.select(self.root)
        self.assertEqual(self.tree_uids(), set())


if __name__ == '__main__':
    unittest.main()
