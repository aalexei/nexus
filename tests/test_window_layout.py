"""Real map-window sizing, sidebar balance, reopening and initial camera fit."""
from contextlib import ExitStack
from pathlib import Path
import unittest
from unittest import mock

import test_keyboard_navigation as navigation
from PyQt6 import QtCore, QtWidgets
from nexus import graphics, mainwindow, window_layout


class WindowLayoutTests(unittest.TestCase):
    setUpClass = classmethod(navigation.KeyboardNavigationTests.setUpClass.__func__)
    tearDownClass = classmethod(navigation.KeyboardNavigationTests.tearDownClass.__func__)
    child = navigation.KeyboardNavigationTests.child
    node = navigation.KeyboardNavigationTests.node

    def setUp(self):
        navigation.KeyboardNavigationTests.setUp(self)
        self.settings_store = QtCore.QSettings('Ectropy', 'Nexus')
        self.settings_store.clear()
        self.graph.savesetting('version', graphics.VERSION)
        self.windows = []
        self.services = ExitStack()
        for name, value in (
            ('updateWindowMenu', lambda: None), ('createViewImage', lambda view: None),
            ('dialogOpen', lambda: None), ('toggleStreaminServer', lambda: None),
            ('streaming', False), ('windowMenu', QtWidgets.QMenu('Window'))):
            self.services.enter_context(mock.patch.object(self.app, name, value, create=True))

    def tearDown(self):
        for window in list(self.windows):
            self.close_window(window)
        self.services.close()
        navigation.KeyboardNavigationTests.tearDown(self)

    def close_window(self, window):
        if window not in self.windows:
            return
        self.windows.remove(window)
        window.editDialog.hide()
        window.editDialog.deleteLater()
        window.close()
        self.app.processEvents()

    def open_window(self):
        window = mainwindow.MainWindow(self.graph.path)
        self.windows.append(window)
        window.show()
        window.activateWindow()
        self.app.processEvents()
        self.app.processEvents()
        return window

    def test_default_and_legacy_tiny_window_open_larger_with_balanced_sidebar(self):
        self.settings_store.setValue('size', QtCore.QSize(400, 400))
        window = self.open_window()
        area = window.screen().availableGeometry()
        self.assertGreater(window.width(), min(800, int(area.width() * .75)))
        self.assertGreater(window.height(), min(550, int(area.height() * .65)))
        self.assertLess(window.contentsDock.width(), window.width() * .45)
        self.assertGreater(window.view.viewport().width(), window.contentsDock.width())
        self.assertFalse(window.isFullScreen())
        self.assertFalse(window.toolBarBreak(window.viewToolBar))
        self.assertLessEqual(window.filterEdit.maximumWidth(), 160)

    def test_window_geometry_and_user_sidebar_width_survive_reopening(self):
        window = self.open_window()
        area = window.screen().availableGeometry()
        size = QtCore.QSize(min(1000, area.width() - 60), min(650, area.height() - 80))
        window.resize(size)
        window.move(area.topLeft() + QtCore.QPoint(25, 35))
        window.resizeDocks([window.contentsDock], [300], QtCore.Qt.Orientation.Horizontal)
        self.app.processEvents()
        actual_size, actual_pos = window.size(), window.pos()
        actual_width = window.contentsDock.width()
        self.close_window(window)
        reopened = self.open_window()
        self.assertEqual(reopened.size(), actual_size)
        self.assertLessEqual((reopened.pos() - actual_pos).manhattanLength(), 4)
        self.assertLessEqual(abs(reopened.contentsDock.width() - actual_width), 3)
        self.assertTrue(reopened.contentsDock.isVisible())

    def test_saved_offscreen_window_and_oversized_sidebar_remain_reachable(self):
        self.settings_store.setValue('pos', QtCore.QPoint(30000, -30000))
        self.settings_store.setValue('size', QtCore.QSize(9000, 7000))
        self.settings_store.setValue('contentsWidth', 4000)
        self.settings_store.setValue('mainWindowScreen', 'Disconnected external monitor')
        window = self.open_window()
        area = window.screen().availableGeometry()
        self.assertTrue(area.contains(window.geometry()))
        self.assertGreaterEqual(window.view.viewport().width(), 320)
        self.assertLess(window.contentsDock.width(), window.width() - 320)

    def test_newly_saved_smaller_window_is_not_replaced_by_default(self):
        window = self.open_window()
        window.resize(min(640, window.width() - 40), min(550, window.height() - 30))
        self.app.processEvents()
        size = window.size()
        self.close_window(window)
        reopened = self.open_window()
        self.assertEqual(reopened.size(), size)
        self.assertGreater(reopened.view.viewport().width(), reopened.contentsDock.width())

    def test_hidden_contents_reopens_hidden_without_changing_user_zoom_on_resize(self):
        self.settings_store.setValue('contentsVisible', False)
        window = self.open_window()
        self.assertTrue(window.contentsDock.isHidden())
        window.view.scale(1.37, 1.37)
        transform = window.view.transform()
        window.resize(window.width() - 40, window.height() - 40)
        self.app.processEvents()
        window.hide()
        window.show()
        self.app.processEvents()
        self.assertEqual(window.view.transform(), transform)
        self.close_window(window)
        self.assertTrue(self.open_window().contentsDock.isHidden())

    def test_initial_map_fit_waits_for_sidebar_and_toolbars(self):
        self.child(self.root, 'Far upper branch', -1200)
        self.child(self.root, 'Far lower branch', 1200)
        window = self.open_window()
        visible = window.view.mapToScene(window.view.viewport().rect()).boundingRect()
        for stem in window.scene.visibleStemsById().values():
            self.assertTrue(visible.contains(stem.leaf.sceneBoundingRect()), stem.node['uid'])
        self.assertTrue(window._initialLayoutDone)
        self.assertFalse(window._initialLayoutTimer.isActive())

    def test_maximized_state_survives_reopening_and_presentation_roundtrip(self):
        window = self.open_window()
        window.showMaximized()
        self.app.processEvents()
        self.assertTrue(window.isMaximized())
        window.presentationModeAct.trigger()
        self.app.processEvents()
        window.editModeAct.trigger()
        self.app.processEvents()
        self.assertTrue(window.isMaximized())
        self.close_window(window)
        reopened = self.open_window()
        self.assertTrue(reopened.isMaximized())
        self.assertFalse(reopened.isFullScreen())

    def test_closing_in_presentation_does_not_save_fullscreen_as_edit_layout(self):
        window = self.open_window()
        size = window.size()
        window.viewFullscreenPresentationAct.setChecked(True)
        window.presentationModeAct.trigger()
        self.app.processEvents()
        self.assertTrue(window.isFullScreen())
        self.close_window(window)
        reopened = self.open_window()
        self.assertFalse(reopened.isFullScreen())
        self.assertEqual(reopened.size(), size)

    def test_clamping_handles_changed_monitor_bounds(self):
        area = QtCore.QRect(-1600, 0, 1600, 900)
        result = window_layout.clamp_rect(QtCore.QRect(3000, -2000, 4000, 2000), area)
        self.assertTrue(area.contains(result))
        self.assertLess(result.width(), area.width())
        self.assertLess(result.height(), area.height())


if __name__ == '__main__':
    unittest.main()
