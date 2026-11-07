"""Inline typing, text-vs-map shortcuts, checkpoint Undo, and popup geometry."""
import copy
import unittest
from unittest import mock
import test_keyboard_navigation as navigation
from PyQt6 import QtCore, QtGui, QtWidgets, QtTest
from nexus import graphics, graphydb, editor_window


class InlineTests(unittest.TestCase):
    setUpClass = classmethod(navigation.KeyboardNavigationTests.setUpClass.__func__)
    tearDownClass = classmethod(navigation.KeyboardNavigationTests.tearDownClass.__func__)
    tearDown = navigation.KeyboardNavigationTests.tearDown
    node = navigation.KeyboardNavigationTests.node
    child = navigation.KeyboardNavigationTests.child
    select = navigation.KeyboardNavigationTests.select
    selected = navigation.KeyboardNavigationTests.selected
    key = navigation.KeyboardNavigationTests.key

    def setUp(self):
        navigation.KeyboardNavigationTests.setUp(self)
        self.view.inline.textMode = True

    def type(self, text):
        QtTest.QTest.keyClicks(self.view, text)
        self.app.processEvents()

    def begin(self):
        self.select(self.root)
        self.key(QtCore.Qt.Key.Key_Return)
        self.assertIsNotNone(self.view.inline.item)
        return self.view.inline.item

    def new(self):
        self.select(self.root)
        self.key(QtCore.Qt.Key.Key_Tab)
        self.assertIsNotNone(self.view.inline.item)
        return self.view.inline.item

    def test_tab_inline_plain_font_and_escape_finish(self):
        zoom = self.view.transform()
        item = self.new()
        self.assertEqual(self.opened, [])
        self.assertEqual(item.DefaultFont.family(), 'Helvetica')
        self.assertEqual(item.DefaultFont.pointSize(), 14)
        self.type('First child')
        uid = item.stem.node['uid']
        self.key(QtCore.Qt.Key.Key_Escape)
        self.assertIsNone(self.view.inline.item)
        self.assertEqual(self.selected()[0].node['uid'], uid)
        self.assertIn('First child', self.graph.getuid(uid)['content'][item.uid]['source'])
        self.assertEqual(self.view.transform(), zoom)
        self.assertTrue(self.view.hasFocus())

    def test_enter_sibling_tab_child_shift_enter_newline(self):
        item = self.new()
        first_uid = item.stem.node['uid']
        self.type('One')
        self.key(QtCore.Qt.Key.Key_Return)
        sibling = self.view.inline.item
        self.assertIs(sibling.stem.parentStem(), self.root)
        self.assertNotEqual(sibling.stem.node['uid'], first_uid)
        self.type('Two')
        self.key(QtCore.Qt.Key.Key_Return, QtCore.Qt.KeyboardModifier.ShiftModifier)
        self.type('lines')
        self.assertEqual(sibling.toPlainText(), 'Two\nlines')
        parent_uid = sibling.stem.node['uid']
        self.key(QtCore.Qt.Key.Key_Tab)
        self.assertEqual(self.view.inline.item.stem.parentStem().node['uid'], parent_uid)

    def test_empty_new_removes_only_new_node_and_enter_tab_do_not_multiply_blanks(self):
        self.graph.clearchanges()
        self.new()
        for key in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Tab):
            self.key(key)
        self.assertEqual(len(self.root.childStems2), 1)
        self.key(QtCore.Qt.Key.Key_Escape)
        self.assertEqual(self.root.childStems2, [])
        self.assertEqual(self.selected(), [self.root])
        self.assertEqual(self.graph.countchanges(), 0)

    def test_cleared_existing_text_keeps_node_and_undo_restores_text(self):
        self.begin()
        self.key(QtCore.Qt.Key.Key_A, QtCore.Qt.KeyboardModifier.ControlModifier)
        self.key(QtCore.Qt.Key.Key_Backspace)
        self.key(QtCore.Qt.Key.Key_Escape)
        self.assertIsNotNone(self.graph.getuid(self.root.node['uid']))
        self.assertEqual(next(iter(self.root.node['content'].values()))['source'], '')
        self.scene.undo()
        self.assertIn('Root label', next(iter(self.root.node['content'].values()))['source'])

    def test_map_letters_delete_and_italic_do_not_trigger_map_actions(self):
        fired = []
        actions = []
        for key in ('S', 'H', 'I', 'Z', 'A', 'Ctrl+I', 'Backspace', 'Delete'):
            action = QtGui.QAction(key, self.view)
            action.setShortcut(key)
            action.triggered.connect(lambda checked=False, k=key: fired.append(k))
            self.view.addAction(action)
            actions.append(action)
        item = self.begin()
        self.type('shiza')
        self.key(QtCore.Qt.Key.Key_Backspace)
        self.key(QtCore.Qt.Key.Key_I, QtCore.Qt.KeyboardModifier.ControlModifier)
        self.type('italic')
        self.assertEqual(fired, [])
        self.assertIn('shizitalic', item.toPlainText())
        self.assertTrue(item.textCursor().charFormat().fontItalic())
        self.assertEqual(len(self.scene.allChildStems()), 1)

    def test_text_undo_and_checkpoints_group_one_map_change(self):
        item = self.begin()
        uid = item.stem.node['uid']
        before = self.graph.countchanges()
        self.type(' first')
        self.view.inline.checkpoint()
        for number in range(5):
            self.type(str(number))
            self.view.inline.checkpoint()
        self.assertEqual(self.graph.countchanges(), before + 1)
        self.key(QtCore.Qt.Key.Key_Z, QtCore.Qt.KeyboardModifier.ControlModifier)
        self.assertIs(self.view.inline.item, item)
        self.assertIsNotNone(self.graph.getuid(uid))
        self.key(QtCore.Qt.Key.Key_Escape)
        self.scene.undo()
        self.assertEqual(next(iter(self.root.node['content'].values()))['source'], 'Root label')

    def test_creation_and_accepted_text_undo_together(self):
        self.graph.clearchanges()
        self.new()
        self.type('Created')
        self.key(QtCore.Qt.Key.Key_Escape)
        self.scene.undo()
        self.assertEqual(self.root.childStems2, [])
        self.assertEqual(self.selected(), [self.root])

    def test_failed_save_retains_live_text_and_can_retry(self):
        item = self.begin()
        self.type(' unsaved')
        with mock.patch.object(self.root.node, 'save', side_effect=OSError('disk full')), self.assertLogs(level='ERROR'):
            self.key(QtCore.Qt.Key.Key_Escape)
        self.assertIs(self.view.inline.item, item)
        self.assertIn('unsaved', item.toPlainText())
        self.key(QtCore.Qt.Key.Key_Escape)
        self.assertIsNone(self.view.inline.item)
        self.assertIn('unsaved', self.root.node['content'][item.uid]['source'])

    def test_live_resizing_retains_cursor_item_zoom_and_format_of_existing_notes(self):
        original = copy.deepcopy(self.root.node['content'])
        item = self.begin()
        zoom = self.view.transform()
        self.type(' plus a long label ' * 15)
        QtTest.QTest.qWait(25)  # Branch layout is coalesced to the next frame.
        self.assertIs(self.view.inline.item, item)
        self.assertIs(self.scene.focusItem(), item)
        self.assertLessEqual(item.textWidth(), 480)
        self.assertEqual(self.view.transform(), zoom)
        self.assertEqual(item.DefaultFont.family(), graphics.CONFIG['text_item_font_family'])
        self.assertNotIn('font_family', original[item.uid])

    def test_fast_typing_coalesces_layout_and_never_renews_descendants(self):
        branch = self.child(self.root, 'Branch')
        self.child(branch, 'Grandchild', 80)
        self.select(branch)
        self.key(QtCore.Qt.Key.Key_Return)
        with mock.patch.object(branch, 'positionLeaf', wraps=branch.positionLeaf) as layout, \
             mock.patch.object(graphics.StemItem, 'renew', side_effect=AssertionError('typing renewed a subtree')):
            QtTest.QTest.keyClicks(self.view, ' fast input ' * 10)
            self.assertEqual(layout.call_count, 0)
            QtTest.QTest.qWait(25)
            self.assertEqual(layout.call_count, 1)
            # Once wrapped, appending within the same line doesn't change bounds.
            before = QtCore.QRectF(branch.leaf.titlerect)
            self.type('x')
            QtTest.QTest.qWait(25)
            if branch.leaf.titlerect == before:
                self.assertEqual(layout.call_count, 1)

    def test_inline_layout_matches_full_refresh_for_nested_rotated_and_flipped_branches(self):
        branch = self.child(self.root, 'Branch')
        child = self.child(branch, 'Child', 80, flip=-1)
        grandchild = self.child(child, 'Grandchild', 60)
        child.node['angle'] = 20
        child.node['scale'] = 0.8
        child.node.save()
        self.root.renew(reload=False, create=False)
        for stem in (self.root, branch, child):
            self.select(stem)
            self.key(QtCore.Qt.Key.Key_Return)
            self.type(' grows substantially ' * 4)
            self.view.inline.geometry()
            stems = self.scene.allChildStems()
            before = [(s.sceneTransform(), s.leaf.sceneBoundingRect(), s.path.path()) for s in stems]
            self.root.renew(reload=False, create=False, children=False)
            after = [(s.sceneTransform(), s.leaf.sceneBoundingRect(), s.path.path()) for s in stems]
            self.assertEqual(before, after)
            self.key(QtCore.Qt.Key.Key_Escape)
            # finish recreates leaves but retains the existing stem objects.
        self.assertIsNotNone(grandchild.scene())

    def test_shift_arrows_select_text_not_other_branches_while_typing(self):
        self.child(self.root, 'Above', -100)
        item = self.begin()
        self.type('abc')
        self.key(QtCore.Qt.Key.Key_Left, QtCore.Qt.KeyboardModifier.ShiftModifier)
        self.assertEqual(item.textCursor().selectedText(), 'c')
        self.assertEqual(self.selected(), [self.root])
        self.key(QtCore.Qt.Key.Key_Up, QtCore.Qt.KeyboardModifier.ShiftModifier)
        self.assertIs(self.view.inline.item, item)
        self.assertEqual(self.selected(), [self.root])

    def test_multiline_paste_and_ime_confirmation_do_not_create_nodes(self):
        item = self.begin()
        clipboard = self.app.clipboard()
        backup = QtCore.QMimeData()
        original = clipboard.mimeData()
        if original:
            for name in original.formats():
                backup.setData(name, original.data(name))
        try:
            clipboard.setText('Paste one\nPaste two')
            self.key(QtCore.Qt.Key.Key_V, QtCore.Qt.KeyboardModifier.ControlModifier)
        finally:
            clipboard.setMimeData(backup)
        self.assertIn('Paste one\nPaste two', item.toPlainText())
        self.view.inline.preedit = True
        self.key(QtCore.Qt.Key.Key_Return)
        self.assertEqual(len(self.scene.allChildStems()), 1)
        self.assertIs(self.view.inline.item, item)
        self.view.inline.preedit = False

    def test_full_popup_shortcut_saves_and_mixed_content_uses_popup(self):
        item = self.begin()
        self.type(' saved')
        self.key(QtCore.Qt.Key.Key_Return, QtCore.Qt.KeyboardModifier.ControlModifier)
        self.assertIsNone(self.view.inline.item)
        self.assertEqual(self.opened[-1], self.root)

        self.assertIn('saved', self.root.node['content'][item.uid]['source'])
        self.root.node['content'][graphydb.generateUUID()] = {'kind': 'Text', 'source': 'Second block',
                                                           'frame': graphics.Transform().tolist(), 'z': 1}
        self.root.node.keyChanged('content')
        self.root.node.save()
        self.root.renew()
        self.key(QtCore.Qt.Key.Key_Return)
        self.assertIsNone(self.view.inline.item)
        self.assertEqual(self.opened[-1], self.root)

    def test_blank_new_node_can_open_full_editor_without_becoming_its_parent(self):
        item = self.new()
        uid = item.stem.node['uid']
        self.key(QtCore.Qt.Key.Key_Return, QtCore.Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.opened[-1].node['uid'], uid)
        self.assertIsNotNone(self.graph.getuid(uid))


    def test_checkpoint_survives_database_reopen_and_typing_mode_can_be_disabled(self):
        item = self.begin()
        self.type(' persisted')
        self.view.inline.checkpoint()
        from nexus import nexusgraph
        reopened = nexusgraph.NexusGraph(self.graph.path)
        try:
            self.assertIn('persisted', reopened.getuid(self.root.node['uid'])['content'][item.uid]['source'])
        finally:
            reopened.close()
        self.key(QtCore.Qt.Key.Key_Escape)
        self.key(QtCore.Qt.Key.Key_T)
        self.assertFalse(self.view.inline.textMode)
        self.key(QtCore.Qt.Key.Key_Return)
        self.assertIsNone(self.view.inline.item)
        self.assertEqual(self.opened[-1], self.root)
        self.view.inline.setMode(True)


    def test_double_click_text_starts_inline_and_click_away_commits(self):
        self.view.centerOn(self.root)
        point = self.view.mapFromScene(self.root.leaf.sceneBoundingRect().center())
        QtTest.QTest.mouseDClick(self.view.viewport(), QtCore.Qt.MouseButton.LeftButton, pos=point)
        self.app.processEvents()
        # QGraphicsView forwards a double-click to the owning StemItem.
        if self.view.inline.item is None:
            QtTest.QTest.mouseRelease(self.view.viewport(), QtCore.Qt.MouseButton.LeftButton, pos=point)
            self.app.processEvents()
        self.assertIsNotNone(self.view.inline.item)
        self.type(' away')
        QtTest.QTest.mouseClick(self.view.viewport(), QtCore.Qt.MouseButton.LeftButton, pos=QtCore.QPoint(10, 10))
        self.app.processEvents()
        self.assertIsNone(self.view.inline.item)
        self.assertIn('away', next(iter(self.root.node['content'].values()))['source'])


    def test_popup_remembers_geometry_and_readable_zoom_across_instances(self):
        self.dialog = graphics.InputDialog()
        self.dialog.setDialog(self.root)
        self.assertFalse(self.dialog.isFullScreen())
        self.assertFalse(self.dialog.isMaximized())
        area = self.dialog.screen().availableGeometry()
        self.dialog.resize(min(740, area.width() - 100), min(530, area.height() - 100))
        self.dialog.move(area.topLeft() + QtCore.QPoint(40, 40))
        self.dialog.view.resetTransform()
        self.dialog.view.scale(1.4, 1.4)
        self.app.processEvents()
        expected = self.dialog.geometry()
        self.dialog.saveClose()
        other = graphics.InputDialog()
        try:
            other.setDialog(self.root)
            self.app.processEvents()
            self.assertEqual(other.size(), expected.size())
            self.assertLess((other.geometry().topLeft() - expected.topLeft()).manhattanLength(), 50)
            self.assertAlmostEqual(other.view.transform().m11(), 1.4)
        finally:
            other.saveClose()
            other.deleteLater()
            self.app.processEvents()


    def test_contents_enter_uses_same_inline_editor(self):
        from nexus import contents
        owner = QtWidgets.QWidget()
        owner.scene, owner.view, owner.editDialog = self.scene, self.view, None
        panel = contents.ContentsPanel(owner)
        try:
            panel.tree.setCurrentItem(panel.items[self.root.node['uid']])
            panel.editNode()
            self.assertIsNotNone(self.view.inline.item)
            self.assertEqual(self.view.inline.item.stem, self.root)
            self.assertEqual(self.opened, [])
        finally:
            panel.stop()
            owner.deleteLater()
            self.app.processEvents()



if __name__ == '__main__':
    unittest.main()
