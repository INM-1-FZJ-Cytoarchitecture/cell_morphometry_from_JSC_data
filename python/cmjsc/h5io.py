"""Reading JSC celldetection-inference(-masked) H5 files.

Observed layout (J0045, 2026-11): root attrs complete (bool), num_detections;
datasets of length N in the same row order: contours (N,224,2) float32 with
[:,:,0]=x (col) and [:,:,1]=y (row); skimage regionprops (raw values, e.g.
area, centroid-0/1, bbox-0..3, perimeter, ...); scores (N,); region_ids (N,);
uncertainties (N,4). The row index i is the cell identity (cell_id = i+1);
the 'label' dataset is constant (regionprops on one-cell masks) and ignored.
"""
from __future__ import annotations

import h5py
import numpy as np

REQUIRED = ("contours", "centroid-0", "centroid-1", "area")


class H5FormatError(Exception):
    pass


def inspect(path) -> dict:
    with h5py.File(path, "r") as f:
        attrs = {k: (v.item() if hasattr(v, "item") else v) for k, v in f.attrs.items()}
        missing = [k for k in REQUIRED if k not in f]
        if missing:
            raise H5FormatError(f"missing datasets: {missing}")
        n = f["contours"].shape[0]
        lens = {k: f[k].shape[0] for k in f if isinstance(f[k], h5py.Dataset)}
        bad = {k: v for k, v in lens.items() if v != n}
        if bad:
            raise H5FormatError(f"datasets with length != {n}: {bad}")
        if "num_detections" in attrs and int(attrs["num_detections"]) != n:
            raise H5FormatError(f"num_detections={attrs['num_detections']} != {n}")
        scalars = [k for k in f if isinstance(f[k], h5py.Dataset) and f[k].ndim == 1]
        return {"n": n, "attrs": attrs, "complete": bool(attrs.get("complete", False)),
                "scalar_datasets": sorted(scalars),
                "has_uncertainties": "uncertainties" in f}


def read_columns(path, columns) -> dict:
    """Read 1-D datasets (and 'uncertainties-k' pseudo columns)."""
    out = {}
    with h5py.File(path, "r") as f:
        for c in columns:
            if c.startswith("uncertainties-"):
                k = int(c.split("-")[1])
                out[c] = f["uncertainties"][:, k]
            else:
                out[c] = f[c][()]
    return out


def iter_contours(path, chunk=50000):
    with h5py.File(path, "r") as f:
        ds = f["contours"]
        n = ds.shape[0]
        for s in range(0, n, chunk):
            yield s, np.asarray(ds[s:min(n, s + chunk)], dtype=np.float64)
