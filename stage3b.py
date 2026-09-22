"""RPG Stage 3B: configure and run AutoDock Vina on peptide ligands."""

from __future__ import annotations

import csv
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Callable, Optional, Sequence


@dataclass(frozen=True)
class VinaConfig:
    """The Vina parameters exposed by the published RPG interface."""

    center_x: float
    center_y: float
    center_z: float
    size_x: float
    size_y: float
    size_z: float
    exhaustiveness: int = 10
    num_modes: int = 10
    energy_range: float = 4.0

    def validate(self) -> None:
        coordinates = (
            self.center_x,
            self.center_y,
            self.center_z,
            self.size_x,
            self.size_y,
            self.size_z,
        )
        if not all(math.isfinite(value) for value in coordinates):
            raise ValueError("Vina box values must be finite numbers")
        if min(self.size_x, self.size_y, self.size_z) <= 0:
            raise ValueError("Vina box dimensions must be greater than zero")
        if self.exhaustiveness <= 0:
            raise ValueError("Vina exhaustiveness must be greater than zero")
        if self.num_modes <= 0:
            raise ValueError("Vina num_modes must be greater than zero")
        if self.energy_range < 0:
            raise ValueError("Vina energy_range cannot be negative")

    @property
    def center(self) -> list[float]:
        return [self.center_x, self.center_y, self.center_z]

    @property
    def size(self) -> list[float]:
        return [self.size_x, self.size_y, self.size_z]

    def to_text(self) -> str:
        self.validate()
        return (
            f"center_x = {self.center_x:g}\n"
            f"center_y = {self.center_y:g}\n"
            f"center_z = {self.center_z:g}\n"
            f"size_x = {self.size_x:g}\n"
            f"size_y = {self.size_y:g}\n"
            f"size_z = {self.size_z:g}\n"
            f"num_modes = {self.num_modes}\n"
            f"energy_range = {self.energy_range:g}\n"
            f"exhaustiveness = {self.exhaustiveness}\n"
        )


def _atom_lines(path: Path) -> list[str]:
    return [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.startswith(("ATOM  ", "HETATM"))
    ]


def validate_receptor_pdbqt(path: Path) -> Path:
    path = Path(path).expanduser().resolve()
    if path.suffix.lower() != ".pdbqt" or not path.is_file():
        raise FileNotFoundError(f"The receptor PDBQT file was not found: {path}")
    if not _atom_lines(path):
        raise ValueError("The receptor PDBQT file contains no atoms")
    ligand_tags = ("ROOT", "BRANCH", "ENDBRANCH", "TORSDOF")
    found_tags = {
        line.split()[0]
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.startswith(ligand_tags)
    }
    if found_tags:
        raise ValueError(
            "The selected receptor contains ligand torsion tags "
            f"({', '.join(sorted(found_tags))}). Select a rigid receptor PDBQT "
            "prepared with Meeko, not a ligand converted by Open Babel."
        )
    return path


def validate_ligand_pdbqts(paths: Sequence[Path]) -> list[Path]:
    if not paths:
        raise ValueError("No peptide PDBQT ligands were selected")

    validated = []
    names = set()
    for candidate in paths:
        path = Path(candidate).expanduser().resolve()
        if path.suffix.lower() != ".pdbqt" or not path.is_file():
            raise FileNotFoundError(f"The ligand PDBQT file was not found: {path}")
        text = path.read_text(encoding="utf-8")
        if not _atom_lines(path) or "ROOT" not in text or "TORSDOF" not in text:
            raise ValueError(f"Invalid ligand PDBQT file: {path.name}")
        if path.stem in names:
            raise ValueError(f"Duplicate ligand name: {path.stem}")
        names.add(path.stem)
        validated.append(path)

    def natural_key(path: Path):
        return (0, int(path.stem)) if path.stem.isdigit() else (1, path.stem.lower())

    return sorted(validated, key=natural_key)


