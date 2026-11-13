# RPG macOS 2.0.0 — archived macOS packages

> RPG 2.0 is now documented as one cross-platform release. See
> `README-RPG-v2.0-release.md` for Windows, Linux and shared release details.

RPG macOS 2.0 is the first complete native macOS port of the original
RivasPardoLab RPG workflow. The upstream project was packaged for Windows: its
auto-py-to-exe configuration references `C:/Users/...`, `vina.exe`, Windows
DLLs and an Open Babel `win_amd64` wheel. This release preserves that upstream
source as historical lineage while defining the completed macOS port as a
separate, reproducible release.

## Source boundary

- Original Windows-oriented source: upstream commit `0bf52a6`.
- Completed macOS 2.0 workflow: commit `5c2ee7a` plus release-only branding and
  packaging metadata.
- Release tag: `v2.0.0`.

No smina, Vinardo, Vina Ensemble or LightDock code belongs to this release.
Those capabilities begin in later RPG versions.

## Included workflow

1. Combinatorial peptide-library generation.
2. Random peptide selection and PDB generation with PeptideBuilder.
3. Ligand PDBQT conversion with Open Babel.
4. Rigid receptor preparation with Meeko or use of an existing receptor PDBQT.
5. AutoDock Vina 1.2.7 docking.
6. Ranking, CSV export, amino-acid enrichment and cartoon pose inspection.

## Final macOS packages

The release is built natively for both architectures from the same source:

```text
dist/RPG-Peptides-2.0.0/macOS-ARM64/
dist/RPG-Peptides-2.0.0/macOS-Intel/
```

Each directory contains the application, ZIP, DMG and SHA-256 checksums. The
applications are ad-hoc signed but not notarized by Apple.

## Reproducible build

Apple Silicon:

```bash
TARGET_ARCH=arm64 PYTHON_BIN=/path/to/arm64/python \
  zsh Scripts/build_macos_v2_0_release.sh
```

Intel, including an Intel Python executed through Rosetta on Apple Silicon:

```bash
TARGET_ARCH=x86_64 PYTHON_BIN=/path/to/x86_64/python \
  zsh Scripts/build_macos_v2_0_release.sh
```

RPG macOS 2.0 is archived after this release. New functionality and performance
changes belong to the active experimental line rather than this tag.
