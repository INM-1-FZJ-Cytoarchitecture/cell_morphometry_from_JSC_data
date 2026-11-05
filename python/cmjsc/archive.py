"""cmjsc archive: verify archived H5 copies (e.g. on L:) against the manifest."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from . import provenance
from .convert import LEDGER, MANIFEST, MANIFEST_F, VERIF, _read_tsv
from .hashing import sha256_file


def run(args) -> int:
    out_dir = Path(args.run)
    rows = _read_tsv(out_dir / MANIFEST)
    if not rows:
        print(f"no {MANIFEST} in {out_dir}")
        return 2
    adir = Path(args.archive_dir)
    index = {}
    for p in adir.rglob("*.h5"):
        index.setdefault(p.name, []).append(p)
    n_match = n_bad = n_missing = 0
    for r in rows:
        name = Path(r["h5_local_path"]).name
        cands = index.get(name, [])
        if not cands:
            r["archive_status"] = "missing"
            n_missing += 1
            continue
        cand = cands[0]
        if r.get("archive_status") == "match" and r.get("archive_path") == str(cand) and not args.recheck:
            n_match += 1
            continue
        sha = sha256_file(cand)
        r["archive_path"], r["archive_sha256"] = str(cand), sha
        r["archive_checked_at"] = provenance.now()
        r["archive_status"] = "match" if sha == r["sha256"] else "MISMATCH"
        n_match += sha == r["sha256"]
        n_bad += sha != r["sha256"]
        print(f"{r['archive_status']:8s} {name}")
    with open(out_dir / MANIFEST, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, MANIFEST_F, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    led = {r["roi_stem"]: r["status"] for r in _read_tsv(out_dir / LEDGER)}
    ver = {r["roi_stem"]: r["status"] for r in _read_tsv(out_dir / VERIF)}
    deletable = [r for r in rows if r["archive_status"] == "match"
                 and led.get(r["roi_stem"]) == "ok" and ver.get(r["roi_stem"]) == "ok"]
    with open(out_dir / "loeschbar.tsv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter="\t")
        w.writerow(["h5_local_path", "size_bytes", "sha256", "archive_path"])
        for r in deletable:
            w.writerow([r["h5_local_path"], r["size_bytes"], r["sha256"], r["archive_path"]])
    pj = out_dir / "PROVENANCE.json"
    if pj.exists():
        prov = json.load(open(pj, encoding="utf-8"))
        prov.setdefault("archive_checks", []).append({
            "at": provenance.now(), "archive_dir": str(adir), "match": n_match,
            "mismatch": n_bad, "missing": n_missing, "deletable": len(deletable),
            "git": provenance.git_state()})
        provenance.write_json(prov, pj)
        provenance.write_markdown(prov, out_dir / "PROVENANCE.md")
    print(f"archive check: {n_match} match, {n_bad} MISMATCH, {n_missing} missing; "
          f"{len(deletable)} H5 listed in loeschbar.tsv (converted + verified + archived)")
    return 0 if n_bad == 0 else 1
