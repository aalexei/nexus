##
## Copyright 2010-2022 Alexei Gilchrist
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

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import pyqtSlot

from math import sqrt, atan2, cos, sin, pi, asin, degrees, pow, exp, fmod
import logging

from bs4 import BeautifulSoup

import re, time, copy, hashlib, json
from . import interpreter, tools, graphydb, config, nexusgraph

import urllib.parse, os
from functools import reduce
import random
import functools, collections

import platform

CONFIG = config.get_config()

SelectMode = 0
TextMode = 1
PenMode = 2
EraserMode = 3

# Mouse press states
MPRESS, MMOVE, MLONG, MDOUBLE, MADD = 1,2,3,4,5

VERSION=0.87

##----------------------------------------------------------------------
class Transform(QtGui.QTransform):
    '''
    Add some functionality to QT's QTransform
    '''

    def toxml(self):
        return "[{}, {}, {}, {}, {}, {}, {}, {}, {}]".format(
            self.m11(),self.m12(),self.m13(),
            self.m21(),self.m22(),self.m23(),
            self.m31(),self.m32(),self.m33())

    def tolist(self):
        return [
            self.m11(),self.m12(),self.m13(),
            self.m21(),self.m22(),self.m23(),
            self.m31(),self.m32(),self.m33()]

    @classmethod
    def fromxml(c,s):
        '''
        expects a string like "[8.94, 0.0, 1.605, 0.0, 8.94, 0.0, -28.35, -5.78, 1.0]"
        '''
        numbers = re.findall('(-?\d+\.?(?:\d+)?(?:e[+-]\d+)?)',s)
        if len(numbers)!=9:
            raise Exception

        numbers = list(map(lambda x:eval(x), numbers))

        return c(*numbers)

    def getRotation(self):
        # Assumes scaling same in x and y!
        # XXX make general
        x0,y0 = self.map(0.0,0.0)
        x1,y1 = self.map(1.0,0.0)
        angle = atan2(y1-y0,x1-x0) # between -pi and pi
        if angle<0:
            # make between 0 and 2pi
            angle = 2*pi+angle
        return angle

    def getScale(self):
        sx = sqrt(self.m11()**2+self.m12()**2)
        sy = sqrt(self.m12()**2+self.m22()**2)

        return sx,sy

    def getXScale(self):
        sx,sy = self.getScale()
        return sx

    def getTRS(self):
        dx = self.m31()
        dy = self.m32()
        r = self.getRotation()
        sx,sy = self.getScale()

        return [dx,dy,r,sx]

    def setTRS(self,dx,dy,r,s, origin=(0,0), reset=True):
        if reset:
            self.reset()
        self.translate(-origin[0],-origin[1])
        self.translate(dx,dy).rotateRadians(r).scale(s,s)
        self.translate(origin[0],origin[1])
        return self

    def __repr__(self):
        return "[[{}, {}, {}], [{}, {}, {}], [{}, {}, {}]]".format(
            self.m11(),self.m12(),self.m13(),
            self.m21(),self.m22(),self.m23(),
            self.m31(),self.m32(),self.m33())

##----------------------------------------------------------------------
def scaleRotateMove(scale=1.0, angle=0.0, dx=0.0, dy=0.0):
    scale = float(scale)
    T = QtGui.QTransform().translate(dx,dy).scale(scale, scale).rotate(angle)
    return T

##----------------------------------------------------------------------
def pressureCurve(p, x1=0.5, y1=0.5):
    '''
    Return presure curve using quadratic bezier with points
    (0,0)-(x1,y1)-(1,1)
    '''
    if x1==0.5:
        return 2*(1-p)*p*y1+p**2
    else:
        return (p*(2*x1-1)*(2*y1-1)-2*(sqrt(p-2*p*x1+x1**2)-x1)*(x1-y1))/(1-2*x1)**2

##----------------------------------------------------------------------
class OverView(QtWidgets.QDialog):
##----------------------------------------------------------------------

    def __init__(self, scene,  parent=None):

        super().__init__(parent)

        self.scene = scene

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.view = QtWidgets.QGraphicsView(scene)
        layout.addWidget(self.view)
        self.setLayout(layout)

        #self.connect(self.scene, QtCore.SIGNAL('changed (const QList<QRectF>&)'), self.viewChange)

    def viewChange(self, rect):

        self.view.fitInView(self.scene.itemsBoundingRect())

