"""cmjsc import-cellseg: local cellseg outputs -> cmjsc run folder.

For ROIs segmented locally with the canonical engine
(F:\\GitHub\\cell_segmentation, ``cellseg run``) instead of the JSC jobbox.
cellseg already writes the cmjsc/cellseg schema (CellSegmentations.zip in the
layer format, CellInstances.tsv with cell_id, x_px, y_px, cell_area_px,
cell_<regionprop> ...). This step only gathers those files into the same run
structure that ``cmjsc convert`` produces, so ``build_morphometric_results``
can read JSC-converted and locally segmented ROIs the same way:

    <out>/cell_segmentations/<roi>_CellInstances.tsv.gz (+ .json)
    <out>/cell_segmentations/<roi>_CellSegmentations.zip (+ .json)
    <out>/cellseg_labels.tsv, cellseg_ledger.tsv, import_manifest.tsv
    <out>/detection_manifests/<roi>_detection_manifest.json
    <out>/PROVENANCE.json/.md, logs/; plus a line in registry/runs.tsv

Nothing is recomputed: cell values are copied unchanged (TSV only gzipped).
The segmentation parameters are taken from each detection_manifest.json
(model name + SHA-256, tile/stride, regionprops set) and checked to be equal
across all imported ROIs.
"""
from __future__ import annotations

import gzip
import json
import logging
import shutil
import sys
import time
from pathlib import Path

import pandas as pd

from . import __version__
from . import feature_sets as FS
from . import labels, paths, provenance, registry
from .convert import _append, _dedupe, _read_tsv, _setup_logging
from .hashing import sha256_file

LEDGER = "cellseg_ledger.tsv"
MANIFEST = "import_manifest.tsv"
LEDGER_F = ["roi_stem", "status", "n_cells", "n_layers", "seconds", "finished", "message"]
MANIFEST_F = ["roi_stem", "source_tsv", "source_tsv_sha256", "source_zip", "source_zip_sha256",
              "detection_manifest", "detection_manifest_sha256", "model_name", "model_sha256",
              "roi_tif_path", "roi_tif_size_bytes", "mask_path", "mask_sha256"]
DONE = {"ok", "empty_cellseg"}

# H5/regionprops name in config/feature_sets.yaml -> column written by cellseg
_COLMAP = {"centroid-0": "y_px", "centroid-1": "x_px", "area": "cell_area_px"}

log = logging.getLogger("cmjsc")


def required_columns(fs) -> list[str]:
    if fs["h5_columns"] == "ALL":
        return ["cell_id", "x_px", "y_px", "cell_area_px"]
    return ["cell_id"] + [_COLMAP.get(c, f"cell_{c}") for c in fs["h5_columns"]]


def _seg_params(man: dict) -> dict:
    md = man.get("metadata", {})
    return {"model_name": md.get("model_name"), "model_sha256": md.get("model_sha256"),
            "inference": md.get("inference"), "props": md.get("props"),
            "generated_by": md.get("generated_by")}


def find_outputs(cellseg_dir: Path) -> dict:
    """{roi_stem: folder} for every <stem>_CellInstances.tsv below cellseg_dir."""
    out = {}
    for t in sorted(Path(cellseg_dir).rglob("*_CellInstances.tsv")):
        stem = t.name[: -len("_CellInstances.tsv")]
        if stem in out:
            raise ValueError(f"ROI {stem} found twice: {out[stem]} and {t.parent}")
        out[stem] = t.parent
    return out


