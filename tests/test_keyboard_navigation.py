"""Qt event regression tests; all map and settings data stays temporary.

Run: QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests -v
"""
import os
import tempfile
import unittest
from settings_helpers import isolate_settings

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt6 import QtCore, QtGui, QtWidgets, QtTest
from nexus import graphics, nexusgraph, graphydb, resources


class KeyboardNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = tempfile.TemporaryDirectory()
        cls.settingsIsolation = isolate_settings(cls.settings.name)
        cls.settingsIsolation.start()
        QtCore.QSettings.setDefaultFormat(QtCore.QSettings.Format.IniFormat)
        QtCore.QSettings.setPath(QtCore.QSettings.Format.IniFormat,
                                 QtCore.QSettings.Scope.UserScope, cls.settings.name)
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        cls.app.setProperty('nexusTestMode', True)

    @classmethod
    def tearDownClass(cls):
        cls.app.setProperty('nexusTestMode', False)
        cls.settingsIsolation.stop()
        cls.settings.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.graph = nexusgraph.NexusGraph(os.path.join(self.tmp.name, 'test.nexus'))
        self.scene = graphics.NexusScene()
        self.scene.graph = self.graph
        node = self.node('Root label')
        self.graph.Edge(self.graph.Node('Root').save(), 'Child', node).save()
        self.root = graphics.StemItem(node, scene=self.scene)
        self.root.renew()
        self.view = graphics.NexusView(self.scene)
        # Legacy map commands remain available with Text mode off. Inline mode
        # has its own real-key regression suite.
        if hasattr(self.view, 'inline'):
            self.view.inline.textMode = False
        self.view.resize(900, 650)
        self.view.show()
        self.view.activateWindow()
        self.view.setFocus()
        self.opened = []
        self.scene.showEditDialog.connect(self.opened.append)
        self.scene.showEditDialog.connect(lambda stem: stem.renew(reload=False))
        self.app.processEvents()

    def tearDown(self):
        if hasattr(self.view, 'inline'):
            self.view.inline.finish()
        if hasattr(self, 'dialog'):
            self.dialog.hide()
            self.dialog.deleteLater()
        self.view.hide()
        self.view.deleteLater()
        self.scene.deleteLater()
        self.app.processEvents()
        self.graph.close()
        self.tmp.cleanup()

    def node(self, text, pos=(0, 0), flip=1):
        return self.graph.Node('Stem', scale=1.0, flip=flip, pos=list(pos),
            content={graphydb.generateUUID(): {'kind': 'Text', 'source': text,
                     'frame': graphics.Transform().tolist(), 'z': 0}}).save()

    def child(self, parent, text, y=0, flip=1):
        node = self.node(text, (200, y), flip)
        self.graph.Edge(parent.node, 'Child', node).save()
        parent.renew()
        return next(s for s in parent.childStems2 if s.node['uid'] == node['uid'])

    def select(self, stem):
        self.scene.clearSelection()
        stem.setSelected(True)

    def selected(self):
        return [s for s in self.scene.selectedItems() if isinstance(s, graphics.StemItem)]

    def key(self, key, modifiers=QtCore.Qt.KeyboardModifier.NoModifier):
        QtTest.QTest.keyClick(self.view, key, modifiers)
        self.app.processEvents()

    def test_delete_selects_next_sibling_and_keyboard_navigation_continues(self):
        upper = self.child(self.root, 'Upper', -150)
        middle = self.child(self.root, 'Middle', 0)
        lower = self.child(self.root, 'Lower', 150)
        descendant = self.child(middle, 'Descendant')
        removed = {middle.node['uid'], descendant.node['uid']}
        self.view.fitInView(self.scene.itemsBoundingRect().adjusted(-100, -100, 100, 100),
                            QtCore.Qt.AspectRatioMode.KeepAspectRatio)
        self.select(middle)
        zoom = self.view.transform()
        scroll = self.scroll_position()
        self.view.verticalScrollBar().setFocus()
        delete_action = QtGui.QAction('Delete', self.view)
        delete_action.setShortcuts([QtGui.QKeySequence.StandardKey.Delete,
                                    QtGui.QKeySequence.StandardKey.Backspace])
        delete_action.triggered.connect(self.scene.delete)
        self.view.addAction(delete_action)
        delete_key = (QtCore.Qt.Key.Key_Backspace if QtGui.QKeySequence.keyBindings(
                      QtGui.QKeySequence.StandardKey.Backspace) else QtCore.Qt.Key.Key_Delete)
        QtTest.QTest.keyClick(self.view.viewport(), delete_key)
        self.app.processEvents()
        self.assertEqual(self.selected(), [lower])
        self.assertTrue(self.view.hasFocus())
        self.assertEqual(self.view.transform(), zoom)
        self.assertEqual(self.scroll_position(), scroll)
        remaining = {n['uid'] for n in self.graph.fetch('[n:Stem]')}
        self.assertTrue(removed.isdisjoint(remaining))
        self.key(QtCore.Qt.Key.Key_Up)
        self.assertEqual(self.selected(), [upper])
        self.key(QtCore.Qt.Key.Key_Return)
        self.assertEqual(self.opened[-1], upper)
        self.graph.undo()
        self.root.renew()
        restored = {n['uid'] for n in self.graph.fetch('[n:Stem]')}
        self.assertTrue(removed.issubset(restored))

    def test_delete_last_sibling_then_only_child_selects_previous_then_parent(self):
        upper = self.child(self.root, 'Upper', -150)
        lower = self.child(self.root, 'Lower', 150)
        self.select(lower)
        self.scene.delete()
        self.assertEqual(self.selected(), [upper])
        self.scene.delete()
        self.assertEqual(self.selected(), [self.root])
        self.assertEqual(self.root.childStems2, [])

    def test_delete_skips_hidden_siblings_and_other_selected_branches(self):
        first = self.child(self.root, 'First', -150)
        hidden = self.child(self.root, 'Hidden', 0)
        second = self.child(self.root, 'Second', 150)
        survivor = self.child(self.root, 'Survivor', 300)
        hidden.hide()
        self.select(first)
        second.setSelected(True)
        self.scene.delete()
        self.assertEqual(self.selected(), [survivor])
        self.assertFalse(hidden.isVisible())

    def test_delete_selected_parent_and_child_has_one_surviving_destination(self):
        branch = self.child(self.root, 'Branch', -150)
        descendant = self.child(branch, 'Descendant')
        next_branch = self.child(self.root, 'Next', 150)
        self.select(branch)
        descendant.setSelected(True)
        self.scene.delete()
        self.assertEqual(self.selected(), [next_branch])
        self.assertEqual(self.root.childStems2, [next_branch])

    def test_context_delete_reveals_destination_without_changing_zoom(self):
        near = self.child(self.root, 'Near', 0)
        far = self.child(self.root, 'Far', 2000)
        self.view.centerOn(near)
        zoom = self.view.transform()
        before = self.scroll_position()
        self.scene.delete(stem=near)
        self.assertEqual(self.selected(), [far])
        self.assertEqual(self.view.transform(), zoom)
        self.assertNotEqual(self.scroll_position(), before)
        visible = self.view.mapToScene(self.view.viewport().rect()).boundingRect()
        self.assertTrue(visible.contains(far.leaf.sceneBoundingRect()))

    def test_cut_uses_same_fallback_and_no_selection_delete_is_noop(self):
        upper = self.child(self.root, 'Upper', -150)
        lower = self.child(self.root, 'Lower', 150)
        self.scene.delete()
        self.assertEqual(self.selected(), [])
        self.assertEqual(len(self.root.childStems2), 2)
        self.select(upper)
        clipboard = self.app.clipboard()
        backup = QtCore.QMimeData()
        original = clipboard.mimeData()
        if original is not None:
            for format_name in original.formats():
                backup.setData(format_name, original.data(format_name))
        try:
            self.scene.cut()
            self.assertEqual(self.selected(), [lower])
        finally:
            clipboard.setMimeData(backup)

    def test_tab_root_fallback_and_child_creation(self):
        self.key(QtCore.Qt.Key.Key_Tab)
        self.assertEqual(len(self.opened), 1)
        child = self.opened[-1]
        self.assertIs(child.parentStem(), self.root)
        self.select(child)
        self.key(QtCore.Qt.Key.Key_Tab)
        self.assertIs(self.opened[-1].parentStem(), child)

    def test_zoom_parent_fits_visible_branch_and_climbs_to_root(self):
        branch = self.child(self.root, 'Branch')
        upper = self.child(branch, 'Upper', -200)
        lower = self.child(branch, 'Hidden lower', 5000)
        unrelated = self.child(self.root, 'Other branch', -2000)
        lower.hide()
        self.select(upper)
        self.view.zoomParent()
        self.assertEqual(self.selected(), [branch])
        visible = self.view.mapToScene(self.view.viewport().rect()).boundingRect()
        self.assertTrue(visible.contains(branch.sceneBoundingRect()))
        self.assertTrue(visible.contains(upper.sceneBoundingRect()))
        self.assertFalse(visible.contains(lower.sceneBoundingRect()))
        self.assertFalse(lower.isVisible())
        branch_zoom = self.view.transform().m11()
        self.view.zoomParent()
        self.assertEqual(self.selected(), [self.root])
        self.assertLess(self.view.transform().m11(), branch_zoom)
        visible = self.view.mapToScene(self.view.viewport().rect()).boundingRect()
        self.assertTrue(visible.contains(unrelated.sceneBoundingRect()))
        root_zoom = self.view.transform()
        self.view.zoomParent()
        self.assertEqual(self.selected(), [self.root])
        self.assertEqual(self.view.transform(), root_zoom)

    def test_zoom_parent_requires_one_node_in_map_edit_mode(self):
        child = self.child(self.root, 'Child')
        before = self.view.transform()
        self.view.zoomParent()
        self.assertEqual(self.selected(), [])
        self.root.setSelected(True)
        child.setSelected(True)
        self.view.zoomParent()
        self.assertEqual(len(self.selected()), 2)
        self.select(child)
        self.scene.mode = 'presentation'
        self.view.zoomParent()
        self.assertEqual(self.selected(), [child])
        self.assertEqual(self.view.transform(), before)

    def test_enter_sibling_left_side_and_f2(self):
        left = self.child(self.root, 'Left', flip=-1)
        self.select(left)
        self.key(QtCore.Qt.Key.Key_Return, QtCore.Qt.KeyboardModifier.ShiftModifier)
        sibling = self.opened[-1]
        self.assertIs(sibling.parentStem(), self.root)
        self.assertEqual(sibling.direction(), -1)
        self.select(left)
        self.key(QtCore.Qt.Key.Key_Return)
        self.assertIs(self.opened[-1], left)
        self.select(self.root)
        self.key(QtCore.Qt.Key.Key_Return, QtCore.Qt.KeyboardModifier.ShiftModifier)
        self.assertIs(self.opened[-1].parentStem(), self.root)

    def test_viewport_arrows_navigate_without_default_scroll(self):
        upper = self.child(self.root, 'Upper', -30)
        lower = self.child(self.root, 'Lower', 30)
        self.view.fitInView(self.scene.itemsBoundingRect(), QtCore.Qt.AspectRatioMode.KeepAspectRatio)
        self.select(upper)
        # Real viewport delivery also exercises QAbstractScrollArea forwarding.
        QtTest.QTest.keyClick(self.view.viewport(), QtCore.Qt.Key.Key_Down)
        self.app.processEvents()
        self.assertEqual(self.selected(), [lower])
        before = (self.view.horizontalScrollBar().value(), self.view.verticalScrollBar().value())
        QtTest.QTest.keyClick(self.view.viewport(), QtCore.Qt.Key.Key_Down)
        self.app.processEvents()
        self.assertEqual(self.selected(), [lower])
        self.assertEqual(before, (self.view.horizontalScrollBar().value(), self.view.verticalScrollBar().value()))

    def test_no_selection_only_tab_creates(self):
        for key in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_F2,
                    QtCore.Qt.Key.Key_Space, QtCore.Qt.Key.Key_Right):
            self.key(key)
            self.assertEqual(self.selected(), [])
            self.assertEqual(self.opened, [])

    def test_arrow_hierarchy_order_boundaries_and_repeat(self):
        lower = self.child(self.root, 'Lower', 150)
        upper = self.child(self.root, 'Upper', -150)
        self.select(upper)
        self.key(QtCore.Qt.Key.Key_Up)
        self.assertEqual(self.selected(), [upper])
        repeat = QtGui.QKeyEvent(QtCore.QEvent.Type.KeyPress, QtCore.Qt.Key.Key_Down,
                                QtCore.Qt.KeyboardModifier.NoModifier, '', True)
        self.app.sendEvent(self.view, repeat)
        self.assertEqual(self.selected(), [lower])
        self.key(QtCore.Qt.Key.Key_Down)
        self.assertEqual(self.selected(), [lower])
        self.key(QtCore.Qt.Key.Key_Left)
        self.assertEqual(self.selected(), [self.root])
        self.key(QtCore.Qt.Key.Key_Right)
        self.assertEqual(self.selected(), [upper])

    def test_up_down_cross_branches_and_skip_hidden_nodes(self):
        top = self.child(self.root, 'A long upper branch extending across the child column', -250)
        top_uid = top.node['uid']
        bottom = self.child(self.root, 'Bottom', 200)
        nested = self.child(bottom, 'Nested', -50)
        top = next(s for s in self.root.childStems2 if s.node['uid'] == top_uid)
        self.select(nested)
        zoom = self.view.transform()
        self.key(QtCore.Qt.Key.Key_Up)
        self.assertEqual(self.selected(), [top])
        self.key(QtCore.Qt.Key.Key_Down)
        self.assertEqual(self.selected(), [nested])
        self.assertEqual(self.view.transform(), zoom)
        # Hidden labels must not be selected; no candidate is a safe no-op.
        top.hide()
        self.select(nested)
        self.key(QtCore.Qt.Key.Key_Up)
        self.assertNotEqual(self.selected(), [top])

    def test_space_collapse_right_expand_and_undo(self):
        child = self.child(self.root, 'Child')
        uid = child.node['uid']
        self.select(self.root)
        self.key(QtCore.Qt.Key.Key_Space)
        self.assertEqual(self.root.childStems2, [])
        self.assertTrue(self.graph.getuid(uid).get('hide'))
        self.graph.undo()
        self.root.renew()
        self.assertEqual(len(self.root.childStems2), 1)
        self.key(QtCore.Qt.Key.Key_Space)
        self.key(QtCore.Qt.Key.Key_Right)
        self.assertEqual(self.selected(), [self.root])
        self.assertEqual(len(self.root.childStems2), 1)
        self.key(QtCore.Qt.Key.Key_Right)
        self.assertEqual(self.selected()[0].node['uid'], uid)

    def scroll_position(self):
        return (self.view.horizontalScrollBar().value(), self.view.verticalScrollBar().value())

    def test_focused_scrollbars_route_plain_arrows_to_selection(self):
        upper = self.child(self.root, 'Upper', -30)
        lower = self.child(self.root, 'Lower', 30)
        self.view.fitInView(self.scene.itemsBoundingRect().adjusted(-100, -100, 100, 100),
                            QtCore.Qt.AspectRatioMode.KeepAspectRatio)
        for bar in (self.view.horizontalScrollBar(), self.view.verticalScrollBar()):
            self.select(upper)
            bar.setFocus()
            before = self.scroll_position()
            QtTest.QTest.keyClick(bar, QtCore.Qt.Key.Key_Down)
            self.app.processEvents()
            self.assertEqual(self.selected(), [lower])
            self.assertEqual(self.scroll_position(), before)
            QtTest.QTest.keyClick(bar, QtCore.Qt.Key.Key_Up)
            self.assertEqual(self.selected(), [upper])

    def test_boundary_arrows_do_not_recenter_offscreen_selection(self):
        self.select(self.root)
        self.view.centerOn(1500, 1500)
        before = self.scroll_position()
        for key in (QtCore.Qt.Key.Key_Up, QtCore.Qt.Key.Key_Down,
                    QtCore.Qt.Key.Key_Left, QtCore.Qt.Key.Key_Right):
            self.key(key)
            self.assertEqual(self.scroll_position(), before)
            self.assertEqual(self.selected(), [self.root])

    def test_macos_keypad_flag_on_physical_arrows(self):
        upper = self.child(self.root, 'Upper', -30)
        lower = self.child(self.root, 'Lower', 30)
        self.view.fitInView(self.scene.itemsBoundingRect().adjusted(-100, -100, 100, 100),
                            QtCore.Qt.AspectRatioMode.KeepAspectRatio)
        keypad = QtCore.Qt.KeyboardModifier.KeypadModifier
        for target in (self.view, self.view.viewport(), self.view.horizontalScrollBar(),
                       self.view.verticalScrollBar()):
            self.select(self.root)
            before = self.scroll_position()
            for key, expected in ((QtCore.Qt.Key.Key_Right, upper),
                                  (QtCore.Qt.Key.Key_Down, lower),
                                  (QtCore.Qt.Key.Key_Up, upper),
                                  (QtCore.Qt.Key.Key_Left, self.root)):
                event = QtGui.QKeyEvent(QtCore.QEvent.Type.KeyPress, key, keypad)
                self.app.sendEvent(target, event)
                self.assertEqual(self.selected(), [expected])
                self.assertEqual(self.scroll_position(), before)
            event = QtGui.QKeyEvent(QtCore.QEvent.Type.KeyPress, QtCore.Qt.Key.Key_Right,
                                   keypad | QtCore.Qt.KeyboardModifier.ControlModifier)
            self.app.sendEvent(target, event)
            self.assertEqual(self.scroll_position(), (before[0] + 48, before[1]))
            self.assertEqual(self.selected(), [self.root])

    def test_command_arrows_pan_without_changing_selection_or_geometry(self):
        self.select(self.root)
        zoom = self.view.transform()
        position = list(self.root.node['pos'])
        changes = []
        self.view.viewChangeStream.connect(lambda _: changes.append(True))
        for target in (self.view, self.view.viewport(), self.view.horizontalScrollBar(),
                       self.view.verticalScrollBar()):
            for key, delta in ((QtCore.Qt.Key.Key_Right, (48, 0)),
                               (QtCore.Qt.Key.Key_Left, (-48, 0)),
                               (QtCore.Qt.Key.Key_Down, (0, 48)),
                               (QtCore.Qt.Key.Key_Up, (0, -48))):
                before = self.scroll_position()
                QtTest.QTest.keyClick(target, key, QtCore.Qt.KeyboardModifier.ControlModifier)
                self.app.processEvents()
                self.assertEqual(self.scroll_position(), tuple(a + b for a, b in zip(before, delta)))
                self.assertEqual(self.selected(), [self.root])
        self.assertEqual(len(changes), 16)
        self.assertEqual(self.view.transform(), zoom)
        self.assertEqual(self.root.node['pos'], position)

    def test_plain_scrollbar_arrows_without_single_selection_do_not_pan(self):
        child = self.child(self.root, 'Child')
        for multiple in (False, True):
            self.scene.clearSelection()
            if multiple:
                self.root.setSelected(True)
                child.setSelected(True)
            before = self.scroll_position()
            for key in (QtCore.Qt.Key.Key_Up, QtCore.Qt.Key.Key_Down,
                        QtCore.Qt.Key.Key_Left, QtCore.Qt.Key.Key_Right):
                QtTest.QTest.keyClick(self.view.verticalScrollBar(), key)
                self.assertEqual(self.scroll_position(), before)

    def test_changed_offscreen_selection_is_revealed_once(self):
        child = self.child(self.root, 'Far away', 2000)
        self.select(self.root)
        self.view.centerOn(self.root)
        before = self.scroll_position()
        self.key(QtCore.Qt.Key.Key_Right)
        self.assertEqual(self.selected(), [child])
        self.assertNotEqual(self.scroll_position(), before)
        revealed = self.scroll_position()
        self.key(QtCore.Qt.Key.Key_Down)
        self.assertEqual(self.scroll_position(), revealed)

    def test_multiselection_and_modifiers_do_not_create(self):
        child = self.child(self.root, 'Child')
        self.root.setSelected(True)
        child.setSelected(True)
        for key in (QtCore.Qt.Key.Key_Tab, QtCore.Qt.Key.Key_Return,
                    QtCore.Qt.Key.Key_F2, QtCore.Qt.Key.Key_Space):
            self.key(key)
        self.assertEqual(len(self.selected()), 2)
        self.assertEqual(self.opened, [])

    def test_presentation_bypasses_creation_and_escape_signal(self):
        self.scene.mode = 'presentation'
        escaped = []
        self.view.presentationEscape.connect(lambda: escaped.append(True))
        self.select(self.root)
        self.key(QtCore.Qt.Key.Key_Tab)
        self.key(QtCore.Qt.Key.Key_Return)
        self.assertEqual(self.opened, [])
        self.key(QtCore.Qt.Key.Key_Escape)
        self.assertEqual(escaped, [True])

    def test_editor_blank_close_restores_parent_and_focus(self):
        self.dialog = graphics.InputDialog()
        self.scene.showEditDialog.connect(self.dialog.setDialog)
        self.key(QtCore.Qt.Key.Key_Tab)
        self.assertTrue(self.dialog.isVisible())
        QtTest.QTest.keyClick(self.dialog, QtCore.Qt.Key.Key_Escape)
        self.app.processEvents()
        self.assertFalse(self.dialog.isVisible())
        self.assertEqual(self.selected(), [self.root])
        self.assertEqual(self.root.childStems2, [])
        self.assertTrue(self.view.hasFocus())

    def test_long_label_collision_and_saved_text(self):
        existing = self.child(self.root, 'Existing', 100)
        original_pos = list(existing.node['pos'])
        self.dialog = graphics.InputDialog()
        self.scene.showEditDialog.connect(self.dialog.setDialog)
        self.select(self.root)
        self.key(QtCore.Qt.Key.Key_Tab)
        new = self.dialog.stem
        # Simulate a label whose final size exceeds its initial reservation.
        new.node['pos'] = list(existing.node['pos'])
        new.renew(reload=False)
        self.dialog.setTextMode()
        item = next(i for i in self.dialog.scene.getItems()
                    if isinstance(i, graphics.TextItem))
        item.setPlainText('A much longer label ' * 20)
        item.saveIfChanged()
        new.renew(reload=False)
        self.assertTrue(new.leaf.sceneBoundingRect().intersects(
            existing.leaf.sceneBoundingRect()))
        QtTest.QTest.keyClick(self.dialog, QtCore.Qt.Key.Key_Escape)
        self.app.processEvents()
        current = self.selected()[0]
        self.assertEqual(current.node['uid'], new.node['uid'])
        self.assertEqual(existing.node['pos'], original_pos)
        self.assertFalse(current.leaf.sceneBoundingRect().intersects(
            existing.leaf.sceneBoundingRect()))
        self.assertTrue(any('A much longer label' in x.get('source', '')
                            for x in self.graph.getuid(new.node['uid'])['content'].values()))

    def test_editor_arrows_and_return_do_not_create_map_nodes(self):
        self.dialog = graphics.InputDialog()
        self.dialog.setDialog(self.root)
        self.dialog.setTextMode()
        item = next(i for i in self.dialog.scene.getItems()
                    if isinstance(i, graphics.TextItem))
        item.setFocus()
        for key in (QtCore.Qt.Key.Key_Left, QtCore.Qt.Key.Key_Right):
            QtTest.QTest.keyClick(self.dialog.view, key)
        QtTest.QTest.keyClick(self.dialog.view, QtCore.Qt.Key.Key_Return,
                             QtCore.Qt.KeyboardModifier.ShiftModifier)
        self.app.processEvents()
        self.assertTrue(self.dialog.isVisible())
        self.assertEqual(self.root.childStems2, [])
        self.assertEqual(self.opened, [])


if __name__ == '__main__':
    unittest.main()
