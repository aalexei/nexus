"""Qt event regression tests; all map and settings data stays temporary.

Run: QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests -v
"""
import os
import tempfile
import unittest
from settings_helpers import isolate_settings

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt6 import QtCore, QtGui, QtWidgets, QtTest
from nexus import graphics, nexusgraph, graphydb, resources


class MapTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = tempfile.TemporaryDirectory()
        cls.settingsIsolation = isolate_settings(cls.settings.name)
        cls.settingsIsolation.start()
        QtCore.QSettings.setDefaultFormat(QtCore.QSettings.Format.IniFormat)
        QtCore.QSettings.setPath(QtCore.QSettings.Format.IniFormat,
                                 QtCore.QSettings.Scope.UserScope, cls.settings.name)
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        cls.app.setProperty('nexusTestMode', True)

    @classmethod
    def tearDownClass(cls):
        cls.app.setProperty('nexusTestMode', False)
        cls.settingsIsolation.stop()
        cls.settings.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.graph = nexusgraph.NexusGraph(os.path.join(self.tmp.name, 'test.nexus'))
        self.scene = graphics.NexusScene()
        self.scene.graph = self.graph
        node = self.node('Root label')
        self.graph.Edge(self.graph.Node('Root').save(), 'Child', node).save()
        self.root = graphics.StemItem(node, scene=self.scene)
        self.root.renew()
        self.view = graphics.NexusView(self.scene)
        # Legacy map commands remain available with Text mode off. Inline mode
        # has its own real-key regression suite.
        if hasattr(self.view, 'inline'):
            self.view.inline.textMode = False
        self.view.resize(900, 650)
        self.view.show()
        self.view.activateWindow()
        self.view.setFocus()
        self.opened = []
        self.scene.showEditDialog.connect(self.opened.append)
        self.scene.showEditDialog.connect(lambda stem: stem.renew(reload=False))
        self.app.processEvents()

    def tearDown(self):
        if hasattr(self.view, 'inline'):
            self.view.inline.finish()
        if hasattr(self, 'dialog'):
            self.dialog.hide()
            self.dialog.deleteLater()
        self.view.hide()
        self.view.deleteLater()
        self.scene.deleteLater()
        self.app.processEvents()
        self.graph.close()
        self.tmp.cleanup()

    def node(self, text, pos=(0, 0), flip=1):
        return self.graph.Node('Stem', scale=1.0, flip=flip, pos=list(pos),
            content={graphydb.generateUUID(): {'kind': 'Text', 'source': text,
                     'frame': graphics.Transform().tolist(), 'z': 0}}).save()

    def child(self, parent, text, y=0, flip=1):
        node = self.node(text, (200, y), flip)
        self.graph.Edge(parent.node, 'Child', node).save()
        parent.renew()
        return next(s for s in parent.childStems2 if s.node['uid'] == node['uid'])

    def select(self, stem):
        self.scene.clearSelection()
        stem.setSelected(True)

    def selected(self):
        return [s for s in self.scene.selectedItems() if isinstance(s, graphics.StemItem)]

    def key(self, key, modifiers=QtCore.Qt.KeyboardModifier.NoModifier):
        QtTest.QTest.keyClick(self.view, key, modifiers)
        self.app.processEvents()

