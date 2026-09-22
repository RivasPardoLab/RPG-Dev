import json
import tempfile
import unittest
from pathlib import Path

from stage2 import build_peptide_pdb
from stage3_receptor import prepare_rigid_receptor, receptor_manifest_path
from stage3b import validate_receptor_pdbqt


class ReceptorPreparationTests(unittest.TestCase):
    def test_meeko_generates_a_rigid_vina_receptor(self):
        try:
            import meeko  # noqa: F401
        except ImportError:
            self.skipTest("Meeko is not installed")

        with tempfile.TemporaryDirectory() as temp_name:
            workspace = Path(temp_name)
            source = workspace / "cleaned.pdb"
            build_peptide_pdb("ACDEFG", source)

            receptor = prepare_rigid_receptor(source, workspace)
            text = receptor.read_text(encoding="utf-8")

            self.assertEqual(receptor.name, "cleaned_receptor.pdbqt")
            self.assertIn("ATOM", text)
            self.assertNotIn("ROOT", text)
            self.assertNotIn("BRANCH", text)
            self.assertNotIn("TORSDOF", text)
            self.assertEqual(validate_receptor_pdbqt(receptor), receptor.resolve())

            manifest = json.loads(receptor_manifest_path(receptor).read_text())
            self.assertEqual(manifest["preparation"]["engine"], "Meeko")
            self.assertEqual(manifest["preparation"]["mode"], "rigid receptor")
            self.assertFalse(manifest["preparation"]["bad_residues_deleted"])

    def test_receptor_is_accepted_by_vina_parser(self):
        try:
            from vina import Vina
            import meeko  # noqa: F401
        except ImportError:
            self.skipTest("Meeko or Vina is not installed")

        with tempfile.TemporaryDirectory() as temp_name:
            workspace = Path(temp_name)
            source = workspace / "cleaned.pdb"
            build_peptide_pdb("AG", source)
            receptor = prepare_rigid_receptor(source, workspace)

            engine = Vina(verbosity=0)
            engine.set_receptor(str(receptor))
            self.assertEqual(engine.info()["rigid_receptor"], str(receptor))

    def test_existing_receptor_is_not_overwritten(self):
        try:
            import meeko  # noqa: F401
        except ImportError:
            self.skipTest("Meeko is not installed")

        with tempfile.TemporaryDirectory() as temp_name:
            workspace = Path(temp_name)
            source = workspace / "cleaned.pdb"
            build_peptide_pdb("AG", source)
            receptor = prepare_rigid_receptor(source, workspace)
            original = receptor.read_text(encoding="utf-8")

            with self.assertRaises(FileExistsError):
                prepare_rigid_receptor(source, workspace)

            self.assertEqual(receptor.read_text(encoding="utf-8"), original)

    def test_ligand_style_pdbqt_is_rejected_as_receptor(self):
        with tempfile.TemporaryDirectory() as temp_name:
            path = Path(temp_name) / "wrong.pdbqt"
            path.write_text(
                "ROOT\n"
                "ATOM      1  C   LIG A   1       0.000   0.000   0.000  0.00  0.00     0.000 C\n"
                "ENDROOT\nTORSDOF 0\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "ligand torsion tags"):
                validate_receptor_pdbqt(path)


if __name__ == "__main__":
    unittest.main()