##----------------------------------------------------------------------
class InputDialog(QtWidgets.QDialog):
##----------------------------------------------------------------------

    # TODO item grouping
    # TODO apply colour changes to selected items

    WIDTHmin = 1000
    HEIGHTmin = 200

    def __init__(self):
        super().__init__(None)

        #self.setSizeGripEnabled(True)
        self.setWindowFlag(QtCore.Qt.Window, True)

        ## create main layout
        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setLayout(layout)

        dialogMenuBar = QtWidgets.QMenuBar(self)
        layout.addWidget(dialogMenuBar)

        self.toolbar = QtWidgets.QToolBar()
        self.toolbar.setOrientation(QtCore.Qt.Horizontal)
        self.toolbar.setIconSize(QtCore.QSize(32,32))
        #self.toolbar.setMovable(True)
        #self.toolbar.setFloatable(True)
        layout.addWidget(self.toolbar)

        ## tab widget to hold main editing components
        stackedwidget = QtWidgets.QStackedWidget(self)
        layout.addWidget(stackedwidget)
        self.stackedwidget = stackedwidget

        ## editing widget
        editwidget = QtWidgets.QWidget()
        stackedwidget.addWidget(editwidget)
        elayout = QtWidgets.QVBoxLayout(editwidget)
        elayout.setSpacing(0)
        elayout.setContentsMargins(0,0,0,0)

        ## properties widget
        propwidget = QtWidgets.QWidget()
        stackedwidget.addWidget(propwidget)

        stackedwidget.setCurrentIndex(0)


        self.view = InkView(None)
        elayout.addWidget(self.view)
        # need a backref to link signal on pasted item
        # TODO better way of doing this, without backref to dialog
        self.view.input_dialog = self

        #
        # Toolbar
        #
        self.createActions()

        self.toolbar.addAction(self.closeAct)
        self.toolbar.addAction(self.propmode)

        self.toolbar.addSeparator()
        self.toolbar.addAction(self.textmode)
        self.toolbar.addAction(self.penmode)
        self.toolbar.addAction(self.highlightmode)
        self.toolbar.addAction(self.erasermode)
        self.toolbar.addAction(self.selectmode)
        self.textmode.setCheckable(True)
        self.penmode.setCheckable(True)
        self.highlightmode.setCheckable(True)
        self.erasermode.setCheckable(True)
        self.selectmode.setCheckable(True)
        modegroup = QtWidgets.QActionGroup(self.toolbar)
        modegroup.addAction(self.textmode)
        modegroup.addAction(self.penmode)
        modegroup.addAction(self.highlightmode)
        modegroup.addAction(self.erasermode)
        modegroup.addAction(self.selectmode)

        self.toolbar.addSeparator()
        self.toolbar.addAction(self.cutAct)
        self.toolbar.addAction(self.copyAct)
        self.toolbar.addAction(self.pasteAct)
        self.toolbar.addAction(self.deleteAct)

        self.toolbar.addSeparator()
        self.toolbar.addAction(self.zoomInAct)
        self.toolbar.addAction(self.zoomOutAct)


        ## extra tools for select mode
        self.toolbar.addAction(self.lowerBottomAct)
        self.toolbar.addAction(self.lowerAct)
        self.toolbar.addAction(self.raiseAct)
        self.toolbar.addAction(self.raiseTopAct)

        ## extra tools for text mode
        self.toolbar.addAction(self.sourceAct)

        self.toolbar.addAction(self.boldAct)
        self.toolbar.addAction(self.italicAct)
        self.toolbar.addAction(self.underlineAct)
        self.toolbar.addAction(self.textColorAct)
        self.toolbar.addAction(self.textBackColorAct)

        self.toolbar.addAction(self.fontAct)
        self.toolbar.addAction(self.clearFormatAct)

        self.sourceAct.setCheckable(True)


        editMenu = dialogMenuBar.addMenu(self.tr("&Edit"))
        #editMenu.addAction(self.undoAct)
        #editMenu.addSeparator()
        editMenu.addAction(self.cutAct)
        editMenu.addAction(self.copyAct)
        editMenu.addAction(self.pasteAct)
        editMenu.addSeparator()
        editMenu.addAction(self.deleteAct)
        editMenu.addSeparator()

        self.view.setFocus()

        #
        # Layout settings pane
        #
        settingslayout = QtWidgets.QHBoxLayout(propwidget)

        #
        # Branch setting
        #
        branchsettings = QtWidgets.QGroupBox("Branch settings")
        settingslayout.addWidget(branchsettings)

        playout = QtWidgets.QFormLayout(branchsettings)
        #branchsettings.setLayout(branchsettings)

        # Iconified checkbox
        self.iconCheck = QtWidgets.QCheckBox()
        self.iconCheck.setToolTip("Show Node as an icon only (good for long notes)")
        playout.addRow("Show as icon only:", self.iconCheck)
        self.iconCheck.stateChanged.connect(self.iconifiedChanged)

        # Tags
        self.tagsEdit = QtWidgets.QLineEdit()
        self.tagsEdit.setValidator(QtGui.QRegExpValidator(QtCore.QRegExp(r"[\w\s-]*")))
        self.tagsEdit.setToolTip("Enter space separated tags")
        self.tagsEdit.editingFinished.connect(self.tagsChanged)
        playout.addRow("Tags:", self.tagsEdit)

        # Scale widget
        self.scalewidget = QtWidgets.QDoubleSpinBox()
        self.scalewidget.setSingleStep(0.1)
        self.scalewidget.setToolTip("Branch scale")
        playout.addRow("Branch scale:", self.scalewidget)
        self.scalewidget.setRange(0.05, 10)
        self.scalewidget.valueChanged.connect(self.scaleWidgetChanged)

        self.setWindowTitle(self.tr("Stem input"))

        # Branch color and inherit box
        pix = QtGui.QPixmap(50, 50)
        pix.fill(QtCore.Qt.gray)
        colbutton = QtWidgets.QPushButton()
        colbutton.setToolTip("Set branch colour")
        self.branchcolorbutton = colbutton
        inheritbox = QtWidgets.QCheckBox("Inherit")
        inheritbox.setToolTip("Inherit branch colour")
        inheritbox.clicked.connect(self.branchInheritColourChanged)
        hl = QtWidgets.QHBoxLayout()
        hl.addWidget(colbutton)
        hl.addWidget(inheritbox)
        playout.addRow("Branch color:", hl)
        self.branchcolorinherit = inheritbox

        colbutton.setIcon(QtGui.QIcon(pix))
        colbutton.setFlat(True)
        colbutton.setMaximumSize(50,50)
        colbutton.clicked.connect(self.setBranchColour)
        self.branchcolorbutton = colbutton

        #
        # Dialog setting
        #
        dialogsettings = QtWidgets.QGroupBox("Dialog settings")
        settingslayout.addWidget(dialogsettings)

        dlayout = QtWidgets.QFormLayout(dialogsettings)

        # Opacity widget
        self.opacitywidget = QtWidgets.QDoubleSpinBox()
        self.opacitywidget.setSingleStep(0.1)
        self.opacitywidget.setToolTip("Dialog window opacity")
        dlayout.addRow("Opacity", self.opacitywidget)
        self.opacitywidget.setRange(0.4, 1.0)
        self.opacitywidget.setValue(1.0)
        self.opacitywidget.valueChanged.connect(self.opacityWidgetChanged)

        # default mode on creation
        self.selectmode.setChecked(True)

        # Full screen
        self.fullscreenwidget = QtWidgets.QCheckBox()
        self.fullscreenwidget.setCheckState(False)
        dlayout.addRow("Maximize dialog", self.fullscreenwidget)



    def setDialog(self, stem):

        if hasattr(self, 'scene'):
            # when dialog is first set up it won't have a scene
            self.scene.clear()

        if hasattr(self, 'stem'):
            # in case we jump straight to editing another item
            self.stem.isBeingEdited = False
            # redraw stem to remove editing mark
            self.stem.update()

        self.scene = InkScene(stem=stem, parent=self)
        self.scene.setBackgroundBrush(QtGui.QBrush(QtGui.QPixmap(":/images/gridbackground.png")))
        self.view.setScene(self.scene)

        stem.isBeingEdited = True

        # TODO simpify? why do we need stem and edge separately?
        self.stem = stem
        self.scene.node = stem.node
        #self.scene.edge = edge
        # TODO Can we remove this dependency at this point (setPenCursor calls graph settings)
        self.scene.graph = self.scene.node.graph

        if self.scene.node.get('iconified', False):
            self.iconCheck.setChecked(True)

        tags = self.scene.node.get('tags', set())
        self.tagsEdit.setText(' '.join(tags))

        self.scalewidget.setValue(float(self.scene.node.get('scale', 1.0)))
       
        pix = QtGui.QPixmap(50, 50)
        if 'branchcolor' in self.scene.node:
            branchcolor = self.scene.node['branchcolor']
            pix.fill(QtGui.QColor(branchcolor))
            self.branchcolorbutton.setDisabled(False)
            self.branchcolorinherit.setCheckState(QtCore.Qt.Unchecked)
        else:
            pix.fill(QtCore.Qt.gray)
            self.branchcolorbutton.setDisabled(True)
            self.branchcolorinherit.setCheckState(QtCore.Qt.Checked)
        self.branchcolorbutton.setIcon(QtGui.QIcon(pix))

        # TODO why calling it twice?
        self.ishighlighter = True
        self.setPenCursor()
        self.ishighlighter = False
        self.setPenCursor()
        
        #
        # Add items
        #
        self.scene.maxZ = 0
        # itemnumbers are used to set the mode
        itemnumbers = collections.Counter()
        itemrect = QtCore.QRectF()
        for k in self.scene.node.outN('e.kind = "In"'):
            if k['kind'] == 'Stroke':
                item = InkItem(k, scene=self.scene)
                itemnumbers['stroke']+=1
            elif k['kind'] == 'Text':
                item = TextItem(k, scene=self.scene)
                ## this is needed to make alignments work:
                item.positionChanged.connect(self.setTextControls)
                itemnumbers['text']+=1
            elif k['kind'] == 'Image':
                item = PixmapItem(k, scene=self.scene)
                itemnumbers['image']+=1
            else:
                item = None

            if item is not None:
                itemrect = itemrect.united(item.mapToScene(item.boundingRect()).boundingRect())

        self.view.centerOn(itemrect.center())

        # TODO clean up code
        ## set the initial mode
        #if sum(itemnumbers.values()) == 0:

        # if len(items) == 0:
        #     ## it's a new blank item, go off the mode
        #     if newdialogmode==SelectMode:
        #         self.selectmode.trigger()
        #     elif newdialogmode==PenMode:
        #         self.penmode.trigger()
        #     else:
        #         self.textmode.trigger()
        # else:
        #     if itemnumbers['image']>0 or (itemnumbers['stroke']>0 and itemnumbers['text']>0):
        #         ## if there is an image choose selection mode
        #         self.selectmode.trigger()
        #     elif itemnumbers['stroke'] > 0:
        #         ## if there is strokes choose pen mode
        #         self.penmode.trigger()
        #     else:
        #         ## otherwise text mode or that recorded in state
        #         self.textmode.trigger()

        if self.selectmode.isChecked():
            self.setSelectMode()
        elif self.penmode.isChecked():
            self.setPenMode()
        elif self.erasermode.isChecked():
            # revert to pen mode (obviously using pen previously)
            self.penmode.trigger()
        elif self.highlightmode.isChecked():
            self.setHighlightModeClicked()
        elif self.textmode.isChecked():
            self.setTextMode()

        if  self.stem.scene().mode == "presentation":
            #self.showFullScreen()
            self.showMaximized()
        elif self.fullscreenwidget.isChecked():
            self.showMaximized()
        elif hasattr(self, 'inputgeometry') and not self.isVisible():
            # If the dialog is already visible don't move it
            self.setGeometry(self.inputgeometry)
        self.show()

    def saveClose(self):

        # If a text item has been entered but has not lost focus it will not have been saved yet
        for item in self.scene.getItems():
            if isinstance(item, TextItem):
                item.deleteOrSave()
       
        # Check for empty text items, delete them if they exist
        for n in self.scene.node.outN('n.kind="Text"'):
            # XXX this will not work for qt source
            if len(n['source'])==0:
                n.delete(setchange=True)

        # If there are no items, delete branch
        # outgoing links: In, Child
        if self.scene.node.outE('e.kind="In"', COUNT=True)==0 and \
           self.scene.node.outE('e.kind="Child"', COUNT=True)==0:

            self.scene.graph.deleteOutFromNodes(graphydb.NSet([self.scene.node]), setchange=True)

        # TODO this will delete a text item that never lost focus (so no node created)

        self.stem.renew(reload=False, children=False)

        self.inputgeometry = self.geometry()

        self.stem.isBeingEdited = False

        self.hide()

    def done(self, r):
        # finilise closing dialog even if WM button clicked or ESC pressed
        self.saveClose()

    def tagsChanged(self):
        # callback when tags field loses focus
        newtags = set(self.tagsEdit.text().split())
        oldtags = self.scene.node.get('tags', set())
        if newtags != oldtags:
            if len(newtags)>0:
                self.scene.node['tags'] = list(newtags)
            else:
                self.scene.node.discard('tags')
            self.scene.node.save(setchange=True)
            self.stem.renew(reload=False, create=True, children=False, recurse=False, position=False)


    def iconifiedChanged(self, state):
        # callback for checkbox
        # state is the new state
        if state:
            # leaf of stem should be displayed as just an icon
            self.scene.node['iconified'] = True
        else:
            self.scene.node.discard('iconified')
        self.scene.node.save(setchange=True)
        self.stem.renew(reload=False, create=True, children=False, recurse=True, position=False)

    def scaleWidgetChanged(self, scale):
        # callback for spinbox
        if 'scale' not in self.scene.node or self.scene.node['scale'] != scale:
            self.scene.node['scale'] = scale
            self.scene.node.save(setchange=True)
            self.stem.renew(reload=False, children=False, recurse=False, position=False)

    def branchInheritColourChanged(self, state):
        # callback for checkbox
        # state is the new state of checkbox
        if state==True:
            self.branchcolorbutton.setDisabled(True)
            if 'branchcolor' in self.scene.node:
                del self.scene.node['branchcolor']
                self.scene.node.save(setchange=True)
                self.stem.renew(reload=False, children=False, recurse=True, position=False)
        else:
            self.branchcolorbutton.setDisabled(False)
            self.setBranchColour()

    def setBranchColour(self):
        # this is only triggered when inherit unchecked
        d = QtWidgets.QColorDialog()
        color = QtGui.QColor(self.scene.node.get('branchcolor','gray'))
        color = d.getColor(color, self,  self.tr("Choose a Color"))

        if color.isValid():
            pix = QtGui.QPixmap(50, 50)
            pix.fill(color)
            self.branchcolorbutton.setIcon(QtGui.QIcon(pix))
            colorhex=color.name(QtGui.QColor.HexArgb)
            self.scene.node['branchcolor'] = colorhex
            self.scene.node.save(setchange=True)
            self.stem.renew(reload=False, children=False, recurse=True, position=False)

    def opacityWidgetChanged(self, opacity):

        self.setWindowOpacity(opacity)

    def createActions(self):

        self.closeAct = QtWidgets.QAction(QtGui.QIcon(":/images/exit.svg"),self.tr("Close"), self)
        self.closeAct.triggered.connect(self.saveClose)

        ## ----------------------------------------------------------------------------------
        self.propmode = QtWidgets.QAction(QtGui.QIcon(":/images/cog.svg"),self.tr("Properties"), self)
        self.propmode.setCheckable(True)
        self.propmode.triggered.connect(self.setPropMode)

        ## ----------------------------------------------------------------------------------
        self.textmode = QtWidgets.QAction(QtGui.QIcon(":/images/text.svg"),self.tr("&Text mode"), self)
        self.textmode.triggered.connect(self.setTextMode)

        self.penmode = QtWidgets.QAction(QtGui.QIcon(":/images/pencil.svg"),self.tr("&Pen mode"), self)
        self.penmode.setShortcut("b")
        self.penmode.triggered.connect(self.setPenModeClicked)

        self.highlightmode = QtWidgets.QAction(QtGui.QIcon(":/images/highlighter.svg"),self.tr("&Highlight mode"), self)
        self.highlightmode.setShortcut("h")
        self.highlightmode.triggered.connect(self.setHighlightModeClicked)

        self.erasermode = QtWidgets.QAction(QtGui.QIcon(":/images/eraser.svg"),self.tr("&Eraser mode"), self)
        self.erasermode.setShortcut("e")
        self.erasermode.triggered.connect(self.setEraserMode)

        self.selectmode = QtWidgets.QAction(QtGui.QIcon(":/images/pointer.svg"),self.tr("&Select mode"), self)
        self.selectmode.triggered.connect(self.setSelectMode)

        ## ----------------------------------------------------------------------------------
        self.cutAct = QtWidgets.QAction(QtGui.QIcon(":/images/edit-cut.svg"),self.tr("Cu&t"), self)
        self.cutAct.setShortcut(QtGui.QKeySequence.Cut)
        self.cutAct.setStatusTip(self.tr("Cut selected to clipboard"))
        self.cutAct.triggered.connect(self.cutEvent)

        ## ----------------------------------------------------------------------------------
        self.copyAct = QtWidgets.QAction(QtGui.QIcon(":/images/edit-copy.svg"),self.tr("&Copy"), self)
        self.copyAct.setShortcut(QtGui.QKeySequence.Copy)
        self.copyAct.setStatusTip(self.tr("Copy selected to clipboard"))
        self.copyAct.triggered.connect(self.copyEvent)

        ## ----------------------------------------------------------------------------------
        self.pasteAct = QtWidgets.QAction(QtGui.QIcon(":/images/edit-paste.svg"), self.tr("&Paste"), self)
        self.pasteAct.setShortcut(QtGui.QKeySequence.Paste)
        self.pasteAct.setStatusTip(self.tr("Paste the clipboard's contents"))
        self.pasteAct.triggered.connect(self.pasteEvent)

        ## ----------------------------------------------------------------------------------
        self.deleteAct = QtWidgets.QAction(QtGui.QIcon(":/images/edit-delete.svg"), self.tr("&Delete"), self)
        self.deleteAct.setShortcut(QtGui.QKeySequence.Delete)
        self.deleteAct.setStatusTip(self.tr("Delete selected"))
        self.deleteAct.triggered.connect(self.deleteEvent)

        ## ----------------------------------------------------------------------------------
        self.zoomInAct = QtWidgets.QAction(QtGui.QIcon(":/images/zoom-in.svg"), self.tr("Zoom In"), self)
        self.zoomInAct.setShortcut(QtGui.QKeySequence.ZoomIn)
        self.zoomInAct.setStatusTip(self.tr("Zoom in"))
        self.zoomInAct.triggered.connect(self.view.zoomIn)

        ## ----------------------------------------------------------------------------------
        self.zoomOutAct = QtWidgets.QAction(QtGui.QIcon(":/images/zoom-out.svg"), self.tr("Zoom Out"), self)
        self.zoomOutAct.setShortcut(QtGui.QKeySequence.ZoomOut)
        self.zoomOutAct.setStatusTip(self.tr("Zoom out"))
        self.zoomOutAct.triggered.connect(self.view.zoomOut)

        ## ----------------------------------------------------------------------------------
        self.zoomOriginalAct = QtWidgets.QAction(QtGui.QIcon(":/images/zoom-one.svg"), self.tr("Reset Zoom"), self)
        self.zoomOriginalAct.setStatusTip(self.tr("Reset Zoom"))
        self.zoomOriginalAct.triggered.connect(self.view.zoomOriginal)

        ## ----------------------------------------------------------------------------------
        self.raiseAct = QtWidgets.QAction(QtGui.QIcon(":/images/raise.svg"), self.tr("Raise"), self)
        self.raiseAct.setStatusTip(self.tr("Raise selected items"))
        self.raiseAct.setVisible(False)
        self.raiseAct.triggered.connect(self.raiseItemsEvent)

        ## ----------------------------------------------------------------------------------
        self.raiseTopAct = QtWidgets.QAction(QtGui.QIcon(":/images/raise-top.svg"), self.tr("Raise to top"), self)
        self.raiseTopAct.setStatusTip(self.tr("Raise selected items to top"))
        self.raiseTopAct.setVisible(False)
        self.raiseTopAct.triggered.connect(self.raiseItemsTopEvent)

        ## ----------------------------------------------------------------------------------
        self.lowerAct = QtWidgets.QAction(QtGui.QIcon(":/images/lower.svg"), self.tr("Lower"), self)
        self.lowerAct.setStatusTip(self.tr("Lower selected items"))
        self.lowerAct.setVisible(False)
        self.lowerAct.triggered.connect(self.lowerItemsEvent)

        ## ----------------------------------------------------------------------------------
        self.lowerBottomAct = QtWidgets.QAction(QtGui.QIcon(":/images/lower-bottom.svg"), self.tr("Lower to bottom"), self)
        self.lowerBottomAct.setStatusTip(self.tr("Lower selected items to bottom"))
        self.lowerBottomAct.setVisible(False)
        self.lowerBottomAct.triggered.connect(self.lowerItemsBottomEvent)

        ## ----------------------------------------------------------------------------------
        self.sourceAct = QtWidgets.QAction(QtGui.QIcon(":/images/source.svg"), self.tr("Show source"), self)
        self.sourceAct.setStatusTip(self.tr("Edit the source"))
        self.sourceAct.setVisible(False)
        self.sourceAct.triggered.connect(self.showTextSourceEvent)

        self.boldAct = QtWidgets.QAction(QtGui.QIcon(":/images/text-bold.svg"), self.tr("Bold"), self)
        self.boldAct.setStatusTip(self.tr("Bold Selection"))
        self.boldAct.setVisible(False)
        self.boldAct.setCheckable(True)
        bold = QtGui.QFont()
        bold.setBold(True)
        self.boldAct.setFont(bold)
        self.boldAct.triggered.connect(self.textBoldEvent)

        self.italicAct = QtWidgets.QAction(QtGui.QIcon(":/images/text-italic.svg"), self.tr("Italic"), self)
        self.italicAct.setStatusTip(self.tr("Italic Selection"))
        self.italicAct.setVisible(False)
        self.italicAct.setCheckable(True)
        italic = QtGui.QFont()
        italic.setItalic(True)
        self.italicAct.setFont(italic)
        self.italicAct.triggered.connect(self.textItalicEvent)

        self.underlineAct = QtWidgets.QAction(QtGui.QIcon(":/images/text-underline.svg"), self.tr("Underline"), self)
        self.underlineAct.setStatusTip(self.tr("Underline Selection"))
        self.underlineAct.setVisible(False)
        self.underlineAct.setCheckable(True)
        under = QtGui.QFont()
        under.setUnderline(True)
        self.underlineAct.setFont(under)
        self.underlineAct.triggered.connect(self.textUnderlineEvent)

        pix = QtGui.QPixmap(16,16)
        pix.fill(QtCore.Qt.black)
        self.textColorAct = QtWidgets.QAction(QtGui.QIcon(pix), self.tr("Color"), self)
        self.textColorAct.setStatusTip(self.tr("Foreground Color"))
        self.textColorAct.setVisible(False)
        self.textColorAct.triggered.connect(self.textColorEvent)

        pix = QtGui.QPixmap(16,16)
        pix.fill(QtCore.Qt.yellow)
        self.textBackColorAct = QtWidgets.QAction(QtGui.QIcon(pix), self.tr("Background Color"), self)
        self.textBackColorAct.setStatusTip(self.tr("Background Color"))
        self.textBackColorAct.setVisible(False)
        self.textBackColorAct.triggered [ bool ].connect(self.textBackColorEvent)

        self.fontAct = QtWidgets.QAction(QtGui.QIcon(":/images/text-font.svg"), self.tr("Font"), self)
        self.fontAct.setStatusTip(self.tr("Font Selection"))
        self.fontAct.setVisible(True)
        self.fontAct.triggered.connect(self.textFontEvent)

        self.clearFormatAct = QtWidgets.QAction(QtGui.QIcon(":/images/text-clear.svg"), self.tr("Clear"), self)
        self.clearFormatAct.setStatusTip(self.tr("Clear Format"))
        self.clearFormatAct.setVisible(False)
        self.clearFormatAct.triggered.connect(self.textClearFormatEvent)


    def PenIcon(self, iconfile, color):
        pixmask = QtGui.QPixmap(iconfile)

        pixpen = QtGui.QPixmap(pixmask.size())
        pixpen.fill(color)
        pixpen.setMask(pixmask.createMaskFromColor(QtGui.QColor("#d8d8d8"), mode=QtCore.Qt.MaskOutColor))

        pix = QtGui.QPixmap(pixpen.size())
        pix.fill(QtCore.Qt.transparent)
        painter = QtGui.QPainter()
        painter.begin(pix)
        painter.setCompositionMode(QtGui.QPainter.CompositionMode_SourceOver)
        painter.drawPixmap(0,0, pixmask)
        painter.drawPixmap(0, 0, pixpen)
        painter.end()

        return QtGui.QIcon(pix)

    def setPropMode(self):

        if self.propmode.isChecked():
            self.stackedwidget.setCurrentIndex(1)

        else:
            self.stackedwidget.setCurrentIndex(0)

    def setPenCursor(self):

        if not self.ishighlighter:
            ## Pen selected
            color = QtGui.QColor(self.scene.graph.getsetting('pencolor', '#FF000000'))
            size = self.scene.graph.getsetting('pensize', 1.5)

            pix = QtGui.QPixmap(4, 4)
            pix.fill(color)
            self.view.viewport().setCursor(QtGui.QCursor(pix, 0,0))

            self.penmode.setIcon(self.PenIcon(":/images/pencil.svg", color))

        else:
            ## highlighter selected
            color = QtGui.QColor(self.scene.graph.getsetting('hicolor', '#60FFFFA0'))
            size = self.scene.graph.getsetting('hisize', 5)

            pix = QtGui.QPixmap(6, 10)
            pix.fill(color)
            painter = QtGui.QPainter()
            painter.begin(pix)
            painter.drawRect(0,0,5,9)
            painter.end()

            self.view.viewport().setCursor(QtGui.QCursor(pix, 0,5))

            self.highlightmode.setIcon(self.PenIcon(":/images/highlighter.svg", color))


        self.scene.pen = QtGui.QPen(QtGui.QColor(color))
        self.scene.pen.setWidthF(size)



    def setTextMode(self):
        '''
        set mode for adding and editing text
        '''
        # TODO select all current text
        # TODO tab should jump between text items
        # TODO pointer should chage to I beam over text and ibeam_+ over canvas (adding text)
        # TODO clicking on canvas should add text item

        self.scene.mode = TextMode
        self.scene.transformationWidget.hide()

        self.raiseAct.setVisible(False)
        self.raiseTopAct.setVisible(False)
        self.lowerAct.setVisible(False)
        self.lowerBottomAct.setVisible(False)
        self.sourceAct.setVisible(True)
        self.boldAct.setVisible(True)
        self.italicAct.setVisible(True)
        self.underlineAct.setVisible(True)
        self.textColorAct.setVisible(True)
        self.textBackColorAct.setVisible(True)
        #self.textFont.setVisible(True)
        self.fontAct.setVisible(True)
        #self.textFontSize.setVisible(True)
        self.clearFormatAct.setVisible(True)

        #self.scene.setBackgroundBrush(QtGui.QBrush(QtCore.Qt.NoBrush))
        # self.scene.setBackgroundBrush(QtGui.QBrush(QtGui.QColor("White")))


        self.view.setDragMode(QtWidgets.QGraphicsView.NoDrag)

        items = self.scene.getItems()

        textitempresent = False
        for item in items:
            if isinstance(item, TextItem):
                textitempresent = True
                break

        if not textitempresent:
            ## Add a blank TextItem
            batch = graphydb.generateUUID()
            n = self.scene.graph.Node('Text', source='', z=1,
                       frame=Transform().tolist()).save(setchange=True, batch=batch)
            e = self.scene.graph.Edge(self.scene.node, 'In', n).save(setchange=True, batch=batch) 

            textitem = TextItem(n, scene=self.scene)
            textitem.positionChanged.connect(self.setTextControls)
            textitem.setMode(TextMode)
            textitem.setFocus()

        # XXX need method for adding text items to stem

        for item in items:
            ## add default item if none; fulleditor access; non movable
            item.setMode(TextMode)

        ## focus one of the items if possible
        for item in items:
            if isinstance(item, TextItem):
                item.setFocus()
                break

    def setHighlightModeClicked(self):

        if self.scene.mode == PenMode and self.ishighlighter:
            ## clicked while selected
            d = tools.PenDialog(self.scene.pen, "highlighter", self)
            d.exec_()
            color = self.scene.pen.color().name(QtGui.QColor.HexArgb)
            size = self.scene.pen.widthF()
            self.scene.graph.savesetting('hicolor', color)
            self.scene.graph.savesetting('hisize', size)

            self.setPenCursor()
            return

        self.ishighlighter = True
        self.setPenMode()

    def setPenModeClicked(self):
        if self.scene.mode == PenMode and not self.ishighlighter:
            ## clicked while selected
            d = tools.PenDialog(self.scene.pen, "pen", self)
            d.exec_()
            color = self.scene.pen.color().name(QtGui.QColor.HexArgb)
            size = self.scene.pen.widthF()
            self.scene.graph.savesetting('pencolor', color)
            self.scene.graph.savesetting('pensize', size)

            self.setPenCursor()
            return

        self.ishighlighter = False
        self.setPenMode()

    def setPenMode(self):
        '''
        set mode for drawing with stylus / mouse
        '''
        # TODO implement eraser
        # TODO grouped delete
        # TODO set scene rotation matrix if in RH or LH modes

        self.scene.mode = PenMode
        self.scene.transformationWidget.hide()

        self.raiseAct.setVisible(False)
        self.raiseTopAct.setVisible(False)
        self.lowerAct.setVisible(False)
        self.lowerBottomAct.setVisible(False)
        self.sourceAct.setVisible(False)
        self.boldAct.setVisible(False)
        self.italicAct.setVisible(False)
        self.underlineAct.setVisible(False)
        self.textColorAct.setVisible(False)
        self.textBackColorAct.setVisible(False)
        self.fontAct.setVisible(False)
        self.clearFormatAct.setVisible(False)

        self.view.setDragMode(QtWidgets.QGraphicsView.NoDrag)
        # self.scene.setBackgroundBrush(QtGui.QBrush(QtGui.QPixmap(":/images/gridbackground.png")))

        for item in self.scene.getItems():
            item.setMode(PenMode)

        self.setPenCursor()

    def setEraserMode(self):
        self.setPenMode()
        self.view.viewport().setCursor(QtCore.Qt.CrossCursor)
        self.scene.mode = EraserMode

    # XXX should drawing modes be in the scene instead?

    def setSelectMode(self):
        '''
        set mode for moving and scaling items
        '''
        # TODO implement new rubberband mode switching (disabling/enabling etc)

        self.scene.mode = SelectMode

        self.raiseAct.setVisible(True)
        self.raiseTopAct.setVisible(True)
        self.lowerAct.setVisible(True)
        self.lowerBottomAct.setVisible(True)
        self.sourceAct.setVisible(False)
        self.boldAct.setVisible(False)
        self.italicAct.setVisible(False)
        self.underlineAct.setVisible(False)
        self.textColorAct.setVisible(False)
        self.textBackColorAct.setVisible(False)
        #self.textFont.setVisible(False)
        self.fontAct.setVisible(False)
        self.clearFormatAct.setVisible(False)

        #self.scene.setBackgroundBrush(QtGui.QBrush(QtCore.Qt.NoBrush))
        # self.scene.setBackgroundBrush(QtGui.QBrush(QtGui.QColor("White")))
        self.view.viewport().setCursor(QtCore.Qt.ArrowCursor)

        for item in self.scene.getItems():
            item.setMode(SelectMode)

    def saveSettings(self):

        # dx,dy,r,s = Transform(self.view.transform()).getTRS()

        # self.state['rotation'] = r
        # self.state['scale'] = s

        settings = QtCore.QSettings("Ectropy", "Nexus")

        ## temporarily (for this session) record the input geometry
        g = self.geometry()
        self.inputgeometry = [g.left(), g.top(), g.width(), g.height()]

    def setTextControls(self, cursor):
        fmt = cursor.charFormat()

        self.boldAct.setChecked(fmt.fontWeight()==QtGui.QFont.Bold)
        self.italicAct.setChecked(fmt.fontItalic())
        self.underlineAct.setChecked(fmt.fontUnderline())

        # XXX more efficient to check for color change first?
        pix = QtGui.QPixmap(16, 16)
        pix.fill(fmt.foreground().color())
        icon = QtGui.QIcon(pix)
        self.textColorAct.setIcon(icon)

        ## how to set background to zero
        pix = QtGui.QPixmap(16, 16)
        col = fmt.background().color()
        if not fmt.background().isOpaque():
            col.setAlpha(0)
        pix.fill(col)
        icon = QtGui.QIcon(pix)
        self.textBackColorAct.setIcon(icon)

    def raiseItemsTopEvent(self):
        maxZ = self.scene.normaliseZvalues()
        for item in self.scene.selectedItems():
            item.setZValue(item.zValue()+1+maxZ)
        self.scene.normaliseZvalues()

    def lowerItemsBottomEvent(self):
        self.scene.normaliseZvalues()
        selected = self.scene.selectedItems()
        if len(selected) == 0:
            return

        selected.sort(key=lambda x:x.zValue())
        maxZ = selected[-1].zValue()
        for item in selected:
            item.setZValue(item.zValue()-1-maxZ)
        self.scene.normaliseZvalues()

    def raiseItemsEvent(self):
        self.scene.normaliseZvalues()
        for item in self.scene.selectedItems():
            item.setZValue(item.zValue()+1.5)
        self.scene.normaliseZvalues()

    def lowerItemsEvent(self):
        self.scene.normaliseZvalues()
        for item in self.scene.selectedItems():
            item.setZValue(item.zValue()-1.5)
        self.scene.normaliseZvalues()

    def showTextSourceEvent(self, state):
        for item in self.scene.getItems():
            if isinstance(item, TextItem):
                if state and item.hasFocus():
                    item.setMode(TextItem.EditSourceMode)
                else:
                    item.setMode(TextItem.EditMode)
                break

    def textBoldEvent(self, state):

        # XXX tool button should reflect current selection
        for item in self.scene.getItems():
            if isinstance(item, TextItem) and item.hasFocus():
                fmt = QtGui.QTextCharFormat()
                if state:
                    fmt.setFontWeight(QtGui.QFont.Bold)
                else:
                    fmt.setFontWeight(QtGui.QFont.Normal)
                cursor=item.textCursor()
                cursor.mergeCharFormat(fmt)
                item.setTextCursor(cursor)
                break

    def textItalicEvent(self, state):

        # XXX tool button should reflect current selection
        for item in self.scene.getItems():
            if isinstance(item, TextItem) and item.hasFocus():
                fmt = QtGui.QTextCharFormat()
                if state:
                    fmt.setFontItalic(True)
                else:
                    fmt.setFontItalic(False)

                cursor=item.textCursor()
                cursor.mergeCharFormat(fmt)
                item.setTextCursor(cursor)
                break

    def textUnderlineEvent(self, state):

        # XXX tool button should reflect current selection
        for item in self.scene.getItems():
            if isinstance(item, TextItem) and item.hasFocus():
                fmt = QtGui.QTextCharFormat()
                if state:
                    fmt.setFontUnderline(True)
                else:
                    fmt.setFontUnderline(False)

                cursor=item.textCursor()
                cursor.mergeCharFormat(fmt)
                item.setTextCursor(cursor)
                break

    def textColorEvent(self, state):

        for item in self.scene.getItems():
            if isinstance(item, TextItem) and item.hasFocus():

                # XXX current color selection
                col = QtWidgets.QColorDialog.getColor()
                if col.isValid():
                    fmt = QtGui.QTextCharFormat()
                    fmt.setForeground(col)
                    cursor=item.textCursor()
                    cursor.mergeCharFormat(fmt)
                    item.setTextCursor(cursor)
                break


    def textBackColorEvent(self, state):

        for item in self.scene.getItems():
            if isinstance(item, TextItem) and item.hasFocus():

                # XXX current color selection
                col = QtWidgets.QColorDialog.getColor()
                if col.isValid():
                    fmt = QtGui.QTextCharFormat()
                    fmt.setBackground(col)
                    cursor=item.textCursor()
                    cursor.mergeCharFormat(fmt)
                    item.setTextCursor(cursor)
                break

    def textClearFormatEvent(self, state):

        for item in self.scene.getItems():
            if isinstance(item, TextItem) and item.hasFocus():
                # XXX totally clear all formatting?
                fmt = QtGui.QTextCharFormat()
                item.textCursor().setCharFormat(fmt)
                fmt = QtGui.QTextBlockFormat()
                cursor=item.textCursor()
                cursor.setBlockFormat(fmt)
                item.setTextCursor(cursor)
                break

    def textFontEvent(self):

        if self.scene.focusedTextItem is not None:
            item = self.scene.focusedTextItem

            font, ok = QtWidgets.QFontDialog.getFont()
            if ok:
                fmt = QtGui.QTextCharFormat()
                fmt.setFont(font)
                cursor=item.textCursor()
                cursor.setCharFormat(fmt)
                item.setTextCursor(cursor)

    def deleteEvent(self):
        selected = self.scene.selectedItems()
        batch = graphydb.generateUUID()
        for item in selected:
            self.scene.removeItem(item, batch=batch)
        self.scene.setSelectionWidget()
        self.scene.refreshStem()

    def cutEvent(self):
        self.copyEvent()
        self.deleteEvent()

    def copyEvent(self):

        # TODO create a copy As function

        selected = self.scene.selectedItems()
        selected.sort(key=lambda x:x.zValue())

        clipboard = QtWidgets.QApplication.clipboard()
        mimedata = QtCore.QMimeData()

        ##
        ## Copy a pixmap of the selected items for external use
        ##
        rect = QtCore.QRectF()

        ## unselect items so selection marks dont show up
        for item in selected:
            rect=rect.united(item.sceneBoundingRect())
            item.setSelected(False)

        ## grab all items that will show up in the region
        # TODO isn't this the same as above?
        allregionitems = self.scene.items(rect)

        ## build a pixmap at 2x the size for better resolution
        pixmap = QtGui.QPixmap(rect.size().toSize()*2)

        ## make background transparent
        pixmap.fill( QtGui.QColor(0,0,0,0))
        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setRenderHint(QtGui.QPainter.HighQualityAntialiasing)
        painter.setRenderHint(QtGui.QPainter.TextAntialiasing)
        painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)

        ## hide unselected visible items that are in the rect
        hiddenitems = []
        for item in allregionitems:
            if item not in selected and item.isVisible():
                item.setVisible(False)
                hiddenitems.append(item)

        self.scene.render(painter, QtCore.QRectF(), rect)
        painter.end()
        mimedata.setImageData(pixmap)

        ## return selection
        for item in selected:
            item.setSelected(True)
        ## return hidden items
        for item in hiddenitems:
            item.setVisible(True)

        ##
        ## Store nexus internal data as a node for pasting elsewhere in tree
        ##
        g = self.scene.node.graph
        copynode = g.getCopyNode(clear=True)

        ## Create a new Stem to hold the copy data
        newstem = g.Node('Stem', z=0, flip=1,
                         scale=1.0, pos=[10,10]).save(setchange=False)
        newedge = g.Edge(copynode, "Child", newstem).save(setchange=False)

        nodes = graphydb.NSet()
        for item in selected:
            if hasattr(item, 'node'):
                nodes.add(item.node)

        items = g.copyTrees(nodes, setchange=False)
        for item in items:
            g.Edge(newstem, 'In', item).save(setchange=False)

        # store nexus link in clipboard
        clipboard = QtWidgets.QApplication.clipboard()
        mimedata = QtCore.QMimeData()
        link = copynode.graph.getNodeLink(copynode)
        mimedata.setData("application/x-nexus", bytes(link, 'utf-8'))
        clipboard.setMimeData(mimedata)

    def pasteEvent(self):

        # TODO if text too long ask if it should be a iconified
        # TODO check for images ... check size and scale appropriately
        # TODO paste to central topics (nothing selected)

        # XXX image from nexus nor taken as item so lose transformations

        clipboard = QtWidgets.QApplication.clipboard()
        mimedata = clipboard.mimeData()

        g = self.scene.graph
        copynode, msg = g.copyNodeWithMimedata(mimedata)
        if copynode is None:
            QtWidgets.QMessageBox.information(None,"Warning", msg)
            return

        # keep track so we can address new nodes
        old_nodes = self.scene.node.outN('e.kind="In"')

        batch = graphydb.generateUUID()
        # Ignore the first level stems and just get the content
        content_nodes = copynode.outN('e.kind="Child"').outN('e.kind="In"')
        items = g.copyTrees(content_nodes, batch=batch, setchange=True)
        for item in items:
            g.Edge(self.scene.node, 'In', item).save(batch=batch, setchange=True)

        # Grab difference in nodes in case there where nested items in copied trees
        new_nodes = self.scene.node.outN('e.kind="In"') - old_nodes

        # TODO clear selection or replace it?
        self.scene.clearSelection()

        # XXX move to view so that we can get current point
        ## position of cursor
        # cp = self.scene.mapFromGlobal(QtGui.QCursor.pos())
        # if not self.scene.geometry().contains(cp):
        #     cp = QtCore.QPoint(0,0)
        # targetpos = self.scene.mapToScene(cp)

        pastedobjects = []
        for n in new_nodes:
            self.scene.maxZ += 1
            n['z'] = self.scene.maxZ
            if n['kind'] == 'Stroke':
                item=InkItem(n, scene=self.scene)
            elif n['kind'] == 'Text':
                item=TextItem(n, scene=self.scene)
            elif n['kind'] == 'Image':
                item=PixmapItem(n, scene=self.scene)
            pastedobjects.append(item)


        ## translate all the items so that top left of their
        ## bounding box is at the target position
        itemrect = QtCore.QRectF()
        for item in pastedobjects:
            itemrect = itemrect.united(item.sceneBoundingRect())

        # dp = targetpos-itemrect.center()
        t = QtGui.QTransform()
        # t.translate(dp.x(),dp.y())
        t.translate(3,-3)
        for item in pastedobjects:
            ## note QTs backward transforms
            item.setTransform(item.transform()*t)
            item.node['frame'] = Transform(item.transform()).tolist()

        new_nodes.save(batch=batch, setchange=True)
        self.scene.refreshStem()
        self.scene.transformationWidget.setSelectedItems(pastedobjects)
        self.scene.transformationWidget.show()


