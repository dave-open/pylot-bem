# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'prop_condition.ui'
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

class Ui_PropCondition(object):
    def setupUi(self, PropCondition):
        if not PropCondition.objectName():
            PropCondition.setObjectName(u"PropCondition")
        self.root = QVBoxLayout(PropCondition)
        self.root.setObjectName(u"root")
        self.groupIdentity = QGroupBox(PropCondition)
        self.groupIdentity.setObjectName(u"groupIdentity")
        self.formIdentity = QFormLayout(self.groupIdentity)
        self.formIdentity.setObjectName(u"formIdentity")
        self.lblLabelCaption = QLabel(self.groupIdentity)
        self.lblLabelCaption.setObjectName(u"lblLabelCaption")

        self.formIdentity.setWidget(0, QFormLayout.ItemRole.LabelRole, self.lblLabelCaption)

        self.editLabel = QLineEdit(self.groupIdentity)
        self.editLabel.setObjectName(u"editLabel")

        self.formIdentity.setWidget(0, QFormLayout.ItemRole.FieldRole, self.editLabel)

        self.lblIdCaption = QLabel(self.groupIdentity)
        self.lblIdCaption.setObjectName(u"lblIdCaption")

        self.formIdentity.setWidget(1, QFormLayout.ItemRole.LabelRole, self.lblIdCaption)

        self.lblId = QLabel(self.groupIdentity)
        self.lblId.setObjectName(u"lblId")
        self.lblId.setTextFormat(Qt.RichText)
        self.lblId.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.formIdentity.setWidget(1, QFormLayout.ItemRole.FieldRole, self.lblId)

        self.btnApplyLabel = QPushButton(self.groupIdentity)
        self.btnApplyLabel.setObjectName(u"btnApplyLabel")

        self.formIdentity.setWidget(2, QFormLayout.ItemRole.FieldRole, self.btnApplyLabel)


        self.root.addWidget(self.groupIdentity)

        self.groupFloating = QGroupBox(PropCondition)
        self.groupFloating.setObjectName(u"groupFloating")
        self.formFloating = QFormLayout(self.groupFloating)
        self.formFloating.setObjectName(u"formFloating")
        self.lblZOriginCaption = QLabel(self.groupFloating)
        self.lblZOriginCaption.setObjectName(u"lblZOriginCaption")

        self.formFloating.setWidget(0, QFormLayout.ItemRole.LabelRole, self.lblZOriginCaption)

        self.lblZOrigin = QLabel(self.groupFloating)
        self.lblZOrigin.setObjectName(u"lblZOrigin")
        self.lblZOrigin.setTextFormat(Qt.RichText)

        self.formFloating.setWidget(0, QFormLayout.ItemRole.FieldRole, self.lblZOrigin)

        self.lblHeelCaption = QLabel(self.groupFloating)
        self.lblHeelCaption.setObjectName(u"lblHeelCaption")

        self.formFloating.setWidget(1, QFormLayout.ItemRole.LabelRole, self.lblHeelCaption)

        self.lblHeel = QLabel(self.groupFloating)
        self.lblHeel.setObjectName(u"lblHeel")
        self.lblHeel.setTextFormat(Qt.RichText)

        self.formFloating.setWidget(1, QFormLayout.ItemRole.FieldRole, self.lblHeel)

        self.lblTrimCaption = QLabel(self.groupFloating)
        self.lblTrimCaption.setObjectName(u"lblTrimCaption")

        self.formFloating.setWidget(2, QFormLayout.ItemRole.LabelRole, self.lblTrimCaption)

        self.lblTrim = QLabel(self.groupFloating)
        self.lblTrim.setObjectName(u"lblTrim")
        self.lblTrim.setTextFormat(Qt.RichText)

        self.formFloating.setWidget(2, QFormLayout.ItemRole.FieldRole, self.lblTrim)

        self.lblConditionNote = QLabel(self.groupFloating)
        self.lblConditionNote.setObjectName(u"lblConditionNote")
        self.lblConditionNote.setWordWrap(True)

        self.formFloating.setWidget(3, QFormLayout.ItemRole.SpanningRole, self.lblConditionNote)


        self.root.addWidget(self.groupFloating)

        self.groupDerived = QGroupBox(PropCondition)
        self.groupDerived.setObjectName(u"groupDerived")
        self.formDerived = QFormLayout(self.groupDerived)
        self.formDerived.setObjectName(u"formDerived")
        self.lblApplicationPointCaption = QLabel(self.groupDerived)
        self.lblApplicationPointCaption.setObjectName(u"lblApplicationPointCaption")

        self.formDerived.setWidget(0, QFormLayout.ItemRole.LabelRole, self.lblApplicationPointCaption)

        self.lblApplicationPoint = QLabel(self.groupDerived)
        self.lblApplicationPoint.setObjectName(u"lblApplicationPoint")
        self.lblApplicationPoint.setTextFormat(Qt.RichText)
        self.lblApplicationPoint.setWordWrap(True)

        self.formDerived.setWidget(0, QFormLayout.ItemRole.FieldRole, self.lblApplicationPoint)

        self.lblSymmetryCaption = QLabel(self.groupDerived)
        self.lblSymmetryCaption.setObjectName(u"lblSymmetryCaption")

        self.formDerived.setWidget(1, QFormLayout.ItemRole.LabelRole, self.lblSymmetryCaption)

        self.lblSymmetry = QLabel(self.groupDerived)
        self.lblSymmetry.setObjectName(u"lblSymmetry")
        self.lblSymmetry.setTextFormat(Qt.RichText)
        self.lblSymmetry.setWordWrap(True)

        self.formDerived.setWidget(1, QFormLayout.ItemRole.FieldRole, self.lblSymmetry)

        self.lblProbeZCaption = QLabel(self.groupDerived)
        self.lblProbeZCaption.setObjectName(u"lblProbeZCaption")

        self.formDerived.setWidget(2, QFormLayout.ItemRole.LabelRole, self.lblProbeZCaption)

        self.lblProbeZ = QLabel(self.groupDerived)
        self.lblProbeZ.setObjectName(u"lblProbeZ")
        self.lblProbeZ.setTextFormat(Qt.RichText)
        self.lblProbeZ.setWordWrap(True)

        self.formDerived.setWidget(2, QFormLayout.ItemRole.FieldRole, self.lblProbeZ)

        self.lblSubmergedCaption = QLabel(self.groupDerived)
        self.lblSubmergedCaption.setObjectName(u"lblSubmergedCaption")

        self.formDerived.setWidget(3, QFormLayout.ItemRole.LabelRole, self.lblSubmergedCaption)

        self.lblSubmerged = QLabel(self.groupDerived)
        self.lblSubmerged.setObjectName(u"lblSubmerged")
        self.lblSubmerged.setTextFormat(Qt.RichText)
        self.lblSubmerged.setWordWrap(True)

        self.formDerived.setWidget(3, QFormLayout.ItemRole.FieldRole, self.lblSubmerged)


        self.root.addWidget(self.groupDerived)

        self.layoutActions = QHBoxLayout()
        self.layoutActions.setObjectName(u"layoutActions")
        self.btnCreateMesh = QPushButton(PropCondition)
        self.btnCreateMesh.setObjectName(u"btnCreateMesh")

        self.layoutActions.addWidget(self.btnCreateMesh)

        self.btnRemoveCondition = QPushButton(PropCondition)
        self.btnRemoveCondition.setObjectName(u"btnRemoveCondition")

        self.layoutActions.addWidget(self.btnRemoveCondition)


        self.root.addLayout(self.layoutActions)

        self.lblRemoveHint = QLabel(PropCondition)
        self.lblRemoveHint.setObjectName(u"lblRemoveHint")
        self.lblRemoveHint.setWordWrap(True)

        self.root.addWidget(self.lblRemoveHint)

        self.spacerBottom = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.root.addItem(self.spacerBottom)


        self.retranslateUi(PropCondition)

        QMetaObject.connectSlotsByName(PropCondition)
    # setupUi

    def retranslateUi(self, PropCondition):
        PropCondition.setWindowTitle(QCoreApplication.translate("PropCondition", u"Condition", None))
        self.groupIdentity.setTitle(QCoreApplication.translate("PropCondition", u"Identity", None))
        self.lblLabelCaption.setText(QCoreApplication.translate("PropCondition", u"Label", None))
        self.lblIdCaption.setText(QCoreApplication.translate("PropCondition", u"Id", None))
        self.lblId.setText(QCoreApplication.translate("PropCondition", u"\u2014", None))
        self.btnApplyLabel.setText(QCoreApplication.translate("PropCondition", u"Apply", None))
        self.groupFloating.setTitle(QCoreApplication.translate("PropCondition", u"Floating condition \u2014 derived", None))
        self.lblZOriginCaption.setText(QCoreApplication.translate("PropCondition", u"z_origin [m]", None))
        self.lblZOrigin.setText(QCoreApplication.translate("PropCondition", u"\u2014", None))
        self.lblHeelCaption.setText(QCoreApplication.translate("PropCondition", u"Heel [deg]", None))
        self.lblHeel.setText(QCoreApplication.translate("PropCondition", u"\u2014", None))
        self.lblTrimCaption.setText(QCoreApplication.translate("PropCondition", u"Trim [deg]", None))
        self.lblTrim.setText(QCoreApplication.translate("PropCondition", u"\u2014", None))
        self.lblConditionNote.setText(QCoreApplication.translate("PropCondition", u"Set once, at creation, and shown here as text because there is nothing to edit. Every mesh and result below was computed against these three numbers: changing one would not update that work, it would invalidate it. To float the vessel differently, make another condition. Only the label above can be changed \u2014 nothing parses it.", None))
        self.groupDerived.setTitle(QCoreApplication.translate("PropCondition", u"Derived", None))
        self.lblApplicationPointCaption.setText(QCoreApplication.translate("PropCondition", u"Application point", None))
        self.lblApplicationPoint.setText(QCoreApplication.translate("PropCondition", u"\u2014", None))
        self.lblSymmetryCaption.setText(QCoreApplication.translate("PropCondition", u"Symmetry", None))
        self.lblSymmetry.setText(QCoreApplication.translate("PropCondition", u"\u2014", None))
        self.lblProbeZCaption.setText(QCoreApplication.translate("PropCondition", u"Probe z [m]", None))
        self.lblProbeZ.setText(QCoreApplication.translate("PropCondition", u"\u2014", None))
        self.lblSubmergedCaption.setText(QCoreApplication.translate("PropCondition", u"Submerged", None))
        self.lblSubmerged.setText(QCoreApplication.translate("PropCondition", u"\u2014", None))
        self.btnCreateMesh.setText(QCoreApplication.translate("PropCondition", u"Create mesh\u2026", None))
        self.btnRemoveCondition.setText(QCoreApplication.translate("PropCondition", u"Remove condition\u2026", None))
        self.lblRemoveHint.setText("")
    # retranslateUi

