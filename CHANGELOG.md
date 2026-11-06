# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), versions = git tags.

## [1.0.2] - 2026-11-06
### Fixed
- KI-003: the RegionAnnotation mask of a JBA_TA special trace is named
  `<roi>_special_trace_mask.tif`; `build_morphometric_results` (MATLAB) now
  falls back to that name, and `cmjsc convert` records the resolved mask file
  and its SHA-256 in `archive_manifest.tsv` (`paths.resolve_mask`). A missing
  mask is still an error. Test added. Conversion results (zip/tsv) are not
  affected; morphometry runs with special traces lacked those ROIs
  (vsp 20261106_1133_morphometry: 6 of 500).
- Package version bumped to 1.0.2 (`__version__`/pyproject still said 1.0.0 in 1.0.1).

## [1.0.3] - 2026-11-06
### Fixed
- KI-002: a ROI without cells (H5 num_detections = 0) broke the MATLAB
  morphometry (empty table read as text). Empty tables are now numeric; the ROI
  gets a feature row with n_cells = 0, density 0 and NaN shape values.
  `cmjsc convert` marks such an H5 `empty_h5` (not `ok`, so not in loeschbar.tsv
  without review); included 0-cell ROIs are reported in the morphometry log.
### Added
- `build_morphometric_results(..., 'exclude_list', xlsx)`: take include_row from
  a (newer) JBA_TA exclude list instead of cellseg_labels.tsv; path + SHA-256 in
  PROVENANCE.

## [1.0.1] - 2026-11-05
### Fixed
- KI-001: the "uncommitted changes" check misread the first line of
  `git status --porcelain` (leading space removed), so a modified
  `registry/runs.tsv` was not ignored when it was the only/first change and
  `build_morphometric_results` refused to start. Fixed in Python and MATLAB;
  test added. No results were affected (the check only blocks a start).

## [1.0.0] - 2026-11-05
### Added
- `cmjsc convert`: JSC H5 -> `CellSegmentations.zip` (cellseg layer format) +
  `CellInstances.tsv.gz` per ROI; feature sets from `config/feature_sets.yaml`
  (`thalamus_v1` default, `complete`); SHA-256 of every H5 in
  `archive_manifest.tsv`; verification (zip round trip, area vs. H5); QC overlays;
  resume; PROVENANCE.json/.md; run registry.
- `cmjsc archive`: verify archived copies, fill archive path/hash, write `loeschbar.tsv`.
- `cmjsc check-affected`: registered runs affected by `known_issues.tsv`.
- MATLAB `build_morphometric_results.m` / `extract_morphometric_features.m`
  (Thalamus formulas, centroid positions, generic labels, calculate_wmean weighting).