class MyEvent(QtWidgets.QGraphicsSceneMouseEvent):

    def setButtons(self, buttons):
        self._buttons=buttons
    def setScenePos(self, scenePos):
        self._scenePos = scenePos

    def scenePos(self):
        return self._scenePos
    def buttons(self):
        return self._buttons

##----------------------------------------------------------------------
class InkScene(QtWidgets.QGraphicsScene):
##----------------------------------------------------------------------

    maxZ = 1
    mode = TextMode
    _lastScenePos = False
    focusedTextItem = None

    def __init__(self, stem, parent = None):
        super().__init__(parent)
        self.stem=stem

        self.setSceneRect(-1000, -1000, 2000, 2000)

        self.transformationWidget = TransformationWidget(parent, self)
        self.addItem(self.transformationWidget)
        self.transformationWidget.hide()
        self.transformationWidget.setZValue(9000)  # make sure it's on top

    def refreshStem(self):
        '''
        Refresh the stem on the map
        '''
        self.stem.renew(reload=True, create=True, position=False, children=False, recurse=True)

    def addItem(self, item):
        QtWidgets.QGraphicsScene.addItem(self, item)

    def removeItem(self, item, batch=None, setchange=True):
        if hasattr(item, 'node'):
            # this will correctly handle linked data nodes
            self.graph.deleteOutFromNodes(graphydb.NSet([item.node]),batch=batch, setchange=setchange)
        super().removeItem(item)

    def getItems(self):
        '''
        return nexus items ... mainly used internally
        '''
        items=[]

        for item in list(self.items()):
            if type(item) in [TextItem, InkItem, PixmapItem]:
                items.append(item)

        return items

    def setSelectionWidget(self):
        selected = self.selectedItems()

        if len(selected)>0:
            rect = QtCore.QRectF()
            for item in selected:
                rect=rect.united(item.sceneBoundingRect())

            self.transformationWidget.setSelectedItems(selected)
            self.transformationWidget.show()
        else:
            self.transformationWidget.hide()

    def normaliseZvalues(self):
        '''
        Give items on canvas a monotonic interger Z value
        '''
        items = self.getItems()
        items.sort(key=lambda x:x.zValue())

        for ii in range(len(items)):
            items[ii].setZValue(ii)

        return ii


class TransformationWidget(QtWidgets.QGraphicsItem):

    selected = []
    ResizeMode = 0
    RotateMode = 1

    def __init__(self, parent = None, scene=None):

        super().__init__()
        self.scene = scene

        ## double headed arrow origin on left point
        dapath=QtGui.QPainterPath()
        dapath.lineTo(8, -8)
        dapath.lineTo(8, -4)
        dapath.lineTo(16, -4)
        dapath.lineTo(16, -8)
        dapath.lineTo(24, 0)
        dapath.lineTo(16, 8)
        dapath.lineTo(16, 4)
        dapath.lineTo(8, 4)
        dapath.lineTo(8, 8)
        dapath.lineTo(0, 0)

        ## double headed curved arrow
        x0 = 12
        y0 = 4
        capath=QtGui.QPainterPath()
        capath.moveTo(8.5-x0, 1.2-y0)
        capath.lineTo(11.3-x0, 4-y0)
        capath.lineTo(0-x0, 4-y0)
        capath.lineTo(0-x0, -7.3-y0)
        capath.lineTo(2.8-x0, -4.5-y0)
        capath.quadTo(12-x0, -13.7-y0, 21.2-x0, -4.5-y0)
        capath.lineTo(24-x0, -7.3-y0)
        capath.lineTo(24-x0, 4-y0)
        capath.lineTo(12.7-x0, 4-y0)
        capath.lineTo(15.5-x0, 1.2-y0)
        capath.quadTo(12-x0, -2.3-y0, 8.5-x0, 1.2-y0)

        # self.tNE = TransformationHandle("tNE", dapath, self)
        # self.tNE.setRotation(-45)
        # self.tNW = TransformationHandle("tNW", dapath, self)
        # self.tNW.setRotation(-135)
        # self.tSW = TransformationHandle("tSW", dapath, self)
        # self.tSW.setRotation(135)
        self.tSE = TransformationHandle("tSE", dapath, self)
        self.tSE.setRotation(45)
        # self.tN = TransformationHandle("tN", dapath, self)
        # self.tN.setRotation(-90)
        # self.tE = TransformationHandle("tE", dapath, self)
        # self.tE.setRotation(0)
        # self.tS = TransformationHandle("tS", dapath, self)
        # self.tS.setRotation(90)
        # self.tW = TransformationHandle("tW", dapath, self)
        # self.tW.setRotation(180)

        # self.rNE = TransformationHandle("rNE", capath, self)
        # self.rNE.setRotation(45)
        self.rNW = TransformationHandle("rNW", capath, self)
        self.rNW.setRotation(-45)
        # self.rSW = TransformationHandle("rSW", capath, self)
        # self.rSW.setRotation(-135)
        # self.rSE = TransformationHandle("rSE", capath, self)
        # self.rSE.setRotation(135)

        # self.rHandles = [self.rNE, self.rNW, self.rSE, self.rSW]
        # self.tHandles = [self.tNE, self.tNW, self.tSE, self.tSW, self.tN, self.tW, self.tE, self.tS]
        self.rHandles = [self.rNW]
        self.tHandles = [self.tSE]

        self.overRect=OverRect(self)

        #self.setMode(self.ResizeMode)

    def setSelectedItems(self, selected=[]):
        self.selected = selected
        self.resize()

    def resize(self):
        rect = QtCore.QRectF()
        for item in self.selected:
            rect=rect.united(item.sceneBoundingRect())

        rect.normalized()
        self.rect = rect

        # self.tNE.setPos(rect.topRight())
        # self.tNW.setPos(rect.topLeft())
        self.tSE.setPos(rect.bottomRight())
        # self.tSW.setPos(rect.bottomLeft())
        # self.tS.setPos((rect.bottomLeft()+rect.bottomRight())/2.0)
        # self.tN.setPos((rect.topLeft()+rect.topRight())/2.0)
        # self.tE.setPos((rect.topRight()+rect.bottomRight())/2.0)
        # self.tW.setPos((rect.bottomLeft()+rect.topLeft())/2.0)

        # self.rNE.setPos(rect.topRight())
        self.rNW.setPos(rect.topLeft())
        # self.rSE.setPos(rect.bottomRight())
        # self.rSW.setPos(rect.bottomLeft())

        self.overRect.setRect(rect)


    def paint(self, painter, option, widget):
        ## this has to be overriden
        pass

    def hide(self):
        QtWidgets.QGraphicsItem.hide(self)

    def boundingRect(self):
        return self.childrenBoundingRect()

    def pointerPressEvent(self, event):

        #QtWidgets.QGraphicsItem.mousePressEvent(self, event)

        if not hasattr(event, "source"):
            ## ignore events if they are not from one of the sub widgets
            return

        if len(self.selected)==0:
            ## Nothing to be done
            ## this shouldn't normally trigger
            return

        #self.mousePressScreenPos = event.screenPos
        #self.mousePressTime = time.time()

        ## find bounding rect of selected items
        rect = QtCore.QRectF()
        for item in self.selected:
            rect=rect.united(item.sceneBoundingRect())

        # XXX draw pivot point

        ## pivot in scene coords
        if (event.modifiers & QtCore.Qt.AltModifier) or \
           event.source in ["rNE","rNW","rSW","rSE"]:
            self.pivot = rect.center()
        elif event.source == "tNE":
            self.pivot = rect.bottomLeft()
        elif event.source == "tNW":
            self.pivot = rect.bottomRight()
        elif event.source == "tSW":
            self.pivot = rect.topRight()
        elif event.source == "tSE":
            self.pivot = rect.topLeft()
        elif event.source == "tS":
            self.pivot = (rect.topLeft()+rect.topRight())/2.0
        elif event.source == "tN":
            self.pivot = (rect.bottomLeft()+rect.bottomRight())/2.0
        elif event.source == "tW":
            self.pivot = (rect.topRight()+rect.bottomRight())/2.0
        elif event.source == "tE":
            self.pivot = (rect.bottomLeft()+rect.topLeft())/2.0

        #event.accept()

    def pointerMoveEvent(self, event):

        if event.source in ["tN","tNE","tE","tSE","tS","tSW","tW","tNW"]:
            self.scaleItems(event)
        elif event.source in ["rNE","rSE","rSW","rNW"]:
            self.rotateItems(event)
        elif event.source == 'rect':
            self.moveItems(event)

    def pointerReleaseEvent(self, event):
        #QtWidgets.QGraphicsItem.mouseReleaseEvent(self, event)

        # save any changed items
        batch = graphydb.generateUUID()
        for item in self.selected:
            if item._changed:
                item.node['frame']=Transform(item.transform()).tolist()
                item.node.save(setchange=True, batch=batch)
                item._changed = False
        self.scene.refreshStem()
        # sp = event.screenPos()
        # t = time.time()

        # dp = sp-self.mousePressScreenPos
        # dt=t-self.mousePressTime
        # # XXX needs tweaking, esp to incoporate with doubleClick
        # if dp.manhattanLength()<3:
        #     if dt < 0.6:
        #         self.mouseClickEvent(event)
        #     else:
        #         self.mouseSlowClickEvent(event)
        # pass

    # def pointerClickEvent(self, event):
    #     pass
    #     #logging.debug("click")

    # def pointerSlowClickEvent(self, event):
    #     pass
    #     # logging.debug("slow click")

    def scaleItems(self, event):

        p0 = event.lastScenePos
        p1 = event.scenePos

        pv = self.pivot.x(), self.pivot.y()

        translate = QtGui.QTransform()
        translate.translate(-pv[0],-pv[1])
        translateback = translate.inverted()[0]

        scale = QtGui.QTransform()
        if event.source in ["tN","tS"]:
            kx = 1.0
        elif p0[0]-pv[0] == 0:
            kx = 0.0
        else:
            kx = (p1[0]-pv[0])/(p0[0]-pv[0])

        if event.source in ["tE","tW"]:
            ky = 1.0
        elif p0[1]-pv[1] == 0:
            ky = 0.0
        else:
            ky = (p1[1]-pv[1])/(p0[1]-pv[1])

        ## Keep aspect ratio while scaling unless shift is used
        if not( event.modifiers & QtCore.Qt.ShiftModifier):
            if abs(kx-1.0)>abs(ky-1.0):
                ky=kx
            else:
                kx=ky

        scale.scale(kx,ky)

        ## QTs transform is transposed from usual math sense!
        ## operators apply from left to right and act on row vectors
        transform = translate*scale*translateback

        for item in self.selected:
            t1 = item.transform()
            item.setTransform(t1*transform)
            item._changed = True

        self.resize()

    def rotateItems(self, event):

        p0 = event.lastScenePos
        p1 = event.scenePos
        pv = self.pivot.x(), self.pivot.y()

        translate = QtGui.QTransform()
        translate.translate(-pv[0],-pv[1])
        translateback = translate.inverted()[0]

        rotate = QtGui.QTransform()
        theta0 = atan2(p0[1]-pv[1],p0[0]-pv[0])
        theta1 = atan2(p1[1]-pv[1],p1[0]-pv[0])
        theta = (theta1-theta0)
        rotate.rotateRadians(theta)

        ## QTs transform is transposed from usual math sense!
        ## operators apply from left to right and act on row vectors
        transform = translate*rotate*translateback

        for item in self.selected:
            t1 = item.transform()
            item.setTransform(t1*transform)
            item._changed = True

        self.resize()

    def moveItems(self, event):

        p0 = event.lastScenePos
        p1 = event.scenePos
        pv = p1[0]-p0[0], p1[1]-p0[1]

        translate = QtGui.QTransform()
        translate.translate(pv[0],pv[1])

        for item in self.selected:
            t1 = item.transform()
            item.setTransform(t1*translate)
            item._changed = True

        self.resize()


class OverRect(QtWidgets.QGraphicsRectItem):

    defaultcol = QtGui.QColor(100,100,100,30)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setBrush(QtGui.QBrush(self.defaultcol))
        self.setPen(QtGui.QPen(QtCore.Qt.NoPen))
        self.setZValue(200)
        self.id = "rect"

    def pointerPressEvent(self, event):
        event.source = self.id
        self.parentItem().pointerPressEvent(event)

    def pointerMoveEvent(self, event):
        event.source = self.id
        self.parentItem().pointerMoveEvent(event)

    def pointerReleaseEvent(self, event):
        event.source = self.id
        self.parentItem().pointerReleaseEvent(event)

class TransformationHandle(QtWidgets.QGraphicsPathItem):

    def __init__(self,  id, path, parent = None):

        self.id = id

        super().__init__(path, parent)
        self.setScale(2)

        self.setAcceptHoverEvents(True)
        self.setBrush(QtGui.QBrush(QtCore.Qt.black))

        ## this is so that the widget doesn't change with scene scaling
        self.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations,  True)

    def hoverEnterEvent(self, event):
        self.setBrush(QtGui.QBrush(QtCore.Qt.yellow))
        QtWidgets.QGraphicsPathItem.hoverEnterEvent(self, event)

    def hoverLeaveEvent(self, event):
        self.setBrush(QtGui.QBrush(QtCore.Qt.black))
        QtWidgets.QGraphicsPathItem.hoverLeaveEvent(self, event)

    def pointerPressEvent(self, event):
        event.source = self.id
        self.parentItem().pointerPressEvent(event)

    def pointerMoveEvent(self, event):
        event.source = self.id
        self.parentItem().pointerMoveEvent(event)

    def pointerReleaseEvent(self, event):
        event.source = self.id
        self.parentItem().pointerReleaseEvent(event)


class PointerEvent():
    '''
    Combine tablet and mouse events
    '''

    def __init__(self, event, etype, scenePos):

        self.time = time.time()
        self.lastTime = self.time
        self.firstTime = self.time

        self.scenePos = scenePos
        self.lastScenePos = scenePos
        self.firstScenePos = scenePos

        self.type = etype
        self.modifiers = event.modifiers()
        self.button = event.button()
        self.timestamp = event.timestamp()

        if isinstance(event, QtGui.QTabletEvent):
            self.pressure = event.pressure
            self.tilt = (event.xTilt(), event.yTilt())

        elif isinstance(event, QtGui.QMouseEvent):
            self.pressure = 0.8
            self.tilt = (0.0, 0.0)

    def update(self, etype, scenePos):
        self.lastTime = self.time
        self.time = time.time()
        self.lastScenePos = self.scenePos
        self.scenePos = scenePos
        self.type = etype


# XXX move modes into class
Free, Mouse, Tablet, Gesture = 0,1,2,3

