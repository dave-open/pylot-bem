# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'prop_library.ui'
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
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QFormLayout, QGroupBox,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QPushButton, QSizePolicy, QSpacerItem, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget)

class Ui_PropLibrary(object):
    def setupUi(self, PropLibrary):
        if not PropLibrary.objectName():
            PropLibrary.setObjectName(u"PropLibrary")
        self.root = QVBoxLayout(PropLibrary)
        self.root.setObjectName(u"root")
        self.groupIdentity = QGroupBox(PropLibrary)
        self.groupIdentity.setObjectName(u"groupIdentity")
        self.formIdentity = QFormLayout(self.groupIdentity)
        self.formIdentity.setObjectName(u"formIdentity")
        self.lblVesselNameCaption = QLabel(self.groupIdentity)
        self.lblVesselNameCaption.setObjectName(u"lblVesselNameCaption")

        self.formIdentity.setWidget(0, QFormLayout.ItemRole.LabelRole, self.lblVesselNameCaption)

        self.editVesselName = QLineEdit(self.groupIdentity)
        self.editVesselName.setObjectName(u"editVesselName")

        self.formIdentity.setWidget(0, QFormLayout.ItemRole.FieldRole, self.editVesselName)

        self.lblDescriptionCaption = QLabel(self.groupIdentity)
        self.lblDescriptionCaption.setObjectName(u"lblDescriptionCaption")

        self.formIdentity.setWidget(1, QFormLayout.ItemRole.LabelRole, self.lblDescriptionCaption)

        self.editDescription = QLineEdit(self.groupIdentity)
        self.editDescription.setObjectName(u"editDescription")

        self.formIdentity.setWidget(1, QFormLayout.ItemRole.FieldRole, self.editDescription)

        self.lblOriginCaption = QLabel(self.groupIdentity)
        self.lblOriginCaption.setObjectName(u"lblOriginCaption")

        self.formIdentity.setWidget(2, QFormLayout.ItemRole.LabelRole, self.lblOriginCaption)

        self.editOrigin = QLineEdit(self.groupIdentity)
        self.editOrigin.setObjectName(u"editOrigin")

        self.formIdentity.setWidget(2, QFormLayout.ItemRole.FieldRole, self.editOrigin)

        self.lblOriginHint = QLabel(self.groupIdentity)
        self.lblOriginHint.setObjectName(u"lblOriginHint")
        self.lblOriginHint.setWordWrap(True)

        self.formIdentity.setWidget(3, QFormLayout.ItemRole.SpanningRole, self.lblOriginHint)

        self.btnApplyIdentity = QPushButton(self.groupIdentity)
        self.btnApplyIdentity.setObjectName(u"btnApplyIdentity")

        self.formIdentity.setWidget(4, QFormLayout.ItemRole.FieldRole, self.btnApplyIdentity)


        self.root.addWidget(self.groupIdentity)

        self.groupBaseShape = QGroupBox(PropLibrary)
        self.groupBaseShape.setObjectName(u"groupBaseShape")
        self.formBaseShape = QFormLayout(self.groupBaseShape)
        self.formBaseShape.setObjectName(u"formBaseShape")
        self.lblCountsCaption = QLabel(self.groupBaseShape)
        self.lblCountsCaption.setObjectName(u"lblCountsCaption")

        self.formBaseShape.setWidget(0, QFormLayout.ItemRole.LabelRole, self.lblCountsCaption)

        self.lblCounts = QLabel(self.groupBaseShape)
        self.lblCounts.setObjectName(u"lblCounts")
        self.lblCounts.setTextFormat(Qt.RichText)

        self.formBaseShape.setWidget(0, QFormLayout.ItemRole.FieldRole, self.lblCounts)

        self.lblBoundsCaption = QLabel(self.groupBaseShape)
        self.lblBoundsCaption.setObjectName(u"lblBoundsCaption")

        self.formBaseShape.setWidget(1, QFormLayout.ItemRole.LabelRole, self.lblBoundsCaption)

        self.lblBounds = QLabel(self.groupBaseShape)
        self.lblBounds.setObjectName(u"lblBounds")
        self.lblBounds.setTextFormat(Qt.RichText)

        self.formBaseShape.setWidget(1, QFormLayout.ItemRole.FieldRole, self.lblBounds)

        self.lblSymmetryCaption = QLabel(self.groupBaseShape)
        self.lblSymmetryCaption.setObjectName(u"lblSymmetryCaption")

        self.formBaseShape.setWidget(2, QFormLayout.ItemRole.LabelRole, self.lblSymmetryCaption)

        self.lblSymmetry = QLabel(self.groupBaseShape)
        self.lblSymmetry.setObjectName(u"lblSymmetry")
        self.lblSymmetry.setTextFormat(Qt.RichText)

        self.formBaseShape.setWidget(2, QFormLayout.ItemRole.FieldRole, self.lblSymmetry)

        self.lblBaseShapeNote = QLabel(self.groupBaseShape)
        self.lblBaseShapeNote.setObjectName(u"lblBaseShapeNote")
        self.lblBaseShapeNote.setWordWrap(True)

        self.formBaseShape.setWidget(3, QFormLayout.ItemRole.SpanningRole, self.lblBaseShapeNote)


        self.root.addWidget(self.groupBaseShape)

        self.groupProbes = QGroupBox(PropLibrary)
        self.groupProbes.setObjectName(u"groupProbes")
        self.layoutProbes = QVBoxLayout(self.groupProbes)
        self.layoutProbes.setObjectName(u"layoutProbes")
        self.tableProbes = QTableWidget(self.groupProbes)
        if (self.tableProbes.columnCount() < 2):
            self.tableProbes.setColumnCount(2)
        __qtablewidgetitem = QTableWidgetItem()
        self.tableProbes.setHorizontalHeaderItem(0, __qtablewidgetitem)
        __qtablewidgetitem1 = QTableWidgetItem()
        self.tableProbes.setHorizontalHeaderItem(1, __qtablewidgetitem1)
        self.tableProbes.setObjectName(u"tableProbes")
        self.tableProbes.setMinimumSize(QSize(0, 110))
        self.tableProbes.setSelectionBehavior(QAbstractItemView.SelectRows)

        self.layoutProbes.addWidget(self.tableProbes)

        self.layoutProbeButtons = QHBoxLayout()
        self.layoutProbeButtons.setObjectName(u"layoutProbeButtons")
        self.btnProbeAdd = QPushButton(self.groupProbes)
        self.btnProbeAdd.setObjectName(u"btnProbeAdd")

        self.layoutProbeButtons.addWidget(self.btnProbeAdd)

        self.btnProbeRemove = QPushButton(self.groupProbes)
        self.btnProbeRemove.setObjectName(u"btnProbeRemove")

        self.layoutProbeButtons.addWidget(self.btnProbeRemove)

        self.btnProbeReset = QPushButton(self.groupProbes)
        self.btnProbeReset.setObjectName(u"btnProbeReset")

        self.layoutProbeButtons.addWidget(self.btnProbeReset)


        self.layoutProbes.addLayout(self.layoutProbeButtons)

        self.lblProbeWarning = QLabel(self.groupProbes)
        self.lblProbeWarning.setObjectName(u"lblProbeWarning")
        self.lblProbeWarning.setWordWrap(True)

        self.layoutProbes.addWidget(self.lblProbeWarning)

        self.btnProbeApply = QPushButton(self.groupProbes)
        self.btnProbeApply.setObjectName(u"btnProbeApply")

        self.layoutProbes.addWidget(self.btnProbeApply)


        self.root.addWidget(self.groupProbes)

        self.groupHealth = QGroupBox(PropLibrary)
        self.groupHealth.setObjectName(u"groupHealth")
        self.layoutHealth = QVBoxLayout(self.groupHealth)
        self.layoutHealth.setObjectName(u"layoutHealth")
        self.btnValidate = QPushButton(self.groupHealth)
        self.btnValidate.setObjectName(u"btnValidate")

        self.layoutHealth.addWidget(self.btnValidate)

        self.lblHealth = QLabel(self.groupHealth)
        self.lblHealth.setObjectName(u"lblHealth")
        self.lblHealth.setWordWrap(True)
        self.lblHealth.setTextFormat(Qt.RichText)

        self.layoutHealth.addWidget(self.lblHealth)


        self.root.addWidget(self.groupHealth)

        self.spacerBottom = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.root.addItem(self.spacerBottom)


        self.retranslateUi(PropLibrary)

        QMetaObject.connectSlotsByName(PropLibrary)
    # setupUi

    def retranslateUi(self, PropLibrary):
        PropLibrary.setWindowTitle(QCoreApplication.translate("PropLibrary", u"Library", None))
        self.groupIdentity.setTitle(QCoreApplication.translate("PropLibrary", u"Identity", None))
        self.lblVesselNameCaption.setText(QCoreApplication.translate("PropLibrary", u"Vessel name", None))
        self.lblDescriptionCaption.setText(QCoreApplication.translate("PropLibrary", u"Description", None))
        self.lblOriginCaption.setText(QCoreApplication.translate("PropLibrary", u"Origin sits at", None))
        self.lblOriginHint.setText(QCoreApplication.translate("PropLibrary", u"The only human record of where (0, 0, 0) is. Getting it wrong invalidates every condition below.", None))
        self.btnApplyIdentity.setText(QCoreApplication.translate("PropLibrary", u"Apply", None))
        self.groupBaseShape.setTitle(QCoreApplication.translate("PropLibrary", u"Base shape \u2014 derived", None))
        self.lblCountsCaption.setText(QCoreApplication.translate("PropLibrary", u"Geometry", None))
        self.lblCounts.setText(QCoreApplication.translate("PropLibrary", u"\u2014", None))
        self.lblBoundsCaption.setText(QCoreApplication.translate("PropLibrary", u"Bounds [m]", None))
        self.lblBounds.setText(QCoreApplication.translate("PropLibrary", u"\u2014", None))
        self.lblSymmetryCaption.setText(QCoreApplication.translate("PropLibrary", u"XZ-symmetric", None))
        self.lblSymmetry.setText(QCoreApplication.translate("PropLibrary", u"\u2014", None))
        self.lblBaseShapeNote.setText(QCoreApplication.translate("PropLibrary", u"Chosen when the library is created and fixed for its lifetime. Every condition, mesh and result is defined against it, so there is no action here \u2014 a different hull is a different library.", None))
        self.groupProbes.setTitle(QCoreApplication.translate("PropLibrary", u"Surface probes", None))
        ___qtablewidgetitem = self.tableProbes.horizontalHeaderItem(0)
        ___qtablewidgetitem.setText(QCoreApplication.translate("PropLibrary", u"x [m]", None))
        ___qtablewidgetitem1 = self.tableProbes.horizontalHeaderItem(1)
        ___qtablewidgetitem1.setText(QCoreApplication.translate("PropLibrary", u"y [m]", None))
        self.btnProbeAdd.setText(QCoreApplication.translate("PropLibrary", u"Add", None))
        self.btnProbeRemove.setText(QCoreApplication.translate("PropLibrary", u"Remove", None))
        self.btnProbeReset.setText(QCoreApplication.translate("PropLibrary", u"Reset to corners", None))
        self.lblProbeWarning.setText(QCoreApplication.translate("PropLibrary", u"Applying an edit recomputes the probe z of every condition. You will be told how many changed before it happens.", None))
        self.btnProbeApply.setText(QCoreApplication.translate("PropLibrary", u"Apply probe edit\u2026", None))
        self.groupHealth.setTitle(QCoreApplication.translate("PropLibrary", u"Library health", None))
        self.btnValidate.setText(QCoreApplication.translate("PropLibrary", u"Validate library", None))
        self.lblHealth.setText(QCoreApplication.translate("PropLibrary", u"Not run yet.", None))
    # retranslateUi

