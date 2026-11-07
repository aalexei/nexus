"""Shortcut discovery/filtering must work without other proposed features."""
import unittest
from PyQt6 import QtCore, QtGui, QtWidgets, QtTest
from nexus import shortcuts
from pr_test_support import MapTestCase


class ShortcutTests(MapTestCase):
    def setUp(self):
        super().setUp()
        self.owner = QtWidgets.QMainWindow()
        self.owner.viewMenu = self.owner.menuBar().addMenu('View')
        self.owner.newAct = QtGui.QAction('New Map', self.owner)
        self.owner.newAct.setShortcut(QtGui.QKeySequence.StandardKey.New)
        self.owner.show()

    def tearDown(self):
        if hasattr(self.owner, '_shortcut_dialog'):
            self.owner._shortcut_dialog.reject()
        self.owner.hide()
        self.owner.deleteLater()
        super().tearDown()

    def test_existing_actions_are_discovered_without_optional_features(self):
        rows = shortcuts.shortcut_rows(self.owner)
        self.assertTrue(any(row[2] == 'New Map' for row in rows))
        self.assertFalse(any(row[0].startswith('Tasks') for row in rows))
        self.assertFalse(any(row[0] == 'Typing on the map' for row in rows))
        self.assertFalse(any(row[0] == 'Map navigation' for row in rows))

    def test_presentation_bindings_and_platform_labels(self):
        rows = shortcuts.shortcut_rows(self.owner)
        self.assertTrue(any(row[2] == 'Next saved view' for row in rows))
        label = shortcuts.key_label(QtGui.QKeySequence('Ctrl+Z'))
        self.assertIn('Z', label)
        self.assertIn('Cmd+' if shortcuts.sys.platform == 'darwin' else 'Ctrl+', label)

    def test_search_filters_and_empty_state_then_clear_restores_rows(self):
        shortcuts.show_keyboard_shortcuts(self.owner)
        dialog = self.owner._shortcut_dialog
        count = dialog.table.rowCount()
        dialog.search.setText('New Map')
        visible = [row for row in range(count) if not dialog.table.isRowHidden(row)]
        self.assertEqual(len(visible), 1)
        dialog.search.setText('no such command here')
        self.assertFalse(any(not dialog.table.isRowHidden(row) for row in range(count)))
        self.assertFalse(dialog.empty.isHidden())
        dialog.search.clear()
        self.assertEqual(sum(not dialog.table.isRowHidden(row) for row in range(count)), count)

    def test_dialog_is_reused_and_does_not_change_the_map(self):
        before = self.graph.connection.total_changes()
        shortcuts.show_keyboard_shortcuts(self.owner)
        original = self.owner._shortcut_dialog
        original.reject()
        shortcuts.show_keyboard_shortcuts(self.owner)
        self.assertIs(self.owner._shortcut_dialog, original)
        self.assertEqual(self.graph.connection.total_changes(), before)

    def test_optional_navigation_rows_appear_only_when_available(self):
        self.owner.view = type('NavigationView', (), {'arrowTarget': lambda *args: None})()
        rows = shortcuts.shortcut_rows(self.owner)
        self.assertTrue(any(row[0] == 'Map navigation' for row in rows))
        self.assertFalse(any(row[0].startswith('Tasks') for row in rows))


if __name__ == '__main__':
    unittest.main()
