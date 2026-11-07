import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from settings_helpers import isolate_settings
from PyQt6 import QtCore, QtGui, QtWidgets, QtTest
from nexus import welcome


class WelcomeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.settingsIsolation = isolate_settings(cls.directory.name)
        cls.settingsIsolation.start()
        QtCore.QSettings.setDefaultFormat(QtCore.QSettings.Format.IniFormat)
        QtCore.QSettings.setPath(QtCore.QSettings.Format.IniFormat, QtCore.QSettings.Scope.UserScope, cls.directory.name)
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    @classmethod
    def tearDownClass(cls):
        cls.settingsIsolation.stop()
        cls.directory.cleanup()

    def setUp(self):
        welcome.settings().clear()
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str((Path(self.tmp.name) / 'Ideas.nex').resolve())
        Path(self.path).touch()
        welcome.settings().setValue('recentFileList', [self.path])
        self.dialog = welcome.NewOrOpenDialog()
        self.dialog.show()
        self.app.processEvents()

    def tearDown(self):
        self.dialog.hide()
        self.dialog.deleteLater()
        self.app.processEvents()
        self.tmp.cleanup()

    def test_recent_rows_search_and_resume(self):
        self.assertEqual(self.dialog.listWidget.item(0).text(), 'Ideas')
        self.assertEqual(self.dialog.resumePath, self.path)
        self.assertEqual(self.dialog.listWidget.horizontalScrollBarPolicy(), QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.dialog.search.setText('unmatched')
        self.assertTrue(self.dialog.empty.isVisible())
        self.dialog.search.setText('ideas')
        self.assertFalse(self.dialog.listWidget.item(0).isHidden())

    def test_pin_remove_never_deletes_file_and_duplicate_history(self):
        welcome.settings().setValue('recentFileList', [self.path, self.path])
        self.dialog.refresh()
        self.assertEqual(self.dialog.listWidget.count(), 1)
        self.dialog.pin(self.path)
        self.assertEqual(welcome.history()[1], [self.path])
        self.dialog.remove(self.path)
        self.assertTrue(Path(self.path).exists())
        self.assertEqual(self.dialog.listWidget.count(), 0)

    def test_cancel_new_open_stays_visible(self):
        for method, action in (('dialogNew', self.dialog.newmap), ('dialogOpen', self.dialog.openmap)):
            with mock.patch.object(self.app, method, return_value=None, create=True):
                action()
            self.assertTrue(self.dialog.isVisible())
            self.assertEqual(self.dialog.result(), 0)

    def test_keyboard_search_down_enter_opens_once(self):
        with mock.patch.object(self.app, 'raiseOrOpen', return_value=object(), create=True) as opened:
            self.dialog.search.setFocus()
            QtTest.QTest.keyClick(self.dialog.search, QtCore.Qt.Key.Key_Down)
            QtTest.QTest.keyClick(self.dialog.listWidget, QtCore.Qt.Key.Key_Return)
            self.app.processEvents()
            opened.assert_called_once_with(self.path)

    def test_missing_pinned_locate_preserves_pin(self):
        old = str((Path(self.tmp.name) / 'Moved.nex').resolve())
        welcome.settings().setValue('recentFileList', [old])
        welcome.settings().setValue('pinnedMaps', [old])
        self.dialog.refresh()
        self.assertIn('Moved or missing', self.dialog.listWidget.item(0).data(QtCore.Qt.ItemDataRole.UserRole + 1))
        with mock.patch.object(QtWidgets.QFileDialog, 'getOpenFileName', return_value=(self.path, '')):
            self.dialog.locate(old)
        self.assertEqual(welcome.history(), ([self.path], [self.path]))

    def test_stale_temporary_removed_but_real_temporary_maps_remain(self):
        stale = str(Path(tempfile.gettempdir()) / 'nexus-nonexistent-test-map.nex')
        ordinary = '/Users/example/Documents/moved-map.nex'
        welcome.settings().setValue('recentFileList', [stale, ordinary, self.path])
        self.assertEqual(welcome.history()[0], [ordinary, self.path])

    def test_test_mode_does_not_record_opened_map(self):
        prior = self.app.property('nexusTestMode')
        try:
            self.app.setProperty('nexusTestMode', True)
            welcome.record_recent('/some/other/map.nex')
            self.assertEqual(welcome.history()[0], [self.path])
        finally:
            self.app.setProperty('nexusTestMode', prior)

    def test_drop_filter_and_real_drop_open(self):
        mime = QtCore.QMimeData()
        mime.setUrls([QtCore.QUrl.fromLocalFile(self.path), QtCore.QUrl('https://example.com/map.nex')])
        self.assertEqual(self.dialog.dropPaths(mime), [self.path])
        event = QtGui.QDropEvent(QtCore.QPointF(50, 50), QtCore.Qt.DropAction.CopyAction, mime,
                                QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
        with mock.patch.object(self.app, 'raiseOrOpen', return_value=object(), create=True) as opened:
            self.dialog.dropEvent(event)
            opened.assert_called_once_with(self.path)

    def test_failed_open_stays_visible_and_geometry_persists(self):
        with mock.patch.object(self.app, 'dialogOpen', side_effect=OSError('invalid map'), create=True):
            self.dialog.openmap()
        self.assertTrue(self.dialog.isVisible())
        self.assertIn('invalid map', self.dialog.message.text())
        self.dialog.resize(800, 520)
        self.dialog.reject()
        self.assertIsInstance(welcome.settings().value('welcomeGeometry'), QtCore.QByteArray)

    def test_render_light_and_dark_rows(self):
        preview_paths = []
        for name in ('Research notes', 'Weekend ideas', 'Reading list', 'Project outline',
                     'Travel plans', 'Design sketches', 'Meeting notes', 'Quick thoughts'):
            folder = Path(self.tmp.name) / 'Documents'
            folder.mkdir(exist_ok=True)
            path = folder / (name + '.nex')
            path.touch()
            preview_paths.append(str(path))
        welcome.settings().setValue('recentFileList', preview_paths)
        self.dialog.refresh()
        for dark in (False, True):
            palette = QtGui.QPalette()
            palette.setColor(QtGui.QPalette.ColorRole.Window, QtGui.QColor('#20252b' if dark else '#f7f8fa'))
            palette.setColor(QtGui.QPalette.ColorRole.Base, QtGui.QColor('#20252b' if dark else '#f7f8fa'))
            palette.setColor(QtGui.QPalette.ColorRole.Text, QtGui.QColor('#eeeeee' if dark else '#20252b'))
            palette.setColor(QtGui.QPalette.ColorRole.WindowText, QtGui.QColor('#eeeeee' if dark else '#20252b'))
            self.dialog.setPalette(palette)
            self.dialog.listWidget.setCurrentRow(0)
            self.app.processEvents()
            pixmap = self.dialog.grab()
            self.assertFalse(pixmap.isNull())
            if os.environ.get('NEXUS_WELCOME_PREVIEW'):
                pixmap.save(os.environ['NEXUS_WELCOME_PREVIEW'] + ('-dark.png' if dark else '-light.png'))


if __name__ == '__main__':
    unittest.main()
