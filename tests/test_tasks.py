"""Task mode, real-key checklist entry, metadata, click safety and exports."""
import copy
from pathlib import Path
import unittest
from unittest import mock

import test_inline as inline_tests
from PyQt6 import QtCore, QtGui, QtWidgets, QtTest, QtSvg
from nexus import tasks, graphydb, nexusgraph


class TaskTests(unittest.TestCase):
    setUpClass = classmethod(inline_tests.InlineTests.setUpClass.__func__)
    tearDownClass = classmethod(inline_tests.InlineTests.tearDownClass.__func__)
    tearDown = inline_tests.InlineTests.tearDown
    new = inline_tests.InlineTests.new
    begin = inline_tests.InlineTests.begin
    type = inline_tests.InlineTests.type
    key = inline_tests.InlineTests.key
    select = inline_tests.InlineTests.select
    child = inline_tests.InlineTests.child
    node = inline_tests.InlineTests.node
    keys = QtCore.Qt.Key
    toggle_mod = QtCore.Qt.KeyboardModifier.ControlModifier | QtCore.Qt.KeyboardModifier.ShiftModifier

    def setUp(self):
        inline_tests.InlineTests.setUp(self)
        # Existing binary-state regression checks explicitly cover the setting
        # OFF. Three-state/default-ON behavior has its own tests below.
        self.view.tasks.setDoingEnabled(False)

    def toggle(self):
        self.key(self.keys.Key_T, self.toggle_mod)

    def cycle(self):
        self.key(self.keys.Key_D, QtCore.Qt.KeyboardModifier.ControlModifier)

    def test_full_keyboard_cycle_and_reverse_undo_preserve_content_and_children(self):
        self.view.tasks.setDoingEnabled(True)
        child = self.child(self.root, 'Child', 60)
        original = copy.deepcopy(self.root.node.data)
        child_transform = child.sceneTransform()
        origin = self.root.leaf.mapToScene(QtCore.QPointF())
        self.select(self.root)
        self.graph.clearchanges()
        for expected in (tasks.TODO, tasks.DOING, tasks.DONE, None):
            self.cycle()
            self.assertEqual(tasks.state(self.root.node) if tasks.is_task(self.root.node) else None, expected)
            self.assertEqual(self.root.node['content'], original['content'])
            self.assertEqual(self.root.leaf.mapToScene(QtCore.QPointF()), origin)
            self.assertEqual(child.sceneTransform(), child_transform)
            self.assertFalse(self.view.tasks.enabled)
        self.assertNotIn('todo', self.root.node)
        self.assertNotIn('todo_state', self.root.node)
        self.assertNotIn('todo_done', self.root.node)
        for expected in (tasks.DONE, tasks.DOING, tasks.TODO, None):
            self.scene.undo()
            self.assertEqual(tasks.state(self.root.node) if tasks.is_task(self.root.node) else None, expected)
        self.assertEqual(self.root.node['pos'], original['pos'])
        self.assertFalse(self.graph.lastchanges())

    def test_cycle_skips_doing_and_mode_does_not_modify_current_note(self):
        self.select(self.root)
        self.graph.clearchanges()
        self.toggle()
        self.assertFalse(tasks.is_task(self.root.node))
        self.assertFalse(self.graph.lastchanges())
        for expected in (tasks.TODO, tasks.DONE, None):
            self.cycle()
            self.assertEqual(tasks.state(self.root.node) if tasks.is_task(self.root.node) else None, expected)
            self.assertTrue(self.view.tasks.enabled)
        self.toggle()
        self.assertFalse(self.view.tasks.enabled)

    def test_status_only_keyboard_cycle_does_not_rebuild_descendants(self):
        child = self.child(self.root, 'Child', 70)
        self.select(self.root)
        self.cycle()
        self.view.tasks.setDoingEnabled(True)
        with mock.patch.object(self.root, 'renew', side_effect=AssertionError('rebuilt subtree')):
            self.cycle()
            self.assertEqual(tasks.state(self.root.node), tasks.DOING)
            self.cycle()
            self.assertTrue(tasks.done(self.root.node))
        self.assertFalse(tasks.is_task(child.node))

    def test_inline_cycle_preserves_live_item_cursor_selection_and_typing(self):
        self.view.tasks.setDoingEnabled(True)
        item = self.begin()
        cursor = item.textCursor()
        cursor.setPosition(2)
        cursor.setPosition(6, QtGui.QTextCursor.MoveMode.KeepAnchor)
        item.setTextCursor(cursor)
        before = item.toPlainText()
        for expected in (tasks.TODO, tasks.DOING, tasks.DONE, None):
            self.cycle()
            self.assertIs(self.view.inline.item, item)
            self.assertEqual((item.textCursor().anchor(), item.textCursor().position()), (2, 6))
            self.assertEqual(item.toPlainText(), before)
            self.assertEqual(tasks.state(item.stem.node) if tasks.is_task(item.stem.node) else None, expected)
            if expected is not None:
                self.assertTrue(item.stem.leaf.taskbox.toolTip().startswith(expected.title()))
        self.type('replacement')
        self.assertIn('replacement', item.toPlainText())
        self.key(self.keys.Key_Z, QtCore.Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(item.toPlainText(), before)
        self.key(self.keys.Key_Escape)

    def test_inline_removal_failure_preserves_done_checkbox_cursor_and_child(self):
        child = self.child(self.root, 'Child', 70)
        self.select(self.root)
        self.cycle(); self.cycle()  # Doing disabled: Todo, then Done.
        item = self.begin()
        cursor = item.textCursor(); cursor.setPosition(3); item.setTextCursor(cursor)
        before = child.sceneTransform()
        save = graphydb.Node.save
        def fail(node, *args, **kwargs):
            if kwargs.get('batch') and node['uid'] == child.node['uid']:
                raise OSError('disk full')
            return save(node, *args, **kwargs)
        with mock.patch.object(graphydb.Node, 'save', fail), self.assertLogs(level='ERROR'):
            self.cycle()
        self.assertIs(self.view.inline.item, item)
        self.assertEqual(item.textCursor().position(), 3)
        self.assertTrue(tasks.done(self.root.node))
        self.assertTrue(tasks.done(self.graph.getuid(self.root.node['uid'])))
        self.assertTrue(self.root.leaf.taskbox.isVisible())
        self.assertEqual(child.sceneTransform(), before)

    def test_cycle_no_selection_multiselection_ime_and_repeat_do_nothing(self):
        other = self.child(self.root, 'Other', 90)
        for selected in ([], [self.root, other]):
            self.scene.clearSelection()
            for stem in selected:
                stem.setSelected(True)
            self.graph.clearchanges()
            self.cycle()
            self.assertFalse(self.graph.lastchanges())
        self.select(self.root)
        repeat = QtGui.QKeyEvent(QtCore.QEvent.Type.KeyPress, self.keys.Key_D,
            QtCore.Qt.KeyboardModifier.ControlModifier, '', True)
        self.app.sendEvent(self.view, repeat)
        self.assertFalse(tasks.is_task(self.root.node))
        self.begin()
        self.view.inline.preedit = True
        self.cycle()
        self.assertFalse(tasks.is_task(self.root.node))
        self.view.inline.preedit = False

    def test_new_node_cycle_shares_creation_undo_and_empty_node_cleanup(self):
        self.graph.clearchanges()
        item = self.new()
        self.type('New note')
        self.cycle()
        uid = item.stem.node['uid']
        self.type(' more')
        self.key(self.keys.Key_Escape)
        self.scene.undo()
        self.assertIsNone(self.graph.getuid(uid))
        self.assertFalse(self.graph.lastchanges())
        item = self.new()
        uid = item.stem.node['uid']
        self.cycle()
        self.key(self.keys.Key_Escape)
        self.assertIsNone(self.graph.getuid(uid))
        self.assertFalse(self.graph.lastchanges())

    def test_selected_existing_note_converts_without_editing_and_one_undo_restores(self):
        child = self.child(self.root, 'Child', 80)
        nested = self.child(child, 'Nested', 40)
        original = copy.deepcopy(self.root.node.data)
        origin = self.root.leaf.mapToScene(QtCore.QPointF())
        descendants = {stem.node['uid']: stem.sceneTransform() for stem in (child, nested)}
        self.select(self.root)
        self.graph.clearchanges()
        self.cycle()
        self.assertFalse(self.view.tasks.enabled)
        self.assertIsNone(self.view.inline.item)
        self.assertTrue(tasks.is_task(self.root.node))
        self.assertEqual(tasks.state(self.root.node), tasks.TODO)
        self.assertEqual(self.root.node['content'], original['content'])
        self.assertEqual(self.root.leaf.mapToScene(QtCore.QPointF()), origin)
        for stem in (child, nested):
            self.assertEqual(stem.sceneTransform(), descendants[stem.node['uid']])
            self.assertFalse(tasks.is_task(stem.node))
        self.assertEqual(len({item.get('batch') for _, item in self.graph.lastchanges()}), 1)
        self.root.renew()
        self.assertEqual(self.root.leaf.mapToScene(QtCore.QPointF()), origin)
        for stem in (child, nested):
            self.assertEqual(stem.sceneTransform(), descendants[stem.node['uid']])
        self.scene.undo()
        self.assertFalse(tasks.is_task(self.root.node))
        self.assertEqual(self.root.node['content'], original['content'])
        self.assertEqual(self.root.node['pos'], original['pos'])
        self.assertFalse(self.graph.lastchanges())
        self.assertFalse(self.view.tasks.enabled)

    def test_selected_rotated_left_note_and_hidden_child_keep_positions(self):
        stem = self.child(self.root, 'Left note', -100, flip=-1)
        stem.node['angle'], stem.node['scale'] = 23, .7
        stem.node.save(); stem.renew()
        child = self.child(stem, 'Hidden', 50)
        uid = child.node['uid']
        point = child.mapToScene(QtCore.QPointF())
        child.node['hide'] = True; child.node.save(); stem.renew()
        origin = stem.leaf.mapToScene(QtCore.QPointF())
        self.select(stem)
        self.cycle()
        self.assertAlmostEqual(stem.leaf.mapToScene(QtCore.QPointF()).x(), origin.x())
        self.assertAlmostEqual(stem.leaf.mapToScene(QtCore.QPointF()).y(), origin.y())
        self.assertEqual(stem.node['scale'], .7)
        self.assertEqual(stem.node['angle'], 23)
        node = self.graph.getuid(uid)
        node.discard('hide'); node.save(); self.root.renew()
        revealed = next(s for s in stem.childStems2 if s.node['uid'] == uid)
        self.assertAlmostEqual(revealed.mapToScene(QtCore.QPointF()).x(), point.x())
        self.assertAlmostEqual(revealed.mapToScene(QtCore.QPointF()).y(), point.y())

    def test_selected_task_state_preserved_when_enabling_and_disabling_mode(self):
        for current in (tasks.DOING, tasks.DONE):
            self.view.tasks.setMode(False)
            self.root.node['todo'], self.root.node['todo_done'], self.root.node['todo_state'] = True, current == tasks.DONE, current
            self.root.node.save(); self.root.renew()
            self.select(self.root)
            self.graph.clearchanges()
            self.toggle()
            self.assertEqual(tasks.state(self.root.node), current)
            self.toggle()
            self.assertEqual(tasks.state(self.root.node), current)
            self.assertFalse(self.graph.lastchanges())

    def test_enabling_without_single_selection_only_changes_creation_mode(self):
        child = self.child(self.root, 'Other', 50)
        for selected in ([], [self.root, child]):
            self.view.tasks.setMode(False)
            self.scene.clearSelection()
            for stem in selected:
                stem.setSelected(True)
            self.graph.clearchanges()
            self.toggle()
            self.assertTrue(self.view.tasks.enabled)
            self.assertFalse(tasks.is_task(self.root.node))
            self.assertFalse(tasks.is_task(child.node))
            self.assertFalse(self.graph.lastchanges())

    def test_selected_conversion_save_failure_restores_note_and_mode(self):
        child = self.child(self.root, 'Child', 70)
        original = copy.deepcopy(self.root.node.data)
        child_pos = list(child.node['pos'])
        self.select(self.root)
        self.graph.clearchanges()
        save = graphydb.Node.save
        def fail(node, *args, **kwargs):
            if kwargs.get('batch') and node['uid'] == child.node['uid']:
                raise OSError('disk full')
            return save(node, *args, **kwargs)
        with mock.patch.object(graphydb.Node, 'save', fail), self.assertLogs(level='ERROR'):
            self.cycle()
        self.assertFalse(self.view.tasks.enabled)
        self.assertFalse(tasks.is_task(self.root.node))
        self.assertEqual(self.root.node['pos'], original['pos'])
        self.assertEqual(self.root.node['content'], original['content'])
        self.assertEqual(child.node['pos'], child_pos)
        self.assertIsNone(self.root.leaf.taskbox)
        self.assertFalse(self.graph.lastchanges())

    def test_selected_mixed_note_preserves_image_pixels_and_content_transforms(self):
        image = QtGui.QImage(60, 40, QtGui.QImage.Format.Format_ARGB32)
        image.fill(QtGui.QColor('purple'))
        copied, _ = self.graph.itemFromImage(image)
        source = self.graph.Node('ImageData')
        source.update(next(iter(copied.images.values())))
        source.save()
        self.graph.Edge(self.root.node, 'With', source).save()
        uid = graphydb.generateUUID()
        self.root.node['content'][uid] = {'kind': 'Image', 'sha1': source['sha1'],
            'frame': [1, 0, 0, 0, 1, 0, 20, 80, 1], 'z': 1}
        self.root.node.keyChanged('content'); self.root.node.save(); self.root.renew()
        original = copy.deepcopy(self.root.node['content'])
        source_data = source['data']
        self.select(self.root)
        self.cycle()
        self.assertTrue(tasks.is_task(self.root.node))
        self.assertEqual(self.root.node['content'], original)
        self.assertEqual(self.graph.getuid(source['uid'])['data'], source_data)
        self.assertIsNone(self.view.inline.item)

    def task(self, text='Task'):
        if not self.view.tasks.enabled:
            self.toggle()
        item = self.new()
        self.type(text)
        stem = item.stem
        self.key(self.keys.Key_Escape)
        return stem

    def click_box(self, stem, offset=QtCore.QPoint()):
        self.view.centerOn(stem)
        self.app.processEvents()
        point = self.view.mapFromScene(stem.leaf.taskbox.sceneBoundingRect().center()) + offset
        QtTest.QTest.mouseClick(self.view.viewport(), QtCore.Qt.MouseButton.LeftButton, pos=point)
        self.app.processEvents()

    def test_mode_toggle_preserves_cursor_text_and_existing_checkbox(self):
        item = self.new()
        self.type('Write introduction')
        cursor = item.textCursor(); cursor.setPosition(5); item.setTextCursor(cursor)
        self.toggle()
        self.assertTrue(self.view.tasks.enabled)
        self.assertFalse(tasks.is_task(item.stem.node))
        self.cycle()
        self.assertTrue(tasks.is_task(item.stem.node))
        self.assertIs(self.view.inline.item, item)
        self.assertEqual(item.textCursor().position(), 5)
        self.assertEqual(item.toPlainText(), 'Write introduction')
        self.assertIsNotNone(item.stem.leaf.taskbox)
        self.toggle()
        self.assertFalse(self.view.tasks.enabled)
        self.assertTrue(tasks.is_task(item.stem.node))
        self.assertEqual(item.textCursor().position(), 5)
        self.key(self.keys.Key_Return)
        self.assertFalse(tasks.is_task(self.view.inline.item.stem.node))

    def test_enter_and_tab_make_unchecked_tasks_escape_does_not_exit_mode(self):
        first = self.task('First')
        self.assertTrue(self.view.tasks.enabled)
        self.view.tasks.setDone(first.node['uid'], True)
        self.select(first)
        self.key(self.keys.Key_Return)
        self.type(' edited')
        self.key(self.keys.Key_Return)
        second = self.view.inline.item.stem
        self.assertTrue(tasks.is_task(second.node))
        self.assertFalse(tasks.done(second.node))
        self.assertIs(second.parentStem(), first.parentStem())
        self.type('Second')
        self.key(self.keys.Key_Tab)
        child = self.view.inline.item.stem
        self.assertIs(child.parentStem(), second)
        self.assertTrue(tasks.is_task(child.node))
        self.assertFalse(tasks.done(child.node))
        self.type('Child')
        self.key(self.keys.Key_Escape)
        self.assertTrue(self.view.tasks.enabled)
        self.toggle()
        self.assertFalse(self.view.tasks.enabled)
        self.assertTrue(tasks.done(first.node))

    def test_empty_repeat_newline_paste_and_ime_do_not_create_extra_tasks(self):
        item = self.new(); self.toggle()
        before = len(self.scene.allChildStems())
        self.key(self.keys.Key_Return)
        self.assertEqual(len(self.scene.allChildStems()), before)
        self.assertTrue(self.view.tasks.enabled)
        self.type('One')
        self.key(self.keys.Key_Return, QtCore.Qt.KeyboardModifier.ShiftModifier)
        self.type('Two')
        self.assertEqual(item.toPlainText(), 'One\nTwo')
        QtWidgets.QApplication.clipboard().setText('\nThree\nFour')
        self.key(self.keys.Key_V, QtCore.Qt.KeyboardModifier.ControlModifier)
        self.assertIn('Three\nFour', item.toPlainText())
        repeat = QtGui.QKeyEvent(QtCore.QEvent.Type.KeyPress, self.keys.Key_T, self.toggle_mod, '', True)
        self.app.sendEvent(self.view, repeat)
        self.assertTrue(self.view.tasks.enabled)
        self.view.inline.preedit = True
        self.key(self.keys.Key_Return)
        self.toggle()
        self.assertTrue(self.view.tasks.enabled)
        self.assertEqual(len(self.scene.allChildStems()), before)
        self.view.inline.preedit = False

    def test_failed_text_save_neither_creates_next_task_nor_toggles_mode(self):
        item = self.new(); self.toggle(); self.type('Unsaved')
        before = len(self.scene.allChildStems())
        with mock.patch.object(item.stem.node, 'save', side_effect=OSError('disk full')), self.assertLogs(level='ERROR'):
            self.key(self.keys.Key_Return)
        self.assertIs(self.view.inline.item, item)
        self.assertEqual(len(self.scene.allChildStems()), before)
        self.assertEqual(item.toPlainText(), 'Unsaved')
        self.assertTrue(self.view.tasks.enabled)

    def test_failed_mode_conversion_keeps_live_text_and_mode_off(self):
        item = self.new(); self.type('Keep my draft')
        with mock.patch.object(item.stem.node, 'save', side_effect=OSError('disk full')), self.assertLogs(level='ERROR'):
            self.cycle()
        self.assertFalse(self.view.tasks.enabled)
        self.assertFalse(tasks.is_task(item.stem.node))
        self.assertIs(self.view.inline.item, item)
        self.assertEqual(item.toPlainText(), 'Keep my draft')

    def test_empty_task_click_and_presentation_are_read_only(self):
        item = self.new(); self.toggle()
        before = self.graph.connection.total_changes()
        self.assertFalse(self.view.tasks.setDone(item.stem.node['uid'], True))
        self.assertIs(self.view.inline.item, item)
        self.assertEqual(self.graph.connection.total_changes(), before)
        self.type('Valid')
        self.key(self.keys.Key_Escape)
        self.scene.mode = 'presentation'
        before = self.graph.connection.total_changes()
        self.assertFalse(self.view.tasks.setDone(item.stem.node['uid'], True))
        self.assertFalse(self.view.tasks.setMode(False))
        self.assertEqual(self.graph.connection.total_changes(), before)
        self.scene.mode = 'edit'

    def test_new_task_and_text_undo_as_one_creation_then_existing_conversion_undo(self):
        self.graph.clearchanges()
        stem = self.task('New task')
        uid = stem.node['uid']
        self.scene.undo()
        self.assertIsNone(self.graph.getuid(uid))
        self.assertEqual(self.root.childStems2, [])
        self.toggle()  # Mode off, but Undo did not toggle the session mode.
        self.graph.clearchanges()
        item = self.begin()
        original = copy.deepcopy(self.root.node['content'])
        self.cycle()
        self.key(self.keys.Key_Escape)
        self.scene.undo()
        self.assertFalse(tasks.is_task(self.root.node))
        self.assertIsNone(self.root.leaf.taskbox)
        self.assertEqual(self.root.node['content'], original)

    def test_actual_copy_paste_retains_task_status_independent_of_creation_mode(self):
        stem = self.task('Copied task')
        self.view.tasks.setDone(stem.node['uid'], True)
        self.scene.copy()
        self.toggle()
        self.select(self.root)
        self.scene.paste()
        clones = [child for child in self.root.childStems2 if child is not stem]
        self.assertEqual(len(clones), 1)
        self.assertTrue(tasks.done(clones[0].node))
        self.assertIsNotNone(clones[0].leaf.taskbox)

    def test_checkbox_saves_text_undo_is_separate_and_never_drags_or_checks_children(self):
        parent = self.task('Parent')
        child = self.child(parent, 'Child')
        child.node['todo'], child.node['todo_done'] = True, False
        child.node.save(); child.renew()
        self.select(parent)
        self.key(self.keys.Key_Return)
        self.type(' edited')
        before_pos = list(parent.node['pos'])
        self.click_box(parent)
        self.assertTrue(tasks.done(parent.node))
        self.assertFalse(tasks.done(child.node))
        self.assertIsNone(self.view.inline.item)
        self.assertEqual(parent.node['pos'], before_pos)
        self.assertTrue(parent.isSelected())
        source = copy.deepcopy(parent.node['content'])
        self.scene.undo()
        self.assertFalse(tasks.done(parent.node))
        self.assertEqual(parent.node['content'], source)
        self.click_box(parent)
        self.click_box(parent)
        self.assertFalse(tasks.done(parent.node))

    def test_completion_does_not_change_source_fonts_and_does_not_refresh_descendants(self):
        stem = self.task('Formatted')
        self.child(stem, 'Nested')
        before = copy.deepcopy(stem.node['content'])
        with mock.patch.object(stem, 'renew', side_effect=AssertionError('subtree renewed')):
            self.assertTrue(self.view.tasks.setDone(stem.node['uid'], True))
            self.app.processEvents()
        self.assertEqual(stem.node['content'], before)
        self.assertEqual(self.graph.getuid(stem.node['uid'])['content'], before)
        self.assertTrue(tasks.done(stem.node))

    def test_conversion_and_later_text_have_independent_map_undo(self):
        self.graph.clearchanges()
        original = copy.deepcopy(self.root.node['content'])
        self.begin(); self.type(' first'); self.view.inline.checkpoint()
        self.cycle(); self.type(' second')
        self.key(self.keys.Key_Escape)
        self.assertTrue(tasks.is_task(self.root.node))
        self.scene.undo()
        self.assertTrue(tasks.is_task(self.root.node))
        self.assertEqual(self.root.node['content'], original)
        self.scene.undo()
        self.assertFalse(tasks.is_task(self.root.node))
        self.assertEqual(self.root.node['content'], original)

    def test_checkbox_save_failure_retains_active_text_and_does_not_complete(self):
        stem = self.task('Original')
        self.select(stem); self.key(self.keys.Key_Return); self.type(' unsaved')
        item = self.view.inline.item
        with mock.patch.object(stem.node, 'save', side_effect=OSError('disk full')), self.assertLogs(level='ERROR'):
            self.click_box(stem)
        self.assertIs(self.view.inline.item, item)
        self.assertIs(self.scene.focusItem(), item)
        self.assertFalse(tasks.done(stem.node))
        self.assertIn('unsaved', item.toPlainText())

    def test_small_checkbox_has_screen_hit_target_and_status_save_failure_is_safe(self):
        stem = self.task('Small task')
        self.view.scale(.25, .25)
        self.click_box(stem, QtCore.QPoint(-7, 0))
        self.assertTrue(tasks.done(stem.node))
        with mock.patch.object(graphydb.Node, 'save', side_effect=OSError('disk full')), self.assertLogs(level='ERROR'):
            self.assertFalse(self.view.tasks.setDone(stem.node['uid'], False))
        self.assertTrue(tasks.done(stem.node))
        self.assertTrue(tasks.done(self.graph.getuid(stem.node['uid'])))

    def test_persistence_copy_delete_undo_and_new_window_starts_mode_off(self):
        stem = self.task('Persisted')
        self.view.tasks.setDone(stem.node['uid'], True)
        uid = stem.node['uid']
        graph = nexusgraph.NexusGraph(self.graph.path)
        try:
            self.assertTrue(tasks.done(graph.getuid(uid)))
        finally:
            graph.close()
        copied = self.graph.copyTrees(graphydb.NSet([stem.node]))
        self.assertTrue(copied.nodes[0]['todo_done'])
        self.scene.delete(); self.scene.undo()
        restored = self.scene.visibleStemsById()[uid]
        self.assertTrue(tasks.done(restored.node))
        self.assertIsNotNone(restored.leaf.taskbox)
        from nexus.graphics import NexusView
        other = NexusView(self.scene)
        try:
            self.assertFalse(other.tasks.enabled)
        finally:
            other.deleteLater(); self.app.processEvents()

    def test_pdf_svg_and_plain_text_export_include_checkbox_without_mutating_content(self):
        stem = self.task('Export me')
        self.view.tasks.setDone(stem.node['uid'], True)
        content = copy.deepcopy(stem.node['content'])
        self.assertEqual(tasks.export_title(stem), '[x] Export me')
        self.scene.clearSelection()
        svg_path = str(Path(self.tmp.name) / 'tasks.svg')
        svg = QtSvg.QSvgGenerator(); svg.setFileName(svg_path)
        rect = self.scene.itemsBoundingRect()
        svg.setViewBox(rect.toRect())
        painter = QtGui.QPainter(svg); self.scene.render(painter); painter.end()
        self.assertIn('#287747', Path(svg_path).read_text())
        pdf_path = str(Path(self.tmp.name) / 'tasks.pdf')
        pdf = QtGui.QPdfWriter(pdf_path)
        painter = QtGui.QPainter(pdf); self.scene.render(painter); painter.end()
        self.assertGreater(Path(pdf_path).stat().st_size, 500)
        self.assertEqual(stem.node['content'], content)


class DoingTaskTests(unittest.TestCase):
    setUpClass = classmethod(TaskTests.setUpClass.__func__)
    tearDownClass = classmethod(TaskTests.tearDownClass.__func__)
    tearDown = TaskTests.tearDown
    new, begin, type, key = TaskTests.new, TaskTests.begin, TaskTests.type, TaskTests.key
    select, child, node = TaskTests.select, TaskTests.child, TaskTests.node
    toggle, cycle, task, click_box = TaskTests.toggle, TaskTests.cycle, TaskTests.task, TaskTests.click_box
    keys, toggle_mod = TaskTests.keys, TaskTests.toggle_mod

    def setUp(self):
        inline_tests.InlineTests.setUp(self)
        QtCore.QSettings('Ectropy', 'Nexus').remove('todoDoingEnabled')

    def test_default_mouse_cycle_todo_doing_done_todo_and_undo(self):
        stem = self.task('Work')
        content = copy.deepcopy(stem.node['content'])
        self.assertTrue(tasks.doing_enabled())
        self.click_box(stem)
        self.assertEqual(tasks.state(stem.node), tasks.DOING)
        self.assertFalse(tasks.done(stem.node))
        self.click_box(stem)
        self.assertEqual(tasks.state(stem.node), tasks.DONE)
        self.click_box(stem)
        self.assertEqual(tasks.state(stem.node), tasks.TODO)
        self.scene.undo()
        self.assertEqual(tasks.state(stem.node), tasks.DONE)
        self.scene.undo()
        self.assertEqual(tasks.state(stem.node), tasks.DOING)
        self.assertEqual(stem.node['content'], content)

    def test_setting_off_skips_doing_but_keeps_existing_progress_and_survives_reopen(self):
        stem = self.task('In progress'); self.click_box(stem)
        before = self.graph.connection.total_changes()
        self.view.tasks.setDoingEnabled(False)
        self.assertEqual(self.graph.connection.total_changes(), before)
        self.assertEqual(tasks.state(stem.node), tasks.DOING)
        graph = nexusgraph.NexusGraph(self.graph.path)
        try:
            self.assertEqual(tasks.state(graph.getuid(stem.node['uid'])), tasks.DOING)
        finally:
            graph.close()
        self.click_box(stem)
        self.assertEqual(tasks.state(stem.node), tasks.DONE)
        self.click_box(stem)
        self.assertEqual(tasks.state(stem.node), tasks.TODO)
        self.click_box(stem)
        self.assertEqual(tasks.state(stem.node), tasks.DONE)

    def test_doing_copies_exports_yellow_and_new_tasks_start_unchecked(self):
        stem = self.task('Doing now'); self.click_box(stem)
        self.assertEqual(tasks.export_title(stem), '[-] Doing now')
        copied = self.graph.copyTrees(graphydb.NSet([stem.node]))
        self.assertEqual(copied.nodes[0]['todo_state'], tasks.DOING)
        self.select(stem); self.key(self.keys.Key_Return); self.type(' updated'); self.key(self.keys.Key_Return)
        self.assertEqual(tasks.state(self.view.inline.item.stem.node), tasks.TODO)
        self.key(self.keys.Key_Escape)
        path = str(Path(self.tmp.name) / 'doing.svg')
        svg = QtSvg.QSvgGenerator(); svg.setFileName(path); svg.setViewBox(self.scene.itemsBoundingRect().toRect())
        painter = QtGui.QPainter(svg); self.scene.render(painter); painter.end()
        self.assertIn('#ffe391', Path(path).read_text())

    def test_legacy_tasks_need_no_migration_and_state_failure_rolls_back(self):
        self.assertEqual(tasks.state({'todo': True, 'todo_done': True}), tasks.DONE)
        self.assertEqual(tasks.state({'todo': True, 'todo_done': False}), tasks.TODO)
        stem = self.task('Fail safely')
        with mock.patch.object(graphydb.Node, 'save', side_effect=OSError('disk full')), self.assertLogs(level='ERROR'):
            self.assertFalse(self.view.tasks.cycle(stem.node['uid']))
        self.assertEqual(tasks.state(stem.node), tasks.TODO)
        self.assertEqual(tasks.state(self.graph.getuid(stem.node['uid'])), tasks.TODO)
