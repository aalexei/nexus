##
## Copyright 2010-2024 Alexei Gilchrist
##
## This file is part of Nexus.
##
## Nexus is free software: you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published by
## the Free Software Foundation, either version 3 of the License, or
## (at your option) any later version.
##
## Nexus is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with Nexus.  If not, see <http://www.gnu.org/licenses/>.

import time
#from PyQt6 import QtCore, QtGui, QtWidgets
from PySide6 import QtCore, QtGui, QtWidgets

from . import resources
import logging

DEFAULTpencols = [
    ['#FFE53935','#FFD81A60','#FF8E24AA','#FF5E34B1','#FF3949AB'],
    ['#FF1F88E5','#FF049BE5','#FF00ACC2','#FF01897B','#FF43A047'],
    ['#FF7BB342','#FFC0CA33','#FFFDD835','#FFFFB302','#FFFB8C00'],
    ['#FFF4511F','#FF6D4C41','#FF757575','#FF546E7A','#FF000000'],
]

DEFAULThicols = [
    ['#60E53935','#60D81A60','#608E24AA','#605E34B1','#603949AB'],
    ['#601F88E5','#60049BE5','#6000ACC2','#6001897B','#6043A047'],
    ['#607BB342','#60C0CA33','#60FDD835','#60FFB302','#60FB8C00'],
    ['#60F4511F','#606D4C41','#60757575','#60546E7A','#60000000'],
]

DEFAULTpensizes = [1.0, 1.5, 2.0, 2.5, 3.0]

DEFAULThisizes = [5,10,15,20,25]

##----------------------------------------------------------------------
class ColorSwatch(QtWidgets.QLabel):
##----------------------------------------------------------------------

    #clicked = QtCore.pyqtSignal(QtGui.QColor)
    clicked = QtCore.Signal(QtGui.QColor)
    #colorChanged = QtCore.pyqtSignal(int, int, QtGui.QColor)
    colorChanged = QtCore.Signal(int, int, QtGui.QColor)

    def __init__(self, idx, color, selected=False, parent=None):
        super().__init__(parent)
        self.color = color
        self.idx = idx
        self.selected = selected
        self.drawSwatch()

    def drawSwatch(self):
        s = 32
        pix = QtGui.QPixmap(s,s)

        painter = QtGui.QPainter()
        painter.begin(pix)
        painter.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_SourceOver)

        ## Draw black and white triangles to show off semi-opaque colors
        path = QtGui.QPainterPath()
        path.addRect(0,0,s,s)
        painter.fillPath(path, QtGui.QBrush(QtCore.Qt.GlobalColor.white))
        path = QtGui.QPainterPath()
        path.addPolygon(QtGui.QPolygonF([QtCore.QPointF(0,0),QtCore.QPointF(s,0),QtCore.QPointF(0,s)]))
        painter.fillPath(path, QtGui.QBrush(QtCore.Qt.GlobalColor.black))

        ## now add color on top
        path = QtGui.QPainterPath()
        path.addRect(0,0,s,s)
        painter.fillPath(path, QtGui.QBrush(self.color))

        if self.selected:
            pen = QtGui.QPen(QtCore.Qt.GlobalColor.black)
            pen.setWidth(4)
            pen.setJoinStyle(QtCore.Qt.PenJoinStyle.MiterJoin)
            painter.setPen(pen)
            painter.drawRect(2,2,s-4,s-4)

        painter.end()

        self.setPixmap(pix)

    def mousePressEvent(self, event):
        self.time = time.time()

    def mouseReleaseEvent(self, event):
        dt = time.time() - self.time
        if dt<1:
            self.clickEvent(event)
        else:
            self.longClickEvent(event)

    def clickEvent(self, event):
        self.clicked.emit(self.color)

    def longClickEvent(self, event):
        out=QtWidgets.QColorDialog.getColor(self.color, options=QtWidgets.QColorDialog.ColorDialogOption.ShowAlphaChannel)
        if out.isValid():
            self.color = out
            self.drawSwatch()
            self.colorChanged.emit(self.idx[0], self.idx[1], self.color)


