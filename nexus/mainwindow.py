##
## Copyright 2010-2019 Alexei Gilchrist
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


import xml.etree.ElementTree as et
import sys,  zipfile,  io,  os, time, random, hashlib, json, shutil
from pathlib import Path
from PyQt5 import QtCore, QtGui, QtOpenGL, QtSvg, QtWidgets, QtPrintSupport
from PyQt5.QtMultimedia import QAudioRecorder, QAudioEncoderSettings, QMultimedia
import gzip
from functools import reduce
import webbrowser, tempfile

import webbrowser, urllib.parse, logging
from . import graphics, resources, interpreter, graphydb, nexusgraph, config
from math import sqrt, log, sinh, cosh, tanh, atan2, fmod, pi, cos, sin
import re, subprocess
import apsw



CONFIG = config.get_config()

# used to preserve links in svg generation
# choose narrow symbols
#alphabet = '0123456789abcdefghijklmnopqrtstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
alphabet = '1ijltI|.,[](){};:!%^`'

## minified script for navigation
SVGCTRL=r'''function svgcontrols(){function t(){l.width.baseVal.value=c.getBoundingClientRect().width,l.height.baseVal.value=c.getBoundingClientRect().height}function e(t,e){var n="matrix("+e.a+","+e.b+","+e.c+","+e.d+","+e.e+","+e.f+")";t.setAttributeNS(null,"transform",n)}function n(){var t=c.getBoundingClientRect(),e=a.getBoundingClientRect(),n=(e.left+e.right)/2,l=(e.top+e.bottom)/2,r=(t.left+t.right)/2-n,u=(t.top+t.bottom)/2-l;o(.9*Math.min(t.height/e.height,t.width/e.width),n,l),i(r,u)}function i(t,n){var i=a.getCTM().a,o=c.getBoundingClientRect(),l=a.getBoundingClientRect(),r=20;t>0&&l.left+t/i>o.right-r&&(t=o.right-r-l.left),0>t&&l.right+t/i<o.left+r&&(t=o.left+r-l.right),n>0&&l.top+n/i>o.bottom-r&&(n=o.bottom-r-l.top),0>n&&l.bottom+n/i<o.top+r&&(n=o.top+r-l.bottom);var u=c.createSVGMatrix().translate(t/i,n/i);e(a,a.getCTM().multiply(u))}function o(t,n,i){var o=c.createSVGPoint(),l=c.getBoundingClientRect();o.x=n-l.left,o.y=i-l.top,o=o.matrixTransform(a.getCTM().inverse());var r=a.getCTM();r.a*t>=Y&&r.a*t<=E?newscale=t:newscale=1;var u=c.createSVGMatrix().translate(o.x,o.y).scale(newscale).translate(-o.x,-o.y);e(a,r.multiply(u))}var c=document.getElementById("nexusmap"),a=document.getElementById("viewcontrol"),l=document.createElementNS("http://www.w3.org/2000/svg","rect");l.setAttribute("id","eventcatcher"),l.setAttribute("x","0"),l.setAttribute("y","0"),l.setAttribute("width","1"),l.setAttribute("height","1"),l.setAttribute("style","fill:none;"),l.setAttribute("pointer-events","none"),c.appendChild(l);var r,u,s,h,g,d,v,f,m,p,w,b,M,C,E=100,Y=.5,x=.02,y="",X=1;c.addEventListener("wheel",function(e){if(t(),e.preventDefault(),e.ctrlKey){var n=Math.exp(-e.deltaY*x);o(n,e.clientX,e.clientY)}else i(-e.deltaX,-e.deltaY)},!1),c.addEventListener("mousedown",function(e){t(),""==y&&(y="dragging",r=e.clientX,u=e.clientY)},!1),c.addEventListener("mousemove",function(t){"dragging"==y&&(g=t.clientX,d=t.clientY,i(g-r,d-u),r=g,u=d)},!1),c.addEventListener("mouseup",function(t){"dragging"==y&&(y="")},!1),window.addEventListener("mouseup",function(t){y=""}),c.addEventListener("touchstart",function(e){y="",t(),1==e.touches.length?(y="panning",r=e.touches[0].clientX,u=e.touches[0].clientY):2==e.touches.length&&(y="zooming",r=e.touches[0].clientX,u=e.touches[0].clientY,s=e.touches[1].clientX,h=e.touches[1].clientY,X=a.getCTM().a,w=(r+s)/2,b=(u+h)/2,m=Math.sqrt(Math.pow(s-r,2)+Math.pow(h-u,2)),X=1)},!1),c.addEventListener("touchmove",function(t){if(t.preventDefault(),"panning"==y)g=t.touches[0].clientX,d=t.touches[0].clientY,i(g-r,d-u),r=g,u=d;else if("zooming"==y){g=t.touches[0].clientX,d=t.touches[0].clientY,v=t.touches[1].clientX,f=t.touches[1].clientY,M=(g+v)/2,C=(d+f)/2,p=Math.sqrt(Math.pow(v-g,2)+Math.pow(f-d,2));var e=p/m;o(e/X,M,C),r=g,u=d,s=v,h=f,X=e}},!1),c.addEventListener("touchleave",function(t){y="",X=1},!1),t(),n()}svgcontrols();
'''
## The setup for this map
CONTROL=r''' '''
## Combine
NAVJS="<![CDATA[\n{}{}]]>".format(SVGCTRL,CONTROL)

## function from http://infix.se/2007/02/06/gentlemen-indent-your-xml
def indentxml(elem, level=0):
    i = "\n" + level*"  "
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "  "
        for e in elem:
            indentxml(e, level+1)
            if not e.tail or not e.tail.strip():
                e.tail = i + "  "
        if not e.tail or not e.tail.strip():
            e.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i

def convert_xml_to_graph(filename):

    zf=zipfile.ZipFile(str(filename), 'r')
    dat = zf.read('map.xml').decode('utf-8')
    nmap = io.StringIO(initial_value=dat)
    zf.close()

    f = et.parse(nmap)
    root = f.getroot()
    if root.tag != "nexus":
        raise ValueError("not a nexus file")
    ##
    ## Apply some version specific fixes
    ##
    version = float(root.get('version'))
    if version < 0.221:
        raise ValueError("nexus map version < 0.221 ")

    if version < 0.32:
        # before version 0.32 the stroke width was abritrarily set to 1 even though the
        # value used was 1.3, this is now set and saved so correct here
        for elem in root.iter('text'):
            elem.set('width','1.3')

    if version in [0.47,0.48]:
        # this version stored text with unicode-escape (and tended to have a cariage return at the begining)
        for elem in root.getiterator():
            if elem.tag == 'text':
                elem.text = bytes(elem.text, "utf-8").decode('unicode-escape').strip()

    viewsxml = root.find('views')
    if version < 0.52:
        # these where the inverse-view with the non-inverse-view x and y in position 2 and 7!!!
        # Who knows! Must have been asleep when I coded that.
        # Fix up here so it's in standard QT form and all for the non-inverse-view
        for view in viewsxml.findall('view'):
            t = view.get('transform')
            T = graphics.Transform.fromxml(t)
            T2 = QtGui.QTransform(T.m11(),T.m12(),0,T.m21(),T.m22(),0,0,0,1)
            T3 = T2.inverted()[0]
            view.set('transform','[%f,%f,%f,%f,%f,%f,%f,%f,1]'%(T3.m11(),T3.m12(),T3.m13(),T3.m21(),T3.m22(),T3.m33(),T.m13(),T.m32()))

    ##
    ## create graphydb in memory first
    ##
    g=nexusgraph.NexusGraph()

    tags = {}
    def addstem(stemxml, parent, z=1, parentdir=1):
        stem = g.Node('Stem')
        if 'iconified' in stemxml.keys():
            stem['iconified'] = True

        transform = graphics.Transform.fromxml(stemxml.get('transform')).tolist()
        scale = transform[0]
        pos = [transform[6], transform[7]]
        ## angle not used before set to zero here
        stem['scale'] = scale
        stem['z'] = z

        d = int(stemxml.get('dir'))
        stem['flip'] = d*parentdir

        if d < 0:
            pos[0] = -pos[0]
        stem['pos'] = pos

        stem.save(setchange=False)

        e = g.Edge(parent, 'Child', stem)
        e.save(setchange=False)

        ## Optional tags:
        ## opacity (E)

        itemz = 1
        stemz = 1
        for itemxml in stemxml:
            if itemxml.tag == 'stem':
                addstem(itemxml, stem, stemz, parentdir=d)
                stemz += 1

            elif itemxml.tag == 'style':
                stem['styleclauses'] = []
                for subxml in itemxml:
                    if subxml.tag == 'branchcolor':
                        stem['branchcolor'] = subxml.get('value')
                    else:
                        raise Exception("Unknown style {}".format(subxml.tag))

            elif itemxml.tag == 'tag':
                text = itemxml.text
                if text not in tags:
                    v = g.Node('Tag')
                    v['text'] = text
                    v.save(setchange=False)
                    tags[text] = v
                else:
                    v = tags[text]
                se = g.Edge(v, 'Tagged', stem)
                se.save(setchange=False)

            ## All the content is saved under keys 'item<uid>'
            ## so undo only stores unchanged items
            elif itemxml.tag == 'text':
                ## add to stem content
                v = {'kind':'Text'}
                v['maxwidth'] = float(itemxml.get('maxwidth'))
                v['source'] = itemxml.text
                v['frame'] = graphics.Transform.fromxml(itemxml.get('transform')).tolist()
                v['z'] = itemz
                stem['item'+graphydb.generateUUID()] = v
                itemz += 1

            elif itemxml.tag == 'image':
                # XXX collect duplicates?
                sha1 = hashlib.sha1(itemxml.text.encode('utf-8')).hexdigest()
                existingim = g.fetch('(n:Image)', 'n.data.sha1 = :sha1', sha1=sha1).one

                if existingim is None:
                    im = g.Node('Image')
                    im['data'] = itemxml.text
                    im['sha1'] = sha1
                    im.save(setchange=False)
                else:
                    im = existingim

                se = g.Edge(stem, 'Attached', im).save(setchange=False)

                v = {'kind':'Image'}
                ## images are linked by the sha1 of the content
                v['datasha1'] = im['sha1']
                v['frame'] = graphics.Transform.fromxml(itemxml.get('transform')).tolist()
                v['z'] = itemz
                stem['item'+graphydb.generateUUID()] = v

                itemz += 1

            elif itemxml.tag == 'stroke':
                v = {'kind':'Stroke'}
                v['color'] = itemxml.get('color', '#000000')
                ## opacity = alpha
                v['opacity'] = float(itemxml.get('alpha', '1.0'))
                v['type'] = itemxml.get('type')
                v['width'] = float(itemxml.get('width', '1.3'))
                v['stroke'] = eval(itemxml.text)
                v['frame'] = graphics.Transform.fromxml(itemxml.get('transform')).tolist()
                v['z'] = itemz
                ## use uid to be able to track changes
                stem['item'+graphydb.generateUUID()] = v

                itemz += 1

            else:
                raise Exception("Unknown stem content {}".format(itemxml.tag))

        if parent['kind'] != 'Root':
            leaf = graphics.Leaf(stem, None)
            if d < 0:
                p = leaf.w()-leaf.e()
            else:
                p = leaf.e()-leaf.w()

        stem.save(setchange=False)

    # set abtritrary version <0.8 so format gets converted to latest in another conversion round
    g.savesetting('version', 0.7)
    graphroot = g.Node('Root').save(setchange=False)

    for itemxml in root:
        if itemxml.tag == 'stem':
            addstem(itemxml, graphroot)

    ##
    ## Copy memory graph to file in place of original xml
    ##

    ## First move old file aside
    logging.info("Moving old file aside")
    path = Path(filename)
    oldformat = path.with_suffix(".oldnex")
    if oldformat.exists():
        raise Exception("Can't convert, '%s' already exists!"%oldformat)
    path.rename(oldformat)

    if path.exists():
        raise Exception("Something went wrong in renaming file, '%s' still exists"%path)

    ## Create graph file under original name and copy contents across
    logging.info("Saving graph-based file")
    g2 = nexusgraph.NexusGraph(str(path))
    with g2.connection.backup("main", g.connection, "main") as b:
        while not b.done:
            b.step(100)

    logging.info("Done")

    return g2

def convert_to_full_tree(g):
    '''
    Convert <0.8 to 0.8 style where everything is a node in the graph
    '''

    ## First move old file aside
    logging.info("Backing up pre 0.8 file")
    path = Path(g.path)

    oldformat = path.with_suffix(".nex_pre08")
    if oldformat.exists():
        logging.exception("Can't convert, '%s' already exists!",oldformat)
        raise Exception("Can't convert, '%s' already exists!"%oldformat)

    shutil.copy2(path, oldformat)

    if not oldformat.exists():
        logging.exeption("Something went wrong in copying '%s' to '%s'",path,oldformat)
        raise Exception("Something went wrong in copying '%s' to '%s'"%(path,oldformat))

    g2 = g
    # clear the undo stack as it may make sense after changes
    g2.clearchanges()

    imageshas = {}
    images = g2.fetch('[n:Image]')
    for im in images:
        # Change the kind as we'll have kind Image from the items
        if im['sha1'] in imageshas:
            # remove accidental duplicates
            im.delete(disconnect=True, setchange=False)
            continue

        imageshas[im['sha1']] = im
        # change kind so it doesn't conflict with image item
        im['kind'] = "ImageData"
        im.save(setchange=False)
        # break edges as we'll relink on the items based on sha1
        for e in im.bothE():
            e.delete(setchange=False)

    # Change tags into attribute instead of node
    tagnodes = g2.fetch('[n:Tag]')
    #print('tagnodes: ',tagnodes)
    for tn in tagnodes:
        #print('edges ', tn.bothE())
        tagged = tn.outN('e.kind="Tagged"')
        #print(tagged)
        for n in tagged:
            tags = n.get('tags', [])
            if tn['text'] not in tags:
                tags.append(tn['text'])
            n['tags'] = tags
            #print(n['tags'])
            n.save(setchange=False)

    tagnodes.delete(disconnect=True, setchange=False)

    # # reverse direction of Tagged edges to make copy easier (follow down)
    # for e in g2.fetch('-[e:Tagged]>'):
    #     e['startuid'], e['enduid'] = e['enduid'], e['startuid']
    #     e.save(setchange=False)

    # now expand out the items into separate nodes
    stems = g2.fetch('[n:Stem]')
    for s in stems:
        # Add content items
        for k in list(s.keys()):
            if k == 'tip':
                # take opportunity to remove tip
                del s[k]
                continue
            elif not k.startswith('item'):
                continue
            itemdata = s[k]

            v = g2.Node(**itemdata)
            v.save(setchange=False)
            e = g2.Edge(s, 'In', v)
            e.save(setchange=False)

            if v['kind']=='Image':
                # change datasha1 key to sha1
                v['sha1'] = v['datasha1']
                del(v['datasha1'])
                v.save(setchange=False)
                # Find the image data by sha1
                imdata = imageshas[v['sha1']]
                g2.Edge(v, 'With', imdata).save(setchange=False)

            del s[k]

        s.save(setchange=False)

    g2.savesetting('version', graphics.VERSION)
    return g2

#----------------------------------------------------------------------
class NewOrOpenDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        logging.debug('Launching NewOrOpenDialog')

        self.setModal(True)
        self.setWindowTitle("Create or Open Nexus Map")

        baselayout = QtWidgets.QVBoxLayout()
        self.setLayout(baselayout)

        baselayout.addWidget(QtWidgets.QLabel("Recent Maps (click to open):"))
        listWidget = QtWidgets.QListWidget(self)
        baselayout.addWidget(listWidget)

        listWidget.itemClicked.connect(self.recentFileOpen)

        ## update the recent files
        settings = QtCore.QSettings("Ectropy", "Nexus")
        files = settings.value('recentFileList', [])

        self.maps = {}
        for f in files:
            name = QtCore.QFileInfo(f).fileName()
            path = QtCore.QFileInfo(f).path()
            text = "{} [{}]".format(name, path)
            self.maps[text] = f

            item = QtWidgets.QListWidgetItem(text, listWidget)

        hlayout = QtWidgets.QHBoxLayout()
        baselayout.addLayout(hlayout)

        button = QtWidgets.QPushButton("Quit")
        button.clicked.connect(self.reject)
        hlayout.addWidget(button)
        button = QtWidgets.QPushButton("New map")
        button.setToolTip("Create a new map")
        button.clicked.connect(self.newmap)
        hlayout.addWidget(button)
        button = QtWidgets.QPushButton("Open another")
        button.setToolTip("Open another map")
        button.clicked.connect(self.openmap)
        button.setDefault(True)
        hlayout.addWidget(button)


    def recentFileOpen(self, item):
        path = self.maps[item.text()]
        app = QtWidgets.QApplication.instance()
        app.raiseOrOpen(path)

        self.accept()

    def newmap(self):
        app = QtWidgets.QApplication.instance()
        app.dialogNew()
        self.accept()

    def openmap(self):
        app = QtWidgets.QApplication.instance()
        self.hide()
        w = app.dialogOpen()
        if w is not None:
            self.accept()
        else:
            self.reject()



