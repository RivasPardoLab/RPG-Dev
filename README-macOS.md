# RPG Stage 1–3A for macOS

This branch is a conservative macOS edition of the RPG workflow through Stage
3A, published in [RivasPardoLab/RPG-Dev](https://github.com/RivasPardoLab/RPG-Dev).
It keeps the RPG interface, amino-acid selector, combination algorithm,
`peptides.txt`, random selection in `random.txt`, and numbered PDB output in
`Chimera-Peptides`. Stage 2 uses PeptideBuilder instead of UCSF Chimera. Stage
3A preserves RPG's Open Babel operation: add hydrogens to the numbered PDB
structures and write corresponding PDBQT files to `Ligands`. AutoDock Vina,
docking, receptor preparation, and result analysis are intentionally not part
of this edition.

Stage 3A deliberately calls Open Babel's `AddHydrogens()` just like the
published RPG code. It does not select a pH, minimize the structures, or apply
a different charge model. Open Babel can report a bond-order/kekulization
warning for some histidine- or tryptophan-containing PDB structures. The PDBQT
files remain readable, but their atom typing should be reviewed before using
those structures in production docking.

## Run from source

```bash
conda env create -f environment-macos.yml
conda activate rpg-macos
python main.py
```

## Build the macOS application

```bash
conda activate rpg-macos
zsh Scripts/build_macos.sh
```

The build creates `dist/RPG-macOS.app` and a distributable DMG. If macOS does
not permit disk-image creation in the current environment, the script creates
`dist/RPG-macOS.zip` instead. The application is ad-hoc signed for local
use, but it is not notarized by Apple. On another Mac, the first launch may
require Control-clicking the app and choosing **Open**.

## Test

```bash
python -m unittest discover -s tests -v
```
