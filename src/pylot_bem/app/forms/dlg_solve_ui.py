# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'dlg_solve.ui'
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
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox,
    QDialog, QDoubleSpinBox, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QListView,
    QListWidget, QListWidgetItem, QPlainTextEdit, QProgressBar,
    QPushButton, QSizePolicy, QSpacerItem, QSpinBox,
    QVBoxLayout, QWidget)

class Ui_DlgSolve(object):
    def setupUi(self, DlgSolve):
        if not DlgSolve.objectName():
            DlgSolve.setObjectName(u"DlgSolve")
        DlgSolve.resize(900, 720)
        self.root = QVBoxLayout(DlgSolve)
        self.root.setObjectName(u"root")
        self.lblHeading = QLabel(DlgSolve)
        self.lblHeading.setObjectName(u"lblHeading")
        self.lblHeading.setWordWrap(True)
        self.lblHeading.setTextFormat(Qt.RichText)

        self.root.addWidget(self.lblHeading)

        self.layoutColumns = QHBoxLayout()
        self.layoutColumns.setObjectName(u"layoutColumns")
        self.layoutLeft = QVBoxLayout()
        self.layoutLeft.setObjectName(u"layoutLeft")
        self.groupPeriods = QGroupBox(DlgSolve)
        self.groupPeriods.setObjectName(u"groupPeriods")
        self.formPeriods = QFormLayout(self.groupPeriods)
        self.formPeriods.setObjectName(u"formPeriods")
        self.lblPeriodFromCaption = QLabel(self.groupPeriods)
        self.lblPeriodFromCaption.setObjectName(u"lblPeriodFromCaption")

        self.formPeriods.setWidget(0, QFormLayout.ItemRole.LabelRole, self.lblPeriodFromCaption)

        self.spinPeriodFrom = QDoubleSpinBox(self.groupPeriods)
        self.spinPeriodFrom.setObjectName(u"spinPeriodFrom")
        self.spinPeriodFrom.setDecimals(2)
        self.spinPeriodFrom.setMinimum(0.100000000000000)
        self.spinPeriodFrom.setMaximum(1000.000000000000000)
        self.spinPeriodFrom.setValue(4.000000000000000)

        self.formPeriods.setWidget(0, QFormLayout.ItemRole.FieldRole, self.spinPeriodFrom)

        self.lblPeriodToCaption = QLabel(self.groupPeriods)
        self.lblPeriodToCaption.setObjectName(u"lblPeriodToCaption")

        self.formPeriods.setWidget(1, QFormLayout.ItemRole.LabelRole, self.lblPeriodToCaption)

        self.spinPeriodTo = QDoubleSpinBox(self.groupPeriods)
        self.spinPeriodTo.setObjectName(u"spinPeriodTo")
        self.spinPeriodTo.setDecimals(2)
        self.spinPeriodTo.setMinimum(0.100000000000000)
        self.spinPeriodTo.setMaximum(1000.000000000000000)
        self.spinPeriodTo.setValue(20.000000000000000)

        self.formPeriods.setWidget(1, QFormLayout.ItemRole.FieldRole, self.spinPeriodTo)

        self.lblPeriodStepCaption = QLabel(self.groupPeriods)
        self.lblPeriodStepCaption.setObjectName(u"lblPeriodStepCaption")

        self.formPeriods.setWidget(2, QFormLayout.ItemRole.LabelRole, self.lblPeriodStepCaption)

        self.spinPeriodStep = QDoubleSpinBox(self.groupPeriods)
        self.spinPeriodStep.setObjectName(u"spinPeriodStep")
        self.spinPeriodStep.setDecimals(2)
        self.spinPeriodStep.setMinimum(0.010000000000000)
        self.spinPeriodStep.setMaximum(1000.000000000000000)
        self.spinPeriodStep.setValue(4.000000000000000)

        self.formPeriods.setWidget(2, QFormLayout.ItemRole.FieldRole, self.spinPeriodStep)

        self.lblPeriodList = QLabel(self.groupPeriods)
        self.lblPeriodList.setObjectName(u"lblPeriodList")
        self.lblPeriodList.setWordWrap(True)
        self.lblPeriodList.setTextFormat(Qt.RichText)

        self.formPeriods.setWidget(3, QFormLayout.ItemRole.SpanningRole, self.lblPeriodList)

        self.lblPeriodHint = QLabel(self.groupPeriods)
        self.lblPeriodHint.setObjectName(u"lblPeriodHint")
        self.lblPeriodHint.setWordWrap(True)

        self.formPeriods.setWidget(4, QFormLayout.ItemRole.SpanningRole, self.lblPeriodHint)


        self.layoutLeft.addWidget(self.groupPeriods)

        self.groupDirections = QGroupBox(DlgSolve)
        self.groupDirections.setObjectName(u"groupDirections")
        self.formDirections = QFormLayout(self.groupDirections)
        self.formDirections.setObjectName(u"formDirections")
        self.lblDirFromCaption = QLabel(self.groupDirections)
        self.lblDirFromCaption.setObjectName(u"lblDirFromCaption")

        self.formDirections.setWidget(0, QFormLayout.ItemRole.LabelRole, self.lblDirFromCaption)

        self.spinDirFrom = QDoubleSpinBox(self.groupDirections)
        self.spinDirFrom.setObjectName(u"spinDirFrom")
        self.spinDirFrom.setDecimals(1)
        self.spinDirFrom.setMinimum(-360.000000000000000)
        self.spinDirFrom.setMaximum(360.000000000000000)
        self.spinDirFrom.setValue(0.000000000000000)

        self.formDirections.setWidget(0, QFormLayout.ItemRole.FieldRole, self.spinDirFrom)

        self.lblDirToCaption = QLabel(self.groupDirections)
        self.lblDirToCaption.setObjectName(u"lblDirToCaption")

        self.formDirections.setWidget(1, QFormLayout.ItemRole.LabelRole, self.lblDirToCaption)

        self.spinDirTo = QDoubleSpinBox(self.groupDirections)
        self.spinDirTo.setObjectName(u"spinDirTo")
        self.spinDirTo.setDecimals(1)
        self.spinDirTo.setMinimum(-360.000000000000000)
        self.spinDirTo.setMaximum(360.000000000000000)
        self.spinDirTo.setValue(180.000000000000000)

        self.formDirections.setWidget(1, QFormLayout.ItemRole.FieldRole, self.spinDirTo)

        self.lblDirStepCaption = QLabel(self.groupDirections)
        self.lblDirStepCaption.setObjectName(u"lblDirStepCaption")

        self.formDirections.setWidget(2, QFormLayout.ItemRole.LabelRole, self.lblDirStepCaption)

        self.spinDirStep = QDoubleSpinBox(self.groupDirections)
        self.spinDirStep.setObjectName(u"spinDirStep")
        self.spinDirStep.setDecimals(1)
        self.spinDirStep.setMinimum(0.100000000000000)
        self.spinDirStep.setMaximum(360.000000000000000)
        self.spinDirStep.setValue(45.000000000000000)

        self.formDirections.setWidget(2, QFormLayout.ItemRole.FieldRole, self.spinDirStep)

        self.lblDirList = QLabel(self.groupDirections)
        self.lblDirList.setObjectName(u"lblDirList")
        self.lblDirList.setWordWrap(True)
        self.lblDirList.setTextFormat(Qt.RichText)

        self.formDirections.setWidget(3, QFormLayout.ItemRole.SpanningRole, self.lblDirList)


        self.layoutLeft.addWidget(self.groupDirections)


        self.layoutColumns.addLayout(self.layoutLeft)

        self.layoutRight = QVBoxLayout()
        self.layoutRight.setObjectName(u"layoutRight")
        self.groupPhysical = QGroupBox(DlgSolve)
        self.groupPhysical.setObjectName(u"groupPhysical")
        self.formPhysical = QFormLayout(self.groupPhysical)
        self.formPhysical.setObjectName(u"formPhysical")
        self.lblDepthCaption = QLabel(self.groupPhysical)
        self.lblDepthCaption.setObjectName(u"lblDepthCaption")

        self.formPhysical.setWidget(0, QFormLayout.ItemRole.LabelRole, self.lblDepthCaption)

        self.layoutDepth = QHBoxLayout()
        self.layoutDepth.setObjectName(u"layoutDepth")
        self.chkInfiniteDepth = QCheckBox(self.groupPhysical)
        self.chkInfiniteDepth.setObjectName(u"chkInfiniteDepth")
        self.chkInfiniteDepth.setChecked(True)

        self.layoutDepth.addWidget(self.chkInfiniteDepth)

        self.spinDepth = QDoubleSpinBox(self.groupPhysical)
        self.spinDepth.setObjectName(u"spinDepth")
        self.spinDepth.setEnabled(False)
        self.spinDepth.setDecimals(2)
        self.spinDepth.setMinimum(0.100000000000000)
        self.spinDepth.setMaximum(100000.000000000000000)
        self.spinDepth.setValue(50.000000000000000)

        self.layoutDepth.addWidget(self.spinDepth)


        self.formPhysical.setLayout(0, QFormLayout.ItemRole.FieldRole, self.layoutDepth)

        self.lblSpeedCaption = QLabel(self.groupPhysical)
        self.lblSpeedCaption.setObjectName(u"lblSpeedCaption")

        self.formPhysical.setWidget(1, QFormLayout.ItemRole.LabelRole, self.lblSpeedCaption)

        self.spinSpeed = QDoubleSpinBox(self.groupPhysical)
        self.spinSpeed.setObjectName(u"spinSpeed")
        self.spinSpeed.setDecimals(2)
        self.spinSpeed.setMaximum(100.000000000000000)

        self.formPhysical.setWidget(1, QFormLayout.ItemRole.FieldRole, self.spinSpeed)

        self.lblGCaption = QLabel(self.groupPhysical)
        self.lblGCaption.setObjectName(u"lblGCaption")

        self.formPhysical.setWidget(2, QFormLayout.ItemRole.LabelRole, self.lblGCaption)

        self.spinG = QDoubleSpinBox(self.groupPhysical)
        self.spinG.setObjectName(u"spinG")
        self.spinG.setDecimals(3)
        self.spinG.setMinimum(0.100000000000000)
        self.spinG.setMaximum(100.000000000000000)
        self.spinG.setSingleStep(0.010000000000000)
        self.spinG.setValue(9.810000000000000)

        self.formPhysical.setWidget(2, QFormLayout.ItemRole.FieldRole, self.spinG)

        self.lblDensityNote = QLabel(self.groupPhysical)
        self.lblDensityNote.setObjectName(u"lblDensityNote")
        self.lblDensityNote.setWordWrap(True)
        self.lblDensityNote.setTextFormat(Qt.RichText)

        self.formPhysical.setWidget(3, QFormLayout.ItemRole.SpanningRole, self.lblDensityNote)


        self.layoutRight.addWidget(self.groupPhysical)

        self.groupLid = QGroupBox(DlgSolve)
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
        self.spinLidZ.setMinimum(-1000.000000000000000)
        self.spinLidZ.setMaximum(0.000000000000000)
        self.spinLidZ.setSingleStep(0.100000000000000)
        self.spinLidZ.setValue(-0.100000000000000)

        self.formLid.setWidget(1, QFormLayout.ItemRole.FieldRole, self.spinLidZ)

        self.lblLidInfo = QLabel(self.groupLid)
        self.lblLidInfo.setObjectName(u"lblLidInfo")
        self.lblLidInfo.setWordWrap(True)
        self.lblLidInfo.setTextFormat(Qt.RichText)

        self.formLid.setWidget(2, QFormLayout.ItemRole.SpanningRole, self.lblLidInfo)


        self.layoutRight.addWidget(self.groupLid)

        self.groupIdentity = QGroupBox(DlgSolve)
        self.groupIdentity.setObjectName(u"groupIdentity")
        self.formIdentity = QFormLayout(self.groupIdentity)
        self.formIdentity.setObjectName(u"formIdentity")
        self.lblIdCaption = QLabel(self.groupIdentity)
        self.lblIdCaption.setObjectName(u"lblIdCaption")

        self.formIdentity.setWidget(0, QFormLayout.ItemRole.LabelRole, self.lblIdCaption)

        self.editId = QLineEdit(self.groupIdentity)
        self.editId.setObjectName(u"editId")

        self.formIdentity.setWidget(0, QFormLayout.ItemRole.FieldRole, self.editId)

        self.lblIdProblem = QLabel(self.groupIdentity)
        self.lblIdProblem.setObjectName(u"lblIdProblem")
        self.lblIdProblem.setWordWrap(True)
        self.lblIdProblem.setTextFormat(Qt.RichText)

        self.formIdentity.setWidget(1, QFormLayout.ItemRole.SpanningRole, self.lblIdProblem)


        self.layoutRight.addWidget(self.groupIdentity)

        self.groupParallel = QGroupBox(DlgSolve)
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

        self.formParallel.setWidget(0, QFormLayout.ItemRole.FieldRole, self.spinWorkers)

        self.lblOmpCaption = QLabel(self.groupParallel)
        self.lblOmpCaption.setObjectName(u"lblOmpCaption")

        self.formParallel.setWidget(1, QFormLayout.ItemRole.LabelRole, self.lblOmpCaption)

        self.spinOmp = QSpinBox(self.groupParallel)
        self.spinOmp.setObjectName(u"spinOmp")
        self.spinOmp.setMinimum(1)
        self.spinOmp.setMaximum(64)

        self.formParallel.setWidget(1, QFormLayout.ItemRole.FieldRole, self.spinOmp)


        self.layoutRight.addWidget(self.groupParallel)


        self.layoutColumns.addLayout(self.layoutRight)


        self.root.addLayout(self.layoutColumns)

        self.groupCost = QGroupBox(DlgSolve)
        self.groupCost.setObjectName(u"groupCost")
        self.formCost = QFormLayout(self.groupCost)
        self.formCost.setObjectName(u"formCost")
        self.lblProblemsCaption = QLabel(self.groupCost)
        self.lblProblemsCaption.setObjectName(u"lblProblemsCaption")

        self.formCost.setWidget(0, QFormLayout.ItemRole.LabelRole, self.lblProblemsCaption)

        self.lblCostProblems = QLabel(self.groupCost)
        self.lblCostProblems.setObjectName(u"lblCostProblems")
        self.lblCostProblems.setTextFormat(Qt.RichText)

        self.formCost.setWidget(0, QFormLayout.ItemRole.FieldRole, self.lblCostProblems)

        self.lblPanelsCaption = QLabel(self.groupCost)
        self.lblPanelsCaption.setObjectName(u"lblPanelsCaption")

        self.formCost.setWidget(1, QFormLayout.ItemRole.LabelRole, self.lblPanelsCaption)

        self.lblCostPanels = QLabel(self.groupCost)
        self.lblCostPanels.setObjectName(u"lblCostPanels")
        self.lblCostPanels.setTextFormat(Qt.RichText)

        self.formCost.setWidget(1, QFormLayout.ItemRole.FieldRole, self.lblCostPanels)

        self.lblMemoryCaption = QLabel(self.groupCost)
        self.lblMemoryCaption.setObjectName(u"lblMemoryCaption")

        self.formCost.setWidget(2, QFormLayout.ItemRole.LabelRole, self.lblMemoryCaption)

        self.lblCostMemory = QLabel(self.groupCost)
        self.lblCostMemory.setObjectName(u"lblCostMemory")
        self.lblCostMemory.setTextFormat(Qt.RichText)

        self.formCost.setWidget(2, QFormLayout.ItemRole.FieldRole, self.lblCostMemory)

        self.lblReliableCaption = QLabel(self.groupCost)
        self.lblReliableCaption.setObjectName(u"lblReliableCaption")

        self.formCost.setWidget(3, QFormLayout.ItemRole.LabelRole, self.lblReliableCaption)

        self.lblCostReliable = QLabel(self.groupCost)
        self.lblCostReliable.setObjectName(u"lblCostReliable")
        self.lblCostReliable.setWordWrap(True)
        self.lblCostReliable.setTextFormat(Qt.RichText)

        self.formCost.setWidget(3, QFormLayout.ItemRole.FieldRole, self.lblCostReliable)


        self.root.addWidget(self.groupCost)

        self.groupRun = QGroupBox(DlgSolve)
        self.groupRun.setObjectName(u"groupRun")
        self.layoutRun = QVBoxLayout(self.groupRun)
        self.layoutRun.setObjectName(u"layoutRun")
        self.progressBar = QProgressBar(self.groupRun)
        self.progressBar.setObjectName(u"progressBar")
        self.progressBar.setValue(0)

        self.layoutRun.addWidget(self.progressBar)

        self.lblProgress = QLabel(self.groupRun)
        self.lblProgress.setObjectName(u"lblProgress")
        self.lblProgress.setWordWrap(True)
        self.lblProgress.setTextFormat(Qt.RichText)

        self.layoutRun.addWidget(self.lblProgress)

        self.listGrid = QListWidget(self.groupRun)
        self.listGrid.setObjectName(u"listGrid")
        self.listGrid.setMaximumSize(QSize(16777215, 80))
        self.listGrid.setFlow(QListView.LeftToRight)
        self.listGrid.setProperty(u"isWrapping", True)
        self.listGrid.setResizeMode(QListView.Adjust)
        self.listGrid.setSelectionMode(QAbstractItemView.NoSelection)

        self.layoutRun.addWidget(self.listGrid)

        self.textLog = QPlainTextEdit(self.groupRun)
        self.textLog.setObjectName(u"textLog")
        self.textLog.setMaximumSize(QSize(16777215, 110))
        self.textLog.setReadOnly(True)

        self.layoutRun.addWidget(self.textLog)

        self.lblProgressHint = QLabel(self.groupRun)
        self.lblProgressHint.setObjectName(u"lblProgressHint")
        self.lblProgressHint.setWordWrap(True)

        self.layoutRun.addWidget(self.lblProgressHint)


        self.root.addWidget(self.groupRun)

        self.layoutButtons = QHBoxLayout()
        self.layoutButtons.setObjectName(u"layoutButtons")
        self.btnStart = QPushButton(DlgSolve)
        self.btnStart.setObjectName(u"btnStart")

        self.layoutButtons.addWidget(self.btnStart)

        self.btnStop = QPushButton(DlgSolve)
        self.btnStop.setObjectName(u"btnStop")
        self.btnStop.setEnabled(False)

        self.layoutButtons.addWidget(self.btnStop)

        self.btnKill = QPushButton(DlgSolve)
        self.btnKill.setObjectName(u"btnKill")
        self.btnKill.setEnabled(False)

        self.layoutButtons.addWidget(self.btnKill)

        self.spacerButtons = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.layoutButtons.addItem(self.spacerButtons)

        self.btnClose = QPushButton(DlgSolve)
        self.btnClose.setObjectName(u"btnClose")

        self.layoutButtons.addWidget(self.btnClose)


        self.root.addLayout(self.layoutButtons)


        self.retranslateUi(DlgSolve)

        self.btnStart.setDefault(True)


        QMetaObject.connectSlotsByName(DlgSolve)
    # setupUi

    def retranslateUi(self, DlgSolve):
        DlgSolve.setWindowTitle(QCoreApplication.translate("DlgSolve", u"Solve", None))
        self.lblHeading.setText(QCoreApplication.translate("DlgSolve", u"\u2014", None))
        self.groupPeriods.setTitle(QCoreApplication.translate("DlgSolve", u"Wave periods [s]", None))
        self.lblPeriodFromCaption.setText(QCoreApplication.translate("DlgSolve", u"From", None))
        self.lblPeriodToCaption.setText(QCoreApplication.translate("DlgSolve", u"To", None))
        self.lblPeriodStepCaption.setText(QCoreApplication.translate("DlgSolve", u"Step", None))
        self.lblPeriodList.setText(QCoreApplication.translate("DlgSolve", u"\u2014", None))
        self.lblPeriodHint.setText(QCoreApplication.translate("DlgSolve", u"Entered as periods and stored as omega. Solved longest period first \u2014 ascending period is descending omega.", None))
        self.groupDirections.setTitle(QCoreApplication.translate("DlgSolve", u"Wave directions [deg]", None))
        self.lblDirFromCaption.setText(QCoreApplication.translate("DlgSolve", u"From", None))
        self.lblDirToCaption.setText(QCoreApplication.translate("DlgSolve", u"To", None))
        self.lblDirStepCaption.setText(QCoreApplication.translate("DlgSolve", u"Step", None))
        self.lblDirList.setText(QCoreApplication.translate("DlgSolve", u"\u2014", None))
        self.groupPhysical.setTitle(QCoreApplication.translate("DlgSolve", u"Physical conditions", None))
        self.lblDepthCaption.setText(QCoreApplication.translate("DlgSolve", u"Water depth [m]", None))
        self.chkInfiniteDepth.setText(QCoreApplication.translate("DlgSolve", u"infinite", None))
        self.lblSpeedCaption.setText(QCoreApplication.translate("DlgSolve", u"Forward speed [m/s]", None))
        self.lblGCaption.setText(QCoreApplication.translate("DlgSolve", u"g [m/s\u00b2]", None))
        self.lblDensityNote.setText(QCoreApplication.translate("DlgSolve", u"<b>No water density here.</b> Results scale exactly linearly with it, so every solve runs at 1 t/m\u00b3 and the density is chosen when a database is delivered. One solve then serves salt water, fresh water and anything else.", None))
        self.groupLid.setTitle(QCoreApplication.translate("DlgSolve", u"Irregular frequencies", None))
        self.lblLidCaption.setText(QCoreApplication.translate("DlgSolve", u"Lid", None))
        self.lblLidZCaption.setText(QCoreApplication.translate("DlgSolve", u"Lid depth [m]", None))
        self.lblLidInfo.setText(QCoreApplication.translate("DlgSolve", u"\u2014", None))
        self.groupIdentity.setTitle(QCoreApplication.translate("DlgSolve", u"Identity", None))
        self.lblIdCaption.setText(QCoreApplication.translate("DlgSolve", u"Result id", None))
        self.editId.setPlaceholderText(QCoreApplication.translate("DlgSolve", u"leave blank for a generated id", None))
        self.lblIdProblem.setText("")
        self.groupParallel.setTitle(QCoreApplication.translate("DlgSolve", u"Parallelism", None))
        self.lblWorkersCaption.setText(QCoreApplication.translate("DlgSolve", u"Worker processes", None))
        self.lblOmpCaption.setText(QCoreApplication.translate("DlgSolve", u"OpenMP threads each", None))
        self.groupCost.setTitle(QCoreApplication.translate("DlgSolve", u"Before you start", None))
        self.lblProblemsCaption.setText(QCoreApplication.translate("DlgSolve", u"Problems", None))
        self.lblCostProblems.setText(QCoreApplication.translate("DlgSolve", u"\u2014", None))
        self.lblPanelsCaption.setText(QCoreApplication.translate("DlgSolve", u"Panels solved", None))
        self.lblCostPanels.setText(QCoreApplication.translate("DlgSolve", u"\u2014", None))
        self.lblMemoryCaption.setText(QCoreApplication.translate("DlgSolve", u"Peak memory", None))
        self.lblCostMemory.setText(QCoreApplication.translate("DlgSolve", u"\u2014", None))
        self.lblReliableCaption.setText(QCoreApplication.translate("DlgSolve", u"Mesh is reliable above", None))
        self.lblCostReliable.setText(QCoreApplication.translate("DlgSolve", u"\u2014", None))
        self.groupRun.setTitle(QCoreApplication.translate("DlgSolve", u"Running", None))
        self.lblProgress.setText(QCoreApplication.translate("DlgSolve", u"Idle.", None))
        self.lblProgressHint.setText(QCoreApplication.translate("DlgSolve", u"Progress is per frequency, never per problem: the first problem at each frequency pays the whole matrix assembly and the rest are nearly free. Under several workers the completed set can have holes, which is why the grid is shown and not just a count.", None))
        self.btnStart.setText(QCoreApplication.translate("DlgSolve", u"Start", None))
        self.btnStop.setText(QCoreApplication.translate("DlgSolve", u"Stop", None))
        self.btnKill.setText(QCoreApplication.translate("DlgSolve", u"Kill", None))
        self.btnClose.setText(QCoreApplication.translate("DlgSolve", u"Close", None))
    # retranslateUi

