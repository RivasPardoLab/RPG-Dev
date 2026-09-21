import tempfile
import unittest
from pathlib import Path

from stage1 import generate_peptide_library


class Stage1GenerationTests(unittest.TestCase):
    def test_generates_every_combination_in_original_rpg_order(self):
        peptide_options = {0: ["A", "R"], 1: ["G", "L"]}
        with tempfile.TemporaryDirectory() as temp_name:
            destination = Path(temp_name) / "peptides.txt"
            count = generate_peptide_library(peptide_options, destination)
            self.assertEqual(count, 4)
            self.assertEqual(destination.read_text(encoding="utf-8"), "AG\nRL\nAL\nRG\n")

    def test_writes_all_three_position_combinations(self):
        peptide_options = {0: ["A", "R"], 1: ["G"], 2: ["S", "T"]}
        with tempfile.TemporaryDirectory() as temp_name:
            destination = Path(temp_name) / "peptides.txt"
            count = generate_peptide_library(peptide_options, destination)
            peptides = destination.read_text(encoding="utf-8").splitlines()
            self.assertEqual(count, 4)
            self.assertCountEqual(peptides, ["AGS", "AGT", "RGS", "RGT"])

    def test_rejects_an_empty_definition(self):
        with tempfile.TemporaryDirectory() as temp_name:
            with self.assertRaisesRegex(ValueError, "At least one peptide position"):
                generate_peptide_library({}, Path(temp_name) / "peptides.txt")

    def test_rejects_an_empty_position(self):
        with tempfile.TemporaryDirectory() as temp_name:
            with self.assertRaisesRegex(ValueError, "Every peptide position"):
                generate_peptide_library({0: ["A"], 1: []}, Path(temp_name) / "peptides.txt")


if __name__ == "__main__":
    unittest.main()
