"""RPG Stage 2: random peptide selection and PDB generation."""

import random
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Callable, Optional, Sequence

import PeptideBuilder
from Bio.PDB import PDBIO


VALID_AMINO_ACIDS = frozenset("ARNDCQEGHILKMFPSTWYV")


def select_random_peptides(
    library_file: Path,
    requested_count: int,
    rng=None,
) -> list[str]:
    """Select up to ``requested_count`` sequences with RPG's random-sample logic."""
    if requested_count <= 0:
        raise ValueError("The number of peptides must be greater than zero")

    library_file = Path(library_file)
    sequences = [
        line.strip().upper()
        for line in library_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not sequences:
        raise ValueError("The peptide library is empty")

    for line_number, sequence in enumerate(sequences, start=1):
        invalid = set(sequence) - VALID_AMINO_ACIDS
        if invalid:
            symbols = ", ".join(sorted(invalid))
            raise ValueError(
                f"Unsupported amino acid code(s) at line {line_number}: {symbols}"
            )

    sample_size = min(requested_count, len(sequences))
    random_source = rng if rng is not None else random
    return random_source.sample(sequences, sample_size)


def write_random_selection(sequences: Sequence[str], destination: Path) -> None:
    """Write ``random.txt`` in the same order used to number the PDB files."""
    destination = Path(destination)
    destination.write_text(
        "".join(f"{sequence}\n" for sequence in sequences),
        encoding="utf-8",
    )


def build_peptide_pdb(sequence: str, destination: Path) -> None:
    """Build one extended peptide and include RPG's terminal OXT atom."""
    structure = PeptideBuilder.make_extended_structure(sequence)
    PeptideBuilder.add_terminal_OXT(structure)
    writer = PDBIO()
    writer.set_structure(structure)
    writer.save(str(destination))


def convert_peptides_to_pdb(
    sequences: Sequence[str],
    output_directory: Path,
    progress: Optional[Callable[[int], None]] = None,
) -> list[Path]:
    """Create numbered PDB files, publishing them only after all builds succeed."""
    if not sequences:
        raise ValueError("No peptides were selected for conversion")

    output_directory = Path(output_directory)
    output_directory.parent.mkdir(parents=True, exist_ok=True)
    existing = sorted(output_directory.glob("*.pdb")) if output_directory.exists() else []
    if existing:
        raise FileExistsError(
            "The Chimera-Peptides folder already contains PDB files. "
            "Move or remove them before running Stage 2 again."
        )

    with TemporaryDirectory(
        prefix=".rpg-stage2-", dir=output_directory.parent
    ) as temp_name:
        temp_directory = Path(temp_name)
        temporary_files = []
        for index, sequence in enumerate(sequences, start=1):
            temporary_file = temp_directory / f"{index}.pdb"
            build_peptide_pdb(sequence, temporary_file)
            temporary_files.append(temporary_file)
            if progress is not None:
                progress(index)

        output_directory.mkdir(parents=True, exist_ok=True)
        published = []
        for temporary_file in temporary_files:
            destination = output_directory / temporary_file.name
            temporary_file.replace(destination)
            published.append(destination)

    return published


def run_stage2(
    library_file: Path,
    requested_count: int,
    workspace: Path,
    progress: Optional[Callable[[int], None]] = None,
    rng=None,
) -> list[Path]:
    """Run the complete RPG Stage 2 workflow in ``workspace``."""
    workspace = Path(workspace)
    selected = select_random_peptides(library_file, requested_count, rng=rng)
    write_random_selection(selected, workspace / "random.txt")
    return convert_peptides_to_pdb(
        selected,
        workspace / "Chimera-Peptides",
        progress=progress,
    )
