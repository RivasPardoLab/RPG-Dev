"""macOS desktop interface for RPG Stage 1 through Vina docking."""

import sys
from pathlib import Path

from PyQt5 import QtGui
from PyQt5.QtCore import QPoint, QThread, Qt, QUrl, pyqtSignal
from PyQt5.QtGui import QDesktopServices, QFont
from PyQt5.QtWidgets import QApplication, QFileDialog, QMainWindow, QMessageBox

from MainWin.ui_mainwindow import Ui_Window
from ConfigWin.ConfVinaWindow import ConfWindow
from PepWin.PeptideWindow import PepWindow, peptideDict
from stage1 import generate_peptide_library
from stage2 import run_stage2
from stage3a import run_stage3a
from stage3b import VinaConfig, run_vina_docking, write_vina_config


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


class PDBQTWorker(QThread):
    progress = pyqtSignal(int)
    completed = pyqtSignal(int, str)
    failed = pyqtSignal(str)

    def __init__(self, workspace: Path, requested_count: int, parent=None):
        super().__init__(parent)
        self.workspace = workspace
        self.requested_count = requested_count

    def run(self):
        try:
            generated = run_stage3a(
                self.workspace,
                self.requested_count,
                progress=self.progress.emit,
            )
        except Exception as error:
            self.failed.emit(str(error))
            return
        self.completed.emit(len(generated), str(generated[0].parent))


