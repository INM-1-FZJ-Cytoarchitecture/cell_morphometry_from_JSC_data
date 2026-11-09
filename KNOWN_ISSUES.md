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

## KI-004 · Convert keeps going when the H5 folder becomes unreachable
- Introduced: 17822b1 (1.0.0) · Status: open (fix proposed, awaiting approval)
- Symptom: after a short outage of the network drive (L:) every remaining H5 gets status `error` (`FileNotFoundError ... No such file or directory`) within seconds; the run ends `partial`, EXIT 1, and the registry row shows thousands of errors.
- Cause: the per-ROI `except` in `convert.py` records the error and moves on; nothing checks whether the H5 folder itself is still reachable.
- Effect: no wrong data (nothing is written for these ROIs; `error` rows are retried on the next run with the same `--out`), but a long run silently stops doing work.
- Found: bg `20261106_1040_J0042_BasalGanglia_props_all_masks_drop_multir`, session 1: L: unreachable at 14:31:40, 2558 of 4588 H5 marked error in ~80 s (2030 ok before). H5 visible again at 19:17; resumed as session 2.
- Proposed fix: if an H5 cannot be opened because the file or folder is missing, check `h5_dir`; if it is unreachable, wait and retry (e.g. up to 30 min), then stop the session cleanly with a clear message instead of marking the rest as error.

## KI-005 · JBA_TA masks are read inverted outside MATLAB (JSC masked jobs measure the surrounding tissue)
- Introduced: 17822b1 (1.0.0, no check) · Root cause: JBA_TA `found_issues` I-023 · Status: guarded in 1.2.0 (27d3bd6: `mask_mismatch` check); data must be re-segmented with corrected masks
- Symptom: the cell centroids of a converted ROI lie outside its `<roi>_mask.tif` (as read in MATLAB); densities, sizes, shapes and spatial indices describe the tissue around the annotation.
- Cause: JBA_TA writes regular masks as 1-bit TIFF with `PhotometricInterpretation = WhiteIsZero`. MATLAB honours it (true = annotation); tifffile (Python) returns the raw bits (photometric MINISWHITE ignored), so the jobbox job `celldetection-inference-masked` (and `cellseg --region-mask`) treat the annotation as background and, with `drop_background: yes`, keep only the cells around it. Special-trace masks are 8-bit `BlackIsZero` and are read correctly. cmjsc never checked that the cells lie in the mask.
- Evidence: Alexey VSP J0037, 12 random ROIs: 11 with 99.8–100 % of centroids outside the MATLAB mask (median distance to the annotation e.g. 465 px), the one special-trace ROI 99.9 % inside. B1_x3211 cdm r trace 5: MATLAB 4.3 % of the crop is annotation, tifffile 95.75 %.
- Affected: every run built on a JSC masked job or a local cellseg region mask with JBA_TA masks: vsp/bg/gp 2026-11-06..09 (Alexey), pmc J0045 runs (same mask source; `cmjsc check-affected`).
- Proposed fix: (1) JBA_TA writes 8-bit masks (I-023) and a converter writes corrected copies for existing projects; (2) `cmjsc convert` checks per ROI the fraction of centroids inside the mask (MATLAB semantics) and flags `mask_mismatch`; (3) affected projects are re-segmented with corrected masks.

## KI-006 · voronoi_area_cv: border cells dominate, missing above 80 000 cells
- Introduced: 17822b1 (1.0.0) · Fixed: 27d3bd6 (1.2.0)
- Symptom: voronoi_area_cv takes values 2.7–269 (median ~62) in BG/VSP and correlates with log(n_cells) (r = 0.71); it is NaN for every ROI with more than 80 000 cells (257 of 2777 groups in BG/VSP, mostly ts/cdm/pm/pl).
- Cause: Voronoi polygons of the cells at the border of the point set are only bounded by the convex hull of all points (only cells touching infinity are skipped); a 130 395-cell ROI gives a maximum Voronoi area of 3·10^10 µm² and CV 172. The cell limit `n_loc <= 80000` was set for run time.
- Fix: only cells whose Voronoi polygon lies completely inside the region mask (minus-sampling edge correction), no upper cell limit, new column `voronoi_n_cells_used`. Proof: VSP B17_x3016 VP (special trace, cells inside the mask) CV 0.55 from 6125/6665 cells.
- Affected runs: every morphometry run before 1.2.0 (`cmjsc check-affected`), including earlier Thalamus results computed with the same `extract_morphometric_features.m` logic.
