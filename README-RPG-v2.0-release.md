# RPG 2.0.0 — archived cross-platform release

RPG 2.0 is the completed baseline of the RivasPardoLab peptide workflow. The
same scientific stages are packaged for macOS Apple Silicon, macOS Intel,
Windows x86-64 and Linux x86-64. Later engines such as smina, Vinardo, Vina
Ensemble and LightDock are intentionally excluded from this archived version.

## Included workflow

1. Combinatorial peptide-library generation.
2. Random peptide selection and PDB generation with PeptideBuilder.
3. Ligand PDBQT conversion with Open Babel.
4. Rigid receptor preparation with Meeko, or selection of an existing PDBQT.
5. AutoDock Vina 1.2.7 docking.
6. Ranking, CSV export, residue enrichment and internal pose inspection.

The distributed applications include Python, Qt, Open Babel, Meeko, RDKit,
PeptideBuilder and AutoDock Vina. End users do not need to install those tools
separately. Every portable package and installer includes the same English
`README.txt` and the MIT `LICENSE.txt`.

## Release artifacts

| System | Architecture | Portable package | Installer |
| --- | --- | --- | --- |
| macOS | Apple Silicon (ARM64) | ZIP | DMG |
| macOS | Intel (x86-64) | ZIP | DMG |
| Windows 10/11 | x86-64 | ZIP | Inno Setup EXE |
| Linux (glibc 2.35+) | x86-64 | TAR.GZ | AppImage |

Windows uses the official Vina 1.2.7 command-line executable because the
official Vina Python bindings are published only for Linux and macOS. The
scientific engine and exposed RPG parameters are the same. Linux is built on
Ubuntu 22.04 to retain compatibility with contemporary x86-64 distributions.

## Reproducible Windows and Linux builds

Native builds run in `.github/workflows/build-rpg-v2.0-cross-platform.yml`.
They install the pinned Python dependencies, download the matching official
Vina 1.2.7 executable, run the complete unit-test suite, create the frozen
application, and run an internal package test that performs PDB generation,
PDBQT conversion and a minimal real Vina docking.

The workflow can be started manually or by pushing a `v2.0.*` tag. It creates
downloadable Actions artifacts but deliberately does not publish them in the
source repository. Final binaries are published in the dedicated
[`RPG-Software`](https://github.com/RivasPardoLab/RPG-Software) repository;
source tags and maintenance branches remain in
[`RPG-Dev`](https://github.com/RivasPardoLab/RPG-Dev).

For a local native build, install Python 3.12 and then run:

```text
python -m pip install -r requirements-cross-platform-v2.0.txt
python Scripts/build_cross_platform_v2_0.py --vina-binary /path/to/vina
```

Cross-compilation is not supported: Windows must be built on Windows and Linux
must be built on Linux. This keeps native libraries and Qt plugins correct.

## Source and license

- Historical Windows-oriented upstream boundary: commit `0bf52a6`.
- Completed RPG 2.0 workflow boundary: commit `5c2ee7a` plus release packaging.
- Release tag: `v2.0.0`.
- Project license: MIT; see `LICENSE`.

The official Vina executable is redistributed under its Apache 2.0 license.
Open Babel and all other bundled components retain their respective upstream
licenses. Release checksums must be verified before distribution.
