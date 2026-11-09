# cell_morphometry_from_JSC_data (`cmjsc`)

Turns the H5 files of a JSC cell-segmentation job (celldetection-inference-masked,
jobbox of Eric Upschulte, INM-1) into a compact, archivable per-ROI structure and
computes cell morphometry per annotation — with complete provenance, so the large
H5 files can be archived (e.g. on L:) and deleted locally.

All future analyses of JSC segmentation results use this repository (like
[JBA_TA](https://github.com/INM-1-FZJ-Cytoarchitecture/JBA_TA) for texture).

```
JBA_TA (texture, ROIs + masks)  ->  JSC jobbox (CPN segmentation, H5)
        ->  cmjsc convert  ->  cmjsc archive  ->  build_morphometric_results (MATLAB)
```

## Setup (once)

```bat
cd F:\GitHub\cell_morphometry_from_JSC_data
py -3.11 -m venv .venv
.venv\Scripts\pip install -e .[test]
.venv\Scripts\python -m pytest
```

## 1. Convert H5 -> CellSegmentations.zip + CellInstances.tsv.gz

```bat
.venv\Scripts\cmjsc convert ^
  --h5-dir      <JSC job folder with *.h5>   (read only, may be a network drive) ^
  --yaml        <jobbox YAML of the job> ^
  --roi-dir     <analysis>\...\high_resolution_ROIs ^
  --mask-dir    <analysis>\...\high_resolution_ROIs_masks ^
  --exclude-list <..._edit_*.xlsx> --brains-tsv <00_admin\brains.tsv> ^
  --project <code> --out <analysis>\03_cellseg\runs\<YYYYMMDD_HHMM>_<job>
```

Options: `--features thalamus_v1|complete` (default from `config/feature_sets.yaml`),
`--density off|coarse` (20-um grid, default off), `--limit N` (test), `--qc-every N`.
A re-run with the same `--out` resumes; H5 files that are incomplete
(`complete != True`), hidden rsync temp files and files changed in the last
5 min are skipped and picked up next time. Mixing feature sets in one run is refused.

Per ROI (`cell_segmentations/`):

| File | Content |
|---|---|
| `<roi>_CellSegmentations.zip` (+json) | instance masks, layers `CellSegmentations_NN.png` (16 bit) or `.tif` (32 bit if > 65535 cells); 0 = background, value = `cell_id`; overlapping cells in further layers (format of `cell_segmentation`/cellseg) |
| `<roi>_CellInstances.tsv.gz` (+json) | one row per cell: `cell_id, x_px, y_px, x_um, y_um, cell_area_px, cell_area_um2`, feature-set columns, `cell_detection_score, region_id` |
| `<roi>_DensityMap.tif` | optional, cells/mm² on a 20-um grid |

Per run: `PROVENANCE.json/.md`, copy of the job YAML, `archive_manifest.tsv`
(path, size, mtime, **SHA-256** of every H5; archive columns empty until
`cmjsc archive`), `verification.tsv`, `cellseg_ledger.tsv`, `cellseg_labels.tsv`,
`qc/` overlays, `logs/`; plus a line in `registry/runs.tsv`.

**Cell identity:** H5 row i = contour i = cell `i+1`. The H5 `label` dataset is
constant (regionprops on one-cell masks) and ignored; positions are skimage
`centroid-0/1` (y/x), never CPN `location`.

**Rasterisation:** `skimage.draw.polygon` (pixel centre inside the contour). It
reproduces the JSC regionprops (area, centroid, intensity); `verification.tsv`
reports per ROI the fraction of cells whose zip area equals the H5 area and a
zip round trip.

## 1b. Locally segmented ROIs (cellseg) -> same run structure

For a few ROIs it can be easier to segment locally with the canonical engine
(`F:\GitHub\cell_segmentation`, `cellseg run <roi>.tif -o <dir>\<roi>
--region-mask <roi>_mask.tif --pixel-size-um 1`) instead of a JSC job. Then

```bat
.venv\Scripts\cmjsc import-cellseg --cellseg-dir <folder with the cellseg outputs> ^
  --roi-dir ... --mask-dir ... --exclude-list ... --brains-tsv ... ^
  --project <code> --out <analysis>\03_cellseg\runs\<YYYYMMDD_HHMM>_local_cellseg
```

copies the cellseg outputs unchanged into a run folder that
`build_morphometric_results` reads like a convert run (`import_manifest.tsv`
holds the SHA-256 of every source file, `detection_manifests/` the model and
inference parameters per ROI). Report locally and JSC-segmented ROIs as two
segmentation runs: the local engine documents tile/stride in its manifest, the
JSC job does not.

## 2. Archive, then delete

```bat
.venv\Scripts\cmjsc archive --run <run folder> --archive-dir L:\<archive folder>
```
Hashes every archived copy, fills `archive_path`/`archive_sha256` in
`archive_manifest.tsv` and writes `loeschbar.tsv` = H5 that are converted,
verified **and** bit-identical on the archive. Delete only those.

## 3. Morphometry per ROI (MATLAB)

```matlab
addpath('F:\GitHub\cell_morphometry_from_JSC_data\matlab');
build_morphometric_results('convert_run', RUN, 'mask_dir', MASKS, ...
    'out_dir', '<analysis>\04_morphometry\runs\<YYYYMMDD_HHMM>_morphometry', ...
    'percentile_trim', [1 1], 'texture_weighted', '<...>\weighted_results_all_included_sections.xlsx');
```
Features per ROI as in the Thalamus morphometry (density/mm², area distribution,
circularity 4πA/P², eccentricity, solidity, Feret, intensity, NN distance,
Clark-Evans R, Voronoi CV), positions from centroid; weighted means with the
JBA_TA `calculate_wmean` logic (include_row filter, groups brain/section/
OST_label/OST_id/side, weight = mask area).

## Feature sets

`config/feature_sets.yaml` is the single definition. Never edit an existing set;
add a new version and move `default`. Every run stores name + SHA-256.

## Reproducibility and errors

- Runs refuse to start from a repo with uncommitted changes (`--allow-dirty` to override, logged).
- Releases are tagged (`vX.Y.Z`); to reproduce a run: `git worktree add ..\cmjsc_<commit> <commit>`
  and repeat the command stored in `PROVENANCE.json`.
- Every bug goes into `known_issues.tsv` (+ `KNOWN_ISSUES.md`) with introducing and fixing
  commit; `cmjsc check-affected` lists all registered runs that are affected.

## Open (to be confirmed by the JSC side)

Model weights file + SHA-256, tile/stride, criterion of `drop_background` are not in
the H5/YAML and are recorded as UNCONFIRMED until documented.
