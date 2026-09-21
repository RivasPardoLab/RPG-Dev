import random
import tempfile
import unittest
from pathlib import Path

from Bio.PDB import PDBParser

from stage2 import run_stage2, select_random_peptides


class Stage2Tests(unittest.TestCase):
    def test_random_selection_matches_rpg_logic(self):
        with tempfile.TemporaryDirectory() as temp_name:
            library = Path(temp_name) / "peptides.txt"
            library.write_text("AA\nRR\nNN\nDD\n", encoding="utf-8")
            selected = select_random_peptides(library, 3, rng=random.Random(7))
            self.assertEqual(selected, ["NN", "AA", "RR"])

    def test_request_larger_than_library_selects_every_peptide(self):
        with tempfile.TemporaryDirectory() as temp_name:
            library = Path(temp_name) / "peptides.txt"
            library.write_text("AA\nRR\nNN\n", encoding="utf-8")
            selected = select_random_peptides(library, 20, rng=random.Random(2))
            self.assertCountEqual(selected, ["AA", "RR", "NN"])

    def test_stage2_writes_random_file_and_numbered_pdbs(self):
        with tempfile.TemporaryDirectory() as temp_name:
            workspace = Path(temp_name)
            library = workspace / "peptides.txt"
            library.write_text("AW\nGS\n", encoding="utf-8")

            generated = run_stage2(
                library,
                2,
                workspace,
                rng=random.Random(1),
            )

            selected = (workspace / "random.txt").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(generated), 2)
            self.assertEqual([path.name for path in generated], ["1.pdb", "2.pdb"])
            self.assertEqual(len(selected), 2)

            parser = PDBParser(QUIET=True)
            residue_names = {
                "A": "ALA",
                "G": "GLY",
                "S": "SER",
                "W": "TRP",
            }
            for index, sequence in enumerate(selected, start=1):
                structure = parser.get_structure(str(index), workspace / "Chimera-Peptides" / f"{index}.pdb")
                residues = list(structure.get_residues())
                self.assertEqual(len(residues), len(sequence))
                self.assertEqual(
                    [residue.resname for residue in residues],
                    [residue_names[code] for code in sequence],
                )
                self.assertIn("OXT", residues[-1])


if __name__ == "__main__":
    unittest.main()
