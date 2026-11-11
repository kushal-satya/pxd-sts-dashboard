#!/usr/bin/env python3
"""reshard.py - split a built final_varieties_hyperlinked.json into the parts the dashboard loads (no network, no API).

  python dashboard/reshard.py <final_varieties_hyperlinked.json> <dashboard folder> [--parts 6]

Writes <dashboard folder>/data/final_varieties_hyperlinked.partN.json and data/index.json. The dashboard reads
data/index.json first, so copying a new final JSON next to index.html without re-sharding has no visible effect.
Windows / macOS / Linux."""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("final", type=Path); ap.add_argument("dashboard", type=Path); ap.add_argument("--parts", type=int, default=6)
    a = ap.parse_args()
    records = json.loads(a.final.read_text(encoding="utf-8"))
    if not isinstance(records, list):
        print("ERROR: expected a JSON array of records"); return 2
    data = a.dashboard / "data"; data.mkdir(parents=True, exist_ok=True)
    n = max(1, a.parts); size = max(1, math.ceil(len(records) / n)); parts = []
    for i in range(n):
        chunk = records[i * size:(i + 1) * size]
        if not chunk:
            break
        rel = f"data/final_varieties_hyperlinked.part{i + 1}.json"
        (a.dashboard / rel).write_text(json.dumps(chunk, ensure_ascii=False), encoding="utf-8"); parts.append(rel)
    built = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M")
    (data / "index.json").write_text(json.dumps({"parts": parts, "records": len(records), "built": built}), encoding="utf-8")
    print(f"resharded {len(records)} records into {len(parts)} parts in {data}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