##----------------------------------------------------------------------
class InkView(QtWidgets.QGraphicsView):
##----------------------------------------------------------------------
    viewChangeStream = QtCore.pyqtSignal(QtWidgets.QGraphicsView)

    def __init__(self, scene, parent = None):

        super().__init__(scene, parent)

        self.setRenderHint(QtGui.QPainter.Antialiasing)
        self.setRenderHint(QtGui.QPainter.TextAntialiasing)
        self.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)
        self.setRenderHint(QtGui.QPainter.HighQualityAntialiasing)
        self.setCacheMode(QtWidgets.QGraphicsView.CacheBackground)
        #self.setDragMode(QtGui.QGraphicsView.NoDrag)
        #self.setDragMode(QtGui.QGraphicsView.ScrollHandDrag)
        #self.setDragMode(QtGui.QGraphicsView.RubberBandDrag)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        #self.setResizeAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        #self.setTransformationAnchor(QtGui.QGraphicsView.NoAnchor)


        #self.grabGesture(QtCore.Qt.PanGesture)
        self.grabGesture(QtCore.Qt.PinchGesture)

        self.setViewportUpdateMode(QtWidgets.QGraphicsView.SmartViewportUpdate)

        self.setAcceptDrops(True)

        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)

        self._eventstate = Free

        # gesture has to overcome threshold before being recognised
        # _sticky is the state variable
        self._sticky = True

        self._itemUnder = None
        self._event = None

        self.setAttribute(QtCore.Qt.WA_AcceptTouchEvents, True)

    def tabletEvent(self, event):
        '''
        tablet event dispatcher
        '''

        self.tablettime = time.time()

        eventtype = event.type()
        pointertype = event.pointerType()
        pressure = event.pressure()
        event.setAccepted(True)
        scene = self.scene()
        scenePos = self.mapToScene(event.pos())

        # Report what was received for debugging
        tev = {QtGui.QTabletEvent.TabletPress:"TabletPress",
               QtGui.QTabletEvent.TabletMove:"TabletMove",
               QtGui.QTabletEvent.TabletRelease:"TabletRelease"}
        etype = tev.get(eventtype,"OtherTabletEvent")
        # logging.debug("I {} pointer={} pressure={} tilt=({},{}) buttons={} device={} id={}".format(
        #     etype, event.pointerType(), pressure,
        #     event.xTilt(), event.yTilt(),
        #     int(event.buttons()),
        #     repr(event.device()),
        #     repr(event.uniqueId())
        #     ))

        pressure = pressureCurve(pressure,**CONFIG['pressure_curve'])

        T=self.viewportTransform()
        Tinv,dummy = T.inverted()
        scenePosF = event.posF()*Tinv
        scenePosF = (scenePosF.x(), scenePosF.y())
        etime = time.time()

        #
        # Dispatch events mirroring mouse event structures
        #
        itemunder = scene.itemAt(scenePos, self.transform())

        if eventtype==QtGui.QTabletEvent.TabletPress:
            self._eventstate = Tablet

            pevent = PointerEvent(event, etype="press", scenePos=scenePosF)
            self._event = pevent

            if pointertype == QtGui.QTabletEvent.Eraser \
                                or scene.mode == EraserMode:
                self.eraserPressEvent(scenePos)

            elif scene.mode == PenMode:
                self.penPressEvent(scenePos, pressure)

            else:
                self.pointerPressEvent(self._event)

        elif eventtype==QtGui.QTabletEvent.TabletMove:
            if self._eventstate != Tablet:
                return

            self._event.update("move", scenePosF)

            if pointertype == QtGui.QTabletEvent.Eraser \
                                or scene.mode == EraserMode:
                self.eraserMoveEvent(scenePos, self.transform())

            elif scene.mode == PenMode:
                self.penMoveEvent(scenePos, pressure)

            else:
                self.pointerMoveEvent(self._event)

        elif eventtype==QtGui.QTabletEvent.TabletRelease:
            if self._eventstate != Tablet:
                return
            self._eventstate = Free

            self._event.update("release", scenePos=scenePosF)

            if pointertype == QtGui.QTabletEvent.Eraser \
                                or scene.mode == EraserMode:
                self.eraserReleaseEvent(self._event)

            elif scene.mode == PenMode:
                self.penReleaseEvent(self._event)

            else:
                self.pointerReleaseEvent(self._event)

        else:
            logging.debug("Unknown tablet event type: %d",eventtype)


    def mousePressEvent(self, event):
        print("View press event")

        # TODO is this still used?
        if self._eventstate !=Free:
            # logging.debug("    (ignoring mousepress)")
            return
        else:
            self._eventstate = Mouse

        # logging.debug('I mousePressEvent')

        scene = self.scene()
        scenePos = self.mapToScene(event.pos())
        scenePosF = scenePos.x(), scenePos.y()

        self._event = PointerEvent(event, etype="press", scenePos=scenePosF)

        if scene.mode == PenMode:
            if not CONFIG['input_ignore_mouse']:
                self.penPressEvent(scenePos)

        elif scene.mode == EraserMode:
            self.eraserPressEvent(scenePos)

        elif scene.mode in [SelectMode, TextMode]:
            self.pointerPressEvent(self._event)

        event.accept()

    def mouseMoveEvent(self, event):

        if event.buttons() == QtCore.Qt.NoButton:
            # Ignore hover events
            return

        if self._eventstate != Mouse:
            # logging.debug("    (ignoring mousemove)")
            return
        # logging.debug('I mouseMoveEvent')

        scene = self.scene()
        scenePos = self.mapToScene(event.pos())
        scenePosF = scenePos.x(), scenePos.y()
        self._event.update("move", scenePosF)

        if scene.mode == PenMode:
            if not CONFIG['input_ignore_mouse']:
                self.penMoveEvent(scenePos)

        elif scene.mode == EraserMode:
            self.eraserMoveEvent(scenePos, self.transform())

        elif scene.mode in [SelectMode, TextMode]:
            self.pointerMoveEvent(self._event)

        event.accept()

    def mouseReleaseEvent(self, event):

        if self._eventstate != Mouse:
            # logging.debug("    (ignoring mouserelease)")
            return

        self._eventstate = Free
        # logging.debug('I mouseReleaseEvent')

        scene = self.scene()
        scenePos = self.mapToScene(event.pos())
        scenePosF = scenePos.x(), scenePos.y()
        self._event.update("release", scenePosF)

        if scene.mode == PenMode:
            if not CONFIG['input_ignore_mouse']:
                self.penReleaseEvent(self._event)

        elif scene.mode == EraserMode:
            self.eraserReleaseEvent(self._event)

        elif scene.mode in [SelectMode, TextMode]:
            self.pointerReleaseEvent(self._event)

        event.accept()

    def pointerPressEvent(self, event):
        '''
        Pointer has been pressed (stylus or mouse)
        - scenePos: position of click in scene coordinates
        '''
        # t = time.time()
        scene = self.scene()
        itemunder = scene.itemAt(QtCore.QPoint(*[int(x) for x in event.scenePos]), self.transform())
        if isinstance(itemunder, (OverRect,TransformationHandle, TextWidthWidget)):
            self._itemUnder = itemunder
            itemunder.pointerPressEvent(event)

        else:
            ## this grouping is so we can delete the items easily
            scene.tmpselect = QtWidgets.QGraphicsPolygonItem()
            scene.tmpselect.setPen(QtGui.QPen(QtCore.Qt.gray, 0.5 , QtCore.Qt.DotLine, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin))
            ## draw over everything
            scene.tmpselect.setZValue(1000)
            scene.addItem(scene.tmpselect)

            poly = QtGui.QPolygonF([QtCore.QPointF(*event.scenePos)])

        self.viewChangeStream.emit(self)

    def pointerMoveEvent(self, event):

        scene = self.scene()
        if self._itemUnder is not None:
            self._itemUnder.pointerMoveEvent(event)

        else:
            if hasattr(scene, "tmpselect"):
                poly = scene.tmpselect.polygon()
                poly.append(QtCore.QPointF(*event.scenePos))
                scene.tmpselect.setPolygon(poly)

        self.viewChangeStream.emit(self)


    def pointerReleaseEvent(self, event):
        scene = self.scene()
        if self._itemUnder is not None:
            self._itemUnder.pointerReleaseEvent(event)
            self._itemUnder = None

        else:

            if not hasattr(scene, "tmpselect"):
                return
            ## find surrounded items and select them
            items = []
            for item in list(scene.items()):
                if type(item) in [TextItem, InkItem, PixmapItem]:
                    items.append(item)
                    item.setSelected(False)

            for item in items:
                if scene.tmpselect.collidesWithItem(item):
                    item.setSelected(True)
            scene.removeItem(scene.tmpselect)

            scene.setSelectionWidget()

        self.viewChangeStream.emit(self)


    #
    # Pen action
    #
    def penPressEvent(self, scenePos, pressure = 0.5):

        t = time.time()
        scene = self.scene()
        scene._lastScenePos = scenePos

        ## this grouping is so we can delete the items easily
        scene.tmpgroup = QtWidgets.QGraphicsItemGroup()
        ## draw over everything
        scene.tmpgroup.setZValue(1000)
        scene.addItem(scene.tmpgroup)

        point = [scenePos.x(),scenePos.y(), pressure, t]
        scene._tmppath = [point]
        scene.strokecoords = [point]

        self.viewChangeStream.emit(self)


    def penMoveEvent(self, scenePos, pressure = 0.5):

        t = time.time()
        scene = self.scene()

        ## empasise more the initial changes in pressure
        ## tunes to astropad .. alittle heavy for wacom
        ## XXX make the pressure curve user adjustable
        #pressure = 1-exp(-2*pressure)
        #a= -0.3
        #b = 4
        #pressure = a*(1-pow(1-pressure,b))+(1-a)*pressure

        p1 = scene._lastScenePos
        p2 = scenePos
        pen = QtGui.QPen(scene.pen)
        pen.setCapStyle(QtCore.Qt.RoundCap)
        point = [p2.x(),p2.y(),pressure,t]
        scene.strokecoords.append(point)
        scene._tmppath.append(point)

        ## only draw the stroke segment every few calls
        ## otherwise mac can't cope and rate goes down, poor thing.
        if len(scene._tmppath)>4:
            x0,y0,z0,t0 = scene._tmppath[0]
            for x1,y1,z1,t1 in scene._tmppath[1:]:
                pen.setWidthF(scene.pen.widthF()*z1)
                line = scene.addLine(x0,y0,x1,y1,pen)
                line.setFlag(line.ItemIsSelectable,False)
                line.setEnabled(False)
                scene.tmpgroup.addToGroup(line)
                x0,y0,z0,t0 = x1,y1,z1,t1

            scene._tmppath = [[x1,y1,z1,t1]]

        scene._lastScenePos = p2
        self.viewChangeStream.emit(self)

    def penReleaseEvent(self, event):

        scene = self.scene()
        scene.maxZ +=1
        coords = smoothInkPath(scene.strokecoords)

        stroke = InkItem.new(scene.node, scene=scene,
                             z=scene.maxZ, width=scene.pen.widthF(),
                             color=scene.pen.color(), coords=coords)

        scene.refreshStem()
        if hasattr(scene, "tmpgroup"):
            for item in scene.tmpgroup.childItems():
                scene.removeItem(item)
            scene.removeItem(scene.tmpgroup)

        self.viewChangeStream.emit(self)

    #
    # Eraser action
    #
    def eraserPressEvent(self, scenePos):
        pass

    def eraserMoveEvent(self, scenePos, transform):

        scene = self.scene()
        item = scene.itemAt(scenePos, transform)

        ## only erase pen strokes, this makes is easy to annotate images
        if item is not None and isinstance(item, InkItem):
            scene.removeItem(item)

        self.viewChangeStream.emit(self)

    def eraserReleaseEvent(self, event):
        # All the action happens on move
        self.scene().refreshStem()

        self.viewChangeStream.emit(self)

    def event(self, event):

        if event.type() == QtCore.QEvent.Gesture:
            return self.gestureEvent(event)
        elif event.type() == QtCore.QEvent.TouchBegin:
            return self.touchBegin(event)
        elif event.type() == QtCore.QEvent.TouchUpdate:
            return self.touchUpdate(event)
        elif event.type() == QtCore.QEvent.TouchEnd:
            return self.touchEnd(event)
        elif event.type() == QtCore.QEvent.TouchCancel:
            return self.touchCancel(event)
        else:
            return QtWidgets.QGraphicsView.event(self, event)

    def touchBegin(self, event):
        #logging.debug('TouchBegin')
        return True

    def touchUpdate(self, event):
        #logging.debug('TouchUpdate points=%d', len(event.touchPoints()))
        return True

    def touchEnd(self, event):
        #logging.debug('TouchEnd')
        return True

    def touchCancel(self, event):
        #logging.debug('TouchCancel')
        return True

    def gestureEvent(self, event):
        pinch = event.gesture(QtCore.Qt.PinchGesture)

        if pinch is not None:
            #logging.debug('I PinchGesture [%d]',pinch.state())
            return self.pinchTriggered(pinch)
        else:
            return False

    def pinchTriggered(self, pinch):

        if platform.system() == 'Darwin':
            # On a mac the centre of the pinch gesture is not useful at the trackpad is relative
            # Need to use the cursor position as the centre:
            #v1 = self.mapFromGlobal(QtGui.QCursor.pos())
            v1 = pinch.centerPoint().toPoint()
        else:
            v1 = self.mapFromGlobal(pinch.centerPoint().toPoint())

        anchor = self.transformationAnchor()
        self.setTransformationAnchor(QtWidgets.QGraphicsView.NoAnchor)

        if pinch.state() == 1:
            # gesture begin
            if self._eventstate == Free:
                self._eventstate = Gesture
            elif self._eventstate == Mouse:
                self._eventstate = Gesture
                #logging.debug("    (switching to pinch from mouse)")
            else:
                #logging.debug("    (ignoring pinch press)")
                return False

            self._g_transform = self.transform()
            self._v0 = v1
            self._s0 = self.mapToScene(self._v0)
            self._sticky = True
            return  True

        elif pinch.state() == 3:
            if self._eventstate != Gesture:
                #logging.debug("    (ignoring pinch release)")
                return False
            else:
                self._eventstate = Free
                self._sticky = True

                return True

        if self._eventstate != Gesture:
            #logging.debug("    (ignoring pinch update)")
            return False

        Rtot = pinch.rotationAngle()
        Stot = pinch.totalScaleFactor()
        dv = v1-self._v0

        # XXX Following not working on mac?
        dist = sqrt(dv.x()**2+dv.y()**2)
        # logging.debug('Pinch dist %f', dist)

        # base movement stickiness on view coordinates (finger motion)
        if not ( CONFIG['pinch_no_scale_threshold'][0]<Stot<CONFIG['pinch_no_scale_threshold'][1] \
                 and abs(Rtot)<CONFIG['pinch_no_rotate_threshold'] \
                 and dist<CONFIG['pinch_no_move_threshold'] ):
            self._sticky = False

        if not self._sticky:
            matrix3 = Transform().scale(Stot,Stot).rotate(Rtot)
            M = Transform(matrix3*self._g_transform)
            Minv, dummy = M.inverted()

            sp = QtCore.QPointF(self.horizontalScrollBar().value(),
                                self.verticalScrollBar().value())
            Tc = Transform.fromTranslate(sp.x(),sp.y())

            D = QtCore.QPointF(v1)*Tc*Minv-self._s0

            M.translate(D.x(),D.y())
            self.setTransform(M, False)

        self.setTransformationAnchor(anchor)

        self.viewChangeStream.emit(self)

        return True

    def scaleView(self, scaleFactor):
        # XXX this seems a really bizare way of doing the scaling!
        factor = self.transform().scale(scaleFactor, scaleFactor).mapRect(QtCore.QRectF(0, 0, 1, 1)).width()
        if factor < 0.07 or factor > 100:
            return

        self.scale(scaleFactor, scaleFactor)
        self.viewChangeStream.emit(self)

    def zoomIn(self):
        self.scaleView(1.15)

    def zoomOut(self):
        self.scaleView(1 / 1.15)

    def zoomOriginal(self):
        self.setTransform(QtGui.QTransform())

    def zoomFitAll(self):
        rect = self.scene().itemsBoundingRect()
        #self.fitInView(rect)
        self.fitInView(rect,QtCore.Qt.KeepAspectRatio)


    def wheelEvent(self, event):
        # logging.debug('Wheel event')
        if (event.modifiers() & QtCore.Qt.ControlModifier) or  (event.modifiers() & QtCore.Qt.AltModifier):
            anchor = self.transformationAnchor()
            self.setTransformationAnchor(QtWidgets.QGraphicsView.NoAnchor)
            matrix = self.transform()
            p = self.mapToScene(self.mapFromGlobal(QtGui.QCursor.pos()))
            matrix.translate(p.x(),p.y())

            dS = pow(2.0, event.angleDelta().y() / 100.0)
            factor = matrix.scale(dS, dS).mapRect(QtCore.QRectF(0, 0, 1, 1)).width()
            if factor < 0.05 or factor > 1000:
                return

            matrix.scale(dS, dS)

            matrix.translate(-p.x(),-p.y())

            self.setTransform(matrix,False)

            self.setTransformationAnchor(anchor)

        else:
            degreesx = 2*8*event.angleDelta().x()
            distancex = -int(degreesx/30.0)
            degreesy = 2*8*event.angleDelta().y()
            distancey = -int(degreesy/30.0)

            sb=self.horizontalScrollBar()
            sb.setValue(sb.value()+distancex)

            sb=self.verticalScrollBar()
            sb.setValue(sb.value()+distancey)

        self.viewChangeStream.emit(self)

    def dropEvent(self, event):
        mimedata = event.mimeData()

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.viewChangeStream.emit(self)

##----------------------------------------------------------------------
class NexusScene(QtWidgets.QGraphicsScene):
##----------------------------------------------------------------------

    statusMessage = QtCore.pyqtSignal(str)
    linkClicked = QtCore.pyqtSignal(str)
    mapModified = QtCore.pyqtSignal()
    showEditDialog = QtCore.pyqtSignal(object)

    ## in presentation mode (changes how items react):
    #presentation = False
    mode = "edit"

    def __init__(self, parent = None):
        super().__init__(parent)

        self.setSceneRect(-3000, -3000, 6000, 6000)

        ## default mode for new dialogs (will remember last one chosen)
        # XXX remove newdialogmode now?
        #self.newdialogmode = TextMode
        #self.inputgeometry = None
        self.dialogstate = {
            'mode':TextMode,
            'geometry': None,
            'scale':1.0,
            'rotation':0.0,
        }

        self.backgroundDialog = BackgroundDialog(self, self.parent())
        self.backgroundDialog.hide()

        brush = QtGui.QBrush(QtGui.QColor("White"), QtCore.Qt.SolidPattern)
        self.setBackgroundBrush(brush)


    def dragEnterEvent(self, event):

        mimedata = event.mimeData()

        ## need to give feedback as to which item is closest
        if mimedata.hasImage() or mimedata.hasHtml() or mimedata.hasText() or mimedata.hasUrls():
            event.acceptProposedAction()
        else:
            super(NexusScene, self).dragEnterEvent(event)

    dragMoveEvent = dragEnterEvent


    def dropEvent(self, event):
        mimedata = event.mimeData()

        if not (mimedata.hasImage() or mimedata.hasHtml() or mimedata.hasText() or mimedata.hasUrls()):
            super(NexusScene, self).dragEnterEvent(event)
            return

        copynode, msg = self.graph.copyNodeWithMimedata(mimedata)
        if copynode is None:
            QtWidgets.QMessageBox.information(None, "Warning", msg)
            return

        view=self.views()[0]
        cp = view.mapFromGlobal(QtGui.QCursor.pos())
        targetpos = QtCore.QPointF(view.mapToScene(cp))

        ## find position relative to closest stem
        ## take a guess as a starting value
        closest = self.childStems()[0]
        pclosest = closest.mapFromScene(targetpos)-closest.tip()
        for target in self.allChildStems():
            p = target.mapFromScene(targetpos)-target.tip()
            if p.manhattanLength() < pclosest.manhattanLength():
                pclosest = p
                closest = target

        batch = graphydb.generateUUID()
        nodes = copynode.outN('e.kind="Child"')
        basenodes = self.graph.copyTrees(nodes, batch=batch, setchange=True)
        for b in basenodes:
            self.graph.Edge(closest.node, 'Child', b).save(batch=batch, setchange=True)
        closest.renew(create=False)

    def delete(self, *param, stem=None):
        '''
        Delete selected items
        '''
        ## find selected base stems (selection may include children)
        nodes = graphydb.NSet()
        parents = []
        if stem is None:
            selected = set(self.selectedItems())
        else:
            selected = {stem}

        for item in selected:
            if isinstance(item, StemItem) \
               and selected.isdisjoint(item.allParentStems()):
                nodes.add(item.node)
                parent = item.parentStem()
                if parent is not None and parent not in parents:
                    parents.append(parent)

        batch = graphydb.generateUUID()
        self.graph.deleteOutFromNodes(nodes, batch=batch, setchange=True)

        for parent in parents:
            parent.renew()

    def cut(self, *param,stem=None):
        self.copy(stem=stem)
        self.delete(stem=stem)

    def copyStemLink(self, *param,stem=None):
        urls = []

        if stem is None:
            selected = set(self.selectedItems())
        else:
            selected = {stem}

        for item in selected:
            if isinstance(item, StemItem):
                link=item.node.graph.getNodeLink(item.node)
                urls.append(QtCore.QUrl(link))

        if len(urls)==0:
            urls = [QtCore.QUrl(self.graph.getNodeLink())]

        clipboard = QtWidgets.QApplication.clipboard()
        mimedata = QtCore.QMimeData()
        mimedata.setUrls(urls)

        clipboard.setMimeData(mimedata)

    def copy(self, *param,stem=None):
        # TODO create a Copy As function (plugins)
        # TODO skip hidden nodes (setting?)

        g = self.graph
        copynode = g.getCopyNode(clear=True)

        if stem is None:
            selected = set(self.selectedItems())
        else:
            selected = {stem}

        ## find selected base stems (selection may include children)
        nodes = graphydb.NSet()
        for item in selected:
            if isinstance(item, StemItem) \
               and selected.isdisjoint(item.allParentStems()):
                nodes.add(item.node)

        # Make copies of sub-trees from selected
        basenodes = g.copyTrees(nodes)
        # link them to the copynode
        for node in basenodes:
            g.Edge(copynode, 'Child', node).save(setchange=True)

        # store nexus link in copy register
        link = g.getNodeLink(copynode)
        clipboard = QtWidgets.QApplication.clipboard()
        mimedata = QtCore.QMimeData()
        mimedata.setData("application/x-nexus", bytes(link, 'utf-8'))
        clipboard.setMimeData(mimedata)

    def paste(self, *param, stem=None):
        if stem is None:
            selected = set(self.selectedItems())
        else:
            selected = {stem}

        if len(selected)==0:
            QtWidgets.QMessageBox.information(None,"Warning", "No stems selected.")
            return

        clipboard = QtWidgets.QApplication.clipboard()
        mimedata = clipboard.mimeData()

        g = self.graph
        copynode, msg = g.copyNodeWithMimedata(mimedata)
        if copynode is None:
            QtWidgets.QMessageBox.information(None,"Warning", msg)
            return

        batch = graphydb.generateUUID()
        nodes = copynode.outN('e.kind="Child"')
        for target in selected:
            basenodes = g.copyTrees(nodes, batch=batch, setchange=True)
            for b in basenodes:
                g.Edge(target.node, 'Child', b).save(batch=batch, setchange=True)
            target.renew(create=False)

    def allChildStems(self, includeroot=True, nottaggedhide=False):
        '''
        return list of all decendant stems (sorted acording to position)
        '''
        allstems = []
        for root in self.childStems():
            if includeroot:
                if nottaggedhide and 'hide' in root.getTags():
                    ## this is silly but if they request it ... ah well
                    continue
                allstems.append(root)
            allstems.extend(root.allChildStems(nottaggedhide))

        return allstems

    def childStems(self):
        '''
        return list of direct decendants stems (lvl 0)
        '''
        stems = []
        for item in list(self.items()):
            if isinstance(item, StemItem) and item.parentStem() is None:
                stems.append(item)

        return stems

    def root(self):
        # XXX this will fail if there are more than one root's
        return self.childStems()[0]







