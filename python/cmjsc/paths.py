"""Repository paths (CMJSC_REGISTRY overrides the registry file, used by tests)."""
import os
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent
REPO_DIR = PKG_DIR.parent.parent
CONFIG_DIR = REPO_DIR / "config"
REGISTRY_FILE = Path(os.environ.get("CMJSC_REGISTRY", REPO_DIR / "registry" / "runs.tsv"))
KNOWN_ISSUES_FILE = REPO_DIR / "known_issues.tsv"
FEATURE_SETS_FILE = CONFIG_DIR / "feature_sets.yaml"


MASK_SUFFIXES = ("_mask.tif", "_special_trace_mask.tif")


def resolve_mask(mask_dir, stem):
    """RegionAnnotation mask of a ROI as written by JBA_TA: <stem>_mask.tif, or
    <stem>_special_trace_mask.tif for a special trace (KI-003). Returns the first
    existing file, else the default name (which then does not exist)."""
    mask_dir = Path(mask_dir)
    for suf in MASK_SUFFIXES:
        cand = mask_dir / f"{stem}{suf}"
        if cand.exists():
            return cand
    return mask_dir / f"{stem}{MASK_SUFFIXES[0]}"