def run(args) -> int:
    out_dir = Path(args.out)
    seg_dir = out_dir / "cell_segmentations"
    seg_dir.mkdir(parents=True, exist_ok=True)
    man_dir = out_dir / "detection_manifests"
    man_dir.mkdir(exist_ok=True)
    logfile = _setup_logging(out_dir)

    git = provenance.git_state()
    if git["dirty"] and not args.allow_dirty:
        log.error("Repository has uncommitted changes %s - commit first or use --allow-dirty.",
                  git["dirty_files"])
        return 2
    fs = FS.load(args.features)
    need = required_columns(fs)
    src = find_outputs(args.cellseg_dir)
    job = args.job or Path(args.cellseg_dir).name

    prov_path = out_dir / "PROVENANCE.json"
    prov = json.load(open(prov_path, encoding="utf-8")) if prov_path.exists() else None
    session = {"started": provenance.now(), "command": " ".join(sys.argv), "git": git,
               "log": str(logfile)}
    if prov is None:
        prov = {"run_id": out_dir.name, "started": session["started"], "command": session["command"],
                "software": {"cmjsc_version": __version__, "git": git,
                             "environment": provenance.environment()},
                "inputs": {"cellseg_dir": str(args.cellseg_dir), "roi_dir": args.roi_dir,
                           "mask_dir": args.mask_dir, "exclude_list": args.exclude_list,
                           "exclude_list_sha256": sha256_file(args.exclude_list) if args.exclude_list else None,
                           "brains_tsv": args.brains_tsv, "project": args.project, "job": job},
                "segmentation_title": "Segmentation (local cellseg, from detection_manifest.json)",
                "segmentation": {"source": "local cellseg (F:\\GitHub\\cell_segmentation)"},
                "parameters": {"feature_set": fs["name"], "feature_set_sha256": fs["sha256"],
                               "feature_set_definition": fs["definition"],
                               "required_columns": need,
                               "note": "cell values copied unchanged from cellseg CellInstances.tsv"},
                "sessions": []}
    elif prov["parameters"]["feature_set_sha256"] != fs["sha256"]:
        log.error("Existing run used feature set %s; refusing to mix. Use a new --out.",
                  prov["parameters"]["feature_set"])
        return 2
    prov["sessions"].append(session)
    prov["status"] = "running"
    provenance.write_json(prov, prov_path)

    done = {r["roi_stem"] for r in _read_tsv(out_dir / LEDGER) if r["status"] in DONE}
    todo = [s for s in src if s not in done]
    log.info("cmjsc %s (%s) import-cellseg | feature set %s | %d ROIs in %s | done %d | to do %d",
             __version__, git["describe"], fs["name"], len(src), args.cellseg_dir, len(done), len(todo))
    seg_ref = prov["segmentation"].get("parameters")
    n_ok = n_err = 0
    for i, stem in enumerate(todo, 1):
        t0 = time.time()
        d = src[stem]
        try:
            tsv = d / f"{stem}_CellInstances.tsv"
            zp = d / f"{stem}_CellSegmentations.zip"
            mf = d / "detection_manifest.json"
            if not zp.exists():
                raise FileNotFoundError(f"missing {zp.name}")
            if not mf.exists():
                raise FileNotFoundError(f"missing detection_manifest.json in {d}")
            man = json.load(open(mf, encoding="utf-8"))
            sp = _seg_params(man)
            if seg_ref is None:
                seg_ref = sp
                prov["segmentation"]["parameters"] = sp
            elif json.dumps(sp, sort_keys=True) != json.dumps(seg_ref, sort_keys=True):
                raise ValueError("segmentation parameters differ from the other ROIs of this run")
            T = pd.read_csv(tsv, sep="\t", nrows=5)
            miss = [c for c in need if c not in T.columns]
            if miss:
                raise ValueError(f"CellInstances.tsv lacks columns {miss} (feature set {fs['name']})")
            n = sum(1 for _ in open(tsv, encoding="utf-8")) - 1
            with open(tsv, "rb") as fi, gzip.open(seg_dir / f"{stem}_CellInstances.tsv.gz", "wb") as fo:
                shutil.copyfileobj(fi, fo)
            shutil.copy2(zp, seg_dir / zp.name)
            for side in (f"{stem}_CellInstances.json", f"{stem}_CellSegmentations.json"):
                if (d / side).exists():
                    shutil.copy2(d / side, seg_dir / side)
            shutil.copy2(mf, man_dir / f"{stem}_detection_manifest.json")
            mask = paths.resolve_mask(args.mask_dir, stem)
            roi = Path(args.roi_dir) / f"{stem}.tif"
            _append(out_dir / MANIFEST, MANIFEST_F, {
                "roi_stem": stem, "source_tsv": str(tsv), "source_tsv_sha256": sha256_file(tsv),
                "source_zip": str(zp), "source_zip_sha256": sha256_file(zp),
                "detection_manifest": str(mf), "detection_manifest_sha256": sha256_file(mf),
                "model_name": sp["model_name"], "model_sha256": sp["model_sha256"],
                "roi_tif_path": str(roi), "roi_tif_size_bytes": roi.stat().st_size if roi.exists() else "",
                "mask_path": str(mask), "mask_sha256": sha256_file(mask) if mask.exists() else ""})
            st = "ok" if n > 0 else "empty_cellseg"
            _append(out_dir / LEDGER, LEDGER_F, {"roi_stem": stem, "status": st, "n_cells": n,
                    "n_layers": "", "seconds": round(time.time() - t0, 1),
                    "finished": provenance.now(), "message": ""})
            n_ok += 1
            log.info("[%d/%d] %s: %s | %d cells", i, len(todo), stem, st, n)
        except Exception as e:  # record and continue
            n_err += 1
            _append(out_dir / LEDGER, LEDGER_F, {"roi_stem": stem, "status": "error",
                    "finished": provenance.now(), "message": repr(e)[:500]})
            log.error("[%d/%d] %s: ERROR %s", i, len(todo), stem, e)

    for f, fl in ((LEDGER, LEDGER_F), (MANIFEST, MANIFEST_F)):
        if (out_dir / f).exists():
            _dedupe(out_dir / f, fl)
    led = _read_tsv(out_dir / LEDGER)
    stems = sorted({r["roi_stem"] for r in led if r["status"] in DONE})
    if stems:
        L = labels.build_label_table(stems, args.exclude_list, args.brains_tsv)
        L.to_csv(out_dir / "cellseg_labels.tsv", sep="\t", index=False)
    counts = {}
    for r in led:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    prov["finished"] = provenance.now()
    prov["status"] = "complete" if counts.get("error", 0) == 0 and len(stems) == len(src) else "partial"
    prov["summary"] = {"rois_found": len(src), "rois_imported": len(stems), "status_counts": counts,
                       "this_session_ok": n_ok, "this_session_errors": n_err}
    provenance.write_json(prov, prov_path)
    provenance.write_markdown(prov, out_dir / "PROVENANCE.md")
    registry.append({"run_id": prov["run_id"], "date": prov["finished"], "tool": "cmjsc import-cellseg",
                     "project": args.project or "", "job": job, "out_dir": str(out_dir),
                     "h5_dir": str(args.cellseg_dir), "git_commit": git["commit"],
                     "git_describe": git["describe"], "feature_set": fs["name"],
                     "feature_set_sha256": fs["sha256"], "n_rois_ok": len(stems),
                     "n_rois_error": counts.get("error", 0),
                     "notes": f"session {len(prov['sessions'])}, status {prov['status']}, local cellseg"})
    log.info("done: %s | imported %d of %d ROIs | errors %d", prov["status"], len(stems), len(src),
             counts.get("error", 0))
    return 0 if n_err == 0 else 1
