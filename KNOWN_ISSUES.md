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
