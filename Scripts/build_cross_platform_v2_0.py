#!/usr/bin/env python3
"""Build an autonomous RPG 2.0 package on Windows or Linux x86-64."""

from __future__ import annotations

import argparse
import hashlib
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path


VERSION = "2.0.0"


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--vina-binary",
        required=True,
        type=Path,
        help="Official AutoDock Vina 1.2.7 executable for this operating system",
    )
    return parser.parse_args()


def target_platform() -> tuple[str, str]:
    system = platform.system()
    machine = platform.machine().lower()
    if machine not in {"amd64", "x86_64"}:
        raise SystemExit(f"RPG 2.0 requires x86-64; detected {platform.machine()}")
    if system == "Windows":
        return "Windows", "RPG-Windows-v2.0-x86_64"
    if system == "Linux":
        return "Linux", "RPG-Linux-v2.0-x86_64"
    raise SystemExit("This builder supports only Windows and Linux x86-64")


def add_data(source: Path, destination: str) -> str:
    return f"{source}{os.pathsep}{destination}"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def make_zip(source: Path, destination: Path) -> None:
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                archive.write(path, Path(source.name) / path.relative_to(source))


def main() -> int:
    arguments = parse_arguments()
    os_label, package_name = target_platform()
    project = Path(__file__).resolve().parents[1]
    vina_binary = arguments.vina_binary.expanduser().resolve()
    if not vina_binary.is_file():
        raise SystemExit(f"Vina executable was not found: {vina_binary}")

    openbabel_plugin_dir = None
    openbabel_data_dir = None
    openbabel_version = None
    if os_label == "Linux":
        import openbabel

        openbabel_root = Path(openbabel.__file__).resolve().parent
        openbabel_version = openbabel.__version__
        plugin_marker = next(openbabel_root.rglob("formats.so"), None)
        data_marker = next(openbabel_root.rglob("atomtyp.txt"), None)
        if plugin_marker is None:
            raise SystemExit(f"Open Babel plugins were not found below {openbabel_root}")
        if data_marker is None:
            raise SystemExit(f"Open Babel data files were not found below {openbabel_root}")
        openbabel_plugin_dir = plugin_marker.parent
        openbabel_data_dir = data_marker.parent

    build_root = project / f"build-v2.0-{os_label.lower()}-x86_64"
    pyinstaller_dist = build_root / "dist"
    release_dir = project / "dist" / f"RPG-Peptides-{VERSION}" / f"{os_label}-x86_64"
    package_dir = release_dir / package_name
    release_dir.mkdir(parents=True, exist_ok=True)
    build_root.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        "RPG-2.0",
        "--collect-all",
        "openbabel",
        "--collect-all",
        "rdkit",
        "--collect-data",
        "meeko",
        "--copy-metadata",
        "openbabel-wheel",
        "--copy-metadata",
        "meeko",
        "--copy-metadata",
        "rdkit",
        "--exclude-module",
        "IPython",
        "--exclude-module",
        "matplotlib",
        "--exclude-module",
        "pandas",
        "--exclude-module",
        "prody",
        "--exclude-module",
        "PySide6",
        "--exclude-module",
        "PyQt6",
        "--add-binary",
        add_data(vina_binary, "."),
        "--add-data",
        add_data(project / "eight-bit-dragon.otf", "."),
        "--add-data",
        add_data(project / "MainWin" / "icons" / "Lab2.png", "MainWin/icons"),
        "--distpath",
        str(pyinstaller_dist),
        "--workpath",
        str(build_root / "pyinstaller"),
        "--specpath",
        str(build_root),
    ]
    if os_label == "Windows":
        command.extend(("--icon", str(project / "icon.ico")))
    else:
        command.extend(
            (
                "--add-binary",
                add_data(
                    openbabel_plugin_dir,
                    f"openbabel/lib/openbabel/{openbabel_version}",
                ),
                "--add-data",
                add_data(
                    openbabel_data_dir,
                    f"openbabel/share/openbabel/{openbabel_version}",
                ),
            )
        )
    command.append(str(project / "main.py"))
    subprocess.run(command, cwd=project, check=True)

    built_dir = pyinstaller_dist / "RPG-2.0"
    if package_dir.exists():
        shutil.rmtree(package_dir)
    shutil.move(str(built_dir), str(package_dir))
    shutil.copy2(project / "LICENSE", package_dir / "LICENSE.txt")
    shutil.copy2(
        project / "README-RPG-v2.0-release.md",
        package_dir / "README.txt",
    )

    artifacts = []
    if os_label == "Windows":
        archive = release_dir / f"{package_name}.zip"
        archive.unlink(missing_ok=True)
        make_zip(package_dir, archive)
    else:
        archive = release_dir / f"{package_name}.tar.gz"
        archive.unlink(missing_ok=True)
        with tarfile.open(archive, "w:gz") as stream:
            stream.add(package_dir, arcname=package_dir.name)
    artifacts.append(archive)

    checksum_file = release_dir / "SHA256SUMS.txt"
    checksum_file.write_text(
        "".join(f"{sha256(path)}  {path.name}\n" for path in artifacts),
        encoding="utf-8",
    )
    print(f"Built package: {package_dir}")
    print(f"Built archive: {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
