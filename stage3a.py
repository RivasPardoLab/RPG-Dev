"""RPG Stage 3A: Open Babel conversion of peptide PDB files to PDBQT."""

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Callable, Optional, Sequence

from openbabel import openbabel as ob


def select_numbered_pdb_files(
    pdb_directory: Path,
    requested_count: int,
) -> list[Path]:
    """Return RPG's consecutive numbered inputs, stopping at the first gap."""
    if requested_count <= 0:
        raise ValueError("The number of PDB files must be greater than zero")

    pdb_directory = Path(pdb_directory)
    selected = []
    for index in range(1, requested_count + 1):
        source = pdb_directory / f"{index}.pdb"
        if not source.is_file():
            break
        selected.append(source)

    if not selected:
        raise FileNotFoundError(
            f"No numbered PDB files were found in {pdb_directory}"
        )
    return selected


def _validate_pdbqt(destination: Path) -> None:
    text = destination.read_text(encoding="utf-8")
    atom_lines = [
        line for line in text.splitlines() if line.startswith(("ATOM  ", "HETATM"))
    ]
    if not atom_lines or "ROOT" not in text or "TORSDOF" not in text:
        raise ValueError(f"Open Babel produced an invalid PDBQT file: {destination.name}")

    try:
        for line in atom_lines:
            float(line.split()[-2])
    except (IndexError, ValueError) as error:
        raise ValueError(
            f"Open Babel did not write valid PDBQT charge fields: {destination.name}"
        ) from error


def convert_pdb_to_pdbqt(source: Path, destination: Path) -> None:
    """Apply RPG's original Open Babel operation to one peptide structure."""
    conversion = ob.OBConversion()
    if not conversion.SetInAndOutFormats("pdb", "pdbqt"):
        raise RuntimeError("Open Babel could not load the PDB/PDBQT formats")

    molecule = ob.OBMol()
    if not conversion.ReadFile(molecule, str(source)):
        raise ValueError(f"Open Babel could not read {source.name}")
    if not molecule.AddHydrogens():
        raise ValueError(f"Open Babel could not add hydrogens to {source.name}")
    if not conversion.WriteFile(molecule, str(destination)):
        raise ValueError(f"Open Babel could not write {destination.name}")
    conversion.CloseOutFile()
    _validate_pdbqt(destination)


def convert_numbered_pdbs(
    pdb_files: Sequence[Path],
    output_directory: Path,
    progress: Optional[Callable[[int], None]] = None,
) -> list[Path]:
    """Convert and publish numbered ligands only after every conversion succeeds."""
    if not pdb_files:
        raise ValueError("No PDB files were selected for conversion")

    output_directory = Path(output_directory)
    output_directory.parent.mkdir(parents=True, exist_ok=True)
    existing = sorted(output_directory.glob("*.pdbqt")) if output_directory.exists() else []
    if existing:
        raise FileExistsError(
            "The Ligands folder already contains PDBQT files. "
            "Move or remove them before running Stage 3A again."
        )

    with TemporaryDirectory(
        prefix=".rpg-stage3a-", dir=output_directory.parent
    ) as temp_name:
        temp_directory = Path(temp_name)
        temporary_files = []
        for index, source in enumerate(pdb_files, start=1):
            temporary_file = temp_directory / f"{index}.pdbqt"
            convert_pdb_to_pdbqt(Path(source), temporary_file)
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


def run_stage3a(
    workspace: Path,
    requested_count: int,
    progress: Optional[Callable[[int], None]] = None,
) -> list[Path]:
    """Run the PDB-to-PDBQT part of RPG Stage 3 in ``workspace``."""
    workspace = Path(workspace)
    selected = select_numbered_pdb_files(
        workspace / "Chimera-Peptides",
        requested_count,
    )
    return convert_numbered_pdbs(
        selected,
        workspace / "Ligands",
        progress=progress,
    )
