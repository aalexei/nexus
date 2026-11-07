"""Map discovery uses temporary files and mocked Spotlight, never user maps."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PyQt6 import QtCore, QtGui, QtTest, QtWidgets
from nexus import map_finder, welcome
import test_welcome


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()

    def tearDown(self):
        self.tmp.cleanup()

    def file(self, name):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        return path

    def test_extensions_missing_directories_and_recovery_exclusion(self):
        for name in ('Ideas.nex', 'Other.nexus', 'UPPER.NEX'):
            self.assertIsNotNone(map_finder.map_entry(self.file(name)))
        self.assertIsNone(map_finder.map_entry(self.file('not-a-map.txt')))
        self.assertIsNone(map_finder.map_entry(self.root / 'missing.nex'))
        (self.root / 'directory.nex').mkdir()
        self.assertIsNone(map_finder.map_entry(self.root / 'directory.nex'))
        self.assertIsNone(map_finder.map_entry(self.file('.Trash/trashed.nex')))
        recovery = self.file('recovery/snapshot-1.nex')
        self.assertIsNone(map_finder.map_entry(recovery, (recovery.parent,)))

    def test_fuzzy_ranking_exact_prefix_subsequence_and_filename_only(self):
        names = ['Notes about quantum dots.nex', 'Quantum-dots.nex', 'qdts.nex', ' unrelated.nex']
        entries = [map_finder.map_entry(self.file(name)) for name in names]
        results = map_finder.ranked_maps(entries, 'qdts')
        self.assertEqual(results[0]['name'], 'qdts.nex')
        self.assertEqual(results[1]['name'], 'Quantum-dots.nex')
        self.assertEqual(len(results), 3)
        self.assertEqual(map_finder.ranked_maps(entries, self.root.name), [])
        self.assertEqual(map_finder.ranked_maps(entries, 'quantum')[0]['name'], 'Quantum-dots.nex')
        self.assertEqual(map_finder.ranked_maps(entries, 'no-match'), [])

    def test_blank_query_sorts_newest_first_and_aliases_are_deduplicated(self):
        older, newer = self.file('older.nex'), self.file('newer.nex')
        os.utime(older, (10, 10))
        os.utime(newer, (20, 20))
        alias = self.root / 'alias.nex'
        alias.symlink_to(newer)
        job = map_finder.DiscoveryJob()
        with mock.patch.object(job, 'spotlight_paths', return_value=[older, newer, alias]):
            entries, _ = job.discover()
        self.assertEqual(len(entries), 2)
        self.assertEqual(map_finder.ranked_maps(entries, '')[0]['path'], str(newer))

    def test_explicit_folder_scan_is_recursive_and_avoids_symlink_loops_and_caches(self):
        wanted = self.file('project/nested/work.nexus')
        self.file('project/.venv/unwanted.nex')
        self.file('project/ordinary.txt')
        (self.root / 'project/loop').symlink_to(self.root / 'project', target_is_directory=True)
        entries, notice = map_finder.DiscoveryJob(str(self.root / 'project')).discover()
        self.assertEqual([entry['path'] for entry in entries], [str(wanted)])
        self.assertEqual(notice, '')

    def test_spotlight_uses_null_delimiters_and_literal_arguments(self):
        path = self.file("quote' and\nnewline.nex")
        process = mock.Mock(returncode=0)
        process.communicate.return_value = (os.fsencode(str(path)) + b'\0', b'')
        process.poll.return_value = 0
        with mock.patch.object(map_finder.subprocess, 'Popen', return_value=process) as launched:
            entries, _ = map_finder.DiscoveryJob().discover()
        self.assertEqual(entries[0]['path'], str(path))
        self.assertEqual(launched.call_args.args[0], ['/usr/bin/mdfind', '-0', map_finder.SPOTLIGHT_QUERY])
        self.assertNotIn('shell', launched.call_args.kwargs)

    def test_cancel_before_start_does_not_launch_process(self):
        job = map_finder.DiscoveryJob()
        job.cancel()
        results = []
        job.signals.finished.connect(results.append)
        with mock.patch.object(map_finder.subprocess, 'Popen') as launched:
            job.run()
        launched.assert_not_called()
        self.assertTrue(results[0]['cancelled'])

    def test_timeout_terminates_process_and_reports_failure(self):
        process = mock.Mock(returncode=None)
        process.poll.return_value = None
        process.communicate.return_value = (b'', b'')
        job = map_finder.DiscoveryJob()
        results = []
        job.signals.finished.connect(results.append)
        with mock.patch.object(map_finder.subprocess, 'Popen', return_value=process), \
                mock.patch.object(map_finder.time, 'monotonic', side_effect=[0, 16]):
            job.run()
        process.terminate.assert_called_once()
        self.assertIn('too long', results[0]['error'])

    def test_folder_permissions_report_partial_results_without_failure(self):
        path = self.file('readable.nex')
        def walk(root, followlinks, onerror):
            onerror(PermissionError('Not readable'))
            yield str(self.root), [], [path.name]
        with mock.patch.object(map_finder.os, 'walk', side_effect=walk):
            entries, notice = map_finder.DiscoveryJob(str(self.root)).discover()
        self.assertEqual(len(entries), 1)
        self.assertIn('could not be read', notice)


class MapFinderWelcomeTests(unittest.TestCase):
    setUpClass = classmethod(test_welcome.WelcomeTests.setUpClass.__func__)
    tearDownClass = classmethod(test_welcome.WelcomeTests.tearDownClass.__func__)

    def setUp(self):
        self.discoveryPatch = mock.patch.object(welcome.NewOrOpenDialog, 'startDiscovery')
        self.startDiscovery = self.discoveryPatch.start()
        test_welcome.WelcomeTests.setUp(self)

    def tearDown(self):
        self.discoveryPatch.stop()
        test_welcome.WelcomeTests.tearDown(self)
        QtCore.QThreadPool.globalInstance().waitForDone(2000)

    def entries(self, *names):
        result = []
        for name in names:
            path = Path(self.tmp.name) / name
            path.touch()
            result.append(map_finder.map_entry(path))
        return result

    def mac(self, entries):
        self.dialog._sources['spotlight'] = entries
        self.dialog.tabs.setCurrentIndex(1)
        self.app.processEvents()

    def test_discovery_is_lazy_and_tabs_keep_independent_queries_and_selection(self):
        self.startDiscovery.assert_not_called()
        self.dialog.search.setText('ideas')
        self.dialog.listWidget.setCurrentRow(0)
        self.mac(self.entries('quantum-dots.nex', 'qdts.nexus'))
        self.startDiscovery.assert_called_once_with('spotlight')
        self.dialog.search.setText('qdts')
        self.dialog.listWidget.setCurrentRow(1)
        selected = self.dialog.currentPath()
        self.dialog.tabs.setCurrentIndex(0)
        self.assertEqual(self.dialog.search.text(), 'ideas')
        self.assertEqual(self.dialog.currentPath(), self.path)
        self.dialog.tabs.setCurrentIndex(1)
        self.assertEqual(self.dialog.search.text(), 'qdts')
        self.assertEqual(self.dialog.currentPath(), selected)
        self.assertEqual(self.startDiscovery.call_count, 1)

    def test_fuzzy_filename_results_open_once_via_keyboard(self):
        entries = self.entries('Quantum-dots.nex', 'Exact qdts.nexus')
        self.mac(entries)
        self.dialog.search.setText('qdts')
        self.assertEqual(self.dialog.listWidget.count(), 2)
        expected = self.dialog.currentPath()
        with mock.patch.object(self.app, 'raiseOrOpen', return_value=object(), create=True) as opened:
            QtTest.QTest.keyClick(self.dialog.search, QtCore.Qt.Key.Key_Down)
            QtTest.QTest.keyClick(self.dialog.listWidget, QtCore.Qt.Key.Key_Return)
            self.app.processEvents()
            opened.assert_called_once_with(expected)

    def test_tab_switch_restores_scroll_position(self):
        self.mac(self.entries(*(f'Map {index:02}.nex' for index in range(40))))
        self.dialog.listWidget.setCurrentRow(25)
        self.dialog.listWidget.doItemsLayout()
        self.dialog.listWidget.verticalScrollBar().setValue(15)
        self.app.processEvents()
        selected = self.dialog.currentPath()
        scroll = self.dialog.listWidget.verticalScrollBar().value()
        self.assertGreater(scroll, 0)
        self.dialog.tabs.setCurrentIndex(0)
        self.app.processEvents()
        self.dialog.tabs.setCurrentIndex(1)
        self.app.processEvents()
        self.assertEqual(self.dialog.currentPath(), selected)
        self.assertEqual(self.dialog.listWidget.verticalScrollBar().value(), scroll)

    def test_single_click_does_not_open_and_finder_action_uses_literal_path(self):
        entry = self.entries("don't lose this.nex")[0]
        self.mac([entry])
        with mock.patch.object(self.app, 'raiseOrOpen', create=True) as opened:
            rect = self.dialog.listWidget.visualItemRect(self.dialog.listWidget.item(0))
            QtTest.QTest.mouseClick(self.dialog.listWidget.viewport(), QtCore.Qt.MouseButton.LeftButton,
                                   pos=rect.center())
            opened.assert_not_called()
        menu = self.dialog.mapContextMenu(entry['path'])
        labels = [action.text() for action in menu.actions()]
        self.assertIn('Show in Finder', labels)
        self.assertNotIn('Remove from Recent (keep file)', labels)
        with mock.patch.object(QtCore.QProcess, 'startDetached', return_value=True) as shown:
            self.dialog.showInFinder(entry['path'])
            shown.assert_called_once_with('/usr/bin/open', ['-R', entry['path']])

    def test_stale_results_are_rejected_and_errors_keep_previous_maps(self):
        entry = self.entries('Good.nex')[0]
        self.mac([entry])
        job = map_finder.DiscoveryJob()
        self.dialog._jobs['spotlight'] = job
        payload = {'scope': 'spotlight', 'token': 'older-job', 'entries': [],
                   'error': '', 'notice': '', 'cancelled': False}
        self.dialog.discoveryFinished(payload)
        self.assertEqual(self.dialog.listWidget.count(), 1)
        payload.update(token=job.token, error='Spotlight unavailable')
        self.dialog.discoveryFinished(payload)
        self.assertEqual(self.dialog.listWidget.count(), 1)
        self.assertIn('Spotlight unavailable', self.dialog.discoveryStatus.text())

    def test_folder_fallback_cancel_and_pin_do_not_change_tab_or_delete_maps(self):
        entries = self.entries('folder-map.nex')
        self.mac(entries)
        with mock.patch.object(QtWidgets.QFileDialog, 'getExistingDirectory', return_value=''):
            self.dialog.chooseSearchFolder()
        self.assertEqual(self.startDiscovery.call_count, 1)
        with mock.patch.object(QtWidgets.QFileDialog, 'getExistingDirectory', return_value=self.tmp.name):
            self.dialog.chooseSearchFolder()
        self.startDiscovery.assert_called_with(welcome.normalize(self.tmp.name))
        self.dialog.pin(entries[0]['path'])
        self.assertEqual(self.dialog.tabs.currentIndex(), 1)
        self.assertTrue(Path(entries[0]['path']).exists())
        self.assertTrue(self.dialog.listWidget.item(0).data(QtCore.Qt.ItemDataRole.UserRole + 2))

    def test_background_job_returns_to_gui_and_close_cancels_jobs(self):
        entry = self.entries('Discovered.nexus')[0]
        self.discoveryPatch.stop()
        with mock.patch.object(map_finder.DiscoveryJob, 'spotlight_paths', return_value=[entry['path']]):
            self.dialog.tabs.setCurrentIndex(1)
            for _ in range(100):
                self.app.processEvents()
                if not self.dialog._jobs:
                    break
                QtTest.QTest.qWait(10)
            self.assertFalse(self.dialog._jobs)
            self.assertEqual(self.dialog.listWidget.item(0).text(), entry['name'])
        job = map_finder.DiscoveryJob()
        self.dialog._jobs['spotlight'] = job
        self.dialog.reject()
        self.assertTrue(job.cancelled.is_set())
        self.assertFalse(self.dialog._jobs)

    def test_missing_discovered_map_does_not_open_or_rewrite_history(self):
        entry = self.entries('Vanished.nex')[0]
        self.mac([entry])
        Path(entry['path']).unlink()
        before = welcome.history()
        with mock.patch.object(self.app, 'raiseOrOpen', create=True) as opened:
            self.dialog.openSelected()
            opened.assert_not_called()
        self.assertEqual(welcome.history(), before)
        self.assertIn('disappeared', self.dialog.message.text())

    def test_mac_tab_light_dark_render_and_controls(self):
        self.mac(self.entries('Quantum-dots.nex', 'Experiment.nexus', 'Reading list.nex',
                              'Meeting notes.nex', 'Project outline.nex'))
        self.assertTrue(self.dialog.macControls.isVisible())
        self.assertFalse(self.dialog.resumeButton.isVisible())
        for dark in (False, True):
            palette = self.dialog.palette()
            palette.setColor(palette.ColorRole.Window,
                             QtGui.QColor('#242528' if dark else '#ffffff'))
            self.dialog.setPalette(palette)
            self.app.processEvents()
            image = self.dialog.grab()
            self.assertFalse(image.isNull())
            destination = os.environ.get('NEXUS_MAP_FINDER_PREVIEW')
            if destination:
                self.assertTrue(image.save(destination + ('-dark.png' if dark else '-light.png')))


if __name__ == '__main__':
    unittest.main()
