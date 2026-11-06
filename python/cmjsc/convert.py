"""cmjsc convert: JSC H5 folder -> CellSegmentations.zip + CellInstances.tsv.gz per ROI."""
from __future__ import annotations

import csv
import json
import logging
import shutil
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import tifffile
import yaml

from . import __version__
from . import feature_sets as FS
from . import h5io, labels, paths, provenance, rasterize, registry
from .hashing import sha256_file

LEDGER = "cellseg_ledger.tsv"
MANIFEST = "archive_manifest.tsv"
VERIF = "verification.tsv"
LEDGER_F = ["roi_stem", "status", "n_cells", "n_layers", "seconds", "finished", "message"]
MANIFEST_F = ["roi_stem", "h5_local_path", "h5_jsc_path_derived", "job", "size_bytes", "sha256",
              "mtime", "roi_tif_path", "roi_tif_size_bytes", "mask_path", "mask_sha256",
              "archive_path", "archive_sha256", "archive_checked_at", "archive_status"]
VERIF_F = ["roi_stem", "n_cells_h5", "n_cells_zip", "n_empty_polygons", "n_layers",
           "zip_roundtrip_exact", "frac_area_exact", "n_area_diff", "max_abs_area_diff",
           "h5_bytes", "zip_bytes", "tsv_bytes", "density_bytes", "output_fraction_of_h5", "status"]
DONE = {"ok", "verify_warn"}

log = logging.getLogger("cmjsc")


