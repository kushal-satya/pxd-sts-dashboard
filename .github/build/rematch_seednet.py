#!/usr/bin/env python3
"""rematch_seednet.py - strict, deterministic CSC -> Seednet matching (replaces the July-2025 fuzzy match).

A CSC variety is linked to a Seednet entry only when match_rules.classify() says confirmed_exact / confirmed_spelling:
same crop, and the same name (ignoring punctuation and parenthetical codes, or equal to one of the codes Seednet lists
in parentheses, e.g. "Gujarat Junagadh Groundnut 9" = "Gujarat Junagadh Groundnut 9 (GJG-9) (J-69)").
2026-11: the status is ALWAYS classify()'s verdict (a looked-up candidate is never forced to confirmed_exact); a non-confirmed
best candidate is still returned (with its status and reason) so the build can keep it as a reviewable candidate. When the
names differ only by a generic word of the crop ('Sahbhagi Dhan' / 'SAHBHAGI') and exactly one Seednet entry of that crop has
that name, the link is confirmed_spelling with reason 'crop word dropped'.
Output: JSON {csc_key: {"status":..., "reason":..., "seednet": {...Seednet row...}}} for every CSC variety, csc_key = "<crop lower>|<name alnum lower>".

Usage: python rematch_seednet.py --master <master.xlsx|csv> --seednet <seednet_data.csv> --out seednet_rematch.json
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from match_rules import CONFIRMED, _norm, _strip_paren, classify_reason, crop_word_variant, fix_brackets  # noqa: E402
from standardize import standardize_crop  # noqa: E402

NA = ("", "nan", "none", "not specified", "unknown", "0")


def csc_key(crop, name) -> str:
    """One key per CSC variety: canonical crop + alphanumeric name (so 'ground nut' / 'groundnut' and 'GJG - 18' / 'GJG-18' are one variety)."""
    return f"{standardize_crop(crop).lower()}|{_norm(name)}"


def name_keys(name) -> set[str]:
    """All normalised forms under which a variety name can be looked up: full, without parentheses, each parenthetical code,
    and each side of a '/' alias."""
    name = re.sub(r"\s+", " ", str(name or "")).strip()
    name = fix_brackets(name)
    keys = {_norm(name), _norm(_strip_paren(name))} | {_norm(p) for p in re.findall(r"\(([^)]*)\)", name)}
    for part in re.split(r"/|\bor\b", _strip_paren(name)): keys.add(_norm(part))
    keys.add(_norm(name.split("(")[0]))  # Seednet names with an unbalanced parenthesis
    return {k for k in keys if len(k) >= 3}


def build_index(seednet_rows: list[dict]) -> dict:
    idx = collections.defaultdict(list)
    for row in seednet_rows:
        crop = standardize_crop(row.get("Crop Name"))
        for k in name_keys(row.get("Variety Name")): idx[(crop, k)].append(row)
        # crop-word index: Seednet name core, and the core without a generic word of its crop
        core = _norm(_strip_paren(row.get("Variety Name")))
        if core: idx[("#core", crop, core)].append(row)
        cw = _norm(crop_word_variant(row.get("Variety Name"), crop))
        if cw: idx[("#core", crop, cw)].append(row)
    return idx


def richness(row: dict) -> int: return sum(1 for v in row.values() if v is not None and str(v).strip().lower() not in NA and str(v).strip().lower() != "not specified")


def best_match(csc_name, csc_crop, idx) -> tuple[str, dict | None]:
    st, row, _ = best_match_reason(csc_name, csc_crop, idx); return st, row


_RANK = {"confirmed_exact": 0, "confirmed_spelling": 1, "same_name_crop_conflict": 2, "different_variety": 3}


def best_match_reason(csc_name, csc_crop, idx) -> tuple[str, dict | None, str]:
    crop = standardize_crop(csc_crop); cands = []
    for k in name_keys(csc_name): cands += idx.get((crop, k), [])
    seen, uniq = set(), []
    for c in cands:
        if id(c) not in seen: seen.add(id(c)); uniq.append(c)
    graded = [(classify_reason(csc_name, csc_crop, c.get("Variety Name"), c.get("Crop Name")), c) for c in uniq]
    good = [(sr, c) for sr, c in graded if sr[0] in CONFIRMED]
    if good:
        (st, why), row = min(good, key=lambda g: (_RANK[g[0][0]], -richness(g[1])))
        return st, row, why
    # crop word dropped: 'Sahbhagi Dhan' (CSC) = 'SAHBHAGI' (Seednet), only when exactly one Seednet variety of the crop has that name
    for form in {_norm(crop_word_variant(csc_name, crop)), _norm(_strip_paren(csc_name))} - {""}:
        hits = idx.get(("#core", crop, form), [])
        names = {_norm(_strip_paren(h.get("Variety Name"))) for h in hits}
        if hits and len(names) == 1 and (form != _norm(_strip_paren(csc_name)) or crop_word_variant(hits[0].get("Variety Name"), crop)):
            if not _digits_equal(csc_name, hits[0].get("Variety Name")): continue
            return "confirmed_spelling", max(hits, key=richness), "crop word dropped"
    if graded:
        (st, why), row = min(graded, key=lambda g: (_RANK.get(g[0][0], 9), -richness(g[1])))
        return st, row, why
    return "no_seednet", None, "no Seednet entry with this name in this crop"


def _digits_equal(a, b) -> bool:
    """The digits of the CSC name must all appear, in order, at the start of the Seednet name's digits or in one of its
    parenthetical codes; stops 'Groundnut 9' matching 'Groundnut 19'."""
    da = [d.lstrip("0") or "0" for d in re.findall(r"\d+", _strip_paren(a))]
    forms = [_strip_paren(b), str(b or "").split("(")[0]] + re.findall(r"\(([^)]*)\)", str(b or ""))
    return any(da == [d.lstrip("0") or "0" for d in re.findall(r"\d+", f)] for f in forms) or _norm(a) == _norm(b)


def main() -> int:
    import pandas as pd
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--master", required=True, type=Path); ap.add_argument("--seednet", required=True, type=Path); ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args()
    df = pd.read_excel(a.master) if a.master.suffix.lower() in (".xlsx", ".xls") else pd.read_csv(a.master, low_memory=False)
    sn = pd.read_csv(a.seednet, low_memory=False, dtype=str).fillna("")
    sn["Variety Name"] = sn["Variety Name"].str.replace(r"\s+", " ", regex=True).str.strip()
    rows = sn.to_dict("records"); idx = build_index(rows); out = {}; c = collections.Counter()
    for crop, name in zip(df["crop"], df["variety_name"]):
        k = csc_key(crop, name)
        if k in out or not _norm(name): continue
        st, row, why = best_match_reason(name, crop, idx); c[st] += 1
        if why == "crop word dropped": c["crop_word_dropped"] += 1
        out[k] = {"status": st, "reason": why, "seednet": row}
    a.out.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"{len(out)} CSC varieties: {dict(c)} -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