##----------------------------------------------------------------------
class NexusView(QtWidgets.QGraphicsView):
##----------------------------------------------------------------------

    DRAGOFF = 0
    DRAGPAN = 1
    DRAGZOOM = 2
    PREDRAGPAN = 3

    _dragmode = DRAGOFF
    _dragy = 0
    _dragx = 0

    # on windows pinch events also send a mouse move
    # ignore mouse move for this time [s] after a pinch:
    # _ignoremousetime = 0

    # seems different trackpads/mice have different zoom factors
    _scrollwheelfactor = 0.5

    # on iw3 no key presses are received by action when in full screen
    # Do alternative pathway here
    presentationEscape = QtCore.pyqtSignal()

    # send position and pen events for recording
    recordStateEvent = QtCore.pyqtSignal(dict)

    viewChangeStream = QtCore.pyqtSignal(QtWidgets.QGraphicsView)

    def __init__(self, scene, parent = None):

        super().__init__(scene, parent)

        self.setViewportUpdateMode(QtWidgets.QGraphicsView.SmartViewportUpdate)

        self.setRenderHint(QtGui.QPainter.Antialiasing)
        self.setRenderHint(QtGui.QPainter.TextAntialiasing)
        self.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)
        self.setCacheMode(self.CacheNone)

        # implement the drag pan ourselves to avoid tablet event bug
        self.setDragMode(QtWidgets.QGraphicsView.NoDrag)

        self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)

        self.viewport().setCursor(QtCore.Qt.OpenHandCursor)

        self.setOptimizationFlags(self.DontSavePainterState | self.DontAdjustForAntialiasing)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, False)

        self.grabGesture(QtCore.Qt.PanGesture)
        self.grabGesture(QtCore.Qt.PinchGesture)
        #self.grabGesture(QtCore.Qt.SwipeGesture)

        # some data structures to hold the pointer trail
        # the points are in a list of lists in reverse order
        self.pointertrail = []
        self.pointertrailitem = None
        self.pointertrailitem2 = None
        self._trailTimer = QtCore.QTimer()
        self._trailTimer.setSingleShot(True)
        self._trailTimer.timeout.connect(self.trailTimerExpire)
        self._trailTimer.setInterval(int(CONFIG['trail_hold_time'])*1000)

        # track when pinch events occur
        self.pinchtime = 0

        self._sticky = True

    def scaleView(self, scaleFactor, point=None):

        matrix = self.transform()
        ## first check final scale is within an acceptable range

        factor = matrix.scale(scaleFactor, scaleFactor).mapRect(QtCore.QRectF(0, 0, 1, 1)).width()
        if factor < 0.05 or factor > 1000:
            return

        if point is None:
            matrix.scale(scaleFactor, scaleFactor)

        else:
            matrix.translate(-point.x(),-point.y())
            matrix.scale(scaleFactor, scaleFactor)
            matrix.translate(point.x(),point.y())

        self.setTransform(matrix,False)



    def zoomIn(self):
        self.scaleView(1.15)

    def zoomOut(self):
        self.scaleView(1 / 1.15)

    def zoomOriginal(self):
        ## XXX set 1:1 zoom
        logging.warn("zoomOriginal not implemented")

    def zoomSelection(self):

        selected = self.scene().selectedItems()
        rect = QtCore.QRectF()
        if len(selected)>0:
            for item in selected:
                rect=rect.united(item.sceneBoundingRect())

        else:
            for item in self.scene().allChildStems():
                rect=rect.united(item.sceneBoundingRect())

        self.fitInView(rect, QtCore.Qt.KeepAspectRatio)

    def getViewSides(self):
        '''
        Get the left and right center points of view
        '''
        vrect = self.viewport().rect()

        vleft = QtCore.QPoint(vrect.left(),int(vrect.top()+vrect.height()/2.0))
        # According to docs for historical reasons rect.right = rect.left+rect.width-1 so do it ourselves
        vright = QtCore.QPoint(vrect.left()+vrect.width(), int(vrect.top()+vrect.height()/2.0))

        sleft = self.mapToScene(vleft)
        sright = self.mapToScene(vright)

        left = (sleft.x(), sleft.y())
        right = (sright.x(),sright.y())

        return {'left':left, 'right':right}


    def setViewSides(self, sides):
        '''
        Set the view based on the center x,y, scale and rotation
        '''
        L = sides['left']
        R = sides['right']

        vrect = self.viewport().rect()
        cx = (L[0]+R[0])/2
        cy = (L[1]+R[1])/2
        s = vrect.width()/sqrt((R[0]-L[0])**2+(R[1]-L[1])**2)
        r = atan2(-(R[1]-L[1]), R[0]-L[0])

        matrix = Transform().setTRS(0,0,r,s)
        self.setTransform(matrix)
        self.centerOn(cx, cy)

        # when recording, these events will be caught otherwise ignored
        self.recordStateEvent.emit({'t':time.time(),'cmd':'view', 'left':sides['left'], 'right':sides['right']})

        # when streaming
        self.viewChangeStream.emit(self)


    def wheelEvent(self, event):

        if (event.modifiers() & QtCore.Qt.ControlModifier) or (event.modifiers() & QtCore.Qt.AltModifier):

            # logging.debug('wheelEvent (mod)')

            anchor = self.transformationAnchor()
            self.setTransformationAnchor(QtWidgets.QGraphicsView.NoAnchor)
            matrix = self.transform()
            p = self.mapToScene(self.mapFromGlobal(QtGui.QCursor.pos()))
            matrix.translate(p.x(),p.y())

            dS = pow(2.0, event.angleDelta().y() / 100.0 * self._scrollwheelfactor)
            factor = matrix.scale(dS, dS).mapRect(QtCore.QRectF(0, 0, 1, 1)).width()
            if factor < 0.05 or factor > 1000:
                return

            matrix.scale(dS, dS)

            matrix.translate(-p.x(),-p.y())

            self.setTransform(matrix,False)

            self.setTransformationAnchor(anchor)
        else:

            # logging.debug('wheelEvent')

            degreesy = 2*8*event.angleDelta().y() * self._scrollwheelfactor
            distancey = -int(degreesy/30.0)

            degreesx = 2*8*event.angleDelta().x() * self._scrollwheelfactor
            distancex = -int(degreesx/30.0)

            sb=self.horizontalScrollBar()
            sb.setValue(sb.value()+distancex)
            sb=self.verticalScrollBar()
            sb.setValue(sb.value()+distancey)

        event.accept()
        self.viewChangeStream.emit(self)



    def mousePressEvent(self, event):

        # if abs(self.pinchtime - time.time())<self._ignoremousetime:
        #     event.accept()
        #     return

        # logging.debug('N mousePressEvent')

        if self.scene().mode in ["presentation", "record"]:
            self._dragmode = self.PREDRAGPAN

        elif event.button() in [QtCore.Qt.RightButton, QtCore.Qt.MiddleButton] and (self.itemAt(event.pos()) is None):
            self._dragmode = self.DRAGZOOM
            self._dragy = event.pos().y()
            self.viewport().setCursor(QtCore.Qt.SizeVerCursor)
            self._zoompoint = self.mapToScene(event.pos())
        elif event.button()==QtCore.Qt.LeftButton and (self.itemAt(event.pos()) is None):
            self._dragmode = self.PREDRAGPAN
            self._dragy = event.pos().y()
            self._dragx = event.pos().x()
            self.viewport().setCursor(QtCore.Qt.ClosedHandCursor)
        else:
            self._dragmode = self.DRAGOFF
            self.viewport().setCursor(QtCore.Qt.OpenHandCursor)
            QtWidgets.QGraphicsView.mousePressEvent(self, event)

    def mouseMoveEvent(self, event):
        # XXX performance
        ## movement triggers drag move

        # if abs(self.pinchtime - time.time())<self._ignoremousetime:
        #     event.accept()
        #     return

        # logging.debug('N mouseMoveEvent')
        if self._dragmode == self.PREDRAGPAN:
            self._dragmode=self.DRAGPAN

        if self._dragmode == self.DRAGZOOM:
            dy = event.pos().y() - self._dragy
            scale = max(min(-dy/400.0 + 1,1.5),0.5)

            self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorViewCenter)
            self.scaleView(scale)

            self._dragy = event.pos().y()

            self.viewChangeStream.emit(self)
            event.accept()

        elif self._dragmode == self.DRAGPAN and self.scene().mode in ["presentation", "record"]:

            s = self.transform().m11()
            self._trailTimer.stop()
            ps = self.mapToScene(event.pos())
            self.recordStateEvent.emit({'t':time.time(), 'cmd':'pen-point','x':ps.x(), 'y':ps.y()})
            if len(self.pointertrail)==0:
                # if there's nothing in the queue add the point within a stroke list
                self.pointertrail.append([ps])
            else:
                # Append to last strokelist
                self.pointertrail[-1].append(ps)

            # create the graphics items for the pointer trail
            if self.pointertrailitem is None:

                self.pointertrailitem = QtWidgets.QGraphicsPathItem(QtGui.QPainterPath())
                #self.pointertrailitem.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations, True)
                pen = QtGui.QPen(QtGui.QColor(CONFIG['trail_outer_color']))
                pen.setWidthF(CONFIG['trail_outer_width']/s)
                pen.setCapStyle(QtCore.Qt.RoundCap)
                self.pointertrailitem.setPen(pen)
                TrailBlur = QtWidgets.QGraphicsBlurEffect()
                TrailBlur.setBlurRadius(5.0/s)
                self.pointertrailitem.setGraphicsEffect(TrailBlur)
                self.scene().addItem(self.pointertrailitem)
            if self.pointertrailitem2 is None:
                # inner collor
                self.pointertrailitem2 = QtWidgets.QGraphicsPathItem(QtGui.QPainterPath())
                #self.pointertrailitem2.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations, True)
                pen = QtGui.QPen(QtGui.QColor(CONFIG['trail_inner_color']))
                pen.setWidthF(CONFIG['trail_inner_width']/s)
                pen.setCapStyle(QtCore.Qt.RoundCap)
                self.pointertrailitem2.setPen(pen)
                TrailBlur = QtWidgets.QGraphicsBlurEffect()
                TrailBlur.setBlurRadius(4.0/s)
                self.pointertrailitem2.setGraphicsEffect(TrailBlur)
                self.scene().addItem(self.pointertrailitem2)

            path = QtGui.QPainterPath()
            path2 = QtGui.QPainterPath()
            for stroke in reversed(self.pointertrail):
                if len(stroke)==0:
                    continue
                path.moveTo(stroke[-1])
                path2.moveTo(stroke[-1])
                for p in reversed(stroke[:-1]):
                    path.lineTo(p)
                    path2.lineTo(p)
            self.pointertrailitem.setPath(path)
            self.pointertrailitem2.setPath(path)

            self.viewChangeStream.emit(self)


        elif self._dragmode == self.DRAGPAN:
            hbar = self.horizontalScrollBar()
            vbar = self.verticalScrollBar()

            x = event.pos().x()
            y = event.pos().y()

            dx = x - self._dragx
            dy = y - self._dragy

            hbar.setValue(hbar.value()-dx)
            vbar.setValue(vbar.value()-dy)

            self._dragx = x
            self._dragy = y

            self.viewChangeStream.emit(self)
            event.accept()

        elif not self.scene().mode in ["presentation", "record"]:
            self.viewport().setCursor(QtCore.Qt.OpenHandCursor)
            QtWidgets.QGraphicsView.mouseMoveEvent(self, event)



    def mouseReleaseEvent(self, event):

        #if abs(self.pinchtime - time.time())<self._ignoremousetime:
        #    event.accept()
        #    return

        # logging.debug('N mouseReleaseEvent')

        if self._dragmode == self.PREDRAGPAN:
            for stem in self.scene().allChildStems():
                stem.setSelected(False)
        self._dragmode = self.DRAGOFF

        # start a new stroke
        self.pointertrail.append([])
        self._trailTimer.start()
       

        if not self.scene().mode in ["presentation", "record"]:
            self.viewport().setCursor(QtCore.Qt.OpenHandCursor)
            QtWidgets.QGraphicsView.mouseReleaseEvent(self, event)
            self.recordStateEvent.emit({'t':time.time(), 'cmd':'pen-up'})

        self.viewChangeStream.emit(self)

    def mouseDoubleClickEvent(self, event):

        if self.scene().mode in ["presentation", "record"]:
            item = self.itemAt(event.pos())
            if isinstance( item, OpenCloseWidget):
                # pass through event for open-close widget as a single click
                item.mousePressEvent(event)
            else:
                # the item could be any of the individual scene items
                # if it's an item in a stem get the stem
                stem = None
                try:
                    parent = item.parentItem()
                    if isinstance( parent, StemItem ):
                        stem = parent
                    elif isinstance( parent, Leaf ):
                        stem = parent.parentItem()
                except:
                    pass
                if stem is not None:
                    stem.editStem()

            event.ignore()
        else:
            super().mouseDoubleClickEvent(event)


    def trailTimerExpire(self):
        self.pointertrail.clear()
        if self.pointertrailitem is not None:
            self.scene().removeItem(self.pointertrailitem )
            self.pointertrailitem = None
        if self.pointertrailitem2 is not None:
            self.scene().removeItem(self.pointertrailitem2 )
            self.pointertrailitem2 = None
        self.recordStateEvent.emit({'t':time.time(), 'cmd':'pen-clear'})
        self.viewChangeStream.emit(self)




    def keyPressEvent(self, event):
        if self.scene().mode in ["presentation", "record"] and event.key() == QtCore.Qt.Key_Escape:
            self.presentationEscape.emit()
            event.accept()
        else:
            super().keyPressEvent(event)


    def event(self, event):
        if event.type() == QtCore.QEvent.Gesture:
            return self.gestureEvent(event)
        else:
            return QtWidgets.QGraphicsView.event(self, event)

    def gestureEvent(self, event):
        pinch = event.gesture(QtCore.Qt.PinchGesture)
        pan = event.gesture(QtCore.Qt.PanGesture)
        swipe = event.gesture(QtCore.Qt.SwipeGesture)

        if swipe is not None:
            # logging.debug('N SwipeGesture [%s]',swipe.state())
            pass
        elif pan is not None:
            # logging.debug('N PanGesture [%d]',pan.state())
            pass

        if pinch is not None:
            # logging.debug('N PinchGesture [%d]',pinch.state())
            self.pinchTriggered(pinch)
            event.accept()

        return True

    def pinchTriggered(self, pinch):

        # self.pinchtime = time.time()

        if platform.system() == 'Darwin':
            # On a mac the centre of the pinch gesture is not useful at the trackpad is relative
            # Need to use the cursor position as the centre:
            #v1 = self.mapFromGlobal(QtGui.QCursor.pos())
            v1 = pinch.centerPoint().toPoint()
        else:
            v1 = self.mapFromGlobal(pinch.centerPoint().toPoint())

        anchor = self.transformationAnchor()
        self.setTransformationAnchor(QtWidgets.QGraphicsView.NoAnchor)

        self._dragmode = self.DRAGOFF

        if anchor == QtWidgets.QGraphicsView.AnchorUnderMouse:
            ## this is used in normal mode
            #v1 = self.mapToScene(self.mapFromGlobal(QtGui.QCursor.pos()))
            #p = c1
            pass
        elif anchor == QtWidgets.QGraphicsView.AnchorViewCenter:
            ## this is used in presentation mode
            v1 = self.viewport().rect().center()
        else:
            pass
            #v1 = QtCore.QPointF(0,0)

        if pinch.state() == 1:
            # gesture begin
            # if self._eventstate == Free:
            #     self._eventstate = Gesture
            # elif self._eventstate == Mouse:
            #     self._eventstate = Gesture
            #     logging.debug("    Switching to Gesture")
            # else:
            #     logging.debug("    Not Free ot Mouse")
            #     return
            self._g_transform = self.transform()
            self._v0 = v1
            self._s0 = self.mapToScene(self._v0)
            self._sticky = True
            return
        elif pinch.state() == 3:
            # self._eventstate = Free
            self._sticky = True

            return

        # if self._eventstate != Gesture:
        #     return
        if self.parent().viewRotateAct.isChecked():
            Rtot = pinch.rotationAngle()
        else:
            Rtot = 0
        Stot = pinch.totalScaleFactor()
        dv = v1-self._v0

        # XXX Following not working on mac?
        dist = sqrt(dv.x()**2+dv.y()**2)
        #logging.debug('Pinch dist %f', dist)
 
        # base movement stickiness on view coordinates (finger motion)
        if not ( CONFIG['pinch_no_scale_threshold'][0]<Stot<CONFIG['pinch_no_scale_threshold'][1] \
                 and abs(Rtot)<CONFIG['pinch_no_rotate_threshold'] \
                 and dist<CONFIG['pinch_no_move_threshold'] ):
            self._sticky = False

        if not self._sticky:
            matrix3 = Transform().scale(Stot,Stot).rotate(Rtot)
            M = Transform(matrix3*self._g_transform)
            Minv, dummy = M.inverted()

            sp = QtCore.QPointF(self.horizontalScrollBar().value(),
                                self.verticalScrollBar().value())
            Tc = Transform.fromTranslate(sp.x(),sp.y())

            D = QtCore.QPointF(v1)*Tc*Minv-self._s0

            # XXX Limit total scale?

            M.translate(D.x(),D.y())
            self.setTransform(M, False)

            self.viewChangeStream.emit(self)


        self.setTransformationAnchor(anchor)


    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.viewChangeStream.emit(self)


##----------------------------------------------------------------------
class BackgroundDialog(QtWidgets.QDialog):
##----------------------------------------------------------------------

    def __init__(self, scene,  parent=None):

        super().__init__(parent)
        self.setModal(False)
        self.setWindowTitle("Map background")

        ## store the scene locally so we can make live changes
        self.scene = scene

        brush = self.scene.backgroundBrush()

        baselayout = QtWidgets.QGridLayout()
        self.setLayout(baselayout)

        baselayout.addWidget(QtWidgets.QLabel("Remove background:") ,0, 0)
        button = QtWidgets.QPushButton()
        button.setText("Clear All")
        button.clicked.connect(self.clearBack)
        baselayout.addWidget(button, 0, 1)

        ## -------------------------------------------------
        page  = QtWidgets.QGroupBox("Solid Color")
        page.setCheckable(True)
        baselayout.addWidget(page, 1, 0, 1, 2)
        layout = QtWidgets.QGridLayout()
        page.setLayout(layout)
        page.clicked.connect(lambda x: self.styleSwitch(1,x))
        self.page1 = page

        layout.addWidget(QtWidgets.QLabel("Color:") ,0, 0)
        if brush.style() == QtCore.Qt.SolidPattern:
            color = brush.color()
            page.setChecked(True)
        else:
            color = QtGui.QColor(QtCore.Qt.white)
            page.setChecked(False)
        pix = QtGui.QPixmap(16,16)
        pix.fill(color)
        colorswatch = QtGui.QIcon(pix)
        button = QtWidgets.QToolButton()
        button.setIcon(colorswatch)
        layout.addWidget(button, 0, 1)
        button.clicked.connect(self.setColor)
        self.colorswatchbutton = button

        ## -------------------------------------------------
        page  = QtWidgets.QGroupBox("Tiled Image")
        page.setCheckable(True)
        baselayout.addWidget(page, 2, 0, 1, 2)
        layout = QtWidgets.QGridLayout()
        page.setLayout(layout)
        page.clicked.connect(lambda x: self.styleSwitch(2,x))
        self.page2 = page
        if brush.style() == QtCore.Qt.TexturePattern:
            page.setChecked(True)
        else:
            page.setChecked(False)

        layout.addWidget(QtWidgets.QLabel("Set image:"), 0, 0)

        button = QtWidgets.QPushButton()
        button.setText("Image")
        button.clicked.connect(self.setImage)
        layout.addWidget(button,0,1)


        ## -------------------------------------------------
        page  = QtWidgets.QGroupBox("Radial Gradient")
        page.setCheckable(True)
        baselayout.addWidget(page, 3, 0, 1, 2)
        layout = QtWidgets.QGridLayout()
        page.setLayout(layout)
        page.clicked.connect(lambda x: self.styleSwitch(3,x))
        self.page3 = page
        if brush.style() == QtCore.Qt.RadialGradientPattern:
            page.setChecked(True)
        else:
            page.setChecked(False)

        layout.addWidget(QtWidgets.QLabel("Colors:"), 0, 0)
        layout.addWidget(QtWidgets.QLabel("Radius:"), 1, 0)

        col = QtGui.QColor(QtCore.Qt.gray)
        pix = QtGui.QPixmap(16,16)
        pix.fill(col)
        colorswatch = QtGui.QIcon(pix)
        button = QtWidgets.QToolButton()
        button.setIcon(colorswatch)
        layout.addWidget(button, 0, 1)
        button.clicked.connect(self.setColor1)
        self.color1button = button
        self.color1 = col

        col = QtGui.QColor(QtCore.Qt.white)
        pix = QtGui.QPixmap(16,16)
        pix.fill(col)
        colorswatch = QtGui.QIcon(pix)
        button = QtWidgets.QToolButton()
        button.setIcon(colorswatch)
        layout.addWidget(button, 0, 2)
        button.clicked.connect(self.setColor2)
        self.color2button = button
        self.color2 = col

        self.radius = QtWidgets.QSpinBox()
        self.radius.setRange(1,2000)
        self.radius.setValue(200)
        self.radius.setSingleStep(10)
        layout.addWidget(self.radius, 1, 1)
        self.radius.valueChanged.connect(self.setRadialBrush)

        ## -------------------------------------------------
        page  = QtWidgets.QGroupBox("General Properties")
        baselayout.addWidget(page, 4, 0, 1, 2)
        layout = QtWidgets.QGridLayout()
        page.setLayout(layout)


        layout.addWidget(QtWidgets.QLabel("Scale:"),0,0)
        scale = QtWidgets.QDoubleSpinBox()
        scale.setRange(0.1,10)
        scale.setValue(1)
        scale.setSingleStep(0.1)
        layout.addWidget(scale,0,1)
        scale.valueChanged.connect(self.setScale)

        self.show()


    def setColor(self):

        brush = self.scene.backgroundBrush()
        col = QtWidgets.QColorDialog.getColor(brush.color(), options=QtWidgets.QColorDialog.ShowAlphaChannel )
        if col.isValid():

            pix = QtGui.QPixmap(16,16)
            pix.fill(col)
            colorswatch = QtGui.QIcon(pix)
            self.colorswatchbutton.setIcon(colorswatch)

            brush = QtGui.QBrush(col, QtCore.Qt.SolidPattern)
            self.scene.setBackgroundBrush(brush)



    def setBrushPattern(self, item):
        v = self.backgroundStyleCombo.itemData(item)
        d, test = v.toInt()
        brush = self.scene.backgroundBrush()
        brush.setStyle(d)
        self.scene.setBackgroundBrush(brush)

    def setImage(self):

        fileName = QtWidgets.QFileDialog.getOpenFileName(None, "Select Image", filter="Images (*.png *.jpg) ;; All files (*)")[0]
        if len(fileName) > 0:
            brush = self.scene.backgroundBrush()
            brush.setTextureImage(QtGui.QImage(fileName))
            self.scene.setBackgroundBrush(brush)

    def setScale(self, value):

        brush = self.scene.backgroundBrush()
        m = QtGui.QTransform()
        m.scale(value, value)
        brush.setTransform(m)
        self.scene.setBackgroundBrush(brush)

    def clearBack(self):

        brush = QtGui.QBrush(QtCore.Qt.NoBrush)
        self.scene.setBackgroundBrush(brush)

    def setColor1(self):

        col = QtWidgets.QColorDialog.getColor(self.color1)
        if col.isValid():
            pix = QtGui.QPixmap(16,16)
            pix.fill(col)
            colorswatch = QtGui.QIcon(pix)
            self.color1button.setIcon(colorswatch)
            self.color1 = col

            self.setRadialBrush()

    def setColor2(self):

        col = QtWidgets.QColorDialog.getColor(self.color2)
        if col.isValid():
            pix = QtGui.QPixmap(16,16)
            pix.fill(col)
            colorswatch = QtGui.QIcon(pix)
            self.color2button.setIcon(colorswatch)
            self.color2 = col

            self.setRadialBrush()

    def setRadialBrush(self):

        gradient = QtGui.QRadialGradient(0,0,self.radius.value(),0,0)
        gradient.setColorAt(0, self.color1)
        gradient.setColorAt(1, self.color2)
        brush=QtGui.QBrush(gradient)

        self.scene.setBackgroundBrush(brush)

    def styleSwitch(self, box, checked):

        if box == 1:
            if checked:
                self.page2.setChecked(False)
                self.page3.setChecked(False)
            else:
                self.page1.setChecked(True)
        elif box == 2:
            if checked:
                self.page1.setChecked(False)
                self.page3.setChecked(False)
            else:
                self.page2.setChecked(True)
        elif box == 3:
            if checked:
                self.page1.setChecked(False)
                self.page2.setChecked(False)
            else:
                self.page3.setChecked(True)


## ----------------------------------------------------------------------
def dot(v1,v2):
    '''
    return the dot product between v1 and v2
    '''

    ans=0
    for a in map(lambda x,y:x*y, v1,v2):
        ans+=a
    return ans
## ----------------------------------------------------------------------
def distanceToLine(P,A,B):
    '''
    Calculate Euclidean distance from P to line A-B in any number of dimensions
    '''

    P = tuple(P)
    A = tuple(A)
    B = tuple(B)

    AP = [v for v in map(lambda x,y:x-y, A,P)]
    AB = [v for v in map(lambda x,y:x-y, A,B)]

    ABAP = dot(AB,AP)
    ABAB = dot(AB,AB)
    APAP = dot(AP,AP)

    d = sqrt(abs(APAP-ABAP**2/ABAB))

    return d

def gaussianSmoothing(P, factor=0.6, near=7):
    '''
    Apply Gaussian weighted smoothing to points

    :param P: list of points [(x,y,z), (x,y,z)]
    :param factor: strength of smoothing
    :param near: only apply smoothing if change is less than this
    :return: smoothed points
    '''

    factor = 0.6

    s0 = 1 - 2 * factor / 3.  # weighting of principal point
    s1 = factor / 3.  # weighting of side points

    near = 7

    Ps = list(P)
    for ii in range(1, len(P) - 1):
        diff = (P[ii][0] - P[ii - 1][0]) ** 2 + (P[ii][1] - P[ii - 1][1]) ** 2 + (P[ii][2] - P[ii - 1][2]) ** 2 \
               + (P[ii][0] - P[ii + 1][0]) ** 2 + (P[ii][1] - P[ii + 1][1]) ** 2 + (P[ii][2] - P[ii + 1][2]) ** 2
        if diff < near:
            Ps[ii][0] = s0 * P[ii][0] + s1 * P[ii - 1][0] + s1 * P[ii + 1][0]
            Ps[ii][1] = s0 * P[ii][1] + s1 * P[ii - 1][1] + s1 * P[ii + 1][1]
            Ps[ii][2] = s0 * P[ii][2] + s1 * P[ii - 1][2] + s1 * P[ii + 1][2]
            # XXX also smooth the width?

    return Ps

## ----------------------------------------------------------------------
def simplifyLowes(curve, i,f, simplified, tol=.1):
    '''
    Recursively simplify a curve using Lowes method

    :param curve: list of points [(f,x,y,z,...), (f,x,y,z,...), ...]
        each point has the frame as element 0 and can be of any dimension
    :param i,f: the initial and final indexes for the section to be simplified
    :param simplified: set of frames to retain, algorithm will add to and return this set
    :param tol: maximum Cartesian distance error to tolerate
    :return: smaller set of points
    '''

    pl1 = curve[i]
    pl2 = curve[f]

    ## store frame numbers
    simplified.add(pl1[0])
    simplified.add(pl2[0])

    maxd = 0
    maxi = 0
    for ii in range(i+1,f):
        p = curve[ii]
        d = distanceToLine(p,pl1,pl2)
        if d > maxd:
            maxd = d
            maxi = ii

    if maxd > tol:

        if maxi==f-1:
            simplified.add(curve[maxi][0])
        else:
            simplified = simplifyLowes(curve, maxi, f, simplified, tol=tol)

        if maxi==i+1:
            simplified.add(curve[maxi][0])
        else:
            simplified = simplifyLowes(curve, i, maxi, simplified, tol=tol)

    return simplified


