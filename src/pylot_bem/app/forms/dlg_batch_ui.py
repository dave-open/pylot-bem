# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'dlg_batch.ui'
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
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog,
    QDoubleSpinBox, QFormLayout, QGridLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
    QProgressBar, QPushButton, QSizePolicy, QSpacerItem,
    QSpinBox, QToolBox, QVBoxLayout, QWidget)

class Ui_DlgBatch(object):
    def setupUi(self, DlgBatch):
        if not DlgBatch.objectName():
            DlgBatch.setObjectName(u"DlgBatch")
        DlgBatch.resize(1507, 1146)
        self.verticalLayout_4 = QVBoxLayout(DlgBatch)
        self.verticalLayout_4.setObjectName(u"verticalLayout_4")
        self.lblHeading = QLabel(DlgBatch)
        self.lblHeading.setObjectName(u"lblHeading")
        self.lblHeading.setTextFormat(Qt.TextFormat.RichText)
        self.lblHeading.setWordWrap(True)

        self.verticalLayout_4.addWidget(self.lblHeading)

        self.toolBox = QToolBox(DlgBatch)
        self.toolBox.setObjectName(u"toolBox")
        self.page = QWidget()
        self.page.setObjectName(u"page")
        self.page.setGeometry(QRect(0, 0, 1489, 922))
        self.verticalLayout = QVBoxLayout(self.page)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.groupPhysical = QGroupBox(self.page)
        self.groupPhysical.setObjectName(u"groupPhysical")
        self.formPhysical = QFormLayout(self.groupPhysical)
        self.formPhysical.setObjectName(u"formPhysical")
        self.lblDepthCaption = QLabel(self.groupPhysical)
        self.lblDepthCaption.setObjectName(u"lblDepthCaption")

        self.formPhysical.setWidget(0, QFormLayout.ItemRole.LabelRole, self.lblDepthCaption)

        self.spinDepth = QDoubleSpinBox(self.groupPhysical)
        self.spinDepth.setObjectName(u"spinDepth")
        self.spinDepth.setEnabled(False)
        self.spinDepth.setDecimals(2)
        self.spinDepth.setMinimum(0.100000000000000)
        self.spinDepth.setMaximum(100000.000000000000000)
        self.spinDepth.setValue(100.000000000000000)

        self.formPhysical.setWidget(0, QFormLayout.ItemRole.FieldRole, self.spinDepth)

        self.chkInfiniteDepth = QCheckBox(self.groupPhysical)
        self.chkInfiniteDepth.setObjectName(u"chkInfiniteDepth")
        self.chkInfiniteDepth.setChecked(True)

        self.formPhysical.setWidget(1, QFormLayout.ItemRole.SpanningRole, self.chkInfiniteDepth)

        self.lblGCaption = QLabel(self.groupPhysical)
        self.lblGCaption.setObjectName(u"lblGCaption")

        self.formPhysical.setWidget(2, QFormLayout.ItemRole.LabelRole, self.lblGCaption)

        self.spinG = QDoubleSpinBox(self.groupPhysical)
        self.spinG.setObjectName(u"spinG")
        self.spinG.setDecimals(3)
        self.spinG.setMinimum(0.100000000000000)
        self.spinG.setMaximum(100.000000000000000)
        self.spinG.setValue(9.810000000000000)

        self.formPhysical.setWidget(2, QFormLayout.ItemRole.FieldRole, self.spinG)

        self.lblSpeedCaption = QLabel(self.groupPhysical)
        self.lblSpeedCaption.setObjectName(u"lblSpeedCaption")

        self.formPhysical.setWidget(3, QFormLayout.ItemRole.LabelRole, self.lblSpeedCaption)

        self.spinSpeed = QDoubleSpinBox(self.groupPhysical)
        self.spinSpeed.setObjectName(u"spinSpeed")
        self.spinSpeed.setDecimals(3)
        self.spinSpeed.setMinimum(0.000000000000000)
        self.spinSpeed.setMaximum(50.000000000000000)
        self.spinSpeed.setValue(0.000000000000000)

        self.formPhysical.setWidget(3, QFormLayout.ItemRole.FieldRole, self.spinSpeed)

        self.lblPhysicalHint = QLabel(self.groupPhysical)
        self.lblPhysicalHint.setObjectName(u"lblPhysicalHint")
        self.lblPhysicalHint.setWordWrap(True)

        self.formPhysical.setWidget(4, QFormLayout.ItemRole.SpanningRole, self.lblPhysicalHint)


        self.verticalLayout.addWidget(self.groupPhysical)

        self.groupConditions = QGroupBox(self.page)
        self.groupConditions.setObjectName(u"groupConditions")
        self.formConditions = QFormLayout(self.groupConditions)
        self.formConditions.setObjectName(u"formConditions")
        self.chkCreateConditions = QCheckBox(self.groupConditions)
        self.chkCreateConditions.setObjectName(u"chkCreateConditions")
        self.chkCreateConditions.setChecked(True)

        self.formConditions.setWidget(0, QFormLayout.ItemRole.SpanningRole, self.chkCreateConditions)

        self.lblZCaption = QLabel(self.groupConditions)
        self.lblZCaption.setObjectName(u"lblZCaption")

        self.formConditions.setWidget(1, QFormLayout.ItemRole.LabelRole, self.lblZCaption)

        self.layoutZ = QHBoxLayout()
        self.layoutZ.setObjectName(u"layoutZ")
        self.spinZFrom = QDoubleSpinBox(self.groupConditions)
        self.spinZFrom.setObjectName(u"spinZFrom")
        self.spinZFrom.setDecimals(3)
        self.spinZFrom.setMinimum(-999.000000000000000)
        self.spinZFrom.setMaximum(999.000000000000000)
        self.spinZFrom.setSingleStep(0.100000000000000)
        self.spinZFrom.setValue(-4.700000000000000)

        self.layoutZ.addWidget(self.spinZFrom)

        self.lblZStep = QLabel(self.groupConditions)
        self.lblZStep.setObjectName(u"lblZStep")

        self.layoutZ.addWidget(self.lblZStep)

        self.spinZStep = QDoubleSpinBox(self.groupConditions)
        self.spinZStep.setObjectName(u"spinZStep")
        self.spinZStep.setDecimals(3)
        self.spinZStep.setMinimum(0.001000000000000)
        self.spinZStep.setMaximum(999.000000000000000)
        self.spinZStep.setSingleStep(0.100000000000000)
        self.spinZStep.setValue(0.100000000000000)

        self.layoutZ.addWidget(self.spinZStep)

        self.lblZTo = QLabel(self.groupConditions)
        self.lblZTo.setObjectName(u"lblZTo")

        self.layoutZ.addWidget(self.lblZTo)

        self.spinZTo = QDoubleSpinBox(self.groupConditions)
        self.spinZTo.setObjectName(u"spinZTo")
        self.spinZTo.setDecimals(3)
        self.spinZTo.setMinimum(-999.000000000000000)
        self.spinZTo.setMaximum(999.000000000000000)
        self.spinZTo.setSingleStep(0.100000000000000)
        self.spinZTo.setValue(-0.100000000000000)

        self.layoutZ.addWidget(self.spinZTo)


        self.formConditions.setLayout(1, QFormLayout.ItemRole.FieldRole, self.layoutZ)

        self.lblZHint = QLabel(self.groupConditions)
        self.lblZHint.setObjectName(u"lblZHint")
        self.lblZHint.setWordWrap(True)

        self.formConditions.setWidget(2, QFormLayout.ItemRole.SpanningRole, self.lblZHint)

        self.lblHeelCaption = QLabel(self.groupConditions)
        self.lblHeelCaption.setObjectName(u"lblHeelCaption")

        self.formConditions.setWidget(3, QFormLayout.ItemRole.LabelRole, self.lblHeelCaption)

        self.editHeels = QLineEdit(self.groupConditions)
        self.editHeels.setObjectName(u"editHeels")

        self.formConditions.setWidget(3, QFormLayout.ItemRole.FieldRole, self.editHeels)

        self.lblTrimCaption = QLabel(self.groupConditions)
        self.lblTrimCaption.setObjectName(u"lblTrimCaption")

        self.formConditions.setWidget(4, QFormLayout.ItemRole.LabelRole, self.lblTrimCaption)

        self.editTrims = QLineEdit(self.groupConditions)
        self.editTrims.setObjectName(u"editTrims")

        self.formConditions.setWidget(4, QFormLayout.ItemRole.FieldRole, self.editTrims)

        self.lblAnglesHint = QLabel(self.groupConditions)
        self.lblAnglesHint.setObjectName(u"lblAnglesHint")
        self.lblAnglesHint.setWordWrap(True)

        self.formConditions.setWidget(5, QFormLayout.ItemRole.SpanningRole, self.lblAnglesHint)

        self.lblConditionGrid = QLabel(self.groupConditions)
        self.lblConditionGrid.setObjectName(u"lblConditionGrid")
        self.lblConditionGrid.setTextFormat(Qt.TextFormat.RichText)
        self.lblConditionGrid.setWordWrap(True)

        self.formConditions.setWidget(6, QFormLayout.ItemRole.SpanningRole, self.lblConditionGrid)


        self.verticalLayout.addWidget(self.groupConditions)

        self.toolBox.addItem(self.page, u"Conditions")
        self.page_2 = QWidget()
        self.page_2.setObjectName(u"page_2")
        self.page_2.setGeometry(QRect(0, 0, 1489, 922))
        self.verticalLayout_2 = QVBoxLayout(self.page_2)
        self.verticalLayout_2.setObjectName(u"verticalLayout_2")
        self.groupBands = QGroupBox(self.page_2)
        self.groupBands.setObjectName(u"groupBands")
        self.layoutBands = QVBoxLayout(self.groupBands)
        self.layoutBands.setObjectName(u"layoutBands")
        self.lblBandsCaption = QLabel(self.groupBands)
        self.lblBandsCaption.setObjectName(u"lblBandsCaption")
        self.lblBandsCaption.setTextFormat(Qt.TextFormat.RichText)

        self.layoutBands.addWidget(self.lblBandsCaption)

        self.editBands = QPlainTextEdit(self.groupBands)
        self.editBands.setObjectName(u"editBands")
        self.editBands.setMinimumSize(QSize(0, 90))
        self.editBands.setMaximumSize(QSize(16777215, 140))

        self.layoutBands.addWidget(self.editBands)

        self.lblBandsHint = QLabel(self.groupBands)
        self.lblBandsHint.setObjectName(u"lblBandsHint")
        self.lblBandsHint.setWordWrap(True)

        self.layoutBands.addWidget(self.lblBandsHint)

        self.lblBands = QLabel(self.groupBands)
        self.lblBands.setObjectName(u"lblBands")
        self.lblBands.setTextFormat(Qt.TextFormat.RichText)
        self.lblBands.setWordWrap(True)

        self.layoutBands.addWidget(self.lblBands)

        self.formBands = QFormLayout()
        self.formBands.setObjectName(u"formBands")
        self.lblIterationsCaption = QLabel(self.groupBands)
        self.lblIterationsCaption.setObjectName(u"lblIterationsCaption")

        self.formBands.setWidget(0, QFormLayout.ItemRole.LabelRole, self.lblIterationsCaption)

        self.spinIterations = QSpinBox(self.groupBands)
        self.spinIterations.setObjectName(u"spinIterations")
        self.spinIterations.setMinimum(1)
        self.spinIterations.setMaximum(500)
        self.spinIterations.setValue(20)

        self.formBands.setWidget(0, QFormLayout.ItemRole.FieldRole, self.spinIterations)

        self.lblTargetsCaption = QLabel(self.groupBands)
        self.lblTargetsCaption.setObjectName(u"lblTargetsCaption")

        self.formBands.setWidget(1, QFormLayout.ItemRole.LabelRole, self.lblTargetsCaption)

        self.comboTargets = QComboBox(self.groupBands)
        self.comboTargets.setObjectName(u"comboTargets")

        self.formBands.setWidget(1, QFormLayout.ItemRole.FieldRole, self.comboTargets)


        self.layoutBands.addLayout(self.formBands)

        self.lblTargets = QLabel(self.groupBands)
        self.lblTargets.setObjectName(u"lblTargets")
        self.lblTargets.setTextFormat(Qt.TextFormat.RichText)
        self.lblTargets.setWordWrap(True)

        self.layoutBands.addWidget(self.lblTargets)


        self.verticalLayout_2.addWidget(self.groupBands)

        self.toolBox.addItem(self.page_2, u"Periods and Meshing")
        self.Wave = QWidget()
        self.Wave.setObjectName(u"Wave")
        self.verticalLayout_3 = QVBoxLayout(self.Wave)
        self.verticalLayout_3.setObjectName(u"verticalLayout_3")
        self.groupDirections = QGroupBox(self.Wave)
        self.groupDirections.setObjectName(u"groupDirections")
        self.formDirections = QFormLayout(self.groupDirections)
        self.formDirections.setObjectName(u"formDirections")
        self.lblDirHalfCaption = QLabel(self.groupDirections)
        self.lblDirHalfCaption.setObjectName(u"lblDirHalfCaption")

        self.formDirections.setWidget(0, QFormLayout.ItemRole.LabelRole, self.lblDirHalfCaption)

        self.layoutDirHalf = QHBoxLayout()
        self.layoutDirHalf.setObjectName(u"layoutDirHalf")
        self.spinDirFrom = QDoubleSpinBox(self.groupDirections)
        self.spinDirFrom.setObjectName(u"spinDirFrom")
        self.spinDirFrom.setDecimals(1)
        self.spinDirFrom.setMinimum(-360.000000000000000)
        self.spinDirFrom.setMaximum(360.000000000000000)
        self.spinDirFrom.setValue(0.000000000000000)

        self.layoutDirHalf.addWidget(self.spinDirFrom)

        self.lblDirTo = QLabel(self.groupDirections)
        self.lblDirTo.setObjectName(u"lblDirTo")

        self.layoutDirHalf.addWidget(self.lblDirTo)

        self.spinDirTo = QDoubleSpinBox(self.groupDirections)
        self.spinDirTo.setObjectName(u"spinDirTo")
        self.spinDirTo.setDecimals(1)
        self.spinDirTo.setMinimum(-360.000000000000000)
        self.spinDirTo.setMaximum(360.000000000000000)
        self.spinDirTo.setValue(180.000000000000000)

        self.layoutDirHalf.addWidget(self.spinDirTo)

        self.lblDirStep = QLabel(self.groupDirections)
        self.lblDirStep.setObjectName(u"lblDirStep")

        self.layoutDirHalf.addWidget(self.lblDirStep)

        self.spinDirStep = QDoubleSpinBox(self.groupDirections)
        self.spinDirStep.setObjectName(u"spinDirStep")
        self.spinDirStep.setDecimals(1)
        self.spinDirStep.setMinimum(0.000000000000000)
        self.spinDirStep.setMaximum(360.000000000000000)
        self.spinDirStep.setValue(15.000000000000000)

        self.layoutDirHalf.addWidget(self.spinDirStep)


        self.formDirections.setLayout(0, QFormLayout.ItemRole.FieldRole, self.layoutDirHalf)

        self.lblDirList = QLabel(self.groupDirections)
        self.lblDirList.setObjectName(u"lblDirList")
        self.lblDirList.setTextFormat(Qt.TextFormat.RichText)
        self.lblDirList.setWordWrap(True)

        self.formDirections.setWidget(1, QFormLayout.ItemRole.SpanningRole, self.lblDirList)

        self.lblDirFullCaption = QLabel(self.groupDirections)
        self.lblDirFullCaption.setObjectName(u"lblDirFullCaption")

        self.formDirections.setWidget(2, QFormLayout.ItemRole.LabelRole, self.lblDirFullCaption)

        self.layoutDirFull = QHBoxLayout()
        self.layoutDirFull.setObjectName(u"layoutDirFull")
        self.spinDirFullFrom = QDoubleSpinBox(self.groupDirections)
        self.spinDirFullFrom.setObjectName(u"spinDirFullFrom")
        self.spinDirFullFrom.setDecimals(1)
        self.spinDirFullFrom.setMinimum(-360.000000000000000)
        self.spinDirFullFrom.setMaximum(360.000000000000000)
        self.spinDirFullFrom.setValue(0.000000000000000)

        self.layoutDirFull.addWidget(self.spinDirFullFrom)

        self.lblDirFullTo = QLabel(self.groupDirections)
        self.lblDirFullTo.setObjectName(u"lblDirFullTo")

        self.layoutDirFull.addWidget(self.lblDirFullTo)

        self.spinDirFullTo = QDoubleSpinBox(self.groupDirections)
        self.spinDirFullTo.setObjectName(u"spinDirFullTo")
        self.spinDirFullTo.setDecimals(1)
        self.spinDirFullTo.setMinimum(-360.000000000000000)
        self.spinDirFullTo.setMaximum(360.000000000000000)
        self.spinDirFullTo.setValue(360.000000000000000)

        self.layoutDirFull.addWidget(self.spinDirFullTo)

        self.lblDirFullStep = QLabel(self.groupDirections)
        self.lblDirFullStep.setObjectName(u"lblDirFullStep")

        self.layoutDirFull.addWidget(self.lblDirFullStep)

        self.spinDirFullStep = QDoubleSpinBox(self.groupDirections)
        self.spinDirFullStep.setObjectName(u"spinDirFullStep")
        self.spinDirFullStep.setDecimals(1)
        self.spinDirFullStep.setMinimum(0.000000000000000)
        self.spinDirFullStep.setMaximum(360.000000000000000)
        self.spinDirFullStep.setValue(15.000000000000000)

        self.layoutDirFull.addWidget(self.spinDirFullStep)


        self.formDirections.setLayout(3, QFormLayout.ItemRole.FieldRole, self.layoutDirFull)

        self.lblDirFullList = QLabel(self.groupDirections)
        self.lblDirFullList.setObjectName(u"lblDirFullList")
        self.lblDirFullList.setTextFormat(Qt.TextFormat.RichText)
        self.lblDirFullList.setWordWrap(True)

        self.formDirections.setWidget(4, QFormLayout.ItemRole.SpanningRole, self.lblDirFullList)

        self.lblDirHint = QLabel(self.groupDirections)
        self.lblDirHint.setObjectName(u"lblDirHint")
        self.lblDirHint.setWordWrap(True)

        self.formDirections.setWidget(5, QFormLayout.ItemRole.SpanningRole, self.lblDirHint)


        self.verticalLayout_3.addWidget(self.groupDirections)

        self.toolBox.addItem(self.Wave, u"Wave directions")
        self.Calculation = QWidget()
        self.Calculation.setObjectName(u"Calculation")
        self.verticalLayout_5 = QVBoxLayout(self.Calculation)
        self.verticalLayout_5.setObjectName(u"verticalLayout_5")
        self.groupLid = QGroupBox(self.Calculation)
        self.groupLid.setObjectName(u"groupLid")
        self.formLid = QFormLayout(self.groupLid)
        self.formLid.setObjectName(u"formLid")
        self.lblLidCaption = QLabel(self.groupLid)
        self.lblLidCaption.setObjectName(u"lblLidCaption")

        self.formLid.setWidget(0, QFormLayout.ItemRole.LabelRole, self.lblLidCaption)

        self.comboLid = QComboBox(self.groupLid)
        self.comboLid.setObjectName(u"comboLid")

        self.formLid.setWidget(0, QFormLayout.ItemRole.FieldRole, self.comboLid)

        self.lblLidZCaption = QLabel(self.groupLid)
        self.lblLidZCaption.setObjectName(u"lblLidZCaption")

        self.formLid.setWidget(1, QFormLayout.ItemRole.LabelRole, self.lblLidZCaption)

        self.spinLidZ = QDoubleSpinBox(self.groupLid)
        self.spinLidZ.setObjectName(u"spinLidZ")
        self.spinLidZ.setEnabled(False)
        self.spinLidZ.setDecimals(3)
        self.spinLidZ.setMinimum(-100.000000000000000)
        self.spinLidZ.setMaximum(0.000000000000000)
        self.spinLidZ.setValue(-0.100000000000000)

        self.formLid.setWidget(1, QFormLayout.ItemRole.FieldRole, self.spinLidZ)

        self.lblLidInfo = QLabel(self.groupLid)
        self.lblLidInfo.setObjectName(u"lblLidInfo")
        self.lblLidInfo.setTextFormat(Qt.TextFormat.RichText)
        self.lblLidInfo.setWordWrap(True)

        self.formLid.setWidget(2, QFormLayout.ItemRole.SpanningRole, self.lblLidInfo)


        self.verticalLayout_5.addWidget(self.groupLid)

        self.groupParallel = QGroupBox(self.Calculation)
        self.groupParallel.setObjectName(u"groupParallel")
        self.formParallel = QFormLayout(self.groupParallel)
        self.formParallel.setObjectName(u"formParallel")
        self.lblWorkersCaption = QLabel(self.groupParallel)
        self.lblWorkersCaption.setObjectName(u"lblWorkersCaption")

        self.formParallel.setWidget(0, QFormLayout.ItemRole.LabelRole, self.lblWorkersCaption)

        self.spinWorkers = QSpinBox(self.groupParallel)
        self.spinWorkers.setObjectName(u"spinWorkers")
        self.spinWorkers.setMinimum(1)
        self.spinWorkers.setMaximum(64)
        self.spinWorkers.setValue(4)

        self.formParallel.setWidget(0, QFormLayout.ItemRole.FieldRole, self.spinWorkers)

        self.lblOmpCaption = QLabel(self.groupParallel)
        self.lblOmpCaption.setObjectName(u"lblOmpCaption")

        self.formParallel.setWidget(1, QFormLayout.ItemRole.LabelRole, self.lblOmpCaption)

        self.spinOmp = QSpinBox(self.groupParallel)
        self.spinOmp.setObjectName(u"spinOmp")
        self.spinOmp.setMinimum(1)
        self.spinOmp.setMaximum(64)
        self.spinOmp.setValue(1)

        self.formParallel.setWidget(1, QFormLayout.ItemRole.FieldRole, self.spinOmp)

        self.lblParallelHint = QLabel(self.groupParallel)
        self.lblParallelHint.setObjectName(u"lblParallelHint")
        self.lblParallelHint.setWordWrap(True)

        self.formParallel.setWidget(2, QFormLayout.ItemRole.SpanningRole, self.lblParallelHint)


        self.verticalLayout_5.addWidget(self.groupParallel)

        self.groupPlan = QGroupBox(self.Calculation)
        self.groupPlan.setObjectName(u"groupPlan")
        self.formPlan = QFormLayout(self.groupPlan)
        self.formPlan.setObjectName(u"formPlan")
        self.chkResume = QCheckBox(self.groupPlan)
        self.chkResume.setObjectName(u"chkResume")
        self.chkResume.setChecked(True)

        self.formPlan.setWidget(0, QFormLayout.ItemRole.SpanningRole, self.chkResume)

        self.lblPlanConditionsCaption = QLabel(self.groupPlan)
        self.lblPlanConditionsCaption.setObjectName(u"lblPlanConditionsCaption")

        self.formPlan.setWidget(1, QFormLayout.ItemRole.LabelRole, self.lblPlanConditionsCaption)

        self.lblPlanConditions = QLabel(self.groupPlan)
        self.lblPlanConditions.setObjectName(u"lblPlanConditions")
        self.lblPlanConditions.setTextFormat(Qt.TextFormat.RichText)
        self.lblPlanConditions.setWordWrap(True)

        self.formPlan.setWidget(1, QFormLayout.ItemRole.FieldRole, self.lblPlanConditions)

        self.lblPlanMeshesCaption = QLabel(self.groupPlan)
        self.lblPlanMeshesCaption.setObjectName(u"lblPlanMeshesCaption")

        self.formPlan.setWidget(2, QFormLayout.ItemRole.LabelRole, self.lblPlanMeshesCaption)

        self.lblPlanMeshes = QLabel(self.groupPlan)
        self.lblPlanMeshes.setObjectName(u"lblPlanMeshes")
        self.lblPlanMeshes.setTextFormat(Qt.TextFormat.RichText)
        self.lblPlanMeshes.setWordWrap(True)

        self.formPlan.setWidget(2, QFormLayout.ItemRole.FieldRole, self.lblPlanMeshes)

        self.lblPlanSolvesCaption = QLabel(self.groupPlan)
        self.lblPlanSolvesCaption.setObjectName(u"lblPlanSolvesCaption")

        self.formPlan.setWidget(3, QFormLayout.ItemRole.LabelRole, self.lblPlanSolvesCaption)

        self.lblPlanSolves = QLabel(self.groupPlan)
        self.lblPlanSolves.setObjectName(u"lblPlanSolves")
        self.lblPlanSolves.setTextFormat(Qt.TextFormat.RichText)
        self.lblPlanSolves.setWordWrap(True)

        self.formPlan.setWidget(3, QFormLayout.ItemRole.FieldRole, self.lblPlanSolves)

        self.lblPlanProblemsCaption = QLabel(self.groupPlan)
        self.lblPlanProblemsCaption.setObjectName(u"lblPlanProblemsCaption")

        self.formPlan.setWidget(4, QFormLayout.ItemRole.LabelRole, self.lblPlanProblemsCaption)

        self.lblPlanProblems = QLabel(self.groupPlan)
        self.lblPlanProblems.setObjectName(u"lblPlanProblems")
        self.lblPlanProblems.setTextFormat(Qt.TextFormat.RichText)
        self.lblPlanProblems.setWordWrap(True)

        self.formPlan.setWidget(4, QFormLayout.ItemRole.FieldRole, self.lblPlanProblems)

        self.lblPlanProblem = QLabel(self.groupPlan)
        self.lblPlanProblem.setObjectName(u"lblPlanProblem")
        self.lblPlanProblem.setTextFormat(Qt.TextFormat.RichText)
        self.lblPlanProblem.setWordWrap(True)

        self.formPlan.setWidget(5, QFormLayout.ItemRole.SpanningRole, self.lblPlanProblem)


        self.verticalLayout_5.addWidget(self.groupPlan)

        self.toolBox.addItem(self.Calculation, u"Calculation settings")
        self.Run = QWidget()
        self.Run.setObjectName(u"Run")
        self.gridLayout = QGridLayout(self.Run)
        self.gridLayout.setObjectName(u"gridLayout")
        self.groupRun = QGroupBox(self.Run)
        self.groupRun.setObjectName(u"groupRun")
        self.layoutRun = QVBoxLayout(self.groupRun)
        self.layoutRun.setObjectName(u"layoutRun")
        self.progressOverall = QProgressBar(self.groupRun)
        self.progressOverall.setObjectName(u"progressOverall")
        self.progressOverall.setValue(0)

        self.layoutRun.addWidget(self.progressOverall)

        self.progressSolve = QProgressBar(self.groupRun)
        self.progressSolve.setObjectName(u"progressSolve")
        self.progressSolve.setValue(0)

        self.layoutRun.addWidget(self.progressSolve)

        self.lblProgress = QLabel(self.groupRun)
        self.lblProgress.setObjectName(u"lblProgress")
        self.lblProgress.setTextFormat(Qt.TextFormat.RichText)
        self.lblProgress.setWordWrap(True)

        self.layoutRun.addWidget(self.lblProgress)

        self.textLog = QPlainTextEdit(self.groupRun)
        self.textLog.setObjectName(u"textLog")
        self.textLog.setMinimumSize(QSize(0, 120))
        self.textLog.setReadOnly(True)

        self.layoutRun.addWidget(self.textLog)


        self.gridLayout.addWidget(self.groupRun, 0, 0, 1, 3)

        self.lblFooterHint = QLabel(self.Run)
        self.lblFooterHint.setObjectName(u"lblFooterHint")
        self.lblFooterHint.setWordWrap(True)

        self.gridLayout.addWidget(self.lblFooterHint, 1, 0, 1, 3)

        self.btnStart = QPushButton(self.Run)
        self.btnStart.setObjectName(u"btnStart")

        self.gridLayout.addWidget(self.btnStart, 2, 0, 1, 1)

        self.btnStop = QPushButton(self.Run)
        self.btnStop.setObjectName(u"btnStop")
        self.btnStop.setEnabled(False)

        self.gridLayout.addWidget(self.btnStop, 2, 1, 1, 1)

        self.btnKill = QPushButton(self.Run)
        self.btnKill.setObjectName(u"btnKill")
        self.btnKill.setEnabled(False)

        self.gridLayout.addWidget(self.btnKill, 2, 2, 1, 1)

        self.toolBox.addItem(self.Run, u"Run")

        self.verticalLayout_4.addWidget(self.toolBox)

        self.layoutButtons = QHBoxLayout()
        self.layoutButtons.setObjectName(u"layoutButtons")
        self.btnLoadJob = QPushButton(DlgBatch)
        self.btnLoadJob.setObjectName(u"btnLoadJob")

        self.layoutButtons.addWidget(self.btnLoadJob)

        self.btnSaveJob = QPushButton(DlgBatch)
        self.btnSaveJob.setObjectName(u"btnSaveJob")

        self.layoutButtons.addWidget(self.btnSaveJob)

        self.spacerJob = QSpacerItem(24, 20, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)

        self.layoutButtons.addItem(self.spacerJob)

        self.spacerButtons = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.layoutButtons.addItem(self.spacerButtons)

        self.btnClose = QPushButton(DlgBatch)
        self.btnClose.setObjectName(u"btnClose")

        self.layoutButtons.addWidget(self.btnClose)


        self.verticalLayout_4.addLayout(self.layoutButtons)


        self.retranslateUi(DlgBatch)

        self.toolBox.setCurrentIndex(0)
        self.btnStart.setDefault(True)


        QMetaObject.connectSlotsByName(DlgBatch)
    # setupUi

    def retranslateUi(self, DlgBatch):
        DlgBatch.setWindowTitle(QCoreApplication.translate("DlgBatch", u"Batch", None))
        self.lblHeading.setText(QCoreApplication.translate("DlgBatch", u"\u2014", None))
        self.groupPhysical.setTitle(QCoreApplication.translate("DlgBatch", u"Physical conditions", None))
        self.lblDepthCaption.setText(QCoreApplication.translate("DlgBatch", u"Water depth [m]", None))
        self.chkInfiniteDepth.setText(QCoreApplication.translate("DlgBatch", u"Infinite depth", None))
        self.lblGCaption.setText(QCoreApplication.translate("DlgBatch", u"g [m/s\u00b2]", None))
        self.lblSpeedCaption.setText(QCoreApplication.translate("DlgBatch", u"Forward speed [m/s]", None))
        self.lblPhysicalHint.setText(QCoreApplication.translate("DlgBatch", u"One set for the whole job. There is no density: every solve runs at 1 t/m\u00b3 and the density is applied when a database is delivered.", None))
        self.groupConditions.setTitle(QCoreApplication.translate("DlgBatch", u"Floating conditions \u2014 the grid", None))
        self.chkCreateConditions.setText(QCoreApplication.translate("DlgBatch", u"Create the conditions below", None))
        self.lblZCaption.setText(QCoreApplication.translate("DlgBatch", u"z_origin [m]", None))
        self.lblZStep.setText(QCoreApplication.translate("DlgBatch", u"step", None))
        self.lblZTo.setText(QCoreApplication.translate("DlgBatch", u"to", None))
        self.lblZHint.setText(QCoreApplication.translate("DlgBatch", u"Height of the vessel origin above the waterplane, negative for a normally floating vessel. This is not the draft \u2014 the two differ by wherever the origin sits on the hull, which is what \"origin sits at\" on the library records.", None))
        self.lblHeelCaption.setText(QCoreApplication.translate("DlgBatch", u"Heel [\u00b0]", None))
        self.editHeels.setText(QCoreApplication.translate("DlgBatch", u"0", None))
        self.editHeels.setPlaceholderText(QCoreApplication.translate("DlgBatch", u"-1, 0, 1   or   -5..5..1", None))
        self.lblTrimCaption.setText(QCoreApplication.translate("DlgBatch", u"Trim [\u00b0]", None))
        self.editTrims.setText(QCoreApplication.translate("DlgBatch", u"0", None))
        self.editTrims.setPlaceholderText(QCoreApplication.translate("DlgBatch", u"-2, -1, 0, 1, 2   or   -2..2..1", None))
        self.lblAnglesHint.setText(QCoreApplication.translate("DlgBatch", u"Degrees, as everywhere on screen; slopes are what gets stored. Positive heel puts starboard down, positive trim puts the bow down. A heeled condition always gets a full mesh.", None))
        self.lblConditionGrid.setText(QCoreApplication.translate("DlgBatch", u"\u2014", None))
        self.toolBox.setItemText(self.toolBox.indexOf(self.page), QCoreApplication.translate("DlgBatch", u"Conditions", None))
        self.groupBands.setTitle(QCoreApplication.translate("DlgBatch", u"Meshes and the periods solved on them", None))
        self.lblBandsCaption.setText(QCoreApplication.translate("DlgBatch", u"One line per mesh: <b>pct \u2192 periods [s]</b>", None))
        self.editBands.setPlainText(QCoreApplication.translate("DlgBatch", u"1 -> 0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4\n"
"2 -> 4.5, 5, 5.5, 6, 6.5, 7, 7.5, 8, 8.5, 9, 9.5, 10\n"
"4 -> 11, 12, 15, 20", None))
        self.lblBandsHint.setText(QCoreApplication.translate("DlgBatch", u"Every line is built and solved for every condition. Short waves need panels that long waves do not, and solver cost is quadratic in the panel count \u2014 so a fine mesh carries the short end of the grid and a coarse one the long end. \":\" works as well as \"\u2192\", ranges may be written 4..20..0.5, and anything after \"#\" is a note.", None))
        self.lblBands.setText(QCoreApplication.translate("DlgBatch", u"\u2014", None))
        self.lblIterationsCaption.setText(QCoreApplication.translate("DlgBatch", u"Remesh iterations", None))
        self.lblTargetsCaption.setText(QCoreApplication.translate("DlgBatch", u"Apply to", None))
        self.lblTargets.setText(QCoreApplication.translate("DlgBatch", u"\u2014", None))
        self.toolBox.setItemText(self.toolBox.indexOf(self.page_2), QCoreApplication.translate("DlgBatch", u"Periods and Meshing", None))
        self.groupDirections.setTitle(QCoreApplication.translate("DlgBatch", u"Wave directions [\u00b0] \u2014 direction of travel", None))
        self.lblDirHalfCaption.setText(QCoreApplication.translate("DlgBatch", u"Half vessel", None))
        self.lblDirTo.setText(QCoreApplication.translate("DlgBatch", u"to", None))
        self.lblDirStep.setText(QCoreApplication.translate("DlgBatch", u"step", None))
        self.lblDirList.setText(QCoreApplication.translate("DlgBatch", u"\u2014", None))
        self.lblDirFullCaption.setText(QCoreApplication.translate("DlgBatch", u"Full vessel", None))
        self.lblDirFullTo.setText(QCoreApplication.translate("DlgBatch", u"to", None))
        self.lblDirFullStep.setText(QCoreApplication.translate("DlgBatch", u"step", None))
        self.lblDirFullList.setText(QCoreApplication.translate("DlgBatch", u"\u2014", None))
        self.lblDirHint.setText(QCoreApplication.translate("DlgBatch", u"Which grid a solve uses is derived from its mesh, never chosen. A symmetric hull at zero heel is meshed as a half vessel whose port side mirrors its starboard side, so half the circle is solved and the rest filled in exactly on delivery. Heel that same hull and the mesh is a full vessel with nothing to mirror \u2014 it needs the whole circle, or the delivered database is interpolated across what was never solved.", None))
        self.toolBox.setItemText(self.toolBox.indexOf(self.Wave), QCoreApplication.translate("DlgBatch", u"Wave directions", None))
        self.groupLid.setTitle(QCoreApplication.translate("DlgBatch", u"Irregular frequencies", None))
        self.lblLidCaption.setText(QCoreApplication.translate("DlgBatch", u"Lid", None))
        self.lblLidZCaption.setText(QCoreApplication.translate("DlgBatch", u"Lid z [m]", None))
        self.lblLidInfo.setText(QCoreApplication.translate("DlgBatch", u"\u2014", None))
        self.groupParallel.setTitle(QCoreApplication.translate("DlgBatch", u"Parallelism", None))
        self.lblWorkersCaption.setText(QCoreApplication.translate("DlgBatch", u"Worker processes", None))
        self.lblOmpCaption.setText(QCoreApplication.translate("DlgBatch", u"OpenMP threads each", None))
        self.lblParallelHint.setText(QCoreApplication.translate("DlgBatch", u"The two multiply. Each worker holds two dense complex matrices, so memory can bind before cores do \u2014 and the mesh does not exist until the batch builds it, so no figure can be shown for it here.", None))
        self.groupPlan.setTitle(QCoreApplication.translate("DlgBatch", u"What this job would do", None))
        self.chkResume.setText(QCoreApplication.translate("DlgBatch", u"Resume: reuse matching meshes, skip solves already covered", None))
        self.lblPlanConditionsCaption.setText(QCoreApplication.translate("DlgBatch", u"Conditions", None))
        self.lblPlanConditions.setText(QCoreApplication.translate("DlgBatch", u"\u2014", None))
        self.lblPlanMeshesCaption.setText(QCoreApplication.translate("DlgBatch", u"Meshes", None))
        self.lblPlanMeshes.setText(QCoreApplication.translate("DlgBatch", u"\u2014", None))
        self.lblPlanSolvesCaption.setText(QCoreApplication.translate("DlgBatch", u"Solves", None))
        self.lblPlanSolves.setText(QCoreApplication.translate("DlgBatch", u"\u2014", None))
        self.lblPlanProblemsCaption.setText(QCoreApplication.translate("DlgBatch", u"Problems", None))
        self.lblPlanProblems.setText(QCoreApplication.translate("DlgBatch", u"\u2014", None))
        self.lblPlanProblem.setText("")
        self.toolBox.setItemText(self.toolBox.indexOf(self.Calculation), QCoreApplication.translate("DlgBatch", u"Calculation settings", None))
        self.groupRun.setTitle(QCoreApplication.translate("DlgBatch", u"Run", None))
        self.progressSolve.setFormat(QCoreApplication.translate("DlgBatch", u"%v of %m frequencies", None))
        self.lblProgress.setText(QCoreApplication.translate("DlgBatch", u"Idle.", None))
        self.lblFooterHint.setText(QCoreApplication.translate("DlgBatch", u"A step that fails is logged and the batch carries on \u2014 one condition out of the water must not cost the other seven hundred. Run the same job again to continue where a night left off: conditions already there are reused, meshes at the same settings are reused, and solves an existing result already covers are skipped.", None))
        self.btnStart.setText(QCoreApplication.translate("DlgBatch", u"Start", None))
        self.btnStop.setText(QCoreApplication.translate("DlgBatch", u"Stop", None))
        self.btnKill.setText(QCoreApplication.translate("DlgBatch", u"Kill", None))
        self.toolBox.setItemText(self.toolBox.indexOf(self.Run), QCoreApplication.translate("DlgBatch", u"Run", None))
        self.btnLoadJob.setText(QCoreApplication.translate("DlgBatch", u"Load job\u2026", None))
        self.btnSaveJob.setText(QCoreApplication.translate("DlgBatch", u"Save job\u2026", None))
        self.btnClose.setText(QCoreApplication.translate("DlgBatch", u"Close", None))
    # retranslateUi

