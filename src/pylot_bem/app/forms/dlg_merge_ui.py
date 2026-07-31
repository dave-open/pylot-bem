# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'dlg_merge.ui'
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
from PySide6.QtWidgets import (QAbstractButton, QApplication, QComboBox, QDialog,
    QDialogButtonBox, QFormLayout, QGroupBox, QHeaderView,
    QLabel, QSizePolicy, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget)

class Ui_DlgMerge(object):
    def setupUi(self, DlgMerge):
        if not DlgMerge.objectName():
            DlgMerge.setObjectName(u"DlgMerge")
        DlgMerge.resize(680, 520)
        self.root = QVBoxLayout(DlgMerge)
        self.root.setObjectName(u"root")
        self.lblHeading = QLabel(DlgMerge)
        self.lblHeading.setObjectName(u"lblHeading")
        self.lblHeading.setWordWrap(True)
        self.lblHeading.setTextFormat(Qt.RichText)

        self.root.addWidget(self.lblHeading)

        self.groupPrimary = QGroupBox(DlgMerge)
        self.groupPrimary.setObjectName(u"groupPrimary")
        self.formPrimary = QFormLayout(self.groupPrimary)
        self.formPrimary.setObjectName(u"formPrimary")
        self.lblPrimaryCaption = QLabel(self.groupPrimary)
        self.lblPrimaryCaption.setObjectName(u"lblPrimaryCaption")

        self.formPrimary.setWidget(0, QFormLayout.ItemRole.LabelRole, self.lblPrimaryCaption)

        self.comboPrimary = QComboBox(self.groupPrimary)
        self.comboPrimary.setObjectName(u"comboPrimary")

        self.formPrimary.setWidget(0, QFormLayout.ItemRole.FieldRole, self.comboPrimary)

        self.lblPrimaryHint = QLabel(self.groupPrimary)
        self.lblPrimaryHint.setObjectName(u"lblPrimaryHint")
        self.lblPrimaryHint.setWordWrap(True)

        self.formPrimary.setWidget(1, QFormLayout.ItemRole.SpanningRole, self.lblPrimaryHint)


        self.root.addWidget(self.groupPrimary)

        self.groupEffect = QGroupBox(DlgMerge)
        self.groupEffect.setObjectName(u"groupEffect")
        self.layoutEffect = QVBoxLayout(self.groupEffect)
        self.layoutEffect.setObjectName(u"layoutEffect")
        self.tableEffect = QTableWidget(self.groupEffect)
        if (self.tableEffect.columnCount() < 4):
            self.tableEffect.setColumnCount(4)
        __qtablewidgetitem = QTableWidgetItem()
        self.tableEffect.setHorizontalHeaderItem(0, __qtablewidgetitem)
        __qtablewidgetitem1 = QTableWidgetItem()
        self.tableEffect.setHorizontalHeaderItem(1, __qtablewidgetitem1)
        __qtablewidgetitem2 = QTableWidgetItem()
        self.tableEffect.setHorizontalHeaderItem(2, __qtablewidgetitem2)
        __qtablewidgetitem3 = QTableWidgetItem()
        self.tableEffect.setHorizontalHeaderItem(3, __qtablewidgetitem3)
        self.tableEffect.setObjectName(u"tableEffect")
        self.tableEffect.setAlternatingRowColors(True)

        self.layoutEffect.addWidget(self.tableEffect)


        self.root.addWidget(self.groupEffect)

        self.groupOutcome = QGroupBox(DlgMerge)
        self.groupOutcome.setObjectName(u"groupOutcome")
        self.layoutOutcome = QVBoxLayout(self.groupOutcome)
        self.layoutOutcome.setObjectName(u"layoutOutcome")
        self.lblOutcome = QLabel(self.groupOutcome)
        self.lblOutcome.setObjectName(u"lblOutcome")
        self.lblOutcome.setWordWrap(True)
        self.lblOutcome.setTextFormat(Qt.RichText)

        self.layoutOutcome.addWidget(self.lblOutcome)


        self.root.addWidget(self.groupOutcome)

        self.lblFooterHint = QLabel(DlgMerge)
        self.lblFooterHint.setObjectName(u"lblFooterHint")
        self.lblFooterHint.setWordWrap(True)

        self.root.addWidget(self.lblFooterHint)

        self.buttonBox = QDialogButtonBox(DlgMerge)
        self.buttonBox.setObjectName(u"buttonBox")
        self.buttonBox.setOrientation(Qt.Horizontal)
        self.buttonBox.setStandardButtons(QDialogButtonBox.Cancel|QDialogButtonBox.Ok)

        self.root.addWidget(self.buttonBox)


        self.retranslateUi(DlgMerge)

        QMetaObject.connectSlotsByName(DlgMerge)
    # setupUi

    def retranslateUi(self, DlgMerge):
        DlgMerge.setWindowTitle(QCoreApplication.translate("DlgMerge", u"Merge solutions", None))
        self.lblHeading.setText(QCoreApplication.translate("DlgMerge", u"\u2014", None))
        self.groupPrimary.setTitle(QCoreApplication.translate("DlgMerge", u"Which one wins where they overlap", None))
        self.lblPrimaryCaption.setText(QCoreApplication.translate("DlgMerge", u"Primary", None))
        self.lblPrimaryHint.setText(QCoreApplication.translate("DlgMerge", u"The primary keeps every frequency it has. The others keep only the frequencies it does not cover, so together they span the same range with nothing contested. Nothing is recomputed and no result is created \u2014 each frequency goes on pointing at the mesh, lid and date it was actually solved with.", None))
        self.groupEffect.setTitle(QCoreApplication.translate("DlgMerge", u"What each result would be left with", None))
        ___qtablewidgetitem = self.tableEffect.horizontalHeaderItem(0)
        ___qtablewidgetitem.setText(QCoreApplication.translate("DlgMerge", u"Result", None))
        ___qtablewidgetitem1 = self.tableEffect.horizontalHeaderItem(1)
        ___qtablewidgetitem1.setText(QCoreApplication.translate("DlgMerge", u"Role", None))
        ___qtablewidgetitem2 = self.tableEffect.horizontalHeaderItem(2)
        ___qtablewidgetitem2.setText(QCoreApplication.translate("DlgMerge", u"Keeps [s]", None))
        ___qtablewidgetitem3 = self.tableEffect.horizontalHeaderItem(3)
        ___qtablewidgetitem3.setText(QCoreApplication.translate("DlgMerge", u"Loses [s]", None))
        self.groupOutcome.setTitle(QCoreApplication.translate("DlgMerge", u"What the database becomes", None))
        self.lblOutcome.setText(QCoreApplication.translate("DlgMerge", u"\u2014", None))
        self.lblFooterHint.setText(QCoreApplication.translate("DlgMerge", u"Removing frequencies cannot be undone \u2014 the data was minutes of solving. A result that would lose every frequency is removed entirely.", None))
    # retranslateUi

