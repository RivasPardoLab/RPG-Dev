import tempfile
import unittest
from pathlib import Path

from docking_box_viewer import load_receptor_geometry


def atom_line(serial: int, x: float, y: float, z: float, atom_type: str = "C") -> str:
    return (
        f"ATOM  {serial:5d}  C   ALA A   1    "
        f"{x:8.3f}{y:8.3f}{z:8.3f}  1.00  0.00     0.000 {atom_type}\n"
    )


class DockingBoxGeometryTests(unittest.TestCase):
    def test_loads_receptor_bounds_center_and_span(self):
        with tempfile.TemporaryDirectory() as temp_name:
            path = Path(temp_name) / "receptor.pdbqt"
            path.write_text(
                atom_line(1, -2.0, 1.0, 5.0, "C")
                + atom_line(2, 4.0, 7.0, -1.0, "OA"),
                encoding="utf-8",
            )

            geometry = load_receptor_geometry(path)

            self.assertEqual(geometry.minimum, (-2.0, 1.0, -1.0))
            self.assertEqual(geometry.maximum, (4.0, 7.0, 5.0))
            self.assertEqual(geometry.center, (1.0, 4.0, 2.0))
            self.assertEqual(geometry.span, (6.0, 6.0, 6.0))
            self.assertEqual(geometry.atoms[1].atom_type, "OA")

    def test_large_receptors_are_deterministically_subsampled(self):
        with tempfile.TemporaryDirectory() as temp_name:
            path = Path(temp_name) / "receptor.pdbqt"
            path.write_text(
                "".join(atom_line(index + 1, index, 0.0, 0.0) for index in range(10)),
                encoding="utf-8",
            )

            geometry = load_receptor_geometry(path, max_display_atoms=3)

            self.assertEqual(len(geometry.atoms), 10)
            self.assertEqual([atom.x for atom in geometry.displayed_atoms], [0, 4, 8])

    def test_rejects_a_file_without_coordinates(self):
        with tempfile.TemporaryDirectory() as temp_name:
            path = Path(temp_name) / "empty.pdbqt"
            path.write_text("REMARK no atoms\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "no coordinates"):
                load_receptor_geometry(path)


if __name__ == "__main__":
    unittest.main()
