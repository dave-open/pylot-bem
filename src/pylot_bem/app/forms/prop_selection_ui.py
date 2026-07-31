# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'prop_selection.ui'
##
## Created by: Qt User Interface Compiler version 6.11.1
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QCursor,
    QFont, QFontDatabase, QGradient, QIcon,
    QImage, QKeySequence, QLinearGradient, QPainter,
    QPalette, QPixmap, QRadialGradient, QTransform)
from PySide6.QtWidgets import (QApplication, QGroupBox, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QPushButton, QSizePolicy,
    QSpacerItem, QVBoxLayout, QWidget)

class Ui_PropSelection(object):
    def setupUi(self, PropSelection):
        if not PropSelection.objectName():
            PropSelection.setObjectName(u"PropSelection")
        self.root = QVBoxLayout(PropSelection)
        self.root.setObjectName(u"root")
        self.lblHeading = QLabel(PropSelection)
        self.lblHeading.setObjectName(u"lblHeading")
        self.lblHeading.setWordWrap(True)
        self.lblHeading.setTextFormat(Qt.RichText)

        self.root.addWidget(self.lblHeading)

        self.groupSelected = QGroupBox(PropSelection)
        self.groupSelected.setObjectName(u"groupSelected")
        self.layoutSelected = QVBoxLayout(self.groupSelected)
        self.layoutSelected.setObjectName(u"layoutSelected")
        self.listSelected = QListWidget(self.groupSelected)
        self.listSelected.setObjectName(u"listSelected")
        self.listSelected.setMinimumSize(QSize(0, 90))

        self.layoutSelected.addWidget(self.listSelected)


        self.root.addWidget(self.groupSelected)

        self.groupTogether = QGroupBox(PropSelection)
        self.groupTogether.setObjectName(u"groupTogether")
        self.layoutTogether = QVBoxLayout(self.groupTogether)
        self.layoutTogether.setObjectName(u"layoutTogether")
        self.lblTogether = QLabel(self.groupTogether)
        self.lblTogether.setObjectName(u"lblTogether")
        self.lblTogether.setWordWrap(True)
        self.lblTogether.setTextFormat(Qt.RichText)

        self.layoutTogether.addWidget(self.lblTogether)

        self.lblNote = QLabel(self.groupTogether)
        self.lblNote.setObjectName(u"lblNote")
        self.lblNote.setWordWrap(True)
        self.lblNote.setTextFormat(Qt.RichText)

        self.layoutTogether.addWidget(self.lblNote)


        self.root.addWidget(self.groupTogether)

        self.layoutActions = QHBoxLayout()
        self.layoutActions.setObjectName(u"layoutActions")
        self.btnCompare = QPushButton(PropSelection)
        self.btnCompare.setObjectName(u"btnCompare")

        self.layoutActions.addWidget(self.btnCompare)

        self.btnMerge = QPushButton(PropSelection)
        self.btnMerge.setObjectName(u"btnMerge")

        self.layoutActions.addWidget(self.btnMerge)

        self.btnRemoveSelected = QPushButton(PropSelection)
        self.btnRemoveSelected.setObjectName(u"btnRemoveSelected")

        self.layoutActions.addWidget(self.btnRemoveSelected)


        self.root.addLayout(self.layoutActions)

        self.spacerBottom = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.root.addItem(self.spacerBottom)


        self.retranslateUi(PropSelection)

        QMetaObject.connectSlotsByName(PropSelection)
    # setupUi

    def retranslateUi(self, PropSelection):
        PropSelection.setWindowTitle(QCoreApplication.translate("PropSelection", u"Selection", None))
        self.lblHeading.setText(QCoreApplication.translate("PropSelection", u"Nothing selected", None))
        self.groupSelected.setTitle(QCoreApplication.translate("PropSelection", u"Selected", None))
        self.groupTogether.setTitle(QCoreApplication.translate("PropSelection", u"Together", None))
        self.lblTogether.setText(QCoreApplication.translate("PropSelection", u"\u2014", None))
        self.lblNote.setText("")
        self.btnCompare.setText(QCoreApplication.translate("PropSelection", u"Compare in Inspect\u2026", None))
        self.btnMerge.setText(QCoreApplication.translate("PropSelection", u"Merge\u2026", None))
        self.btnRemoveSelected.setText(QCoreApplication.translate("PropSelection", u"Remove selected\u2026", None))
    # retranslateUi

