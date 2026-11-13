"""macOS desktop interface for RPG Stage 1 through Stage 4 result analysis."""

import sys
from pathlib import Path

from PyQt5 import QtGui
from PyQt5.QtCore import QPoint, QThread, Qt, QUrl, pyqtSignal
from PyQt5.QtGui import QDesktopServices, QFont
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidgetItem,
)

from MainWin.ui_mainwindow import Ui_Window
from ConfigWin.ConfVinaWindow import ConfWindow
from PepWin.PeptideWindow import PepWindow, peptideDict
from stage1 import generate_peptide_library
from stage2 import run_stage2
from stage3a import run_stage3a
from stage3_receptor import prepare_rigid_receptor
from docking_box_viewer import DockingBoxDialog
from pose_viewer import DockingPoseDialog
from stage3b import (
    VinaConfig,
    run_vina_docking,
    validate_receptor_pdbqt,
    write_vina_config,
)
from stage4 import (
    analyze_position_enrichment,
    filter_ranked_results,
    load_ranked_results,
    resolve_workspace_receptor,
    write_best_peptides,
    write_position_enrichment,
)


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


class ReceptorWorker(QThread):
    completed = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, source_pdb: Path, workspace: Path, parent=None):
        super().__init__(parent)
        self.source_pdb = Path(source_pdb)
        self.workspace = Path(workspace)

    def run(self):
        try:
            receptor = prepare_rigid_receptor(self.source_pdb, self.workspace)
        except Exception as error:
            self.failed.emit(str(error))
            return
        self.completed.emit(str(receptor))


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
        self.setWindowTitle("RPG macOS 2.0 — Peptide Library and AutoDock Vina")
        self.setWindowFlag(Qt.FramelessWindowHint)
        self.resize(1000, 800)

        self.selector = PepWindow(self)
        self.selector.setModal(True)
        self.confwin = ConfWindow(self)
        self.confwin.setModal(True)
        self.worker = None
        self.pdb_worker = None
        self.pdbqt_worker = None
        self.receptor_worker = None
        self.vina_worker = None
        self.output_file = None
        self.library_count = 0
        self.pdb_count = 0
        self.receptor_file = None
        self.ligand_files = []
        self.vina_config = None
        self.stage4_workspace = None
        self.stage4_receptor_file = None
        self.stage4_results = []
        self.stage4_filtered = []
        self.old_position = QPoint()

        self._configure_ui()
        self._connect_actions()
        self._center_window()

    def _configure_ui(self):
        self.ui.stackedWidget.setCurrentWidget(self.ui.stage1)
        self.ui.homeButton.hide()
        self.ui.stage2Button.hide()
        self.ui.stage3Button.hide()
        self.ui.stage4Button.show()
        self.ui.stage4Button.setEnabled(True)
        self.ui.stage1Button.setEnabled(False)
        self.ui.gotostage2Button.hide()
        self.ui.mid_frame.hide()
        self.ui.listnameFrame.hide()
        self.ui.textEdit.hide()
        self.ui.label_7.hide()
        self.ui.textEdit.setReadOnly(True)
        self._configure_stage2_page()
        self._configure_stage3a_page()
        self._configure_stage4_page()

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
            "Provide a cleaned protein PDB and RPG will prepare a rigid Vina "
            "receptor with Meeko. You can also select an existing rigid PDBQT."
        )
        self.ui.selectprotein_stage3Button.setText("Prepare Receptor from PDB")
        self.ui.selectpep_stage3Button.setText("Use Existing Receptor PDBQT")
        self.ligand_subset_button = QPushButton("Choose Ligand Subset", self.ui.frame_13)
        self.ligand_subset_button.setFocusPolicy(Qt.NoFocus)
        self.ligand_subset_button.setMinimumWidth(230)
        self.ligand_subset_button.setMaximumWidth(260)
        self.ligand_subset_button.setStyleSheet(
            self.ui.selectpep_stage3Button.styleSheet()
        )
        self.ui.verticalLayout_17.addWidget(
            self.ligand_subset_button, 0, Qt.AlignHCenter
        )
        self.ui.label_15.setText("Docking")
        self.ui.label_16.setWordWrap(True)
        self.ui.label_16.setText(
            "Preview or manually configure the search box, then run AutoDock "
            "Vina with the original RPG parameters."
        )
        self.ui.configureVinaButton.setText("Configure Vina")
        self.preview_box_button = QPushButton("Preview Docking Box", self.ui.frame_19)
        self.preview_box_button.setFocusPolicy(Qt.NoFocus)
        self.preview_box_button.setMinimumSize(200, 30)
        self.preview_box_button.setMaximumSize(200, 30)
        self.preview_box_button.setStyleSheet(
            self.ui.configureVinaButton.styleSheet()
        )
        self.ui.verticalLayout_20.insertWidget(
            1, self.preview_box_button, 0, Qt.AlignHCenter
        )
        self.ui.runVinaButton.setText("Run Vina")
        self.ui.runVinaButton.hide()
        self.ui.gotostage4Button.hide()

    def _configure_stage4_page(self):
        self.ui.choosedir_stage4.setText("Open Existing RPG Workspace")
        self.ui.label_stage4.setAlignment(Qt.AlignCenter)
        self.ui.label_stage4.setWordWrap(True)
        self.ui.label_stage4.setText(
            "Open a workspace containing random.txt and "
            "VinaResults/affinities.csv, or continue here after docking."
        )

        self.ui.aff_spinbox.hide()
        self.use_affinity_cutoff = QCheckBox(
            "Affinity ≤", self.ui.frame_Selectpeptides
        )
        self.use_affinity_cutoff.setChecked(True)
        self.affinity_cutoff_box = QDoubleSpinBox(self.ui.frame_Selectpeptides)
        self.affinity_cutoff_box.setDecimals(2)
        self.affinity_cutoff_box.setRange(-1000.0, 1000.0)
        self.affinity_cutoff_box.setSingleStep(0.1)
        self.affinity_cutoff_box.setValue(-5.0)
        self.affinity_cutoff_box.setSuffix(" kcal/mol")
        self.affinity_cutoff_box.setMinimumWidth(165)
        self.affinity_cutoff_box.setStyleSheet(self.ui.aff_spinbox.styleSheet())
        self.top_n_label = QLabel("Top", self.ui.frame_Selectpeptides)
        self.top_n_box = QSpinBox(self.ui.frame_Selectpeptides)
        self.top_n_box.setRange(0, 1_000_000)
        self.top_n_box.setSpecialValueText("All")
        self.top_n_box.setValue(0)
        self.top_n_box.setMinimumWidth(90)
        self.top_n_box.setStyleSheet(self.ui.aff_spinbox.styleSheet())
        self.ui.horizontalLayout_20.insertWidget(0, self.use_affinity_cutoff)
        self.ui.horizontalLayout_20.insertWidget(1, self.affinity_cutoff_box)
        self.ui.horizontalLayout_20.insertWidget(2, self.top_n_label)
        self.ui.horizontalLayout_20.insertWidget(3, self.top_n_box)
        self.ui.bestpepButton.setText("Rank and Export")

        self.ui.tableWidget.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.ui.tableWidget.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.ui.tableWidget.setAlternatingRowColors(False)
        self.ui.frame_6.setMinimumHeight(205)
        self.ui.label_19.setText("Minimum frequency among filtered peptides")
        self.ui.confidenceSpinbox.setValue(50)
        self.ui.horizontalSlider.setValue(50)
        self.ui.pickAAButton.setText("Analyze Amino Acids")
        self.ui.tableWidget_2.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.ui.tableWidget_2.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.ui.tableWidget_2.setAlternatingRowColors(False)

        self.ui.label_20.setText("Ranked docking pose")
        self.ui.spinBox_pymol.setPrefix("Rank ")
        self.ui.pymol_button.setText("View Cartoon Pose")
        self.ui.resetRPGButton.hide()
        self.ui.frame_14.setMinimumHeight(70)
        self.ui.frame_14.setMaximumHeight(80)

        self.ui.frame_Selectpeptides.hide()
        self.ui.frame_6.hide()
        self.ui.frame_10.hide()
        self.ui.tableWidget_2.hide()
        # The legacy PyMOL controls are replaced by an embedded cartoon viewer
        # in Stage 4B. Keep them out of this analysis-only release.
        self.ui.frame_14.hide()

    def _connect_actions(self):
        self.ui.setpepButton.clicked.connect(self.open_peptide_selector)
        self.ui.directoryButton.clicked.connect(self.choose_output_directory)
        self.ui.stage1Button.clicked.connect(self.show_stage1)
        self.ui.stage2Button.clicked.connect(self.show_stage2)
        self.ui.gotostage2Button.clicked.connect(self.show_stage2)
        self.ui.runchimButton.clicked.connect(self.build_pdb_files)
        self.ui.stage3Button.clicked.connect(self.show_stage3a)
        self.ui.gotostage3Button.clicked.connect(self.show_stage3a)
        self.ui.stage4Button.clicked.connect(self.show_stage4)
        self.ui.gotostage4Button.clicked.connect(self.show_stage4)
        self.ui.obconvertButton.clicked.connect(self.build_pdbqt_files)
        self.ui.selectprotein_stage3Button.clicked.connect(
            self.prepare_receptor_from_pdb
        )
        self.ui.selectpep_stage3Button.clicked.connect(self.select_receptor)
        self.ligand_subset_button.clicked.connect(self.select_ligands)
        self.ui.configureVinaButton.clicked.connect(self.open_vina_configuration)
        self.preview_box_button.clicked.connect(self.open_docking_box_viewer)
        self.ui.runVinaButton.clicked.connect(self.run_vina)
        self.ui.choosedir_stage4.clicked.connect(self.choose_stage4_workspace)
        self.ui.bestpepButton.clicked.connect(self.rank_stage4_results)
        self.ui.pickAAButton.clicked.connect(self.analyze_stage4_sequences)
        self.ui.pymol_button.clicked.connect(self.open_stage4_pose_viewer)
        self.ui.tableWidget.cellClicked.connect(
            lambda row, _column: self.ui.spinBox_pymol.setValue(row + 1)
        )
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
        self.ui.stage4Button.setEnabled(True)

    def show_stage2(self):
        if self.output_file is None:
            return
        self.ui.stackedWidget.setCurrentWidget(self.ui.stage2)
        self.ui.stage1Button.setEnabled(True)
        self.ui.stage2Button.setEnabled(False)
        self.ui.stage3Button.setEnabled(self.pdb_count > 0)
        self.ui.stage4Button.setEnabled(True)

    def show_stage3a(self):
        if self.output_file is None or self.pdb_count == 0:
            return
        self.ui.stackedWidget.setCurrentWidget(self.ui.stage3)
        self.ui.stage1Button.setEnabled(True)
        self.ui.stage2Button.setEnabled(True)
        self.ui.stage3Button.setEnabled(False)
        self.ui.stage4Button.setEnabled(True)

    def show_stage4(self):
        self.ui.stackedWidget.setCurrentWidget(self.ui.stage4)
        self.ui.stage1Button.setEnabled(True)
        self.ui.stage2Button.setEnabled(self.output_file is not None)
        self.ui.stage3Button.setEnabled(self.pdb_count > 0)
        self.ui.stage4Button.setEnabled(False)

        if self.output_file is None:
            return
        workspace = self.output_file.parent
        affinity_report = workspace / "VinaResults" / "affinities.csv"
        if affinity_report.is_file() and workspace != self.stage4_workspace:
            self.load_stage4_workspace(workspace)

    def choose_stage4_workspace(self):
        selected = QFileDialog.getExistingDirectory(
            self,
            "Select an RPG workspace with Vina results",
            str(
                self.stage4_workspace
                or (self.output_file.parent if self.output_file else default_documents_directory())
            ),
        )
        if selected:
            self.load_stage4_workspace(Path(selected))

    def load_stage4_workspace(self, workspace: Path, show_error: bool = True) -> bool:
        workspace = Path(workspace).expanduser().resolve()
        try:
            results = load_ranked_results(workspace)
        except Exception as error:
            if show_error:
                self._show_message(
                    str(error), QMessageBox.Critical, "Cannot load Stage 4 results"
                )
            return False

        self.stage4_workspace = workspace
        if (
            self.output_file is not None
            and workspace == self.output_file.parent
            and self.receptor_file is not None
            and self.receptor_file.is_file()
        ):
            self.stage4_receptor_file = self.receptor_file
        else:
            self.stage4_receptor_file = resolve_workspace_receptor(workspace)
        self.stage4_results = results
        self.stage4_filtered = []
        self.top_n_box.setMaximum(len(results))
        self.top_n_box.setValue(0)
        lowest = results[0].affinity
        highest = results[-1].affinity
        suggested = min(-5.0, highest)
        self.affinity_cutoff_box.setRange(
            min(-1000.0, lowest - 10.0), max(1000.0, highest + 10.0)
        )
        self.affinity_cutoff_box.setValue(suggested)
        self.ui.label_stage4.setText(
            f"Loaded {len(results):,} docking results from {workspace}. "
            f"Affinity range: {lowest:g} to {highest:g} kcal/mol."
        )
        self.ui.frame_Selectpeptides.show()
        self.ui.frame_6.hide()
        self.ui.frame_10.hide()
        self.ui.tableWidget_2.hide()
        self.ui.frame_14.hide()
        self.ui.tableWidget.clearContents()
        self.ui.tableWidget.setRowCount(0)
        self.ui.tableWidget_2.clearContents()
        self.ui.tableWidget_2.setRowCount(0)
        return True

    @staticmethod
    def _table_item(value, numeric: bool = False) -> QTableWidgetItem:
        item = QTableWidgetItem()
        if numeric:
            item.setData(Qt.EditRole, value)
            item.setTextAlignment(Qt.AlignCenter)
        else:
            item.setText(str(value))
        return item

    def rank_stage4_results(self):
        if not self.stage4_results or self.stage4_workspace is None:
            return
        cutoff = (
            self.affinity_cutoff_box.value()
            if self.use_affinity_cutoff.isChecked()
            else None
        )
        top_n = self.top_n_box.value() or None
        try:
            selected = filter_ranked_results(
                self.stage4_results, maximum_affinity=cutoff, top_n=top_n
            )
        except Exception as error:
            self._show_message(
                str(error), QMessageBox.Critical, "Cannot rank Stage 4 results"
            )
            return
        if not selected:
            self._show_message(
                "No docking result meets the selected filters.",
                QMessageBox.Warning,
                "No matching peptides",
            )
            return
        try:
            report = write_best_peptides(
                self.stage4_workspace / "Best-Peptides.csv", selected
            )
        except Exception as error:
            self._show_message(
                str(error), QMessageBox.Critical, "Cannot export ranked peptides"
            )
            return
        self.stage4_filtered = selected
        table = self.ui.tableWidget
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(
            ("Rank", "Peptide ID", "Sequence", "Affinity (kcal/mol)", "Result file")
        )
        table.setRowCount(len(selected))
        for rank, result in enumerate(selected, start=1):
            row = rank - 1
            table.setItem(row, 0, self._table_item(rank, numeric=True))
            table.setItem(row, 1, self._table_item(result.peptide_id, numeric=True))
            table.setItem(row, 2, self._table_item(result.sequence))
            table.setItem(row, 3, self._table_item(result.affinity, numeric=True))
            table.setItem(row, 4, self._table_item(result.result_file))
        table.resizeColumnsToContents()
        table.setColumnWidth(0, 70)
        table.setColumnWidth(1, 105)
        table.setColumnWidth(3, 180)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.ui.frame_6.show()
        self.ui.frame_10.show()
        self.ui.tableWidget_2.hide()
        self.ui.spinBox_pymol.setRange(1, len(selected))
        self.ui.spinBox_pymol.setValue(1)
        self.ui.frame_14.show()
        self.ui.label_stage4.setText(
            f"Ranked {len(selected):,} of {len(self.stage4_results):,} results. "
            f"Exported {report.name} in {self.stage4_workspace}."
        )

    def analyze_stage4_sequences(self):
        if not self.stage4_filtered or self.stage4_workspace is None:
            return
        try:
            enriched = analyze_position_enrichment(
                self.stage4_filtered, self.ui.confidenceSpinbox.value()
            )
            report = write_position_enrichment(
                self.stage4_workspace / "Best-AminoAcids.csv", enriched
            )
        except Exception as error:
            self._show_message(
                str(error), QMessageBox.Critical, "Cannot analyze peptide sequences"
            )
            return

        table = self.ui.tableWidget_2
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(
            ("Peptide position", "Amino acid", "Count", "Frequency (%)")
        )
        table.setRowCount(len(enriched))
        for row, result in enumerate(enriched):
            table.setItem(row, 0, self._table_item(result.position, numeric=True))
            table.setItem(row, 1, self._table_item(result.amino_acid))
            table.setItem(row, 2, self._table_item(result.count, numeric=True))
            table.setItem(
                row, 3, self._table_item(round(result.frequency_percent, 2), numeric=True)
            )
        table.resizeColumnsToContents()
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.show()
        self.ui.label_stage4.setText(
            f"Found {len(enriched):,} position/amino-acid combinations at or above "
            f"{self.ui.confidenceSpinbox.value()}%. Exported {report.name}."
        )

    def open_stage4_pose_viewer(self):
        if not self.stage4_filtered or self.stage4_workspace is None:
            return
        rank = self.ui.spinBox_pymol.value()
        if rank > len(self.stage4_filtered):
            return
        result = self.stage4_filtered[rank - 1]
        pose_path = self.stage4_workspace / "VinaResults" / result.result_file

        receptor_path = self.stage4_receptor_file
        if receptor_path is None or not receptor_path.is_file():
            selected, _ = QFileDialog.getOpenFileName(
                self,
                "Select the rigid receptor used for docking",
                str(self.stage4_workspace / "Receptor"),
                "PDBQT files (*.pdbqt)",
            )
            if not selected:
                return
            receptor_path = Path(selected).expanduser().resolve()
            self.stage4_receptor_file = receptor_path

        try:
            dialog = DockingPoseDialog(
                receptor_path,
                pose_path,
                result.sequence,
                result.affinity,
                parent=self,
            )
        except Exception as error:
            self._show_message(
                str(error), QMessageBox.Critical, "Cartoon pose viewer failed"
            )
            return
        dialog.exec_()

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
        self.stage4_workspace = None
        self.stage4_receptor_file = None
        self.stage4_results = []
        self.stage4_filtered = []
        self.ui.selectprotein_stage3Button.setText("Prepare Receptor from PDB")
        self.ui.selectpep_stage3Button.setText("Use Existing Receptor PDBQT")
        self.ligand_subset_button.setText("Choose Ligand Subset")
        self.ui.Second_Stage3.hide()
        self.ui.Third_Stage3.hide()
        self.ui.stage3Button.hide()
        self.ui.gotostage3Button.hide()
        self.ui.gotostage4Button.hide()
        self.ui.frame_Selectpeptides.hide()
        self.ui.frame_6.hide()
        self.ui.frame_10.hide()
        self.ui.tableWidget_2.hide()
        self.ui.frame_14.hide()
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
        self.ligand_subset_button.setText(
            f"Choose Ligand Subset ({count:,} selected)"
        )
        self._update_vina_readiness()
        self._show_message(
            f"Stage 3A generated {count:,} PDBQT ligands in:\n{output_directory}\n\n"
            "Continue by preparing a cleaned receptor PDB or selecting an "
            "existing rigid receptor PDBQT.",
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
        try:
            receptor = validate_receptor_pdbqt(Path(selected))
        except Exception as error:
            self._show_message(
                str(error), QMessageBox.Critical, "Invalid rigid receptor"
            )
            return
        self.receptor_file = receptor
        self.vina_config = None
        self.ui.runVinaButton.hide()
        self.ui.selectpep_stage3Button.setText(f"Existing: {receptor.name}")
        self._update_vina_readiness()

    def prepare_receptor_from_pdb(self):
        if self.output_file is None:
            return
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Select the cleaned receptor PDB",
            str(self.output_file.parent),
            "Protein Data Bank files (*.pdb)",
        )
        if not selected:
            return

        self.ui.selectprotein_stage3Button.setEnabled(False)
        self.ui.selectpep_stage3Button.setEnabled(False)
        self.ui.selectprotein_stage3Button.setText("Preparing rigid receptor…")
        self.ui.label_11.setText(
            "Meeko is assigning receptor templates, charges and AutoDock atom types…"
        )
        self.receptor_worker = ReceptorWorker(
            Path(selected), self.output_file.parent, self
        )
        self.receptor_worker.completed.connect(self.receptor_preparation_finished)
        self.receptor_worker.failed.connect(self.receptor_preparation_failed)
        self.receptor_worker.start()

    def receptor_preparation_finished(self, receptor_path: str):
        self.receptor_file = Path(receptor_path)
        self.vina_config = None
        self.ui.runVinaButton.hide()
        self.ui.selectprotein_stage3Button.setEnabled(True)
        self.ui.selectpep_stage3Button.setEnabled(True)
        self.ui.selectprotein_stage3Button.setText(
            f"Prepared: {self.receptor_file.name}"
        )
        self._update_vina_readiness()
        self._show_message(
            f"The rigid receptor was prepared with Meeko and saved as:\n"
            f"{self.receptor_file}\n\nNo chains, waters, ligands, metals or "
            "problematic residues were deleted automatically.",
            QMessageBox.Information,
            "Rigid receptor ready",
        )

    def receptor_preparation_failed(self, message: str):
        self.ui.selectprotein_stage3Button.setEnabled(True)
        self.ui.selectpep_stage3Button.setEnabled(True)
        self.ui.selectprotein_stage3Button.setText("Prepare Receptor from PDB")
        self.ui.label_11.setText("Receptor preparation failed: " + message)
        self._show_message(message, QMessageBox.Critical, "Receptor preparation failed")

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
        self.ligand_subset_button.setText(
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

    def open_docking_box_viewer(self):
        if self.receptor_file is None:
            self._show_message(
                "Prepare or select a rigid receptor before opening the box preview.",
                QMessageBox.Warning,
                "Receptor required",
            )
            return

        if self.vina_config is None:
            initial_center = None
            initial_size = (
                self.confwin.ui.sizeX_box.value(),
                self.confwin.ui.sizey_box.value(),
                self.confwin.ui.sizeZ_box.value(),
            )
        else:
            initial_center = self.vina_config.center
            initial_size = self.vina_config.size

        try:
            dialog = DockingBoxDialog(
                self.receptor_file,
                initial_center=initial_center,
                initial_size=initial_size,
                parent=self,
            )
        except Exception as error:
            self._show_message(
                str(error), QMessageBox.Critical, "Docking-box preview failed"
            )
            return

        if dialog.exec_() != QDialog.Accepted:
            return

        for box, value in zip(
            (
                self.confwin.ui.centerx_box,
                self.confwin.ui.centery_box_2,
                self.confwin.ui.centerx_box_3,
            ),
            dialog.center,
        ):
            box.setValue(value)
        for box, value in zip(
            (
                self.confwin.ui.sizeX_box,
                self.confwin.ui.sizey_box,
                self.confwin.ui.sizeZ_box,
            ),
            dialog.size,
        ):
            box.setValue(value)
        self.save_vina_configuration()

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
        self.load_stage4_workspace(self.output_file.parent, show_error=False)
        self.ui.gotostage4Button.show()
        self.ui.gotostage4Button.setEnabled(True)
        self._show_message(
            f"AutoDock Vina completed {count:,} peptide dockings.\n\n"
            f"Results: {output_directory}\n\n"
            "Continue to Stage 4 to rank and analyze the peptide sequences.",
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
    app.setApplicationName("RPG macOS 2.0")
    app.setApplicationVersion("2.0.0")
    app.setOrganizationName("RivasPardoLab")
    QtGui.QFontDatabase.addApplicationFont(str(APP_ROOT / "eight-bit-dragon.otf"))
    app.setWindowIcon(QtGui.QIcon(str(APP_ROOT / "MainWin" / "icons" / "Lab2.png")))

    window = RPGWindow()
    window.show()
    return app.exec_()
