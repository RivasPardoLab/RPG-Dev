import json
import tempfile
import unittest
from pathlib import Path

from stage2 import build_peptide_pdb
from stage3a import convert_pdb_to_pdbqt
from stage3b import VinaConfig, run_vina_docking, write_vina_config


def _make_inputs(workspace: Path):
    pdb = workspace / "peptide.pdb"
    ligand = workspace / "1.pdbqt"
    receptor = workspace / "receptor.pdbqt"
    build_peptide_pdb("AG", pdb)
    convert_pdb_to_pdbqt(pdb, ligand)
    atoms = [
        line
        for line in ligand.read_text(encoding="utf-8").splitlines()
        if line.startswith(("ATOM  ", "HETATM"))
    ]
    receptor.write_text("\n".join(atoms) + "\n", encoding="utf-8")
    return receptor, ligand


def _config():
    return VinaConfig(
        center_x=2,
        center_y=-1,
        center_z=0,
        size_x=20,
        size_y=20,
        size_z=20,
        exhaustiveness=1,
        num_modes=2,
        energy_range=4,
    )


class Stage3BTests(unittest.TestCase):
    def test_config_preserves_rpg_parameters(self):
        with tempfile.TemporaryDirectory() as temp_name:
            path = write_vina_config(Path(temp_name) / "config.txt", _config())
            text = path.read_text(encoding="utf-8")

            self.assertIn("center_x = 2\n", text)
            self.assertIn("size_y = 20\n", text)
            self.assertIn("num_modes = 2\n", text)
            self.assertIn("energy_range = 4\n", text)
            self.assertIn("exhaustiveness = 1\n", text)

    def test_results_and_reproducibility_reports_are_published(self):
        with tempfile.TemporaryDirectory() as temp_name:
            workspace = Path(temp_name)
            receptor, ligand = _make_inputs(workspace)

            def fake_dock(receptor_path, ligand_path, destination, config):
                atom = next(
                    line
                    for line in ligand_path.read_text(encoding="utf-8").splitlines()
                    if line.startswith("ATOM  ")
                )
                destination.write_text(
                    "MODEL 1\nREMARK VINA RESULT:    -4.250      0.000      0.000\n"
                    + atom
                    + "\nENDMDL\n",
                    encoding="utf-8",
                )
                return {"engine": "test-vina", "version": "1", "seed": 7}

            progress = []
            generated = run_vina_docking(
                receptor,
                [ligand],
                workspace,
                _config(),
                progress=progress.append,
                dock_one=fake_dock,
            )

            self.assertEqual([path.name for path in generated], ["1-out.pdbqt"])
            self.assertEqual(progress, [1])
            manifest = json.loads(
                (workspace / "VinaResults" / "docking-manifest.json").read_text()
            )
            self.assertEqual(manifest["results"][0]["seed"], 7)
            self.assertEqual(
                manifest["results"][0]["best_affinity_kcal_mol"], -4.25
            )
            self.assertTrue((workspace / "VinaResults" / "affinities.csv").is_file())

    def test_existing_results_are_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp_name:
            workspace = Path(temp_name)
            receptor, ligand = _make_inputs(workspace)
            results = workspace / "VinaResults"
            results.mkdir()
            existing = results / "keep.txt"
            existing.write_text("keep\n", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                run_vina_docking(receptor, [ligand], workspace, _config())

            self.assertEqual(existing.read_text(encoding="utf-8"), "keep\n")

    def test_official_vina_binding_produces_a_valid_pose(self):
        try:
            import vina  # noqa: F401
        except ImportError:
            self.skipTest("AutoDock Vina bindings are not installed")

        with tempfile.TemporaryDirectory() as temp_name:
            workspace = Path(temp_name)
            receptor, ligand = _make_inputs(workspace)
            generated = run_vina_docking(receptor, [ligand], workspace, _config())

            result = generated[0].read_text(encoding="utf-8")
            self.assertIn("REMARK VINA RESULT:", result)
            self.assertIn("MODEL 1", result)


if __name__ == "__main__":
    unittest.main()
