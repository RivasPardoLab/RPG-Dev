"""Entry point for the RPG 2.0 peptide-library and Vina workflow."""

from __future__ import annotations

import json
import os
import platform
import sys
import tempfile
from pathlib import Path


def configure_packaged_openbabel() -> None:
    """Point frozen Linux builds at the Open Babel plugin and data folders."""
    if not getattr(sys, "frozen", False):
        return

    application_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    locations = {
        "BABEL_LIBDIR": (
            application_root / "openbabel" / "lib" / "openbabel" / "3.1.0",
            application_root / "lib" / "openbabel" / "3.1.0",
        ),
        "BABEL_DATADIR": (
            application_root / "openbabel" / "share" / "openbabel" / "3.1.0",
            application_root / "share" / "openbabel" / "3.1.0",
        ),
    }
    markers = {
        "BABEL_LIBDIR": "pdbqtformat.so",
        "BABEL_DATADIR": "atomtyp.txt",
    }
    for variable, candidates in locations.items():
        if variable in os.environ:
            continue
        for candidate in candidates:
            if candidate.is_dir():
                os.environ[variable] = str(candidate)
                break
        else:
            # PyInstaller's layout varies between platforms and versions.
            # Locate Open Babel by its canonical plugin/data marker instead of
            # assuming a fixed wheel directory layout.
            marker = next(application_root.rglob(markers[variable]), None)
            if marker is not None:
                os.environ[variable] = str(marker.parent)


def packaged_self_test(report_path: Path) -> int:
    """Exercise the scientific modules bundled into a frozen application."""
    report = {
        "application": "RPG 2.0",
        "version": "2.0.0",
        "platform": platform.platform(),
        "architecture": platform.machine(),
    }
    try:
        import PeptideBuilder
        import meeko
        import openbabel
        import rdkit
        from PyQt5.QtCore import QT_VERSION_STR

        from stage2 import build_peptide_pdb
        from stage3a import convert_pdb_to_pdbqt
        from stage3b import VinaConfig, dock_ligand_with_vina, vina_backend_info

        vina_info = vina_backend_info()

        report["components"] = {
            "Open Babel": openbabel.__version__,
            "Meeko": meeko.__version__,
            "RDKit": rdkit.__version__,
            "Vina": f"{vina_info['version']} ({vina_info['interface']})",
            "Qt": QT_VERSION_STR,
            "PeptideBuilder": getattr(PeptideBuilder, "__version__", "installed"),
        }
        with tempfile.TemporaryDirectory(prefix="rpg-self-test-") as temp_name:
            peptide = Path(temp_name) / "peptide.pdb"
            ligand = Path(temp_name) / "peptide.pdbqt"
            build_peptide_pdb("AG", peptide)
            convert_pdb_to_pdbqt(peptide, ligand)
            ligand_text = ligand.read_text(encoding="utf-8")
            report["pdbqt_atoms"] = sum(
                line.startswith(("ATOM  ", "HETATM"))
                for line in ligand_text.splitlines()
            )
            receptor = Path(temp_name) / "receptor.pdbqt"
            receptor.write_text(
                "\n".join(
                    line
                    for line in ligand_text.splitlines()
                    if line.startswith(("ATOM  ", "HETATM"))
                )
                + "\n",
                encoding="utf-8",
            )
            pose = Path(temp_name) / "pose.pdbqt"
            docking = dock_ligand_with_vina(
                receptor,
                ligand,
                pose,
                VinaConfig(2, -1, 0, 20, 20, 20, 1, 1, 4),
            )
            report["docking_backend"] = docking
            report["docking_pose_created"] = (
                pose.is_file() and "REMARK VINA RESULT:" in pose.read_text(encoding="utf-8")
            )
            if not report["docking_pose_created"]:
                raise RuntimeError("Vina did not produce a valid test pose")
        report["status"] = "ok"
        exit_code = 0
    except Exception as error:  # pragma: no cover - exercised in frozen packages
        report["status"] = "error"
        report["error"] = f"{type(error).__name__}: {error}"
        exit_code = 1

    report_path = Path(report_path).expanduser().resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return exit_code


def cli_main() -> int:
    configure_packaged_openbabel()
    if "--self-test" in sys.argv:
        index = sys.argv.index("--self-test")
        try:
            destination = Path(sys.argv[index + 1])
        except IndexError:
            destination = Path.cwd() / "rpg-self-test.json"
        return packaged_self_test(destination)

    from stage1_app import main

    return main()


if __name__ == "__main__":
    raise SystemExit(cli_main())