#----------------------------------------------------------------------
class NexusApplication(QtWidgets.QApplication):
#----------------------------------------------------------------------

    def __init__(self):
        super().__init__(sys.argv)
        self.windows = []

        self.setAttribute(QtCore.Qt.AA_DontShowIconsInMenus)
        menu = QtWidgets.QMenu(self.tr("&Window"))
        menu.aboutToShow.connect(self.updateWindowMenu)

        act = QtWidgets.QAction(QtGui.QIcon(":/images/view-fullscreen.svg"), self.tr("Full Screen"), self)
        act.setStatusTip(self.tr("Toggle full screen mode"))
        act.triggered.connect(self.windowFullScreen)
        act.setCheckable(True)
        menu.addAction(act)
        act.setCheckable(True)
        self.actionFullScreen = act

        QtGui.QFontDatabase.addApplicationFont(":/images/et-book-roman-line-figures.ttf")
        QtGui.QFontDatabase.addApplicationFont(":/images/et-book-bold-line-figures.ttf")
        QtGui.QFontDatabase.addApplicationFont(":/images/et-book-display-italic-old-style-figures.ttf")
        QtGui.QFontDatabase.addApplicationFont(":/images/et-book-semi-bold-old-style-figures.ttf")
        QtGui.QFontDatabase.addApplicationFont(":/images/et-book-roman-old-style-figures.ttf")

        self.windowMenu = menu

        logging.debug('start')

    def updateWindowMenu(self):
        ## first update indicators for active window
        activewindow = self.activeWindow()
        if activewindow is None:
            pass
        elif activewindow.isFullScreen():
            self.actionFullScreen.setChecked(True)
        else:
            self.actionFullScreen.setChecked(False)

        ## clear the window list
        for action in self.windowMenu.actions():
            if hasattr(action, "windowAction"):
                self.windowMenu.removeAction(action)

        ## N.B. we need to keep a copy of the window list otherwise
        ## python's garbage collector with throw away our MainWindows!
        self.windows = self.windowList()
        for window in self.windows:
            act = QtWidgets.QAction(QtGui.QIcon(":/images/nexusicon.svg"), window.windowTitle(), self)
            ## tag the action so we can identify and delete it
            act.windowAction = True
            if window == activewindow:
                act.setEnabled(False)
            act.triggered.connect(window.activateWindowViaMenu)
            self.windowMenu.addAction(act)

    def windowFullScreen(self):
        window = self.activeWindow()
        if window.isFullScreen():
            window.showNormal()
            #window.showMaximized()
        else:
            window.showFullScreen()

        self.updateWindowMenu()

    def windowList(self):
        mainwindows = []
        for widget in self.topLevelWidgets():
            if isinstance(widget, MainWindow):
                mainwindows.append(widget)

        return mainwindows

    def raiseOrOpen(self, fileName):
        '''
        Either raise the window or open a new file
        '''

        logging.debug("raise or open: '%s'", fileName)
        if len(fileName)==0:
            return None
        for window in self.windowList():
            if window.scene.graph.path == fileName:
                w = window
                logging.debug("Raising %s", fileName)
                break
        else:
            logging.debug("Opening %s", fileName)
            w = MainWindow(fileName=fileName)

        w.show()
        w.raise_()
        w.activateWindow()

        return w

    def dialogOpen(self):

        fileName, dummy = QtWidgets.QFileDialog.getOpenFileName(filter="Nexus (*.nex) ;; All files (*)")
        if len(fileName) > 0:
            return self.raiseOrOpen(fileName)
        else:
            return None

    def dialogNew(self):
        path, dummy = QtWidgets.QFileDialog.getSaveFileName(None, "New File", filter="Nexus (*.nex) ;; All files (*)")
        if len(path) > 0:
            return self.createNewFile(path)
        else:
            return None

    def createNewFile(self, path):
        '''
        '''
        ## Ensure the file ends in ".nex"
        P = Path(path).with_suffix(".nex")

        if P.exists():
            ## Dialog to overwrite
            raise Exception('File already exists')

        g = nexusgraph.NexusGraph(str(P))
        graphroot = g.Node('Root').save(setchange=False)

        ## Create basic Root node
        stem = g.Node(
            kind='Stem',
            scale = 1.0,
            z = 10,
            flip = 1,
            pos = [0,0],
            ).save(setchange=False)

        g.Edge(graphroot, 'Child', stem).save(setchange=False)

        text = g.Node(
            kind='Text',
            source=P.stem.title(),
            frame=[1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0],
            z=0,
            ).save(setchange=False)

        g.Edge(stem, 'In', text).save(setchange=False)

        g.savesetting('version', graphics.VERSION)

        return self.raiseOrOpen(str(P))


    #X def event(self, event):
    #X     if event.type() == QtCore.QEvent.FileOpen:
    #X         f =  event.file()
    #X
    #X         logging.debug("Received FileOpen event for %s", f)
    #X
    #X         ext = os.path.splitext(f)[1]
    #X         if ext == '.nex':
    #X             canonicalFilePath = QtCore.QFileInfo(f).canonicalFilePath()
    #X             self.raiseOrOpen(canonicalFilePath)
    #X             return True
    #X         else:
    #X             return QtWidgets.QApplication.event(self, event)
    #X
    #X     else:
    #X         return QtWidgets.QApplication.event(self, event)

    def event(self, event):
        if event.type() == QtCore.QEvent.FileOpen:
            f =  event.file()

            logging.debug("Received FileOpen event for %s", f)

            ext = os.path.splitext(f)[1]
            if ext == '.nex':
                canonicalFilePath = QtCore.QFileInfo(f).canonicalFilePath()
                self.raiseOrOpen(canonicalFilePath)

        return QtWidgets.QApplication.event(self, event)

