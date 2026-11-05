"""Contours -> non-overlapping label layers -> CellSegmentations.zip.

Rasterisation rule: skimage.draw.polygon on the CPN contour (a pixel belongs
to a cell when its centre lies inside the polygon). This rule reproduces the
JSC regionprops of J0045 (area, centroid, intensity_mean identical for ~98 %
of cells in a first check; exact agreement is reported per ROI in
verification.tsv). It differs from cellseg's cv2.fillPoly (int-truncated
vertices), which gives ~15 px larger cells than the H5 values.

Zip format = cellseg convention (F:\\GitHub\\cell_segmentation, rasterize.py):
members CellSegmentations_NN.png (16-bit) when every cell_id <= 65535,
otherwise CellSegmentations_NN.tif (32-bit int); 0 = background, pixel value
= cell_id = H5 row index + 1. Overlapping cells go to further layers (greedy:
first layer whose pixels are free).
"""
from __future__ import annotations

import io
import zipfile

import cv2
import numpy as np
from skimage.draw import polygon as _polygon

from .h5io import iter_contours


def rasterize_layers(h5_path, shape, max_layers=64):
    """Return (layers, raster_area, n_empty).

    layers      : list of 2-D arrays (uint16 or uint32), value = cell_id
    raster_area : pixel count per cell (index = cell_id - 1)
    n_empty     : cells whose polygon covers no pixel centre (not in the zip)
    """
    import h5py
    with h5py.File(h5_path, "r") as f:
        n_total = f["contours"].shape[0]
    rows, cols = shape
    dtype = np.uint16 if n_total <= 65535 else np.uint32
    layers: list[np.ndarray] = []
    raster_area = np.zeros(n_total, dtype=np.int64)
    n_empty = 0
    for start, block in iter_contours(h5_path):
        for j, ct in enumerate(block):
            gid = start + j + 1
            rr, cc = _polygon(ct[:, 1], ct[:, 0], shape=(rows, cols))
            if rr.size == 0:
                n_empty += 1
                continue
            raster_area[gid - 1] = rr.size
            for layer in layers:
                if not layer[rr, cc].any():
                    layer[rr, cc] = gid
                    break
            else:
                if len(layers) >= max_layers:
                    raise RuntimeError(f"more than {max_layers} overlap layers needed")
                layer = np.zeros((rows, cols), dtype=dtype)
                layer[rr, cc] = gid
                layers.append(layer)
    return layers, raster_area, n_empty


def write_zip(layers, zip_path) -> dict:
    max_label = max((int(l.max()) for l in layers), default=0)
    use_png = max_label <= 65535
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for i, layer in enumerate(layers):
            if use_png:
                ok, buf = cv2.imencode(".png", layer.astype(np.uint16, copy=False))
                if not ok:
                    raise IOError("PNG encoding failed")
                zf.writestr(f"CellSegmentations_{i:02d}.png", buf.tobytes())
            else:
                import tifffile
                bio = io.BytesIO()
                tifffile.imwrite(bio, layer.astype(np.int32, copy=False), compression="zlib")
                zf.writestr(f"CellSegmentations_{i:02d}.tif", bio.getvalue())
    return {"n_layers": len(layers), "file_format": "zipped PNG" if use_png else "zipped TIFF",
            "bit_depth": 16 if use_png else 32, "max_label": max_label}


def read_zip_counts(zip_path, n_cells) -> tuple[np.ndarray, int]:
    """Round trip: pixel count per cell_id from the written zip, number of layers."""
    counts = np.zeros(n_cells + 1, dtype=np.int64)
    n_layers = 0
    with zipfile.ZipFile(zip_path, "r") as zf:
        for name in sorted(zf.namelist()):
            raw = zf.read(name)
            if name.lower().endswith(".png"):
                arr = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_UNCHANGED)
            else:
                import tifffile
                arr = tifffile.imread(io.BytesIO(raw))
            v = arr[arr > 0].astype(np.int64)
            counts += np.bincount(v, minlength=n_cells + 1)[: n_cells + 1]
            n_layers += 1
    return counts[1:], n_layers


def density_map_coarse(cx, cy, shape, bin_px=20, pixel_size_um=1.0):
    """Cells per mm^2 on a coarse grid (bin_px x bin_px pixels), float32."""
    rows, cols = shape
    nb_r, nb_c = int(np.ceil(rows / bin_px)), int(np.ceil(cols / bin_px))
    r = np.clip((cy // bin_px).astype(int), 0, nb_r - 1)
    c = np.clip((cx // bin_px).astype(int), 0, nb_c - 1)
    m = np.zeros((nb_r, nb_c), np.float32)
    np.add.at(m, (r, c), 1.0)
    area_mm2 = (bin_px * pixel_size_um / 1000.0) ** 2
    return m / area_mm2
