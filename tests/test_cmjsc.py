"""Offline tests on a synthetic JSC-like H5 (no real data needed)."""
import csv
import gzip
import json
import os

import h5py
import numpy as np
import pandas as pd
import pytest
import tifffile
from skimage.draw import polygon


def _circle(cx, cy, r, n=224):
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return np.stack([cx + r * np.cos(t), cy + r * np.sin(t)], axis=1).astype(np.float32)


@pytest.fixture()
def job(tmp_path, monkeypatch):
    monkeypatch.setenv("CMJSC_REGISTRY", str(tmp_path / "runs.tsv"))
    import importlib, cmjsc.paths, cmjsc.registry
    importlib.reload(cmjsc.paths); importlib.reload(cmjsc.registry)
    with open(tmp_path / "runs.tsv", "w") as fh:
        fh.write("\t".join(cmjsc.registry.FIELDS) + "\n")
    shape = (300, 400)
    stem = "B1_x100_x123_x4p_l_trace_1_xorigin_256_yorigin_512"
    for d in ("h5", "rois", "masks", "out"):
        (tmp_path / d).mkdir()
    img = (np.arange(shape[0] * shape[1]) % 251).astype(np.uint8).reshape(shape)
    tifffile.imwrite(tmp_path / "rois" / f"{stem}.tif", img)
    tifffile.imwrite(tmp_path / "masks" / f"{stem}_mask.tif", np.ones(shape, np.uint8))
    cs = [_circle(50, 50, 10.3), _circle(58, 50, 9.7), _circle(200, 150, 20.2), _circle(66, 50, 8.1)]
    area, c0, c1 = [], [], []
    for ct in cs:
        rr, cc = polygon(ct[:, 1], ct[:, 0], shape)
        area.append(rr.size); c0.append(rr.mean()); c1.append(cc.mean())
    n = len(cs)
    with h5py.File(tmp_path / "h5" / f"{stem}.h5", "w") as f:
        f.attrs["complete"] = True
        f.attrs["num_detections"] = n
        f["contours"] = np.stack(cs)
        f["area"] = np.array(area, float)
        f["centroid-0"] = np.array(c0)
        f["centroid-1"] = np.array(c1)
        for k in ("perimeter", "eccentricity", "solidity", "feret_diameter_max",
                  "intensity_mean", "intensity_std", "moments_hu-0", "label"):
            f[k] = np.ones(n)
        f["scores"] = np.full(n, 0.99, np.float32)
        f["region_ids"] = np.ones(n, np.int64)
        f["uncertainties"] = np.zeros((n, 4), np.float32)
    yml = tmp_path / "job.yaml"
    yml.write_text("job: celldetection-inference-masked\nname: test\noutput: /p/x\n"
                   "regionprops.properties: [all]\nengine.mask.drop_background: yes\n")
    return tmp_path, stem, np.array(area)


def _convert(tmp, extra=()):
    from cmjsc.cli import main
    return main(["convert", "--h5-dir", str(tmp / "h5"), "--yaml", str(tmp / "job.yaml"),
                 "--roi-dir", str(tmp / "rois"), "--mask-dir", str(tmp / "masks"),
                 "--out", str(tmp / "out" / "run1"), "--min-age-min", "0", "--qc-every", "1",
                 "--allow-dirty", *extra])


def test_convert_default(job):
    tmp, stem, area = job
    assert _convert(tmp) == 0
    run = tmp / "out" / "run1"
    seg = run / "cell_segmentations"
    df = pd.read_csv(seg / f"{stem}_CellInstances.tsv.gz", sep="\t")
    assert list(df.cell_id) == [1, 2, 3, 4]
    assert "cell_moments_hu-0" not in df.columns          # not in thalamus_v1
    assert {"x_px", "y_px", "cell_area_px", "cell_perimeter", "cell_detection_score", "region_id"} <= set(df.columns)
    from cmjsc.rasterize import read_zip_counts
    counts, nl = read_zip_counts(seg / f"{stem}_CellSegmentations.zip", 4)
    assert nl >= 2                                         # overlapping cells -> 2+ layers
    assert np.array_equal(counts, area)                    # every cell complete in the zip
    ver = list(csv.DictReader(open(run / "verification.tsv"), delimiter="\t"))
    assert ver[0]["status"] == "ok" and float(ver[0]["frac_area_exact"]) == 1.0
    man = list(csv.DictReader(open(run / "archive_manifest.tsv"), delimiter="\t"))
    from cmjsc.hashing import sha256_file
    assert man[0]["sha256"] == sha256_file(tmp / "h5" / f"{stem}.h5")
    assert man[0]["archive_path"] == ""
    prov = json.load(open(run / "PROVENANCE.json"))
    assert prov["parameters"]["feature_set"] == "thalamus_v1" and prov["status"] == "complete"
    assert (run / "job.yaml").exists() and (run / "PROVENANCE.md").exists()
    assert (run / "qc" / f"{stem}_overlay.png").exists()
    # resume: nothing to do, still ok
    assert _convert(tmp) == 0


def test_complete_and_archive(job, tmp_path):
    tmp, stem, _ = job
    assert _convert(tmp, ["--features", "complete", "--density", "coarse"]) == 0
    seg = tmp / "out" / "run1" / "cell_segmentations"
    df = pd.read_csv(seg / f"{stem}_CellInstances.tsv.gz", sep="\t")
    assert "cell_moments_hu-0" in df.columns and "cell_uncertainties-3" in df.columns
    assert "cell_label" not in df.columns
    assert (seg / f"{stem}_DensityMap.tif").exists()
    # archive check against a copy
    import shutil
    from cmjsc.cli import main
    arch = tmp / "L_archive"; arch.mkdir()
    shutil.copy2(tmp / "h5" / f"{stem}.h5", arch / f"{stem}.h5")
    assert main(["archive", "--run", str(tmp / "out" / "run1"), "--archive-dir", str(arch)]) == 0
    rows = list(csv.DictReader(open(tmp / "out" / "run1" / "loeschbar.tsv"), delimiter="\t"))
    assert len(rows) == 1


def test_mixing_feature_sets_refused(job):
    tmp, _, _ = job
    assert _convert(tmp) == 0
    assert _convert(tmp, ["--features", "complete"]) == 2


def test_feature_set_hash_stable():
    from cmjsc import feature_sets
    a, b = feature_sets.load(), feature_sets.load("thalamus_v1")
    assert a["sha256"] == b["sha256"] and a["name"] == "thalamus_v1"


def test_roi_name_parsing():
    from cmjsc.labels import parse_roi
    d = parse_roi("B10_x3781_x900002_x4m_r_trace_2_xorigin_54016_yorigin_1024")
    assert d["OST_label"] == "x4m" and d["trace"] == 2 and d["side"] == "r"


def test_dirty_check_ignores_registry_first_line(monkeypatch):
    from cmjsc import provenance
    monkeypatch.setattr(provenance, "_porcelain", lambda: ["registry/runs.tsv"])
    assert provenance.git_state()["dirty"] is False
    monkeypatch.setattr(provenance, "_porcelain", lambda: ["registry/runs.tsv", "python/x.py"])
    assert provenance.git_state()["dirty"] is True
