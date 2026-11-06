# Known issues

Machine-readable list: `known_issues.tsv` (issue_id, title, introduced_commit,
fixed_commit, affects, status, details). `cmjsc check-affected` reports every run
in `registry/runs.tsv` built with a commit that contains the bug and not the fix.

## KI-001 · Dirty check misreads the first changed file
- Introduced: 17822b1 (1.0.0) · Fixed: 88e4b49 (1.0.1)
- Symptom: `build_morphometric_results` stopped with "uncommitted changes (M registry/runs.tsv)" although registry/ is meant to be ignored.
- Cause: the output of `git status --porcelain` was stripped; the leading space of the status code of the first line was lost and the path was cut one character too far.
- Effect: a run refuses to start. No result was computed with wrong data.
- Found: pmc morphometry run 2026-11-05 (MORPHO_FEHLER.flag).


## KI-002 · ROI without cells breaks the morphometry
- Introduced: 17822b1 (1.0.0) · Status: fixed in dde6681 (1.0.3)
- Symptom: `extraction_inventory.csv` status error "Conversion to double from cell is not possible"; the group is missing from `weighted_morphometric_results` (`weighted_join_diagnostics`: only_texture).
- Cause: an H5 with `num_detections = 0` gives an empty `CellInstances.tsv.gz`; MATLAB reads the empty columns as text. `cmjsc convert` reports such a ROI as `ok`.
- Found: pmc J0045, B9_x3421_x124_x4a_r_trace_2 (sub-09, 33 Mpx tissue, no cells detected at the JSC), 2026-11-06.
- Proposed fix: read empty tables as numeric; feature row with n_cells = 0 and NaN shape values; convert flags 0-cell H5 as `empty_h5` (not deletable without review).

## KI-003 · Morphometry cannot find special-trace masks
- Introduced: 17822b1 (1.0.0) · Fixed: 1b03d0c (1.0.2)
- Symptom: `extraction_inventory.csv` status error `Unable to find file "...\<roi>_mask.tif"` for ROIs with `special_trace = 1` (JBA_TA trace_type e.g. `onlyouter1`); their group is missing from `weighted_morphometric_results` (`weighted_join_diagnostics`: only_texture).
- Cause: JBA_TA stores the RegionAnnotation of a special trace as `<roi>_special_trace_mask.tif`; `one()` in `build_morphometric_results.m` only looks for `<roi>_mask.tif`. `cmjsc convert` (convert.py, `mask_path`) assumes `<roi>_mask.tif` as well: `archive_manifest.tsv` then names a non-existent mask file with an empty `mask_sha256` for these ROIs (conversion itself is unaffected, masks are not read).
- Found: vsp 20261106_1133_morphometry (VentralesStriatumPallidum, 6 of 500 ROIs: B10_x4111, B13_x4021, B17_x3016, B4_x4906, B5_x4111, B8_x4381, all VP, include_row = 1), 2026-11-06. 404 instead of 410 weighted groups. BasalGanglia and GP have no special-trace masks.
- Fix: the mask is resolved as `<roi>_mask.tif`, else `<roi>_special_trace_mask.tif` (MATLAB `one()`, Python `paths.resolve_mask`); `archive_manifest.tsv` records the resolved `mask_path` + `mask_sha256`; a missing mask stays an error. Proof: vsp 20261106_1206_morphometry (same convert run): 500 ok, 0 failed, 410 weighted groups, all matched with texture.
- Affected runs: vsp 20261106_1133_morphometry (superseded by 20261106_1206_morphometry). Convert runs are unaffected in zip/tsv; only `mask_path`/`mask_sha256` of special-trace ROIs in `archive_manifest.tsv` are wrong there (vsp 20261106_1040_J0037: 6 rows). pmc runs: no special-trace masks were involved (no mask errors in extraction_inventory).