class VinaWorker(QThread):
    progress = pyqtSignal(int)
    completed = pyqtSignal(int, str)
    failed = pyqtSignal(str)

    def __init__(self, receptor, ligands, workspace, config, parent=None):
        super().__init__(parent)
        self.receptor = Path(receptor)
        self.ligands = [Path(path) for path in ligands]
        self.workspace = Path(workspace)
        self.config = config

    def run(self):
        try:
            generated = run_vina_docking(
                self.receptor,
                self.ligands,
                self.workspace,
                self.config,
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
        self.setWindowTitle("RPG — Peptide Library and AutoDock Vina")
        self.setWindowFlag(Qt.FramelessWindowHint)
        self.resize(1000, 800)

        self.selector = PepWindow(self)
        self.selector.setModal(True)
        self.confwin = ConfWindow(self)
        self.confwin.setModal(True)
        self.worker = None
        self.pdb_worker = None
        self.pdbqt_worker = None
        self.vina_worker = None
        self.output_file = None
        self.library_count = 0
        self.pdb_count = 0
        self.receptor_file = None
        self.ligand_files = []
        self.vina_config = None
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
        self._configure_stage3a_page()

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

    def _configure_stage3a_page(self):
        self.ui.label_stage3_Continue.hide()
        self.ui.Continue_stage3.hide()
        self.ui.Second_Stage3.hide()
        self.ui.Third_Stage3.hide()
        self.ui.label_stage3_NewGame.setMinimumWidth(760)
        self.ui.label_stage3_NewGame.setAlignment(Qt.AlignCenter)
        self.ui.label_stage3_NewGame.setWordWrap(True)
        self.ui.label_stage3_NewGame.setText(
            "<html><body><p align='center'>Prepare the peptide PDB files "
            "as PDBQT ligands for AutoDock Vina using Open Babel.</p></body></html>"
        )
        self.ui.label_12.setText("Stage 3A")
        self.ui.label_14.setWordWrap(True)
        self.ui.label_14.setText(
            "Open Babel will add hydrogens and write numbered PDBQT files "
            "to the Ligands folder."
        )
        self.ui.label_18.setText("How many PDB files do you want to convert?")
        self.ui.spinBox_2.setRange(1, 10000)
        self.ui.obconvertButton.setText("Convert to PDBQT")
        self.ui.verticalLayout_20.removeWidget(self.ui.progressBar_vina)
        self.ui.progressBar_vina.setParent(self.ui.frame_15)
        self.ui.verticalLayout_18.addWidget(self.ui.progressBar_vina)
        self.ui.progressBar_vina.hide()
        self.ui.Second_Stage3.hide()
        self.ui.Third_Stage3.hide()
        self.ui.label_13.setText("Stage 3B")
        self.ui.label_11.setWordWrap(True)
        self.ui.label_11.setText(
            "Select a prepared receptor in PDBQT format. The peptide ligands "
            "generated above are selected automatically."
        )
        self.ui.selectprotein_stage3Button.setText("Select Receptor PDBQT")
        self.ui.selectpep_stage3Button.setText("Choose Ligand Subset")
        self.ui.label_15.setText("Docking")
        self.ui.label_16.setWordWrap(True)
        self.ui.label_16.setText(
            "Configure the search box and run AutoDock Vina with the original "
            "RPG parameters."
        )
        self.ui.configureVinaButton.setText("Configure Vina")
        self.ui.runVinaButton.setText("Run Vina")
        self.ui.runVinaButton.hide()
        self.ui.gotostage4Button.hide()

    def _connect_actions(self):
        self.ui.setpepButton.clicked.connect(self.open_peptide_selector)
        self.ui.directoryButton.clicked.connect(self.choose_output_directory)
        self.ui.stage1Button.clicked.connect(self.show_stage1)
        self.ui.stage2Button.clicked.connect(self.show_stage2)
        self.ui.gotostage2Button.clicked.connect(self.show_stage2)
        self.ui.runchimButton.clicked.connect(self.build_pdb_files)
        self.ui.stage3Button.clicked.connect(self.show_stage3a)
        self.ui.gotostage3Button.clicked.connect(self.show_stage3a)
        self.ui.obconvertButton.clicked.connect(self.build_pdbqt_files)
        self.ui.selectprotein_stage3Button.clicked.connect(self.select_receptor)
        self.ui.selectpep_stage3Button.clicked.connect(self.select_ligands)
        self.ui.configureVinaButton.clicked.connect(self.open_vina_configuration)
        self.ui.runVinaButton.clicked.connect(self.run_vina)
        self.confwin.ui.saveButton.clicked.connect(self.save_vina_configuration)
        self.confwin.ui.resetButton.clicked.connect(self.reset_vina_configuration)
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
        self.ui.stage3Button.setEnabled(self.pdb_count > 0)

    def show_stage2(self):
        if self.output_file is None:
            return
        self.ui.stackedWidget.setCurrentWidget(self.ui.stage2)
        self.ui.stage1Button.setEnabled(True)
        self.ui.stage2Button.setEnabled(False)
        self.ui.stage3Button.setEnabled(self.pdb_count > 0)

    def show_stage3a(self):
        if self.output_file is None or self.pdb_count == 0:
            return
        self.ui.stackedWidget.setCurrentWidget(self.ui.stage3)
        self.ui.stage1Button.setEnabled(True)
        self.ui.stage2Button.setEnabled(True)
        self.ui.stage3Button.setEnabled(False)

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
        self.pdb_count = 0
        self.receptor_file = None
        self.ligand_files = []
        self.vina_config = None
        self.ui.Second_Stage3.hide()
        self.ui.Third_Stage3.hide()
        self.ui.stage3Button.hide()
        self.ui.gotostage3Button.hide()
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
        self.pdb_count = count
        self.ui.progressBar_2.setValue(count)
        self.ui.label_working.hide()
        self.ui.label_done.setText(
            f"{count:,} peptides were selected at random and converted successfully. "
            f"The numbered PDB files are in:\n{output_directory}"
        )
        self.ui.label_done.show()
        self.ui.spinBox_2.setValue(min(100, count))
        self.ui.obconvertButton.setEnabled(True)
        self.ui.progressBar_vina.hide()
        self.ui.stage3Button.show()
        self.ui.stage3Button.setEnabled(True)
        self.ui.gotostage3Button.show()
        self.ui.gotostage3Button.setEnabled(True)
        self._show_message(
            f"Stage 2 generated {count:,} PDB files in:\n{output_directory}\n\n"
            "Continue to Stage 3A to prepare PDBQT ligands.",
            QMessageBox.Information,
            "Stage 2 complete",
        )

    def pdb_generation_failed(self, message: str):
        self.ui.label_working.hide()
        self.ui.runchimButton.setEnabled(True)
        self._show_message(message, QMessageBox.Critical, "PDB conversion failed")

    def build_pdbqt_files(self):
        if self.output_file is None or self.pdb_count == 0:
            self._show_message(
                "No PDB files are available. Run Stage 2 first.",
                QMessageBox.Warning,
                "PDB files missing",
            )
            return

        workspace = self.output_file.parent
        output_directory = workspace / "Ligands"
        if output_directory.exists() and any(output_directory.glob("*.pdbqt")):
            self._show_message(
                "The Ligands folder already contains PDBQT files. "
                "Move or remove them before running Stage 3A again.",
                QMessageBox.Warning,
                "Existing PDBQT files",
            )
            return

        requested_count = self.ui.spinBox_2.value()
        expected_count = min(requested_count, self.pdb_count)
        self.ui.obconvertButton.setEnabled(False)
        self.ui.label_14.setText(
            "Open Babel is adding hydrogens and converting the peptide PDB files…"
        )
        self.ui.progressBar_vina.setRange(0, expected_count)
        self.ui.progressBar_vina.setValue(0)
        self.ui.progressBar_vina.show()

        self.pdbqt_worker = PDBQTWorker(workspace, requested_count, self)
        self.pdbqt_worker.progress.connect(self.ui.progressBar_vina.setValue)
        self.pdbqt_worker.completed.connect(self.pdbqt_generation_finished)
        self.pdbqt_worker.failed.connect(self.pdbqt_generation_failed)
        self.pdbqt_worker.start()

    def pdbqt_generation_finished(self, count: int, output_directory: str):
        self.ui.progressBar_vina.setValue(count)
        ligand_directory = Path(output_directory)
        self.ligand_files = sorted(
            ligand_directory.glob("*.pdbqt"),
            key=lambda path: (
                (0, int(path.stem))
                if path.stem.isdigit()
                else (1, path.stem.lower())
            ),
        )
        self.ui.label_14.setText(
            f"{count:,} peptide PDB files were converted successfully. "
            f"The numbered PDBQT ligands are in:\n{output_directory}"
        )
        self.ui.progressBar_vina.hide()
        self.ui.Second_Stage3.show()
        self.ui.selectpep_stage3Button.setText(
            f"Choose Ligand Subset ({count:,} selected)"
        )
        self._update_vina_readiness()
        self._show_message(
            f"Stage 3A generated {count:,} PDBQT ligands in:\n{output_directory}\n\n"
            "Continue by selecting a prepared receptor PDBQT for AutoDock Vina.",
            QMessageBox.Information,
            "Stage 3A complete",
        )

    def pdbqt_generation_failed(self, message: str):
        self.ui.label_14.setText("PDBQT conversion failed: " + message)
        self.ui.obconvertButton.setEnabled(True)
        self._show_message(message, QMessageBox.Critical, "PDBQT conversion failed")

    def select_receptor(self):
        if self.output_file is None:
            return
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Select the prepared receptor",
            str(self.output_file.parent),
            "PDBQT files (*.pdbqt)",
        )
        if not selected:
            return
        self.receptor_file = Path(selected).expanduser().resolve()
        self.ui.selectprotein_stage3Button.setText(
            f"Receptor: {self.receptor_file.name}"
        )
        self._update_vina_readiness()

    def select_ligands(self):
        if self.output_file is None:
            return
        selected, _ = QFileDialog.getOpenFileNames(
            self,
            "Select peptide ligands",
            str(self.output_file.parent / "Ligands"),
            "PDBQT files (*.pdbqt)",
        )
        if not selected:
            return
        self.ligand_files = [Path(path).expanduser().resolve() for path in selected]
        self.ui.selectpep_stage3Button.setText(
            f"Choose Ligand Subset ({len(self.ligand_files):,} selected)"
        )
        self._update_vina_readiness()

    def _update_vina_readiness(self):
        ready = self.receptor_file is not None and bool(self.ligand_files)
        self.ui.Third_Stage3.setVisible(ready)
        if ready:
            self.ui.label_11.setText(
                f"Receptor: {self.receptor_file.name}\n"
                f"Peptide ligands selected: {len(self.ligand_files):,}"
            )
            self.ui.configureVinaButton.show()
            self.ui.runVinaButton.setVisible(self.vina_config is not None)

    def open_vina_configuration(self):
        self.confwin.show()
        self.confwin.raise_()
        self.confwin.activateWindow()

    def reset_vina_configuration(self):
        for box in (
            self.confwin.ui.centerx_box,
            self.confwin.ui.centery_box_2,
            self.confwin.ui.centerx_box_3,
        ):
            box.setValue(0)
        for box in (
            self.confwin.ui.sizeX_box,
            self.confwin.ui.sizey_box,
            self.confwin.ui.sizeZ_box,
        ):
            box.setValue(60)
        self.confwin.ui.Exhaustivness_box.setValue(10)

    def save_vina_configuration(self):
        if self.output_file is None:
            return
        config = VinaConfig(
            center_x=self.confwin.ui.centerx_box.value(),
            center_y=self.confwin.ui.centery_box_2.value(),
            center_z=self.confwin.ui.centerx_box_3.value(),
            size_x=self.confwin.ui.sizeX_box.value(),
            size_y=self.confwin.ui.sizey_box.value(),
            size_z=self.confwin.ui.sizeZ_box.value(),
            exhaustiveness=self.confwin.ui.Exhaustivness_box.value(),
            num_modes=10,
            energy_range=4,
        )
        try:
            config_path = write_vina_config(
                self.output_file.parent / "config.txt", config
            )
        except Exception as error:
            self._show_message(
                str(error), QMessageBox.Critical, "Invalid Vina configuration"
            )
            return

        self.vina_config = config
        self.confwin.close()
        self.ui.runVinaButton.show()
        self.ui.label_16.setText(
            f"Vina configuration saved in {config_path.name}. "
            f"Box center: {config.center}; size: {config.size}; "
            f"exhaustiveness: {config.exhaustiveness}."
        )

    def run_vina(self):
        if (
            self.output_file is None
            or self.receptor_file is None
            or not self.ligand_files
            or self.vina_config is None
        ):
            self._show_message(
                "Select the receptor and ligands, then save the Vina configuration.",
                QMessageBox.Warning,
                "Docking configuration incomplete",
            )
            return

        results_directory = self.output_file.parent / "VinaResults"
        if results_directory.exists() and any(results_directory.iterdir()):
            self._show_message(
                "The VinaResults folder is not empty. Move or remove its contents "
                "before running docking again.",
                QMessageBox.Warning,
                "Existing Vina results",
            )
            return

        self.ui.runVinaButton.setEnabled(False)
        self.ui.configureVinaButton.setEnabled(False)
        self.ui.progressBar_vina.setParent(self.ui.frame_19)
        self.ui.verticalLayout_20.insertWidget(2, self.ui.progressBar_vina)
        self.ui.progressBar_vina.setRange(0, len(self.ligand_files))
        self.ui.progressBar_vina.setValue(0)
        self.ui.progressBar_vina.show()
        self.ui.label_16.setText("AutoDock Vina is docking the peptide library…")

        self.vina_worker = VinaWorker(
            self.receptor_file,
            self.ligand_files,
            self.output_file.parent,
            self.vina_config,
            self,
        )
        self.vina_worker.progress.connect(self.ui.progressBar_vina.setValue)
        self.vina_worker.completed.connect(self.vina_finished)
        self.vina_worker.failed.connect(self.vina_failed)
        self.vina_worker.start()

    def vina_finished(self, count: int, output_directory: str):
        self.ui.progressBar_vina.setValue(count)
        self.ui.runVinaButton.setEnabled(True)
        self.ui.configureVinaButton.setEnabled(True)
        self.ui.label_16.setText(
            f"Docking complete: {count:,} peptide results, affinities.csv and "
            f"docking-manifest.json were saved in:\n{output_directory}"
        )
        self._show_message(
            f"AutoDock Vina completed {count:,} peptide dockings.\n\n"
            f"Results: {output_directory}",
            QMessageBox.Information,
            "Vina docking complete",
        )

    def vina_failed(self, message: str):
        self.ui.runVinaButton.setEnabled(True)
        self.ui.configureVinaButton.setEnabled(True)
        self.ui.label_16.setText("Vina docking failed: " + message)
        self._show_message(message, QMessageBox.Critical, "Vina docking failed")

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
