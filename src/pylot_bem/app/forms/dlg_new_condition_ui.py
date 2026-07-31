# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'dlg_new_condition.ui'
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
    QLineEdit, QSizePolicy, QVBoxLayout, QWidget)

class Ui_DlgNewCondition(object):
    def setupUi(self, DlgNewCondition):
        if not DlgNewCondition.objectName():
            DlgNewCondition.setObjectName(u"DlgNewCondition")
        DlgNewCondition.resize(520, 420)
        self.root = QVBoxLayout(DlgNewCondition)
        self.root.setObjectName(u"root")
        self.groupHow = QGroupBox(DlgNewCondition)
        self.groupHow.setObjectName(u"groupHow")
        self.formHow = QFormLayout(self.groupHow)
        self.formHow.setObjectName(u"formHow")
        self.lblZOriginCaption = QLabel(self.groupHow)
        self.lblZOriginCaption.setObjectName(u"lblZOriginCaption")

        self.formHow.setWidget(0, QFormLayout.ItemRole.LabelRole, self.lblZOriginCaption)

        self.spinZOrigin = QDoubleSpinBox(self.groupHow)
        self.spinZOrigin.setObjectName(u"spinZOrigin")
        self.spinZOrigin.setDecimals(3)
        self.spinZOrigin.setMinimum(-10000.000000000000000)
        self.spinZOrigin.setMaximum(10000.000000000000000)
        self.spinZOrigin.setValue(-5.000000000000000)

        self.formHow.setWidget(0, QFormLayout.ItemRole.FieldRole, self.spinZOrigin)

        self.lblZOriginHint = QLabel(self.groupHow)
        self.lblZOriginHint.setObjectName(u"lblZOriginHint")
        self.lblZOriginHint.setWordWrap(True)

        self.formHow.setWidget(1, QFormLayout.ItemRole.SpanningRole, self.lblZOriginHint)

        self.lblHeelCaption = QLabel(self.groupHow)
        self.lblHeelCaption.setObjectName(u"lblHeelCaption")

        self.formHow.setWidget(2, QFormLayout.ItemRole.LabelRole, self.lblHeelCaption)

        self.spinHeel = QDoubleSpinBox(self.groupHow)
        self.spinHeel.setObjectName(u"spinHeel")
        self.spinHeel.setDecimals(3)
        self.spinHeel.setMinimum(-89.000000000000000)
        self.spinHeel.setMaximum(89.000000000000000)

        self.formHow.setWidget(2, QFormLayout.ItemRole.FieldRole, self.spinHeel)

        self.lblTrimCaption = QLabel(self.groupHow)
        self.lblTrimCaption.setObjectName(u"lblTrimCaption")

        self.formHow.setWidget(3, QFormLayout.ItemRole.LabelRole, self.lblTrimCaption)

        self.spinTrim = QDoubleSpinBox(self.groupHow)
        self.spinTrim.setObjectName(u"spinTrim")
        self.spinTrim.setDecimals(3)
        self.spinTrim.setMinimum(-89.000000000000000)
        self.spinTrim.setMaximum(89.000000000000000)

        self.formHow.setWidget(3, QFormLayout.ItemRole.FieldRole, self.spinTrim)

        self.lblLabelCaption = QLabel(self.groupHow)
        self.lblLabelCaption.setObjectName(u"lblLabelCaption")

        self.formHow.setWidget(4, QFormLayout.ItemRole.LabelRole, self.lblLabelCaption)

        self.editLabel = QLineEdit(self.groupHow)
        self.editLabel.setObjectName(u"editLabel")

        self.formHow.setWidget(4, QFormLayout.ItemRole.FieldRole, self.editLabel)

        self.lblIdCaption = QLabel(self.groupHow)
        self.lblIdCaption.setObjectName(u"lblIdCaption")

        self.formHow.setWidget(5, QFormLayout.ItemRole.LabelRole, self.lblIdCaption)

        self.editId = QLineEdit(self.groupHow)
        self.editId.setObjectName(u"editId")

        self.formHow.setWidget(5, QFormLayout.ItemRole.FieldRole, self.editId)

        self.lblLabelHint = QLabel(self.groupHow)
        self.lblLabelHint.setObjectName(u"lblLabelHint")
        self.lblLabelHint.setWordWrap(True)

        self.formHow.setWidget(6, QFormLayout.ItemRole.SpanningRole, self.lblLabelHint)


        self.root.addWidget(self.groupHow)

        self.groupDerived = QGroupBox(DlgNewCondition)
        self.groupDerived.setObjectName(u"groupDerived")
        self.formDerived = QFormLayout(self.groupDerived)
        self.formDerived.setObjectName(u"formDerived")
        self.lblApplicationPointCaption = QLabel(self.groupDerived)
        self.lblApplicationPointCaption.setObjectName(u"lblApplicationPointCaption")

        self.formDerived.setWidget(0, QFormLayout.ItemRole.LabelRole, self.lblApplicationPointCaption)

        self.lblApplicationPoint = QLabel(self.groupDerived)
        self.lblApplicationPoint.setObjectName(u"lblApplicationPoint")
        self.lblApplicationPoint.setWordWrap(True)
        self.lblApplicationPoint.setTextFormat(Qt.RichText)

        self.formDerived.setWidget(0, QFormLayout.ItemRole.FieldRole, self.lblApplicationPoint)

        self.lblSymmetryCaption = QLabel(self.groupDerived)
        self.lblSymmetryCaption.setObjectName(u"lblSymmetryCaption")

        self.formDerived.setWidget(1, QFormLayout.ItemRole.LabelRole, self.lblSymmetryCaption)

        self.lblSymmetry = QLabel(self.groupDerived)
        self.lblSymmetry.setObjectName(u"lblSymmetry")
        self.lblSymmetry.setWordWrap(True)
        self.lblSymmetry.setTextFormat(Qt.RichText)

        self.formDerived.setWidget(1, QFormLayout.ItemRole.FieldRole, self.lblSymmetry)

        self.lblSubmergedCaption = QLabel(self.groupDerived)
        self.lblSubmergedCaption.setObjectName(u"lblSubmergedCaption")

        self.formDerived.setWidget(2, QFormLayout.ItemRole.LabelRole, self.lblSubmergedCaption)

        self.lblSubmerged = QLabel(self.groupDerived)
        self.lblSubmerged.setObjectName(u"lblSubmerged")
        self.lblSubmerged.setWordWrap(True)
        self.lblSubmerged.setTextFormat(Qt.RichText)

        self.formDerived.setWidget(2, QFormLayout.ItemRole.FieldRole, self.lblSubmerged)


        self.root.addWidget(self.groupDerived)

        self.lblProblem = QLabel(DlgNewCondition)
        self.lblProblem.setObjectName(u"lblProblem")
        self.lblProblem.setWordWrap(True)
        self.lblProblem.setTextFormat(Qt.RichText)

        self.root.addWidget(self.lblProblem)

        self.buttonBox = QDialogButtonBox(DlgNewCondition)
        self.buttonBox.setObjectName(u"buttonBox")
        self.buttonBox.setOrientation(Qt.Horizontal)
        self.buttonBox.setStandardButtons(QDialogButtonBox.Cancel|QDialogButtonBox.Ok)

        self.root.addWidget(self.buttonBox)


        self.retranslateUi(DlgNewCondition)

        QMetaObject.connectSlotsByName(DlgNewCondition)
    # setupUi

    def retranslateUi(self, DlgNewCondition):
        DlgNewCondition.setWindowTitle(QCoreApplication.translate("DlgNewCondition", u"New floating condition", None))
        self.groupHow.setTitle(QCoreApplication.translate("DlgNewCondition", u"How the vessel floats", None))
        self.lblZOriginCaption.setText(QCoreApplication.translate("DlgNewCondition", u"z_origin [m]", None))
        self.lblZOriginHint.setText(QCoreApplication.translate("DlgNewCondition", u"The height of the vessel origin above the waterplane \u2014 negative for a normally floating vessel. This is not the naval draft: the two differ by wherever the origin sits on the hull.", None))
        self.lblHeelCaption.setText(QCoreApplication.translate("DlgNewCondition", u"Heel [deg]", None))
        self.lblTrimCaption.setText(QCoreApplication.translate("DlgNewCondition", u"Trim [deg]", None))
        self.lblLabelCaption.setText(QCoreApplication.translate("DlgNewCondition", u"Label", None))
        self.editLabel.setPlaceholderText(QCoreApplication.translate("DlgNewCondition", u"design draft", None))
        self.lblIdCaption.setText(QCoreApplication.translate("DlgNewCondition", u"Id", None))
        self.editId.setPlaceholderText(QCoreApplication.translate("DlgNewCondition", u"leave blank for a generated id", None))
        self.lblLabelHint.setText(QCoreApplication.translate("DlgNewCondition", u"Both are human display only and nothing parses either. The difference is that a label can be corrected afterwards and an id cannot \u2014 the id is what every other screen shows, and what meshes and results below will point at.", None))
        self.groupDerived.setTitle(QCoreApplication.translate("DlgNewCondition", u"What follows \u2014 derived", None))
        self.lblApplicationPointCaption.setText(QCoreApplication.translate("DlgNewCondition", u"Application point", None))
        self.lblApplicationPoint.setText(QCoreApplication.translate("DlgNewCondition", u"\u2014", None))
        self.lblSymmetryCaption.setText(QCoreApplication.translate("DlgNewCondition", u"Symmetry", None))
        self.lblSymmetry.setText(QCoreApplication.translate("DlgNewCondition", u"\u2014", None))
        self.lblSubmergedCaption.setText(QCoreApplication.translate("DlgNewCondition", u"Submerged", None))
        self.lblSubmerged.setText(QCoreApplication.translate("DlgNewCondition", u"\u2014", None))
        self.lblProblem.setText("")
    # retranslateUi

