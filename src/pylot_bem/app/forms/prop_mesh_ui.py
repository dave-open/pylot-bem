# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'prop_mesh.ui'
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
    QLabel, QListWidget, QListWidgetItem, QPushButton,
    QSizePolicy, QSpacerItem, QVBoxLayout, QWidget)

class Ui_PropMesh(object):
    def setupUi(self, PropMesh):
        if not PropMesh.objectName():
            PropMesh.setObjectName(u"PropMesh")
        self.root = QVBoxLayout(PropMesh)
        self.root.setObjectName(u"root")
        self.groupBuiltWith = QGroupBox(PropMesh)
        self.groupBuiltWith.setObjectName(u"groupBuiltWith")
        self.formBuiltWith = QFormLayout(self.groupBuiltWith)
        self.formBuiltWith.setObjectName(u"formBuiltWith")
        self.lblIdCaption = QLabel(self.groupBuiltWith)
        self.lblIdCaption.setObjectName(u"lblIdCaption")

        self.formBuiltWith.setWidget(0, QFormLayout.ItemRole.LabelRole, self.lblIdCaption)

        self.lblId = QLabel(self.groupBuiltWith)
        self.lblId.setObjectName(u"lblId")
        self.lblId.setTextFormat(Qt.RichText)
        self.lblId.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.formBuiltWith.setWidget(0, QFormLayout.ItemRole.FieldRole, self.lblId)

        self.lblSettingsCaption = QLabel(self.groupBuiltWith)
        self.lblSettingsCaption.setObjectName(u"lblSettingsCaption")

        self.formBuiltWith.setWidget(1, QFormLayout.ItemRole.LabelRole, self.lblSettingsCaption)

        self.lblSettings = QLabel(self.groupBuiltWith)
        self.lblSettings.setObjectName(u"lblSettings")
        self.lblSettings.setTextFormat(Qt.RichText)

        self.formBuiltWith.setWidget(1, QFormLayout.ItemRole.FieldRole, self.lblSettings)

        self.lblConditionCaption = QLabel(self.groupBuiltWith)
        self.lblConditionCaption.setObjectName(u"lblConditionCaption")

        self.formBuiltWith.setWidget(2, QFormLayout.ItemRole.LabelRole, self.lblConditionCaption)

        self.lblCondition = QLabel(self.groupBuiltWith)
        self.lblCondition.setObjectName(u"lblCondition")
        self.lblCondition.setTextFormat(Qt.RichText)

        self.formBuiltWith.setWidget(2, QFormLayout.ItemRole.FieldRole, self.lblCondition)

        self.lblMeshNote = QLabel(self.groupBuiltWith)
        self.lblMeshNote.setObjectName(u"lblMeshNote")
        self.lblMeshNote.setWordWrap(True)

        self.formBuiltWith.setWidget(3, QFormLayout.ItemRole.SpanningRole, self.lblMeshNote)


        self.root.addWidget(self.groupBuiltWith)

        self.groupDerived = QGroupBox(PropMesh)
        self.groupDerived.setObjectName(u"groupDerived")
        self.formDerived = QFormLayout(self.groupDerived)
        self.formDerived.setObjectName(u"formDerived")
        self.lblFacesCaption = QLabel(self.groupDerived)
        self.lblFacesCaption.setObjectName(u"lblFacesCaption")

        self.formDerived.setWidget(0, QFormLayout.ItemRole.LabelRole, self.lblFacesCaption)

        self.lblFaces = QLabel(self.groupDerived)
        self.lblFaces.setObjectName(u"lblFaces")
        self.lblFaces.setTextFormat(Qt.RichText)
        self.lblFaces.setWordWrap(True)

        self.formDerived.setWidget(0, QFormLayout.ItemRole.FieldRole, self.lblFaces)

        self.lblPanelsCaption = QLabel(self.groupDerived)
        self.lblPanelsCaption.setObjectName(u"lblPanelsCaption")

        self.formDerived.setWidget(1, QFormLayout.ItemRole.LabelRole, self.lblPanelsCaption)

        self.lblPanels = QLabel(self.groupDerived)
        self.lblPanels.setObjectName(u"lblPanels")
        self.lblPanels.setTextFormat(Qt.RichText)

        self.formDerived.setWidget(1, QFormLayout.ItemRole.FieldRole, self.lblPanels)

        self.lblSymmetryCaption = QLabel(self.groupDerived)
        self.lblSymmetryCaption.setObjectName(u"lblSymmetryCaption")

        self.formDerived.setWidget(2, QFormLayout.ItemRole.LabelRole, self.lblSymmetryCaption)

        self.lblSymmetry = QLabel(self.groupDerived)
        self.lblSymmetry.setObjectName(u"lblSymmetry")
        self.lblSymmetry.setTextFormat(Qt.RichText)
        self.lblSymmetry.setWordWrap(True)

        self.formDerived.setWidget(2, QFormLayout.ItemRole.FieldRole, self.lblSymmetry)

        self.lblReliableCaption = QLabel(self.groupDerived)
        self.lblReliableCaption.setObjectName(u"lblReliableCaption")

        self.formDerived.setWidget(3, QFormLayout.ItemRole.LabelRole, self.lblReliableCaption)

        self.lblReliable = QLabel(self.groupDerived)
        self.lblReliable.setObjectName(u"lblReliable")
        self.lblReliable.setTextFormat(Qt.RichText)
        self.lblReliable.setWordWrap(True)

        self.formDerived.setWidget(3, QFormLayout.ItemRole.FieldRole, self.lblReliable)

        self.lblMemoryCaption = QLabel(self.groupDerived)
        self.lblMemoryCaption.setObjectName(u"lblMemoryCaption")

        self.formDerived.setWidget(4, QFormLayout.ItemRole.LabelRole, self.lblMemoryCaption)

        self.lblMemory = QLabel(self.groupDerived)
        self.lblMemory.setObjectName(u"lblMemory")
        self.lblMemory.setTextFormat(Qt.RichText)

        self.formDerived.setWidget(4, QFormLayout.ItemRole.FieldRole, self.lblMemory)


        self.root.addWidget(self.groupDerived)

        self.groupSolutions = QGroupBox(PropMesh)
        self.groupSolutions.setObjectName(u"groupSolutions")
        self.layoutSolutions = QVBoxLayout(self.groupSolutions)
        self.layoutSolutions.setObjectName(u"layoutSolutions")
        self.listSolutions = QListWidget(self.groupSolutions)
        self.listSolutions.setObjectName(u"listSolutions")
        self.listSolutions.setMinimumSize(QSize(0, 80))

        self.layoutSolutions.addWidget(self.listSolutions)


        self.root.addWidget(self.groupSolutions)

        self.layoutActions = QHBoxLayout()
        self.layoutActions.setObjectName(u"layoutActions")
        self.btnSolve = QPushButton(PropMesh)
        self.btnSolve.setObjectName(u"btnSolve")

        self.layoutActions.addWidget(self.btnSolve)

        self.btnRemoveMesh = QPushButton(PropMesh)
        self.btnRemoveMesh.setObjectName(u"btnRemoveMesh")

        self.layoutActions.addWidget(self.btnRemoveMesh)


        self.root.addLayout(self.layoutActions)

        self.lblConflict = QLabel(PropMesh)
        self.lblConflict.setObjectName(u"lblConflict")
        self.lblConflict.setWordWrap(True)
        self.lblConflict.setTextFormat(Qt.RichText)

        self.root.addWidget(self.lblConflict)

        self.spacerBottom = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.root.addItem(self.spacerBottom)


        self.retranslateUi(PropMesh)

        QMetaObject.connectSlotsByName(PropMesh)
    # setupUi

    def retranslateUi(self, PropMesh):
        PropMesh.setWindowTitle(QCoreApplication.translate("PropMesh", u"Calculation mesh", None))
        self.groupBuiltWith.setTitle(QCoreApplication.translate("PropMesh", u"Built with \u2014 derived", None))
        self.lblIdCaption.setText(QCoreApplication.translate("PropMesh", u"Id", None))
        self.lblId.setText(QCoreApplication.translate("PropMesh", u"\u2014", None))
        self.lblSettingsCaption.setText(QCoreApplication.translate("PropMesh", u"Settings", None))
        self.lblSettings.setText(QCoreApplication.translate("PropMesh", u"\u2014", None))
        self.lblConditionCaption.setText(QCoreApplication.translate("PropMesh", u"At condition", None))
        self.lblCondition.setText(QCoreApplication.translate("PropMesh", u"\u2014", None))
        self.lblMeshNote.setText(QCoreApplication.translate("PropMesh", u"A mesh is fixed once built. Nothing to edit \u2014 if the resolution is wrong, remove it and create another. That is also how two resolutions get compared: keep both.", None))
        self.groupDerived.setTitle(QCoreApplication.translate("PropMesh", u"Derived", None))
        self.lblFacesCaption.setText(QCoreApplication.translate("PropMesh", u"Faces", None))
        self.lblFaces.setText(QCoreApplication.translate("PropMesh", u"\u2014", None))
        self.lblPanelsCaption.setText(QCoreApplication.translate("PropMesh", u"Panels solved", None))
        self.lblPanels.setText(QCoreApplication.translate("PropMesh", u"\u2014", None))
        self.lblSymmetryCaption.setText(QCoreApplication.translate("PropMesh", u"Symmetry", None))
        self.lblSymmetry.setText(QCoreApplication.translate("PropMesh", u"\u2014", None))
        self.lblReliableCaption.setText(QCoreApplication.translate("PropMesh", u"Reliable above", None))
        self.lblReliable.setText(QCoreApplication.translate("PropMesh", u"\u2014", None))
        self.lblMemoryCaption.setText(QCoreApplication.translate("PropMesh", u"Memory", None))
        self.lblMemory.setText(QCoreApplication.translate("PropMesh", u"\u2014", None))
        self.groupSolutions.setTitle(QCoreApplication.translate("PropMesh", u"Solutions", None))
        self.btnSolve.setText(QCoreApplication.translate("PropMesh", u"Solve\u2026", None))
        self.btnRemoveMesh.setText(QCoreApplication.translate("PropMesh", u"Remove mesh\u2026", None))
        self.lblConflict.setText("")
    # retranslateUi

