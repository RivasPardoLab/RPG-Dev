# RPG macOS 2.0.0 — Stage 1–4B

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
`VinaResults`. Stage 4A ranks and filters those results, exports the selected
peptides, and analyzes amino-acid frequency at every sequence position. Stage
4B displays the best Vina pose for any ranked peptide together with the
receptor in the embedded cartoon viewer.

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
user. **Preview Docking Box** opens the receptor as a smoothed protein-backbone
cartoon in RPG's built-in viewer. Drag to rotate, use the mouse wheel to zoom,
and hold Shift while dragging to move the box in the current viewing plane.
Center and size can also be entered to 0.01 Å precision. **Use Box in Vina**
transfers those values directly to `config.txt`.

The viewer initially centers RPG's 60 × 60 × 60 Å box on the receptor. **Fit
whole receptor (+4 Å)** is a geometric convenience, not a prediction of the
binding site; focused docking should still use experimental, structural, or
otherwise scientifically justified site information.

The run creates numbered `*-out.pdbqt` pose files plus `affinities.csv` and
`docking-manifest.json`. The manifest records the Vina version, configuration,
and actual random seed for every ligand. Existing contents of `VinaResults`
are never overwritten.

## Stage 4 result analysis and pose visualization

After docking, choose **Go to Stage 4**. RPG loads `random.txt` and
`VinaResults/affinities.csv`, preserves the original numeric mapping between
each ligand and peptide sequence, and sorts results from the most favorable
(most negative) Vina affinity to the least favorable. Results can be filtered
by an inclusive affinity cutoff, limited to the top N entries, or both.

**Rank and Export** writes `Best-Peptides.csv` in the RPG workspace and shows
the ranked result table. **Analyze Amino Acids** then applies the selected
minimum frequency to those filtered peptide sequences and writes
`Best-AminoAcids.csv`. An existing completed workspace can also be opened
directly from Stage 4.

Stage 4B adds **View Cartoon Pose**. Select a rank from the filtered table and
open its best Vina pose in the embedded viewer. The receptor is shown as a blue
cartoon and the peptide as an orange cartoon; drag to rotate and use the wheel
to zoom. RPG reads the receptor from `docking-manifest.json`, falls back to a
PDBQT in the workspace's `Receptor` folder, and asks for the receptor only when
neither location is available.

The pose viewer intentionally displays the first model in each `*-out.pdbqt`,
which is Vina's best-scoring mode and corresponds to the affinity used by the
ranking table. Visualization does not alter coordinates, rerun docking, or
rescore the complex.

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

The final archived release is built with
`Scripts/build_macos_v2_0_release.sh` for both ARM64 and Intel. See
`README-RPG-macOS-v2.0-release.md` for the source boundary, artifact layout and
reproducible commands. The applications are ad-hoc signed for local use but
are not notarized by Apple. On another Mac, the first launch may require
Control-clicking the app and choosing **Open**.

## Test

```bash
python -m unittest discover -s tests -v
```
