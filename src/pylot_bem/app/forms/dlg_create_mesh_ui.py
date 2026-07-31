# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'dlg_create_mesh.ui'
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
    QDoubleSpinBox, QFormLayout, QGroupBox, QLabel,
    QLineEdit, QSizePolicy, QSpinBox, QVBoxLayout,
    QWidget)

class Ui_DlgCreateMesh(object):
    def setupUi(self, DlgCreateMesh):
        if not DlgCreateMesh.objectName():
            DlgCreateMesh.setObjectName(u"DlgCreateMesh")
        DlgCreateMesh.resize(460, 330)
        self.root = QVBoxLayout(DlgCreateMesh)
        self.root.setObjectName(u"root")
        self.lblHeading = QLabel(DlgCreateMesh)
        self.lblHeading.setObjectName(u"lblHeading")
        self.lblHeading.setWordWrap(True)
        self.lblHeading.setTextFormat(Qt.RichText)

        self.root.addWidget(self.lblHeading)

        self.groupIdentity = QGroupBox(DlgCreateMesh)
        self.groupIdentity.setObjectName(u"groupIdentity")
        self.formIdentity = QFormLayout(self.groupIdentity)
        self.formIdentity.setObjectName(u"formIdentity")
        self.lblIdCaption = QLabel(self.groupIdentity)
        self.lblIdCaption.setObjectName(u"lblIdCaption")

        self.formIdentity.setWidget(0, QFormLayout.ItemRole.LabelRole, self.lblIdCaption)

        self.editId = QLineEdit(self.groupIdentity)
        self.editId.setObjectName(u"editId")

        self.formIdentity.setWidget(0, QFormLayout.ItemRole.FieldRole, self.editId)

        self.lblIdHint = QLabel(self.groupIdentity)
        self.lblIdHint.setObjectName(u"lblIdHint")
        self.lblIdHint.setWordWrap(True)

        self.formIdentity.setWidget(1, QFormLayout.ItemRole.SpanningRole, self.lblIdHint)

        self.lblIdProblem = QLabel(self.groupIdentity)
        self.lblIdProblem.setObjectName(u"lblIdProblem")
        self.lblIdProblem.setWordWrap(True)
        self.lblIdProblem.setTextFormat(Qt.RichText)

        self.formIdentity.setWidget(2, QFormLayout.ItemRole.SpanningRole, self.lblIdProblem)


        self.root.addWidget(self.groupIdentity)

        self.groupSettings = QGroupBox(DlgCreateMesh)
        self.groupSettings.setObjectName(u"groupSettings")
        self.formSettings = QFormLayout(self.groupSettings)
        self.formSettings.setObjectName(u"formSettings")
        self.lblPctCaption = QLabel(self.groupSettings)
        self.lblPctCaption.setObjectName(u"lblPctCaption")

        self.formSettings.setWidget(0, QFormLayout.ItemRole.LabelRole, self.lblPctCaption)

        self.spinPct = QDoubleSpinBox(self.groupSettings)
        self.spinPct.setObjectName(u"spinPct")
        self.spinPct.setDecimals(2)
        self.spinPct.setMinimum(0.010000000000000)
        self.spinPct.setMaximum(100.000000000000000)
        self.spinPct.setSingleStep(0.500000000000000)
        self.spinPct.setValue(2.000000000000000)

        self.formSettings.setWidget(0, QFormLayout.ItemRole.FieldRole, self.spinPct)

        self.lblIterationsCaption = QLabel(self.groupSettings)
        self.lblIterationsCaption.setObjectName(u"lblIterationsCaption")

        self.formSettings.setWidget(1, QFormLayout.ItemRole.LabelRole, self.lblIterationsCaption)

        self.spinIterations = QSpinBox(self.groupSettings)
        self.spinIterations.setObjectName(u"spinIterations")
        self.spinIterations.setMinimum(1)
        self.spinIterations.setMaximum(500)
        self.spinIterations.setValue(20)

        self.formSettings.setWidget(1, QFormLayout.ItemRole.FieldRole, self.spinIterations)

        self.lblPctHint = QLabel(self.groupSettings)
        self.lblPctHint.setObjectName(u"lblPctHint")
        self.lblPctHint.setWordWrap(True)

        self.formSettings.setWidget(2, QFormLayout.ItemRole.SpanningRole, self.lblPctHint)


        self.root.addWidget(self.groupSettings)

        self.groupSymmetry = QGroupBox(DlgCreateMesh)
        self.groupSymmetry.setObjectName(u"groupSymmetry")
        self.layoutSymmetry = QVBoxLayout(self.groupSymmetry)
        self.layoutSymmetry.setObjectName(u"layoutSymmetry")
        self.lblSymmetry = QLabel(self.groupSymmetry)
        self.lblSymmetry.setObjectName(u"lblSymmetry")
        self.lblSymmetry.setWordWrap(True)
        self.lblSymmetry.setTextFormat(Qt.RichText)

        self.layoutSymmetry.addWidget(self.lblSymmetry)

        self.lblSymmetryHint = QLabel(self.groupSymmetry)
        self.lblSymmetryHint.setObjectName(u"lblSymmetryHint")
        self.lblSymmetryHint.setWordWrap(True)

        self.layoutSymmetry.addWidget(self.lblSymmetryHint)


        self.root.addWidget(self.groupSymmetry)

        self.lblFooterHint = QLabel(DlgCreateMesh)
        self.lblFooterHint.setObjectName(u"lblFooterHint")
        self.lblFooterHint.setWordWrap(True)

        self.root.addWidget(self.lblFooterHint)

        self.buttonBox = QDialogButtonBox(DlgCreateMesh)
        self.buttonBox.setObjectName(u"buttonBox")
        self.buttonBox.setOrientation(Qt.Horizontal)
        self.buttonBox.setStandardButtons(QDialogButtonBox.Cancel|QDialogButtonBox.Ok)

        self.root.addWidget(self.buttonBox)


        self.retranslateUi(DlgCreateMesh)

        QMetaObject.connectSlotsByName(DlgCreateMesh)
    # setupUi

    def retranslateUi(self, DlgCreateMesh):
        DlgCreateMesh.setWindowTitle(QCoreApplication.translate("DlgCreateMesh", u"Create mesh", None))
        self.lblHeading.setText(QCoreApplication.translate("DlgCreateMesh", u"\u2014", None))
        self.groupIdentity.setTitle(QCoreApplication.translate("DlgCreateMesh", u"Identity", None))
        self.lblIdCaption.setText(QCoreApplication.translate("DlgCreateMesh", u"Id", None))
        self.editId.setPlaceholderText(QCoreApplication.translate("DlgCreateMesh", u"leave blank for a generated id", None))
        self.lblIdHint.setText(QCoreApplication.translate("DlgCreateMesh", u"Your own name for this mesh, if you want one \u2014 it is what every other screen shows. Fixed once the mesh exists, and nothing anywhere parses it, so it carries no meaning beyond what you read into it.", None))
        self.lblIdProblem.setText("")
        self.groupSettings.setTitle(QCoreApplication.translate("DlgCreateMesh", u"Regrid", None))
        self.lblPctCaption.setText(QCoreApplication.translate("DlgCreateMesh", u"pct [%]", None))
        self.lblIterationsCaption.setText(QCoreApplication.translate("DlgCreateMesh", u"Iterations", None))
        self.lblPctHint.setText(QCoreApplication.translate("DlgCreateMesh", u"Lower pct is finer. Solver cost is quadratic in the panel count and its factorisation is cubic, so this is the knob that decides seconds versus minutes.", None))
        self.groupSymmetry.setTitle(QCoreApplication.translate("DlgCreateMesh", u"Symmetry \u2014 derived", None))
        self.lblSymmetry.setText(QCoreApplication.translate("DlgCreateMesh", u"\u2014", None))
        self.lblSymmetryHint.setText(QCoreApplication.translate("DlgCreateMesh", u"Derived from the condition, never chosen. A heeled condition gets a full mesh whatever the hull is.", None))
        self.lblFooterHint.setText(QCoreApplication.translate("DlgCreateMesh", u"A mesh cannot be changed afterwards \u2014 remove it and create another. Its panel count, memory and reliable period are shown once it exists; they follow from the regrid and cannot be known before it runs.", None))
    # retranslateUi

