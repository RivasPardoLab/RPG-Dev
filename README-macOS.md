# RPG Stage 1–2 for macOS

This branch is a conservative macOS edition of the Stage 1 and Stage 2 workflow
published in [RivasPardoLab/RPG-Dev](https://github.com/RivasPardoLab/RPG-Dev).
It keeps the RPG interface, amino-acid selector, combination algorithm,
`peptides.txt`, random selection in `random.txt`, and numbered PDB output in
`Chimera-Peptides`. Stage 2 uses PeptideBuilder instead of UCSF Chimera.
Open Babel, AutoDock Vina, docking, and result analysis are intentionally not
part of this edition.

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