#----------------------------------------------------------------------
class MainWindow(QtWidgets.QMainWindow):
#----------------------------------------------------------------------

    sequenceNumber = 1
    MaxRecentFiles = 10

    def __init__(self, fileName=None, parent=None):

        super().__init__(parent)

        self.setDefaultSettings()

        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.isUntitled = True

        self.setWindowIcon(QtGui.QIcon(":/images/nexusicon.png"))

        self.editDialog = graphics.InputDialog()

        #
        # scene and view
        #
        self.scene = self.loadMap(fileName)

        self.scene.showEditDialog.connect(self.editDialog.setDialog)

        self.view = graphics.NexusView(self.scene)
        self.setCentralWidget(self.view)


        # dock = QtWidgets.QDockWidget(self.tr("Edit"), self)
        # self.editwidget = EditWidget(self)
        # dock.setWidget(self.editwidget)
        # self.addDockWidget(QtCore.Qt.TopDockWidgetArea, dock)

        #
        # Views widget
        #
        # self.viewsModel = ViewsModel(0,1)
        viewstoolbar = QtWidgets.QToolBar()
        self.views = ViewsWidget(self, viewstoolbar)

        dock = QtWidgets.QDockWidget(self.tr("Views"), self)
        self.viewsAct = dock.toggleViewAction()
        dock.setWidget(self.views)
        dock.setTitleBarWidget(viewstoolbar)
        self.addDockWidget(QtCore.Qt.LeftDockWidgetArea, dock)
        dock.dockLocationChanged.connect(self.views.locationChanged)
        dock.close()

        self.createActions()

        self.createMenus()
        self.createStatusBar()

        self.readSettings()

        self.scene.statusMessage.connect(self.showMessage)
        self.scene.linkClicked.connect(self.linkClicked)


        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)

        QtWidgets.QApplication.restoreOverrideCursor()

        self.view.update()
        self.raise_()

        self.setWindowTitle("{}".format(Path(self.scene.graph.path).name) )
        self.showMessage("Nexus Map loaded")

        rect = QtCore.QRectF()
        for item in self.scene.allChildStems():
            rect=rect.united(item.sceneBoundingRect())

        self.view.fitInView(rect, QtCore.Qt.KeepAspectRatio)

        ## update the recent files
        settings = QtCore.QSettings("Ectropy", "Nexus")
        files = settings.value('recentFileList', [])

        try:
            files.remove(fileName)
        except ValueError:
            pass

        files.insert(0, fileName)
        del files[self.MaxRecentFiles:]

        settings.setValue('recentFileList', files)

        self.updateRecentFilesMenu()

        QtWidgets.QApplication.restoreOverrideCursor()

        ## need to keep a reference or it will get garbage collected!
        app = QtWidgets.QApplication.instance()
        app.updateWindowMenu()

        self.presentationhiddenstems = []

        self.createToolBars()

        self.updateRecentFilesMenu()

        self.setMode()


    def setDefaultSettings(self):
        '''
        Make sure there is a consistent set of settings
        '''
        # XXX rename to set factory defaults and include function to do so

        settings = QtCore.QSettings("Ectropy", "Nexus")

        def setifunset(settings, key, value):
            if not settings.contains(key):
                settings.setValue(key, value)

        setifunset(settings, "style/branchcolor", "#715D80")
        setifunset(settings, "style/branchthickness", 5)
        setifunset(settings, "new/stemscale", 0.7)

        setifunset(settings, "input/pen1/color", "#000080")
        setifunset(settings, "input/pen2/color", "#000000")
        setifunset(settings, "input/pen3/color", "#006000")
        setifunset(settings, "input/pen4/color", "#C00000")
        setifunset(settings, "input/pen5/color", "#008080")
        setifunset(settings, "input/pen6/color", "#800080")
        setifunset(settings, "input/pen7/color", "#FFFF00")

        setifunset(settings, "input/pen1/width", 1.3)
        setifunset(settings, "input/pen2/width", 1.3)
        setifunset(settings, "input/pen3/width", 1.3)
        setifunset(settings, "input/pen4/width", 1.3)
        setifunset(settings, "input/pen5/width", 1.3)
        setifunset(settings, "input/pen6/width", 1.3)
        setifunset(settings, "input/pen7/width", 1.3)

    def closeEvent(self, event):

        self.writeSettings()
        event.accept()

    def activateWindowViaMenu(self):
        self.raise_()
        self.activateWindow()

    def newFile(self):
        '''
        Callback for action
        '''
        app = QtWidgets.QApplication.instance()
        app.dialogNew()

    def openRecentFile(self):
        ## Action target
        action = self.sender()
        if action:
            app = QtWidgets.QApplication.instance()
            app.raiseOrOpen(action.data())

    def saveAs(self):
        ## Action target

        curpath = Path(self.scene.graph.path)
        # XXX set same directory?

        graph = self.scene.graph

        path, dummy = QtWidgets.QFileDialog.getSaveFileName(None, "New File", filter="Nexus (*.nex) ;; All files (*)")
        if len(path) > 0:
            ## Ensure the file ends in ".nex"
            path = Path(path).with_suffix(".nex")

            ## Create graph file under original name and copy contents across
            self.showMessage("Copying %s -> %s"%(str(curpath), str(path)))
            g2 = nexusgraph.NexusGraph(str(path))
            with g2.connection.backup("main", graph.connection, "main") as b:
                while not b.done:
                    b.step(100)
            self.showMessage("Done")

            app = QtWidgets.QApplication.instance()
            app.raiseOrOpen(str(path))


    def exportLinkedSVGs(self):
        '''
        Find all .nex files linked from this one and export whole lot to converted SVG files
        '''

        ## Get target directory
        dialog = QtWidgets.QFileDialog(self, self.tr("Choose target folder"))
        dialog.setAcceptMode(QtWidgets.QFileDialog.AcceptOpen)
        dialog.setFileMode(QtWidgets.QFileDialog.Directory)
        dialog.setOption(QtWidgets.QFileDialog.ShowDirsOnly)
        if not dialog.exec_():
            return
        directory = Path(dialog.selectedFiles()[0])

        def getlinks(g, basepath):
            stems = g.fetch('[n:Stem]')
            mappath = Path(g.path).parent
            links = set()
            for stem in stems:
                if 'tags' in stem and 'hide' in stem['tags']:
                    continue
                for k,v in stem.items():
                    if k.startswith('item') and v['kind']=="Text":
                        ## find any links
                        try:
                            objs = et.fromstring(v['source'])
                        except et.ParseError:
                            continue
                        for link in objs.iter('a'):
                            href = link.attrib['href']
                            if href[-4:] == '.nex':
                                try:
                                    path = mappath.joinpath(href)
                                    path = path.resolve()
                                except FileNotFoundError:
                                    self.showMessage("Couldn't find '%s'"%path)
                                    continue
                                links.add(path.relative_to(basepath))
            return links

        progress = QtWidgets.QProgressDialog("Discovering maps...", "Abort", 0, 1, self)
        progress.setWindowModality(QtCore.Qt.WindowModal)
        progress.show()

        currentpath = Path(self.scene.graph.path)
        basepath = currentpath.parent
        links = getlinks(self.scene.graph, basepath)

        maps = set([currentpath.relative_to(basepath)])

        app = QtWidgets.QApplication.instance()

        while len(links)>0:
            app.processEvents()
            ## pick a file and load it
            link = links.pop()

            g = self.loadOrConvertMap(str(basepath.joinpath(link)))
            newlinks = getlinks(g, basepath)

            ## mark file as visited
            maps.add(link)

            for l in newlinks:
                if l not in maps:
                    links.add(l)

        progress.setMaximum(len(maps))
        progress.setLabelText("Converting %d maps..."%len(maps))

        ## maps now containst a set of linked maps with relative paths (to this one)
        for i,m in enumerate(maps):
            app.processEvents()

            ## copy entire graph to memory to modify so we don't mess up undo etc
            g = nexusgraph.NexusGraph()
            gf = nexusgraph.NexusGraph(str(basepath.joinpath(m)))
            with g.connection.backup("main", gf.connection, "main") as b:
                while not b.done:
                    b.step(100)

            for n in g.fetch('[n:Stem]', 'n.data.hide = 1'):
                n.discard('hide').save()
            scene = graphics.NexusScene()
            scene.graph = g
            rootnodes = g.fetch('(r:Root) -(e:Child)> [n:Stem]')

            for n in rootnodes:
                root = graphics.StemItem(node=n, scene=scene)
                root.renew(reload=False)

            svgtarget = directory.joinpath(m).with_suffix('.svg')
            self.exportSVG(scene, str(svgtarget))

            progress.setValue(i+1)
            progress.setLabelText("Converting %d maps..."%(len(maps)-i-1))
            if progress.wasCanceled():
                break

        progress.close()
        self.showMessage("Exported %d svg files."%len(maps))

    def exportText(self):

        filename, dummy = QtWidgets.QFileDialog.getSaveFileName(self, self.tr("Export Text"), filter="Text files (*.txt) ;; All files (*)")
        if len(filename)==0:
            return False
        path,ext = os.path.splitext(str(filename))
        path += '.txt'

        fp = open(path, "w")

        root = self.scene.root()
        fp.write( ' '.join(root.titles()) + '\n' )

        for child in root.allChildStems():
            if 'hide' not in child.getTags() and child.isVisible():
                title = ' '.join(child.titles())
                level = child.depth
                fp.write("\t"*level+title+"\n")

        fp.close()

    def exportSVG(self, scene=None, path=None):

        if scene is None or scene==False:
            # XXX the False is a hack to catch slot call from action
            scene = self.scene

        if path is None:
            pa,ext=os.path.splitext(str(self.scene.graph.path))

            fileName, dummy = QtWidgets.QFileDialog.getSaveFileName(self, self.tr("Export SVG"), pa+'.svg', filter="SVG files (*.svg) ;; All files (*)")
            if len(fileName)==0:
                return False
            path,ext = os.path.splitext(str(fileName))
            path += '.svg'

        self.showMessage("Exporting SVG to %s"%path)
        logging.info("Exporting SVG to %s"%path)

        # remove background so it doesn't appear in svg
        backgroundbrush = scene.backgroundBrush()
        scene.setBackgroundBrush(QtGui.QBrush())

        ## clean up scene ready for export
        frames = False
        if self.viewsFramesAct.isChecked():
            frames = True
            self.viewsFramesAct.trigger()

        ## deselect everything
        scene.clearSelection()

        hiddenstems = []
        R = QtCore.QRectF()
        for child in scene.allChildStems(includeroot=False):
            if 'hide' in child.getTags() and child.isVisible():
                child.hide()
                hiddenstems.append(child)
            else:
                R=R.united(child.boundingRect())


        ## links are broken in SVGgenerator ... work around this
        links = {}
        textitems = []
        linknumber=0
        shortlinknumber = 0
        for stem in scene.allChildStems():
            for textitem in stem.leaf.childItems():
                if isinstance(textitem, graphics.TextItem):
                    html = textitem.toHtml()
                    objs = et.fromstring(html)
                    # find any links
                    for link in objs.iter('a'):
                        # QT puts a span with the link style in the text part! SVGgenerator converts this to a drawn line :(
                        span = link.find('span')
                        if span is not None:
                            text = span.text

                            # replace some of text by index to form key
                            # just replace first 3 out of 5 to avoid changing lengths too much
                            # and causing wraping issues
                            # change all if url text is smaller

                            L = 5
                            if len(text)>=L:
                                randkey = text[:-L]+"%03d"%linknumber
                                linknumber +=1
                            else:
                                randkey = "%02d" % shortlinknumber
                                shortlinknumber += 1

                            # store key - [url, original text]
                            links[randkey] = {'url': link.attrib['href'], 'text': text}


                            ## replace text by random key so we can pick it up later in the svg
                            span.text = randkey

                            ## set item's xml from html (may end up doing multiple times if multiple links)
                            textitem.setHtml(et.tostring(objs).decode('utf-8'))

                            ## store item and html to restore after svg generation
                            ## duplicates won't matter
                            textitems.append((textitem, html))


                            ## change the a-link to span and remove the undelying span so we avoid the stupid underline decoration
                            #link.clear()
                            #link.tag = 'span'

                            ## replace text by random key so we can pick it up later in the svg
                            #link.text = randkey

        ## Get the title of the root node
        title = scene.root().titles()[0]

        ## grab source rect, this will be same as target
        ## which makes transforms easy
        sourceRect = scene.itemsBoundingRect()

        WIDTH = sourceRect.width()
        HEIGHT = sourceRect.height()

        buff = QtCore.QBuffer()
        buff.open(QtCore.QIODevice.ReadWrite)

        generator = QtSvg.QSvgGenerator()

        generator.setFileName(path)
        generator.setOutputDevice(buff)
        generator.setViewBox(sourceRect.toRect())
        generator.setTitle(title)
        generator.setDescription("A Nexus mindmap")

        painter = QtGui.QPainter(generator)
        scene.render(painter, sourceRect, sourceRect)
        painter.end()

        ## return text strings to previous
        for textitem, html in textitems:
            textitem.setHtml(html)

        et.register_namespace("","http://www.w3.org/2000/svg")
        et.register_namespace("xlink","http://www.w3.org/1999/xlink") # why does this only sometimes get linked?
        #root.set('xmlns:xlink', 'http://www.w3.org/1999/xlink')

        root = et.fromstring(buff.data())

        ## QT produces a whole lot of empty groups with lots of attributes. Collapse them here
        for parentg in root.findall('{http://www.w3.org/2000/svg}g'):
            for g in parentg.findall('{http://www.w3.org/2000/svg}g'):
                if len(g) == 0:
                    parentg.remove(g)

        ## wrap graphical elements in group for zooming and panning
        G = et.Element('g')
        G.set('id', 'viewcontrol')
        G.set('transform', 'matrix(1,0,0,1,{},{})'.format(int(-R.left()), int(-R.top())))
        for e in list(root):
            if e.tag in ['{http://www.w3.org/2000/svg}g']:
                G.append(e)
                root.remove(e)
        root.append(G)

        ## this plays havock with zoom
        if 'viewBox' in root.attrib:
            del root.attrib['viewBox']

        root.set('id', 'nexusmap')
        root.set('width', '100%')
        root.set('height', '100%')

        ## go through and change links to nex files to actual links to svg files
        for txtxml in root.iter('{http://www.w3.org/2000/svg}text'):
            if txtxml.text in links:
                url = links[txtxml.text]['url']

                ## convert .nex to .svgz
                basename, ext = os.path.splitext(url)
                if ext == '.nex':
                    url = basename+'.svg'

                text = links[txtxml.text]['text']

                linkxml = et.Element('a', {'{http://www.w3.org/1999/xlink}href':url, 'fill':'blue'})
                linkxml.text = text
                txtxml.text = ''
                txtxml.append(linkxml)


        ## XXX how to delete them entirely?
        for g in root.iter('{http://www.w3.org/2000/svg}g'):
            # remove default value
            # XXX problems if nested withon an opacity!=1 ?
            if g.get('fill-opacity', '') == '1':
                del g.attrib['fill-opacity']

            ## remove font attributes from groups that have only paths or images
            ## and line attributes (and font since in text) from only text groups
            onlypath = True
            onlytext = True
            for c in g:
                if c.tag not in ['{http://www.w3.org/2000/svg}path', '{http://www.w3.org/2000/svg}image']:
                    onlypath = False
                elif c.tag not in ['{http://www.w3.org/2000/svg}text']:
                    onlytext = False
            if onlypath:
                for a in ['font-family', 'font-size', 'font-weight', 'font-style']:
                    if a in g.attrib:
                        del g.attrib[a]
            if onlytext:
                for a in ['fill', 'stroke', 'stroke-linecap', 'stroke-linejoin','stroke-opacity','stroke-width',
                          'font-family', 'font-size', 'font-style', 'font-weight']:
                    if a in g.attrib:
                        del g.attrib[a]


        ## truncate numbers - don't need full precision
        # XXX % rounding would be better
        simpledec = re.compile(r'\d*\.\d+')
        def mround(match):
            return "{:.1f}".format(float(match.group()))

        for p in root.iter('{http://www.w3.org/2000/svg}path'):
            d = p.get('d')
            d2 = re.sub(simpledec, mround, d)
            p.set('d', d2)

            ## remove default values
            if p.get('vector-effect','')=='none':
                del p.attrib['vector-effect']


        script = et.Element('script')
        script.text = NAVJS
        script.tail = "\n"
        root.append(script)

        tree = et.ElementTree(root)

        directory = Path(path).parent
        if not directory.exists():
            directory.mkdir(parents=True)

        with open(path, 'wb') as f:
            tree.write(f, method='html')

        if frames:
            self.viewsFramesAct.trigger()
        for child in hiddenstems:
            child.show()

        scene.setBackgroundBrush(backgroundbrush)

    def about(self):
        QtWidgets.QMessageBox.about(self, self.tr("About Nexus"),
                                self.tr("Nexus - flexible mindmapping\n"
                                        "Alexei Gilchrist\n"
                                        "version %s\nGPL v3"%str(graphics.VERSION)))

    def createActions(self):

        app = QtWidgets.QApplication.instance()

        # ----------------------------------------------------------------------------------
        self.newAct = QtWidgets.QAction(QtGui.QIcon(":/images/new.svg"),self.tr("&New"), self)
        self.newAct.setShortcut(QtGui.QKeySequence.New)
        self.newAct.setStatusTip(self.tr("Create a new file"))
        self.newAct.triggered.connect(self.newFile)

        # ----------------------------------------------------------------------------------
        self.openAct = QtWidgets.QAction(QtGui.QIcon(":/images/open.svg"),self.tr("&Open..."), self)
        self.openAct.setShortcut(QtGui.QKeySequence.Open)
        self.openAct.setStatusTip(self.tr("Open an existing file"))
        self.openAct.triggered.connect(app.dialogOpen)

        # ----------------------------------------------------------------------------------
        # self.saveAct = QtWidgets.QAction(QtGui.QIcon(":/images/save.svg"),self.tr("&Save"), self)
        # self.saveAct.setShortcut(QtGui.QKeySequence.Save)
        # self.saveAct.setStatusTip(self.tr("Save the document to disk"))
        # self.saveAct.triggered.connect(self.save)

        # ----------------------------------------------------------------------------------
        self.saveAsAct = QtWidgets.QAction(QtGui.QIcon(":/images/save-as.svg"), self.tr("Save &As..."), self)
        self.saveAsAct.setStatusTip(self.tr("Save the document under a new name"))
        self.saveAsAct.triggered.connect(self.saveAs)

        # ----------------------------------------------------------------------------------
        self.exportSVGAct = QtWidgets.QAction(QtGui.QIcon(":/images/export.svg"), self.tr("Export as SVG..."), self)
        self.exportSVGAct.setShortcut(self.tr("Ctrl+E"))
        self.exportSVGAct.setStatusTip(self.tr("Export the map to SVG"))
        self.exportSVGAct.triggered.connect(self.exportSVG)

        self.exportLinkedSVGsAct = QtWidgets.QAction(QtGui.QIcon(":/images/export.svg"), self.tr("Export linked as SVG..."), self)
        self.exportLinkedSVGsAct.setStatusTip(self.tr("Recursively export all linked maps as SVG"))
        self.exportLinkedSVGsAct.triggered.connect(self.exportLinkedSVGs)

        self.exportTextAct = QtWidgets.QAction(QtGui.QIcon(":/images/export.svg"), self.tr("Export text..."), self)
        self.exportTextAct.setStatusTip(self.tr("Export text as outline"))
        self.exportTextAct.triggered.connect(self.exportText)

        # ----------------------------------------------------------------------------------
        self.printMapAct = QtWidgets.QAction(QtGui.QIcon(":/images/print.svg"),self.tr("&Print Map"), self)
        self.printMapAct.setShortcut(QtGui.QKeySequence.Print)
        self.printMapAct.setStatusTip(self.tr("Print whole map"))
        self.printMapAct.triggered.connect(self.printMapSlot)

        self.printViewsAct = QtWidgets.QAction(QtGui.QIcon(":/images/print.svg"),self.tr("&Print Views"), self)
        self.printViewsAct.setStatusTip(self.tr("Print Views"))
        self.printViewsAct.triggered.connect(self.printViewsSlot)
        # ----------------------------------------------------------------------------------
        self.closeAct = QtWidgets.QAction(self.tr("&Close"), self)
        self.closeAct.setShortcut(QtGui.QKeySequence.Close)
        self.closeAct.setStatusTip(self.tr("Close this window"))
        self.closeAct.triggered.connect(self.close)

        # ----------------------------------------------------------------------------------
        self.exitAct = QtWidgets.QAction(self.tr("Q&uit"), self)
        self.exitAct.setMenuRole(QtWidgets.QAction.QuitRole)
        self.exitAct.setShortcut(self.tr("Ctrl+Q"))
        self.exitAct.setStatusTip(self.tr("Quit the application"))
        self.exitAct.triggered.connect(QtWidgets.qApp.closeAllWindows)


        # ----------------------------------------------------------------------------------
        #self.grabModeAct = QtWidgets.QAction(QtGui.QIcon(":/images/grab-mode.svg"), self.tr("Grab Mode"), self)
        #self.grabModeAct.setCheckable(True)

        # ----------------------------------------------------------------------------------
        #self.addModeAct = QtWidgets.QAction(QtGui.QIcon(":/images/add-mode.svg"), self.tr("Add Mode"), self)
        #self.addModeAct.setCheckable(True)

        # ----------------------------------------------------------------------------------
        #self.moveModeAct = QtWidgets.QAction(QtGui.QIcon(":/images/move-mode.svg"), self.tr("Move Mode"), self)
        #self.moveModeAct.setCheckable(True)

        #modegroup = QtWidgets.QActionGroup(self)
        #modegroup.addAction(self.grabModeAct)
        #modegroup.addAction(self.addModeAct)
        #modegroup.addAction(self.moveModeAct)
        #self.grabModeAct.setChecked(True)

        # ----------------------------------------------------------------------------------
        self.cutAct = QtWidgets.QAction(QtGui.QIcon(":/images/edit-cut.svg"),self.tr("Cu&t"),
                                    self)
        self.cutAct.setShortcut(QtGui.QKeySequence.Cut)
        self.cutAct.setStatusTip(self.tr("Cut the current selection's "
                                         "contents to the clipboard"))
        self.cutAct.triggered.connect(self.scene.cut)

        # ----------------------------------------------------------------------------------
        self.copyAct = QtWidgets.QAction(QtGui.QIcon(":/images/edit-copy.svg"),self.tr("&Copy"),
                                     self)
        self.copyAct.setShortcut(QtGui.QKeySequence.Copy)
        self.copyAct.setStatusTip(self.tr("Copy the current selection's "
                                          "contents to the clipboard"))
        self.copyAct.triggered.connect(self.scene.copy)

        # ----------------------------------------------------------------------------------
        self.copyStemLinkAct = QtWidgets.QAction(QtGui.QIcon(":/images/edit-copy.svg"),self.tr("&Copy Links"),
                                     self)
        self.copyStemLinkAct.setShortcut("Shift+Ctrl+C")
        self.copyStemLinkAct.setStatusTip(self.tr("Copy the current selection links"
                                          "to the clipboard"))
        self.copyStemLinkAct.triggered.connect(self.scene.copyStemLink)

        # ----------------------------------------------------------------------------------
        self.pasteAct = QtWidgets.QAction(QtGui.QIcon(":/images/edit-paste.svg"),
                                      self.tr("&Paste"), self)
        self.pasteAct.setShortcut(QtGui.QKeySequence.Paste)
        self.pasteAct.setStatusTip(self.tr("Paste the clipboard's contents "
                                           "into the current selection"))
        self.pasteAct.triggered.connect(self.scene.paste)

        # ----------------------------------------------------------------------------------
        self.deleteAct = QtWidgets.QAction(QtGui.QIcon(":/images/edit-delete.svg"),
                                       self.tr("&Delete"), self)
        self.deleteAct.setShortcut(QtGui.QKeySequence.Delete)
        self.deleteAct.setStatusTip(self.tr("Delete selection"))
        self.deleteAct.triggered.connect(self.scene.delete)

        # ----------------------------------------------------------------------------------
        self.undoAct = QtWidgets.QAction(QtGui.QIcon(":/images/undo.svg"), self.tr("Undo"), self)
        self.undoAct.setShortcut(QtGui.QKeySequence.Undo)
        self.undoAct.setStatusTip(self.tr("Undo last change"))
        self.undoAct.triggered.connect(self.undo)

        # ----------------------------------------------------------------------------------
        self.setScaleAct = QtWidgets.QAction(self.tr("Set Scale"), self)
        self.setScaleAct.setStatusTip(self.tr("Set the scale for selected"))
        self.setScaleAct.setShortcut("S")
        self.setScaleAct.triggered.connect(self.sceneDialogSetScale)

        # ----------------------------------------------------------------------------------
        self.scaleByAct = QtWidgets.QAction(self.tr("Scale By"), self)
        self.scaleByAct.setStatusTip(self.tr("Scale selected by a factor"))
        self.scaleByAct.triggered.connect(self.sceneDialogScaleBy)

        # ----------------------------------------------------------------------------------
        self.increaseScaleAct = QtWidgets.QAction(self.tr("Increase Scale"), self)
        self.increaseScaleAct.setStatusTip(self.tr("Increase scale of selected"))
        self.increaseScaleAct.setShortcuts(["+","="])
        self.increaseScaleAct.triggered.connect(self.sceneSelectedIncreaseScale)

        # ----------------------------------------------------------------------------------
        self.decreaseScaleAct = QtWidgets.QAction(self.tr("Decrease Scale"), self)
        self.decreaseScaleAct.setStatusTip(self.tr("Decrease scale of selected"))
        self.decreaseScaleAct.setShortcuts(["-","_"])
        self.decreaseScaleAct.triggered.connect(self.sceneSelectedDecreaseScale)

        # ----------------------------------------------------------------------------------
        self.selectAllAct = QtWidgets.QAction(self.tr("Select All"), self)
        self.selectAllAct.setStatusTip(self.tr("Select all stems"))
        self.selectAllAct.setShortcut("A")
        self.selectAllAct.triggered.connect(self.sceneSelectAll)

        # ----------------------------------------------------------------------------------
        self.selectChildrenAct = QtWidgets.QAction(self.tr("Select Children"), self)
        self.selectChildrenAct.setStatusTip(self.tr("Select all child stems"))
        self.selectChildrenAct.setShortcut("C")
        self.selectChildrenAct.triggered.connect(self.sceneSelectChildren)

        # ----------------------------------------------------------------------------------
        self.selectSiblingsAct = QtWidgets.QAction(self.tr("Select Siblings"), self)
        self.selectSiblingsAct.setStatusTip(self.tr("Extend selection to siblings"))
        self.selectSiblingsAct.setShortcut("E")
        self.selectSiblingsAct.triggered.connect(self.sceneSelectSiblings)

        # ----------------------------------------------------------------------------------
        #self.clearStyleAct = QtWidgets.QAction(self.tr("Clear Style"), self)
        #self.clearStyleAct.setStatusTip(self.tr("Clear the style setting for selected"))
        #self.clearStyleAct.triggered.connect(self.sceneSelectedClearStyle)

        # ----------------------------------------------------------------------------------
        self.hideAct = QtWidgets.QAction(self.tr("Hide"), self)
        self.hideAct.setStatusTip(self.tr("Hide selected"))
        self.hideAct.setShortcut("H")
        self.hideAct.triggered.connect(self.sceneSelectedHide)

        # ----------------------------------------------------------------------------------
        self.setOpacityAct = QtWidgets.QAction(self.tr("Set Opacity"), self)
        self.setOpacityAct.setStatusTip(self.tr("Set the opacity of selected items"))
        self.setOpacityAct.setShortcut("O")
        self.setOpacityAct.triggered.connect(self.sceneDialogOpacity)

        # ----------------------------------------------------------------------------------
        self.toggleIconifyAct = QtWidgets.QAction(self.tr("Toggle Iconify"), self)
        self.toggleIconifyAct.setStatusTip(self.tr("Toggle showing item as icon only"))
        self.toggleIconifyAct.setShortcut("I")
        self.toggleIconifyAct.triggered.connect(self.sceneToggleIconify)

        # ----------------------------------------------------------------------------------
        self.clearUndoHistoryAct = QtWidgets.QAction(self.tr("Clear Undo History"), self)
        self.clearUndoHistoryAct.setStatusTip(self.tr("Clear all undo history"))
        self.clearUndoHistoryAct.triggered.connect(self.sceneClearUndoHistory)

        # ----------------------------------------------------------------------------------
        self.aboutAct = QtWidgets.QAction(self.tr("About"), self)
        self.aboutAct.setMenuRole(QtWidgets.QAction.AboutRole)
        self.aboutAct.setStatusTip(self.tr("Show the application's About box"))
        self.aboutAct.triggered.connect(self.about)

        # ----------------------------------------------------------------------------------
        self.zoomInAct = QtWidgets.QAction(QtGui.QIcon(":/images/zoom-in.svg"), self.tr("Zoom In"), self)
        self.zoomInAct.setShortcut(QtGui.QKeySequence.ZoomIn)
        self.zoomInAct.setStatusTip(self.tr("Zoom in"))
        self.zoomInAct.triggered.connect(self.view.zoomIn)

        # ----------------------------------------------------------------------------------
        self.zoomOutAct = QtWidgets.QAction(QtGui.QIcon(":/images/zoom-out.svg"), self.tr("Zoom Out"), self)
        self.zoomOutAct.setShortcut(QtGui.QKeySequence.ZoomOut)
        self.zoomOutAct.setStatusTip(self.tr("Zoom out"))
        self.zoomOutAct.triggered.connect(self.view.zoomOut)

        # ----------------------------------------------------------------------------------
        self.zoomSelectionAct = QtWidgets.QAction(QtGui.QIcon(":/images/zoom-select.svg"), self.tr("Zoom to Selection"), self)
        self.zoomSelectionAct.setShortcut("Z")
        self.zoomSelectionAct.setStatusTip(self.tr("Zoom to Selection"))
        self.zoomSelectionAct.triggered.connect(self.view.zoomSelection)

        # ----------------------------------------------------------------------------------
        self.zoomOriginalAct = QtWidgets.QAction(QtGui.QIcon(":/images/zoom-one.svg"), self.tr("Reset Zoom"), self)
        self.zoomOriginalAct.setStatusTip(self.tr("Reset Zoom"))
        self.zoomOriginalAct.triggered.connect(self.view.zoomOriginal)

        # ----------------------------------------------------------------------------------
        self.filterRunAct = QtWidgets.QAction(QtGui.QIcon(":/images/filter.svg"), self.tr("Run filter"), self)
        self.filterRunAct.setStatusTip(self.tr("Filter map"))
        # ----------------------------------------------------------------------------------
        self.filterClearAct = QtWidgets.QAction(QtGui.QIcon(":/images/filter-clear.svg"), self.tr("Clear filter"), self)
        self.filterClearAct.setStatusTip(self.tr("Clear filters"))

        # ----------------------------------------------------------------------------------
        # Modes
        #
        # self.presentationModeAct = QtWidgets.QAction(QtGui.QIcon(":/images/view-presentation.svg"), self.tr("Presentation"), self)
        # self.presentationModeAct.setStatusTip(self.tr("Set Toggle Presentation Mode"))
        # self.presentationModeAct.triggered.connect(self.setPresentationMode)
        # self.presentationModeAct.setCheckable(True)
        # self.presentationModeAct.setChecked(False)

        self.editModeAct = QtWidgets.QAction(QtGui.QIcon(":/images/grab-mode.svg"), self.tr("Edit Mode"), self)
        self.editModeAct.setCheckable(True)
        self.editModeAct.triggered.connect(self.setMode)

        self.presentationModeAct = QtWidgets.QAction(QtGui.QIcon(":/images/view-presentation.svg"), self.tr("Presentation Mode"), self)
        self.presentationModeAct.setCheckable(True)
        self.presentationModeAct.triggered.connect(self.setMode)

        self.recordModeAct = QtWidgets.QAction(QtGui.QIcon(":/images/microphone.svg"), self.tr("Record Mode"), self)
        self.recordModeAct.setCheckable(True)
        self.recordModeAct.triggered.connect(self.setMode)

        modegroup = QtWidgets.QActionGroup(self)
        modegroup.addAction(self.editModeAct)
        modegroup.addAction(self.presentationModeAct)
        modegroup.addAction(self.recordModeAct)

        self.editModeAct.setChecked(True)

        self.view.presentationEscape.connect(self.setMode)
        # ----------------------------------------------------------------------------------
        # Recording
        #
        self.recStartAct = QtWidgets.QAction(QtGui.QIcon(":/images/record.svg"), self.tr("Start Recording"), self)
        self.recStartAct.setCheckable(True)
        self.recStartAct.triggered.connect(self.recordStart)

        self.recPauseAct = QtWidgets.QAction(QtGui.QIcon(":/images/pause.svg"), self.tr("Pause Recording"), self)
        self.recPauseAct.setCheckable(True)
        self.recPauseAct.triggered.connect(self.recordPause)

        self.recEndAct = QtWidgets.QAction(QtGui.QIcon(":/images/stop.svg"), self.tr("End Recording"), self)
        self.recEndAct.setCheckable(True)
        self.recEndAct.triggered.connect(self.recordEnd)

        # self.recSourceAct = QtWidgets.QAction(QtGui.QIcon(":/images/sound.svg"), self.tr("Microphone Source"), self)
        # self.recSourceAct.triggered.connect(self.recordSetSource)

        # The Start/Pause/End don't form an action group as their state
        # is set by the audio class in response to actual state changes
        
        # ----------------------------------------------------------------------------------
        self.viewsAct.setIcon(QtGui.QIcon(":/images/view-index.svg"))
        self.viewsAct.setShortcut("Ctrl+I")
        #self.viewsAct.setDisabled(True)

        # ----------------------------------------------------------------------------------
        self.viewsNextAct = QtWidgets.QAction(QtGui.QIcon(":/images/view-forward.svg"),self.tr("Forward"), self)
        self.viewsNextAct.triggered.connect(self.viewsNext)
        #self.viewsNextAct.setDisabled(True)

        # ----------------------------------------------------------------------------------
        self.viewsPreviousAct = QtWidgets.QAction(QtGui.QIcon(":/images/view-back.svg"),self.tr("Back"), self)
        self.viewsPreviousAct.triggered.connect(self.viewsPrevious)
        #self.viewsPreviousAct.setDisabled(True)

        # ----------------------------------------------------------------------------------
        self.viewsHomeAct = QtWidgets.QAction(QtGui.QIcon(":/images/view-home.svg"),self.tr("Home"), self)
        self.viewsHomeAct.triggered.connect(self.viewsHome)
        #self.viewsHomeAct.setDisabled(True)

        # ----------------------------------------------------------------------------------
        self.viewsFirstAct = QtWidgets.QAction(QtGui.QIcon(":/images/view-first.svg"),self.tr("First"), self)
        self.viewsFirstAct.triggered.connect(self.viewsFirst)
        #self.viewsFirstAct.setDisabled(True)

        # ----------------------------------------------------------------------------------
        self.viewsFramesAct = QtWidgets.QAction(self.tr("Show Frames"), self)
        self.viewsFramesAct.triggered.connect(self.viewsFrames)
        self.viewsFramesAct.setCheckable(True)
        self.viewsFramesAct.setChecked(False)
        #self.viewsFramesAct.setDisabled(True)

        # ----------------------------------------------------------------------------------
        self.viewRotateAct = QtWidgets.QAction(self.tr("Allow Rotations"), self)
        self.viewRotateAct.setCheckable(True)
        self.viewRotateAct.setChecked(False)

        # ----------------------------------------------------------------------------------
        self.setBackgroundAct = QtWidgets.QAction(self.tr("Set Background..."), self)
        self.setBackgroundAct.triggered.connect(self.sceneSetBackground)

        # ----------------------------------------------------------------------------------
        self.hidePointerAct = QtWidgets.QAction(self.tr("Hide Pointer"), self)
        self.hidePointerAct.setCheckable(True)
        self.hidePointerAct.setChecked(False)
        self.hidePointerAct.triggered.connect(self.hidePointer)
        self.hidePointerAct.setEnabled(False)

        # ----------------------------------------------------------------------------------
        self.recentFileActs = []
        for ii in range(self.MaxRecentFiles):
            self.recentFileActs.append(
                QtWidgets.QAction(self, visible=False, triggered=self.openRecentFile)
            )

    def createMenus(self):

        self.fileMenu = self.menuBar().addMenu(self.tr("&File"))
        self.fileMenu.addAction(self.newAct)
        self.fileMenu.addAction(self.openAct)
        self.recentMenu = self.fileMenu.addMenu("Recent")
        for ii in range(self.MaxRecentFiles):
            self.recentMenu.addAction(self.recentFileActs[ii])
        self.fileMenu.addSeparator()
        # self.fileMenu.addAction(self.saveAct)
        self.fileMenu.addAction(self.saveAsAct)
        self.fileMenu.addSeparator()
        self.fileMenu.addAction(self.printMapAct)
        self.fileMenu.addAction(self.printViewsAct)
        self.fileMenu.addSeparator()
        self.fileMenu.addAction(self.exportSVGAct)
        self.fileMenu.addAction(self.exportLinkedSVGsAct)
        self.fileMenu.addAction(self.exportTextAct)
        self.fileMenu.addSeparator()
        self.fileMenu.addAction(self.closeAct)
        self.fileMenu.addAction(self.exitAct)

        self.editMenu = self.menuBar().addMenu(self.tr("&Edit"))
        self.editMenu.addAction(self.undoAct)
        self.editMenu.addSeparator()
        self.editMenu.addAction(self.cutAct)
        self.editMenu.addAction(self.copyAct)
        self.editMenu.addAction(self.copyStemLinkAct)
        self.editMenu.addAction(self.pasteAct)
        self.editMenu.addSeparator()
        self.editMenu.addAction(self.deleteAct)
        self.editMenu.addSeparator()
        # self.editMenu.addAction(self.grabModeAct)
        # self.editMenu.addAction(self.addModeAct)
        # self.editMenu.addAction(self.moveModeAct)
        # self.editMenu.addSeparator()
        self.editMenu.addAction(self.selectAllAct)
        self.editMenu.addAction(self.selectChildrenAct)
        self.editMenu.addAction(self.selectSiblingsAct)
        self.editMenu.addSeparator()
        self.editMenu.addAction(self.setScaleAct)
        self.editMenu.addAction(self.scaleByAct)
        self.editMenu.addAction(self.increaseScaleAct)
        self.editMenu.addAction(self.decreaseScaleAct)
        #self.editMenu.addAction(self.clearStyleAct)
        self.editMenu.addAction(self.hideAct)
        self.editMenu.addAction(self.setOpacityAct)
        self.editMenu.addAction(self.toggleIconifyAct)
        self.editMenu.addSeparator()
        self.editMenu.addAction(self.clearUndoHistoryAct)

        self.viewMenu = self.menuBar().addMenu(self.tr("&View"))
        self.viewMenu.addAction(self.zoomInAct)
        self.viewMenu.addAction(self.zoomOutAct)
        self.viewMenu.addAction(self.zoomSelectionAct)
        self.viewMenu.addSeparator()

        self.viewMenu.addAction(self.presentationModeAct)
        self.viewMenu.addAction(self.editModeAct)
        self.viewMenu.addAction(self.presentationModeAct)
        self.viewMenu.addAction(self.recordModeAct)
        self.viewMenu.addSeparator()
        self.viewMenu.addAction(self.viewsFramesAct)
        self.viewMenu.addAction(self.viewRotateAct)
        self.viewMenu.addAction(self.setBackgroundAct)
        self.viewMenu.addAction(self.hidePointerAct)
        self.viewMenu.addSeparator()
        self.viewMenu.addAction(self.viewsAct)
        self.viewMenu.addAction(self.viewsFirstAct)
        self.viewMenu.addAction(self.viewsHomeAct)
        self.viewMenu.addAction(self.viewsNextAct)
        self.viewMenu.addAction(self.viewsPreviousAct)

        self.recMenu = self.menuBar().addMenu(self.tr("&Recording"))
        self.recMenu.addAction(self.recStartAct)
        self.recMenu.addAction(self.recPauseAct)
        self.recMenu.addAction(self.recEndAct)
        self.recMenu.setEnabled(False)

        # grab the window menu maintained from the application
        app = QtWidgets.QApplication.instance()
        self.menuBar().addMenu(app.windowMenu)

        self.menuBar().addSeparator()

        self.helpMenu = self.menuBar().addMenu(self.tr("&Help"))
        self.helpMenu.addAction(self.aboutAct)

    def updateRecentFilesMenu(self):
        settings = QtCore.QSettings("Ectropy", "Nexus")
        files = settings.value('recentFileList', [])

        numRecentFiles = min(len(files), self.MaxRecentFiles)

        for ii in range(numRecentFiles):
            name = QtCore.QFileInfo(files[ii]).fileName()
            path = QtCore.QFileInfo(files[ii]).path()
            text = "{} [{}]".format(name, path)
            self.recentFileActs[ii].setText(text)
            self.recentFileActs[ii].setData(files[ii])
            self.recentFileActs[ii].setVisible(True)

        for ii in range(numRecentFiles, self.MaxRecentFiles):
            self.recentFileActs[ii].setVisible(False)



    def createToolBars(self):
        self.fileToolBar = self.addToolBar(self.tr("File"))
        self.fileToolBar.setIconSize(QtCore.QSize(24,24))
        self.fileToolBar.addAction(self.newAct)
        self.fileToolBar.addAction(self.openAct)

        self.editToolBar = self.addToolBar(self.tr("Edit"))
        self.editToolBar.setIconSize(QtCore.QSize(24,24))
        self.editToolBar.addAction(self.undoAct)
        self.editToolBar.addAction(self.cutAct)
        self.editToolBar.addAction(self.copyAct)
        self.editToolBar.addAction(self.pasteAct)
        self.editToolBar.addAction(self.deleteAct)

        self.viewToolBar = self.addToolBar(self.tr("View"))
        self.viewToolBar.setIconSize(QtCore.QSize(24,24))
        self.viewToolBar.addAction(self.zoomInAct)
        self.viewToolBar.addAction(self.zoomOutAct)
        self.viewToolBar.addAction(self.zoomSelectionAct)
        self.viewToolBar.addAction(self.viewsAct)
        self.viewToolBar.addAction(self.viewsFirstAct)
        self.viewToolBar.addAction(self.viewsPreviousAct)
        self.viewToolBar.addAction(self.viewsHomeAct)
        self.viewToolBar.addAction(self.viewsNextAct)

        self.modeToolBar = self.addToolBar(self.tr("Mode"))
        self.modeToolBar.addAction(self.editModeAct)
        self.modeToolBar.addAction(self.presentationModeAct)
        self.modeToolBar.addAction(self.recordModeAct)

        self.recToolBar = self.addToolBar(self.tr("Record"))
        self.recToolBar.setIconSize(QtCore.QSize(24,24))
        self.recToolBar.addAction(self.recStartAct)
        self.recToolBar.addAction(self.recPauseAct)
        self.recToolBar.addAction(self.recEndAct)
        self.recSourceCombo = QtWidgets.QComboBox()
        self.recToolBar.addWidget(self.recSourceCombo)


        self.filterEdit = FilterEdit()
        self.filterToolBar = self.addToolBar(self.tr("Filter"))
        self.filterToolBar.addWidget(self.filterEdit)
        self.filterToolBar.addAction(self.filterClearAct)
        self.filterToolBar.addAction(self.filterRunAct)
        self.filterToolBar.setIconSize(QtCore.QSize(24,24))
        self.filterEdit.runfilter.connect(self.sceneFilterStems)
        self.filterRunAct.triggered.connect(self.filterEdit.editingFinished2)
        self.filterClearAct.triggered.connect(self.filterEdit.clear)


    def createStatusBar(self):
        self.showMessage("Ready")

    def showMessage(self, msg, ms=2000):
        self.statusBar().showMessage(self.tr(msg), ms)
        logging.info("Statusbar: {}".format(msg))

    def readSettings(self):
        settings = QtCore.QSettings("Ectropy", "Nexus")
        pos = settings.value('pos', QtCore.QPoint(200, 200))
        size = settings.value('size', QtCore.QSize(400, 400))
        self.resize(size)
        self.move(pos)

    def writeSettings(self):
        settings = QtCore.QSettings("Ectropy", "Nexus")
        settings.setValue('pos', self.pos())
        settings.setValue('size', self.size())

    def undo(self):
        changeditems = self.scene.graph.undo()
        ## first pass - refresh the whole lot
        # XXX more efficient undo by looking at changeditems
        changedtypes = [t for t,uid in changeditems]
        if '+' in changedtypes:
            ## Refresh the whole lot as we don't know where it was removed from
            self.scene.root().renew()
            return

        changeduids = [uid for t,uid in changeditems]

        allchidren = []
        parents = []
        for item in self.scene.allChildStems(includeroot=True):
            if item.node['uid'] in changeduids:
                parent = item.parentItem()
                if parent is None:
                    parents.append(item)
                else:
                    parents.append(parent)
                    allchidren.append(item)
                allchidren.extend(item.allChildStems())

        for p in parents:
            if p not in allchidren:
                p.renew()

        # XXX sometimes no parents?!
        # XXX happens when reversing a hide as the stems are no longer in scene!
        if len(parents)==0:
            self.scene.root().renew()

    def loadOrConvertMap(self, filename):
        '''
        Load the old zip format
        Create a graphydb in memory
        Move to file
        '''

        try:
            g = nexusgraph.NexusGraph(filename)
            g.stats ## this will throw an Exception if it fails
        except apsw.NotADBError:
            self.showMessage("{} is not a graphydb, converting...".format(filename))
            g = convert_xml_to_graph(filename)

        version = g.getsetting('version')
        if version < 0.8:
            self.showMessage("{} version < 0.8, converting...".format(filename))
            g = convert_to_full_tree(g)

        return g

    def loadMap(self, filename):
        '''
        Load map data into a scene.

        Do not update current views yet so this function can be used in scripting.
        '''
        logging.debug("Loading map data from %s", filename)
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)

        g = self.loadOrConvertMap(filename)

        try:
            scene = graphics.NexusScene(self)
            scene.graph = g

            ## Find base items and create trees
            # XXX there should only be 1 root item - check
            rootnodes = g.fetch('(r:Root) -(e:Child)> [n:Stem]')
            for n in rootnodes:
                root = graphics.StemItem(node=n, scene=scene)
                root.renew(reload=False)


        except ValueError as e:
            error = 'Failed to open file "%s": %s' % (filename, e)
            raise Exception(error)

        QtWidgets.QApplication.restoreOverrideCursor()

        return scene

    def printMap(self, printer):

        painter = QtGui.QPainter(printer)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setRenderHint(QtGui.QPainter.TextAntialiasing)
        painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)

        self.scene.clearSelection()
        scenebrush = self.scene.backgroundBrush()
        self.scene.setBackgroundBrush(QtGui.QBrush(QtCore.Qt.NoBrush))

        targetRect = QtCore.QRectF(0, 0, painter.device().width(), painter.device().height())

        sourceRect = QtCore.QRectF()
        for item in self.scene.allChildStems():
            if item.isVisible():
                sourceRect = sourceRect.united(item.sceneBoundingRect())

        ## this is how scene.render() works out the scaling ratio for KeepAspectRatio
        xratio = targetRect.width() / sourceRect.width()
        yratio = targetRect.height() / sourceRect.height()
        ratio = min(xratio, yratio)

        ## by default the top left corners of source and target will coincide
        ## these are the offsets of painter to centre map
        dx = (targetRect.width() - ratio*sourceRect.width())/2.0
        dy = (targetRect.height() - ratio*sourceRect.height())/2.0

        ## this will center the map
        painter.translate(dx, dy)

        ## top and left justified:
        #painter.translate(0, 0)

        ## top and centred:
        #painter.translate(dx, 0)

        self.scene.render(painter, targetRect, sourceRect)

        painter.end()
        self.scene.setBackgroundBrush(scenebrush)


    def printViews(self, printer):

        VIEWS = self.viewsModel.rowCount()


        painter = QtGui.QPainter(printer)

        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setRenderHint(QtGui.QPainter.TextAntialiasing)
        painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)

        self.scene.clearSelection()
        scenebrush = self.scene.backgroundBrush()
        self.scene.setBackgroundBrush(QtGui.QBrush(QtCore.Qt.NoBrush))

        targetRect = QtCore.QRectF(0, 0, painter.device().width(), painter.device().height())

        ## keep a record of the visible stems, will hide stems not in view to save space.
        visibleStems = []
        for stem in self.scene.allChildStems():
            if stem.isVisible():
                visibleStems.append(stem)


        for ii in range(VIEWS):
            viewitem = self.viewsModel.item(ii)

            # XXX clean up this code .. doesn't do rotations
            matrix = viewitem.viewInverseTransform()
            center = viewitem.viewCentre()
            scale = sqrt(matrix.m11()**2+matrix.m21()**2)
            rotation = atan2(matrix.m11(), matrix.m21()) # between -pi and pi
            if rotation < 0:
                ## make between 0 and 2pi
                rotation = 2*pi+rotation

            tmpmatrix = QtGui.QTransform()
            tmpmatrix.rotateRadians(rotation-pi/2.0)
            tmpmatrix.scale(scale, scale)

            matrixinv, dummy = tmpmatrix.inverted()

            ## should max out the rect item in target rect?
            sourceRect = QtCore.QRectF(0, 0, ViewRectangle.VIEWW, ViewRectangle.VIEWH)
            sourceRect.translate(-sourceRect.width()/2.0, -sourceRect.height()/2.0)

            sourceRect = matrixinv.mapRect(sourceRect)
            sourceRect.translate(center)

            # XXX hide any view rects

            ## hide items not in view
            inview = []
            for item in viewitem.viewRectItem.collidingItems():
                if isinstance(item, graphics.StemItem):
                    inview.append(item)
                    ## if parents hide so do the children
                    inview.extend(item.allParentStems())
                    ## add any children not explicitly hidden since at the very least the tails will be visible
                    for child in item.childStems2:
                        if child in visibleStems:
                            inview.append(child)

            for stem in visibleStems:
                if stem not in inview:
                    stem.hide()

            self.scene.render(painter, targetRect, sourceRect)

            ## show items previously visible (or collidingItems won't register them for next view)
            for stem in visibleStems:
                stem.show()

            if ii < VIEWS-1:
                self.printer.newPage()

        painter.end()
        self.scene.setBackgroundBrush(scenebrush)

    def printIt(self, views=False):

        self.printer = QtPrintSupport.QPrinter(QtPrintSupport.QPrinter.HighResolution)
        self.printer = QtPrintSupport.QPrinter()
        self.printer.setOutputFormat(QtPrintSupport.QPrinter.NativeFormat)

        self.printer.setColorMode(QtPrintSupport.QPrinter.Color)
        self.printer.setCreator('Nexus %s' % str(graphics.VERSION))

        filename = os.path.basename(str(self.scene.graph.path))
        self.printer.setDocName(filename)
        self.printer.setOrientation(QtPrintSupport.QPrinter.Landscape)

        self.printer.setOutputFormat(QtPrintSupport.QPrinter.NativeFormat)

        # XXX PyInstaller BUG
        # XXX normal print dialog noshow with a "QPrintDialog: Cannot be used on non-native printers" error
        #dialog = QtPrintSupport.QPrintPreviewDialog(self.printer, self)
        dialog = QtPrintSupport.QPrintDialog(self.printer, self)

        dialog.setWindowTitle(self.tr("Print ")+filename)

        ## hide frames
        frames = False
        if self.viewsFramesAct.isChecked():
            frames = True
            self.viewsFramesAct.trigger()

        hiddenstems = []
        for child in self.scene.allChildStems(includeroot=False):
            if 'hide' in child.getTags() and child.isVisible():
                child.hide()
                hiddenstems.append(child)

        if views:
            ## Used for print preview:
            dialog.paintRequested.connect(self.printViews)

            if dialog.exec_():
                self.printViews(self.printer)
        else:
            ## Used for print preview:
            #dialog.paintRequested.connect(self.printMap)

            if dialog.exec_():
                self.printMap(self.printer)

        ## restore frames visibility
        if frames:
            self.viewsFramesAct.trigger()
        for child in hiddenstems:
            child.show()

    def printMapSlot(self):
        self.printIt()

    def printViewsSlot(self):
        self.printIt(views=True)

    def sceneFilterStems(self,  command):
        II = interpreter.FilterInterpreter(self.scene)
        out = II.run(command)
        logging.info(out)

    def sceneDialogScaleBy(self):
        selected = self.scene.selectedItems()

        if len(selected)==0:
            QtWidgets.QMessageBox.information(None,"Warning", "No stems selected.")
            return

        scale, ok = QtWidgets.QInputDialog.getDouble(None, "Scale selected", "Scale by:",
                    value=1.0, min=0.01, max=10, decimals=2)

        if ok:
            self.sceneSelectedScaleBy(scale)

    def sceneSelectedScaleBy(self, scale):
        batch = graphydb.generateUUID()
        for item in self.scene.selectedItems():
            item.node['scale']=item.node.get('scale',1.0)*scale
            item.node.save(batch=batch, setchange=True)
            item.renew(reload=False, children=False, recurse=False, position=False)

    def sceneSelectedIncreaseScale(self):
        self.sceneSelectedScaleBy(1.1)

    def sceneSelectedDecreaseScale(self):
        self.sceneSelectedScaleBy(0.9)

    def sceneDialogSetScale(self):
        selected = self.scene.selectedItems()
        if len(selected)==0:
            return

        # is there a common scale in selected items?
        scales = [float(stem.node.get('scale', 1.0)) for stem in selected ]

        if min(scales)==max(scales):
            initialscale = scales[0]
        else:
            initialscale = 1.0

        if len(selected)==0:
            QtWidgets.QMessageBox.information(None,"Warning", "No stems selected.")
            return

        scale, ok = QtWidgets.QInputDialog.getDouble(None, "Set scale", "Set scale to:",
                    value=initialscale, min=0.01, max=10, decimals=2)

        if ok:
            selected = self.scene.selectedItems()
            batch = graphydb.generateUUID()
            for item in selected:
                item.node['scale'] = scale
                item.node.save(batch=batch, setchange=True)
                item.renew(reload=False, children=False, recurse=False, position=False)

    def sceneSelectedHide(self):
        selected = self.scene.selectedItems()
        parents = []
        allchildren = []
        batch = graphydb.generateUUID()
        for item in selected:
            if item.depth > 0:
                item.node['hide'] = True
                item.node.save(batch=batch, setchange=True)
                parent = item.parentStem()
                parents.append(parent)
                allchildren.extend(parent.allChildStems())

        for p in parents:
            if p not in allchildren:
                p.renew(reload=False, position=False)

    def sceneDialogOpacity(self):
        selected = self.scene.selectedItems()
        if len(selected)==0:
            return

        opacity, ok = QtWidgets.QInputDialog.getDouble(None, "Set opacity", "Set opacity:",
                    value=1.0, min=0.01, max=1, decimals=2)

        if ok:
            batch = graphydb.generateUUID()
            for item in selected:
                if opacity < 1:
                    item.node['opacity'] = opacity
                else:
                    item.node.discard('opacity')
                item.node.save(batch=batch, setchange=True)
                item.renew(reload=False, children=False, position=False)


    def sceneToggleIconify(self):
        selected = self.scene.selectedItems()
        if len(selected)==0:
            return

        batch = graphydb.generateUUID()

        for item in selected:
            if 'iconified' in item.node:
                del item.node['iconified']
            else:
                item.node['iconified'] = True

            item.node.save(batch=batch, setchange=True)
            item.renew(children=False, )

    def sceneClearUndoHistory(self):
        self.scene.graph.clearchanges()
        logging.info("Undo changes cleared")

    #def sceneSelectedClearStyle(self):
    #    #Z XXX this looks old style,  need to update
    #    selected = self.scene.selectedItems()
    #    for item in selected:
    #        item._style.clear()
    #        item.updateStem()
    #        for child in item.allChildStems():
    #            child.updateStem()

    def sceneSelectAll(self):
        '''
        Toggle selection of all non root stems
        '''
        selected = [stem.isSelected() for stem in self.scene.allChildStems(includeroot=False)]
        if len(selected)==0:
            return

        ## Are they all selected?
        allselected = reduce(lambda x,y: x and y, selected)

        for stem in self.scene.allChildStems(includeroot=False):
            stem.setSelected(not allselected)

    def sceneSelectChildren(self):
        selected = self.scene.selectedItems()
        for selectedstem in selected:
            toselect=selectedstem.allChildStems()
            for stem in toselect:
                stem.setSelected(True)

    def sceneSelectSiblings(self):
        selected = self.scene.selectedItems()
        for selectedstem in selected:
            parent = selectedstem.parentStem()
            if parent is not None:
                toselect = parent.childStems2
                for stem in toselect:
                    stem.setSelected(True)

    def sceneSetBackground(self):
        self.scene.backgroundDialog.show()
        self.scene.backgroundDialog.raise_()
        self.scene.backgroundDialog.activateWindow()

    def strippedName(self, fullFileName):
        return QtCore.QFileInfo(fullFileName).fileName()


    def linkClicked(self, url):
        logging.debug('link clicked: %s', url)

        urlbits = urllib.parse.urlparse(str(url))

        if urlbits.scheme in ['', 'file']:
            # opening a file locally

            # get full path to file
            if urlbits.path[0] != '/':
                # it's a relative path
                mappath = os.path.dirname(str(self.scene.graph.path))
                if mappath == '':
                    mappath = os.path.dirname(urlbits.path)
                path = os.path.join(mappath,urlbits.path)
            else:
                path = urlbits.path

            if not os.path.exists(path):
                self.showMessage("file does not exist: %s"%str(path))
                return

            # handle nexus files ourselves
            if len(path)>3 and path[-4:]=='.nex':
                app = QtWidgets.QApplication.instance()
                existing = app.raiseOrOpen(path)

                if self.presentationModeAct.isChecked():
                    existing.presentationModeAct.activate(QtWidgets.QAction.Trigger)
                    existing.jumpToView(existing.viewsModel.firstView())

            else:
                # let the OS handle opening the file
                QtGui.QDesktopServices.openUrl(QtCore.QUrl(urllib.parse.urljoin('file:',path)))

        else:
            ## pass URL to OS to open ..
            # TODO webbrowser broken in Sierra 10.12.5 use QT instead
            # see http://www.andrewjaffe.net/blog/2017/05/python-bug-hunt.html
            self.showMessage("Opening %s"%str(url))
            QtGui.QDesktopServices.openUrl(QtCore.QUrl(url))
            #webbrowser.open(url)


    def jumpToView(self,  viewitem):

        if viewitem is None:
            return

        ## Below we implement the algorithm in
        ## "Smooth and Efficient Zooming and Panning" J.J. van Wijk and W.A.A. Nuij

        ## Effective velocity, this will determine the number of steps
        V = 0.003
        ## rho is a tradeoff between zooming and panning, higher values jump more
        rho = 1.6

        ## initial point
        sides0 = self.view.getViewSides()
        lp0 = QtCore.QPointF(*sides0['left'])
        rp0 = QtCore.QPointF(*sides0['right'])
        c0 = (lp0+rp0)/2.0
        width0 = sqrt((lp0.x()-rp0.x())**2+(lp0.y()-rp0.y())**2)
        rot0 = atan2(-(rp0-lp0).y(), (rp0-lp0).x())


        ## final point
        lp1 = QtCore.QPointF(*viewitem['left'])
        rp1 = QtCore.QPointF(*viewitem['right'])
        c1 = (lp1+rp1)/2.0
        width1 = sqrt((lp1.x()-rp1.x())**2+(lp1.y()-rp1.y())**2)
        rot1 = atan2(-(rp1-lp1).y(), (rp1-lp1).x())

        ## the algorithm below is in terms of the width of the field of view
        ## the natural width at scaling 1 will be 1

        ## the transform scale is inversely proportional with field of view
        w0 = width0
        w1 = width1

        ## we are moving along a 2D line from 0 to u1
        u1 = sqrt( (c1.x()-c0.x())**2 + (c1.y()-c0.y())**2 )

        ## unit vector in direction of motion
        uvector = (c1-c0)/u1

        ## s is the distance (?) along the path [0 -> S]
        try:
            b0 = (w1**2 - w0**2 + rho**4 * u1**2 )/(2*w0*u1*rho**2 )
            b1 = (w1**2 - w0**2 - rho**4 * u1**2 )/(2*w1*u1*rho**2 )
        except ZeroDivisionError:
            b0 = b1 = 0
        r0 = log(-b0+sqrt(b0**2+1))
        r1 = log(-b1+sqrt(b1**2+1))
        S = (r1-r0)/rho

        tottime = S/V

        ## how often to call the frame update in ms
        ## 33 = 30 frames/s
        dt = 33

        totalsteps = int(round(tottime/dt))
        logging.debug("Transition: tot time: %f,  steps:%d",tottime, totalsteps)

        if totalsteps > 0:
            angle1 = rot1-rot0
            if angle1>=0:
                angle2 = -(2*pi-angle1)
            else:
                angle2 = (2*pi+angle1)
            if abs(angle1) <= abs(angle2):
                angle = angle1
            else:
                angle = angle2
            drot=angle/float(totalsteps)
        else:
            drot = 0

        ## do all the calculations initially and cache the results
        self.viewsteps = []
        for ii in range(1,totalsteps):
            s = ii/float(totalsteps)*S
            us = w0*cosh(r0)*tanh(rho*s+r0)/rho**2 - w0*sinh(r0)/rho**2
            ws = w0*cosh(r0)/cosh(rho*s+r0)
            theta =  ii*drot+rot0
            dw = QtCore.QPointF(cos(theta)/2.0,-sin(theta)/2.0)*ws

            tmpcentre = c0+uvector*us
            tmplp = tmpcentre-dw
            tmprp = tmpcentre+dw

            self.viewsteps.append({'left':(tmplp.x(),tmplp.y()), 'right':(tmprp.x(),tmprp.y())})

        self.viewsteps.append({'left':(lp1.x(),lp1.y()), 'right':(rp1.x(),rp1.y())})
        self.viewcurrentstep = 0

        self.viewtimer = QtCore.QTimer()
        self.viewtimer.timeout.connect(self.timedView)
        self.viewtimer.start(dt)


        self.views.viewsListView.clearSelection()
        # TODO fix selection
        # self.views.viewsListView.setCurrentIndex(viewitem.index())

    def timedView(self):

        if self.viewcurrentstep > len(self.viewsteps)-1:
            self.viewtimer.stop()
        else:
            sides = self.viewsteps[self.viewcurrentstep]
            self.view.setViewSides(sides)
            self.viewcurrentstep += 1


    def setMode(self):

        # The current checked status of the action is the new state after button presses etc
        if self.presentationModeAct.isChecked():
            self.setPresentationMode()

        elif self.recordModeAct.isChecked():
            self.setRecordingMode()

        else:
            self.setEditingMode()

    def setEditingMode(self):
        self.scene.presentation = False
        self.scene.mode = "edit"
        # self.presentationModeAct.setChecked(False)
        logging.debug("Switching on edit mode")

        # TODO Need to store geometry of window on first use
        # show Normal seems too abrupt after full screen
        # Seems to not store maximised state on a mac?
        self.showNormal()
        #self.showMaximized()

        self.view.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.view.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.viewToolBar.setVisible(True)
        self.recToolBar.setVisible(False)
        self.statusBar().setVisible(True)

        self.menuBar().setVisible(True)

        self.recMenu.setEnabled(False)
        self.editToolBar.setVisible(True)
        self.fileToolBar.setVisible(True)
        self.filterToolBar.setVisible(True)
        self.modeToolBar.setVisible(True)

        for child in self.presentationhiddenstems:
            child.show()
        self.presentationhiddenstems = []

        #self.view.centerOn(center)
        self.hidePointerAct.setChecked(True) # force toggle off
        self.hidePointerAct.trigger()
        self.hidePointerAct.setEnabled(False)
        QtWidgets.QApplication.instance().restoreOverrideCursor()

        self.viewsNextAct.setShortcut(QtGui.QKeySequence())
        self.viewsPreviousAct.setShortcut(QtGui.QKeySequence())
        self.viewsHomeAct.setShortcut(QtGui.QKeySequence())
        self.presentationModeAct.setShortcut(QtGui.QKeySequence())
        self.viewsFirstAct.setShortcut(QtGui.QKeySequence())
        self.hidePointerAct.setShortcut(QtGui.QKeySequence())

    def setPresentationMode(self):

        self.scene.mode = "presentation"
        logging.debug("Switching on presentation mode")

        self.statusBar().setVisible(False)
        self.menuBar().setVisible(False)
        self.editToolBar.setVisible(False)
        self.fileToolBar.setVisible(False)
        self.filterToolBar.setVisible(False)
        self.viewToolBar.setVisible(False)
        self.recToolBar.setVisible(False)
        self.modeToolBar.setVisible(False)
        self.scene.clearSelection()

        if self.viewsFramesAct.isChecked():
            self.viewsFramesAct.trigger()

        self.presentationhiddenstems = []
        for child in self.scene.allChildStems(includeroot=False):
            if 'hide' in child.getTags() and child.isVisible():
                child.hide()
                self.presentationhiddenstems.append(child)

        # this seems to throw off the view snaps:
        self.view.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)

        self.showFullScreen()

        #self.view.centerOn(center)
        self.hidePointerAct.setEnabled(True)
        self.hidePointerAct.setChecked(False) # force toggle on
        self.hidePointerAct.trigger()

        # (Use shift to actually move canvas)
        self.viewsNextAct.setShortcuts(CONFIG['view_next_keys'])
        self.viewsPreviousAct.setShortcuts(CONFIG['view_prev_keys'])
        self.viewsHomeAct.setShortcuts(CONFIG['view_home_keys'])
        self.viewsFirstAct.setShortcuts(CONFIG['view_first_keys'])
        self.hidePointerAct.setShortcuts(CONFIG['view_pointer_keys'])

        self.editModeAct.setShortcut("Esc")

    def setRecordingMode(self):

        self.scene.mode = "record"
        logging.debug("Switching on record mode")

        self.recToolBar.setVisible(True)
        self.editToolBar.setVisible(False)
        self.fileToolBar.setVisible(False)
        self.filterToolBar.setVisible(False)
        self.modeToolBar.setVisible(False)

        self.recMenu.setEnabled(True)

        self.scene.clearSelection()

        if self.viewsFramesAct.isChecked():
            self.viewsFramesAct.trigger()

        self.presentationhiddenstems = []
        for child in self.scene.allChildStems(includeroot=False):
            if 'hide' in child.getTags() and child.isVisible():
                child.hide()
                self.presentationhiddenstems.append(child)

        self.showMaximized()

        #self.view.centerOn(center)
        self.hidePointerAct.setEnabled(True)
        self.hidePointerAct.setChecked(True) # force toggle on
        self.hidePointerAct.trigger()

        # (Use shift to actually move canvas)
        self.viewsNextAct.setShortcuts(CONFIG['view_next_keys'])
        self.viewsPreviousAct.setShortcuts(CONFIG['view_prev_keys'])
        self.viewsHomeAct.setShortcuts(CONFIG['view_home_keys'])
        self.viewsFirstAct.setShortcuts(CONFIG['view_first_keys'])
        self.hidePointerAct.setShortcuts(CONFIG['view_pointer_keys'])

        self.editModeAct.setShortcut("Esc")

        #
        # Recording setup
        #
        #self.audio = pyaudio.PyAudio()
        ## list of input devices
        # info = self.audio.get_host_api_info_by_index(0)
        # numdevices = info.get('deviceCount')
        # devices = []
        # for i in range(0, numdevices):
        #     if (self.audio.get_device_info_by_host_api_device_index(0, i).get('maxInputChannels')) > 0:
        #         devices.append(self.audio.get_device_info_by_host_api_device_index(0, i).get('name'))
        self.audiorecorder = QAudioRecorder()

        codecs = self.audiorecorder.supportedAudioCodecs()
        containers = self.audiorecorder.supportedContainers()
        sample_rates = self.audiorecorder.supportedAudioSampleRates()
        sources = self.audiorecorder.audioInputs()
        default_source = self.audiorecorder.defaultAudioInput()
        sources.remove(default_source)
        sources.insert(0, default_source)
        self.recSourceCombo.clear()
        self.recSourceCombo.addItems(sources)
        self.recSourceCombo.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLength)

        settings = QAudioEncoderSettings()
        settings.setCodec('audio/pcm')
        settings.setSampleRate(44100)
        settings.setChannelCount(2)

        self.audiorecorder.setAudioSettings(settings)
        self.audiorecorder.setContainerFormat('audio/x-wav')

        self.recStartAct.setEnabled(True)
        self.recPauseAct.setEnabled(False)
        self.recEndAct.setEnabled(False)

        self.audiorecorder.stateChanged.connect(self.audioRecorderStateChange)
        self.audioRecorderStateChange()

    def storeRecordingEvent(self, event):
        self.event_stream.append(event)

    def audioRecorderStateChange(self):

        if self.audiorecorder.state()==QAudioRecorder.RecordingState:
            print("Recording")
        elif self.audiorecorder.state()==QAudioRecorder.PausedState:
            print("Paused")
        else:
            print("Stopped")

    def recordStart(self):

        if self.audiorecorder.state()==QAudioRecorder.StoppedState:
            # This is the initial state of the recorder
           
            # create a temporary directory to store files for movie
            self.tmprecdir = Path(tempfile.mkdtemp(prefix="movie_components_", dir=Path.cwd()))

            logging.info("Created temporary directory %s for movie", self.tmprecdir)
            url = QtCore.QUrl("{}/audio.wav".format(self.tmprecdir))
            self.audiorecorder.setOutputLocation(url)
            self.audiorecorder.setAudioInput(self.recSourceCombo.currentText())

            # initialise stream
            self.event_stream = []

        # The following applies for initial start and resuming from pause
        self.view.recordStateEvent.connect(self.storeRecordingEvent)
        self.audiorecorder.record()
        t = time.time()
        sides = self.view.getViewSides()
                                
        self.event_stream.append({'t':t,'cmd':'start'})
        self.event_stream.append({'t':t,'cmd':'view', 'left':sides['left'], 'right':sides['right']})

        self.recStartAct.setChecked(True)
        self.recPauseAct.setChecked(False)
        self.recEndAct.setChecked(False)
        self.recStartAct.setEnabled(False)
        self.recPauseAct.setEnabled(True)
        self.recEndAct.setEnabled(True)


    def recordPause(self):
        self.audiorecorder.pause()
        self.event_stream.append({'t':time.time(),'cmd':'pause'})
        self.view.recordStateEvent.disconnect(self.storeRecordingEvent)


        self.recStartAct.setChecked(False)
        self.recPauseAct.setChecked(True)
        self.recEndAct.setChecked(False)
        self.recStartAct.setEnabled(True)
        self.recPauseAct.setEnabled(False)
        self.recEndAct.setEnabled(True)

    def recordEnd(self):
        self.audiorecorder.stop()
        self.event_stream.append({'t':time.time(),'cmd':'end'})
        try:
            self.view.recordStateEvent.disconnect(self.storeRecordingEvent)
        except TypeError:
            # may have stopped from pause, in which case not connected
            pass
        logging.info("recording ended")

        self.recStartAct.setChecked(False)
        self.recPauseAct.setChecked(False)
        self.recEndAct.setChecked(True)
        self.recStartAct.setEnabled(True)
        self.recPauseAct.setEnabled(False)
        self.recEndAct.setEnabled(False)


        # Sort event_stream just to be safe
        self.event_stream.sort(key = lambda x:x['t'])

        # Generate frames
        fp = (self.tmprecdir/"timing.txt").open("w")
        F = 1
        currentview = {}
        currentpen = [[]]
        N = len(self.event_stream)
        # extra time accumulated on skipping frames:
        skipped = 0

        # this is a mirror of code in graphics
        # I know, I know, don't duplicate, abstract
        # outer colour
        self.pointertrailitem = QtWidgets.QGraphicsPathItem(QtGui.QPainterPath())
        self.pointertrailitem.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations, True)
        pen = QtGui.QPen(QtGui.QColor(CONFIG['trail_outer_color']))
        pen.setWidthF(CONFIG['trail_outer_width'])
        pen.setCapStyle(QtCore.Qt.RoundCap)
        self.pointertrailitem.setPen(pen)
        self.pointertrailitem.setGraphicsEffect(QtWidgets.QGraphicsBlurEffect())
        self.scene.addItem(self.pointertrailitem)

        # inner colour
        self.pointertrailitem2 = QtWidgets.QGraphicsPathItem(QtGui.QPainterPath())
        self.pointertrailitem2.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations, True)
        pen = QtGui.QPen(QtGui.QColor(CONFIG['trail_inner_color']))
        pen.setWidthF(CONFIG['trail_inner_width'])
        pen.setCapStyle(QtCore.Qt.RoundCap)
        self.pointertrailitem2.setPen(pen)
        self.pointertrailitem2.setGraphicsEffect(QtWidgets.QGraphicsBlurEffect())
        self.scene.addItem(self.pointertrailitem2)

        progress = QtWidgets.QProgressDialog("Making frames","Cancel",0,120, self)
        progress.setWindowModality(QtCore.Qt.WindowModal)

        for i in range(N):
            if i%1==0:
                print('Writing frames: {:.0f}%'.format(i/N*100))
                progress.setValue(i/N*100)
            e = self.event_stream[i]
            cmd = e['cmd']
            if cmd in ['start','end']:
                continue
            # the following will throw exeption if end frame so skip those above
            dt = self.event_stream[i+1]['t']-e['t']

            if cmd == 'view':
                # XXX needs fix for left and right
                currentview = {'left':e['left'], 'right':e['right']}
            elif cmd=='pen-clear':
                currentpen = [[]]
            elif cmd=='pen-up':
                currentpen.append([])
            elif cmd=='pen-point':
                currentpen[-1].append(QtCore.QPointF(e['x'],e['y']))
                if dt+skipped < 0.0167 and self.event_stream[i+1]['cmd']!='pen-up':
                    #frame faster than 1/60 fps so skip making this one
                    skipped+=dt
                    continue

            # draw frame
            if cmd in ['view','pen-clear', 'pen-up', 'pen-point']:
                framename = 'frame_{:04d}.png'.format(F)
                fp.write('file {}\nduration {}\n'.format(framename,dt+skipped))

                image = self.generateFrame(left=currentview['left'], right=currentpen['right'], penpoints=currentpen)
                image.save((self.tmprecdir/framename).as_posix())

                F+=1
                skipped = 0

        # last frame must be written again or ffmped ignores the duration
        fp.write('file {}\n'.format(framename))
        fp.close()

        self.scene.removeItem(self.pointertrailitem )
        self.scene.removeItem(self.pointertrailitem2 )

        progress.setLabelText("Generating video")
        progress.setValue(100)

        # Generate video
        self.showMessage("Generating video from frames")
        subprocess.run(['ffmpeg', '-f', 'concat',
                        '-i', 'timing.txt',
                        '-vf', 'fps=60', # 60fps
                        '-pix_fmt', 'yuv420p', # so quicktime can play it
                        'video.mp4' ], cwd=self.tmprecdir)

        progress.setLabelText("Combining with audio")
        progress.setValue(110)

        # Combine audio and video
        self.showMessage("Combining video and audio")
        subprocess.run(['ffmpeg', '-i', 'video.mp4',
                        '-itsoffset', '0.5', # delay the audio slightly
                        '-i', 'audio.wav',
                        '-c:v', 'copy',
                        '-c:a', 'aac',
                        'complete.mp4' ], cwd=self.tmprecdir)

        progress.setValue(120)

        filename = QtWidgets.QFileDialog.getSaveFileName(self, "Save Movie File", "output.mp4", "*.mp4")
        if len(filename[0])>0:
            videopath = filename[0]
            vid = self.tmprecdir/"complete.mp4"
            vid.rename(videopath)
        else:
            return

        # TODO cleanup temporary directory unless user indicates not to
        # TODO slight delay on audio recording starting
        # TODO figure out where audio too soon is coming from (delay in starting to record?)
        # TODO needs better feedback
        # TODO probably should be moved to separate thread
        # TODO accomodate changing screens: store central point and width of HD view and addapt dynamically
        
    def generateFrame(self, left, right, penpoints):


        # path = QtGui.QPainterPath()
        # for stroke in penpoints:
        #     if len(stroke)==0:
        #         continue
        #     subpath = QtGui.QPainterPath()
        #     p = stroke[0]
        #     subpath.moveTo(p)
        #     for p in stroke:
        #         subpath.lineTo(p)
        #     # subpath.closeSubpath()
        #     path.addPath(subpath)
        # self.pointertrailitem.setPath(path)
        # self.pointertrailitem2.setPath(path)
        # self.pointertrailitem.update(path.boundingRect())
        # self.pointertrailitem2.update(path.boundingRect())

        # self.view.update()
        # self.pointertrailitem.show()
        # self.pointertrailitem2.show()
        # self.view.setViewportUpdateMode(self.view.FullViewportUpdate)
        # self.view.resetCachedContent()
        
        self.view.setViewSides({'left':left, 'right':right})

        W = 1920
        H = 1080
        viewrect = self.view.viewport().rect()
        dx = (viewrect.width()-W)/2
        dy = (viewrect.height()-H)/2

        image = QtGui.QImage(W,H, QtGui.QImage.Format_ARGB32)
        image.fill(QtCore.Qt.transparent)
        painter = QtGui.QPainter(image)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform, True)
        self.view.render(painter, QtCore.QRectF(), QtCore.QRect(dx,dy,W,H), QtCore.Qt.KeepAspectRatio)

        ## Ideally the pen would be draw here but the transformations are a mess
        ## Needs a complete overhaul to accomodate different res screens anyway
        vc = viewrect.center()
        s = W/(4*viewrect.width())
        c = QtCore.QPointF(W/2,H/2)
        tc = QtCore.QPointF(x,y)
        for stroke in penpoints:
            if len(stroke)==0:
                continue

            #stroke2=[s*(self.view.mapFromScene(QtCore.QPointF(sx,sy))-vp) for sx,sy in stroke]
            stroke2=[s*(self.view.mapFromScene(sp)-vc)+c-2*tc for sp in stroke]
            print(dx,dy, tc, vc)
            #print(stroke2[:3])
            #print(vp,s)
            painter.drawPolyline(QtGui.QPolygonF(stroke2))

        painter.end()


        return image

    def hidePointer(self):
        '''
        Hide and show the pointer in full screen mode
        Change zoom to view center when pointer is hidden and to cursor when pointer is shown
        '''

        if self.hidePointerAct.isChecked():
            QtWidgets.QApplication.instance().restoreOverrideCursor()
            QtWidgets.QApplication.instance().setOverrideCursor(QtCore.Qt.BlankCursor)
            #self.view.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorViewCenter)
        else:
            QtWidgets.QApplication.instance().restoreOverrideCursor() # restore first so default in in the stack
            s=CONFIG['trail_outer_width']*CONFIG['trail_pointer_factor']
            pix = QtGui.QPixmap(s, s)
            rg = QtGui.QRadialGradient(s/2,s/2,s/2, s/2, s/2, CONFIG['trail_inner_width']/2)
            rg.setColorAt(0, QtGui.QColor(CONFIG['trail_inner_color']))
            rg.setColorAt(1, QtGui.QColor(CONFIG['trail_outer_color']))
            pix.fill(QtCore.Qt.transparent)
            painter = QtGui.QPainter(pix)
            painter.setBrush(QtGui.QBrush(rg))
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawEllipse(0,0,s,s)
            painter.end()
            QtWidgets.QApplication.instance().setOverrideCursor(QtGui.QCursor(pix, -s/2,-s/2))
            #self.view.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)


    def viewsNext(self):
        """
        Go to next view in the list
        """
        self.views.viewsModel.athome = None
        self.jumpToView(self.views.viewsModel.nextView())

    def viewsPrevious(self):
        """
        Go to previous view in the list
        """
        self.views.viewsModel.athome = None
        self.jumpToView(self.views.viewsModel.previousView())

    def viewsHome(self):
        """
        Toggle the home view
        """

        if self.viewsModel.athome is None:
            # store where we are and switch to homeview
            self.views.viewsModel.athome = self.viewsModel.currentView()
            self.jumpToView(self.views.viewsModel.homeView())

        else:
            # We are on homeview .. go back
            self.jumpToView(self.views.viewsModel.athome)
            self.views.viewsModel.athome = None

    def viewsFirst(self):
        """
        Go to first view
        """
        self.jumpToView(self.views.viewsModel.firstView())

    def viewsFrames(self):
        """
        Toggle showing view frames
        """

        if self.viewsFramesAct.isChecked():
            vis = True
        else:
            vis = False

        selecteditems = []
        selected = self.views.viewsListView.selectedIndexes()
        for s in selected:
            selecteditems.append(self.views.viewsModel.itemFromIndex(s))
        print(selecteditems)

        for item in self.views.viewsModel.views:
            if vis and item in selecteditems:
                item['rect'].setVisible(vis)
            else:
                item['rect'].setVisible(False)



