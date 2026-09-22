import sys
from PyQt5.QtCore import Qt, QPoint
from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtWidgets import QDialog, QApplication, QWidget, QLineEdit, QVBoxLayout, QCheckBox, QHBoxLayout, QMainWindow
from PyQt5.QtGui import QIntValidator
from ConfigWin.ui_configwin import *



class ConfWindow(QDialog):

    def __init__(self, parent=None):
        QDialog.__init__(self)
        self.ui = Ui_Dialog()
        self.ui.setupUi(self)
        for box in (
            self.ui.centerx_box,
            self.ui.centery_box_2,
            self.ui.centerx_box_3,
            self.ui.sizeX_box,
            self.ui.sizey_box,
            self.ui.sizeZ_box,
        ):
            box.setMinimumWidth(90)
            box.setMaximumWidth(110)
        self.setWindowFlag(Qt.FramelessWindowHint)

