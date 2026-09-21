import tempfile
import unittest
from pathlib import Path

from openbabel import openbabel as ob

from stage2 import build_peptide_pdb
from stage3a import run_stage3a, select_numbered_pdb_files


class Stage3ATests(unittest.TestCase):
    def test_numbered_selection_stops_at_first_missing_file(self):
        with tempfile.TemporaryDirectory() as temp_name:
            directory = Path(temp_name)
            (directory / "1.pdb").touch()
            (directory / "3.pdb").touch()

            selected = select_numbered_pdb_files(directory, 10)

            self.assertEqual([path.name for path in selected], ["1.pdb"])

    def test_stage3a_preserves_numbering_and_generates_valid_pdbqt(self):
        with tempfile.TemporaryDirectory() as temp_name:
            workspace = Path(temp_name)
            pdb_directory = workspace / "Chimera-Peptides"
            pdb_directory.mkdir()
            build_peptide_pdb("AG", pdb_directory / "1.pdb")
            build_peptide_pdb("FY", pdb_directory / "2.pdb")

            generated = run_stage3a(workspace, 2)

            self.assertEqual([path.name for path in generated], ["1.pdbqt", "2.pdbqt"])
            first = generated[0].read_text(encoding="utf-8")
            second = generated[1].read_text(encoding="utf-8")
            self.assertIn("ALA", first)
            self.assertIn("GLY", first)
            self.assertNotIn("PHE", first)
            self.assertIn("PHE", second)
            self.assertIn("TYR", second)

            for path in generated:
                text = path.read_text(encoding="utf-8")
                self.assertIn("ROOT", text)
                self.assertIn("TORSDOF", text)
                self.assertTrue(
                    any(
                        line.split()[-1] == "HD"
                        for line in text.splitlines()
                        if line.startswith("ATOM")
                    )
                )

                reader = ob.OBConversion()
                self.assertTrue(reader.SetInFormat("pdbqt"))
                molecule = ob.OBMol()
                self.assertTrue(reader.ReadFile(molecule, str(path)))
                self.assertGreater(molecule.NumAtoms(), 0)

    def test_existing_ligands_are_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp_name:
            workspace = Path(temp_name)
            pdb_directory = workspace / "Chimera-Peptides"
            ligand_directory = workspace / "Ligands"
            pdb_directory.mkdir()
            ligand_directory.mkdir()
            build_peptide_pdb("AA", pdb_directory / "1.pdb")
            existing = ligand_directory / "1.pdbqt"
            existing.write_text("existing\n", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                run_stage3a(workspace, 1)

            self.assertEqual(existing.read_text(encoding="utf-8"), "existing\n")


if __name__ == "__main__":
    unittest.main()