class FilterEdit(QtWidgets.QLineEdit):

    runfilter = QtCore.pyqtSignal(str)

    def __init__(self, *args):
        super().__init__(*args)
        self.editingFinished.connect(self.editingFinished2)
        self.setToolTip("all() / find(title=re,tag=re) / selected() / tagged(re)")


    def editingFinished2(self):
        '''
        This is a second pathway to the function so we can pass the text
        '''
        self.runfilter.emit(str(self.text()))



class RecordDialog(QtWidgets.QDialog):


    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.setWindowTitle("Record")
        #self.setWindowFlags(QtCore.Qt.WindowStaysOnTopHint)

        self.audiorecorder = QAudioRecorder()

        codecs = self.audiorecorder.supportedAudioCodecs()
        containers = self.audiorecorder.supportedContainers()
        sample_rates = self.audiorecorder.supportedAudioSampleRates()


        #self.setWindowOpacity(0.6)

        QBtn = QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel

        self.buttonBox = QtWidgets.QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)

        #self.audio = pyaudio.PyAudio()

        #
        # list of input devices
        #
        # info = self.audio.get_host_api_info_by_index(0)
        # numdevices = info.get('deviceCount')
        # devices = []
        # for i in range(0, numdevices):
        #     if (self.audio.get_device_info_by_host_api_device_index(0, i).get('maxInputChannels')) > 0:
        #         devices.append(self.audio.get_device_info_by_host_api_device_index(0, i).get('name'))

        sources = self.audiorecorder.audioInputs()
        print(sources)
        default_source = self.audiorecorder.defaultAudioInput()
        sources.remove(default_source)
        sources.insert(0, default_source)
        self.sources = QtWidgets.QComboBox()
        self.sources.addItems(sources)
        self.sources.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLength)
        self.sources.setMinimumContentsLength(6)

        #
        # Levels
        #
        self.levels = QtWidgets.QLabel("? ?")

        #
        # output file name
        #
        self.outputfilename = QtWidgets.QLineEdit("output.wav")

        #
        # Record button
        #
        self.recordbutton = QtWidgets.QPushButton("Record")
        # self.recordbutton.setCheckable(True)
        self.recordbutton.setMinimumSize(100,100)
        self.recordbutton.clicked.connect(self.recordPushed)

        form = QtWidgets.QFormLayout()
        form.addRow("Source:", self.sources)
        form.addRow("Levels:", self.levels)
        form.addRow("Output:", self.outputfilename )

        self.layout = QtWidgets.QVBoxLayout()
        self.layout.addLayout(form)
        self.layout.addWidget(self.recordbutton)
        self.layout.addWidget(self.buttonBox)
        self.setLayout(self.layout)

        self.audiorecorder.stateChanged.connect(self.onStateChange)
        self.onStateChange()

    def onStateChange(self):

        if self.audiorecorder.state()==QAudioRecorder.StoppedState:
            self.recordbutton.setStyleSheet("background-color: #400000;")
            self.recordbutton.setText('Off')
        elif self.audiorecorder.state()==QAudioRecorder.RecordingState:
            self.recordbutton.setStyleSheet("background-color: #A00000;")
            self.recordbutton.setText('Recording')
        else:
            self.recordbutton.setStyleSheet("background-color: #900000;")
            self.recordbutton.setText('Paused')

    def recordPushed(self):

        # TODO on record pass keypresses to main window
        # TODO or implement as toolbar
        if self.audiorecorder.state()==QAudioRecorder.StoppedState:
            self.setSettings()

            self.audiorecorder.record()
        elif self.audiorecorder.state()==QAudioRecorder.RecordingState:
            pass
            self.audiorecorder.pause()
        else:
            pass
            self.audiorecorder.record()

    def setSettings(self):
        settings = QAudioEncoderSettings()
        settings.setCodec('audio/pcm')
        settings.setSampleRate(44100)
        settings.setChannelCount(2)
        self.audiorecorder.setAudioSettings(settings)
        self.audiorecorder.setContainerFormat('audio/x-wav')
        self.audiorecorder.setOutputLocation(QtCore.QUrl('output.wav'))
        self.audiorecorder.setAudioInput(self.sources.currentText())

    def accept(self):

        # save audio
        self.audiorecorder.stop()

        # TODO generate frames

        # TODO generate video

        # TODO combine audio and video
       
        print('accept()')

    def reject(self):
        # Cancel / close window / escape
        print('reject()')
        self.audiorecorder.stop()

        # TODO escape from recording mode on main window

        super().reject()

