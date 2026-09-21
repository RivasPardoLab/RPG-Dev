"""macOS desktop interface for RPG Stage 1 and Stage 2."""

import sys
from pathlib import Path

from PyQt5 import QtGui
from PyQt5.QtCore import QPoint, QThread, Qt, QUrl, pyqtSignal
from PyQt5.QtGui import QDesktopServices, QFont
from PyQt5.QtWidgets import QApplication, QFileDialog, QMainWindow, QMessageBox

from MainWin.ui_mainwindow import Ui_Window
from PepWin.PeptideWindow import PepWindow, peptideDict
from stage1 import generate_peptide_library
from stage2 import run_stage2


APP_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def default_documents_directory() -> Path:
    documents = Path.home() / "Documents"
    return documents if documents.is_dir() else Path.home()


class PeptideWorker(QThread):
    completed = pyqtSignal(int)
    failed = pyqtSignal(str)

    def __init__(self, peptide_options, destination: Path, parent=None):
        super().__init__(parent)
        self.peptide_options = {
            index: tuple(choices) for index, choices in peptide_options.items()
        }
        self.destination = destination

    def run(self):
        try:
            count = generate_peptide_library(self.peptide_options, self.destination)
        except Exception as error:
            self.failed.emit(str(error))
            return
        self.completed.emit(count)


class PDBWorker(QThread):
    progress = pyqtSignal(int)
    completed = pyqtSignal(int, str)
    failed = pyqtSignal(str)

    def __init__(self, library_file: Path, requested_count: int, parent=None):
        super().__init__(parent)
        self.library_file = library_file
        self.requested_count = requested_count

    def run(self):
        try:
            generated = run_stage2(
                self.library_file,
                self.requested_count,
                self.library_file.parent,
                progress=self.progress.emit,
            )
        except Exception as error:
            self.failed.emit(str(error))
            return
        self.completed.emit(len(generated), str(generated[0].parent))


class RPGWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.ui = Ui_Window()
        self.ui.setupUi(self)
        self.setWindowTitle("RPG — Peptide Library and PDB Generator")
        self.setWindowFlag(Qt.FramelessWindowHint)
        self.resize(1000, 800)

        self.selector = PepWindow(self)
        self.selector.setModal(True)
        self.worker = None
        self.pdb_worker = None
        self.output_file = None
        self.library_count = 0
        self.old_position = QPoint()

        self._configure_ui()
        self._connect_actions()
        self._center_window()

    def _configure_ui(self):
        self.ui.stackedWidget.setCurrentWidget(self.ui.stage1)
        self.ui.homeButton.hide()
        self.ui.stage2Button.hide()
        self.ui.stage3Button.hide()
        self.ui.stage4Button.hide()
        self.ui.stage1Button.setEnabled(False)
        self.ui.gotostage2Button.hide()
        self.ui.mid_frame.hide()
        self.ui.listnameFrame.hide()
        self.ui.textEdit.hide()
        self.ui.label_7.hide()
        self.ui.textEdit.setReadOnly(True)
        self._configure_stage2_page()

    def _configure_stage2_page(self):
        self.ui.label_5.hide()
        self.ui.stage2_selectButton.hide()
        self.ui.label_stage2_newgame.setWordWrap(True)
        self.ui.label_stage2_newgame.setText(
            "<html><body><p align='center'>Your peptide library is ready.<br/>"
            "Choose how many randomly selected peptides should be converted "
            "into 3D PDB models.</p></body></html>"
        )
        self.ui.runchimButton.setText("Build PDB Files")
        self.ui.label_working.setText("Building peptide PDB files with PeptideBuilder…")
        self.ui.label_done.setWordWrap(True)
        self.ui.label_done.setText(
            "The selected peptides were converted successfully. The numbered "
            "PDB files are in the Chimera-Peptides folder."
        )
        self.ui.label_working.hide()
        self.ui.label_done.hide()
        self.ui.progressBar_2.hide()
        self.ui.gotostage3Button.hide()

    def _connect_actions(self):
        self.ui.setpepButton.clicked.connect(self.open_peptide_selector)
        self.ui.directoryButton.clicked.connect(self.choose_output_directory)
        self.ui.stage1Button.clicked.connect(self.show_stage1)
        self.ui.stage2Button.clicked.connect(self.show_stage2)
        self.ui.gotostage2Button.clicked.connect(self.show_stage2)
        self.ui.runchimButton.clicked.connect(self.build_pdb_files)
        self.ui.xButton.clicked.connect(self.close)
        self.ui.minimizeButton.clicked.connect(self.showMinimized)
        self.ui.squareButton.clicked.connect(self.toggle_maximized)
        self.ui.helpButton.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://github.com/RivasPardoLab/RPG-Dev"))
        )
        self.ui.pushButton_2.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://www.rivaspardo-lab.org/lab"))
        )
        self.selector.ui.listoButton.clicked.connect(self.peptide_selection_ready)
        self.selector.ui.xButton.clicked.connect(self.cancel_peptide_selection)

    def _center_window(self):
        screen = QApplication.primaryScreen()
        if screen is not None:
            frame = self.frameGeometry()
            frame.moveCenter(screen.availableGeometry().center())
            self.move(frame.topLeft())

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.old_position = event.globalPos()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and not self.isMaximized():
            delta = event.globalPos() - self.old_position
            self.move(self.pos() + delta)
            self.old_position = event.globalPos()

    def toggle_maximized(self):
        self.showNormal() if self.isMaximized() else self.showMaximized()

    def show_stage1(self):
        self.ui.stackedWidget.setCurrentWidget(self.ui.stage1)
        self.ui.stage1Button.setEnabled(False)
        self.ui.stage2Button.setEnabled(self.output_file is not None)

    def show_stage2(self):
        if self.output_file is None:
            return
        self.ui.stackedWidget.setCurrentWidget(self.ui.stage2)
        self.ui.stage1Button.setEnabled(True)
        self.ui.stage2Button.setEnabled(False)

    def open_peptide_selector(self):
        self.ui.setpepButton.setEnabled(False)
        self.selector.show()
        self.selector.raise_()
        self.selector.activateWindow()

    def cancel_peptide_selection(self):
        self.selector.hide()
        self.ui.setpepButton.setEnabled(True)

    def peptide_selection_ready(self):
        options = self._peptide_options_snapshot()
        if not options:
            return

        self.selector.hide()
        self.ui.setpepButton.setEnabled(True)
        self.ui.mid_frame.show()
        self.ui.listnameFrame.show()
        self.ui.label_7.show()
        self.ui.textEdit.show()
        combinations = 1
        for choices in options.values():
            combinations *= len(choices)
        self.ui.textEdit.setPlainText(
            f"Configured {len(options)} positions and {combinations:,} peptide combinations."
        )

    def _peptide_options_snapshot(self):
        if not peptideDict:
            return {}
        positions = sorted(peptideDict)
        if positions != list(range(len(positions))):
            return {}
        return {index: tuple(peptideDict[index]) for index in positions}

    def choose_output_directory(self):
        options = self._peptide_options_snapshot()
        if not options:
            self._show_message(
                "Configure the peptide first and select at least one amino acid at every position.",
                QMessageBox.Warning,
                "Peptide configuration required",
            )
            return

        selected = QFileDialog.getExistingDirectory(
            self,
            "Select the folder for your peptide library",
            str(default_documents_directory()),
        )
        if not selected:
            return

        destination = Path(selected).expanduser().resolve() / "peptides.txt"
        if destination.exists():
            self._show_message(
                "A peptides.txt file already exists in that folder. Rename or remove it before trying again.",
                QMessageBox.Warning,
                "Existing peptide library",
            )
            return

        self.output_file = destination
        self.ui.setpepButton.setEnabled(False)
        self.ui.directoryButton.setEnabled(False)
        self.ui.textEdit.setPlainText("Generating peptides…")

        self.worker = PeptideWorker(options, destination, self)
        self.worker.completed.connect(self.generation_finished)
        self.worker.failed.connect(self.generation_failed)
        self.worker.start()

    def generation_finished(self, count: int):
        self.library_count = count
        self.ui.runchimButton.setEnabled(True)
        self.ui.label_working.hide()
        self.ui.label_done.hide()
        self.ui.progressBar_2.hide()
        self.ui.textEdit.setPlainText(
            f"Library generated successfully: {count:,} peptides saved in {self.output_file}."
        )
        self.ui.setpepButton.setEnabled(True)
        self.ui.directoryButton.setEnabled(True)
        self.ui.spinBox.setRange(1, 10000)
        self.ui.spinBox.setValue(min(10, count))
        self.ui.stage2Button.show()
        self.ui.stage2Button.setEnabled(True)
        self.ui.gotostage2Button.show()
        self.ui.gotostage2Button.setEnabled(True)
        self._show_message(
            f"The peptide library was saved as:\n{self.output_file}\n\n"
            "Continue to Stage 2 to build PDB files.",
            QMessageBox.Information,
            "Stage 1 complete",
        )

    def generation_failed(self, message: str):
        self.ui.textEdit.setPlainText("Peptide generation failed: " + message)
        self.ui.setpepButton.setEnabled(True)
        self.ui.directoryButton.setEnabled(True)
        self._show_message(message, QMessageBox.Critical, "Generation failed")

    def build_pdb_files(self):
        if self.output_file is None or not self.output_file.is_file():
            self._show_message(
                "The peptides.txt library could not be found. Run Stage 1 again.",
                QMessageBox.Warning,
                "Peptide library missing",
            )
            return

        output_directory = self.output_file.parent / "Chimera-Peptides"
        if output_directory.exists() and any(output_directory.glob("*.pdb")):
            self._show_message(
                "The Chimera-Peptides folder already contains PDB files. "
                "Move or remove them before running Stage 2 again.",
                QMessageBox.Warning,
                "Existing PDB files",
            )
            return

        requested_count = self.ui.spinBox.value()
        expected_count = min(requested_count, self.library_count)
        self.ui.runchimButton.setEnabled(False)
        self.ui.label_done.hide()
        self.ui.label_working.show()
        self.ui.progressBar_2.setRange(0, expected_count)
        self.ui.progressBar_2.setValue(0)
        self.ui.progressBar_2.show()

        self.pdb_worker = PDBWorker(self.output_file, requested_count, self)
        self.pdb_worker.progress.connect(self.ui.progressBar_2.setValue)
        self.pdb_worker.completed.connect(self.pdb_generation_finished)
        self.pdb_worker.failed.connect(self.pdb_generation_failed)
        self.pdb_worker.start()

    def pdb_generation_finished(self, count: int, output_directory: str):
        self.ui.progressBar_2.setValue(count)
        self.ui.label_working.hide()
        self.ui.label_done.setText(
            f"{count:,} peptides were selected at random and converted successfully. "
            f"The numbered PDB files are in:\n{output_directory}"
        )
        self.ui.label_done.show()
        self._show_message(
            f"Stage 2 generated {count:,} PDB files in:\n{output_directory}",
            QMessageBox.Information,
            "Stage 2 complete",
        )

    def pdb_generation_failed(self, message: str):
        self.ui.label_working.hide()
        self.ui.runchimButton.setEnabled(True)
        self._show_message(message, QMessageBox.Critical, "PDB conversion failed")

    def _show_message(self, text, icon, title):
        message = QMessageBox(self)
        message.setFont(QFont("Eight Bit Dragon", 8))
        message.setWindowTitle(title)
        message.setText(text)
        message.setIcon(icon)
        message.setStyleSheet(
            "QDialog { border: 2px solid rgb(120, 120, 120); }"
            "* { background-color: rgb(40, 40, 32); color: white; }"
        )
        message.exec_()


def main() -> int:
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app = QApplication(sys.argv)
    app.setApplicationName("RPG macOS")
    app.setOrganizationName("RivasPardoLab")
    QtGui.QFontDatabase.addApplicationFont(str(APP_ROOT / "eight-bit-dragon.otf"))
    app.setWindowIcon(QtGui.QIcon(str(APP_ROOT / "MainWin" / "icons" / "Lab2.png")))

    window = RPGWindow()
    window.show()
    return app.exec_()
