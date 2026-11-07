"""Copy mixed editor content as clean pixels and editable Nexus data."""
import unittest
from unittest.mock import patch
import pr_test_support as navigation
from PyQt6 import QtCore, QtGui
from nexus import graphics, graphydb, nexusgraph


class EditorCopyTests(navigation.MapTestCase):
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

    def tearDown(self):
        self.app.clipboard().setMimeData(self.previous_clipboard)
        navigation.MapTestCase.tearDown(self)

    def open_selection(self):
        self.dialog = graphics.InputDialog()
        self.dialog.setDialog(self.root)
        self.dialog.selectmode.trigger()
        text = next(item for item in self.dialog.scene.getItems()
                    if isinstance(item, graphics.TextItem))
        text.setTextWidth(240)
        text.setSelected(True)
        self.dialog.scene.setSelectionWidget()
        self.app.processEvents()
        return text

    def test_copy_keeps_pixels_and_editable_content_on_clipboard(self):
        text = self.open_selection()
        self.dialog.copyEvent()
        mime = self.app.clipboard().mimeData()
        self.assertTrue(mime.hasImage())
        self.assertTrue(mime.hasFormat('application/x-nexus'))
        copied = nexusgraph.CopyFormat.getMimedata(mime)
        self.assertEqual(copied.nodes[0]['content'][0]['source'], text['source'])
        image = mime.imageData()
        self.assertIsInstance(image, QtGui.QImage)
        self.assertFalse(image.isNull())

    def test_mixed_copy_keeps_original_image_data_and_visible_image_extent(self):
        image = QtGui.QImage(32, 16, QtGui.QImage.Format.Format_ARGB32)
        image.fill(QtGui.QColor('#10b9a2'))
        copydata, _ = self.graph.itemFromImage(image)
        data = next(iter(copydata.images.values()))
        stored = self.graph.Node('ImageData')
        stored.update(data)
        stored.save()
        self.graph.Edge(self.root.node, 'With', stored).save()
        content = copydata.nodes[0]['content'][0]
        transform = graphics.Transform()
        transform.translate(0, 60)
        content['frame'] = transform.tolist()
        self.root.node['content'][graphydb.generateUUID()] = content
        self.root.node.keyChanged('content')
        self.root.node.save()
        text = self.open_selection()
        picture = next(item for item in self.dialog.scene.getItems()
                       if isinstance(item, graphics.PixmapItem))
        picture.setSelected(True)
        self.dialog.scene.setSelectionWidget()
        self.dialog.copyEvent()
        mime = self.app.clipboard().mimeData()
        copied = nexusgraph.CopyFormat.getMimedata(mime)
        self.assertEqual(len(copied.nodes[0]['content']), 2)
        self.assertEqual(copied.images[content['sha1']]['data'], data['data'])
        raster = mime.imageData()
        self.assertEqual(raster.pixelColor(32, 136).name(), '#10b9a2')
        self.assertTrue(text.isSelected())
        self.assertTrue(picture.isSelected())

    def test_copy_omits_grid_unselected_content_and_editor_handles(self):
        text = self.open_selection()
        scene = self.dialog.scene
        unrelated = scene.addRect(text.sceneBoundingRect(), QtGui.QPen(QtCore.Qt.PenStyle.NoPen),
                                  QtGui.QBrush(QtGui.QColor('magenta')))
        unrelated.setZValue(100)
        background = scene.backgroundBrush()
        before_visible = {item: item.isVisible() for item in scene.items()}
        self.dialog.copyEvent()
        image = self.app.clipboard().mimeData().imageData()
        # The blank part of this wide text block must stay transparent.
        self.assertEqual(image.pixelColor(image.width()//2, image.height()//2).alpha(), 0)
        self.assertEqual(image.pixelColor(image.width()-2, 2).alpha(), 0)
        self.assertTrue(any(image.pixelColor(x, y).alpha() > 0
                            for x in range(min(140, image.width()))
                            for y in range(image.height())))
        self.assertEqual(scene.backgroundBrush(), background)
        self.assertTrue(text.isSelected())
        self.assertEqual({item: item.isVisible() for item in scene.items()}, before_visible)
        self.assertTrue(scene.transformationWidget.isVisible())

    def test_failed_render_restores_editor_and_preserves_clipboard(self):
        text = self.open_selection()
        scene = self.dialog.scene
        background = scene.backgroundBrush()
        before_visible = {item: item.isVisible() for item in scene.items()}
        self.app.clipboard().setText('Previous clipboard contents')
        with patch.object(scene, 'render', side_effect=RuntimeError('render failed')):
            with self.assertRaisesRegex(RuntimeError, 'render failed'):
                self.dialog.copyEvent()
        self.assertEqual(scene.backgroundBrush(), background)
        self.assertTrue(text.isSelected())
        self.assertEqual({item: item.isVisible() for item in scene.items()}, before_visible)
        self.assertEqual(self.app.clipboard().text(), 'Previous clipboard contents')


if __name__ == '__main__':
    unittest.main()