class PreferencesDialog(QtWidgets.QDialog):
    '''
    Main preferences dialog
    '''

    # TODO allow abritrary URL prefixes to be mapped to commands
    # TODO default font
    # TODO default branch parameters
    pass

class ViewsModel(QtCore.QAbstractListModel):
    current = 0
    home = 0 # home is the first view by default
    athome = None  # the location of the previous view will be stored here on switch
    
    def __init__(self):
        super().__init__()
        self.views = []

    def data(self, index, role):
        if role == QtCore.Qt.DecorationRole:
            # See below for the data structure.
            v = self.views[index.row()]
            # Return the todo text only.
            return v['_icon']

    def rowCount(self, index):
        return len(self.views)

    def addRow(self, item, after=-1):
        if after==-1:
            self.views.append(item)
        else:
            self.views.insert(after+1, item)
        self.layoutChanged.emit()

    def itemFromIndex(self, index):
        return self.views[index.row()]
       
    def _cleanlimits(self,  viewnumber):
        '''
        clamp limits for requested view number
        so can always request next or previous
        '''
        return max(min(viewnumber, len(self.views)-1), 0)

    def currentView(self):
        '''
        Return current view in presentation
        '''
        return self.views[self.current]

    def firstView(self):
        '''
        reset view to first one
        '''
        self.current = 0
        return self.currentView()

    def setCurrentView(self,  viewnumber):
        '''
        Set current view for presentations
        '''
        self.current = self._cleanlimits(viewnumber)

    def nextView(self):

        self.current = self._cleanlimits(self.current+1)
        return self.currentView()

    def previousView(self):

        self.current = self._cleanlimits(self.current-1)
        return self.currentView()

    def homeView(self):
        '''
        Return special "home" view slide
        '''
        return self.views[self.home]

    def setHomeView(self,  viewnumber):
        self.home = self._cleanlimits(viewnumber)

