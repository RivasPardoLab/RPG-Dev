"""Embedded Stage 4B cartoon viewer for receptor–peptide docking poses."""

from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from docking_box_viewer import ProteinCanvas, load_receptor_geometry


class DockingPoseDialog(QDialog):
    def __init__(
        self,
        receptor_path: Path,
        pose_path: Path,
        sequence: str,
        affinity: float,
        parent=None,
    ):
        super().__init__(parent)
        self.receptor_path = Path(receptor_path).expanduser().resolve()
        self.pose_path = Path(pose_path).expanduser().resolve()
        receptor = load_receptor_geometry(self.receptor_path)
        peptide = load_receptor_geometry(self.pose_path)
        if not receptor.cartoon_segments:
            raise ValueError(
                "The receptor does not contain C-alpha records required for "
                "cartoon rendering"
            )
        if not peptide.cartoon_segments:
            raise ValueError(
                "The peptide pose does not contain C-alpha records required for "
                "cartoon rendering"
            )

        self.setWindowTitle("RPG Stage 4B — Docking Pose")
        self.resize(1100, 700)
        self.setModal(True)

        root = QHBoxLayout(self)
        self.canvas = ProteinCanvas(
            receptor,
            self,
            overlay_geometry=peptide,
            show_box=False,
        )
        root.addWidget(self.canvas, 1)

        controls = QVBoxLayout()
        controls.setSpacing(12)
        title = QLabel("Receptor–peptide pose")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        controls.addWidget(title)

        details = QLabel(
            f"Sequence: {sequence}\n"
            f"Best Vina affinity: {affinity:g} kcal/mol\n\n"
            f"Receptor: {self.receptor_path.name}\n"
            f"Pose: {self.pose_path.name}"
        )
        details.setWordWrap(True)
        controls.addWidget(details)

        receptor_legend = QLabel("● Receptor cartoon")
        receptor_legend.setStyleSheet("color: rgb(100, 180, 225); font-weight: bold;")
        controls.addWidget(receptor_legend)
        peptide_legend = QLabel("● Peptide cartoon")
        peptide_legend.setStyleSheet("color: rgb(255, 155, 75); font-weight: bold;")
        controls.addWidget(peptide_legend)

        representation = QLabel(
            "Both structures are rendered from their protein backbone as "
            "smoothed cartoon traces. The first Vina pose (the best-scoring "
            "mode) is displayed."
        )
        representation.setWordWrap(True)
        representation.setStyleSheet("color: #607080;")
        controls.addWidget(representation)

        reset_button = QPushButton("Reset view")
        reset_button.clicked.connect(self.canvas.reset_view)
        controls.addWidget(reset_button)
        controls.addStretch(1)

        help_label = QLabel("Drag to rotate the complex and use the wheel to zoom.")
        help_label.setWordWrap(True)
        help_label.setStyleSheet("color: #607080;")
        controls.addWidget(help_label)

        close_button = QPushButton("Close")
        close_button.setDefault(True)
        close_button.clicked.connect(self.accept)
        controls.addWidget(close_button)
        root.addLayout(controls)

        self.setAttribute(Qt.WA_DeleteOnClose, True)
