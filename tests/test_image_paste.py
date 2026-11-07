"""Direct map/inline image paste, atomic persistence, and legacy clipboard paths."""
import copy
import unittest
from unittest import mock

from PyQt6 import QtCore, QtGui, QtWidgets, QtTest
import test_keyboard_navigation as navigation
from nexus import graphics, graphydb, nexusgraph, image_paste


class ImagePasteTests(unittest.TestCase):
    setUpClass = classmethod(navigation.KeyboardNavigationTests.setUpClass.__func__)
    tearDownClass = classmethod(navigation.KeyboardNavigationTests.tearDownClass.__func__)
    tearDown = navigation.KeyboardNavigationTests.tearDown
    node = navigation.KeyboardNavigationTests.node
    child = navigation.KeyboardNavigationTests.child
    select = navigation.KeyboardNavigationTests.select
    key = navigation.KeyboardNavigationTests.key

    def setUp(self):
        navigation.KeyboardNavigationTests.setUp(self)
        self.old_clipboard = QtCore.QMimeData()
        previous = self.app.clipboard().mimeData()
        if previous is not None:
            for fmt in previous.formats():
                self.old_clipboard.setData(fmt, previous.data(fmt))
            if previous.hasImage():
                self.old_clipboard.setImageData(previous.imageData())
        self.addCleanup(lambda: self.app.clipboard().setMimeData(self.old_clipboard))

    def clipboard_image(self, width=1200, height=600, ratio=1, text=None):
        image = QtGui.QImage(width, height, QtGui.QImage.Format.Format_ARGB32)
        image.fill(QtGui.QColor('orange'))
        image.setPixelColor(0, 0, QtGui.QColor('red'))
        image.setPixelColor(width-1, height-1, QtGui.QColor('blue'))
        image.setDevicePixelRatio(ratio)
        mime = QtCore.QMimeData()
        mime.setImageData(image)
        if text is not None:
            mime.setText(text)
        self.app.clipboard().setMimeData(mime)
        return image

    def images(self, stem=None):
        return [i for i in (stem or self.root).leaf.childItems() if isinstance(i, graphics.PixmapItem)]

    def paste(self):
        self.key(QtCore.Qt.Key.Key_V, QtCore.Qt.KeyboardModifier.ControlModifier)

    def test_selected_map_paste_keeps_node_content_and_children_and_is_one_undo(self):
        child = self.child(self.root, 'Child', 100)
        nested = self.child(child, 'Nested', 30)
        self.select(self.root)
        before = copy.deepcopy(self.root.node.data)
        origin = self.root.leaf.mapToScene(QtCore.QPointF())
        positions = [child.sceneTransform(), nested.sceneTransform()]
        text = next(i for i in self.root.leaf.childItems() if isinstance(i, graphics.TextItem))
        bottom = text.mapRectToParent(text.boundingRect()).bottom()
        source = self.clipboard_image()
        self.graph.clearchanges()
        # Map menu/toolbar paste routes through scene.paste as in MainWindow.
        self.scene.paste()
        self.assertEqual(len(self.scene.allChildStems()), 3)
        self.assertEqual(len(self.images()), 1)
        image = self.images()[0]
        self.assertAlmostEqual(image.mapRectToParent(image.boundingRect()).top(), bottom+24)
        rect = image.mapRectToParent(image.boundingRect())
        self.assertLessEqual(rect.width(), 380)
        self.assertAlmostEqual(rect.width()/rect.height(), 2)
        self.assertFalse(image.sceneBoundingRect().intersects(child.leaf.sceneBoundingRect()))
        for uid, value in before['content'].items():
            self.assertEqual(self.root.node['content'][uid], value)
        self.assertEqual(self.root.leaf.mapToScene(QtCore.QPointF()), origin)
        self.assertEqual([child.sceneTransform(), nested.sceneTransform()], positions)
        decoded = nexusgraph.DataToImage(self.graph.findImageData(image['sha1'])['data'])
        self.assertEqual(decoded.size(), source.size())
        self.assertEqual(decoded.pixelColor(0, 0), QtGui.QColor('red'))
        self.assertEqual(decoded.pixelColor(source.width()-1, source.height()-1), QtGui.QColor('blue'))
        self.assertEqual(len({change.get('batch') for _, change in self.graph.lastchanges()}), 1)
        self.root.renew()
        self.assertEqual(len(self.images()), 1)
        self.assertEqual([child.sceneTransform(), nested.sceneTransform()], positions)
        self.scene.undo()
        self.assertEqual(self.root.node['content'], before['content'])
        self.assertEqual(self.root.node['pos'], before['pos'])
        self.assertFalse(list(self.graph.fetch('[n:ImageData]')))
        self.assertFalse(self.graph.lastchanges())

    def test_inline_paste_saves_text_prefers_image_over_alt_text_and_closes_inline_only(self):
        self.view.inline.textMode = True
        self.view.inline.start(self.root)
        item = self.view.inline.item
        cursor = item.textCursor(); cursor.insertText(' saved draft'); item.setTextCursor(cursor)
        self.clipboard_image(text='image alt text')
        self.paste()
        self.assertIsNone(self.view.inline.item)
        self.assertEqual(self.opened, [])
        text = next(i for i in self.root.leaf.childItems() if isinstance(i, graphics.TextItem))
        self.assertIn('saved draft', text.toPlainText())
        self.assertNotIn('image alt text', text.toPlainText())
        self.assertEqual(len(self.images()), 1)
        self.scene.undo()
        self.assertEqual(len(self.images()), 0)
        text = next(i for i in self.root.leaf.childItems() if isinstance(i, graphics.TextItem))
        self.assertIn('saved draft', text.toPlainText())

    def test_retina_small_and_repeated_images_reuse_source_and_stack_below(self):
        self.select(self.root)
        self.clipboard_image(400, 200, ratio=2)
        self.scene.paste()
        first = self.images()[0]
        rect = first.mapRectToParent(first.boundingRect())
        self.assertAlmostEqual(rect.width(), 200)
        self.assertAlmostEqual(rect.height(), 100)
        self.scene.paste()
        self.assertEqual(len(list(self.graph.fetch('[n:ImageData]'))), 1)
        self.assertEqual(len(list(self.root.node.outE('e.kind="With"'))), 1)
        self.assertEqual(len(self.images()), 2)
        second = next(i for i in self.images() if i.uid != first.uid)
        self.assertGreaterEqual(second.mapRectToParent(second.boundingRect()).top(), rect.bottom()+24)
        self.scene.undo()
        self.assertEqual(len(self.images()), 1)
        self.assertEqual(len(list(self.graph.fetch('[n:ImageData]'))), 1)
        self.clipboard_image(40, 20)
        self.scene.paste()
        self.assertTrue(any(i.mapRectToParent(i.boundingRect()).size() == QtCore.QSizeF(40, 20) for i in self.images()))

    def test_paste_into_empty_new_inline_node_survives_and_undo_removes_creation(self):
        self.view.inline.textMode = True
        self.select(self.root)
        self.graph.clearchanges()
        self.key(QtCore.Qt.Key.Key_Tab)
        uid = self.view.inline.item.stem.node['uid']
        self.clipboard_image()
        self.paste()
        target = next(s for s in self.scene.allChildStems() if s.node['uid'] == uid)
        self.assertEqual(len(self.images(target)), 1)
        self.assertIsNone(self.view.inline.item)
        self.scene.undo()
        self.assertIsNone(self.graph.getuid(uid))
        self.assertFalse(list(self.graph.fetch('[n:ImageData]')))
        self.assertFalse(self.graph.lastchanges())

    def test_failed_image_save_rolls_back_sources_and_keeps_live_text(self):
        self.view.inline.textMode = True
        self.view.inline.start(self.root)
        item = self.view.inline.item
        cursor = item.textCursor(); cursor.insertText(' keep draft'); item.setTextCursor(cursor)
        self.assertTrue(self.view.inline.checkpoint())
        original = copy.deepcopy(self.root.node.data)
        self.clipboard_image()
        save = graphydb.Node.save
        def fail(node, *args, **kwargs):
            if node['uid'] == self.root.node['uid'] and kwargs.get('batch'):
                raise OSError('disk full')
            return save(node, *args, **kwargs)
        with mock.patch.object(graphydb.Node, 'save', fail), self.assertLogs(level='ERROR'):
            self.paste()
        self.assertIs(self.view.inline.item, item)
        self.assertIn('keep draft', item.toPlainText())
        self.assertEqual(self.root.node['content'], original['content'])
        self.assertEqual(self.root.node['pos'], original['pos'])
        self.assertEqual(self.images(), [])
        self.assertFalse(list(self.graph.fetch('[n:ImageData]')))
        self.assertFalse(list(self.root.node.outE('e.kind="With"')))

    def test_failed_text_checkpoint_blocks_image_and_retains_unsaved_draft(self):
        self.view.inline.textMode = True
        self.view.inline.start(self.root)
        item = self.view.inline.item
        cursor = item.textCursor(); cursor.insertText(' unsaved'); item.setTextCursor(cursor)
        self.clipboard_image()
        with mock.patch.object(self.root.node, 'save', side_effect=OSError('disk full')), self.assertLogs(level='ERROR'):
            self.paste()
        self.assertIs(self.view.inline.item, item)
        self.assertIn('unsaved', item.toPlainText())
        self.assertFalse(list(self.graph.fetch('[n:ImageData]')))

    def test_child_save_failure_rolls_back_parent_geometry_and_all_image_data(self):
        child = self.child(self.root, 'Child', 70)
        before = copy.deepcopy(self.root.node.data)
        child_transform = child.sceneTransform()
        origin = self.root.leaf.mapToScene(QtCore.QPointF())
        self.select(self.root)
        self.clipboard_image()
        self.graph.clearchanges()
        save = graphydb.Node.save
        def fail(node, *args, **kwargs):
            if node['uid'] == child.node['uid'] and kwargs.get('batch'):
                raise OSError('disk full')
            return save(node, *args, **kwargs)
        with mock.patch.object(graphydb.Node, 'save', fail), self.assertLogs(level='ERROR'):
            self.scene.paste()
        self.assertEqual(self.graph.getuid(self.root.node['uid'])['content'], before['content'])
        self.assertEqual(self.root.node['pos'], before['pos'])
        self.assertEqual(self.root.leaf.mapToScene(QtCore.QPointF()), origin)
        self.assertEqual(child.sceneTransform(), child_transform)
        self.assertEqual(self.images(), [])
        self.assertFalse(list(self.graph.fetch('[n:ImageData]')))
        self.assertFalse(self.graph.lastchanges())

    def test_iconified_node_rejects_paste_rather_than_hiding_new_content_on_reopen(self):
        self.root.node['iconified'] = True
        self.root.node.save(); self.root.renew()
        self.select(self.root)
        self.clipboard_image()
        self.graph.clearchanges()
        self.scene.paste()
        self.assertFalse(self.graph.lastchanges())
        self.assertFalse(list(self.graph.fetch('[n:ImageData]')))

    def test_rotated_left_node_hidden_child_and_task_state_preserved(self):
        stem = self.child(self.root, 'Left', -100, flip=-1)
        stem.node['angle'], stem.node['todo'], stem.node['todo_done'] = 25, True, True
        stem.node.save(); stem.renew()
        child = self.child(stem, 'Hidden', 20)
        uid = child.node['uid']
        point = child.mapToScene(QtCore.QPointF())
        child.node['hide'] = True; child.node.save(); stem.renew()
        origin = stem.leaf.mapToScene(QtCore.QPointF())
        self.select(stem)
        self.clipboard_image()
        self.scene.paste()
        self.assertTrue(stem.node['todo_done'])
        self.assertAlmostEqual(stem.leaf.mapToScene(QtCore.QPointF()).x(), origin.x())
        self.assertAlmostEqual(stem.leaf.mapToScene(QtCore.QPointF()).y(), origin.y())
        node = self.graph.getuid(uid)
        node.discard('hide'); node.save(); stem.renew()
        revealed = next(c for c in stem.childStems2 if c.node['uid'] == uid)
        self.assertAlmostEqual(revealed.mapToScene(QtCore.QPointF()).x(), point.x())
        self.assertAlmostEqual(revealed.mapToScene(QtCore.QPointF()).y(), point.y())

    def test_selection_and_readonly_guards_and_invalid_image(self):
        other = self.child(self.root, 'Other', 100)
        self.clipboard_image()
        self.graph.clearchanges()
        for selected in ([], [self.root, other]):
            self.scene.clearSelection()
            for stem in selected:
                stem.setSelected(True)
            self.scene.paste()
            self.assertFalse(self.graph.lastchanges())
        self.select(self.root)
        self.scene.mode = 'presentation'
        self.scene.paste()
        self.scene.mode = 'edit'
        self.view.inline.preedit = True
        self.scene.paste()
        self.view.inline.preedit = False
        self.assertFalse(self.graph.lastchanges())
        mime = QtCore.QMimeData(); mime.setImageData(QtGui.QImage())
        self.assertFalse(image_paste.paste_image(self.scene, mime, self.view))

    def test_branch_copies_with_image_fallback_and_plain_text_paste_unchanged(self):
        self.select(self.root)
        self.clipboard_image()
        mime = self.app.clipboard().mimeData()
        copied = self.graph.copyTrees(graphydb.NSet([self.root.node]))
        copied.setMimedata(mime)
        self.assertFalse(image_paste.is_external_image(mime))
        self.scene.paste()
        self.assertEqual(self.images(), [])
        self.assertEqual(len(self.root.childStems2), 1)
        self.view.inline.textMode = True
        self.view.inline.start(self.root)
        self.app.clipboard().setText(' plain pasted')
        self.paste()
        self.assertIn('plain pasted', self.view.inline.item.toPlainText())