class ViewsModelold(QtGui.QStandardItemModel):

    current = 0
    home = 0 # home is the first view by default
    athome = None  # the location of the previous view will be stored here on switch

    reordered = QtCore.pyqtSignal()

    def _cleanlimits(self,  viewnumber):
        '''
        clean up limits for requested view number
        '''
        # NB if no items maxview will be -1
        maxview = self.rowCount()-1
        return max(min(viewnumber, maxview), 0)

    def currentView(self):
        '''
        Return current view in presentation
        '''
        return self.item(self.current)

    def firstView(self):
        '''
        reset view to first one
        '''
        self.current = 0
        return self.currentView()

    def setCurrentView(self,  viewnumber):
        '''
        Set current view for presentations
        '''
        self.current = self._cleanlimits(viewnumber)

    def nextView(self):

        self.current = self._cleanlimits(self.current+1)
        return self.currentView()

    def previousView(self):

        self.current = self._cleanlimits(self.current-1)
        return self.currentView()

    def homeView(self):
        '''
        Return special "home" view slide
        '''
        return self.item(self.home)

    def setHomeView(self,  viewnumber):
        self.home = self._cleanlimits(viewnumber)

    def dropMimeData(self, data, action, targetrow, targetcolumn, parent ):

        if data.hasFormat('application/x-qabstractitemmodeldatalist'):
            bytearray = data.data('application/x-qabstractitemmodeldatalist')
            ds = QtCore.QDataStream(bytearray)

            ## parse the internal drag and drop format to find the source items
            ## we just need the rows
            rows = []
            while not ds.atEnd():
                row = ds.readInt32()
                rows.append(row)
                column = ds.readInt32()
                map_items = ds.readInt32()
                for i in range(map_items):
                    key = ds.readInt32()
                    value = ds.readQVariant()

            ## rows will be in the order of the selection ... keep them in list order
            rows.sort()

            ## grab a row independent reference to each item
            sourceitems = []
            for row in rows:
                sourceitems.append( self.item(row ) )

            ## insert marker so we keep track of where to add items
            if targetrow == -1:
                targetrow = self.rowCount()
            #target = ViewsItem(scene=self.scene)
            target = QtGui.QStandardItem()
            self.insertRow(targetrow, target)

            ## move items to new home
            for item in sourceitems:
                tmp = self.takeRow( item.row() )
                self.insertRow(target.row(), tmp)

            ## remove marker
            self.takeRow( target.row() )
            self.reordered.emit()

            return True

        else:
            return False

