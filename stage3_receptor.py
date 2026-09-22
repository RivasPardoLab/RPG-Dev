"""Prepare a cleaned PDB macromolecule as a rigid AutoDock Vina receptor."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from stage3b import validate_receptor_pdbqt


def receptor_output_path(workspace: Path, source_pdb: Path) -> Path:
    source_pdb = Path(source_pdb)
    return Path(workspace) / "Receptor" / f"{source_pdb.stem}_receptor.pdbqt"


def receptor_manifest_path(receptor_path: Path) -> Path:
    receptor_path = Path(receptor_path)
    return receptor_path.with_name(f"{receptor_path.stem}-manifest.json")


def _validate_source_pdb(source_pdb: Path) -> tuple[Path, dict]:
    source_pdb = Path(source_pdb).expanduser().resolve()
    if source_pdb.suffix.lower() != ".pdb" or not source_pdb.is_file():
        raise FileNotFoundError(f"The cleaned receptor PDB was not found: {source_pdb}")

    atom_lines = []
    chains = set()
    residues = set()
    for line in source_pdb.read_text(encoding="utf-8").splitlines():
        if line.startswith(("ATOM  ", "HETATM")):
            atom_lines.append(line)
            chains.add(line[21:22].strip() or "(blank)")
            residues.add((line[21:22], line[22:27], line[17:20]))

    if not atom_lines:
        raise ValueError("The selected PDB contains no ATOM or HETATM records")

    return source_pdb, {
        "atoms": len(atom_lines),
        "residues": len(residues),
        "chains": sorted(chains),
    }


def prepare_rigid_receptor(source_pdb: Path, workspace: Path) -> Path:
    """Parameterize a user-cleaned PDB with Meeko and publish a rigid PDBQT."""
    source_pdb, input_summary = _validate_source_pdb(source_pdb)
    workspace = Path(workspace).expanduser().resolve()
    destination = receptor_output_path(workspace, source_pdb)
    manifest_destination = receptor_manifest_path(destination)
    receptor_directory = destination.parent

    if destination.exists():
        raise FileExistsError(
            f"The prepared receptor already exists: {destination}. "
            "Move or rename it before preparing the PDB again."
        )

    try:
        import meeko
        from meeko import (
            MoleculePreparation,
            PDBQTWriterLegacy,
            Polymer,
            PolymerCreationError,
            ResidueChemTemplates,
        )
    except ImportError as error:
        raise RuntimeError(
            "Meeko receptor preparation is unavailable. Recreate the macOS "
            "environment from environment-macos.yml."
        ) from error

    pdb_string = source_pdb.read_text(encoding="utf-8")
    preparation = MoleculePreparation.from_config({"compute_charges": False})
    templates = ResidueChemTemplates.create_from_defaults()
    try:
        polymer = Polymer.from_pdb_string(
            pdb_string,
            templates,
            preparation,
            set_template={},
            residues_to_delete=[],
            ignore_https_cert=False,
            allow_bad_res=False,
        )
    except PolymerCreationError as error:
        raise ValueError(
            "Meeko could not match every receptor residue to a chemical "
            f"template. Review missing atoms, alternate locations, residue "
            f"names, metals, cofactors, and chain breaks. Details:\n{error}"
        ) from error

    rigid_pdbqt, flexible_residues = PDBQTWriterLegacy.write_from_polymer(polymer)
    if flexible_residues:
        raise RuntimeError("Rigid receptor preparation unexpectedly produced flexible residues")

    receptor_directory.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(
        prefix=".rpg-receptor-", dir=receptor_directory.parent
    ) as temp_name:
        temporary_directory = Path(temp_name)
        temporary_receptor = temporary_directory / destination.name
        temporary_receptor.write_text(rigid_pdbqt, encoding="utf-8")
        validate_receptor_pdbqt(temporary_receptor)

        manifest = {
            "source_pdb": str(source_pdb),
            "prepared_receptor": destination.name,
            "preparation": {
                "engine": "Meeko",
                "version": meeko.__version__,
                "mode": "rigid receptor",
                "charges": "Meeko residue-template defaults",
                "bad_residues_deleted": False,
            },
            "input_summary": input_summary,
        }
        temporary_manifest = temporary_directory / manifest_destination.name
        temporary_manifest.write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )

        receptor_directory.mkdir(parents=True, exist_ok=True)
        temporary_receptor.replace(destination)
        temporary_manifest.replace(manifest_destination)

    return destination
