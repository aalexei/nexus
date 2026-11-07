"""Isolate named QSettings too: setDefaultFormat alone does not affect them."""
from unittest import mock
from PyQt6 import QtCore


def isolate_settings(directory):
    original = QtCore.QSettings

    class TemporarySettings(original):
        def __init__(self, *args, **kwargs):
            if len(args) >= 2 and isinstance(args[0], str) and isinstance(args[1], str):
                super().__init__(original.Format.IniFormat, original.Scope.UserScope, *args, **kwargs)
            else:
                super().__init__(*args, **kwargs)
            self.setFallbacksEnabled(False)

    original.setPath(original.Format.IniFormat, original.Scope.UserScope, str(directory))
    return mock.patch.object(QtCore, 'QSettings', TemporarySettings)
