"""Comfortable map-window defaults and reachable, persistent geometry."""
from PyQt6 import QtCore, QtWidgets


def available_area(window, settings):
    screens = QtWidgets.QApplication.screens()
    name = settings.value('mainWindowScreen', '')
    screen = next((screen for screen in screens if screen.name() == name), None)
    screen = screen or window.screen() or QtWidgets.QApplication.primaryScreen()
    return screen.availableGeometry()


def clamp_rect(rect, area):
    # Leave room for native window borders/title bar, not just client contents.
    usable = area.adjusted(8, 28, -8, -8)
    rect = QtCore.QRect(rect)
    rect.setWidth(min(max(1, rect.width()), usable.width()))
    rect.setHeight(min(max(1, rect.height()), usable.height()))
    rect.moveLeft(max(usable.left(), min(rect.left(), usable.right() - rect.width() + 1)))
    rect.moveTop(max(usable.top(), min(rect.top(), usable.bottom() - rect.height() + 1)))
    return rect


def restore(window):
    settings = QtCore.QSettings('Ectropy', 'Nexus')
    area = available_area(window, settings)
    default = QtCore.QSize(min(1280, int(area.width() * .9)), min(900, int(area.height() * .85)))
    saved = settings.value('mainWindowGeometry')
    restored = isinstance(saved, QtCore.QByteArray) and window.restoreGeometry(saved)
    maximized = restored and window.isMaximized()
    if restored:
        rect = window.normalGeometry()
        if rect.isEmpty():
            rect = window.geometry()
        screens = QtWidgets.QApplication.screens()
        target = next((s for s in screens if s.availableGeometry().contains(rect.center())), None)
        if target is not None:
            area = target.availableGeometry()
    else:
        size = settings.value('size', default)
        # Migrate the old 400x400 default/undersized legacy layout once. New
        # saved geometry still respects deliberate smaller window sizes.
        if not isinstance(size, QtCore.QSize) or size.width() < min(860, default.width()) or size.height() < min(560, default.height()):
            size = default
        pos = settings.value('pos')
        if not isinstance(pos, QtCore.QPoint):
            pos = QtCore.QPoint(area.x() + (area.width() - size.width()) // 2,
                               area.y() + (area.height() - size.height()) // 2)
        rect = QtCore.QRect(pos, size)
    # Never reopen directly into a fullscreen Space. Preserve maximization.
    window.view.setMinimumSize(min(320, int(area.width() * .4)), min(240, int(area.height() * .4)))
    window.setWindowState(QtCore.Qt.WindowState.WindowNoState)
    window.setGeometry(clamp_rect(rect, area))
    if maximized:
        window.setWindowState(QtCore.Qt.WindowState.WindowMaximized)
    try:
        window._contentsWidth = int(settings.value('contentsWidth', 260))
    except (TypeError, ValueError):
        window._contentsWidth = 260
    window.contentsDock.setVisible(settings.value('contentsVisible', True, type=bool))
    size_contents(window)


def size_contents(window):
    # A restored sidebar cannot squeeze the canvas back into a narrow strip.
    width = max(190, min(window._contentsWidth, max(190, window.width() - 360)))
    window.resizeDocks([window.contentsDock], [width], QtCore.Qt.Orientation.Horizontal)


def save(window):
    settings = QtCore.QSettings('Ectropy', 'Nexus')
    in_edit = window.scene.mode == 'edit'
    geometry = window.saveGeometry() if in_edit else getattr(window, '_editingGeometry', window.saveGeometry())
    settings.setValue('mainWindowGeometry', geometry)
    settings.setValue('mainWindowScreen', window.screen().name())
    normal = window.normalGeometry()
    if normal.isEmpty():
        normal = window.geometry()
    settings.setValue('pos', normal.topLeft())
    settings.setValue('size', normal.size())
    if in_edit and window.contentsDock.isVisible() and not window.contentsDock.isFloating():
        settings.setValue('contentsWidth', window.contentsDock.width())
    elif not in_edit and hasattr(window, '_editingContentsWidth'):
        settings.setValue('contentsWidth', window._editingContentsWidth)
    settings.setValue('contentsVisible', not window.contentsDock.isHidden())
