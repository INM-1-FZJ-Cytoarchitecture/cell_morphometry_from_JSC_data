"""Command line: cmjsc convert | import-cellseg | archive | check-affected | feature-sets."""
from __future__ import annotations

import argparse
import sys

from . import __version__


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="cmjsc", description=__doc__)
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("convert", help="JSC H5 folder -> CellSegmentations.zip + CellInstances.tsv.gz")
    c.add_argument("--h5-dir", required=True, help="folder with the JSC H5 files (read only, may be a network drive)")
    c.add_argument("--yaml", help="jobbox YAML of the JSC job (copied into the run, hashed)")
    c.add_argument("--roi-dir", required=True, help="high_resolution_ROIs (image shape, QC overlays)")
    c.add_argument("--mask-dir", required=True, help="high_resolution_ROIs_masks (recorded for provenance)")
    c.add_argument("--exclude-list", help="JBA_TA exclude list (_edit.xlsx) for include_row")
    c.add_argument("--brains-tsv", help="table b_code_OST -> pm_id, sub_id (e.g. 00_admin/brains.tsv)")
    c.add_argument("--out", required=True, help="run folder <analysis>/03_cellseg/runs/<YYYYMMDD_HHMM>_<job>")
    c.add_argument("--project", default="")
    c.add_argument("--job", help="job name (default: name of --h5-dir)")
    c.add_argument("--features", default=None, help="feature set from config/feature_sets.yaml (default: its 'default')")
    c.add_argument("--density", choices=["off", "coarse"], default="off", help="DensityMap on a 20-um grid")
    c.add_argument("--pixel-size-um", type=float, default=1.0)
    c.add_argument("--min-area-exact", type=float, default=0.95,
                   help="min. fraction of cells whose rasterised area equals the H5 area")
    c.add_argument("--min-age-min", type=float, default=5.0, help="skip H5 modified less than N minutes ago")
    c.add_argument("--min-in-mask", type=float, default=0.9,
                   help="min. fraction of cell centroids inside the RegionAnnotation mask, else status mask_mismatch (KI-005)")
    c.add_argument("--qc-every", type=int, default=100, help="QC overlay for every n-th ROI (0 = off)")
    c.add_argument("--pattern", default="*.h5", help="glob for H5 names (e.g. B1_*.h5)")
    c.add_argument("--limit", type=int, default=0)
    c.add_argument("--allow-dirty", action="store_true")

    m = sub.add_parser("import-cellseg", help="local cellseg outputs -> run folder (as convert)")
    m.add_argument("--cellseg-dir", required=True, help="folder with cellseg outputs (<roi>_CellInstances.tsv, searched recursively)")
    m.add_argument("--roi-dir", required=True, help="high_resolution_ROIs (recorded for provenance)")
    m.add_argument("--mask-dir", required=True, help="high_resolution_ROIs_masks (recorded for provenance)")
    m.add_argument("--exclude-list", help="JBA_TA exclude list (_edit.xlsx) for include_row")
    m.add_argument("--brains-tsv", help="table b_code_OST -> pm_id, sub_id")
    m.add_argument("--out", required=True, help="run folder <analysis>/03_cellseg/runs/<YYYYMMDD_HHMM>_<job>")
    m.add_argument("--project", default="")
    m.add_argument("--job", help="job name (default: name of --cellseg-dir)")
    m.add_argument("--features", default=None, help="feature set whose columns must be present")
    m.add_argument("--min-in-mask", type=float, default=0.9,
                   help="min. fraction of cell centroids inside the RegionAnnotation mask, else status mask_mismatch")
    m.add_argument("--allow-dirty", action="store_true")

    a = sub.add_parser("archive", help="verify archived H5 copies and write loeschbar.tsv")
    a.add_argument("--run", required=True, help="run folder of cmjsc convert")
    a.add_argument("--archive-dir", required=True, help="folder with the archived H5 (searched recursively)")
    a.add_argument("--recheck", action="store_true", help="hash again even if already matched")

    sub.add_parser("check-affected", help="list registered runs affected by known_issues.tsv")
    sub.add_parser("feature-sets", help="show the feature sets")

    args = ap.parse_args(argv)
    if args.cmd == "convert":
        from .convert import run
        return run(args)
    if args.cmd == "import-cellseg":
        from .import_cellseg import run
        return run(args)
    if args.cmd == "archive":
        from .archive import run
        return run(args)
    if args.cmd == "check-affected":
        from .registry import affected_runs
        rows = affected_runs()
        if not rows:
            print("no registered run is affected by a known issue")
        for r in rows:
            print(f"{r['issue_id']}\t{r['project']}\t{r['run_id']}\t{r['out_dir']}\t{r['title']}")
        return 0
    if args.cmd == "feature-sets":
        import yaml
        from .paths import FEATURE_SETS_FILE
        print(open(FEATURE_SETS_FILE, encoding="utf-8").read())
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
