"""Interactive cartoon rendering for receptors, poses, and the Vina box."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from PyQt5.QtCore import QPoint, QPointF, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF
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
    atom_name: str = ""
    residue_name: str = ""
    chain_id: str = ""
    residue_number: int = 0
    insertion_code: str = ""


@dataclass(frozen=True)
class ReceptorGeometry:
    atoms: tuple[AtomPoint, ...]
    displayed_atoms: tuple[AtomPoint, ...]
    cartoon_segments: tuple[tuple[AtomPoint, ...], ...]
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

    @property
    def cartoon_residue_count(self) -> int:
        return sum(len(segment) for segment in self.cartoon_segments)


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
    atom_name = line[12:16].strip()
    residue_name = line[17:20].strip()
    chain_id = line[21:22].strip()
    insertion_code = line[26:27].strip()
    try:
        residue_number = int(line[22:26])
    except ValueError:
        try:
            residue_number = int(fields[5])
        except (IndexError, ValueError):
            residue_number = 0
    return AtomPoint(
        x,
        y,
        z,
        atom_type,
        atom_name,
        residue_name,
        chain_id,
        residue_number,
        insertion_code,
    )


def _distance(first: AtomPoint, second: AtomPoint) -> float:
    return math.sqrt(
        (first.x - second.x) ** 2
        + (first.y - second.y) ** 2
        + (first.z - second.z) ** 2
    )


def build_cartoon_segments(
    atoms: Sequence[AtomPoint], maximum_ca_distance: float = 6.0
) -> tuple[tuple[AtomPoint, ...], ...]:
    """Build ordered protein backbone segments from one C-alpha per residue."""
    if maximum_ca_distance <= 0:
        raise ValueError("maximum_ca_distance must be greater than zero")

    residues = {}
    for atom in atoms:
        if atom.atom_name.upper() != "CA":
            continue
        key = (atom.chain_id, atom.residue_number, atom.insertion_code)
        residues.setdefault(key, atom)

    ordered = sorted(
        residues.values(),
        key=lambda atom: (atom.chain_id, atom.residue_number, atom.insertion_code),
    )
    segments = []
    current = []
    for atom in ordered:
        if current and (
            atom.chain_id != current[-1].chain_id
            or _distance(current[-1], atom) > maximum_ca_distance
        ):
            segments.append(tuple(current))
            current = []
        current.append(atom)
    if current:
        segments.append(tuple(current))
    return tuple(segments)


def smooth_cartoon_trace(
    points: Sequence[Sequence[float]], samples_per_span: int = 8
) -> tuple[tuple[float, float, float], ...]:
    """Interpolate a C-alpha trace with a Catmull-Rom spline."""
    points = tuple(tuple(float(value) for value in point) for point in points)
    if samples_per_span <= 0:
        raise ValueError("samples_per_span must be greater than zero")
    if len(points) < 3:
        return points

    smoothed = [points[0]]
    for index in range(len(points) - 1):
        p0 = points[max(0, index - 1)]
        p1 = points[index]
        p2 = points[index + 1]
        p3 = points[min(len(points) - 1, index + 2)]
        for sample in range(1, samples_per_span + 1):
            t = sample / samples_per_span
            t2 = t * t
            t3 = t2 * t
            smoothed.append(
                tuple(
                    0.5
                    * (
                        2 * p1[axis]
                        + (-p0[axis] + p2[axis]) * t
                        + (2 * p0[axis] - 5 * p1[axis] + 4 * p2[axis] - p3[axis])
                        * t2
                        + (-p0[axis] + 3 * p1[axis] - 3 * p2[axis] + p3[axis])
                        * t3
                    )
                    for axis in range(3)
                )
            )
    return tuple(smoothed)


def load_receptor_geometry(
    receptor_path: Path, max_display_atoms: int = 12000
) -> ReceptorGeometry:
    """Read receptor coordinates and deterministically subsample them for display."""
    receptor_path = Path(receptor_path).expanduser().resolve()
    if not receptor_path.is_file():
        raise FileNotFoundError(f"The receptor file was not found: {receptor_path}")
    if max_display_atoms <= 0:
        raise ValueError("max_display_atoms must be greater than zero")

    atoms_list = []
    found_model = False
    for line in receptor_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("MODEL"):
            if found_model:
                break
            found_model = True
            continue
        if found_model and line.startswith("ENDMDL"):
            break
        if line.startswith(("ATOM  ", "HETATM")):
            atoms_list.append(_parse_atom_line(line))
    atoms = tuple(atoms_list)
    if not atoms:
        raise ValueError("The receptor contains no coordinates to display")

    minimum = tuple(min(getattr(atom, axis) for atom in atoms) for axis in "xyz")
    maximum = tuple(max(getattr(atom, axis) for atom in atoms) for axis in "xyz")
    stride = max(1, math.ceil(len(atoms) / max_display_atoms))
    displayed = atoms[::stride]
    cartoons = build_cartoon_segments(atoms)
    return ReceptorGeometry(atoms, displayed, cartoons, minimum, maximum)


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

    def __init__(
        self,
        geometry: ReceptorGeometry,
        parent=None,
        overlay_geometry: Optional[ReceptorGeometry] = None,
        show_box: bool = True,
    ):
        super().__init__(parent)
        self.geometry = geometry
        self.overlay_geometry = overlay_geometry
        self.show_box = show_box
        if overlay_geometry is None:
            self.view_center = geometry.center
            self.view_span = geometry.span
        else:
            view_minimum = tuple(
                min(first, second)
                for first, second in zip(geometry.minimum, overlay_geometry.minimum)
            )
            view_maximum = tuple(
                max(first, second)
                for first, second in zip(geometry.maximum, overlay_geometry.maximum)
            )
            self.view_center = tuple(
                (low + high) / 2.0
                for low, high in zip(view_minimum, view_maximum)
            )
            self.view_span = tuple(
                high - low for low, high in zip(view_minimum, view_maximum)
            )
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
        extents = [max(self.view_span), 1.0]
        if self.show_box:
            extents.append(max(self.box_size))
        extent = max(extents)
        return max(0.1, min(self.width(), self.height()) * 0.72 / extent * self.zoom)

    def _project(self, point: Sequence[float]) -> tuple[QPointF, float]:
        origin = self.view_center
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

    def _draw_atom_fallback(
        self, painter: QPainter, geometry: ReceptorGeometry
    ) -> None:
        projected_atoms = []
        for atom in geometry.displayed_atoms:
            position, depth = self._project((atom.x, atom.y, atom.z))
            projected_atoms.append((depth, position, atom.atom_type.upper()))
        projected_atoms.sort(key=lambda item: item[0])

        depth_span = max(max(geometry.span), 1.0)
        for depth, position, atom_type in projected_atoms:
            color = ATOM_COLORS.get(atom_type, QColor(125, 205, 145))
            color.setAlpha(170)
            radius = max(1.1, min(3.4, 2.0 + depth / depth_span))
            painter.setPen(Qt.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(position, radius, radius)

    def _draw_cartoon(
        self,
        painter: QPainter,
        geometry: ReceptorGeometry,
        color: QColor,
        width: float,
    ) -> None:
        traces = []
        for segment in geometry.cartoon_segments:
            coordinates = [(atom.x, atom.y, atom.z) for atom in segment]
            trace = smooth_cartoon_trace(coordinates)
            projected = [self._project(point) for point in trace]
            mean_depth = sum(point[1] for point in projected) / len(projected)
            traces.append((mean_depth, projected))

        for _, projected in sorted(traces, key=lambda item: item[0]):
            if len(projected) == 1:
                painter.setPen(Qt.NoPen)
                painter.setBrush(color)
                painter.drawEllipse(projected[0][0], width / 2, width / 2)
                continue
            path = QPainterPath(projected[0][0])
            for point, _ in projected[1:]:
                path.lineTo(point)
            outline = QPen(QColor(18, 25, 31, 220), width + 3.0)
            outline.setCapStyle(Qt.RoundCap)
            outline.setJoinStyle(Qt.RoundJoin)
            painter.setPen(outline)
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)
            ribbon = QPen(color, width)
            ribbon.setCapStyle(Qt.RoundCap)
            ribbon.setJoinStyle(Qt.RoundJoin)
            painter.setPen(ribbon)
            painter.drawPath(path)

            # Small C-alpha markers make short peptide cartoons unambiguous.
            painter.setPen(QPen(color.lighter(125), 1))
            painter.setBrush(color.lighter(115))
            marker_radius = max(1.8, width * 0.24)
            for atom in segment:
                position, _ = self._project((atom.x, atom.y, atom.z))
                painter.drawEllipse(position, marker_radius, marker_radius)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor(16, 20, 26))

        if self.geometry.cartoon_segments:
            self._draw_cartoon(
                painter, self.geometry, QColor(100, 180, 225, 225), 7.5
            )
        else:
            self._draw_atom_fallback(painter, self.geometry)

        if self.overlay_geometry is not None:
            if self.overlay_geometry.cartoon_segments:
                self._draw_cartoon(
                    painter,
                    self.overlay_geometry,
                    QColor(255, 155, 75, 245),
                    9.0,
                )
            else:
                self._draw_atom_fallback(painter, self.overlay_geometry)

        if self.show_box:
            projected_corners = [
                self._project(corner) for corner in self._box_corners()
            ]
            faces = sorted(
                self.BOX_FACES,
                key=lambda face: sum(
                    projected_corners[index][1] for index in face
                )
                / 4,
            )
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(30, 205, 235, 25))
            for face in faces:
                painter.drawPolygon(
                    QPolygonF([projected_corners[index][0] for index in face])
                )

            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(40, 225, 250), 2))
            for start, end in self.BOX_EDGES:
                painter.drawLine(
                    projected_corners[start][0], projected_corners[end][0]
                )

            center_point, _ = self._project(self.box_center)
            painter.setPen(QPen(QColor(255, 225, 95), 2))
            painter.drawLine(
                center_point + QPointF(-7, 0), center_point + QPointF(7, 0)
            )
            painter.drawLine(
                center_point + QPointF(0, -7), center_point + QPointF(0, 7)
            )

        painter.setFont(QFont("Helvetica", 10))
        painter.setPen(QColor(210, 220, 230))
        instructions = "Drag: rotate   Wheel: zoom"
        if self.show_box:
            instructions += "   Shift+drag: move box"
        painter.drawText(14, 24, instructions)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.last_mouse_position = event.pos()
            self.dragging_box = self.show_box and bool(
                event.modifiers() & Qt.ShiftModifier
            )
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
        segment_count = len(self.geometry.cartoon_segments)
        segment_word = "segment" if segment_count == 1 else "segments"
        details = QLabel(
            f"{self.receptor_path.name}\n"
            f"Cartoon: {self.geometry.cartoon_residue_count:,} residues in "
            f"{segment_count:,} backbone {segment_word}"
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
