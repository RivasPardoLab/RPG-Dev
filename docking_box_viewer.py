"""Interactive, dependency-free receptor and Vina search-box preview."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from PyQt5.QtCore import QPoint, QPointF, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PyQt5.QtWidgets import (
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


@dataclass(frozen=True)
class AtomPoint:
    x: float
    y: float
    z: float
    atom_type: str


@dataclass(frozen=True)
class ReceptorGeometry:
    atoms: tuple[AtomPoint, ...]
    displayed_atoms: tuple[AtomPoint, ...]
    minimum: tuple[float, float, float]
    maximum: tuple[float, float, float]

    @property
    def center(self) -> tuple[float, float, float]:
        return tuple(
            (low + high) / 2.0 for low, high in zip(self.minimum, self.maximum)
        )

    @property
    def span(self) -> tuple[float, float, float]:
        return tuple(high - low for low, high in zip(self.minimum, self.maximum))


def _parse_atom_line(line: str) -> AtomPoint:
    try:
        x = float(line[30:38])
        y = float(line[38:46])
        z = float(line[46:54])
    except ValueError:
        fields = line.split()
        if len(fields) < 9:
            raise ValueError(f"Invalid receptor atom record: {line}") from None
        x, y, z = map(float, fields[6:9])

    fields = line.split()
    atom_type = fields[-1] if fields else "C"
    return AtomPoint(x, y, z, atom_type)


def load_receptor_geometry(
    receptor_path: Path, max_display_atoms: int = 12000
) -> ReceptorGeometry:
    """Read receptor coordinates and deterministically subsample them for display."""
    receptor_path = Path(receptor_path).expanduser().resolve()
    if not receptor_path.is_file():
        raise FileNotFoundError(f"The receptor file was not found: {receptor_path}")
    if max_display_atoms <= 0:
        raise ValueError("max_display_atoms must be greater than zero")

    atoms = tuple(
        _parse_atom_line(line)
        for line in receptor_path.read_text(encoding="utf-8").splitlines()
        if line.startswith(("ATOM  ", "HETATM"))
    )
    if not atoms:
        raise ValueError("The receptor contains no coordinates to display")

    minimum = tuple(min(getattr(atom, axis) for atom in atoms) for axis in "xyz")
    maximum = tuple(max(getattr(atom, axis) for atom in atoms) for axis in "xyz")
    stride = max(1, math.ceil(len(atoms) / max_display_atoms))
    displayed = atoms[::stride]
    return ReceptorGeometry(atoms, displayed, minimum, maximum)


ATOM_COLORS = {
    "C": QColor(155, 165, 175),
    "A": QColor(155, 165, 175),
    "N": QColor(92, 140, 255),
    "NA": QColor(92, 140, 255),
    "O": QColor(245, 88, 88),
    "OA": QColor(245, 88, 88),
    "S": QColor(245, 205, 70),
    "SA": QColor(245, 205, 70),
    "P": QColor(255, 155, 55),
    "H": QColor(225, 225, 225),
    "HD": QColor(225, 225, 225),
}


class ProteinCanvas(QWidget):
    boxMoved = pyqtSignal(float, float, float)

    BOX_EDGES = (
        (0, 1), (1, 3), (3, 2), (2, 0),
        (4, 5), (5, 7), (7, 6), (6, 4),
        (0, 4), (1, 5), (2, 6), (3, 7),
    )
    BOX_FACES = (
        (0, 1, 3, 2), (4, 5, 7, 6),
        (0, 1, 5, 4), (2, 3, 7, 6),
        (0, 2, 6, 4), (1, 3, 7, 5),
    )

    def __init__(self, geometry: ReceptorGeometry, parent=None):
        super().__init__(parent)
        self.geometry = geometry
        self.box_center = list(geometry.center)
        self.box_size = [60.0, 60.0, 60.0]
        self.yaw = math.radians(-35)
        self.pitch = math.radians(22)
        self.zoom = 1.0
        self.last_mouse_position: Optional[QPoint] = None
        self.dragging_box = False
        self.setMinimumSize(650, 560)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setStyleSheet("background: #10141a; border: 1px solid #44505c;")

    def set_box(self, center: Sequence[float], size: Sequence[float]) -> None:
        self.box_center = [float(value) for value in center]
        self.box_size = [max(0.5, float(value)) for value in size]
        self.update()

    def reset_view(self) -> None:
        self.yaw = math.radians(-35)
        self.pitch = math.radians(22)
        self.zoom = 1.0
        self.update()

    def _rotate(self, point: Sequence[float]) -> tuple[float, float, float]:
        x, y, z = point
        cosine_yaw, sine_yaw = math.cos(self.yaw), math.sin(self.yaw)
        cosine_pitch, sine_pitch = math.cos(self.pitch), math.sin(self.pitch)
        rotated_x = cosine_yaw * x + sine_yaw * z
        yaw_z = -sine_yaw * x + cosine_yaw * z
        rotated_y = cosine_pitch * y - sine_pitch * yaw_z
        rotated_z = sine_pitch * y + cosine_pitch * yaw_z
        return rotated_x, rotated_y, rotated_z

    def _scale(self) -> float:
        extent = max(max(self.geometry.span), max(self.box_size), 1.0)
        return max(0.1, min(self.width(), self.height()) * 0.72 / extent * self.zoom)

    def _project(self, point: Sequence[float]) -> tuple[QPointF, float]:
        origin = self.geometry.center
        relative = tuple(value - base for value, base in zip(point, origin))
        x, y, depth = self._rotate(relative)
        scale = self._scale()
        return QPointF(self.width() / 2 + x * scale, self.height() / 2 - y * scale), depth

    def _box_corners(self) -> list[tuple[float, float, float]]:
        halves = [value / 2.0 for value in self.box_size]
        return [
            tuple(
                self.box_center[axis] + sign[axis] * halves[axis]
                for axis in range(3)
            )
            for sign in (
                (-1, -1, -1), (1, -1, -1),
                (-1, 1, -1), (1, 1, -1),
                (-1, -1, 1), (1, -1, 1),
                (-1, 1, 1), (1, 1, 1),
            )
        ]

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor(16, 20, 26))

        projected_atoms = []
        for atom in self.geometry.displayed_atoms:
            position, depth = self._project((atom.x, atom.y, atom.z))
            projected_atoms.append((depth, position, atom.atom_type.upper()))
        projected_atoms.sort(key=lambda item: item[0])

        depth_span = max(max(self.geometry.span), 1.0)
        for depth, position, atom_type in projected_atoms:
            color = ATOM_COLORS.get(atom_type, QColor(125, 205, 145))
            color.setAlpha(185)
            radius = max(1.1, min(3.4, 2.0 + depth / depth_span))
            painter.setPen(Qt.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(position, radius, radius)

        projected_corners = [self._project(corner) for corner in self._box_corners()]
        faces = sorted(
            self.BOX_FACES,
            key=lambda face: sum(projected_corners[index][1] for index in face) / 4,
        )
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(30, 205, 235, 25))
        for face in faces:
            painter.drawPolygon(QPolygonF([projected_corners[index][0] for index in face]))

        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(40, 225, 250), 2))
        for start, end in self.BOX_EDGES:
            painter.drawLine(projected_corners[start][0], projected_corners[end][0])

        center_point, _ = self._project(self.box_center)
        painter.setPen(QPen(QColor(255, 225, 95), 2))
        painter.drawLine(center_point + QPointF(-7, 0), center_point + QPointF(7, 0))
        painter.drawLine(center_point + QPointF(0, -7), center_point + QPointF(0, 7))

        painter.setFont(QFont("Helvetica", 10))
        painter.setPen(QColor(210, 220, 230))
        painter.drawText(14, 24, "Drag: rotate   Shift+drag: move box   Wheel: zoom")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.last_mouse_position = event.pos()
            self.dragging_box = bool(event.modifiers() & Qt.ShiftModifier)
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        if self.last_mouse_position is None or not event.buttons() & Qt.LeftButton:
            return
        delta = event.pos() - self.last_mouse_position
        self.last_mouse_position = event.pos()
        if self.dragging_box:
            distance_x = delta.x() / self._scale()
            distance_y = -delta.y() / self._scale()
            cosine_yaw, sine_yaw = math.cos(self.yaw), math.sin(self.yaw)
            cosine_pitch, sine_pitch = math.cos(self.pitch), math.sin(self.pitch)
            right = (cosine_yaw, 0.0, sine_yaw)
            up = (sine_pitch * sine_yaw, cosine_pitch, -sine_pitch * cosine_yaw)
            for axis in range(3):
                self.box_center[axis] += distance_x * right[axis] + distance_y * up[axis]
            self.boxMoved.emit(*self.box_center)
        else:
            self.yaw += delta.x() * 0.008
            self.pitch = max(
                math.radians(-89),
                min(math.radians(89), self.pitch + delta.y() * 0.008),
            )
        self.update()

    def mouseReleaseEvent(self, event):
        self.last_mouse_position = None
        self.dragging_box = False
        self.unsetCursor()

    def wheelEvent(self, event):
        factor = 1.12 if event.angleDelta().y() > 0 else 1 / 1.12
        self.zoom = max(0.2, min(8.0, self.zoom * factor))
        self.update()


class DockingBoxDialog(QDialog):
    def __init__(
        self,
        receptor_path: Path,
        initial_center: Optional[Sequence[float]] = None,
        initial_size: Sequence[float] = (60.0, 60.0, 60.0),
        parent=None,
    ):
        super().__init__(parent)
        self.receptor_path = Path(receptor_path)
        self.geometry = load_receptor_geometry(self.receptor_path)
        self.setWindowTitle("RPG Docking Box Preview")
        self.resize(1050, 700)
        self.setModal(True)

        root = QHBoxLayout(self)
        self.canvas = ProteinCanvas(self.geometry, self)
        root.addWidget(self.canvas, 1)

        controls = QVBoxLayout()
        controls.setSpacing(12)
        title = QLabel("AutoDock Vina search box")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        controls.addWidget(title)
        details = QLabel(
            f"{self.receptor_path.name}\n"
            f"{len(self.geometry.atoms):,} atoms "
            f"({len(self.geometry.displayed_atoms):,} displayed)"
        )
        details.setWordWrap(True)
        controls.addWidget(details)

        form = QFormLayout()
        self.center_boxes = [self._coordinate_box() for _ in range(3)]
        self.size_boxes = [self._size_box() for _ in range(3)]
        for axis, box in zip("XYZ", self.center_boxes):
            form.addRow(f"Center {axis} (Å)", box)
        for axis, box in zip("XYZ", self.size_boxes):
            form.addRow(f"Size {axis} (Å)", box)
        controls.addLayout(form)

        self.volume_label = QLabel()
        controls.addWidget(self.volume_label)
        center_button = QPushButton("Center box on receptor")
        center_button.clicked.connect(self.center_on_receptor)
        controls.addWidget(center_button)
        fit_button = QPushButton("Fit whole receptor (+4 Å)")
        fit_button.clicked.connect(self.fit_whole_receptor)
        controls.addWidget(fit_button)
        view_button = QPushButton("Reset view")
        view_button.clicked.connect(self.canvas.reset_view)
        controls.addWidget(view_button)
        controls.addStretch(1)

        help_label = QLabel(
            "Rotate the receptor to inspect the site. Hold Shift while "
            "dragging to move the box in the current viewing plane. Use the "
            "numeric controls for precise coordinates and depth."
        )
        help_label.setWordWrap(True)
        help_label.setStyleSheet("color: #607080;")
        controls.addWidget(help_label)

        apply_button = QPushButton("Use Box in Vina")
        apply_button.setDefault(True)
        apply_button.clicked.connect(self.accept)
        controls.addWidget(apply_button)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        controls.addWidget(cancel_button)
        root.addLayout(controls)

        center = initial_center if initial_center is not None else self.geometry.center
        for box, value in zip(self.center_boxes, center):
            box.setValue(float(value))
        for box, value in zip(self.size_boxes, initial_size):
            box.setValue(float(value))
        for box in (*self.center_boxes, *self.size_boxes):
            box.valueChanged.connect(self._controls_changed)
        self.canvas.boxMoved.connect(self._canvas_box_moved)
        self._controls_changed()

    @staticmethod
    def _coordinate_box() -> QDoubleSpinBox:
        box = QDoubleSpinBox()
        box.setRange(-10000.0, 10000.0)
        box.setDecimals(2)
        box.setSingleStep(0.5)
        return box

    @staticmethod
    def _size_box() -> QDoubleSpinBox:
        box = QDoubleSpinBox()
        box.setRange(0.5, 1000.0)
        box.setDecimals(2)
        box.setSingleStep(0.5)
        box.setValue(60.0)
        return box

    @property
    def center(self) -> tuple[float, float, float]:
        return tuple(box.value() for box in self.center_boxes)

    @property
    def size(self) -> tuple[float, float, float]:
        return tuple(box.value() for box in self.size_boxes)

    def _controls_changed(self):
        self.canvas.set_box(self.center, self.size)
        volume = math.prod(self.size)
        self.volume_label.setText(f"Search volume: {volume:,.1f} Å³")

    def _canvas_box_moved(self, x: float, y: float, z: float):
        for box, value in zip(self.center_boxes, (x, y, z)):
            box.blockSignals(True)
            box.setValue(value)
            box.blockSignals(False)
        self._controls_changed()

    def center_on_receptor(self):
        for box, value in zip(self.center_boxes, self.geometry.center):
            box.setValue(value)

    def fit_whole_receptor(self):
        self.center_on_receptor()
        for box, value in zip(self.size_boxes, self.geometry.span):
            box.setValue(max(0.5, value + 4.0))