def smoothInkPath(P):

    if len(P)==0:
        logging.warning("zero stroke path length")
        return []

    try:
        rate = len(P)/(P[-1][3]-P[0][3])
    except ZeroDivisionError:
        rate = 0

    Ps = gaussianSmoothing(P)

    # now simplify the path removing unnecessary points
    raw = []
    # add indices to the points
    for pp in range(len(Ps)):
        pt=list(Ps[pp])
        pt[2] *= 10
        pt.insert(0,pp)
        raw.append(pt)

    simplified = simplifyLowes(raw, 0, len(raw)-1, set(), tol=.18)

    simplified = list(simplified)
    simplified.sort()

    S=[]
    for ii in simplified:
        S.append(Ps[ii])

    # logging.debug("stroke simplification: %d -> %d (%.1f%%)  \t\tRate: %.2f ",len(P),len(S),len(S)/float(len(P))*100, rate)

    return S

def sign(x):
    return -2*(x<0)+1


## HSV values in [0..1]
## returns [r, g, b] values from 0 to 255
def hsv_to_rgb(h, s, v):
    h_i = int(h*6)
    f = h*6 - h_i
    p = v * (1 - s)
    q = v * (1 - f*s)
    t = v * (1 - (1 - f) * s)
    if h_i==0: r, g, b = v, t, p
    if h_i==1: r, g, b = q, v, p
    if h_i==2: r, g, b = p, v, t
    if h_i==3: r, g, b = p, q, v
    if h_i==4: r, g, b = t, p, v
    if h_i==5: r, g, b = v, p, q
    return '#%X%X%X'%(round(r*255),round(g*255),round(b*255))

##----------------------------------------------------------------------
class InkItem(QtWidgets.QGraphicsPathItem):
##----------------------------------------------------------------------


    def __init__(self, node, scene=None, parent=None):
        ## Rendered in one of two ways:
        ## 1) in tree: parent = leaf container item, scene = None
        ## 2) in edit dialog: parent = None and scene = edit scene

        if parent is None:
            super().__init__()
            scene.addItem(self)
        else:
            super().__init__(parent)

        self.node = node

        self.setAcceptHoverEvents(True)
        self.originalCursor = None
        # XXX consolidate cursor setting code

        self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, False)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsMovable, False)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsFocusable, False)
        self.setZValue(node['z'])

        self.width = node['width']
        self.color = QtGui.QColor(node.get('color','#000000'))
        self.color.setAlphaF(node.get('opacity',1.0))

        self.setinkpath(node['stroke'])
        self.setTransform(Transform(*node['frame']))

        # used to track moves, scales, etc
        self._changed = False

    @classmethod
    def new(cls, stemnode, scene, coords=[], transform=Transform(),
            z=1, width=1.0, color=QtGui.QColor("Black"),
            batch=None, setchange=True):
        '''
        Convenience method to create a new DB node from QT objects
        '''

        newnode = stemnode.graph.Node('Stroke')
        newedge = stemnode.graph.Edge(stemnode, 'In', newnode)

        newnode['z'] = z
        newnode['width'] = width

        newnode['color'] = str(color.name())
        newnode['opacity'] = color.alphaF()

        XYZ = len(coords[0])>2
        if XYZ:
            newnode['type'] = "XYZ"
        else:
            newnode['type'] = "XY"

        # coords are relative to first point for compression
        # position carried in frame
        p0 = coords[0]
        out = []
        for p in coords:
            if XYZ:
                out.append([p[0]-p0[0], p[1]-p0[1],p[2]])
            else:
                out.append([p[0]-p0[0], p[1]-p0[1]])
        newnode['stroke'] = out

        # make copy of transform otherwise default one instantiated on definition
        # accumulates translations
        T=Transform(transform)
        T.translate(p0[0], p0[1])
        newnode['frame'] = T.tolist()

        if batch is None and setchange:
            # store node and edge in same change
            batch = graphydb.generateUUID() 
        newnode.save(batch=batch, setchange=setchange)
        newedge.save(batch=batch, setchange=setchange)

        return cls(newnode, scene)

    def keyPressEvent(self, event):

        for item in self.scene().selectedItems():
            if item.flags() & QtWidgets.QGraphicsItem.ItemIsFocusable:
                item.handleKeyPressEvent(event)

    def handleKeyPressEvent(self, event):

        if event.matches(QtGui.QKeySequence.Delete):
            self.scene().removeItem(self)

    # def mouseMoveEvent(self, event):

    #     p0 = event.lastScenePos()
    #     p1 = event.scenePos()

    #     batch = graphydb.generateUUID()
    #     for item in self.scene().selectedItems():
    #         if item.flags() & QtWidgets.QGraphicsItem.ItemIsMovable:
    #             p0i = item.mapFromScene(p0)
    #             p1i = item.mapFromScene(p1)
    #             dpi = p1i-p0i
    #             item.setTransform(QtGui.QTransform.fromTranslate(dpi.x(), dpi.y()), True)
    #             item.save(batch=batch)

    def setinkpath(self, S):

        path=QtGui.QPainterPath()

        b1 = None
        for ii in range(1,len(S)):
            b0 = QtCore.QPointF(S[ii-1][0],S[ii-1][1])
            b1 = QtCore.QPointF(S[ii][0],S[ii][1])

            if len(S[ii])>2:
                width0 = self.width*S[ii-1][2]
                width1 = self.width*S[ii][2]
            else:
                width0 = self.width
                width1 = self.width

            d = b1-b0
            length =  sqrt(d.x()**2+d.y()**2)
            d = d/length
            ## rotate by 90 deg
            p = QtCore.QPointF(-d.y(),d.x())

            p0 = b0-p*width0/2.0
            p1 = b1-p*width1/2.0
            p2 = b1+p*width1/2.0
            p3 = b0+p*width0/2.0
            path.moveTo(p0)
            path.lineTo(p1)
            theta = degrees(atan2(-d.y(),d.x()))
            path.arcTo(b1.x()-width1/2.0,b1.y()-width1/2.0,width1,width1,theta+90,-180)
            path.lineTo(p3)
            path.arcTo(b0.x()-width0/2.0,b0.y()-width0/2.0,width0,width0,theta-90,-180)

            path.closeSubpath()

        path.setFillRule(QtCore.Qt.WindingFill)
        self.setPath(path)
        self.setPen(QtGui.QPen(QtCore.Qt.NoPen))
        self.setBrush(QtGui.QBrush(self.color, QtCore.Qt.SolidPattern))

        # TODO[autosave] remove the following?
        self.coords = S

    def shape(self):
        # XXX performance

        ## make the shape of the item a little thicker - make it much easier to select and move!
        stroker = QtGui.QPainterPathStroker()
        stroker.setWidth(5)
        path = stroker.createStroke(self.path())
        return path

    def setMode(self, mode):

        if mode == PenMode:

            self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, False)
            self.setFlag(QtWidgets.QGraphicsItem.ItemIsMovable, False)
            self.setFlag(QtWidgets.QGraphicsItem.ItemIsFocusable, False)
            self.setSelected(False)

        elif mode == SelectMode:

            self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, True)
            self.setFlag(QtWidgets.QGraphicsItem.ItemIsMovable, True)
            self.setFlag(QtWidgets.QGraphicsItem.ItemIsFocusable, True)
            self.setSelected(False)

        else:

            self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, False)
            self.setFlag(QtWidgets.QGraphicsItem.ItemIsMovable, False)
            self.setFlag(QtWidgets.QGraphicsItem.ItemIsFocusable, False)
            self.setSelected(False)

    def hoverEnterEvent(self, event):
        if self.flags() & QtWidgets.QGraphicsItem.ItemIsMovable and self.isSelected():
            self.originalCursor = self.cursor()
            self.setCursor(QtCore.Qt.SizeAllCursor)

        QtWidgets.QGraphicsPathItem.hoverEnterEvent(self, event)

    def hoverMoveEvent(self, event):
        if self.flags() & QtWidgets.QGraphicsItem.ItemIsMovable \
           and self.isSelected() and not self.hasCursor():
            self.originalCursor = self.cursor()
            self.setCursor(QtCore.Qt.SizeAllCursor)
        QtWidgets.QGraphicsPathItem.hoverMoveEvent(self, event)

    def hoverLeaveEvent(self, event):

        if self.originalCursor is not None:
            self.setCursor(self.originalCursor)
            self.originalCursor = None

        QtWidgets.QGraphicsPathItem.hoverLeaveEvent(self, event)


##----------------------------------------------------------------------
class TextWidthWidget(QtWidgets.QGraphicsPathItem):
##----------------------------------------------------------------------

    def __init__(self, parent):
        super().__init__(parent)

        self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsFocusable, False)
        self.setAcceptHoverEvents(True)

        self.setBrush(QtGui.QBrush(QtCore.Qt.black))
        self.setPen(QtGui.QPen(QtCore.Qt.black))

        self.setShape()

    def contentsChanged(self):

        self.setShape()


    def setShape(self, setwidth=False):

        width = self.parentItem().boundingRect().width()

        if setwidth:
            self.parentItem().maxTextWidth = width

        ## create box handle for changing width
        r = QtCore.QRectF(width-0.5, 0.5, 8, 8)

        path=QtGui.QPainterPath()
        path.addRect(r)

        self.setPath(path)

    def hoverEnterEvent(self, event):
        self.setBrush(QtGui.QBrush(QtCore.Qt.yellow))
        QtWidgets.QGraphicsPathItem.hoverEnterEvent(self, event)

    def hoverLeaveEvent(self, event):
        self.setBrush(QtGui.QBrush(QtCore.Qt.black))
        QtWidgets.QGraphicsPathItem.hoverLeaveEvent(self, event)

    def pointerPressEvent(self, event):
        
        # QtWidgets.QGraphicsPathItem.mousePressEvent(self, event)
        self.parentItem().setSelected(True)
        self.parentItem().setFocus()
        self.setSelected(False)


    def pointerMoveEvent(self, event):
        # QtWidgets.QGraphicsPathItem.mouseMoveEvent(self, event)
        # import pudb; pudb.set_trace()
        p = self.parentItem()
        x0 = p.transform().m31()
        x = max(0, event.scenePos[0])-x0
        self.parentItem().setTextWidth(x)

        ## NB the actual width will depend on the font ... set it from the widget
        self.setShape(setwidth=True)
        self.setSelected(False)

    def pointerReleaseEvent(self, event):
        # QtWidgets.QGraphicsPathItem.mouseReleaseEvent(self, event)
        self.setSelected(False)
        p = self.parentItem()
        p.node['maxwidth'] = p.textWidth()
        p.node.save(setchange=True)




##----------------------------------------------------------------------
class TextItem(QtWidgets.QGraphicsTextItem):
##------------------`----------------------------------------------------

    url = None

    ## these modes should not overlap with pen/text/select modes
    StaticMode = 10
    EditMode = 11
    EditSourceMode = 12

    mode = StaticMode

    statusMessage = QtCore.pyqtSignal(str)
    linkClicked = QtCore.pyqtSignal(str)
    positionChanged = QtCore.pyqtSignal(QtGui.QTextCursor)

    def __init__(self, node, parent=None, scene=None):
        ## Rendered in one of two ways:
        ## 1) in tree: parent = leaf container item, scene = None
        ## 2) in edit dialog: parent = None and scene = edit scene

        if parent is None:
            super().__init__()
            scene.addItem(self)
        else:
            super().__init__(parent)

        self.node = node

        self.DefaultFont = QtGui.QFont(node.get("font_family", CONFIG['text_item_font_family']),
                                       node.get("font_size", CONFIG['text_item_font_size']))

        self.setFont(self.DefaultFont)
        self.setDefaultTextColor(QtGui.QColor(node.get("color", CONFIG['text_item_color'])))

        self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, False)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsMovable, False)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsFocusable, False)
        self.setZValue(node['z'])

        self.setTabChangesFocus(True)

        self.maxTextWidth = node.get('maxwidth', CONFIG['text_item_width'])
        self.widthWidget = TextWidthWidget(self)
        self.widthWidget.hide()

        self.document().contentsChanged.connect(self.widthWidget.contentsChanged)
        self.linkHovered.connect(self.linkHover)

        ## set the default mode
        self.setHtml(self.node['source'])
        self.setStaticMode()

        self.setTransform(Transform(*node['frame']))

        # used to track moves, scales, etc
        self._changed = False

    @classmethod
    def new(cls, stemnode, scene, transform=Transform(),
            z=1, maxwidth=None, color=None, source="",
            batch=None, setchange=True):
        '''
        Convenience method to create a new DB node from QT objects
        '''

        # make copy of transform otherwise default one instantiated on
        # definition accumulates translations
        T=Transform(transform)

        newnode = stemnode.graph.Node('Text')
        newedge = stemnode.graph.Edge(stemnode, 'In', newnode)

        newnode['z'] = z
        if maxwidth is not None:
            newnode['maxwidth'] = maxwidth

        # TODO Add font changing
        if color is not None:
            newnode['color'] = str(color.name())
            newnode['opacity'] = color.alphaF()

        newnode['source'] = source
        newnode['frame'] = T.tolist()
        newnode['z'] = z

        if batch is None and setchange:
            # store node and edge in same change
            batch = graphydb.generateUUID()
        newnode.save(batch=batch, setchange=setchange)
        newedge.save(batch=batch, setchange=setchange)

        return cls(newnode, scene)

    # def save(self, batch=None, setchange=True):
    #     if self.mode == self.EditSourceMode:
    #         ## reset mode so we do have the source and it's been processed by QT
    #         self.setMode(self.StaticMode)

    #     self.node['source'] = self.getSrc()
    #     self.node['frame'] = Transform(self.transform()).tolist()
    #     self.node['z'] = self.zValue()
    #     self.node['maxwidth'] = self.maxTextWidth

    #     self.node.save(batch=batch, setchange=setchange)

    # def changed(self):
    #     return self._changed or \
    #            self.node['source'] != self.getSrc() or \
    #            self.node['maxwidth'] != self.maxTextWidth


    # def getdata(self):

    #     itemdata = self.node

    #     if self.mode == self.EditSourceMode:
    #         ## reset mode so we do have the source and it's been processed by QT
    #         self.setMode(self.StaticMode)

    #     itemdata['source'] = self.getSrc()
    #     itemdata['frame'] = Transform(self.transform()).tolist()
    #     itemdata['z'] = self.zValue()

    #     itemdata['maxwidth'] = self.maxTextWidth

    #     return itemdata

    def getSrc(self):

        ## first look at the existing mode to grab the data

        if self.mode == self.EditSourceMode:
            ## what's visible is the source .. grab verbatim
            src = self.toPlainText().strip()
        else:
            ## what's visible is interpreted .. grab source
            src = self.document().toHtml().strip()

        ## clean up the html.
        ## Here is the problem: QT puts the default font in
        ## the <body> tag but it doesn't read it back from the html, so that if
        ## you change the font in the <body> tag, QT will move that change into
        ## a <span> tag thereby locking it in place in the actual html.
        ## Similarly if you change the default font and it doesn't correspond
        ## to that in the <body> it will get shifted. Ironically the default
        ## text colour is handled outside the html ... these two behaviours
        ## play havock with inheritance down stems so we will strip off the
        ## body tag and ignore it and track the default font and color
        ## ourselves

        soup = BeautifulSoup(src, "html.parser")

        body = soup.find('body')

        if body is None:
            body = soup

        src = body.renderContents().decode('utf-8').strip()

        return src

    def setMode(self, mode):

        ## now set up the mode ...
        ## first process coarse graphics modes
        if mode == PenMode:
            self.setPenMode()
        elif mode == SelectMode:
            self.setSelectMode()
        elif mode == TextMode:
            self.setEditMode()
        elif mode == self.EditSourceMode:
            self.setEditSourceMode()
        elif mode == self.EditMode:
            self.setEditMode()
        else:
            self.setStaticMode()


    def setStaticMode(self):
        '''
        Mode for the text in stem leaves
        - links are clickable
        - no other interaction
        '''

        src = self.getSrc()

        self.mode = self.StaticMode

        ## set source so it's interpreted as html
        self.setHtml(src)

        self.setTextWidth(-1)
        if self.document().idealWidth() > self.maxTextWidth:
            self.setTextWidth(self.maxTextWidth)

        ## remove any textselections
        cursor = self.textCursor()
        cursor.clearSelection()
        self.setTextCursor(cursor)
        self.setFont(self.DefaultFont)

        ## no special cursors
        self.unsetCursor()

        ## width-setting widget hidden
        self.widthWidget.hide()

        self.setTextInteractionFlags(QtCore.Qt.LinksAccessibleByMouse)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, False)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsMovable, False)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsFocusable, False)

    def setSelectMode(self):
        '''
        Mode for viewing text in dialogs ink and select mode
        '''

        self.mode = SelectMode

        self.setHtml(self.getSrc())

        # self.setTextWidth(-1)
        # if self.document().idealWidth() > self.maxTextWidth:
        #     self.setTextWidth(self.maxTextWidth)

        self.unsetCursor()
        self.widthWidget.show()

        cursor = self.textCursor()
        cursor.clearSelection()
        self.setTextCursor(cursor)
        self.setFont(self.DefaultFont)

        self.setTextInteractionFlags(QtCore.Qt.NoTextInteraction)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsFocusable, True)
        self.setSelected(False)

    def setPenMode(self):
        '''
        Mode for viewing text in dialogs ink and select mode
        '''

        self.mode = PenMode

        self.setHtml(self.getSrc())

        self.setTextWidth(-1)
        if self.document().idealWidth() > self.maxTextWidth:
            self.setTextWidth(self.maxTextWidth)

        self.unsetCursor()
        self.widthWidget.hide()

        cursor = self.textCursor()
        cursor.clearSelection()
        self.setTextCursor(cursor)
        self.setFont(self.DefaultFont)

        self.setTextInteractionFlags(QtCore.Qt.NoTextInteraction)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, False)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsMovable, False)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsFocusable, False)
        self.setSelected(False)

    def setEditMode(self):
        '''
        Mode for edting the text as WYSIWYG
        '''
        src = self.getSrc()

        self.mode = self.EditMode

        ## clear any formatting for edit mode
        doc = self.document()
        doc.clear()

        self.setCursor(QtCore.Qt.IBeamCursor)
        self.setFont(self.DefaultFont)

        self.setHtml(src)

        # XXX without adjusting the size the src can be unreasonably long
        self.setTextWidth(self.maxTextWidth)

        cursor = self.textCursor()
        cursor.clearSelection()
        cursor.movePosition(QtGui.QTextCursor.End, QtGui.QTextCursor.MoveAnchor)
        self.setTextCursor(cursor)

        self.setTextInteractionFlags(QtCore.Qt.TextEditorInteraction)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, False)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsMovable, False)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsFocusable, True)

        self.widthWidget.setShape()
        self.widthWidget.show()

    def setEditSourceMode(self):
        '''
        Mode for editing the text as source
        '''
        src = self.getSrc()

        self.mode = self.EditSourceMode

        ## clear any formatting for edit mode
        doc = self.document()
        doc.clear()

        self.setCursor(QtCore.Qt.IBeamCursor)

        #font = QtGui.QFont("Optima")
        font = QtGui.QFont()
        font.setPointSize(9)
        self.setFont(font)

        ## load up the text depending on editMode
        # XXX escape the characters in unicode?
        self.setPlainText(src)

        ## generally want a wide width for the source
        self.setTextWidth(CONFIG['text_item_width'])

        cursor = self.textCursor()
        cursor.clearSelection()
        cursor.movePosition(QtGui.QTextCursor.End, QtGui.QTextCursor.MoveAnchor)
        self.setTextCursor(cursor)

        self.setTextWidth(CONFIG['text_item_width'])
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsMovable, False)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsFocusable, True)

        self.widthWidget.setShape()
        self.widthWidget.show()

    def focusInEvent(self,  event):
        # print ('focus in event')

        QtWidgets.QGraphicsTextItem.focusInEvent(self, event)

        if self.mode in [self.EditMode, self.EditSourceMode]:

            ## clean up other items
            items = self.scene().getItems()

            for item in items:
                if isinstance(item, TextItem) and item != self:
                    item.widthWidget.hide()

                    if item.mode == item.EditSourceMode:
                        item.setMode(item.EditMode)
            self.widthWidget.show()

        scene = self.scene()
        scene.focusedTextItem = self
        self.positionChanged.emit(self.textCursor())

    def deleteOrSave(self):
        src = self.getSrc()
        scene = self.scene()

        if len(self.toPlainText().strip())==0:
            # delete blank text items
            scene.removeItem(self)

        elif src != self.node['source']:
            self.node['source'] = src
            self.node.save(setchange=True)
            scene.refreshStem()

    def focusOutEvent(self,  event):
        QtWidgets.QGraphicsTextItem.focusOutEvent(self, event)
        self.deleteOrSave()

    def mouseDoubleClickEvent(self, event):
        if self.isSelected() and self.mode in [SelectMode]:
            self.setMode(self.EditMode)
            return
        else:
            QtWidgets.QGraphicsTextItem.mouseDoubleClickEvent(self, event)

    def mouseReleaseEvent(self, event):
        QtWidgets.QGraphicsTextItem.mouseReleaseEvent(self, event)

    def mousePressEvent(self, event):
        print('TextItem press event')
        if self.url is not None:
            try:
                ## remove any existing links so we don't end up emiting multiple signals
                self.linkClicked.disconnect(self.scene().linkClicked)
            except TypeError:
                ## if the connection didn't exist it will emit a TypeError exception
                pass
            # XXX should replace with Qt.UniqueConnection but...
            # doesn't seem to work yet (v4.6-1) giving the error:
            # AttributeError: type object 'Qt' has no attribute 'UniqueConnection'
            # self.linkClicked.connect(self.scene().linkClicked, QtCore.Qt.UniqueConnection)
            self.linkClicked.connect(self.scene().linkClicked)
            self.linkClicked.emit(str(self.url))
            return

        if self.mode == self.StaticMode:
            ## normal actions
            parent = self.parentItem()
            parent.mousePressEvent(event)
        else:
            QtWidgets.QGraphicsTextItem.mousePressEvent(self, event)


        self.positionChanged.emit(self.textCursor())

    # def mouseMoveEvent(self, event):

    #     if self.url is not None:
    #         return

    #     if self.mode in [self.EditMode, self.EditSourceMode]:
    #         ## normal actions
    #         QtWidgets.QGraphicsTextItem.mouseMoveEvent(self, event)
    #         return

    #     p0 = event.lastScenePos()
    #     p1 = event.scenePos()

    #     for item in self.scene().selectedItems():
    #         if item.flags() & QtWidgets.QGraphicsItem.ItemIsMovable:
    #             p0i = item.mapFromScene(p0)
    #             p1i = item.mapFromScene(p1)
    #             dpi = p1i-p0i
    #             item.setTransform(QtGui.QTransform.fromTranslate(dpi.x(), dpi.y()), True)
    #             # if hasattr(item, '_changed'):
    #             #     item._changed = True

    def pos(self, *args):
        logging.warn('accessing pos()')
        return QtWidgets.QGraphicsTextItem.pos(self, *args)

    def setPos(self, *args):
        logging.warn('accessing setPos()')
        return QtWidgets.QGraphicsTextItem.setPos(self, *args)


    def keyPressEvent(self, event):

        # if event.key()==QtCore.Qt.Key_Return and event.modifiers()==QtCore.Qt.NoModifier:
        #     ## pass event along so 'OK' is clicked .. (get actual return with shift-return)
        #     QtWidgets.QGraphicsItem.keyPressEvent(self, event)
        #     return

        if self.mode == self.EditMode and event.modifiers() & QtCore.Qt.ControlModifier:

            # XXX combine text format with input dialog actions
            if event.key() == QtCore.Qt.Key_B:
                ## set bold
                cursor = self.textCursor()
                fmt = cursor.charFormat()
                fmt.setFontWeight(QtGui.QFont.Normal \
                                if fmt.fontWeight() > QtGui.QFont.Normal \
                                else QtGui.QFont.Bold)
                cursor.mergeCharFormat(fmt)

            elif event.key() == QtCore.Qt.Key_I:
                ## toggle italic
                cursor = self.textCursor()
                fmt = cursor.charFormat()
                fmt.setFontItalic(not fmt.fontItalic())
                cursor.mergeCharFormat(fmt)

            elif event.key() == QtCore.Qt.Key_U:
                ## toggle underline
                cursor = self.textCursor()
                fmt = cursor.charFormat()
                fmt.setFontUnderline(not fmt.fontUnderline())
                cursor.mergeCharFormat(fmt)

            else:
                QtWidgets.QGraphicsTextItem.keyPressEvent(self, event)


        elif self.mode in [self.EditMode, self.EditSourceMode]:
            QtWidgets.QGraphicsTextItem.keyPressEvent(self, event)
            self.positionChanged.emit(self.textCursor())
        else:
            ## pass event on
            for item in self.scene().selectedItems():
                if item.flags() & QtWidgets.QGraphicsItem.ItemIsFocusable:
                    item.handleKeyPressEvent(event)


    def handleKeyPressEvent(self, event):

        if event.matches(QtGui.QKeySequence.Delete):
            self.scene().removeItem(self)

    def linkHover(self, url):
        '''
        give some feed back when over a link
        '''

        if len(url) > 0:
            self.setCursor(QtCore.Qt.PointingHandCursor)
            self.url = url

            # XXX should this be done at creation time? what if scene not defined?
            self.statusMessage.connect(self.scene().statusMessage)

            self.statusMessage.emit(str(url))

        else:
            self.setCursor(QtCore.Qt.ArrowCursor)
            self.statusMessage.emit("")
            self.url = None

    # def hoverEnterEvent(self, event):
    #     if self.flags() & QtWidgets.QGraphicsItem.ItemIsMovable and self.isSelected():
    #         self.setCursor(QtCore.Qt.SizeAllCursor)

    #     QtWidgets.QGraphicsTextItem.hoverEnterEvent(self, event)

    # def hoverMoveEvent(self, event):
    #     if self.flags() & QtWidgets.QGraphicsItem.ItemIsMovable \
    #        and self.isSelected() and not self.hasCursor():
    #         self.setCursor(QtCore.Qt.SizeAllCursor)
    #     QtWidgets.QGraphicsTextItem.hoverMoveEvent(self, event)

    # def hoverLeaveEvent(self, event):
    #     if self.flags() & QtWidgets.QGraphicsItem.ItemIsMovable \
    #        and self.isSelected():
    #         self.unsetCursor()
    #     QtWidgets.QGraphicsTextItem.hoverLeaveEvent(self, event)

    def paint(self, painter, option, widget):

        ## if editing source put a light gray background to make it easier
        ## to see ... chances are the source view will overlap other items
        if self.mode == self.EditSourceMode:
            painter.setBrush(QtGui.QBrush(QtGui.QColor(240,240,240)))
            painter.setPen(QtGui.QPen(QtGui.QColor(0,0,0,0)))
            painter.drawRect(self.boundingRect())
        QtWidgets.QGraphicsTextItem.paint(self, painter, option, widget)

