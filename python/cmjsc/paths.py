"""Repository paths (CMJSC_REGISTRY overrides the registry file, used by tests)."""
import os
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent
REPO_DIR = PKG_DIR.parent.parent
CONFIG_DIR = REPO_DIR / "config"
REGISTRY_FILE = Path(os.environ.get("CMJSC_REGISTRY", REPO_DIR / "registry" / "runs.tsv"))
KNOWN_ISSUES_FILE = REPO_DIR / "known_issues.tsv"
FEATURE_SETS_FILE = CONFIG_DIR / "feature_sets.yaml"
