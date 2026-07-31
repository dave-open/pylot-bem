# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'dlg_delete_frequencies.ui'
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
from PySide6.QtWidgets import (QAbstractButton, QApplication, QDialog, QDialogButtonBox,
    QGroupBox, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QSizePolicy, QVBoxLayout,
    QWidget)

class Ui_DlgDeleteFrequencies(object):
    def setupUi(self, DlgDeleteFrequencies):
        if not DlgDeleteFrequencies.objectName():
            DlgDeleteFrequencies.setObjectName(u"DlgDeleteFrequencies")
        DlgDeleteFrequencies.resize(560, 480)
        self.root = QVBoxLayout(DlgDeleteFrequencies)
        self.root.setObjectName(u"root")
        self.lblHeading = QLabel(DlgDeleteFrequencies)
        self.lblHeading.setObjectName(u"lblHeading")
        self.lblHeading.setWordWrap(True)
        self.lblHeading.setTextFormat(Qt.RichText)

        self.root.addWidget(self.lblHeading)

        self.lblIntro = QLabel(DlgDeleteFrequencies)
        self.lblIntro.setObjectName(u"lblIntro")
        self.lblIntro.setWordWrap(True)

        self.root.addWidget(self.lblIntro)

        self.listFrequencies = QListWidget(DlgDeleteFrequencies)
        self.listFrequencies.setObjectName(u"listFrequencies")

        self.root.addWidget(self.listFrequencies)

        self.layoutSelect = QHBoxLayout()
        self.layoutSelect.setObjectName(u"layoutSelect")
        self.btnCheckConflicted = QPushButton(DlgDeleteFrequencies)
        self.btnCheckConflicted.setObjectName(u"btnCheckConflicted")

        self.layoutSelect.addWidget(self.btnCheckConflicted)

        self.btnCheckNone = QPushButton(DlgDeleteFrequencies)
        self.btnCheckNone.setObjectName(u"btnCheckNone")

        self.layoutSelect.addWidget(self.btnCheckNone)


        self.root.addLayout(self.layoutSelect)

        self.groupPreview = QGroupBox(DlgDeleteFrequencies)
        self.groupPreview.setObjectName(u"groupPreview")
        self.layoutPreview = QVBoxLayout(self.groupPreview)
        self.layoutPreview.setObjectName(u"layoutPreview")
        self.lblPreview = QLabel(self.groupPreview)
        self.lblPreview.setObjectName(u"lblPreview")
        self.lblPreview.setWordWrap(True)
        self.lblPreview.setTextFormat(Qt.RichText)

        self.layoutPreview.addWidget(self.lblPreview)


        self.root.addWidget(self.groupPreview)

        self.buttonBox = QDialogButtonBox(DlgDeleteFrequencies)
        self.buttonBox.setObjectName(u"buttonBox")
        self.buttonBox.setOrientation(Qt.Horizontal)
        self.buttonBox.setStandardButtons(QDialogButtonBox.Cancel|QDialogButtonBox.Ok)

        self.root.addWidget(self.buttonBox)


        self.retranslateUi(DlgDeleteFrequencies)

        QMetaObject.connectSlotsByName(DlgDeleteFrequencies)
    # setupUi

    def retranslateUi(self, DlgDeleteFrequencies):
        DlgDeleteFrequencies.setWindowTitle(QCoreApplication.translate("DlgDeleteFrequencies", u"Delete frequencies", None))
        self.lblHeading.setText(QCoreApplication.translate("DlgDeleteFrequencies", u"\u2014", None))
        self.lblIntro.setText(QCoreApplication.translate("DlgDeleteFrequencies", u"Tick the frequencies to remove. Whole frequencies only \u2014 removing part of one would leave the degree-of-freedom and direction coverage ragged. A frequency marked \u26a0 is contested by another result: removing it here is what resolves that conflict.", None))
        self.btnCheckConflicted.setText(QCoreApplication.translate("DlgDeleteFrequencies", u"Tick the contested ones", None))
        self.btnCheckNone.setText(QCoreApplication.translate("DlgDeleteFrequencies", u"Tick none", None))
        self.groupPreview.setTitle(QCoreApplication.translate("DlgDeleteFrequencies", u"What this does", None))
        self.lblPreview.setText(QCoreApplication.translate("DlgDeleteFrequencies", u"\u2014", None))
    # retranslateUi

