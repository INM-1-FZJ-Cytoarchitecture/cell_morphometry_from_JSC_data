"""Run registry (registry/runs.tsv in this repo) and affected-run check."""
from __future__ import annotations

import csv
import subprocess

from .paths import KNOWN_ISSUES_FILE, REGISTRY_FILE, REPO_DIR

FIELDS = ["run_id", "date", "tool", "project", "job", "out_dir", "h5_dir", "git_commit",
          "git_describe", "feature_set", "feature_set_sha256", "n_rois_ok", "n_rois_error", "notes"]


def append(row: dict, path=REGISTRY_FILE):
    with open(path, "a", newline="", encoding="utf-8") as fh:
        csv.DictWriter(fh, FIELDS, delimiter="\t", extrasaction="ignore").writerow(row)


def read(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def _is_ancestor(a, b) -> bool:
    """True if commit a is an ancestor of (or equal to) commit b."""
    r = subprocess.run(["git", "-C", str(REPO_DIR), "merge-base", "--is-ancestor", a, b],
                       capture_output=True)
    return r.returncode == 0


def affected_runs(registry=REGISTRY_FILE, issues=KNOWN_ISSUES_FILE):
    """Runs whose commit contains an issue's introducing commit but not its fix."""
    out = []
    runs = read(registry)
    for iss in read(issues):
        intro, fix = iss.get("introduced_commit", ""), iss.get("fixed_commit", "")
        for r in runs:
            c = r.get("git_commit", "")
            if not c:
                continue
            has_bug = (not intro) or _is_ancestor(intro, c)
            has_fix = bool(fix) and _is_ancestor(fix, c)
            if has_bug and not has_fix:
                out.append({**iss, **{"run_id": r["run_id"], "project": r["project"],
                                      "out_dir": r["out_dir"], "run_commit": c}})
    return out
