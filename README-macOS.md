# RPG Stage 1–3B for macOS

This branch is a conservative macOS edition of the RPG workflow through Vina
docking, based on [RivasPardoLab/RPG-Dev](https://github.com/RivasPardoLab/RPG-Dev).
It keeps the RPG interface, amino-acid selector, combination algorithm,
`peptides.txt`, random selection in `random.txt`, and numbered PDB output in
`Chimera-Peptides`. Stage 2 uses PeptideBuilder instead of UCSF Chimera. Stage
3A preserves RPG's Open Babel operation: add hydrogens to the numbered PDB
structures and write corresponding PDBQT files to `Ligands`. Stage 3B accepts
a user-cleaned protein PDB and prepares it as a rigid receptor with Meeko 0.8,
or accepts an existing rigid receptor PDBQT. It retains RPG's original Vina
search-box parameters and runs AutoDock Vina 1.2.7. Results are written to
`VinaResults`. Stage 4 result analysis is intentionally not part of this
edition yet.

Stage 3A deliberately calls Open Babel's `AddHydrogens()` just like the
published RPG code. It does not select a pH, minimize the structures, or apply
a different charge model. Open Babel can report a bond-order/kekulization
warning for some histidine- or tryptophan-containing PDB structures. The PDBQT
files remain readable, but their atom typing should be reviewed before using
those structures in production docking.

## Vina docking

After Stage 3A, use **Prepare Receptor from PDB** with a protein structure that
you have already cleaned. RPG parameterizes it with Meeko and writes the rigid
PDBQT plus `<name>_receptor-manifest.json` in `Receptor`. This conservative
step does not silently remove chains, waters, ligands, metals, alternate
locations, or bad residues. Template failures must be corrected in the input
structure.

**Use Existing Receptor PDBQT** remains available. RPG now rejects files with
ligand-only torsion records such as `ROOT`, `BRANCH`, or `TORSDOF` before Vina
runs. The numbered peptide ligands are selected automatically, while **Choose
Ligand Subset** can restrict the run.

The Vina dialog preserves the published RPG defaults: 10 poses, energy range 4
kcal/mol, and exhaustiveness 10. Center and box dimensions are supplied by the
user. **Preview Docking Box** opens the receptor in RPG's built-in viewer. Drag
to rotate, use the mouse wheel to zoom, and hold Shift while dragging to move
the box in the current viewing plane. Center and size can also be entered to
0.01 Å precision. **Use Box in Vina** transfers those values directly to
`config.txt`.

The viewer initially centers RPG's 60 × 60 × 60 Å box on the receptor. **Fit
whole receptor (+4 Å)** is a geometric convenience, not a prediction of the
binding site; focused docking should still use experimental, structural, or
otherwise scientifically justified site information.

The run creates numbered `*-out.pdbqt` pose files plus `affinities.csv` and
`docking-manifest.json`. The manifest records the Vina version, configuration,
and actual random seed for every ligand. Existing contents of `VinaResults`
are never overwritten.

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
