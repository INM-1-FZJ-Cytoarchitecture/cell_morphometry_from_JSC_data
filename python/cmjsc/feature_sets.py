"""Central, versioned feature-set definitions (config/feature_sets.yaml)."""
from __future__ import annotations

import json

import yaml

from .hashing import sha256_bytes
from .paths import FEATURE_SETS_FILE

# Fixed output names (cellseg schema). Anything else -> "cell_<raw name>".
RENAME = {
    "area": "cell_area_px",
    "perimeter": "cell_perimeter",
    "eccentricity": "cell_eccentricity",
    "solidity": "cell_solidity",
    "feret_diameter_max": "cell_feret_diameter_max",
    "intensity_mean": "cell_intensity_mean",
    "intensity_std": "cell_intensity_std",
    "scores": "cell_detection_score",
    "region_ids": "region_id",
}


def load(name: str | None = None, path=FEATURE_SETS_FILE) -> dict:
    """Return {'name', 'h5_columns' (list or 'ALL'), 'sha256', 'definition'}."""
    cfg = yaml.safe_load(open(path, encoding="utf-8"))
    name = name or cfg["default"]
    if name not in cfg["sets"]:
        raise ValueError(f"Unknown feature set '{name}'. Known: {', '.join(cfg['sets'])}")
    d = cfg["sets"][name]
    canon = json.dumps({"name": name, **d}, sort_keys=True).encode()
    return {"name": name, "h5_columns": d["h5_columns"], "sha256": sha256_bytes(canon),
            "definition": d, "default": cfg["default"]}
