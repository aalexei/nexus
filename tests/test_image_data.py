"""Deleting image items preserves the correct stored image sources."""
import unittest

import pr_test_support as navigation
from PyQt6 import QtGui
from nexus import graphics, graphydb, nexusgraph


class ImageDataTests(navigation.MapTestCase):
    setUpClass = classmethod(navigation.MapTestCase.setUpClass.__func__)
    tearDownClass = classmethod(navigation.MapTestCase.tearDownClass.__func__)
    setUp = navigation.MapTestCase.setUp
    tearDown = navigation.MapTestCase.tearDown
    node = navigation.MapTestCase.node

    def add_image(self, color, source=None):
        if source is None:
            image = QtGui.QImage(40, 30, QtGui.QImage.Format.Format_ARGB32)
            image.fill(QtGui.QColor(color))
            copied, _ = self.graph.itemFromImage(image)
            data = next(iter(copied.images.values()))
            source = self.graph.Node('ImageData')
            source.update(data)
            source.save()
            self.graph.Edge(self.root.node, 'With', source).save()
        uid = graphydb.generateUUID()
        self.root.node['content'][uid] = {
            'kind': 'Image', 'sha1': source['sha1'],
            'frame': graphics.Transform().tolist(), 'z': 1,
        }
        self.root.node.keyChanged('content')
        self.root.node.save()
        return uid, source

    def open_editor(self):
        self.dialog = graphics.InputDialog()
        self.dialog.setDialog(self.root)
        self.dialog.selectmode.trigger()
        self.app.processEvents()

    def image_item(self, uid):
        return next(item for item in self.dialog.scene.getItems()
                    if isinstance(item, graphics.PixmapItem) and item.uid == uid)

    def linked_shas(self, node=None):
        node = node or self.root.node
        return {edge.end['sha1'] for edge in node.outE('e.kind="With"')}

    def test_deleting_second_image_preserves_first_source_and_undo_restores(self):
        first_uid, first = self.add_image('red')
        second_uid, second = self.add_image('blue')
        self.open_editor()
        self.graph.clearchanges()
        self.image_item(second_uid).deleteNodeItem()
        self.assertEqual(self.linked_shas(), {first['sha1']})
        self.assertIsNotNone(self.graph.findImageData(first['sha1']))
        self.assertIsNone(self.graph.findImageData(second['sha1']))
        self.assertIn(first_uid, self.root.node['content'])
        self.assertNotIn(second_uid, self.root.node['content'])

        self.graph.undo()
        restored = self.graph.getuid(self.root.node['uid'])
        self.assertIn(second_uid, restored['content'])
        self.assertEqual(self.linked_shas(restored), {first['sha1'], second['sha1']})
        decoded = nexusgraph.DataToImage(self.graph.findImageData(second['sha1'])['data'])
        self.assertEqual(decoded.pixelColor(0, 0), QtGui.QColor('blue'))

    def test_same_source_remains_until_its_last_item_is_deleted(self):
        first_uid, source = self.add_image('green')
        second_uid, _ = self.add_image('green', source=source)
        self.open_editor()
        self.image_item(first_uid).deleteNodeItem()
        self.assertEqual(self.linked_shas(), {source['sha1']})
        self.assertIsNotNone(self.graph.findImageData(source['sha1']))
        self.image_item(second_uid).deleteNodeItem()
        self.assertEqual(self.linked_shas(), set())
        self.assertIsNone(self.graph.findImageData(source['sha1']))

    def test_source_shared_by_other_stem_is_not_deleted(self):
        uid, source = self.add_image('purple')
        other = self.node('Other image owner')
        self.graph.Edge(other, 'With', source).save()
        self.open_editor()
        self.image_item(uid).deleteNodeItem()
        self.assertEqual(self.linked_shas(), set())
        self.assertEqual(self.linked_shas(other), {source['sha1']})
        self.assertIsNotNone(self.graph.findImageData(source['sha1']))

    def test_duplicate_matching_links_are_removed_without_affecting_other_image(self):
        keep_uid, keep = self.add_image('orange')
        delete_uid, remove = self.add_image('cyan')
        self.graph.Edge(self.root.node, 'With', remove).save()
        self.open_editor()
        self.image_item(delete_uid).deleteNodeItem()
        self.assertEqual(self.linked_shas(), {keep['sha1']})
        self.assertIn(keep_uid, self.root.node['content'])
        self.assertIsNone(self.graph.findImageData(remove['sha1']))


if __name__ == '__main__':
    unittest.main()
