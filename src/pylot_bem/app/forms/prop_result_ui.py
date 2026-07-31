# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'prop_result.ui'
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
from PySide6.QtWidgets import (QApplication, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QSizePolicy,
    QSpacerItem, QVBoxLayout, QWidget)

class Ui_PropResult(object):
    def setupUi(self, PropResult):
        if not PropResult.objectName():
            PropResult.setObjectName(u"PropResult")
        self.root = QVBoxLayout(PropResult)
        self.root.setObjectName(u"root")
        self.groupIdentity = QGroupBox(PropResult)
        self.groupIdentity.setObjectName(u"groupIdentity")
        self.formIdentity = QFormLayout(self.groupIdentity)
        self.formIdentity.setObjectName(u"formIdentity")
        self.lblLabelCaption = QLabel(self.groupIdentity)
        self.lblLabelCaption.setObjectName(u"lblLabelCaption")

        self.formIdentity.setWidget(0, QFormLayout.ItemRole.LabelRole, self.lblLabelCaption)

        self.editLabel = QLineEdit(self.groupIdentity)
        self.editLabel.setObjectName(u"editLabel")

        self.formIdentity.setWidget(0, QFormLayout.ItemRole.FieldRole, self.editLabel)

        self.btnApplyLabel = QPushButton(self.groupIdentity)
        self.btnApplyLabel.setObjectName(u"btnApplyLabel")

        self.formIdentity.setWidget(1, QFormLayout.ItemRole.FieldRole, self.btnApplyLabel)

        self.lblLabelHint = QLabel(self.groupIdentity)
        self.lblLabelHint.setObjectName(u"lblLabelHint")
        self.lblLabelHint.setWordWrap(True)

        self.formIdentity.setWidget(2, QFormLayout.ItemRole.SpanningRole, self.lblLabelHint)


        self.root.addWidget(self.groupIdentity)

        self.groupSolved = QGroupBox(PropResult)
        self.groupSolved.setObjectName(u"groupSolved")
        self.formSolved = QFormLayout(self.groupSolved)
        self.formSolved.setObjectName(u"formSolved")
        self.lblIdCaption = QLabel(self.groupSolved)
        self.lblIdCaption.setObjectName(u"lblIdCaption")

        self.formSolved.setWidget(0, QFormLayout.ItemRole.LabelRole, self.lblIdCaption)

        self.lblId = QLabel(self.groupSolved)
        self.lblId.setObjectName(u"lblId")
        self.lblId.setTextFormat(Qt.RichText)
        self.lblId.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.formSolved.setWidget(0, QFormLayout.ItemRole.FieldRole, self.lblId)

        self.lblPeriodsCaption = QLabel(self.groupSolved)
        self.lblPeriodsCaption.setObjectName(u"lblPeriodsCaption")

        self.formSolved.setWidget(1, QFormLayout.ItemRole.LabelRole, self.lblPeriodsCaption)

        self.lblPeriods = QLabel(self.groupSolved)
        self.lblPeriods.setObjectName(u"lblPeriods")
        self.lblPeriods.setTextFormat(Qt.RichText)
        self.lblPeriods.setWordWrap(True)

        self.formSolved.setWidget(1, QFormLayout.ItemRole.FieldRole, self.lblPeriods)

        self.lblDirectionsCaption = QLabel(self.groupSolved)
        self.lblDirectionsCaption.setObjectName(u"lblDirectionsCaption")

        self.formSolved.setWidget(2, QFormLayout.ItemRole.LabelRole, self.lblDirectionsCaption)

        self.lblDirections = QLabel(self.groupSolved)
        self.lblDirections.setObjectName(u"lblDirections")
        self.lblDirections.setTextFormat(Qt.RichText)
        self.lblDirections.setWordWrap(True)

        self.formSolved.setWidget(2, QFormLayout.ItemRole.FieldRole, self.lblDirections)

        self.lblPhysicalCaption = QLabel(self.groupSolved)
        self.lblPhysicalCaption.setObjectName(u"lblPhysicalCaption")

        self.formSolved.setWidget(3, QFormLayout.ItemRole.LabelRole, self.lblPhysicalCaption)

        self.lblPhysical = QLabel(self.groupSolved)
        self.lblPhysical.setObjectName(u"lblPhysical")
        self.lblPhysical.setTextFormat(Qt.RichText)
        self.lblPhysical.setWordWrap(True)

        self.formSolved.setWidget(3, QFormLayout.ItemRole.FieldRole, self.lblPhysical)

        self.lblLidCaption = QLabel(self.groupSolved)
        self.lblLidCaption.setObjectName(u"lblLidCaption")

        self.formSolved.setWidget(4, QFormLayout.ItemRole.LabelRole, self.lblLidCaption)

        self.lblLid = QLabel(self.groupSolved)
        self.lblLid.setObjectName(u"lblLid")
        self.lblLid.setTextFormat(Qt.RichText)

        self.formSolved.setWidget(4, QFormLayout.ItemRole.FieldRole, self.lblLid)

        self.lblMeshCaption = QLabel(self.groupSolved)
        self.lblMeshCaption.setObjectName(u"lblMeshCaption")

        self.formSolved.setWidget(5, QFormLayout.ItemRole.LabelRole, self.lblMeshCaption)

        self.lblMesh = QLabel(self.groupSolved)
        self.lblMesh.setObjectName(u"lblMesh")
        self.lblMesh.setTextFormat(Qt.RichText)
        self.lblMesh.setWordWrap(True)

        self.formSolved.setWidget(5, QFormLayout.ItemRole.FieldRole, self.lblMesh)

        self.lblSolverCaption = QLabel(self.groupSolved)
        self.lblSolverCaption.setObjectName(u"lblSolverCaption")

        self.formSolved.setWidget(6, QFormLayout.ItemRole.LabelRole, self.lblSolverCaption)

        self.lblSolver = QLabel(self.groupSolved)
        self.lblSolver.setObjectName(u"lblSolver")
        self.lblSolver.setTextFormat(Qt.RichText)

        self.formSolved.setWidget(6, QFormLayout.ItemRole.FieldRole, self.lblSolver)

        self.lblCoverageCaption = QLabel(self.groupSolved)
        self.lblCoverageCaption.setObjectName(u"lblCoverageCaption")

        self.formSolved.setWidget(7, QFormLayout.ItemRole.LabelRole, self.lblCoverageCaption)

        self.lblCoverage = QLabel(self.groupSolved)
        self.lblCoverage.setObjectName(u"lblCoverage")
        self.lblCoverage.setTextFormat(Qt.RichText)
        self.lblCoverage.setWordWrap(True)

        self.formSolved.setWidget(7, QFormLayout.ItemRole.FieldRole, self.lblCoverage)


        self.root.addWidget(self.groupSolved)

        self.lblNote = QLabel(PropResult)
        self.lblNote.setObjectName(u"lblNote")
        self.lblNote.setWordWrap(True)
        self.lblNote.setTextFormat(Qt.RichText)

        self.root.addWidget(self.lblNote)

        self.groupDensity = QGroupBox(PropResult)
        self.groupDensity.setObjectName(u"groupDensity")
        self.layoutDensity = QVBoxLayout(self.groupDensity)
        self.layoutDensity.setObjectName(u"layoutDensity")
        self.lblDensityNote = QLabel(self.groupDensity)
        self.lblDensityNote.setObjectName(u"lblDensityNote")
        self.lblDensityNote.setWordWrap(True)

        self.layoutDensity.addWidget(self.lblDensityNote)


        self.root.addWidget(self.groupDensity)

        self.groupDatabase = QGroupBox(PropResult)
        self.groupDatabase.setObjectName(u"groupDatabase")
        self.layoutDatabase = QVBoxLayout(self.groupDatabase)
        self.layoutDatabase.setObjectName(u"layoutDatabase")
        self.lblDatabase = QLabel(self.groupDatabase)
        self.lblDatabase.setObjectName(u"lblDatabase")
        self.lblDatabase.setWordWrap(True)
        self.lblDatabase.setTextFormat(Qt.RichText)

        self.layoutDatabase.addWidget(self.lblDatabase)


        self.root.addWidget(self.groupDatabase)

        self.layoutActions = QHBoxLayout()
        self.layoutActions.setObjectName(u"layoutActions")
        self.btnInspect = QPushButton(PropResult)
        self.btnInspect.setObjectName(u"btnInspect")

        self.layoutActions.addWidget(self.btnInspect)

        self.btnDeleteFrequencies = QPushButton(PropResult)
        self.btnDeleteFrequencies.setObjectName(u"btnDeleteFrequencies")

        self.layoutActions.addWidget(self.btnDeleteFrequencies)

        self.btnRemoveResult = QPushButton(PropResult)
        self.btnRemoveResult.setObjectName(u"btnRemoveResult")

        self.layoutActions.addWidget(self.btnRemoveResult)


        self.root.addLayout(self.layoutActions)

        self.spacerBottom = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.root.addItem(self.spacerBottom)


        self.retranslateUi(PropResult)

        QMetaObject.connectSlotsByName(PropResult)
    # setupUi

    def retranslateUi(self, PropResult):
        PropResult.setWindowTitle(QCoreApplication.translate("PropResult", u"Result", None))
        self.groupIdentity.setTitle(QCoreApplication.translate("PropResult", u"Identity", None))
        self.lblLabelCaption.setText(QCoreApplication.translate("PropResult", u"Label", None))
        self.editLabel.setPlaceholderText(QCoreApplication.translate("PropResult", u"a name for this solution", None))
        self.btnApplyLabel.setText(QCoreApplication.translate("PropResult", u"Apply", None))
        self.lblLabelHint.setText(QCoreApplication.translate("PropResult", u"Shown in the tree in place of the id. Human display only \u2014 nothing parses it, so it can be changed at any time, unlike the id below.", None))
        self.groupSolved.setTitle(QCoreApplication.translate("PropResult", u"What was solved \u2014 derived", None))
        self.lblIdCaption.setText(QCoreApplication.translate("PropResult", u"Id", None))
        self.lblId.setText(QCoreApplication.translate("PropResult", u"\u2014", None))
        self.lblPeriodsCaption.setText(QCoreApplication.translate("PropResult", u"Periods [s]", None))
        self.lblPeriods.setText(QCoreApplication.translate("PropResult", u"\u2014", None))
        self.lblDirectionsCaption.setText(QCoreApplication.translate("PropResult", u"Directions [deg]", None))
        self.lblDirections.setText(QCoreApplication.translate("PropResult", u"\u2014", None))
        self.lblPhysicalCaption.setText(QCoreApplication.translate("PropResult", u"Conditions", None))
        self.lblPhysical.setText(QCoreApplication.translate("PropResult", u"\u2014", None))
        self.lblLidCaption.setText(QCoreApplication.translate("PropResult", u"Lid", None))
        self.lblLid.setText(QCoreApplication.translate("PropResult", u"\u2014", None))
        self.lblMeshCaption.setText(QCoreApplication.translate("PropResult", u"On mesh", None))
        self.lblMesh.setText(QCoreApplication.translate("PropResult", u"\u2014", None))
        self.lblSolverCaption.setText(QCoreApplication.translate("PropResult", u"Solver", None))
        self.lblSolver.setText(QCoreApplication.translate("PropResult", u"\u2014", None))
        self.lblCoverageCaption.setText(QCoreApplication.translate("PropResult", u"Carries", None))
        self.lblCoverage.setText(QCoreApplication.translate("PropResult", u"\u2014", None))
        self.lblNote.setText("")
        self.groupDensity.setTitle(QCoreApplication.translate("PropResult", u"Density", None))
        self.lblDensityNote.setText(QCoreApplication.translate("PropResult", u"None was chosen when this was solved and none is recorded. Density is applied when a database is delivered, so this one result serves every density.", None))
        self.groupDatabase.setTitle(QCoreApplication.translate("PropResult", u"Feeds database", None))
        self.lblDatabase.setText(QCoreApplication.translate("PropResult", u"\u2014", None))
        self.btnInspect.setText(QCoreApplication.translate("PropResult", u"Inspect\u2026", None))
        self.btnDeleteFrequencies.setText(QCoreApplication.translate("PropResult", u"Delete frequencies\u2026", None))
        self.btnRemoveResult.setText(QCoreApplication.translate("PropResult", u"Remove result\u2026", None))
    # retranslateUi