class ViewsItem(QtGui.QStandardItem):

    ICONMAXSIZE = 300

    def __init__(self, node, scene=None):
        super().__init__()
        self.node = node

        self.setDropEnabled(False)
        # self.viewRectItem = None
        rectitem = ViewRectangle(self)
        scene.addItem(rectitem)
        self.viewRectItem = rectitem

        # set the transformation on the viewRectItem
        T = graphics.Transform(*self.node['transform'])
        self.viewRectItem.setTransform(T)
        self.viewRectItem.setVisible(False)

    def setView(self, view):

        invmatrix = view.transform()
        matrix = invmatrix.inverted()[0]
        centrePoint = view.mapToScene(view.viewport().rect().center())

        # XXX store centre, scale, and rotation
        dx,dy,r,s = graphics.Transform(matrix).getTRS()
        matrix = graphics.Transform().setTRS(centrePoint.x(),centrePoint.y(),r,s)
        self.viewRectItem.setTransform(matrix)

        self.saveView()
        self.createPreview(view)

    def saveView(self):
        self.node['transform'] = self.viewTransform().tolist()
        self.node.save(setchange=False)

    def createPreview(self, view=None, icon=None):

        if view is None:
            # try and get view from viewrectItem
            # XXX how to get right view?
            view = self.viewRectItem.scene().views()[0]


        if icon is None:
            # take a snapshot of the view

            # temporarily deselect selected items
            selected = self.viewRectItem.scene().selectedItems()
            for item in selected:
                item.setSelected(False)

            # remember the visibility of viewrect and hide it
            # XXX need to hide them all
            vis = self.viewRectItem.isVisible()
            self.viewRectItem.hide()

            # remember current view
            matrix0 = view.transform()
            center0 = view.mapToScene(view.viewport().rect().center())

            # set view to viewRectItem's view
            matrix = self.viewInverseTransform()
            center = self.viewCentre()
            view.setTransform(matrix)
            view.centerOn(center)

            # generate pixmap
            pixmap = view.grab()
            pixmap = pixmap.scaled( self.ICONMAXSIZE, self.ICONMAXSIZE, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)

            # restore view
            view.setTransform(matrix0)
            view.centerOn(center0)

            icon = QtGui.QIcon(pixmap)

            # restore visibility
            self.viewRectItem.setVisible(vis)

            # restore selected state
            for item in selected:
                item.setSelected(True)

        self.setIcon(icon)

    def viewTransform(self):
        return graphics.Transform(self.viewRectItem.sceneTransform())

    def viewInverseTransform(self):
        ## convenience function
        return graphics.Transform(self.viewRectItem.sceneTransform().inverted()[0])

    def viewCentre(self):
        ## convenience function (point contained in sceneTransform())
        return self.viewRectItem.scenePos()


