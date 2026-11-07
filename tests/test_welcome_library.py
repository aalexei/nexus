"""Starred/library controls and recoverable deletion of temporary maps only."""
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from PyQt6 import QtCore, QtGui, QtTest, QtWidgets
from nexus import welcome, map_finder
import test_welcome


class WelcomeLibraryTests(unittest.TestCase):
    setUpClass = classmethod(test_welcome.WelcomeTests.setUpClass.__func__)
    tearDownClass = classmethod(test_welcome.WelcomeTests.tearDownClass.__func__)

    def setUp(self):
        self.startPatch = mock.patch.object(welcome.NewOrOpenDialog, 'startDiscovery')
        self.startPatch.start()
        test_welcome.WelcomeTests.setUp(self)

    def tearDown(self):
        self.startPatch.stop()
        test_welcome.WelcomeTests.tearDown(self)

    def star(self):
        self.dialog.pin(self.path)

    def indexed(self):
        self.dialog._sources['spotlight'] = [map_finder.map_entry(self.path)]
        self.dialog.tabs.setCurrentIndex(1)
        self.app.processEvents()

    def test_starred_is_a_separate_tab_and_unstar_does_not_delete(self):
        self.star()
        self.dialog.tabs.setCurrentIndex(2)
        self.assertEqual(self.dialog.tabs.tabText(2), 'Starred')
        self.assertEqual(self.dialog.currentPath(), self.path)
        self.dialog.pin(self.path)
        self.assertEqual(self.dialog.listWidget.count(), 0)
        self.assertIn('No starred maps', self.dialog.empty.text())
        self.assertTrue(Path(self.path).is_file())

    def test_starred_query_survives_switching_and_remove_recent_keeps_star(self):
        self.star()
        self.dialog.remove(self.path)
        self.assertEqual(self.dialog.listWidget.count(), 0)
        self.assertEqual(welcome.history()[1], [self.path])
        self.dialog.tabs.setCurrentIndex(2)
        self.dialog.search.setText('ideas')
        self.dialog.tabs.setCurrentIndex(0)
        self.dialog.tabs.setCurrentIndex(2)
        self.assertEqual(self.dialog.search.text(), 'ideas')
        self.assertEqual(self.dialog.currentPath(), self.path)

    def test_routine_discovery_info_is_hidden_but_failure_is_visible(self):
        self.indexed()
        self.assertFalse(self.dialog.discoveryStatus.isVisible())
        self.assertEqual(self.dialog.discoveryStatus.text(), '')
        self.dialog._notices['spotlight'] = 'Could not search this folder.'
        self.dialog.renderMac()
        self.assertTrue(self.dialog.discoveryStatus.isVisible())
        self.assertIn('Could not search', self.dialog.discoveryStatus.text())
        self.assertNotIn('Indexed files only', self.dialog.discoveryStatus.text())

    def test_cancel_keeps_file_history_and_results_unchanged(self):
        self.star()
        self.indexed()
        before = welcome.history()
        with mock.patch.object(self.dialog, 'confirmTrash', return_value=False), \
                mock.patch.object(QtCore.QFile, 'moveToTrash') as moved:
            self.dialog.trashMap(self.path)
            moved.assert_not_called()
        self.assertTrue(Path(self.path).is_file())
        self.assertEqual(welcome.history(), before)
        self.assertEqual(self.dialog.listWidget.count(), 1)

    def test_failed_trash_keeps_file_history_and_results(self):
        self.star()
        self.indexed()
        before = welcome.history()
        with mock.patch.object(self.dialog, 'confirmTrash', return_value=True), \
                mock.patch.object(QtCore.QFile, 'moveToTrash', return_value=(False, None)):
            self.dialog.trashMap(self.path)
        self.assertTrue(Path(self.path).is_file())
        self.assertEqual(welcome.history(), before)
        self.assertEqual(self.dialog.listWidget.count(), 1)
        self.assertIn('Could not move', self.dialog.message.text())

    def test_success_removes_only_that_map_from_all_sources_and_rejects_late_results(self):
        self.star()
        self.indexed()
        entry = self.dialog._sources['spotlight'][0]
        job = map_finder.DiscoveryJob()
        self.dialog._jobs['spotlight'] = job
        # Simulate a recoverable move to a private test folder, not user Trash.
        destination = Path(self.tmp.name) / 'private-test-trash.nex'
        def move(path):
            Path(path).rename(destination)
            return True, str(destination)
        with mock.patch.object(self.dialog, 'confirmTrash', return_value=True), \
                mock.patch.object(QtCore.QFile, 'moveToTrash', side_effect=move) as moved:
            self.dialog.trashMap(self.path)
            moved.assert_called_once_with(self.path)
        self.assertFalse(Path(self.path).exists())
        self.assertTrue(destination.exists())
        self.assertEqual(welcome.history(), ([], []))
        self.assertEqual(self.dialog.listWidget.count(), 0)
        self.dialog.discoveryFinished({'scope': 'spotlight', 'token': job.token,
            'entries': [entry], 'error': '', 'notice': '', 'cancelled': False})
        self.assertEqual(self.dialog.listWidget.count(), 0)
        self.assertIn('restore', self.dialog.message.text())

    def test_open_map_is_not_trashed(self):
        window = SimpleNamespace(scene=SimpleNamespace(graph=SimpleNamespace(path=self.path)))
        with mock.patch.object(self.app, 'windowList', return_value=[window], create=True), \
                mock.patch.object(self.dialog, 'confirmTrash') as confirmation, \
                mock.patch.object(QtCore.QFile, 'moveToTrash') as moved:
            self.dialog.trashMap(self.path)
            confirmation.assert_not_called()
            moved.assert_not_called()
        self.assertIn('Close this map', self.dialog.message.text())

    def test_replaced_file_during_confirmation_is_not_trashed(self):
        original = Path(self.path)
        def replace(path):
            original.rename(original.with_suffix('.original-backup'))
            original.touch()
            return True
        with mock.patch.object(self.dialog, 'confirmTrash', side_effect=replace), \
                mock.patch.object(QtCore.QFile, 'moveToTrash') as moved:
            self.dialog.trashMap(self.path)
            moved.assert_not_called()
        self.assertIn('file changed', self.dialog.message.text())
        self.assertTrue(original.exists())

    def test_directory_missing_file_and_symlink_targets_are_rejected(self):
        directory = Path(self.tmp.name) / 'directory.nex'
        directory.mkdir()
        link = Path(self.tmp.name) / 'link.nex'
        link.symlink_to(self.path)
        with mock.patch.object(self.dialog, 'confirmTrash') as confirmation, \
                mock.patch.object(QtCore.QFile, 'moveToTrash') as moved:
            for path in (str(directory), str(link), str(directory / 'missing.nex')):
                self.dialog.trashMap(path)
            confirmation.assert_not_called()
            moved.assert_not_called()
        self.assertTrue(Path(self.path).exists())

    def test_bin_and_star_clicks_are_distinct_and_do_not_open_map(self):
        rect = self.dialog.listWidget.visualItemRect(self.dialog.listWidget.item(0))
        star = QtCore.QPoint(rect.right() - 48, rect.center().y())
        trash = QtCore.QPoint(rect.right() - 16, rect.center().y())
        with mock.patch.object(self.app, 'raiseOrOpen', create=True) as opened, \
                mock.patch.object(self.dialog, 'confirmTrash', return_value=False) as confirm:
            QtTest.QTest.mouseClick(self.dialog.listWidget.viewport(), QtCore.Qt.MouseButton.LeftButton, pos=star)
            self.assertEqual(welcome.history()[1], [self.path])
            QtTest.QTest.mouseClick(self.dialog.listWidget.viewport(), QtCore.Qt.MouseButton.LeftButton, pos=trash)
            confirm.assert_called_once_with(self.path)
            opened.assert_not_called()

    def test_bin_double_click_and_drag_off_do_not_delete_or_open(self):
        rect = self.dialog.listWidget.visualItemRect(self.dialog.listWidget.item(0))
        trash = QtCore.QPoint(rect.right() - 16, rect.center().y())
        with mock.patch.object(self.app, 'raiseOrOpen', create=True) as opened, \
                mock.patch.object(self.dialog, 'confirmTrash', return_value=False) as confirm:
            QtTest.QTest.mousePress(self.dialog.listWidget.viewport(), QtCore.Qt.MouseButton.LeftButton, pos=trash)
            QtTest.QTest.mouseRelease(self.dialog.listWidget.viewport(), QtCore.Qt.MouseButton.LeftButton, pos=rect.center())
            confirm.assert_not_called()
            QtTest.QTest.mouseDClick(self.dialog.listWidget.viewport(), QtCore.Qt.MouseButton.LeftButton, pos=trash)
            opened.assert_not_called()

    def test_confirmation_shows_filename_path_and_defaults_to_cancel(self):
        with mock.patch.object(QtWidgets.QMessageBox, 'exec', return_value=0):
            self.assertFalse(self.dialog.confirmTrash(self.path))
        box = self.dialog.findChildren(QtWidgets.QMessageBox)[-1]
        self.assertIn(Path(self.path).name, box.text())
        self.assertIn(self.path, box.informativeText())
        self.assertEqual(box.textFormat(), QtCore.Qt.TextFormat.PlainText)
        self.assertEqual(box.standardButton(box.defaultButton()), QtWidgets.QMessageBox.StandardButton.Cancel)
        self.assertIs(box.escapeButton(), box.defaultButton())

    @unittest.skipUnless(sys.platform == 'darwin', 'Native macOS Trash check')
    def test_native_trash_api_on_disposable_file_then_restore(self):
        # Real macOS API, exclusively this fixture's empty temporary map. Put
        # it back immediately; no personal map is deleted or left in Trash.
        success, destination = QtCore.QFile.moveToTrash(self.path)
        self.assertTrue(success)
        try:
            self.assertFalse(Path(self.path).exists())
            self.assertTrue(destination and Path(destination).is_file())
        finally:
            if destination and Path(destination).is_file():
                self.assertTrue(QtCore.QFile.rename(destination, self.path))
        self.assertTrue(Path(self.path).is_file())

    def test_visual_starred_rows(self):
        self.star()
        self.dialog.tabs.setCurrentIndex(2)
        self.app.processEvents()
        destination = os.environ.get('NEXUS_LIBRARY_PREVIEW')
        for dark in (False, True):
            palette = self.dialog.palette()
            palette.setColor(palette.ColorRole.Window, QtGui.QColor('#242528' if dark else '#ffffff'))
            self.dialog.setPalette(palette)
            self.app.processEvents()
            pixmap = self.dialog.grab()
            self.assertFalse(pixmap.isNull())
            if destination:
                self.assertTrue(pixmap.save(destination + ('-dark.png' if dark else '-light.png')))


if __name__ == '__main__':
    unittest.main()
