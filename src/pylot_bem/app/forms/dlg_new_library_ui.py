# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'dlg_new_library.ui'
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
from PySide6.QtWidgets import (QAbstractButton, QApplication, QCheckBox, QComboBox,
    QDialog, QDialogButtonBox, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QSizePolicy, QVBoxLayout, QWidget)

class Ui_DlgNewLibrary(object):
    def setupUi(self, DlgNewLibrary):
        if not DlgNewLibrary.objectName():
            DlgNewLibrary.setObjectName(u"DlgNewLibrary")
        DlgNewLibrary.resize(760, 560)
        self.root = QVBoxLayout(DlgNewLibrary)
        self.root.setObjectName(u"root")
        self.layoutColumns = QHBoxLayout()
        self.layoutColumns.setObjectName(u"layoutColumns")
        self.groupSource = QGroupBox(DlgNewLibrary)
        self.groupSource.setObjectName(u"groupSource")
        self.formSource = QFormLayout(self.groupSource)
        self.formSource.setObjectName(u"formSource")
        self.lblMeshFileCaption = QLabel(self.groupSource)
        self.lblMeshFileCaption.setObjectName(u"lblMeshFileCaption")

        self.formSource.setWidget(0, QFormLayout.ItemRole.LabelRole, self.lblMeshFileCaption)

        self.layoutMeshFile = QHBoxLayout()
        self.layoutMeshFile.setObjectName(u"layoutMeshFile")
        self.editMeshFile = QLineEdit(self.groupSource)
        self.editMeshFile.setObjectName(u"editMeshFile")

        self.layoutMeshFile.addWidget(self.editMeshFile)

        self.btnBrowseMesh = QPushButton(self.groupSource)
        self.btnBrowseMesh.setObjectName(u"btnBrowseMesh")

        self.layoutMeshFile.addWidget(self.btnBrowseMesh)


        self.formSource.setLayout(0, QFormLayout.ItemRole.FieldRole, self.layoutMeshFile)

        self.lblUnitsCaption = QLabel(self.groupSource)
        self.lblUnitsCaption.setObjectName(u"lblUnitsCaption")

        self.formSource.setWidget(1, QFormLayout.ItemRole.LabelRole, self.lblUnitsCaption)

        self.comboUnits = QComboBox(self.groupSource)
        self.comboUnits.setObjectName(u"comboUnits")

        self.formSource.setWidget(1, QFormLayout.ItemRole.FieldRole, self.comboUnits)

        self.lblLibraryFileCaption = QLabel(self.groupSource)
        self.lblLibraryFileCaption.setObjectName(u"lblLibraryFileCaption")

        self.formSource.setWidget(2, QFormLayout.ItemRole.LabelRole, self.lblLibraryFileCaption)

        self.layoutLibraryFile = QHBoxLayout()
        self.layoutLibraryFile.setObjectName(u"layoutLibraryFile")
        self.editLibraryFile = QLineEdit(self.groupSource)
        self.editLibraryFile.setObjectName(u"editLibraryFile")

        self.layoutLibraryFile.addWidget(self.editLibraryFile)

        self.btnBrowseLibrary = QPushButton(self.groupSource)
        self.btnBrowseLibrary.setObjectName(u"btnBrowseLibrary")

        self.layoutLibraryFile.addWidget(self.btnBrowseLibrary)


        self.formSource.setLayout(2, QFormLayout.ItemRole.FieldRole, self.layoutLibraryFile)

        self.lblVesselNameCaption = QLabel(self.groupSource)
        self.lblVesselNameCaption.setObjectName(u"lblVesselNameCaption")

        self.formSource.setWidget(3, QFormLayout.ItemRole.LabelRole, self.lblVesselNameCaption)

        self.editVesselName = QLineEdit(self.groupSource)
        self.editVesselName.setObjectName(u"editVesselName")

        self.formSource.setWidget(3, QFormLayout.ItemRole.FieldRole, self.editVesselName)

        self.lblDescriptionCaption = QLabel(self.groupSource)
        self.lblDescriptionCaption.setObjectName(u"lblDescriptionCaption")

        self.formSource.setWidget(4, QFormLayout.ItemRole.LabelRole, self.lblDescriptionCaption)

        self.editDescription = QLineEdit(self.groupSource)
        self.editDescription.setObjectName(u"editDescription")

        self.formSource.setWidget(4, QFormLayout.ItemRole.FieldRole, self.editDescription)

        self.lblOriginCaption = QLabel(self.groupSource)
        self.lblOriginCaption.setObjectName(u"lblOriginCaption")

        self.formSource.setWidget(5, QFormLayout.ItemRole.LabelRole, self.lblOriginCaption)

        self.editOrigin = QLineEdit(self.groupSource)
        self.editOrigin.setObjectName(u"editOrigin")

        self.formSource.setWidget(5, QFormLayout.ItemRole.FieldRole, self.editOrigin)

        self.lblOriginHint = QLabel(self.groupSource)
        self.lblOriginHint.setObjectName(u"lblOriginHint")
        self.lblOriginHint.setWordWrap(True)

        self.formSource.setWidget(6, QFormLayout.ItemRole.SpanningRole, self.lblOriginHint)


        self.layoutColumns.addWidget(self.groupSource)

        self.groupBounds = QGroupBox(DlgNewLibrary)
        self.groupBounds.setObjectName(u"groupBounds")
        self.formBounds = QFormLayout(self.groupBounds)
        self.formBounds.setObjectName(u"formBounds")
        self.lblBoundsXCaption = QLabel(self.groupBounds)
        self.lblBoundsXCaption.setObjectName(u"lblBoundsXCaption")

        self.formBounds.setWidget(0, QFormLayout.ItemRole.LabelRole, self.lblBoundsXCaption)

        self.lblBoundsX = QLabel(self.groupBounds)
        self.lblBoundsX.setObjectName(u"lblBoundsX")
        self.lblBoundsX.setTextFormat(Qt.RichText)

        self.formBounds.setWidget(0, QFormLayout.ItemRole.FieldRole, self.lblBoundsX)

        self.lblBoundsYCaption = QLabel(self.groupBounds)
        self.lblBoundsYCaption.setObjectName(u"lblBoundsYCaption")

        self.formBounds.setWidget(1, QFormLayout.ItemRole.LabelRole, self.lblBoundsYCaption)

        self.lblBoundsY = QLabel(self.groupBounds)
        self.lblBoundsY.setObjectName(u"lblBoundsY")
        self.lblBoundsY.setTextFormat(Qt.RichText)

        self.formBounds.setWidget(1, QFormLayout.ItemRole.FieldRole, self.lblBoundsY)

        self.lblBoundsZCaption = QLabel(self.groupBounds)
        self.lblBoundsZCaption.setObjectName(u"lblBoundsZCaption")

        self.formBounds.setWidget(2, QFormLayout.ItemRole.LabelRole, self.lblBoundsZCaption)

        self.lblBoundsZ = QLabel(self.groupBounds)
        self.lblBoundsZ.setObjectName(u"lblBoundsZ")
        self.lblBoundsZ.setTextFormat(Qt.RichText)

        self.formBounds.setWidget(2, QFormLayout.ItemRole.FieldRole, self.lblBoundsZ)

        self.lblCountsCaption = QLabel(self.groupBounds)
        self.lblCountsCaption.setObjectName(u"lblCountsCaption")

        self.formBounds.setWidget(3, QFormLayout.ItemRole.LabelRole, self.lblCountsCaption)

        self.lblCounts = QLabel(self.groupBounds)
        self.lblCounts.setObjectName(u"lblCounts")
        self.lblCounts.setTextFormat(Qt.RichText)

        self.formBounds.setWidget(3, QFormLayout.ItemRole.FieldRole, self.lblCounts)

        self.lblBoundsHint = QLabel(self.groupBounds)
        self.lblBoundsHint.setObjectName(u"lblBoundsHint")
        self.lblBoundsHint.setWordWrap(True)

        self.formBounds.setWidget(4, QFormLayout.ItemRole.SpanningRole, self.lblBoundsHint)

        self.lblChecks = QLabel(self.groupBounds)
        self.lblChecks.setObjectName(u"lblChecks")
        self.lblChecks.setWordWrap(True)
        self.lblChecks.setTextFormat(Qt.RichText)

        self.formBounds.setWidget(5, QFormLayout.ItemRole.SpanningRole, self.lblChecks)


        self.layoutColumns.addWidget(self.groupBounds)


        self.root.addLayout(self.layoutColumns)

        self.groupSymmetry = QGroupBox(DlgNewLibrary)
        self.groupSymmetry.setObjectName(u"groupSymmetry")
        self.layoutSymmetry = QVBoxLayout(self.groupSymmetry)
        self.layoutSymmetry.setObjectName(u"layoutSymmetry")
        self.chkSymmetric = QCheckBox(self.groupSymmetry)
        self.chkSymmetric.setObjectName(u"chkSymmetric")

        self.layoutSymmetry.addWidget(self.chkSymmetric)

        self.lblSymmetryHint = QLabel(self.groupSymmetry)
        self.lblSymmetryHint.setObjectName(u"lblSymmetryHint")
        self.lblSymmetryHint.setWordWrap(True)

        self.layoutSymmetry.addWidget(self.lblSymmetryHint)


        self.root.addWidget(self.groupSymmetry)

        self.lblFooterHint = QLabel(DlgNewLibrary)
        self.lblFooterHint.setObjectName(u"lblFooterHint")
        self.lblFooterHint.setWordWrap(True)

        self.root.addWidget(self.lblFooterHint)

        self.buttonBox = QDialogButtonBox(DlgNewLibrary)
        self.buttonBox.setObjectName(u"buttonBox")
        self.buttonBox.setOrientation(Qt.Horizontal)
        self.buttonBox.setStandardButtons(QDialogButtonBox.Cancel|QDialogButtonBox.Ok)

        self.root.addWidget(self.buttonBox)


        self.retranslateUi(DlgNewLibrary)

        QMetaObject.connectSlotsByName(DlgNewLibrary)
    # setupUi

    def retranslateUi(self, DlgNewLibrary):
        DlgNewLibrary.setWindowTitle(QCoreApplication.translate("DlgNewLibrary", u"New library \u2014 import base shape", None))
        self.groupSource.setTitle(QCoreApplication.translate("DlgNewLibrary", u"Source", None))
        self.lblMeshFileCaption.setText(QCoreApplication.translate("DlgNewLibrary", u"Base shape file", None))
        self.btnBrowseMesh.setText(QCoreApplication.translate("DlgNewLibrary", u"Browse\u2026", None))
        self.lblUnitsCaption.setText(QCoreApplication.translate("DlgNewLibrary", u"Units in file", None))
        self.lblLibraryFileCaption.setText(QCoreApplication.translate("DlgNewLibrary", u"Library file", None))
        self.btnBrowseLibrary.setText(QCoreApplication.translate("DlgNewLibrary", u"Browse\u2026", None))
        self.lblVesselNameCaption.setText(QCoreApplication.translate("DlgNewLibrary", u"Vessel name", None))
        self.lblDescriptionCaption.setText(QCoreApplication.translate("DlgNewLibrary", u"Description", None))
        self.lblOriginCaption.setText(QCoreApplication.translate("DlgNewLibrary", u"Origin sits at", None))
        self.editOrigin.setPlaceholderText(QCoreApplication.translate("DlgNewLibrary", u"stern, centerline, keel", None))
        self.lblOriginHint.setText(QCoreApplication.translate("DlgNewLibrary", u"Free text, and the only human record of where (0, 0, 0) is. Getting it wrong invalidates every condition in the library.", None))
        self.groupBounds.setTitle(QCoreApplication.translate("DlgNewLibrary", u"Resulting bounds \u2014 derived", None))
        self.lblBoundsXCaption.setText(QCoreApplication.translate("DlgNewLibrary", u"x [m]", None))
        self.lblBoundsX.setText(QCoreApplication.translate("DlgNewLibrary", u"\u2014", None))
        self.lblBoundsYCaption.setText(QCoreApplication.translate("DlgNewLibrary", u"y [m]", None))
        self.lblBoundsY.setText(QCoreApplication.translate("DlgNewLibrary", u"\u2014", None))
        self.lblBoundsZCaption.setText(QCoreApplication.translate("DlgNewLibrary", u"z [m]", None))
        self.lblBoundsZ.setText(QCoreApplication.translate("DlgNewLibrary", u"\u2014", None))
        self.lblCountsCaption.setText(QCoreApplication.translate("DlgNewLibrary", u"Geometry", None))
        self.lblCounts.setText(QCoreApplication.translate("DlgNewLibrary", u"\u2014", None))
        self.lblBoundsHint.setText(QCoreApplication.translate("DlgNewLibrary", u"Bounds update live with the unit choice \u2014 that is what makes the scale checkable rather than a guess.", None))
        self.lblChecks.setText(QCoreApplication.translate("DlgNewLibrary", u"\u2014", None))
        self.groupSymmetry.setTitle(QCoreApplication.translate("DlgNewLibrary", u"Symmetry", None))
        self.chkSymmetric.setText(QCoreApplication.translate("DlgNewLibrary", u"This hull is symmetric about its XZ plane", None))
        self.lblSymmetryHint.setText(QCoreApplication.translate("DlgNewLibrary", u"A declaration by you \u2014 nothing can derive it. A hull's tessellation can be wildly asymmetric while the surface it describes is symmetric to under a millimetre. Declaring it halves every mesh and quarters the memory.", None))
        self.lblFooterHint.setText(QCoreApplication.translate("DlgNewLibrary", u"The only moment a base shape is chosen. It is fixed for the life of the library.", None))
    # retranslateUi