#----------------------------------------------------------------------
class ViewRectangle(QtWidgets.QGraphicsPathItem):
    '''
    Scene widget to indicate a View
    '''

    # viewChanged = QtCore.pyqtSignal()

    def __init__(self, viewItem):

        self.viewitem = viewItem

        self.VIEWW, self.VIEWH = CONFIG['view_rect_size']

        path = QtGui.QPainterPath()
        rect = QtCore.QRectF(-self.VIEWW/2.0,-self.VIEWH/2.0,self.VIEWW,self.VIEWH)
        path.addRect(rect)
        super().__init__(path)

        self.setPen(QtGui.QPen(QtCore.Qt.darkRed, 5))
        self.setBrush(QtGui.QBrush(QtGui.QColor(100,100,100,60)))
        self.setFlag(self.ItemIsMovable, True)
        self.setCursor(QtCore.Qt.SizeAllCursor)
        #self.setFlag(self.ItemIsSelectable, True)

        ViewRectangleHandle("tNE", self)
        ViewRectangleHandle("tSE", self)
        ViewRectangleHandle("tSW", self)
        ViewRectangleHandle("tNW", self)

        ViewRectangleDirection(self)
        
    def mousePressEvent(self, event):

        QtWidgets.QGraphicsItem.mousePressEvent(self, event)
        if not hasattr(event,"source"):
            return


        for item in self.scene().selectedItems():
            item.setSelected(False)

        self.mousePressPos = event.scenePos()
        self.originalTransform = self.transform()

        rect = self.boundingRect()
        if event.modifiers() & QtCore.Qt.AltModifier:
            self.pivot = QtCore.QPointF(0,0)

        elif event.source == "tNE":
            self.pivot = QtCore.QPointF(-self.VIEWW/2.0,self.VIEWH/2.0)

        elif event.source == "tNW":
            self.pivot = QtCore.QPointF(self.VIEWW/2.0,self.VIEWH/2.0)

        elif event.source == "tSW":
            self.pivot = QtCore.QPointF(self.VIEWW/2.0,-self.VIEWH/2.0)

        elif event.source == "tSE":
            self.pivot = QtCore.QPointF(-self.VIEWW/2.0,-self.VIEWH/2.0)

        else:
            self.pivot = QtCore.QPointF(0,0)


        QtWidgets.QGraphicsItem.mousePressEvent(self, event)

    def mouseMoveEvent(self, event):

        if not hasattr(event,"sourceId"):
            ## this is for plain moves
            super().mouseMoveEvent(event)
            return

        p0 = self.mapFromScene(self.mousePressPos)
        p1 = self.mapFromScene(event.scenePos())

        pv = self.pivot

        transform = QtGui.QTransform(self.originalTransform)
        if p0.x()-pv.x() == 0:
            kx = 0.0
        else:
            kx = (p1.x()-pv.x())/(p0.x()-pv.x())

        if p0.y()-pv.y() == 0:
            ky = 0.0
        else:
            ky = (p1.y()-pv.y())/(p0.y()-pv.y())

        k = min(kx,ky)

        transform.translate(pv.x(),pv.y())
        transform.scale(k,k)
        transform.translate(-pv.x(),-pv.y())
        self.setTransform(transform)

        event.accept()

    def mouseReleaseEvent(self, event):

        QtWidgets.QGraphicsItem.mouseReleaseEvent(self, event)

        self.viewitem.saveView()
        self.viewitem.createPreview()


#----------------------------------------------------------------------
class ViewRectangleHandle(QtWidgets.QGraphicsRectItem):
    '''
    Widget to control size of view rectangle

    Just delegates action to parent (ViewRectangle)
    '''

    def __init__(self, id, parent):

        self.id = id
        W = 200

        if id=='tNE':
            X,Y = parent.VIEWW/2.0-W, -parent.VIEWH/2.0
        elif id=='tSE':
            X,Y = parent.VIEWW/2.0-W, parent.VIEWH/2.0-W
        elif id=='tSW':
            X,Y = -parent.VIEWW/2.0, parent.VIEWH/2.0-W
        else:
            X,Y = -parent.VIEWW/2.0, -parent.VIEWH/2.0

        super().__init__(X, Y, W, W, parent)

    def mousePressEvent(self, event):
        self.mousePressScreenPos = event.screenPos()
        self.mousePressTime = time.time()

        event.sourceId = self.id
        self.parentItem().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        event.sourceId = self.id
        self.parentItem().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        event.sourceId = self.id
        self.parentItem().mouseReleaseEvent(event)


class ViewRectangleDirection(QtWidgets.QGraphicsPathItem):
    """
    Graphic to indicate up direction on a view frame
    """
    def __init__(self, parent):
        apath=QtGui.QPainterPath()
        apath.moveTo(0, -40)
        apath.lineTo(40, 0)
        apath.lineTo(20, 0)
        apath.lineTo(20, 40)
        apath.lineTo(-20, 40)
        apath.lineTo(-20, 0)
        apath.lineTo(-40, 0)
        apath.lineTo(0, -40)

        super().__init__(apath, parent)
        self.setPen(QtGui.QPen(QtCore.Qt.black, 0))
        self.setBrush(QtGui.QBrush(QtGui.QColor(100,100,100,50)))

        self.setScale(5)


class ViewsListView(QtWidgets.QListView):

    Horizontal = 0
    Vertical = 1
    orientation = Vertical

    selectionChange = QtCore.pyqtSignal()

    def __init__(self):
        super().__init__()

        self.setViewMode(self.ListMode)
        self.setWrapping(False)
        self.setFlow(QtWidgets.QListView.TopToBottom)
        self.setMovement(self.Snap)
        self.setResizeMode( self.Adjust )
        self.setSelectionRectVisible( True )
        self.setSelectionMode( self.ExtendedSelection )
        self.setSpacing(0)
        self.setVerticalScrollMode(self.ScrollPerPixel)
        self.setHorizontalScrollMode(self.ScrollPerPixel)

        # NOTE: the dragDropMode must be set AFTER the viewMode!!!
        self.setDragDropMode( self.InternalMove )


    def resizeEvent(self, event):

        super(ViewsListView, self).resizeEvent(event)
        self.setViewIconSize()

    def setViewIconSize(self):
        if self.orientation == self.Vertical:
            size = self.size().width()
        else:
            size = self.size().height()
        self.setIconSize(QtCore.QSize(size-12,size-12))

    def resetOrientation(self):

        if self.orientation == self.Vertical:
            self.setFlow(self.TopToBottom)
        else:
            self.setFlow(self.LeftToRight)

        self.setViewIconSize()

    def selectionChanged(self,  selected,  deselected):
        QtWidgets.QListView.selectionChanged(self, selected, deselected)
        self.selectionChange.emit()


#----------------------------------------------------------------------
class ViewsWidget(QtWidgets.QWidget):

    ICONMAXSIZE = 300

    def __init__(self, parent, toolbar):
        super().__init__(parent)

        self.view = parent.view
        self.scene = parent.scene
        self.viewsModel = ViewsModel()


        self.toolbar = toolbar

        ## create main layout
        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        ## create listview
        self.viewsListView = ViewsListView()
        self.viewsListView.setModel(self.viewsModel)
        self.viewsListView.doubleClicked.connect(self.doubleClicked)
        #self.viewsModel.reordered.connect(self.relinkViews)
        #self.views.viewsListView.selectionChange.connect(self.viewsFrames)
        layout.addWidget(self.viewsListView)

        ## create actions
        self.resetViewAct = QtWidgets.QAction(QtGui.QIcon(":/images/view-reset.svg"), self.tr("&Reset View"), self)
        self.resetViewAct.setStatusTip(self.tr("Reset item to current view"))
        self.resetViewAct.triggered.connect(self.resetView)

        self.addViewAct = QtWidgets.QAction(QtGui.QIcon(":/images/view-add.svg"), self.tr("&Add View"), self)
        self.addViewAct.setStatusTip(self.tr("Add new View"))
        self.addViewAct.triggered.connect(self.addCurrentView)

        self.deleteViewAct = QtWidgets.QAction(QtGui.QIcon(":/images/view-remove.svg"), self.tr("&Delete View"), self)
        self.deleteViewAct.setStatusTip(self.tr("Delete selected View"))
        self.deleteViewAct.triggered.connect(self.deleteView)

        ## create toolbar
        self.toolbar.setIconSize(QtCore.QSize(20,20))
        self.toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonIconOnly)

        self.toolbar.addAction(self.addViewAct)
        self.toolbar.addAction(self.resetViewAct)
        self.toolbar.addAction(self.deleteViewAct)


        g = self.scene.graph

        # load the chain of views from the graphdb
        views = g.fetch('[n:View]')

        # first view found without an incomming transition is the rootview
        rootviews = []
        for view in views:
            if len(view.inE('e.kind = "Transition"')) == 0:
                rootviews.append(view)


        # check for orphaned views
        if len(rootviews) == 0:
            viewnode = None
        else:
            logging.warn("Found multiple root views, choosing one, deleting rest.")
            # find first with outgoing Transition or take last
            for view in rootviews:
                if len(view.outE('e.kind = "Transition"'))>0:
                    viewnode = view
                    break
                else:
                    viewnode = view
            # remove unused ones
            for view in rootviews:
                if view != viewnode:
                    view.delete(setchange=False)

        # while viewnode is not None:
        #     item = ViewsItem(viewnode, scene=self.scene)
        #     #item.fromxml(viewxml, self.view)
        #     self.viewsModel.appendRow(item)
        #     item.createPreview(view=self.view)

        #     viewnode = viewnode.outN('e.kind = "Transition"').one


    def locationChanged(self, loc):
        '''
        Where this widget is docked has changed ... adjust flow accordingly
        '''

        if loc in [QtCore.Qt.NoDockWidgetArea]:
            pass
        elif loc in [QtCore.Qt.TopDockWidgetArea, QtCore.Qt.BottomDockWidgetArea]:
            self.viewsListView.orientation = self.viewsListView.Horizontal
        else:
            self.viewsListView.orientation = self.viewsListView.Vertical

        self.viewsListView.resetOrientation()

    def doubleClicked(self,  itemindex):
        node = self.viewsModel.itemFromIndex(itemindex)

        self.view.setViewSides({k: node[k] for k in ('left','right')})

        self.viewsModel.athome = False
        self.viewsModel.current = itemindex.row()

    def addCurrentView(self):
        '''
        Add the current view as a Views item
        '''
        data = self.view.getViewSides()

        node = self.scene.graph.Node('View')
        node['left'] = data['left']
        node['right'] = data['right']
        # node.save(setchange=False)

        self.addView(node)

    def addView(self, node):

        rectitem = ViewRectangle(self.scene)
        self.scene.addItem(rectitem)
        node['_rect'] = rectitem
        #self.viewRectItem = rectitem

        # TODO fix view rect
        # set the transformation on the viewRectItem
        #T = graphics.Transform(*self.node['transform'])
        # XXX T = graphics.Transform().setTRS(node['x'], node['y'], node['r'], node['s'])
        # XXX rectitem.setTransform(T)
        rectitem.setVisible(False)

        # self.saveView()
        icon = self.createPreview({k: node[k] for k in ('left','right')})
        node['_icon'] = icon

        # TODO save view to graph
        # if not self.window().viewsFramesAct.isChecked():
        #     item.viewRectItem.setVisible(False)

        selected = self.viewsListView.selectedIndexes()
        if len(selected) == 0:
            self.viewsModel.addRow(node)
        else:
            row=0
            for itemindex in selected:
                row = max(row, itemindex.row())

            self.viewsModel.addRow(node, row)


        self.relinkViews()

        self.viewsListView.clearSelection()
        # self.viewsListView.setCurrentIndex(0)
        # TODO update selection
       

    def createPreview(self, node):

        # temporarily deselect selected items
        selected = self.scene.selectedItems()
        for item in selected:
            item.setSelected(False)

        # remember the visibility of viewrect and hide it
        # XXX need to hide them all
        #vis = self.viewRectItem.isVisible()
        #self.viewRectItem.hide()

        # remember current view
        sides = self.view.getViewSides()

        # set view to viewRectItem's view
        self.view.setViewSides(node)

        # generate pixmap
        # TODO fix the aspect ratio of pixmap to 1080p
        pixmap = self.view.grab()
        pixmap = pixmap.scaled( self.ICONMAXSIZE, self.ICONMAXSIZE, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)

        # restore view
        self.view.setViewSides(sides)

        icon = QtGui.QIcon(pixmap)

        # restore visibility
        # self.viewRectItem.setVisible(vis)

        # restore selected state
        for item in selected:
            item.setSelected(True)

        return icon
       

    def relinkViews(self):
        # ensure all views are daisy chained correctly
        # rows = self.viewsModel.rowCount()
        # if rows == 0:
        #     # Nothing to do
        #     return

        # delete all Transition edges and relink
        # for r in range(rows):
        #     item = self.viewsModel.item(r)
        #     item.node.bothE('e.kind="Transition"').delete(setchange=False)
        # for r in range(1,rows):
        #     item0 = self.viewsModel.item(r-1)
        #     item1 = self.viewsModel.item(r)
        #     self.scene.graph.Edge(item0.node, "Transition", item1.node).save(setchange=False)
        pass
   
    def resetView(self):

        # XXX this should be in NexusView .. only raise a signal here
        # XXX use grabView() code instead and replace item

        itemindex = self.viewsListView.selectedIndexes()[0]
        item = self.viewsModel.itemFromIndex(itemindex)

        item.setView(self.view)

    def deleteView(self):

        itemstodelete = []
        indexes =  self.viewsListView.selectedIndexes()
        rows = [ ii.row() for ii in indexes ]
        rows.sort()

        for itemindex in indexes:
            itemstodelete.append(self.viewsModel.itemFromIndex(itemindex) )
            minindex = max

        for item in itemstodelete:
            item.node.delete(disconnect=True, setchange=False)
            self.scene.removeItem(item.viewRectItem)
            self.viewsModel.removeRow(item.row())

        self.relinkViews()

        if len(rows)>0:
            row = rows[0]-1
            if row >= 0:
                index = self.viewsModel.item(row).index()
                self.viewsListView.scrollTo(index)
                self.viewsListView.setCurrentIndex(index)


#----------------------------------------------------------------------
# Experiment to see if editing window can be a dockwidget
class EditWidget(QtWidgets.QWidget):

    def __init__(self, parent):
        super().__init__(parent)


    def editStem(self, node):
        pass
