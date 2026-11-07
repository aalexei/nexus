"""Isolated thumbnail rendering and hover cancellation on temporary maps."""
import hashlib
import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from settings_helpers import isolate_settings

from PyQt6 import QtCore, QtGui, QtTest, QtWidgets
from nexus import graphics, nexusgraph, welcome, map_preview, preview_cache, preview_worker


class PreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.preferences = tempfile.TemporaryDirectory()
        cls.settingsIsolation = isolate_settings(cls.preferences.name)
        cls.settingsIsolation.start()
        QtCore.QSettings.setDefaultFormat(QtCore.QSettings.Format.IniFormat)
        QtCore.QSettings.setPath(QtCore.QSettings.Format.IniFormat,
                                 QtCore.QSettings.Scope.UserScope, cls.preferences.name)
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    @classmethod
    def tearDownClass(cls):
        cls.settingsIsolation.stop()
        cls.preferences.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.path = str(self.root / 'Preview map.nex')
        self.graph = nexusgraph.NexusGraph(self.path)
        self.graph.savesetting('version', graphics.VERSION)
        root = self.graph.Node('Root').save()
        stem = self.graph.Node('Stem', scale=1, flip=1, pos=[0, 0], content={
            'label': {'kind': 'Text', 'source': 'Preview root', 'frame': graphics.Transform().tolist(), 'z': 0}}).save()
        self.graph.Edge(root, 'Child', stem).save()
        child = self.graph.Node('Stem', scale=.5, flip=1, pos=[200, 40], content={
            'label': {'kind': 'Text', 'source': 'Saved branch', 'frame': graphics.Transform().tolist(), 'z': 0}}).save()
        self.graph.Edge(stem, 'Child', child).save()
        self.stem = stem
        self.cache = self.root / 'cache'
        self.cache.mkdir()
        self.renderer = map_preview.PreviewService(self.cache)
        self.results = []
        self.renderer.ready.connect(self.results.append)
        welcome.settings().clear()
        welcome.settings().setValue('recentFileList', [self.path])
        self.dialog = welcome.NewOrOpenDialog()
        self.dialog.preview.renderer = self.renderer
        self.dialog.show()
        self.dialog.activateWindow()
        self.app.processEvents()
        # Service tests drive hover explicitly; isolate them from a stationary
        # native cursor that happens to lie over the freshly shown window.
        self.dialog.preview.clear()
        self.dialog.listWidget.viewport().removeEventFilter(self.dialog.preview)

    def tearDown(self):
        self.dialog.preview.clear()
        self.renderer.stop()
        self.dialog.hide()
        self.dialog.deleteLater()
        self.renderer.deleteLater()
        self.app.processEvents()
        self.graph.connection.close()
        self.tmp.cleanup()

    def wait(self, predicate, seconds=12):
        limit = time.monotonic() + seconds
        while not predicate() and time.monotonic() < limit:
            self.app.processEvents()
            QtTest.QTest.qWait(10)
        self.assertTrue(predicate(), 'Preview did not finish within deadline')

    def request(self, token='test'):
        self.renderer.request(self.path, token)
        self.wait(lambda: any(result['token'] == token for result in self.results))
        return next(result for result in self.results if result['token'] == token)

    def digest(self):
        return hashlib.sha256(Path(self.path).read_bytes()).hexdigest()

    def test_render_original_unchanged_and_cache_hit_avoids_rendering(self):
        before, changes = self.digest(), self.graph.connection.total_changes()
        first = self.request('first')
        self.assertEqual(first['error'], '')
        image = QtGui.QImage(first['image'])
        self.assertEqual(image.size(), QtCore.QSize(preview_cache.WIDTH, preview_cache.HEIGHT))
        self.assertEqual(self.digest(), before)
        self.assertEqual(self.graph.connection.total_changes(), changes)
        second = self.request('second')
        self.assertEqual(first['image'], second['image'])
        self.assertFalse(list(self.cache.glob('.render-*')))

    def test_saved_edit_invalidates_thumbnail(self):
        first = self.request('before')
        self.stem['content']['label']['source'] = 'Different saved text'
        self.stem.keyChanged('content')
        self.stem.save()
        second = self.request('after')
        self.assertEqual(second['error'], '')
        self.assertNotEqual(first['image'], second['image'])

    def test_large_image_opt_in_is_exact_path_not_basename_or_folder(self):
        welcome.settings().setValue('previewLargeImageMaps', [self.path])
        self.assertTrue(self.renderer.largeImagesEnabled(self.path))
        self.assertFalse(self.renderer.largeImagesEnabled(str(self.root / 'elsewhere' / Path(self.path).name)))
        self.assertFalse(self.renderer.largeImagesEnabled(str(self.root / 'Other.nex')))
        welcome.settings().setValue('previewLargeImageMaps', self.path)
        self.assertFalse(self.renderer.largeImagesEnabled(self.path))

    def test_named_settings_really_stay_in_temporary_directory(self):
        store = welcome.settings()
        self.assertEqual(store.format(), QtCore.QSettings.Format.IniFormat)
        self.assertIn(Path(self.preferences.name).resolve(), Path(store.fileName()).resolve().parents)
        self.assertFalse(store.fallbacksEnabled())

    def test_scoped_profile_has_separate_cache_key_and_process_flag(self):
        standard = self.request('standard')
        welcome.settings().setValue('previewLargeImageMaps', [self.path])
        self.renderer.request(self.path, 'scoped')
        self.assertIn('--large-images', self.renderer.active['process'].arguments())
        self.wait(lambda: any(result['token'] == 'scoped' for result in self.results))
        scoped = self.results[-1]
        self.assertEqual(scoped['error'], '')
        self.assertNotEqual(standard['image'], scoped['image'])

    def test_size_guard_remains_for_other_maps_and_opt_in_can_render_larger_map(self):
        self.graph.connection.execute('CREATE TABLE preview_test_padding (data BLOB)')
        self.graph.connection.execute('INSERT INTO preview_test_padding VALUES (zeroblob(?))', (65 * 1024 * 1024,))
        before = self.digest()
        self.assertTrue(self.request('standard-limit')['error'])
        self.renderer.cooldown.clear()
        welcome.settings().setValue('previewLargeImageMaps', [self.path])
        self.assertEqual(self.request('scoped-limit')['error'], '')
        self.assertEqual(self.digest(), before)

    def test_reduced_private_images_preserve_transformed_bounds_and_references(self):
        image = QtGui.QImage(3200, 1800, QtGui.QImage.Format.Format_RGB32)
        image.fill(QtGui.QColor('red'))
        data = self.graph.Node('ImageData', sha1='stable-reference', data=nexusgraph.ImageToData(image)).save()
        self.graph.Edge(self.stem, 'With', data).save()
        frame = graphics.Transform().translate(33, 71).rotate(27).scale(.3, .4)
        self.stem['content']['image'] = {'kind': 'Image', 'sha1': 'stable-reference', 'frame': frame.tolist()}
        self.stem.keyChanged('content')
        self.stem.save()
        before = self.digest()
        private = nexusgraph.NexusGraph(':memory:')
        try:
            with private.connection.backup('main', self.graph.connection, 'main') as backup:
                while not backup.done:
                    backup.step(100)
            preview_worker.reduce_images(private.connection)
            import json
            updated_data = json.loads(private.connection.execute('SELECT data FROM nodes WHERE uid=?', (data['uid'],)).fetchone()[0])
            updated_stem = json.loads(private.connection.execute('SELECT data FROM nodes WHERE uid=?', (self.stem['uid'],)).fetchone()[0])
            bitmap = nexusgraph.DataToImage(updated_data['data'])
            self.assertLessEqual(max(bitmap.width(), bitmap.height()), 1024)
            updated_frame = QtGui.QTransform(*updated_stem['content']['image']['frame'])
            for x, y in ((0, 0), (1, 0), (0, 1), (1, 1)):
                old = frame.map(QtCore.QPointF(x * image.width(), y * image.height()))
                new = updated_frame.map(QtCore.QPointF(x * bitmap.width(), y * bitmap.height()))
                self.assertAlmostEqual(old.x(), new.x())
                self.assertAlmostEqual(old.y(), new.y())
            self.assertEqual(updated_data['sha1'], 'stable-reference')
            self.assertEqual(self.digest(), before)
        finally:
            private.connection.close()

    def test_scoped_profile_skips_only_isolated_records_not_disconnected_trees(self):
        orphan = self.graph.Node('Stem', content={}).save()
        welcome.settings().setValue('previewLargeImageMaps', [self.path])
        self.assertEqual(self.request('isolated')['error'], '')
        self.graph.Edge(orphan, 'Child', self.graph.Node('Stem', content={}).save()).save()
        self.assertTrue(self.request('disconnected-tree')['error'])

    def test_scoped_image_pixel_guard(self):
        # A compressed header advertising excessive dimensions is refused
        # before allocating or attempting to decode its pixels.
        import base64, struct, zlib
        def chunk(kind, payload):
            return struct.pack('>I', len(payload)) + kind + payload + struct.pack('>I', zlib.crc32(kind + payload))
        header = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 6000, 6000, 8, 2, 0, 0, 0)) + chunk(b'IDAT', b'') + chunk(b'IEND', b'')
        self.graph.Node('ImageData', sha1='excessive', data=base64.b64encode(header).decode()).save()
        with self.assertRaisesRegex(ValueError, 'pixel limit'):
            preview_worker.reduce_images(self.graph.connection)

    def test_invalid_and_legacy_files_fail_without_changing_source(self):
        self.graph.savesetting('version', .8)
        before = self.digest()
        legacy = self.request('legacy')
        self.assertTrue(legacy['error'])
        self.assertEqual(self.digest(), before)
        invalid = self.root / 'not-a-map.nex'
        invalid.touch()
        self.renderer.request(str(invalid), 'invalid')
        self.wait(lambda: any(result['token'] == 'invalid' for result in self.results))
        self.assertTrue(self.results[-1]['error'])
        self.assertEqual(invalid.stat().st_size, 0)

    def test_cycle_is_rejected_without_gui_crash(self):
        self.graph.Edge(self.stem, 'Child', self.stem).save()
        result = self.request('cycle')
        self.assertTrue(result['error'])

    def test_corrupt_cache_is_regenerated(self):
        first = self.request('first')
        cache = Path(first['image'])
        with cache.open('r+b') as stream:
            stream.truncate(24)
        self.assertFalse(preview_cache.valid_png(cache))
        second = self.request('repaired')
        self.assertEqual(second['error'], '')
        self.assertTrue(preview_cache.valid_png(cache))

    def test_external_html_resources_are_not_loaded(self):
        self.stem['content']['label']['source'] = '<img src="file:///etc/passwd">'
        self.stem.keyChanged('content')
        self.stem.save()
        before = self.digest()
        result = self.request('external')
        self.assertTrue(result['error'])
        self.assertEqual(self.digest(), before)

    def test_deleted_file_and_changed_symlink_return_unavailable(self):
        alias = self.root / 'changed.nex'
        alias.symlink_to(self.path)
        self.renderer.request(str(alias), 'symlink')
        self.wait(lambda: any(result['token'] == 'symlink' for result in self.results))
        self.assertTrue(self.results[-1]['error'])
        self.renderer.request(str(self.root / 'missing.nex'), 'missing')
        self.wait(lambda: any(result['token'] == 'missing' for result in self.results))
        self.assertTrue(self.results[-1]['error'])

    def test_worker_timeout_is_reported_and_main_service_can_recover(self):
        self.renderer.request(self.path, 'timeout')
        job = self.renderer.active
        job['process'].started.connect(lambda: self.renderer._timeout(job))
        self.wait(lambda: any(result['token'] == 'timeout' for result in self.results))
        self.assertIn('timed out', self.results[-1]['error'])
        self.assertFalse(list(self.cache.glob('.render-*')))
        self.renderer.cooldown.clear()
        self.assertEqual(self.request('recovered')['error'], '')

    def test_cache_failure_does_not_abort_or_mutate_source(self):
        blocked = self.root / 'not-a-directory'
        blocked.touch()
        before = self.digest()
        self.renderer.directory = blocked
        result = self.request('blocked-cache')
        self.assertTrue(result['error'])
        self.assertEqual(self.digest(), before)

    def test_idle_save_warming_waits_and_coalesces_changes(self):
        owner = QtWidgets.QWidget()
        owner.scene = SimpleNamespace(graph=self.graph)
        clock = [0]
        original = self.app.property('nexusTestMode')
        self.app.setProperty('nexusTestMode', True)
        try:
            with mock.patch.object(map_preview.time, 'monotonic', side_effect=lambda: clock[0]), \
                    mock.patch.object(map_preview, 'service') as current:
                current.return_value.prefetch.return_value = True
                warmer = map_preview.IdlePreview(owner)
                warmer.poll()
                clock[0] = 3
                warmer.poll()
                current.return_value.prefetch.assert_not_called()
                clock[0] = 5
                warmer.poll()
                current.return_value.prefetch.assert_called_once_with(self.path)
                self.graph.savesetting('saved-edit', 1)
                clock[0] = 6
                warmer.poll()
                clock[0] = 8
                warmer.poll()
                self.assertEqual(current.return_value.prefetch.call_count, 1)
                clock[0] = 11
                warmer.poll()
                self.assertEqual(current.return_value.prefetch.call_count, 2)
                warmer.stop()
        finally:
            self.app.setProperty('nexusTestMode', original)
            owner.deleteLater()

    def test_cancelled_result_is_not_delivered_and_newest_request_wins(self):
        self.renderer.request(self.path, 'old')
        self.renderer.request(self.path, 'new')
        self.wait(lambda: any(result['token'] == 'new' for result in self.results))
        self.assertFalse(any(result['token'] == 'old' for result in self.results))
        self.assertFalse(list(self.cache.glob('.render-*')))

    def test_hover_delay_mouse_leave_and_stale_results(self):
        hover = self.dialog.preview
        with mock.patch.object(self.renderer, 'request') as requested:
            hover.hover(self.path)
            QtTest.QTest.qWait(100)
            requested.assert_not_called()
            hover.clear()
            QtTest.QTest.qWait(200)
            requested.assert_not_called()
            hover.hover(self.path)
            self.wait(lambda: requested.called, seconds=2)
            self.assertTrue(hover.popup.isVisible())
            token = hover.token
            hover.clear()
            hover.completed({'token': token, 'path': self.path, 'image': '', 'error': 'failed'})
            self.assertFalse(hover.popup.isVisible())

    def test_preview_does_not_steal_focus_and_closes_on_file_change(self):
        self.dialog.search.setFocus()
        self.app.processEvents()
        hover = self.dialog.preview
        hover.hover(self.path)
        self.wait(lambda: bool(self.results))
        self.assertTrue(hover.popup.isVisible())
        self.assertTrue(self.dialog.search.hasFocus())
        self.assertTrue(hover.popup.testAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents))
        self.graph.savesetting('changed-under-preview', True)
        self.wait(lambda: not hover.popup.isVisible(), seconds=2)
        self.assertFalse(hover.popup.isVisible())

    def test_unrelated_directory_changes_do_not_dismiss_preview(self):
        hover = self.dialog.preview
        hover.hover(self.path)
        self.wait(lambda: bool(self.results))
        (self.root / 'unrelated.txt').touch()
        hover.directoryChanged()
        self.app.processEvents()
        self.assertTrue(hover.popup.isVisible())
        with mock.patch.object(map_preview.Path, 'exists', return_value=True):
            hover.directoryChanged()
        self.assertFalse(hover.popup.isVisible())

    def test_real_mouse_hover_preview_does_not_open_or_change_selection(self):
        self.dialog.listWidget.viewport().installEventFilter(self.dialog.preview)
        item = self.dialog.listWidget.item(0)
        rect = self.dialog.listWidget.visualItemRect(item)
        with mock.patch.object(self.app, 'raiseOrOpen', create=True) as opened:
            QtTest.QTest.mouseMove(self.dialog.listWidget.viewport(), QtCore.QPoint(2, 2))
            self.app.processEvents()
            QtTest.QTest.mouseMove(self.dialog.listWidget.viewport(), rect.center())
            self.wait(lambda: bool(self.results))
            self.assertTrue(self.dialog.preview.popup.isVisible())
            self.assertEqual(self.dialog.currentPath(), self.path)
            opened.assert_not_called()
            self.dialog.search.setText('different')
            self.assertFalse(self.dialog.preview.popup.isVisible())

    def test_cache_pruning_is_bounded_and_preserves_unrelated_files(self):
        image = QtGui.QImage(preview_cache.WIDTH, preview_cache.HEIGHT, QtGui.QImage.Format.Format_RGB32)
        image.fill(QtGui.QColor('white'))
        for index in range(5):
            image.save(str(self.cache / ('thumb-' + f'{index:064x}' + '.png')))
        unrelated = self.cache / 'my-file.txt'
        unrelated.touch()
        with mock.patch.object(preview_cache, 'MAX_FILES', 2):
            preview_cache.prune(self.cache)
        self.assertEqual(len(list(self.cache.glob('thumb-*.png'))), 2)
        self.assertTrue(unrelated.exists())

    def test_preview_optional_visual(self):
        destination = os.environ.get('NEXUS_HOVER_PREVIEW')
        hover = self.dialog.preview
        hover.hover(self.path)
        self.wait(lambda: bool(self.results))
        self.assertFalse(hover.image.pixmap().isNull())
        if destination:
            self.assertTrue(hover.popup.grab().save(destination))


if __name__ == '__main__':
    unittest.main()
