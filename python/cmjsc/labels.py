"""ROI names, exclude list and brain table -> one label row per ROI."""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

ROI_RE = re.compile(
    r"^(?P<brain_id>[A-Za-z]+\d+)_(?P<section_number>x\d+)_(?P<OST_id>x\d+)_"
    r"(?P<OST_label>[^_]+)_(?P<side>[lr])_trace_(?P<trace>\d+)_"
    r"xorigin_(?P<x_origin>-?\d+)_yorigin_(?P<y_origin>-?\d+)$")

KEY = ["brain_id", "section_number", "OST_id", "OST_label", "side", "trace"]


def parse_roi(stem: str) -> dict:
    m = ROI_RE.match(stem)
    if not m:
        raise ValueError(f"ROI name does not match the JBA_TA schema: {stem}")
    d = m.groupdict()
    d["trace"] = int(d["trace"])
    d["x_origin"] = int(d["x_origin"])
    d["y_origin"] = int(d["y_origin"])
    return d


def read_exclude_list(path) -> pd.DataFrame:
    df = pd.read_excel(path, dtype=str)
    need = {"brain_id", "section_number", "OST_label", "OST_id", "side", "trace", "include_row"}
    miss = need - set(df.columns)
    if miss:
        raise ValueError(f"exclude list lacks columns {sorted(miss)}: {path}")
    df["trace"] = df["trace"].astype(float).astype(int)
    df["include_row"] = df["include_row"].astype(float).astype(int)
    return df


def read_brains(path) -> pd.DataFrame | None:
    if not path:
        return None
    b = pd.read_csv(path, sep="\t", dtype=str)
    return b


def build_label_table(roi_stems, exclude_list=None, brains_tsv=None) -> pd.DataFrame:
    rows = [{"roi_stem": s, **parse_roi(s)} for s in roi_stems]
    L = pd.DataFrame(rows)
    if L.empty:
        return L
    if exclude_list is not None:
        E = read_exclude_list(exclude_list)
        cols = [c for c in ["brain_pm", "trace_type", "special_trace", "include_row"] if c in E.columns]
        E = E[KEY + cols].drop_duplicates(subset=KEY)
        L = L.merge(E, on=KEY, how="left", validate="many_to_one")
        L["in_exclude_list"] = L["include_row"].notna()
        L["include_row"] = L["include_row"].fillna(-1).astype(int)
    if brains_tsv:
        B = read_brains(brains_tsv)
        bcol = "b_code_OST" if "b_code_OST" in B.columns else B.columns[1]
        B = B.rename(columns={bcol: "brain_id"})
        keep = [c for c in ["brain_id", "pm_id", "sub_id"] if c in B.columns]
        L = L.merge(B[keep], on="brain_id", how="left")
    return L
