"""Provenance: software state, environment, inputs."""
from __future__ import annotations

import getpass
import json
import platform
import socket
import subprocess
import sys
from datetime import datetime
from importlib import metadata

from .paths import REPO_DIR

IGNORE_DIRTY = ("registry/",)


def _git(*args) -> str:
    try:
        return subprocess.run(["git", "-C", str(REPO_DIR), *args], capture_output=True,
                              text=True, timeout=30).stdout.strip()
    except Exception:
        return ""


def git_state() -> dict:
    status = _git("status", "--porcelain")
    dirty_files = [l[3:] for l in status.splitlines()
                   if l and not any(l[3:].startswith(p) for p in IGNORE_DIRTY)]
    return {
        "repo": str(REPO_DIR),
        "remote": _git("config", "--get", "remote.origin.url"),
        "commit": _git("rev-parse", "HEAD"),
        "describe": _git("describe", "--tags", "--always", "--dirty"),
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "dirty_files": dirty_files,
        "dirty": bool(dirty_files),
    }


def environment() -> dict:
    pk = {}
    for name in ["numpy", "h5py", "scikit-image", "opencv-python-headless", "tifffile",
                 "imagecodecs", "pandas", "openpyxl", "PyYAML", "cmjsc"]:
        try:
            pk[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            pk[name] = None
    return {"python": sys.version, "executable": sys.executable,
            "platform": platform.platform(), "host": socket.gethostname(),
            "user": getpass.getuser(), "packages": pk}


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def write_json(obj, path):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, ensure_ascii=False, default=str)


def write_markdown(prov: dict, path):
    g, e = prov["software"]["git"], prov["software"]["environment"]
    lines = [
        f"# PROVENANCE – {prov['run_id']}", "",
        f"- Tool: cmjsc {prov['software']['cmjsc_version']} · git {g['describe']} ({g['commit']}) · {g['remote']}",
        f"- Dirty: {g['dirty']} {g['dirty_files'] if g['dirty'] else ''}",
        f"- Python {e['python'].split()[0]} · {e['platform']} · {e['host']} · {e['user']}",
        f"- Command: `{prov['command']}`",
        f"- Started: {prov['started']} · Finished: {prov.get('finished', '-')} · Status: {prov.get('status')}",
        "", "## Inputs",
    ]
    for k, v in prov["inputs"].items():
        lines.append(f"- {k}: {v}")
    lines += ["", "## Segmentation (from JSC job YAML)"]
    for k, v in prov["segmentation"].items():
        lines.append(f"- {k}: {v}")
    lines += ["", "## Parameters"]
    for k, v in prov["parameters"].items():
        lines.append(f"- {k}: {v}")
    if "summary" in prov:
        lines += ["", "## Summary"]
        for k, v in prov["summary"].items():
            lines.append(f"- {k}: {v}")
    lines += ["", "Per-file hashes: `archive_manifest.tsv`; per-ROI checks: `verification.tsv`;"
              " per-ROI status: `cellseg_ledger.tsv`."]
    open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