##----------------------------------------------------------------------
class SizeSwatch(QtWidgets.QLabel):
##----------------------------------------------------------------------

    #clicked = QtCore.pyqtSignal(float)
    clicked = QtCore.Signal(float)
    #sizeChanged = QtCore.pyqtSignal(int, float)
    sizeChanged = QtCore.Signal(int, float)

    def __init__(self, idx, size, selected=False, kind="pen", parent=None):
        super().__init__(parent)
        self.idx = idx
        self.size = size
        self.kind = kind
        self.selected = selected
        self.drawSwatch()

    def drawSwatch(self):
        s = 32
        pix = QtGui.QPixmap(s,s)

        if self.kind=="pen":
            size = self.size*2.0
        else:
            size = self.size/2.0

        painter = QtGui.QPainter()
        painter.begin(pix)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_SourceOver)

        ## Draw black and white triangles to show off semi-opaque colors
        path = QtGui.QPainterPath()
        path.addRect(0,0,s,s)
        painter.fillPath(path, QtGui.QBrush(QtCore.Qt.GlobalColor.white))
        path = QtGui.QPainterPath()
        path.addEllipse(QtCore.QPointF(s/2,s/2), size, size)
        painter.fillPath(path, QtGui.QBrush(QtCore.Qt.GlobalColor.black))

        if self.selected:
            pen = QtGui.QPen(QtCore.Qt.GlobalColor.black)
            pen.setWidth(4)
            pen.setJoinStyle(QtCore.Qt.PenJoinStyle.MiterJoin)
            painter.setPen(pen)
            painter.drawRect(2,2,s-4,s-4)

        painter.end()

        self.setPixmap(pix)

        #self.setText("%.1f"%self.size )

    def mousePressEvent(self, event):
        self.time = time.time()

    def mouseReleaseEvent(self, event):
        dt = time.time() - self.time
        if dt<1:
            self.clickEvent(event)
        else:
            self.longClickEvent(event)

    def clickEvent(self, event):
        self.clicked.emit(self.size)

    def longClickEvent(self, event):
        s, status = QtWidgets.QInputDialog.getDouble(self, "Enter width", "Width:", self.size, 0.1, 10)
        if status:
            self.size = s
            self.drawSwatch()
            self.sizeChanged.emit(self.idx, self.size)

##----------------------------------------------------------------------
## PenDialog - dialog for setting pen options
class PenDialog(QtWidgets.QDialog):
##----------------------------------------------------------------------

    def __init__(self, pen, kind, parent=None):
        super().__init__(parent)

        self.pen = pen
        pencolor = pen.color()
        pensize = pen.widthF()

        if kind=="pen":
            self.setWindowTitle("Pen Properties")
        else:
            self.setWindowTitle("Highlighter Properties")

        colorGroup = QtWidgets.QGroupBox(self.tr("Colour"))
        sizeGroup = QtWidgets.QGroupBox(self.tr("Size"))

        grid = QtWidgets.QGridLayout()
        colorGroup.setLayout(grid)

        settings = QtCore.QSettings("Ectropy", "Nexus")

        for r in range(len(DEFAULTpencols)):
            for c in range(len(DEFAULTpencols[0])):
                if kind=="pen":
                    swatchcolor = QtGui.QColor(settings.value("input/pencolor[%d,%d]"%(r,c), DEFAULTpencols[r][c]))
                else:
                    swatchcolor = QtGui.QColor(settings.value("input/hicolor[%d,%d]"%(r,c), DEFAULThicols[r][c]))
                w = ColorSwatch((r,c), swatchcolor, selected=(pencolor.name(QtGui.QColor.NameFormat.HexArgb)==swatchcolor.name(QtGui.QColor.NameFormat.HexArgb)), parent=self)
                grid.addWidget(w,r,c)
                w.clicked.connect(self.setColor)
                w.colorChanged.connect(self.changeColor)


        grid = QtWidgets.QGridLayout()
        sizeGroup.setLayout(grid)

        for r in range(len(DEFAULTpensizes)):
            if kind=="pen":
                swatchsize = settings.value("input/pensize[%s]"%r, DEFAULTpensizes[r])
            else:
                swatchsize = settings.value("input/hisize[%s]"%r, DEFAULThisizes[r])
            w = SizeSwatch(r, swatchsize, selected=(pensize==swatchsize), kind=kind, parent=self)
            grid.addWidget(w,r,0)
            w.clicked.connect(self.setSize)
            w.sizeChanged.connect(self.changeSize)

        mainLayout = QtWidgets.QHBoxLayout()
        mainLayout.addWidget(colorGroup)
        mainLayout.addWidget(sizeGroup)
        self.setLayout(mainLayout)

    def setColor(self, color):
        self.pen.setColor(color)
        super().accept()

    def setSize(self, size):
        self.pen.setWidthF(size)
        super().accept()

    @staticmethod
    def changeColor(idx0, idx1, color):
        settings = QtCore.QSettings("Ectropy", "Nexus")
        settings.setValue("input/pencolor[%d,%d]"%(idx0, idx1), color.name(QtGui.QColor.NameFormat.HexArgb))

    @staticmethod
    def changeSize(idx, size):
        settings = QtCore.QSettings("Ectropy", "Nexus")
        settings.setValue("input/pensize[%d]"%idx, size)