def write_vina_config(path: Path, config: VinaConfig) -> Path:
    """Write RPG's Vina configuration atomically."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(config.to_text(), encoding="utf-8")
    temporary.replace(path)
    return path


def _validate_vina_output(path: Path) -> float:
    text = path.read_text(encoding="utf-8")
    if "REMARK VINA RESULT:" not in text or not _atom_lines(path):
        raise ValueError(f"Vina produced an invalid result: {path.name}")
    for line in text.splitlines():
        if line.startswith("REMARK VINA RESULT:"):
            try:
                return float(line.split()[3])
            except (IndexError, ValueError) as error:
                raise ValueError(
                    f"Vina produced an invalid affinity value: {path.name}"
                ) from error
    raise ValueError(f"Vina produced no affinity value: {path.name}")


def dock_ligand_with_vina(
    receptor: Path,
    ligand: Path,
    destination: Path,
    config: VinaConfig,
) -> dict:
    """Dock one ligand with the official AutoDock Vina Python bindings."""
    try:
        import vina
        from vina import Vina
    except ImportError as error:
        raise RuntimeError(
            "AutoDock Vina is not installed. Recreate the macOS environment "
            "from environment-macos.yml."
        ) from error

    engine = Vina(sf_name="vina", cpu=0, seed=0, verbosity=0)
    seed = engine.info()["seed"]
    engine.set_receptor(str(receptor))
    engine.set_ligand_from_file(str(ligand))
    engine.compute_vina_maps(center=config.center, box_size=config.size)
    engine.dock(
        exhaustiveness=config.exhaustiveness,
        n_poses=config.num_modes,
    )
    engine.write_poses(
        str(destination),
        n_poses=config.num_modes,
        energy_range=config.energy_range,
        overwrite=True,
    )
    return {"engine": "AutoDock Vina", "version": vina.__version__, "seed": seed}


def run_vina_docking(
    receptor: Path,
    ligands: Sequence[Path],
    workspace: Path,
    config: VinaConfig,
    progress: Optional[Callable[[int], None]] = None,
    dock_one: Callable[[Path, Path, Path, VinaConfig], dict] = dock_ligand_with_vina,
) -> list[Path]:
    """Dock all selected ligands and publish results only after full success."""
    receptor = validate_receptor_pdbqt(receptor)
    ligands = validate_ligand_pdbqts(ligands)
    config.validate()
    workspace = Path(workspace).expanduser().resolve()
    results_directory = workspace / "VinaResults"

    if results_directory.exists() and any(results_directory.iterdir()):
        raise FileExistsError(
            "The VinaResults folder is not empty. Move or remove its contents "
            "before running docking again."
        )

    workspace.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".rpg-stage3b-", dir=workspace) as temp_name:
        temporary = Path(temp_name)
        records = []
        generated = []

        for index, ligand in enumerate(ligands, start=1):
            output = temporary / f"{ligand.stem}-out.pdbqt"
            metadata = dock_one(receptor, ligand, output, config)
            affinity = _validate_vina_output(output)
            records.append(
                {
                    "ligand": ligand.name,
                    "result": output.name,
                    "best_affinity_kcal_mol": affinity,
                    **metadata,
                }
            )
            generated.append(output)
            if progress is not None:
                progress(index)

        manifest = {
            "receptor": str(receptor),
            "configuration": asdict(config),
            "results": records,
        }
        (temporary / "docking-manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n",
            encoding="utf-8",
        )
        with (temporary / "affinities.csv").open(
            "w", encoding="utf-8", newline=""
        ) as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=("ligand", "result", "best_affinity_kcal_mol"),
                extrasaction="ignore",
            )
            writer.writeheader()
            writer.writerows(records)

        results_directory.mkdir(parents=True, exist_ok=True)
        published = []
        for output in generated:
            destination = results_directory / output.name
            output.replace(destination)
            published.append(destination)
        for report_name in ("docking-manifest.json", "affinities.csv"):
            (temporary / report_name).replace(results_directory / report_name)

    return published
