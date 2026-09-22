"""RPG Stage 4: rank docked peptides and analyze sequence enrichment."""

from __future__ import annotations

import csv
import math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Optional, Sequence


@dataclass(frozen=True)
class RankedPeptide:
    peptide_id: int
    sequence: str
    affinity: float
    ligand_file: str
    result_file: str


@dataclass(frozen=True)
class PositionEnrichment:
    position: int
    amino_acid: str
    count: int
    frequency_percent: float


def _read_sequences(path: Path) -> list[str]:
    if not path.is_file():
        raise FileNotFoundError(f"The Stage 2 selection file was not found: {path}")
    sequences = [
        line.strip().upper()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not sequences:
        raise ValueError("random.txt contains no peptide sequences")
    lengths = {len(sequence) for sequence in sequences}
    if len(lengths) != 1:
        raise ValueError("The peptide sequences in random.txt have inconsistent lengths")
    return sequences


def load_ranked_results(workspace: Path) -> list[RankedPeptide]:
    """Load and rank Vina results, preserving RPG's numeric sequence mapping."""
    workspace = Path(workspace).expanduser().resolve()
    sequences = _read_sequences(workspace / "random.txt")
    results_directory = workspace / "VinaResults"
    affinity_path = results_directory / "affinities.csv"
    if not affinity_path.is_file():
        raise FileNotFoundError(f"The Vina affinity report was not found: {affinity_path}")

    required_columns = {"ligand", "result", "best_affinity_kcal_mol"}
    records: list[RankedPeptide] = []
    peptide_ids = set()
    with affinity_path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None or not required_columns.issubset(reader.fieldnames):
            raise ValueError("affinities.csv does not contain the expected RPG columns")
        for row_number, row in enumerate(reader, start=2):
            ligand_name = row["ligand"].strip()
            ligand_stem = Path(ligand_name).stem
            if not ligand_stem.isdigit():
                raise ValueError(
                    f"Cannot map ligand {ligand_name!r} at row {row_number} to random.txt"
                )
            peptide_id = int(ligand_stem)
            if peptide_id < 1 or peptide_id > len(sequences):
                raise ValueError(
                    f"Ligand {ligand_name!r} references peptide {peptide_id}, "
                    f"but random.txt contains {len(sequences)} sequences"
                )
            if peptide_id in peptide_ids:
                raise ValueError(f"Duplicate peptide result in affinities.csv: {peptide_id}")
            try:
                affinity = float(row["best_affinity_kcal_mol"])
            except (TypeError, ValueError):
                raise ValueError(
                    f"Invalid affinity at row {row_number}: "
                    f"{row['best_affinity_kcal_mol']!r}"
                ) from None
            if not math.isfinite(affinity):
                raise ValueError(f"Non-finite affinity at row {row_number}")

            result_name = row["result"].strip()
            if not result_name:
                raise ValueError(f"Missing result filename at row {row_number}")
            if not (results_directory / result_name).is_file():
                raise FileNotFoundError(
                    f"The docking result listed in affinities.csv was not found: "
                    f"{result_name}"
                )

            peptide_ids.add(peptide_id)
            records.append(
                RankedPeptide(
                    peptide_id=peptide_id,
                    sequence=sequences[peptide_id - 1],
                    affinity=affinity,
                    ligand_file=ligand_name,
                    result_file=result_name,
                )
            )

    if not records:
        raise ValueError("affinities.csv contains no docking results")
    return sorted(records, key=lambda record: (record.affinity, record.peptide_id))


def filter_ranked_results(
    results: Sequence[RankedPeptide],
    maximum_affinity: Optional[float] = None,
    top_n: Optional[int] = None,
) -> list[RankedPeptide]:
    if maximum_affinity is not None and not math.isfinite(maximum_affinity):
        raise ValueError("The affinity cutoff must be a finite number")
    if top_n is not None and top_n <= 0:
        raise ValueError("top_n must be greater than zero when supplied")

    ranked = sorted(results, key=lambda record: (record.affinity, record.peptide_id))
    if maximum_affinity is not None:
        ranked = [record for record in ranked if record.affinity <= maximum_affinity]
    if top_n is not None:
        ranked = ranked[:top_n]
    return ranked


def analyze_position_enrichment(
    results: Sequence[RankedPeptide], minimum_frequency_percent: float
) -> list[PositionEnrichment]:
    if not results:
        raise ValueError("No ranked peptides are available for sequence analysis")
    if not 0 <= minimum_frequency_percent <= 100:
        raise ValueError("The minimum amino-acid frequency must be between 0 and 100")
    lengths = {len(result.sequence) for result in results}
    if len(lengths) != 1:
        raise ValueError("Selected peptide sequences have inconsistent lengths")

    peptide_count = len(results)
    sequence_length = lengths.pop()
    enriched = []
    for index in range(sequence_length):
        counts = Counter(result.sequence[index] for result in results)
        for amino_acid, count in sorted(
            counts.items(), key=lambda item: (-item[1], item[0])
        ):
            frequency = count * 100.0 / peptide_count
            if frequency >= minimum_frequency_percent:
                enriched.append(
                    PositionEnrichment(index + 1, amino_acid, count, frequency)
                )
    return enriched


def _write_csv_atomically(
    destination: Path, fieldnames: Sequence[str], rows: Sequence[dict]
) -> Path:
    destination = Path(destination).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".rpg-stage4-", dir=destination.parent) as name:
        temporary = Path(name) / destination.name
        with temporary.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        temporary.replace(destination)
    return destination


def write_best_peptides(path: Path, results: Sequence[RankedPeptide]) -> Path:
    rows = [
        {
            "Rank": rank,
            "Peptide ID": result.peptide_id,
            "Sequence": result.sequence,
            "Best affinity (kcal/mol)": f"{result.affinity:g}",
            "Result file": result.result_file,
        }
        for rank, result in enumerate(results, start=1)
    ]
    return _write_csv_atomically(
        path,
        ("Rank", "Peptide ID", "Sequence", "Best affinity (kcal/mol)", "Result file"),
        rows,
    )


def write_position_enrichment(
    path: Path, rows: Sequence[PositionEnrichment]
) -> Path:
    serialized = [
        {
            "Peptide position": row.position,
            "Amino acid": row.amino_acid,
            "Count": row.count,
            "Frequency (%)": f"{row.frequency_percent:.2f}",
        }
        for row in rows
    ]
    return _write_csv_atomically(
        path,
        ("Peptide position", "Amino acid", "Count", "Frequency (%)"),
        serialized,
    )
