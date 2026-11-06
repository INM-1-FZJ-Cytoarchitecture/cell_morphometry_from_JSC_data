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
- Introduced: 17822b1 (1.0.0) · Status: open (fix proposed, awaiting approval)
- Symptom: `extraction_inventory.csv` status error "Conversion to double from cell is not possible"; the group is missing from `weighted_morphometric_results` (`weighted_join_diagnostics`: only_texture).
- Cause: an H5 with `num_detections = 0` gives an empty `CellInstances.tsv.gz`; MATLAB reads the empty columns as text. `cmjsc convert` reports such a ROI as `ok`.
- Found: pmc J0045, B9_x3421_x124_x4a_r_trace_2 (sub-09, 33 Mpx tissue, no cells detected at the JSC), 2026-11-06.
- Proposed fix: read empty tables as numeric; feature row with n_cells = 0 and NaN shape values; convert flags 0-cell H5 as `empty_h5` (not deletable without review).
