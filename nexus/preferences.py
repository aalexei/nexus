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
##
## Originally based on example classes from Qt toolkit, substantially modified

from PyQt5 import QtCore, QtGui, QtWidgets


import logging

class InputPage(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        settings = QtCore.QSettings("Ectropy", "Nexus")

        mainLayout = QtWidgets.QVBoxLayout()
        self.setLayout(mainLayout)

        # ------------------------------
        configGroup = QtWidgets.QGroupBox("General")
        mainLayout.addWidget(configGroup)
        configLayout = QtWidgets.QVBoxLayout()
        configGroup.setLayout(configLayout)

        layout = QtWidgets.QHBoxLayout()
        configLayout.addLayout(layout)
        layout.addWidget(QtWidgets.QLabel("Input panel zoom:"))
        widget=QtWidgets.QSpinBox()
        widget.setToolTip("A slightly larger than normal zoom helps\n match handwriting to text size")
        layout.addWidget(widget)


        # ------------------------------
        configGroup = QtWidgets.QGroupBox("Pen configuration")
        mainLayout.addWidget(configGroup)
        configLayout = QtWidgets.QVBoxLayout()
        configGroup.setLayout(configLayout)

        layout = QtWidgets.QHBoxLayout()
        layout.addWidget(QtWidgets.QLabel("Default pens:"))
        configLayout.addLayout(layout)
        widget=QtWidgets.QSpinBox()
        layout.addWidget(widget)

        layout = QtWidgets.QHBoxLayout()
        layout.addWidget(QtWidgets.QLabel("Background:"))
        configLayout.addLayout(layout)
        widget=QtWidgets.QSpinBox()
        layout.addWidget(widget)

        # ------------------------------
        configGroup = QtWidgets.QGroupBox("Text configuration")
        mainLayout.addWidget(configGroup)
        configLayout = QtWidgets.QVBoxLayout()
        configGroup.setLayout(configLayout)

        layout = QtWidgets.QHBoxLayout()
        layout.addWidget(QtWidgets.QLabel("Default color:"))
        configLayout.addLayout(layout)
        widget=QtWidgets.QSpinBox()
        layout.addWidget(widget)

        layout = QtWidgets.QHBoxLayout()
        layout.addWidget(QtWidgets.QLabel("Default font:"))
        configLayout.addLayout(layout)
        widget=QtWidgets.QSpinBox()
        layout.addWidget(widget)

        mainLayout.addStretch(1)



class NewStemPage(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        settings = QtCore.QSettings("Ectropy", "Nexus")

        mainLayout = QtWidgets.QVBoxLayout()
        self.setLayout(mainLayout)

        # ------------------------------
        configGroup = QtWidgets.QGroupBox("General")
        mainLayout.addWidget(configGroup)
        configLayout = QtWidgets.QVBoxLayout()
        configGroup.setLayout(configLayout)

        layout = QtWidgets.QHBoxLayout()
        configLayout.addLayout(layout)
        layout.addWidget(QtWidgets.QLabel("New stem scale:"))
        widget=QtWidgets.QSpinBox()
        layout.addWidget(widget)

        layout = QtWidgets.QHBoxLayout()
        configLayout.addLayout(layout)
        layout.addWidget(QtWidgets.QLabel("Branch Color:"))
        widget=QtWidgets.QSpinBox()
        layout.addWidget(widget)

        updateGroup = QtWidgets.QGroupBox("Package selection")
        systemCheckBox = QtWidgets.QCheckBox("Update system")
        appsCheckBox = QtWidgets.QCheckBox("Update applications")
        docsCheckBox = QtWidgets.QCheckBox("Update documentation")
#

        startUpdateButton = QtWidgets.QPushButton("Start update")

        updateLayout = QtWidgets.QVBoxLayout()
        updateLayout.addWidget(systemCheckBox)
        updateLayout.addWidget(appsCheckBox)
        updateLayout.addWidget(docsCheckBox)
        updateGroup.setLayout(updateLayout)
#
        #packageLayout = QtGui.QVBoxLayout()
        #packageLayout.addWidget(packageList)
        #packageGroup.setLayout(packageLayout)
##
        ##mainLayout = QtGui.QVBoxLayout()
        #mainLayout.addWidget(updateGroup)
        #mainLayout.addWidget(packageGroup)
        #mainLayout.addSpacing(12)
        #mainLayout.addWidget(startUpdateButton)
        mainLayout.addStretch(1)
#


class HelpersPage(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        settings = QtCore.QSettings("Ectropy", "Nexus")

        mainLayout = QtWidgets.QVBoxLayout()
        self.setLayout(mainLayout)

        # ------------------------------
        configGroup = QtWidgets.QGroupBox("Url protocols")
        mainLayout.addWidget(configGroup)
        configLayout = QtWidgets.QVBoxLayout()
        configGroup.setLayout(configLayout)


        packageList = QtWidgets.QListWidget()
        qtItem = QtWidgets.QListWidgetItem(packageList)
        qtItem.setText("mplayer")
        qsaItem = QtWidgets.QListWidgetItem(packageList)
        qsaItem.setText("gvim")
        teamBuilderItem = QtWidgets.QListWidgetItem(packageList)
        teamBuilderItem.setText("okular")

        configLayout.addWidget(packageList)

        mainLayout.addStretch(1)

        self.setLayout(mainLayout)


class ConfigDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.contentsWidget = QtWidgets.QListWidget()
        self.contentsWidget.setViewMode(QtWidgets.QListView.IconMode)
        self.contentsWidget.setIconSize(QtCore.QSize(96, 84))
        self.contentsWidget.setMovement(QtWidgets.QListView.Static)
        #self.contentsWidget.setMaximumWidth(128)
        self.contentsWidget.setMaximumWidth(144)
        self.contentsWidget.setSpacing(12)

        self.pagesWidget = QtWidgets.QStackedWidget()
        self.pagesWidget.addWidget(InputPage())
        self.pagesWidget.addWidget(NewStemPage())
        self.pagesWidget.addWidget(HelpersPage())

        closeButton = QtWidgets.QPushButton("Close")

        self.createIcons()
        self.contentsWidget.setCurrentRow(0)

        closeButton.clicked.connect(self.close)

        horizontalLayout = QtWidgets.QHBoxLayout()
        horizontalLayout.addWidget(self.contentsWidget)
        horizontalLayout.addWidget(self.pagesWidget, 1)

        buttonsLayout = QtWidgets.QHBoxLayout()
        buttonsLayout.addStretch(1)
        buttonsLayout.addWidget(closeButton)

        mainLayout = QtWidgets.QVBoxLayout()
        mainLayout.addLayout(horizontalLayout)
        mainLayout.addStretch(1)
        mainLayout.addSpacing(12)
        mainLayout.addLayout(buttonsLayout)

        self.setLayout(mainLayout)

        self.setWindowTitle("Preferences")

    def changePage(self, current, previous):
        if not current:
            current = previous

        self.pagesWidget.setCurrentIndex(self.contentsWidget.row(current))

    def createIcons(self):
        configButton = QtWidgets.QListWidgetItem(self.contentsWidget)
        configButton.setIcon(QtGui.QIcon(':/images/inputpane.png'))
        configButton.setText("Input dialog")
        configButton.setTextAlignment(QtCore.Qt.AlignHCenter)
        configButton.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)

        updateButton = QtWidgets.QListWidgetItem(self.contentsWidget)
        updateButton.setIcon(QtGui.QIcon(':/images/inputpane.png'))
        updateButton.setText("New stems")
        updateButton.setTextAlignment(QtCore.Qt.AlignHCenter)
        updateButton.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)

        queryButton = QtWidgets.QListWidgetItem(self.contentsWidget)
        queryButton.setIcon(QtGui.QIcon(':/images/inputpane.png'))
        queryButton.setText("Applications")
        queryButton.setTextAlignment(QtCore.Qt.AlignHCenter)
        queryButton.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)

        self.contentsWidget.currentItemChanged.connect(self.changePage)


if __name__ == '__main__':

    import sys

    app = QtWidgets.QApplication(sys.argv)
    dialog = ConfigDialog()
    sys.exit(dialog.exec_())
