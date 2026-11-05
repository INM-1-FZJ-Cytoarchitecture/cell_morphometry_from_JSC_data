# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), versions = git tags.

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