#----------------------------------------------------------------------
class PixmapItem(QtWidgets.QGraphicsPixmapItem):
#----------------------------------------------------------------------

    # TODO lossless encoding? png/jpg .. preserve details

    def __init__(self, node, parent=None, scene=None):
        ## Rendered in one of two ways:
        ## 1) in tree: parent = leaf container item, scene = None
        ## 2) in edit dialog: parent = None and scene = edit scene

        if parent is None:
            super().__init__()
            scene.addItem(self)
        else:
            super().__init__(parent)

        self.node = node

        self.setAcceptHoverEvents(True)
        self.setZValue(node['z'])
        self.setTransform(Transform(*node['frame']))

        ## set pixmap from stored data
        datanode = node.outN('n.kind="ImageData"').one
        imagedata = nexusgraph.DataToImage(datanode['data'])
        self.setPixmap(QtGui.QPixmap.fromImage(imagedata))

        # used to track moves, scales, etc
        self._changed = False

    @classmethod
    def new(cls, stemnode, scene, transform=Transform(),
            z=1, maxwidth=None, color=None, pixmap=None,
            batch=None, setchange=True):
        '''
        Convenience method to create a new DB node from QT objects
        '''
        newnode = stemnode.graph.Node('Image')
        newedge = stemnode.graph.Edge(stemnode, 'In', newnode)

        # make copy of transform otherwise default one instantiated on
        # definition accumulates translations
        T=Transform(transform)
        newnode['frame'] = T.tolist()
        newnode['z'] = z

        # XXX should check to see it it exists already
        batch = graphydb.generateUUID()
        datnode = newnode.graph.Node("ImageData")
        datnode['data'] = nexusgraph.ImageToData(pixmap.toImage())
        datnode['sha1'] = hashlib.sha1(datnode['data'].encode('utf-8')).hexdigest()
        datnode.save(setchange=True, batch=batch)

        newnode['sha1'] = datnode['sha1']
        newnode.save(setchange=True, batch=batch)

        edge = newnode.graph.Edge(newnode, "With", datnode)
        edge.save(setchange=True, batch=batch)

        return cls(newnode, scene)


    def mouseMoveEvent(self, event):
        p0 = event.lastScenePos()
        p1 = event.scenePos()

        batch = graphydb.generateUUID()
        for item in self.scene().selectedItems():
            if item.flags() & QtWidgets.QGraphicsItem.ItemIsMovable:
                p0i = item.mapFromScene(p0)
                p1i = item.mapFromScene(p1)
                dpi = p1i-p0i
                item.setTransform(QtGui.QTransform.fromTranslate(dpi.x(), dpi.y()), True)
                item.save(batch=batch)
                # if hasattr(item, '_changed'):
                #     item._changed = True

    def setMode(self, mode):

        if mode == PenMode:
            self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, False)
            self.setFlag(QtWidgets.QGraphicsItem.ItemIsMovable, False)
            self.setFlag(QtWidgets.QGraphicsItem.ItemIsFocusable, False)
            self.setSelected(False)

        elif mode == SelectMode:
            self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, True)
            self.setFlag(QtWidgets.QGraphicsItem.ItemIsMovable, True)
            self.setFlag(QtWidgets.QGraphicsItem.ItemIsFocusable, True)
            self.setSelected(False)

        else:
            self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, False)
            self.setFlag(QtWidgets.QGraphicsItem.ItemIsMovable, False)
            self.setFlag(QtWidgets.QGraphicsItem.ItemIsFocusable, False)
            self.setSelected(False)

    def hoverEnterEvent(self, event):
        if self.flags() & QtWidgets.QGraphicsItem.ItemIsMovable and self.isSelected():
            self.setCursor(QtCore.Qt.SizeAllCursor)

        QtWidgets.QGraphicsPixmapItem.hoverEnterEvent(self, event)

    # def hoverMoveEvent(self, event):
    #     if self.flags() & QtWidgets.QGraphicsItem.ItemIsMovable \
    #        and self.isSelected() and not self.hasCursor():
    #         self.setCursor(QtCore.Qt.SizeAllCursor)
    #     QtWidgets.QGraphicsPixmapItem.hoverMoveEvent(self, event)

    def hoverLeaveEvent(self, event):
        self.unsetCursor()
        QtWidgets.QGraphicsPixmapItem.hoverLeaveEvent(self, event)

##----------------------------------------------------------------------
class Leaf(QtWidgets.QGraphicsItem):
    '''
    A static structure that holds the visible data - text images and strokes
    '''
##----------------------------------------------------------------------

    pad = 3
    tagitem = None

    def __init__(self, node, parent):
        super().__init__(parent)

        iconified = node.get('iconified', False)
        if iconified:
            ## just create an icon and store the information
            # TODO Can't identify the QGraphicsScene in the arguments of the QGraphicsItem
            # TODO why have self.leaf in leaf??
            # TODO need to fix for high resolution displays
            self.leaf = QtWidgets.QGraphicsPixmapItem(QtGui.QPixmap(":/images/iconified.svg"), parent=self)

        else:
            for k in node.outN('e.kind = "In"'):
                if k['kind'] == 'Stroke':
                    item = InkItem(k, parent=self)
                elif k['kind'] == 'Text':
                    item = TextItem(k, parent=self)
                    ## this is needed to make alignments work:
                    item.setTextWidth(item.boundingRect().width())
                elif k['kind'] == 'Image':
                    item = PixmapItem(k, parent=self)


        # this is the size of the leaf before adding tags etc
        pad = self.pad

        self.titlerect = self.childrenBoundingRect().adjusted(-pad,-pad,pad,pad)

        self.tags = node.get('tags',set())

        self.setBoundingRect()

    def e(self):
        return self.titlerect.bottomRight()
    def w(self):
        return self.titlerect.bottomLeft()
    def c(self):
        return self.titlerect.center()

    def childrenBoundingRect(self):
        ## override to skip width widget in textitem

        rect = QtCore.QRectF()
        for child in self.childItems():
            rect = rect.united(self.mapRectFromItem(child, child.boundingRect()))

            if not isinstance(child, QtWidgets.QGraphicsTextItem):
                rect = rect.united(self.mapRectFromItem(child, child.childrenBoundingRect()))

        return rect

    def paint(self, painter, option, widget):

        #painter.setPen(QtGui.QPen(QtCore.Qt.red, 0.5))
        #painter.drawRect(self.boundingRect())
        pass

    def setBoundingRect(self):
        ## cache the leafs boundingRect
        self.boundingrect = self.childrenBoundingRect().adjusted(-2, -2, 2, 2)

    def boundingRect(self):
        ## return cached bounding rect
        return self.boundingrect


class OpenCloseWidget(QtWidgets.QGraphicsPathItem):

    def __init__(self, stem):
        super().__init__(QtGui.QPainterPath(), stem)
        self.stem = stem
        self.setCursor(QtCore.Qt.PointingHandCursor)

        self.setPen(QtGui.QPen(QtCore.Qt.black, 1 , QtCore.Qt.SolidLine, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin))
        self.setBrush(QtGui.QBrush(QtGui.QColor(230,230,230)))

        self.open = True
        self.setBoundingRegionGranularity(1)

    def setSymbol(self):

        childnodes = self.stem.node.outN('e.kind="Child"')
        childstems = self.stem.childStems2

        ## if no children .. don't show widget
        if len(childnodes)==0:
            self.hide()
            return
        else:
            self.show()

        ## analyse children visibilities...
        ## set to open if at least one is hidden
        self.open = True
        for child in childnodes:
            self.open = self.open and 'hide' not in child

        #parent = self.stem.parentStem()
        #if parent is None:
        #    rect = self.stem.leaf.boundingRect()
        #    loc = rect.center()
        #else:
        #    # XXX scale
        #    loc = self.stem.tip()+QtCore.QPointF(0, 2.5)

        loc = QtCore.QPointF(0, 0)

        brush = self.brush()
        pen = self.pen()
        if self.stem.depth > 0:
            brush.setColor(QtGui.QColor(self.stem.style('branchcolor')).lighter())
            self.setBrush(brush)
            pen.setColor(QtGui.QColor(self.stem.style('branchcolor')).darker())
            self.setPen(pen)

        openclose = QtGui.QPainterPath()
        openclose.addEllipse(loc, 6, 6)
        openclose.moveTo(loc+QtCore.QPointF(-3, 0))
        openclose.lineTo(loc+QtCore.QPointF(3, 0))

        if not self.open:
            openclose.moveTo(loc+QtCore.QPointF(0, -3))
            openclose.lineTo(loc+QtCore.QPointF(0, 3))

        self.setPath(openclose)

    def toggleVisibilities(self):

        childnodes = self.stem.node.outN('e.kind="Child"')
        dohide = self.scene().mode in ["presentation", "record"]

        batch = graphydb.generateUUID()
        if self.open:
            for child in childnodes:
                if dohide and 'hide' in child.get('tags',set()):
                    continue
                child['hide'] = True
                child.save(batch=batch, setchange=True)
        else:
            for child in childnodes:
                if dohide and 'hide' in child.get('tags',set()):
                    continue
                child.discard('hide')
                child.save(batch=batch, setchange=True)

        self.stem.renew(create=False, position=False)

    def mousePressEvent(self, event):

        self.toggleVisibilities()

        event.accept()

