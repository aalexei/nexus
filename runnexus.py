#!/usr/bin/env python3
#
# Copyright 2010-2025 Alexei Gilchrist
#
# This file is part of Nexus.
#
# Nexus is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Nexus is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Nexus.  If not, see <http://www.gnu.org/licenses/>.

import sys,  time
from PyQt6 import QtCore, QtGui, QtWidgets

from nexus.mainwindow import MainWindow, NexusApplication, NewOrOpenDialog
from pathlib import Path
from nexus.graphics import VERSION
import logging

#import cProfile
# if hasattr(QtCore.Qt, 'AA_EnableHighDpiScaling'):
#     QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
# if hasattr(QtCore.Qt, 'AA_UseHighDpiPixmaps'):
#     QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)

if __name__ == "__main__":
    app = NexusApplication()

    # app.processEvents()

    validfiles = []
    for filename in sys.argv[1:]:
        f = Path(filename).resolve()
        if f.exists():
            validfiles.append(f.as_posix())

    for f in validfiles:
        app.raiseOrOpen(f)

    # if nothing has been opened then do dialog
    if len(app.windowList())==0:
        d = NewOrOpenDialog()
        # d.exec_()
        d.show()
        # d.activateWindow()

    #cProfile.run('app.exec_()','stats')
    app.exec()