def _append(path, fields, row):
    new = not Path(path).exists()
    with open(path, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fields, delimiter="\t", extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerow(row)


def _read_tsv(path):
    if not Path(path).exists():
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def _dedupe(path, fields):
    rows = _read_tsv(path)
    last = {}
    for r in rows:
        last[r["roi_stem"]] = r
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fields, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        for k in sorted(last):
            w.writerow(last[k])


def _setup_logging(out_dir):
    (out_dir / "logs").mkdir(parents=True, exist_ok=True)
    fn = out_dir / "logs" / f"convert_{time.strftime('%Y%m%d_%H%M%S')}.log"
    log.setLevel(logging.INFO)
    log.handlers.clear()
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    for h in (logging.FileHandler(fn, encoding="utf-8"), logging.StreamHandler(sys.stdout)):
        h.setFormatter(fmt)
        log.addHandler(h)
    return fn


def _yaml_info(yaml_path):
    if not yaml_path:
        return {"note": "no job YAML given"}, None
    raw = open(yaml_path, "rb").read()
    y = yaml.safe_load(raw.decode("utf-8")) or {}
    info = {
        "job_yaml": str(yaml_path),
        "job_yaml_sha256": sha256_file(yaml_path),
        "jobbox_job": y.get("job"),
        "job_name": y.get("name"),
        "model": y.get("model", "not set in YAML -> jobbox default (template lists only 'vacumu')"),
        "model_weights_file_sha256": "UNCONFIRMED (requested from Eric Upschulte)",
        "tile_size_stride": "UNCONFIRMED (requested from Eric Upschulte)",
        "regionprops_properties": y.get("regionprops.properties"),
        "drop_background": y.get("engine.mask.drop_background"),
        "drop_background_criterion": "UNCONFIRMED (requested from Eric Upschulte)",
        "source_files_image": y.get("source.files.image"),
        "source_files_mask": y.get("source.files.mask"),
        "jsc_output": y.get("output"),
    }
    return info, y


def process_roi(h5_path, stem, roi_dir, mask_dir, seg_dir, qc_dir, fs, opt, prov_ref):
    t0 = time.time()
    roi_tif = Path(roi_dir) / f"{stem}.tif"
    if not roi_tif.exists():
        raise FileNotFoundError(f"ROI image not found: {roi_tif}")
    with tifffile.TiffFile(roi_tif) as tf:
        shape = tuple(tf.pages[0].shape[:2])
    info = h5io.inspect(h5_path)
    n = info["n"]

    # ---- table -------------------------------------------------------------
    if fs["h5_columns"] == "ALL":
        cols = [c for c in info["scalar_datasets"] if c != "label"]
        if info["has_uncertainties"]:
            cols += [f"uncertainties-{k}" for k in range(4)]
    else:
        cols = list(fs["h5_columns"])
    for extra in ("scores", "region_ids"):
        if extra in info["scalar_datasets"] and extra not in cols:
            cols.append(extra)
    data = h5io.read_columns(h5_path, cols)
    px = float(opt["pixel_size_um"])
    df = pd.DataFrame({"cell_id": np.arange(1, n + 1, dtype=np.int64),
                       "x_px": data["centroid-1"], "y_px": data["centroid-0"]})
    df["x_um"] = df["x_px"] * px
    df["y_um"] = df["y_px"] * px
    df["cell_area_px"] = data["area"]
    df["cell_area_um2"] = data["area"] * px * px
    for c in cols:
        if c in ("centroid-0", "centroid-1", "area"):
            continue
        name = FS.RENAME.get(c, "cell_" + c)
        df[name] = data[c]
    tail = [c for c in ("cell_detection_score", "region_id") if c in df.columns]
    df = df[[c for c in df.columns if c not in tail] + tail]
    tsv = seg_dir / f"{stem}_CellInstances.tsv.gz"
    df.to_csv(tsv, sep="\t", index=False, float_format="%.10g", compression="gzip")
    sidecar = {
        "Description": "Single-cell table from a JSC celldetection H5 (one row per detected cell).",
        "CellIdentity": "cell_id = H5 row index + 1 (matches pixel values in CellSegmentations.zip); "
                        "H5 'label' is constant and ignored; CPN 'location' is not used.",
        "ValueSource": "skimage regionprops computed at the JSC (raw values, no filtering)",
        "CoordinateSpace": "image-pixel (ROI image, origin top-left); x = column, y = row",
        "PixelSizeUm": px,
        "FeatureSet": {"name": fs["name"], "sha256": fs["sha256"], "h5_columns": cols},
        "SourceH5": str(h5_path), "SourceH5SHA256": prov_ref["sha256"],
        "GeneratedBy": prov_ref["generated_by"],
    }
    json.dump(sidecar, open(seg_dir / f"{stem}_CellInstances.json", "w", encoding="utf-8"), indent=2)

    # ---- masks -> zip ------------------------------------------------------
    layers, raster_area, n_empty = rasterize.rasterize_layers(h5_path, shape)
    zpath = seg_dir / f"{stem}_CellSegmentations.zip"
    zinfo = rasterize.write_zip(layers, zpath)
    density_bytes = 0
    if opt["density"] == "coarse":
        dm = rasterize.density_map_coarse(df["x_px"].to_numpy(), df["y_px"].to_numpy(), shape,
                                          bin_px=int(round(20 / px)), pixel_size_um=px)
        dpath = seg_dir / f"{stem}_DensityMap.tif"
        tifffile.imwrite(dpath, dm, compression="zlib")
        density_bytes = dpath.stat().st_size
    if qc_dir is not None and layers:
        _qc_overlay(roi_tif, layers, qc_dir / f"{stem}_overlay.png",
                    centre=(float(np.median(df["y_px"])), float(np.median(df["x_px"]))))
    del layers
    json.dump({
        "Description": "Cell instance masks rasterised from the CPN contours of a JSC H5. "
                       "Dynamic number of label layers (overlapping cells in further layers). "
                       "0 = background, other values = cell_id (matches CellInstances).",
        "MaskKind": "cell_instance_segmentation",
        "FileFormat": zinfo["file_format"], "BitDepth": zinfo["bit_depth"],
        "NumberOfLayers": zinfo["n_layers"], "MaxLabel": zinfo["max_label"],
        "ImageShape": list(shape), "CoordinateSpace": "pixel",
        "Rasterization": "skimage.draw.polygon (pixel centre inside contour), reproduces JSC regionprops",
        "EmptyPolygons": int(n_empty),
        "SourceH5": str(h5_path), "SourceH5SHA256": prov_ref["sha256"],
        "GeneratedBy": prov_ref["generated_by"],
    }, open(seg_dir / f"{stem}_CellSegmentations.json", "w", encoding="utf-8"), indent=2)

    # ---- verification ------------------------------------------------------
    zc, nl = rasterize.read_zip_counts(zpath, n)
    roundtrip = bool(np.array_equal(zc, raster_area)) and nl == zinfo["n_layers"]
    h5_area = np.asarray(data["area"], dtype=np.int64)
    diff = raster_area - h5_area
    frac = float(np.mean(diff == 0)) if n else 1.0
    n_zip = int((zc > 0).sum())
    ok = roundtrip and n_zip == n - n_empty and frac >= opt["min_area_exact"]
    h5b = Path(h5_path).stat().st_size
    zb, tb = zpath.stat().st_size, tsv.stat().st_size
    ver = {"roi_stem": stem, "n_cells_h5": n, "n_cells_zip": n_zip, "n_empty_polygons": n_empty,
           "n_layers": zinfo["n_layers"], "zip_roundtrip_exact": roundtrip,
           "frac_area_exact": f"{frac:.5f}", "n_area_diff": int((diff != 0).sum()),
           "max_abs_area_diff": int(np.abs(diff).max()) if n else 0, "h5_bytes": h5b,
           "zip_bytes": zb, "tsv_bytes": tb, "density_bytes": density_bytes,
           "output_fraction_of_h5": f"{(zb + tb + density_bytes) / h5b:.4f}",
           "status": "ok" if ok else "verify_warn"}
    return ver, time.time() - t0


def _qc_overlay(roi_tif, layers, out_png, crop=2000, centre=None):
    """Crop (crop x crop px) around the median cell position with cell outlines
    (red = layer 0, orange = further layers)."""
    import cv2
    img = tifffile.imread(roi_tif)
    if img.ndim > 2:
        img = img[..., 0]
    r, c = img.shape
    cr, cc = centre if centre is not None else (r / 2, c / 2)
    r0 = int(min(max(0, cr - crop / 2), max(0, r - crop)))
    c0 = int(min(max(0, cc - crop / 2), max(0, c - crop)))
    sl = (slice(r0, r0 + crop), slice(c0, c0 + crop))
    rgb = cv2.cvtColor(img[sl], cv2.COLOR_GRAY2BGR)
    for k, layer in enumerate(layers):
        lab = layer[sl].astype(np.int32)
        d = np.zeros(lab.shape, bool)
        d[:-1, :] |= lab[:-1, :] != lab[1:, :]
        d[1:, :] |= lab[1:, :] != lab[:-1, :]
        d[:, :-1] |= lab[:, :-1] != lab[:, 1:]
        d[:, 1:] |= lab[:, 1:] != lab[:, :-1]
        edge = d & (lab > 0)
        rgb[edge] = (0, 0, 255) if k == 0 else (0, 200, 255)
    cv2.imwrite(str(out_png), rgb)


def run(args) -> int:
    out_dir = Path(args.out)
    seg_dir = out_dir / "cell_segmentations"
    seg_dir.mkdir(parents=True, exist_ok=True)
    qc_dir = out_dir / "qc"
    qc_dir.mkdir(exist_ok=True)
    logfile = _setup_logging(out_dir)

    git = provenance.git_state()
    if git["dirty"] and not args.allow_dirty:
        log.error("Repository has uncommitted changes %s - commit first or use --allow-dirty.",
                  git["dirty_files"])
        return 2
    fs = FS.load(args.features)
    yinfo, _ = _yaml_info(args.yaml)
    h5_dir = Path(args.h5_dir)
    job = args.job or h5_dir.name
    generated_by = {"Name": "cmjsc", "Version": __version__, "GitCommit": git["commit"],
                    "GitDescribe": git["describe"], "Repository": git["remote"]}

    prov_path = out_dir / "PROVENANCE.json"
    prov = json.load(open(prov_path, encoding="utf-8")) if prov_path.exists() else None
    session = {"started": provenance.now(), "command": " ".join(sys.argv), "git": git,
               "log": str(logfile)}
    if prov is None:
        prov = {"run_id": out_dir.name, "started": session["started"], "command": session["command"],
                "software": {"cmjsc_version": __version__, "git": git,
                             "environment": provenance.environment()},
                "inputs": {"h5_dir": str(h5_dir), "roi_dir": args.roi_dir, "mask_dir": args.mask_dir,
                           "exclude_list": args.exclude_list,
                           "exclude_list_sha256": sha256_file(args.exclude_list) if args.exclude_list else None,
                           "brains_tsv": args.brains_tsv, "project": args.project, "job": job},
                "segmentation": yinfo,
                "parameters": {"feature_set": fs["name"], "feature_set_sha256": fs["sha256"],
                               "feature_set_definition": fs["definition"],
                               "pixel_size_um": args.pixel_size_um, "density": args.density,
                               "min_area_exact": args.min_area_exact, "min_age_min": args.min_age_min,
                               "rasterization": "skimage.draw.polygon"},
                "sessions": []}
    else:
        if prov["parameters"]["feature_set_sha256"] != fs["sha256"]:
            log.error("Existing run used feature set %s (%s); refusing to mix. Use a new --out.",
                      prov["parameters"]["feature_set"], prov["parameters"]["feature_set_sha256"])
            return 2
    prov["sessions"].append(session)
    prov["status"] = "running"
    provenance.write_json(prov, prov_path)
    if args.yaml:
        shutil.copy2(args.yaml, out_dir / Path(args.yaml).name)

    done = {r["roi_stem"] for r in _read_tsv(out_dir / LEDGER) if r["status"] in DONE}
    now = time.time()
    files = sorted(p for p in h5_dir.glob(args.pattern) if p.suffix == ".h5" and not p.name.startswith("."))
    todo, waiting = [], []
    for p in files:
        if p.stem in done:
            continue
        if now - p.stat().st_mtime < args.min_age_min * 60:
            waiting.append(p.stem)
            continue
        todo.append(p)
    if args.limit:
        todo = todo[: args.limit]
    log.info("cmjsc %s (%s) | feature set %s | %d H5 in %s | done %d | to do %d | too new %d",
             __version__, git["describe"], fs["name"], len(files), h5_dir, len(done), len(todo),
             len(waiting))

    opt = {"pixel_size_um": args.pixel_size_um, "density": args.density,
           "min_area_exact": args.min_area_exact}
    jsc_base = (yinfo.get("jsc_output") or "").rstrip("/")
    n_ok = n_err = 0
    for i, p in enumerate(todo, 1):
        stem = p.stem
        try:
            inf = h5io.inspect(p)
            if not inf["complete"]:
                _append(out_dir / LEDGER, LEDGER_F, {"roi_stem": stem, "status": "incomplete_h5",
                        "finished": provenance.now(), "message": "H5 attr complete != True"})
                log.warning("[%d/%d] %s: H5 not complete - skipped", i, len(todo), stem)
                continue
            st = p.stat()
            sha = sha256_file(p)
            mask_file = paths.resolve_mask(args.mask_dir, stem)  # _mask.tif or _special_trace_mask.tif (KI-003)
            mrow = {"roi_stem": stem, "h5_local_path": str(p),
                    "h5_jsc_path_derived": f"{jsc_base}/{h5_dir.name}/{p.name}" if jsc_base else "",
                    "job": job, "size_bytes": st.st_size, "sha256": sha, "mtime": st.st_mtime,
                    "roi_tif_path": str(Path(args.roi_dir) / f"{stem}.tif"),
                    "roi_tif_size_bytes": (Path(args.roi_dir) / f"{stem}.tif").stat().st_size,
                    "mask_path": str(mask_file),
                    "mask_sha256": sha256_file(mask_file) if mask_file.exists() else "",
                    "archive_path": "", "archive_sha256": "", "archive_checked_at": "",
                    "archive_status": ""}
            qc = qc_dir if (args.qc_every and (len(done) + i - 1) % args.qc_every == 0) else None
            ver, sec = process_roi(p, stem, args.roi_dir, args.mask_dir, seg_dir, qc, fs, opt,
                                   {"sha256": sha, "generated_by": generated_by})
            st2 = p.stat()
            if (st2.st_size, st2.st_mtime) != (st.st_size, st.st_mtime):
                raise RuntimeError("H5 changed during processing (size/mtime differ)")
            _append(out_dir / MANIFEST, MANIFEST_F, mrow)
            _append(out_dir / VERIF, VERIF_F, ver)
            _append(out_dir / LEDGER, LEDGER_F, {"roi_stem": stem, "status": ver["status"],
                    "n_cells": ver["n_cells_h5"], "n_layers": ver["n_layers"],
                    "seconds": f"{sec:.1f}", "finished": provenance.now(), "message": ""})
            n_ok += 1
            log.info("[%d/%d] %s: %s | %d cells, %d layers, area exact %s, out %s of H5, %.0f s",
                     i, len(todo), stem, ver["status"], ver["n_cells_h5"], ver["n_layers"],
                     ver["frac_area_exact"], ver["output_fraction_of_h5"], sec)
        except Exception as e:  # keep going, record the error
            n_err += 1
            _append(out_dir / LEDGER, LEDGER_F, {"roi_stem": stem, "status": "error",
                    "finished": provenance.now(), "message": repr(e)[:500]})
            log.exception("[%d/%d] %s: ERROR %s", i, len(todo), stem, e)

    for f, fl in ((LEDGER, LEDGER_F), (MANIFEST, MANIFEST_F), (VERIF, VERIF_F)):
        if (out_dir / f).exists():
            _dedupe(out_dir / f, fl)

    # labels for every converted ROI
    led = _read_tsv(out_dir / LEDGER)
    stems = sorted({r["roi_stem"] for r in led if r["status"] in DONE})
    if stems:
        L = labels.build_label_table(stems, args.exclude_list, args.brains_tsv)
        L.to_csv(out_dir / "cellseg_labels.tsv", sep="\t", index=False)

    status_counts = {}
    for r in led:
        status_counts[r["status"]] = status_counts.get(r["status"], 0) + 1
    ver_rows = _read_tsv(out_dir / VERIF)
    h5b = sum(int(r["h5_bytes"]) for r in ver_rows)
    outb = sum(int(r["zip_bytes"]) + int(r["tsv_bytes"]) + int(r["density_bytes"]) for r in ver_rows)
    prov["finished"] = provenance.now()
    stem_set = set(stems)
    n_files_done = sum(p.stem in stem_set for p in files)
    prov["status"] = "complete" if not waiting and status_counts.get("error", 0) == 0 \
        and n_files_done == len(files) and args.pattern == "*.h5" else "partial"
    prov["summary"] = {"h5_files_seen": len(files), "rois_converted": len(stems),
                       "status_counts": status_counts, "h5_too_new_skipped": len(waiting),
                       "h5_total_bytes": h5b, "output_total_bytes": outb,
                       "output_fraction_of_h5": round(outb / h5b, 4) if h5b else None,
                       "this_session_ok": n_ok, "this_session_errors": n_err}
    provenance.write_json(prov, prov_path)
    provenance.write_markdown(prov, out_dir / "PROVENANCE.md")
    registry.append({"run_id": prov["run_id"], "date": prov["finished"], "tool": "cmjsc convert",
                     "project": args.project or "", "job": job, "out_dir": str(out_dir),
                     "h5_dir": str(h5_dir), "git_commit": git["commit"],
                     "git_describe": git["describe"], "feature_set": fs["name"],
                     "feature_set_sha256": fs["sha256"], "n_rois_ok": len(stems),
                     "n_rois_error": status_counts.get("error", 0),
                     "notes": f"session {len(prov['sessions'])}, status {prov['status']}"})
    log.info("done: %s | converted %d of %d H5 (run total %d) | errors %d | output %.1f %% of H5 size",
             prov["status"], n_files_done, len(files), len(stems), status_counts.get("error", 0),
             100 * outb / h5b if h5b else 0)
    return 0 if n_err == 0 else 1
