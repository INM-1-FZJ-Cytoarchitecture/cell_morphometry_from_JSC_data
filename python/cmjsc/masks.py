"""RegionAnnotation masks (JBA_TA) read with the same semantics as MATLAB.

JBA_TA writes regular masks (<roi>_mask.tif) as 1-bit TIFF with
PhotometricInterpretation = WhiteIsZero. MATLAB honours it (true = annotation);
tifffile returns the raw bits, in which the annotation is 0. Reading them
naively inverts the region (JBA_TA found_issues I-023, cmjsc KI-005).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import tifffile


def read_mask(path) -> np.ndarray:
    """Boolean mask, True = annotation, honouring the TIFF photometric."""
    with tifffile.TiffFile(str(path)) as tf:
        page = tf.pages[0]
        a = page.asarray()
        white_is_zero = page.photometric == tifffile.PHOTOMETRIC.MINISWHITE
    a = np.squeeze(a)
    if a.ndim > 2:
        a = a[..., 0]
    return (a == 0) if white_is_zero else (a > 0)


def frac_inside(mask: np.ndarray, x_px, y_px) -> float:
    """Fraction of points (skimage centroids, 0-based x = column, y = row) in the mask."""
    x = np.asarray(x_px, dtype=float)
    y = np.asarray(y_px, dtype=float)
    ok = np.isfinite(x) & np.isfinite(y)
    if not ok.any():
        return float("nan")
    r = np.clip(np.rint(y[ok]).astype(np.int64), 0, mask.shape[0] - 1)
    c = np.clip(np.rint(x[ok]).astype(np.int64), 0, mask.shape[1] - 1)
    return float(mask[r, c].mean())


def check_cells_in_mask(mask_file, x_px, y_px, min_in_mask: float) -> tuple[float, bool]:
    """(fraction inside, passed). A missing mask or zero cells pass with NaN."""
    if mask_file is None or not Path(mask_file).exists() or len(x_px) == 0:
        return float("nan"), True
    f = frac_inside(read_mask(mask_file), x_px, y_px)
    return f, (not np.isfinite(f)) or f >= min_in_mask
