import csv
import json
import tempfile
import unittest
from pathlib import Path

from stage4 import (
    analyze_position_enrichment,
    filter_ranked_results,
    load_ranked_results,
    resolve_workspace_receptor,
    write_best_peptides,
    write_position_enrichment,
)


def _make_workspace(root: Path) -> Path:
    root.joinpath("random.txt").write_text("AC\nAD\nEC\n", encoding="utf-8")
    results = root / "VinaResults"
    results.mkdir()
    for name in ("1-out.pdbqt", "2-out.pdbqt", "3-out.pdbqt"):
        results.joinpath(name).write_text("MODEL 1\nENDMDL\n", encoding="utf-8")
    with results.joinpath("affinities.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=("ligand", "result", "best_affinity_kcal_mol"),
        )
        writer.writeheader()
        writer.writerows(
            (
                {
                    "ligand": "2.pdbqt",
                    "result": "2-out.pdbqt",
                    "best_affinity_kcal_mol": "-6.1",
                },
                {
                    "ligand": "1.pdbqt",
                    "result": "1-out.pdbqt",
                    "best_affinity_kcal_mol": "-7.5",
                },
                {
                    "ligand": "3.pdbqt",
                    "result": "3-out.pdbqt",
                    "best_affinity_kcal_mol": "-5.0",
                },
            )
        )
    return root


class Stage4Tests(unittest.TestCase):
    def test_results_are_mapped_to_random_sequences_and_ranked(self):
        with tempfile.TemporaryDirectory() as temp_name:
            results = load_ranked_results(_make_workspace(Path(temp_name)))

            self.assertEqual([row.peptide_id for row in results], [1, 2, 3])
            self.assertEqual([row.sequence for row in results], ["AC", "AD", "EC"])
            self.assertEqual([row.affinity for row in results], [-7.5, -6.1, -5.0])

    def test_affinity_and_top_n_filters_are_combined(self):
        with tempfile.TemporaryDirectory() as temp_name:
            results = load_ranked_results(_make_workspace(Path(temp_name)))

            selected = filter_ranked_results(
                results, maximum_affinity=-5.5, top_n=1
            )

            self.assertEqual([row.peptide_id for row in selected], [1])

    def test_best_peptide_report_is_written_in_rank_order(self):
        with tempfile.TemporaryDirectory() as temp_name:
            workspace = _make_workspace(Path(temp_name))
            selected = filter_ranked_results(
                load_ranked_results(workspace), maximum_affinity=-5.5
            )

            report = write_best_peptides(workspace / "Best-Peptides.csv", selected)

            with report.open(encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual([row["Sequence"] for row in rows], ["AC", "AD"])
            self.assertEqual(rows[0]["Rank"], "1")
            self.assertEqual(rows[0]["Best affinity (kcal/mol)"], "-7.5")

    def test_position_enrichment_uses_the_filtered_sequences(self):
        with tempfile.TemporaryDirectory() as temp_name:
            workspace = _make_workspace(Path(temp_name))
            results = load_ranked_results(workspace)

            enriched = analyze_position_enrichment(results, 60)

            self.assertEqual(
                [(row.position, row.amino_acid, row.count) for row in enriched],
                [(1, "A", 2), (2, "C", 2)],
            )
            report = write_position_enrichment(
                workspace / "Best-AminoAcids.csv", enriched
            )
            with report.open(encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(rows[0]["Frequency (%)"], "66.67")

    def test_missing_pose_reported_by_affinities_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_name:
            workspace = _make_workspace(Path(temp_name))
            (workspace / "VinaResults" / "2-out.pdbqt").unlink()

            with self.assertRaises(FileNotFoundError):
                load_ranked_results(workspace)

    def test_receptor_is_resolved_from_manifest_or_portable_workspace_copy(self):
        with tempfile.TemporaryDirectory() as temp_name:
            workspace = _make_workspace(Path(temp_name))
            receptor_directory = workspace / "Receptor"
            receptor_directory.mkdir()
            receptor = receptor_directory / "protein.pdbqt"
            receptor.write_text("ATOM\n", encoding="utf-8")
            manifest = workspace / "VinaResults" / "docking-manifest.json"
            manifest.write_text(
                json.dumps({"receptor": "/missing/location/protein.pdbqt"}),
                encoding="utf-8",
            )

            resolved = resolve_workspace_receptor(workspace)

            self.assertEqual(resolved, receptor.resolve())


if __name__ == "__main__":
    unittest.main()
