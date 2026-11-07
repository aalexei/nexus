"""Regression coverage for search, undo focus, reordering and recovery."""
import os
from pathlib import Path
import unittest
from unittest import mock

import apsw
import test_keyboard_navigation as navigation
from PyQt6 import QtCore, QtGui, QtWidgets, QtTest
from nexus import graphics, node_search as workflow, mainwindow


class WorkflowTests(unittest.TestCase):
    setUpClass = classmethod(navigation.KeyboardNavigationTests.setUpClass.__func__)
    tearDownClass = classmethod(navigation.KeyboardNavigationTests.tearDownClass.__func__)
    setUp = navigation.KeyboardNavigationTests.setUp
    tearDown = navigation.KeyboardNavigationTests.tearDown
    node = navigation.KeyboardNavigationTests.node
    child = navigation.KeyboardNavigationTests.child
    select = navigation.KeyboardNavigationTests.select
    selected = navigation.KeyboardNavigationTests.selected
    key = navigation.KeyboardNavigationTests.key

    def test_undo_deleted_branch_restores_selection_subtree_and_keyboard_focus(self):
        branch = self.child(self.root, 'Branch', -150)
        descendant = self.child(branch, 'Descendant')
        sibling = self.child(self.root, 'Sibling', 150)
        uid, child_uid = branch.node['uid'], descendant.node['uid']
        self.select(branch)
        zoom = self.view.transform()
        self.scene.delete()
        self.assertEqual(self.selected(), [sibling])
        self.scene.undo()
        self.assertEqual([s.node['uid'] for s in self.selected()], [uid])
        self.assertIn(child_uid, [s.node['uid'] for s in self.scene.allChildStems()])
        self.assertTrue(self.view.hasFocus())
        self.assertEqual(self.view.transform(), zoom)
        self.key(QtCore.Qt.Key.Key_Right)
        self.assertEqual(self.selected()[0].node['uid'], child_uid)


    def test_undo_multiple_deleted_branches_restores_base_selection(self):
        one = self.child(self.root, 'One', -150)
        two = self.child(self.root, 'Two', 150)
        self.child(one, 'Nested')
        uids = {one.node['uid'], two.node['uid']}
        self.select(one)
        two.setSelected(True)
        self.scene.delete()
        self.scene.undo()
        self.assertEqual({s.node['uid'] for s in self.selected()}, uids)


    def test_undo_creation_selects_parent_and_no_history_is_noop(self):
        self.graph.clearchanges()
        self.select(self.root)
        self.scene.undo()
        self.assertEqual(self.selected(), [self.root])
        self.key(QtCore.Qt.Key.Key_Tab)
        self.select(self.opened[-1])
        self.scene.undo()
        self.assertEqual(self.selected(), [self.root])
        self.assertEqual(self.root.childStems2, [])


    def test_option_arrow_reorders_persists_and_undo_keeps_selected_subtree(self):
        upper = self.child(self.root, 'Upper', -150)
        lower = self.child(self.root, 'Lower', 150)
        grandchild = self.child(lower, 'Grandchild')
        uid = lower.node['uid']
        self.select(lower)
        before = {s.node['uid']: list(s.node['pos']) for s in (upper, lower)}
        zoom = self.view.transform()
        self.view.verticalScrollBar().setFocus()
        event = QtGui.QKeyEvent(QtCore.QEvent.Type.KeyPress, QtCore.Qt.Key.Key_Up,
                               QtCore.Qt.KeyboardModifier.AltModifier | QtCore.Qt.KeyboardModifier.KeypadModifier)
        self.app.sendEvent(self.view.verticalScrollBar(), event)
        self.app.processEvents()
        self.assertLess(lower.leaf.sceneBoundingRect().center().y(), upper.leaf.sceneBoundingRect().center().y())
        self.assertEqual(self.selected(), [lower])
        self.assertIs(grandchild.parentStem(), lower)
        self.assertEqual(self.view.transform(), zoom)
        for s in (upper, lower):
            self.assertEqual(self.graph.getuid(s.node['uid'])['pos'], s.node['pos'])
        self.scene.undo()
        self.assertEqual(self.selected()[0].node['uid'], uid)
        for s in (upper, lower):
            self.assertEqual(s.node['pos'], before[s.node['uid']])


    def test_reordering_boundaries_multiselection_and_modes_are_safe(self):
        upper = self.child(self.root, 'Upper', -150)
        lower = self.child(self.root, 'Lower', 150)
        left = self.child(self.root, 'Left', 0, flip=-1)
        self.select(upper)
        before = self.graph.countchanges()
        self.key(QtCore.Qt.Key.Key_Up, QtCore.Qt.KeyboardModifier.AltModifier)
        self.assertEqual(self.graph.countchanges(), before)
        self.key(QtCore.Qt.Key.Key_Down, QtCore.Qt.KeyboardModifier.AltModifier)
        self.assertEqual(left.node['pos'], [200, 0])
        lower.setSelected(True)
        before = self.graph.countchanges()
        self.key(QtCore.Qt.Key.Key_Down, QtCore.Qt.KeyboardModifier.AltModifier)
        self.assertEqual(self.graph.countchanges(), before)
        self.scene.mode = 'presentation'
        self.scene.reorderBranch(1)
        self.scene.undo()
        self.assertEqual(self.graph.countchanges(), before)


    def search_dialog(self):
        owner = QtWidgets.QWidget()
        owner.scene, owner.view = self.scene, self.view
        self.search_owner = owner
        self.dialog = workflow.NodeSearchDialog(owner)
        self.dialog.show()
        self.dialog.search.setFocus()
        self.app.processEvents()
        return self.dialog


    def test_search_html_duplicates_breadcrumbs_and_hidden_ancestors(self):
        branch = self.child(self.root, 'Parent', -150)
        target = self.child(branch, '<b>Quantum</b> photon', 5000)
        other = self.child(self.root, 'Quantum photon', 150)
        uid = target.node['uid']
        branch.openclose.toggleVisibilities()
        self.root.openclose.toggleVisibilities()
        self.select(self.root)
        zoom = self.view.transform()
        dialog = self.search_dialog()
        dialog.search.setText('PHOTON quantum')
        self.assertEqual(dialog.results.count(), 2)
        rows = [dialog.results.item(i) for i in range(2)]
        row = next(i for i, item in enumerate(rows) if item.data(QtCore.Qt.ItemDataRole.UserRole) == uid)
        self.assertIn('Root label › Parent', rows[row].text())
        dialog.results.setCurrentRow(row)
        QtTest.QTest.keyClick(dialog.search, QtCore.Qt.Key.Key_Return)
        self.app.processEvents()
        self.assertFalse(dialog.isVisible())
        self.assertEqual([s.node['uid'] for s in self.selected()], [uid])
        self.assertEqual(self.view.transform(), zoom)
        self.assertTrue(self.view.hasFocus())
        # Only the target's path is expanded, not every sibling.
        self.assertIn('hide', self.graph.getuid(other.node['uid']))


    def test_search_empty_no_matches_arrow_choice_and_escape_preserve_selection(self):
        self.child(self.root, 'Match A', -150)
        self.child(self.root, 'Match B', 150)
        self.select(self.root)
        dialog = self.search_dialog()
        self.assertEqual(dialog.results.count(), 0)
        dialog.search.setText('not present')
        self.assertEqual(dialog.results.count(), 0)
        QtTest.QTest.keyClick(dialog.search, QtCore.Qt.Key.Key_Return)
        self.assertTrue(dialog.isVisible())
        dialog.search.setText('Match')
        QtTest.QTest.keyClick(dialog.search, QtCore.Qt.Key.Key_Down)
        self.assertEqual(dialog.results.currentRow(), 1)
        QtTest.QTest.keyClick(dialog.search, QtCore.Qt.Key.Key_Escape)
        self.app.processEvents()
        self.assertEqual(self.selected(), [self.root])


    def test_search_background_translucent_and_heading_draggable(self):
        dialog = self.search_dialog()
        self.assertEqual(dialog.windowModality(), QtCore.Qt.WindowModality.NonModal)
        self.assertTrue(dialog.windowFlags() & QtCore.Qt.WindowType.Tool)
        image = dialog.grab().toImage()
        self.assertEqual(image.pixelColor(0, 0).alpha(), 0)
        scale = image.devicePixelRatio()
        alpha = image.pixelColor(int(10 * scale), int(100 * scale)).alpha()
        self.assertGreater(alpha, 180)
        self.assertLess(alpha, 245)
        before = dialog.pos()
        origin = dialog.heading.rect().center()
        QtTest.QTest.mousePress(dialog.heading, QtCore.Qt.MouseButton.LeftButton, pos=origin)
        event = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove, QtCore.QPointF(origin),
            QtCore.QPointF(dialog.heading.mapToGlobal(origin) + QtCore.QPoint(20, 15)),
            QtCore.Qt.MouseButton.NoButton, QtCore.Qt.MouseButton.LeftButton,
            QtCore.Qt.KeyboardModifier.NoModifier)
        self.app.sendEvent(dialog.heading, event)
        QtTest.QTest.mouseRelease(dialog.heading, QtCore.Qt.MouseButton.LeftButton, pos=origin)
        self.assertEqual(dialog.pos(), before + QtCore.QPoint(20, 15))
        if os.environ.get('NEXUS_SEARCH_PREVIEW'):
            dialog.grab().save(os.environ['NEXUS_SEARCH_PREVIEW'])
