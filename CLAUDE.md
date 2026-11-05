# Instructions for Claude – cell_morphometry_from_JSC_data

1. JSC segmentation results are ALWAYS processed with this repo (`cmjsc convert`,
   `cmjsc archive`, `matlab/build_morphometric_results.m`), never with ad-hoc scripts.
2. Before changing code: read README, CHANGELOG, KNOWN_ISSUES.md. Code changes only
   with Sebastian's approval; commit + push to main, tag releases, update CHANGELOG.
3. Feature sets: never edit an existing set in `config/feature_sets.yaml`; add a new one.
4. Every bug found: row in `known_issues.tsv` (+ text in KNOWN_ISSUES.md) with
   introducing and fixing commit; then run `cmjsc check-affected` and report the
   affected projects/runs to Sebastian.
5. Commit `registry/runs.tsv` after runs (it is excluded from the dirty check).
6. Never claim model/weights/tile/stride facts that are not documented by the JSC
   job (YAML/manifest), Eric Upschulte or Sebastian.
7. H5 files are deleted only if listed in `loeschbar.tsv` and Sebastian agrees.