##----------------------------------------------------------------------
class StemItem(QtWidgets.QGraphicsItem):
##----------------------------------------------------------------------

    ## base width of level 1 stems
    rootwidth = 20

    ## tip width of stems
    stemwidth = 5

    _move_threshold = CONFIG['no_move_threshold']

    def __init__(self, node, override={}, parent = None, scene = None):

        # XXX is this still necessary?
        if parent is None:
            super().__init__()
            scene.addItem(self)
        else:
            super().__init__(parent)

        ## store reference to database node
        self.node = node
        node['_qt'] = self

        ## keep refrence to QT child stems
        self.childStems2 = []

        self.index = 0

        if parent is None:
            self.depth = 0
        else:
            self.depth = parent.depth+1

        self.isBeingEdited = False

        ##
        ## widget to show stem as selected
        ##
        self.selectpath = QtWidgets.QGraphicsPathItem(QtGui.QPainterPath(), self)
        self.selectpath.setPen(QtGui.QPen(QtCore.Qt.black, 1, QtCore.Qt.DashLine))
        self.selectpath.hide()

        ##
        ## widget to show stem as being edited
        ##
        self.editedpath = QtWidgets.QGraphicsPathItem(QtGui.QPainterPath(), self)
        self.editedpath.setPen(QtGui.QPen(QtCore.Qt.red, 2, QtCore.Qt.SolidLine))
        self.editedpath.hide()

        ##
        ## widget to show log press feedback
        ##
        self.longPressWidget = QtWidgets.QGraphicsEllipseItem(0,0,6,6,self)
        self.longPressWidget.setPen(QtGui.QPen(QtCore.Qt.black, 1))
        self.longPressWidget.setBrush(QtGui.QBrush(QtCore.Qt.gray))
        self.longPressWidget.hide()
        self.longPressWidget.setZValue(90)

        ##
        ## setup a basic starting point for flags etc
        ##
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable,True)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsMovable,True)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresParentOpacity,True)
        self.setSelected(False)
        self.setCursor(QtCore.Qt.ArrowCursor)

        self.path = QtWidgets.QGraphicsPathItem(QtGui.QPainterPath(),self)

        self.newstemtail = None

        self.openclose = OpenCloseWidget(self)
        self.openclose.setZValue(100)

        self.indexText = None
        self.indexBack = None
        # tag label items
        self.tagitems = None
        self.leaf = None

        self._pressTimer = QtCore.QTimer()
        self._pressTimer.setSingleShot(True)
        self._pressTimer.timeout.connect(self.pressTimerExpire)
        self._pressTimer.setInterval(CONFIG['long_press_time'])


    def renew(self, reload=True, create=True, position=True, children=True, recurse=True):
        '''
        Refresh the visible structure based on the database.
              reload = the node data is taken from database
              create = recreate leaf
            position = position leaf
            children = add/delete children
             recurse = renew down tree with same parameters
        '''

        ##
        ## Reload the data
        ##
        if reload:
            ## reload data ... local changes will be discarded (other than keys stating with _)
            self.node.renew()

        ##
        ## If marked 'hide' remove (check after potential reload)
        ##
        if 'hide' in self.node:
            ## remove this stem
            parent = self.parentStem()
            if parent is not None:
                parent.childStems2.remove(self)
            # NB: unlike InkScene, removeItem here will not remove db item
            self.scene().removeItem(self)
            return

        p = self.base()
        T = scaleRotateMove(float(self.node.get('scale', 1.0)), self.node.get('angle', 0.0), p.x(), p.y())
        self.setTransform(T)

        self.setOpacity(self.style('opacity'))

        tmpposition = False
        if create or self.leaf is None:
            ## depth goes off the QT structure with parents child
            self.depth = len(self.allParentStems())
            self.setZValue(-self.depth)

            #self.prepareGeometryChange()
            self.createLeaf()

            ## Use temporary variable so original value is recursed
            tmpposition = True


        if position or tmpposition:
            self.positionLeaf()

        ##
        ## manage the children
        ##
        if children:
            ## fetch from database
            childNodes = self.node.outN('e.kind = "Child"')

            ## exorcise ghost children
            for qc in list(self.childStems2):
                if qc.node['uid'] not in childNodes:

                    self.scene().removeItem(qc)
                    self.childStems2.remove(qc)

            ## welcome new children
            currentchilduids = [ q.node['uid'] for q in self.childStems2]
            for n in childNodes:
                if n['uid'] not in currentchilduids:
                    child = StemItem(node=n, scene=self.scene(), parent=self)
                    self.childStems2.append(child)

        ##
        ## Recursively attend to decendants
        ##
        if recurse:
            ## renew children
            for child in list(self.childStems2):
                child.renew(reload=reload, create=create, position=position, children=children, recurse=recurse)

        self.reindexChildren()

        if create or children:
            self.openclose.setSymbol()

    def createLeaf(self):

        # XXX check to see what needs to be changed instead of obliterating

        ## first clear any old leaf items
        if self.leaf is not None:
            self.scene().removeItem(self.leaf)

        self.leaf = Leaf(self.node, parent=self)
        self.leaf.setZValue(10)

        # XXX removing this means central node in wrong place
        self.positionLeaf()

        ##
        ## create stem index text to show order
        ##
        if self.depth==0:
            ## no stem index on root
            self.indexText = None
            self.indexBack = None
        else:
            rect = QtCore.QRectF(0, -.5, 6, 6)
            path = QtGui.QPainterPath()
            path.addRoundedRect(rect, 1, 1)

            indexBack = QtWidgets.QGraphicsPathItem(path, self)
            indexBack.setBrush(QtGui.QBrush(QtGui.QColor(self.style('branchcolor')).lighter()))
            indexBack.setPen(QtGui.QPen(QtCore.Qt.gray, 0.1 , QtCore.Qt.SolidLine, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin))
            indexBack.setZValue(11)

            self.indexText = QtWidgets.QGraphicsSimpleTextItem(str(self.index), indexBack)

            ci = indexBack.boundingRect().center()

            self.indexText.setScale(.3)
            ct = self.indexText.boundingRect().center()

            pos = QtCore.QPointF(2, 0)
            self.indexText.setPos(pos.x(), pos.y())
            self.indexBack = indexBack

        ##
        ## Draw leaf surrounds
        ##
        if self.depth == 0:
            ##
            ## Central topic
            ##
            penwidth = 2
            pad = 10

            tr = self.leaf.mapToParent(self.leaf.boundingRect()).boundingRect().adjusted(-pad,-pad,pad,pad)
            path = QtGui.QPainterPath()
            path.addRoundedRect(tr,6,6)
            self.path.setPen(QtGui.QPen(QtCore.Qt.black, penwidth , QtCore.Qt.SolidLine, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin))
            self.path.setBrush(QtGui.QBrush(QtGui.QColor(200,200,200)))
            self.path.setPath(path)

        else:
            ##
            ## draw standard branch, actually, use redrawTail()
            ##
            self.path.setPen(QtGui.QPen(QtCore.Qt.NoPen))
            self.path.setBrush(QtGui.QBrush(QtGui.QColor(self.style('branchcolor'))))
            self.redrawTail()

        ##
        ## Set tag labels
        ##
        if self.tagitems is not None:
            self.scene().removeItem(self.tagitems)
        self.tagitems = QtWidgets.QGraphicsItemGroup(self)
        tags = self.getTags()
        offset = 0
        pad = 3
        for tag in tags:
            tagitem=QtWidgets.QGraphicsSimpleTextItem(tag, self.tagitems)
            tagitem.setTransform(QtGui.QTransform.fromTranslate(offset, 0), True)
            rect = tagitem.boundingRect().adjusted(-1, -1, 1, 1)
            path = QtGui.QPainterPath()
            path.addRoundedRect(rect, 1, 1)
            back = QtWidgets.QGraphicsPathItem(path, self.tagitems)
            back.setTransform(QtGui.QTransform.fromTranslate(offset, 0), True)
            back.setPen(QtGui.QPen(QtCore.Qt.gray, 0 , QtCore.Qt.SolidLine, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin))
            back.setBrush(QtGui.QBrush(QtGui.QColor('#ffffbb')))
            back.setZValue(-10)

            offset += rect.width()+pad

        T = QtGui.QTransform.fromScale(.4, .4)
        if self.depth > 0:
            if self.direction() > 0:
                T = T.translate(0,(1+self.stemwidth)/0.4)
                self.tagitems.setTransform(T)
            else:
                w = self.tagitems.childrenBoundingRect().width()
                T = T.translate(-w,(1+self.stemwidth)/0.4)
                self.tagitems.setTransform(T)
        else:
            # TODO position the tags on central node somewhere visible
            self.tagitems.hide()

    def positionLeaf(self):
        ##
        ## Position leaf
        ##
        if self.depth == 0:
            leafrect = self.leaf.boundingRect()
            p = leafrect.center()
            lT = self.leaf.transform()
            self.leaf.setTransform(QtGui.QTransform.fromTranslate(-lT.dx()-p.x(), -lT.dy()-p.y()), True)
            #self.leaf.setTransform(QtGui.QTransform.fromTranslate(-p.x(), -p.y()), True)
        else:
            if self.direction() > 0:
                ltip = self.leaf.mapToParent(self.leaf.e())
            else:
                ltip = self.leaf.mapToParent(self.leaf.w())

            tip = self.tip()
            d = tip-ltip
            self.leaf.setTransform(QtGui.QTransform.fromTranslate(d.x(), d.y()), True)

        ##
        ## Set rect to show stem is selected
        ##
        tr = self.leaf.mapToParent(self.leaf.boundingRect()).boundingRect()
        sp = QtGui.QPainterPath()
        if self.depth==0:
            tr = tr.adjusted(-5, -5, 5, 5)
        sp.addRect(tr)
        self.selectpath.setPath(sp)
        self.selectpath.setZValue(20)

        ##
        ## Set rect to show stem is being edited
        ##
        sp = QtGui.QPainterPath()
        tr = tr.adjusted(-5, -5, 5, 5)
        sp.addRect(tr)
        self.editedpath.setPath(sp)
        self.editedpath.setZValue(20)

        ##
        ## Position open-close symbol
        ##
        if self.depth==0:
            p = self.boundingRect().bottomRight()-QtCore.QPointF(0,0)
        else:
            # XXX why the correction of -2?
            p = self.tip()+QtCore.QPointF(0,self.stemwidth-2)/2.0
        self.openclose.setTransform(QtGui.QTransform.fromTranslate(p.x(),p.y()))


        #self.openclose.setSymbol()
        self.redrawTail()

    def redrawTail(self):
        if self.depth>0:
            Proot = self.mapFromParent(self.parentStem().tip())
            R=(self.rootwidth if self.depth==1 else self.stemwidth)/float(self.node.get('scale', 1.0))
            path = self.createTailPath(Proot, QtCore.QPointF(0, 0), self.tip(), self.direction(), R)
            self.path.setPath(path)

    def __getattr__(self, name):
        if name[0]=='c' and isinstance( int(name[1:]), int ) and int(name[1:]) >=0:
            return self.child(int(name[1:]))
        else:
            raise AttributeError

    def child(self, idx):
        for stem in self.childStems2:
            if stem.index == idx:
                return stem
        else:
            raise Exception("Can't find child stem with that index")

    def reindexChildren(self):
        self.childStems2.sort(key=lambda x: x.posangle())
        for i,child in enumerate(self.childStems2):
            child.index = i
            child.indexText.setText(str(i))

    def style(self, key):

        if key in self.node:
            value = self.node[key]

        elif self.parentStem() is not None:
            value = self.parentStem().style(key)

        else:
            defaults = {
                'branchcolor':'#999999',
                'scale':0.6,
                'opacity':1,
            }
            value = defaults[key]

        return value


    def createTailPath(self, Proot, Pbase, Ptip, direction, R):
        '''
        return a path object for the stem's tail

                    (0,0)
                Pbase o----o Ptip
                     /
                o---o Proot

        Ptip and Proot have to be in the items coordinate system
        Pbase is normally (0,0)
        '''

        ## H is a relative vector
        H=QtCore.QPointF(0, self.stemwidth)

        L = sqrt((Pbase.x()-Proot.x())**2+(Pbase.y()-Proot.y())**2)
        control = QtCore.QPointF(-0.4*L*direction, 0)

        theta = -atan2(Proot.x()-control.x()-Pbase.x(), Proot.y()-control.y()-Pbase.y())

        dpt = -QtCore.QPointF(R*cos(theta), R*sin(theta))
        dpb = QtCore.QPointF(R*cos(theta), R*sin(theta))

        ppt = Proot+direction*dpt+H/2.0
        ppb = Proot+direction*dpb+H/2.0

        ## create path
        path = QtGui.QPainterPath()
        path.moveTo(ppb)
        path.quadTo(Pbase+control+H, Pbase+H)
        path.lineTo(Ptip+H+QtCore.QPointF(-direction*self.stemwidth, 0))
        path.lineTo(Ptip)
        path.lineTo(Pbase)
        path.quadTo(Pbase+control, ppt)
        if direction >0:
            start = 180-180*theta/pi
            sweep = 180
        else:
            start = -180*theta/pi
            sweep = -180
        path.arcTo(Proot.x()-R, Proot.y()-R+self.stemwidth/2.0, 2*R, 2*R, start, sweep)
        path.closeSubpath()

        return path

    def mousePressEvent(self, event):
        #logging.debug("StemPressEvent")

        # TODO refactor as _m_press_timer
        self._pressTimer.start()

        self._m_press_pos = event.scenePos()
        self._m_state = MPRESS
        # logging.debug('[*] Press event ->[1]')

        if (event.button() == QtCore.Qt.LeftButton and event.modifiers() == QtCore.Qt.ControlModifier) or \
           (event.button() in [QtCore.Qt.RightButton, QtCore.Qt.MiddleButton]):
            self._m_state = MADD
            # logging.debug('[1] Modifiers ->[5]')
            self.drawBud(event.pos())

        else:

            if event.button() == QtCore.Qt.LeftButton:
                if event.modifiers() == QtCore.Qt.ShiftModifier:
                    self.setSelected(not self.isSelected())

                elif event.modifiers() == QtCore.Qt.NoModifier and not self.isSelected():
                    self.scene().clearSelection()
                    self.setSelected(True)

            for stem in self.scene().selectedItems():
                ## record the inition press point to see overall change in moves (more stable)
                parent = stem.parentStem()
                if parent is not None:
                    stem._scenebase = parent.mapToScene(stem.base())
                else:
                    stem._scenebase = stem.base()
                stem._scenetip = stem.mapToScene(stem.tip())

        # if self.scene().presentation:
        #     self.presstime = time.time()
        #     #event.ignore()
        #     return

        event.accept()

    def mouseMoveEvent(self, event):

        p1 = event.scenePos()
        p0 = self._m_press_pos

        # Use item pos as touch gesture shouldn't depend on zoom
        p0i = self.mapFromScene(p0)
        p1i = self.mapFromScene(p1)
        d = sqrt(abs((p1i.x()-p0i.x())**2+(p1i.y()-p0i.y())**2))

        # if self.scene().presentation:
        #     #self.presstime = 0
        #     event.ignore()
        #     return

        if self._m_state == MPRESS:
            if d>self._move_threshold:
                # Moved enough to register this as a move
                self._m_state = MMOVE
                self._pressTimer.stop()
                # logging.debug('[1] Move start ->[2]')

        elif self._m_state == MMOVE:
            # Move selected plus this one
            # logging.debug('[2] Moving')
            # XXX select self if not selected
            self.moveSelected(p1-p0)

        elif self._m_state == MLONG:
            if d>self._move_threshold:
                self._m_state = MADD
                # logging.debug('[3] Moved ->[5]')
            else:
                # Nothing to be done but wait for release, sigh.
                pass
                # logging.debug('[3] Waiting')

        if self._m_state == MADD:
            # logging.debug('[5] show bud')
            # Indicate where the new stem will be
            self.drawBud(event.pos())

        event.accept()

    def mouseReleaseEvent(self, event):
        #logging.debug("StemReleaseEvent")

        p1 = event.scenePos()
        p0 = self._m_press_pos
        self._pressTimer.stop()

        # Use item pos as touch gesture shouldn't depend on zoom
        p0i = self.mapFromScene(p0)
        p1i = self.mapFromScene(p1)
        d = sqrt(abs((p1i.x()-p0i.x())**2+(p1i.y()-p0i.y())**2))

        if self._m_state == MMOVE or \
            (self._m_state == MPRESS and d>self._move_threshold):
            # logging.debug('[1]/[2] End - Move')
            # Move all selected stems including this one

            ## collect all the stems that may have changed
            stems = []
            for stem in self.scene().selectedItems():
                stems.append(stem)
                #stems.extend(stem.allChildStems())

            ## direction or position may have changed
            batch = graphydb.generateUUID()
            for stem in stems:
                stem.node.save(batch=batch, setchange=True)

                if stem.parentStem() is not None:
                    stem.parentStem().reindexChildren()

                ## N.B. may flip at last instance?
                # XXX check for last intance flips
                stem.renew(reload=False, children=False, create=False, recurse=False)

        elif self._m_state == MADD or \
            (self._m_state == MLONG and d>self._move_threshold):
            # logging.debug('[5] End - Edit new stem')

            self.longPressWidget.hide()
            self.newStem(p=event.pos())

            # clear out stemtail
            if self.newstemtail is not None:
                self.scene().removeItem(self.newstemtail)
                self.newstemtail = None

        elif self._m_state == MLONG: # or \
            # logging.debug('[1]/[3] Long Press End - Menu')
            # Launch context menu
            self.longPressWidget.hide()
            self.contextMenu(event.screenPos())

        elif self._m_state == MDOUBLE:
            # logging.debug('[2] End - Edit stem')
            # edit current stem
            self.longPressWidget.hide()
            self.editStem()

        else:
            # logging.debug('[*] End - Change Selection')
            pass


        # if self.scene().presentation:
        #     t=time.time()
        #     if self.presstime !=0 and (t-self.presstime) > 1:
        #         popup = QtWidgets.QMenu()
        #         addnote = popup.addAction('Add note')
        #         action = popup.exec_(event.screenPos())
        #         if action  == addnote:
        #             x,y = self.suggestChildPosition()
        #             self.newStem(p=QtCore.QPointF(x,y), fullscreen=True, iconified=True)
        #     event.ignore()
        #     return

        # hide it here just in case it ends up hanging around
        self.longPressWidget.hide()
        event.accept()

    def pressTimerExpire(self):
        if self._m_state == MPRESS:
            self._m_state = MLONG
            t = self.tip()
            W = 20.0
            color = QtGui.QColor(self.style('branchcolor'))
            self.longPressWidget.setPen(QtGui.QPen(color,1))
            color.setAlphaF(0.5)
            self.longPressWidget.setBrush(QtGui.QBrush(color))
            self.longPressWidget.setRect(t.x()-W/2,t.y()-W/2+self.stemwidth/2.0-1,W,W)
            self.longPressWidget.show()
            # logging.debug('[1] Long press registered ->[3]')
        else:
            # logging.debug('Timer triggered not in MPRESS')
            pass


    def contextMenu(self, global_pos=None):
        cmenu = QtWidgets.QMenu()
        edit_action=cmenu.addAction("Edit")
        cmenu.addSeparator()
        copy_action=cmenu.addAction("Copy")
        cut_action=cmenu.addAction("Cut")
        paste_action=cmenu.addAction("Paste")
        copylink_action=cmenu.addAction("Copy Link")
        cmenu.addSeparator()
        delete_action=cmenu.addAction("Delete")
        cmenu.addSeparator()
        #presentation_action=cmenu.addAction("Presentation")

        action = cmenu.exec_(global_pos)

        if action==edit_action:
            self.editStem()
        elif action==delete_action:
            self.scene().delete(stem=self)
        elif action==cut_action:
            self.scene().cut(stem=self)
        elif action==copy_action:
            self.scene().copy(stem=self)
        elif action==paste_action:
            self.scene().paste(stem=self)
        elif action==copylink_action:
            self.scene().copyStemLink(stem=self)
        #elif action==presentation_action:
        #    print('presentation')


    def mouseDoubleClickEvent(self, event):
        # logging.debug('[{}] Double Click ->[4]'.format(self._m_state))
        self._m_state = MDOUBLE
        # double click action handled in mouseReleaseEvent
        event.accept()

    def drawBud(self, p):

        if self.newstemtail is None:
            self.newstemtail = QtWidgets.QGraphicsPathItem(QtGui.QPainterPath(),self)
            self.newstemtail.setPen(QtGui.QPen(QtCore.Qt.NoPen))
            if self.depth==0:
                color=QtGui.QColor(hsv_to_rgb(random.random(), 0.6, 0.85))
            else:
                color = QtGui.QColor(self.style('branchcolor'))
            color.setAlphaF(0.3)
            self.newstemtail.setBrush(QtGui.QBrush(color))
            self.newstemtail.setZValue(-1)

            self.scene().clearSelection()
            self.setSelected(True)

        ## make direction the same as parent
        direction = sign((p-self.tip()).x())
        R=(self.rootwidth if self.depth==0 else self.stemwidth)
        path = self.createTailPath(self.tip(), p, p+direction*QtCore.QPointF(30, 0), direction, R)
        self.newstemtail.setPath(path)

    def moveSelected(self, scenedp):

        allselected = self.scene().selectedItems()
        ## remove selected stems that have a parent selected
        children = []
        for stem in allselected:
            children.extend(stem.allChildStems())
        selected = []
        for stem in allselected:
            if stem not in children:
                selected.append(stem)

        #X# scenedp = event.scenePos()-self._scenepointerdown

        ## move the selected stems
        for stem in selected:
            parent = stem.parentStem()
            if  parent is not None:
                ## branch
                ptip = parent.mapToScene(parent.tip())
            else:
                ## root
                ptip = QtCore.QPointF(0,0)

            newbase = stem._scenebase + scenedp

            ## half-way point to determine if flip should occur
            half = (stem._scenebase+stem._scenetip)/2.0 + scenedp

            stem._flipped = False
            if stem.depth > 0 and ((stem.direction() > 0 and half.x() < ptip.x()) \
                or (stem.direction() < 0 and half.x() > ptip.x())):
                ## need to flip stem
                flip = -1

                ## new position with tip and base swapped
                newbase = stem._scenetip + scenedp

                ## flip base and tip for start of move
                stem._scenebase, stem._scenetip = stem._scenetip, stem._scenebase

                stem._flipped = True
            else:
                ## keep step orientation the same
                flip = 1

            stem.node['flip'] *= flip

            ## store position relative to parent's tip
            if parent is not None:
                p = parent.mapFromScene(newbase)-parent.mapFromScene(ptip)
            else:
                p = newbase-ptip

            ## store as if in left to right direction
            if stem.direction() < 0:
                ## correct direction for storing
                stem.node['pos'] = [-p.x(), p.y()]
            else:
                stem.node['pos'] = [p.x(), p.y()]

        for stem in selected:
            ## update but don't save or reload yet! (done in mouseReleaseEvent)
            if stem._flipped:
                stem.renew(reload=False, create=False, children=False)
            else:
                ## Just move with no other updates for speed
                newbase = stem.base()
                T = scaleRotateMove(float(stem.node.get('scale', 1.0)), stem.node.get('angle', 0.0), newbase.x(), newbase.y())
                stem.setTransform(T)
                stem.redrawTail()


    def direction(self):
        if self.depth==0:
            return 1
        else:
            return self.parentStem().direction()*self.node['flip']

    def base(self):
        p = self.node['pos'] ## Don't modify p in place!
        if self.depth==0:
            return QtCore.QPointF(p[0],p[1])
        else:
            if self.direction()<0:
                return self.parentStem().tip()+QtCore.QPointF(-p[0],p[1])
            else:
                return self.parentStem().tip()+QtCore.QPointF(p[0],p[1])

    def tip(self):
        '''
        return location of tip of stem in local item co-ordinates
        '''
        if self.depth == 0:
            tx,ty = 0.0, 0.0
        else:
            leaf = self.leaf
            if self.direction() < 0:
                p = leaf.w() - leaf.e()
                tx,ty = -p.x(), p.y()
            else:
                p = leaf.e() - leaf.w()
                tx,ty = p.x(), p.y()

        return QtCore.QPointF(self.direction()*tx,ty)

    def getTags(self):
        '''
        return attached tags
        '''
        # tags = []
        # for n in self.node.outN('e.kind = "Tagged"'):
        #     tags.append(n['text'])

        return self.node.get('tags', set())

    def titles(self):
        '''
        return title strings
        '''
        out = []
        for item in self.leaf.childItems():
            if isinstance(item, TextItem):
                out.append(str(item.toPlainText()))

        return out

    def suggestChildPosition(self):


        # XXX to be used in long press and paste ...  not working

        tip = self.tip()

        X = tip.x() +self.direction()*30

        ys = [c.mapToParent(c.parentStem().tip()).y() for c in self.childStems2]

        if len(ys)>0:

            Y = max(ys)+20
        else:
            Y = -20


        return X,Y


    def addChildStem(self, data, batch=None):

        newnode = self.node.graph.Node('Stem')
        newedge = self.node.graph.Edge(self.node, 'Child', newnode)

        settings = QtCore.QSettings("Ectropy", "Nexus")
        if self.depth == 0:
            scale = float(settings.value('new/stemscale'))
        else:
            scale = self.transform().m11()

        ## Place the new stem below the children following the rough pattern
        tip = self.tip()
        points = [-c.mapFromParent(c.parentStem().tip()) for c in self.childStems2]
        if len(points)>1:
            ## Get the rough position of the children
            maxy = points[0].y()
            miny = points[0].y()
            meanx=points[0].x()
            for p in points[1:]:
                maxy = max(maxy, p.y())
                miny = min(miny, p.y())
                meanx += p.x()
            meanx = meanx/float(len(points))

            x = meanx
            y = maxy+(maxy-miny)/float(len(points)-1)

        elif len(points)==1:
            x = points[0].x()
            y = points[0].y()+50

        else:
            x = self.direction()*30
            y = -50

        if scale != 1:
            newnode['scale'] = scale
        newnode['pos'] = [x*scale, y*scale]
        newnode['flip'] = sign(x)*self.direction()

        newnode.update(data)

        if batch is None:
            batch = graphydb.generateUUID()
        newnode.save(batch=batch, setchange=True)
        newedge.save(batch=batch, setchange=True)

        stem = StemItem(newnode, parent=self, scene=self.scene())

        leaf = Leaf(stem.node, None)
        if stem.direction()<0:
            p = leaf.w()-leaf.e()
        else:
            p = leaf.e()-leaf.w()

        self.childStems2.append(stem)
        stem.renew(reload=False, create=False, position=False)
        stem.parentStem().reindexChildren()

        self.openclose.setSymbol()

        return stem

        # XXX .. images?

    def newStem(self, p=QtCore.QPointF(), fullscreen=False, iconified=False):

        ## add new db items but don't save then yet in case user cancels
        G = self.node.graph
        newnode = G.Node('Stem')
        newedge = G.Edge(self.node, 'Child', newnode)

        settings = QtCore.QSettings("Ectropy", "Nexus")
        if self.depth == 0:
            scale = float(settings.value('new/stemscale'))
            ## Set a random color
            newnode['branchcolor'] = self.newstemtail.brush().color().name()
        else:
            scale = self.transform().m11()

        dp=p-self.tip()
        newnode['scale'] = scale
        newnode['flip'] = sign(dp.x())*self.direction()
        if iconified:
            newnode['iconified']=True
        if self.direction()*newnode['flip']<0:
            newnode['pos'] = [-dp.x(), dp.y()]
        else:
            newnode['pos'] = [dp.x(), dp.y()]

        batch = graphydb.generateUUID()
        newnode.save(batch=batch, setchange=True)
        newedge.save(batch=batch, setchange=True)

        newstem = StemItem(newnode, parent=self)
        self.childStems2.append(newstem)
        # remember the cursor
        #cur = self.cursor()
        # d = InputDialog(newnode, newedge, stem=self,
        #                 state = self.scene().dialogstate,
        #                 fullscreen=fullscreen,
        #                 )

        self.scene().showEditDialog.emit(newstem)
        # d.setDialog(newnode, newedge, self)
        # d.show()
        # d.exec_()

        #self.renew(reload=False)

        #self.setCursor(cur)
        ## store the geometry of input window
        # self.scene().dialogstate['geometry'] = d.inputgeometry

        ## remember new-stem dialog state
        # self.scene().dialogstate['mode'] = d.scene.mode

        self.scene().removeItem(self.newstemtail)
        self.newstemtail = None
        self.openclose.setSymbol()

    def editStem(self):
        '''
        Bring up a dialog to edit the stem and then reimplement
        '''

        # TODO clean up code
        # edge = self.node.inE('e.kind="Child"').one
        # fullscreen = True if self.scene().presentation else False
        # cur = self.cursor()
        # d = InputDialog(self.node, edge, stem=self,
        #                 state = self.scene().dialogstate,
        #                 fullscreen = fullscreen)
        self.scene().showEditDialog.emit(self)
        #d.setDialog(self.node, edge, self)
        #d.show()
        # d.exec_()

        # if self.node.exists:
            # stem may be deleted after edit (i.e. all items removed)
            # so this item may be about to be garbage collected
            # only renew if it exists
            # self.renew(children=False, reload=False)

            ## store the geometry of input window
            #self.scene().dialogstate['geometry'] = d.inputgeometry
            ## remember new-stem dialog state
            #self.scene().dialogstate['mode'] = d.scene.mode

            #self.view.viewport().setCursor(cur)
            # self.setCursor(cur)


    def parentStem(self):
        '''
        return parent stem ... here for completeness
        '''
        ## NB parentItem of stem is either None or another stem
        return self.parentItem()

    def allParentStems(self):
        '''
        return list of all ancestors
        '''
        parents= []
        parent = self.parentStem()
        while parent is not None:
            parents.append(parent)
            parent = parent.parentStem()
        return parents


    def posangle(self):
        x, y = self.node['pos']
        x *= self.direction()
        ## y measured down in QT
        y *= -1
        parentdirection = self.direction()*self.node['flip']
        if self.depth==1:
            theta=fmod(5*pi/2-atan2(y,x), 2*pi)
        elif parentdirection > 0:
            theta=fmod(pi-atan2(y,x), 2*pi)
        else:
            theta=fmod(2*pi+atan2(y,x), 2*pi)
        return theta

    # def childStems(self):
    #     '''
    #     return list of direct child stems
    #     '''
    #     childstems = []
    #     for item in self.childItems():
    #         if isinstance(item, StemItem):
    #             childstems.append(item)
    #
    #     childstems.sort(key=functools.cmp_to_key(self.sortByPos))
    #
    #     return childstems

    def allChildStems(self, nottaggedhide=False):
        '''
        return list of all decendants
        '''
        allchildstems = []

        for child in self.childStems2:
            if nottaggedhide and 'hide' in child.getTags():
                continue
            allchildstems.append(child)
            allchildstems = allchildstems + child.allChildStems(nottaggedhide)

        return allchildstems

    def paint(self, painter, option, widget):

        if self.isSelected():
            self.selectpath.show()
        else:
            self.selectpath.hide()

        if self.isBeingEdited:
            self.editedpath.show()
        else:
            self.editedpath.hide()


    def boundingRect(self):

        if hasattr(self, 'selectpath'):
            return self.selectpath.boundingRect().adjusted(-2,-2,2,2)
        else:
            return QtCore.QRectF()

    def shape(self):

        return self.selectpath.shape()

 
