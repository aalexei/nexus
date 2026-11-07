"""Mixed editor insertion preserves source pixels and existing arrangements."""
import copy
import os
import unittest

import pr_test_support as navigation
from PyQt6 import QtCore, QtGui, QtWidgets
from nexus import graphics, nexusgraph


class EditorLayoutTests(navigation.MapTestCase):
    setUpClass = classmethod(navigation.MapTestCase.setUpClass.__func__)
    tearDownClass = classmethod(navigation.MapTestCase.tearDownClass.__func__)
    node = navigation.MapTestCase.node

    def setUp(self):
        navigation.MapTestCase.setUp(self)
        previous = self.app.clipboard().mimeData()
        self.previous_clipboard = QtCore.QMimeData()
        if previous is not None:
            for fmt in previous.formats():
                self.previous_clipboard.setData(fmt, previous.data(fmt))
            if previous.hasImage():
                self.previous_clipboard.setImageData(previous.imageData())
        self.dialog = graphics.InputDialog()
        self.dialog.resize(780, 600)
        self.dialog.setDialog(self.root)
        self.dialog.selectmode.trigger()
        self.app.processEvents()

    def tearDown(self):
        self.app.clipboard().setMimeData(self.previous_clipboard)
        navigation.MapTestCase.tearDown(self)

    def image(self, width, height, ratio=1):
        image = QtGui.QImage(width, height, QtGui.QImage.Format.Format_ARGB32)
        image.fill(QtGui.QColor('white'))
        image.setDevicePixelRatio(ratio)
        return image

    def paste_image(self, image):
        before = set(self.root.node['content'])
        mime = QtCore.QMimeData()
        mime.setImageData(image)
        self.app.clipboard().setMimeData(mime)
        self.dialog.pasteEvent()
        self.app.processEvents()
        uid = next(iter(set(self.root.node['content']) - before))
        return next(item for item in self.dialog.scene.getItems() if item.uid == uid)

    def displayed_image_rect(self, item):
        size = item.pixmap().size()
        return item.transform().mapRect(QtCore.QRectF(0, 0, size.width(), size.height()))

    def test_large_and_portrait_images_keep_proportions_and_usable_size(self):
        landscape = self.paste_image(self.image(1600, 800))
        rect = self.displayed_image_rect(landscape)
        self.assertAlmostEqual(rect.width(), 380)
        self.assertAlmostEqual(rect.height(), 190)
        portrait = self.paste_image(self.image(400, 1200))
        rect = self.displayed_image_rect(portrait)
        self.assertAlmostEqual(rect.height(), 280)
        self.assertAlmostEqual(rect.width(), 280 / 3)

    def test_small_images_are_not_upscaled_and_retina_uses_logical_size(self):
        small = self.paste_image(self.image(80, 40))
        self.assertAlmostEqual(self.displayed_image_rect(small).width(), 80)
        retina = self.paste_image(self.image(400, 200, ratio=2))
        self.assertAlmostEqual(self.displayed_image_rect(retina).width(), 200)
        self.assertAlmostEqual(self.displayed_image_rect(retina).height(), 100)

    def test_sequential_paste_is_clear_of_content_and_preserves_existing_frames(self):
        frames = copy.deepcopy(self.root.node['content'])
        bounds = self.dialog.scene.contentBounds()
        first = self.paste_image(self.image(600, 300))
        self.assertGreaterEqual(first.sceneBoundingRect().top(), bounds.bottom() + 23.9)
        first_frame = copy.deepcopy(first['frame'])
        second = self.paste_image(self.image(300, 600))
        self.assertGreaterEqual(second.sceneBoundingRect().top(), first.sceneBoundingRect().bottom() + 23.9)
        self.assertEqual(first['frame'], first_frame)
        for uid, item in frames.items():
            self.assertEqual(self.root.node['content'][uid]['frame'], item['frame'])
        self.assertEqual(self.dialog.scene.mode, graphics.SelectMode)
        self.assertTrue(second.isSelected())
        self.assertTrue(self.dialog.scene.transformationWidget.isVisible())

    def test_internal_paste_preserves_relative_rotation_scale_and_spacing(self):
        first = QtGui.QTransform().translate(30, 60).rotate(20).scale(.8, .8)
        second = QtGui.QTransform().translate(120, 160).rotate(-10).scale(1.2, 1.2)
        copied = nexusgraph.CopyFormat()
        copied.addAsContent([
            {'kind': 'Text', 'source': 'One', 'frame': graphics.Transform(first).tolist()},
            {'kind': 'Text', 'source': 'Two', 'frame': graphics.Transform(second).tolist()},
        ])
        mime = QtCore.QMimeData()
        copied.setMimedata(mime)
        self.app.clipboard().setMimeData(mime)
        self.dialog.pasteEvent()
        items = {item.toPlainText(): item for item in self.dialog.scene.getItems()
                 if isinstance(item, graphics.TextItem)}
        delta = None
        for label, original in [('One', first), ('Two', second)]:
            actual = items[label].transform()
            for component in ('m11', 'm12', 'm21', 'm22'):
                self.assertAlmostEqual(getattr(actual, component)(), getattr(original, component)())
            displacement = QtCore.QPointF(actual.dx() - original.dx(), actual.dy() - original.dy())
            if delta is not None:
                self.assertAlmostEqual(displacement.x(), delta.x())
                self.assertAlmostEqual(displacement.y(), delta.y())
            delta = displacement

    def test_original_pixels_all_corners_and_dimensions_survive_reopen(self):
        image = self.image(900, 700)
        points = [(0, 0, 'red'), (899, 0, 'blue'), (0, 699, 'green'), (899, 699, 'magenta')]
        for x, y, color in points:
            image.setPixelColor(x, y, QtGui.QColor(color))
        item = self.paste_image(image)
        uid, sha = item.uid, item['sha1']
        frame = copy.deepcopy(item['frame'])
        source = nexusgraph.DataToImage(self.graph.findImageData(sha)['data'])
        self.assertEqual(source.size(), image.size())
        for x, y, color in points:
            self.assertEqual(source.pixelColor(x, y), QtGui.QColor(color))
        self.dialog.hide()
        self.dialog.setDialog(self.root)
        self.dialog.selectmode.trigger()
        reopened = next(item for item in self.dialog.scene.getItems() if item.uid == uid)
        self.assertEqual(reopened['frame'], frame)
        restored = reopened.pixmap().toImage()
        self.assertEqual(restored.size(), image.size())
        for x, y, color in points:
            self.assertEqual(restored.pixelColor(x, y), QtGui.QColor(color))

    def test_fit_content_ignores_handles_and_changes_only_view(self):
        self.paste_image(self.image(600, 300))
        before = copy.deepcopy(self.root.node['content'])
        bounds = self.dialog.scene.contentBounds()
        # A decorative editing helper must not affect the fit extent.
        self.dialog.scene.addRect(QtCore.QRectF(3000, 3000, 50, 50))
        self.dialog.fitContentAct.trigger()
        self.app.processEvents()
        visible = self.dialog.view.mapToScene(self.dialog.view.viewport().rect()).boundingRect()
        self.assertTrue(visible.contains(bounds))
        self.assertLessEqual(self.dialog.view.transform().m11(), 1.5001)
        self.assertEqual(self.root.node['content'], before)

    def test_viewport_draws_each_image_corner_after_fit_and_pan(self):
        image = self.image(600, 400)
        corners = [(0, 0, 'red'), (570, 0, 'blue'),
                   (0, 370, 'green'), (570, 370, 'magenta')]
        painter = QtGui.QPainter(image)
        for x, y, color in corners:
            painter.fillRect(x, y, 30, 30, QtGui.QColor(color))
        painter.end()
        item = self.paste_image(image)
        item.setSelected(False)
        self.dialog.scene.transformationWidget.hide()
        self.dialog.fitContentAct.trigger()
        self.app.processEvents()
        for dx in (0, 10, -10):
            self.dialog.view.centerOn(item.sceneBoundingRect().center() + QtCore.QPointF(dx, 0))
            self.app.processEvents()
            rendered = self.dialog.view.viewport().grab().toImage()
            ratio = rendered.devicePixelRatio()
            for x, y, color in corners:
                position = self.dialog.view.mapFromScene(item.mapToScene(QtCore.QPointF(x + 15, y + 15)))
                self.assertEqual(rendered.pixelColor(round(position.x() * ratio),
                                                     round(position.y() * ratio)), QtGui.QColor(color))

    def test_one_undo_removes_new_image_and_keeps_existing_content(self):
        before = copy.deepcopy(self.root.node['content'])
        self.graph.clearchanges()
        item = self.paste_image(self.image(320, 180))
        uid = item.uid
        self.graph.undo()
        restored = self.graph.getuid(self.root.node['uid'])
        self.assertNotIn(uid, restored['content'])
        self.assertEqual(restored['content'], before)

    def test_optional_mixed_editor_preview(self):
        destination = os.environ.get('NEXUS_EDITOR_PREVIEW')
        if not destination:
            self.skipTest('Set NEXUS_EDITOR_PREVIEW to save a visual example')
        image = self.image(760, 440)
        painter = QtGui.QPainter(image)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setPen(QtGui.QPen(QtGui.QColor('#00bbaa'), 10))
        painter.drawLine(100, 220, 660, 110)
        painter.drawLine(100, 220, 660, 330)
        painter.setBrush(QtGui.QColor('#eeeeee'))
        painter.setPen(QtGui.QPen(QtGui.QColor('#222222'), 4))
        painter.drawRoundedRect(QtCore.QRectF(30, 160, 200, 120), 16, 16)
        painter.setFont(QtGui.QFont('Helvetica', 26))
        painter.drawText(QtCore.QRectF(30, 160, 200, 120), QtCore.Qt.AlignmentFlag.AlignCenter, 'Nexus')
        painter.end()
        self.paste_image(image)
        self.dialog.fitContentAct.trigger()
        self.app.processEvents()
        self.assertTrue(self.dialog.grab().save(destination))


if __name__ == '__main__':
    unittest.main()
