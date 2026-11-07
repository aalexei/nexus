"""Restore a normal floating editor on an available monitor, without auto-fit."""
from math import hypot
from PyQt6 import QtCore, QtWidgets


def restore(dialog, map_view):
    settings = QtCore.QSettings('Ectropy', 'Nexus')
    screens = QtWidgets.QApplication.screens()
    screen_name = settings.value('editorScreen', '')
    screen = next((s for s in screens if s.name() == screen_name), None)
    screen = screen or (map_view.screen() if map_view is not None else QtWidgets.QApplication.primaryScreen())
    area = screen.availableGeometry()
    saved = settings.value('editorGeometry')
    if saved is not None and dialog.restoreGeometry(saved):
        rect = dialog.normalGeometry()
        dialog.setWindowState(QtCore.Qt.WindowState.WindowNoState)
        if rect.isEmpty():
            rect = dialog.geometry()
    else:
        width = max(dialog.minimumSizeHint().width(), area.width() // 2)
        height = max(dialog.minimumSizeHint().height(), int(area.height() * .7))
        rect = QtCore.QRect(area.x() + (area.width() - width) // 2,
                            area.y() + (area.height() - height) // 2, width, height)
    # Missing monitor or changed resolution: keep the entire window reachable.
    target = next((s for s in screens if s.availableGeometry().contains(rect.center())), screen)
    area = target.availableGeometry()
    rect.setWidth(min(rect.width(), area.width()))
    rect.setHeight(min(rect.height(), area.height()))
    rect.moveLeft(max(area.left(), min(rect.left(), area.right() - rect.width() + 1)))
    rect.moveTop(max(area.top(), min(rect.top(), area.bottom() - rect.height() + 1)))
    dialog.setGeometry(rect)
    try:
        zoom = float(settings.value('editorZoom', 1.25))
    except (TypeError, ValueError):
        zoom = 1.25
    if not .1 <= zoom <= 10:
        zoom = 1.25
    dialog.view.resetTransform()
    dialog.view.scale(zoom, zoom)


def save(dialog):
    settings = QtCore.QSettings('Ectropy', 'Nexus')
    settings.setValue('editorGeometry', dialog.saveGeometry())
    settings.setValue('editorScreen', dialog.screen().name())
    transform = dialog.view.transform()
    settings.setValue('editorZoom', hypot(transform.m11(), transform.m12()))
