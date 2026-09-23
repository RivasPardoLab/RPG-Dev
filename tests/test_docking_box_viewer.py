import tempfile
import unittest
from pathlib import Path

from docking_box_viewer import load_receptor_geometry, smooth_cartoon_trace


def atom_line(serial: int, x: float, y: float, z: float, atom_type: str = "C") -> str:
    return (
        f"ATOM  {serial:5d}  C   ALA A   1    "
        f"{x:8.3f}{y:8.3f}{z:8.3f}  1.00  0.00     0.000 {atom_type}\n"
    )


def backbone_line(
    serial: int,
    residue_number: int,
    x: float,
    y: float,
    z: float,
    chain: str = "A",
) -> str:
    return (
        f"ATOM  {serial:5d}  CA  ALA {chain}{residue_number:4d}    "
        f"{x:8.3f}{y:8.3f}{z:8.3f}  1.00  0.00     0.000 C\n"
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

    def test_cartoon_backbone_is_sorted_by_residue_not_pdbqt_torsion_order(self):
        with tempfile.TemporaryDirectory() as temp_name:
            path = Path(temp_name) / "peptide.pdbqt"
            path.write_text(
                backbone_line(1, 3, 6.0, 0.0, 0.0)
                + backbone_line(2, 1, 0.0, 0.0, 0.0)
                + backbone_line(3, 2, 3.0, 0.0, 0.0),
                encoding="utf-8",
            )

            geometry = load_receptor_geometry(path)

            self.assertEqual(len(geometry.cartoon_segments), 1)
            self.assertEqual(
                [atom.residue_number for atom in geometry.cartoon_segments[0]],
                [1, 2, 3],
            )

    def test_only_the_best_vina_model_is_loaded_for_cartoon_viewing(self):
        with tempfile.TemporaryDirectory() as temp_name:
            path = Path(temp_name) / "pose.pdbqt"
            path.write_text(
                "MODEL 1\n"
                + backbone_line(1, 1, 1.0, 2.0, 3.0)
                + "ENDMDL\nMODEL 2\n"
                + backbone_line(1, 1, 100.0, 200.0, 300.0)
                + "ENDMDL\n",
                encoding="utf-8",
            )

            geometry = load_receptor_geometry(path)

            self.assertEqual(len(geometry.atoms), 1)
            self.assertEqual(geometry.center, (1.0, 2.0, 3.0))

    def test_cartoon_trace_is_smoothed_without_moving_its_endpoints(self):
        trace = smooth_cartoon_trace(((0, 0, 0), (2, 1, 0), (4, 0, 0)), 4)

        self.assertEqual(trace[0], (0.0, 0.0, 0.0))
        self.assertEqual(trace[-1], (4.0, 0.0, 0.0))
        self.assertGreater(len(trace), 3)


if __name__ == "__main__":
    unittest.main()
