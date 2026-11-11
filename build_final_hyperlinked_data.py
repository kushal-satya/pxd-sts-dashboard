#!/usr/bin/env python3
"""Build a presentation-grade, hyperlinked final dashboard dataset.

Input:
  - dashboard/varieties_complete.json (existing 1940-record dataset)

Outputs:
  - dashboard/final_varieties_hyperlinked.json
  - dashboard/final_varieties_hyperlinked.csv

Adds:
  - crop/state normalization fields for clean filters
  - full query-level click-through URLs (Google/Scholar/NCBI)
  - flattened hyperlink columns for CSV export/sharing
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import quote_plus, urlparse

BASE_DIR = Path(__file__).resolve().parent
INPUT_JSON = BASE_DIR / "varieties_complete.json"
OUTPUT_JSON = BASE_DIR / "final_varieties_hyperlinked.json"
OUTPUT_CSV = BASE_DIR / "final_varieties_hyperlinked.csv"
OUTPUT_LINKS_LONG_CSV = BASE_DIR / "final_varieties_links_long.csv"
OUTPUT_ANALYSIS_JSON = BASE_DIR / "final_varieties_showcase_analysis.json"


STATE_CODE_TO_NAME = {
    "AN": "Andaman and Nicobar Islands",
    "AP": "Andhra Pradesh",
    "AR": "Arunachal Pradesh",
    "AS": "Assam",
    "BR": "Bihar",
    "CG": "Chhattisgarh",
    "CH": "Chandigarh",
    "DD": "Dadra and Nagar Haveli and Daman and Diu",
    "DL": "Delhi",
    "DN": "Dadra and Nagar Haveli and Daman and Diu",
    "GA": "Goa",
    "GJ": "Gujarat",
    "HP": "Himachal Pradesh",
    "HR": "Haryana",
    "JH": "Jharkhand",
    "JK": "Jammu and Kashmir",
    "KA": "Karnataka",
    "KL": "Kerala",
    "LA": "Ladakh",
    "LD": "Lakshadweep",
    "MH": "Maharashtra",
    "ML": "Meghalaya",
    "MN": "Manipur",
    "MP": "Madhya Pradesh",
    "MZ": "Mizoram",
    "NL": "Nagaland",
    "OR": "Odisha",
    "PB": "Punjab",
    "PY": "Puducherry",
    "RJ": "Rajasthan",
    "SK": "Sikkim",
    "TG": "Telangana",
    "TN": "Tamil Nadu",
    "TR": "Tripura",
    "UK": "Uttarakhand",
    "UP": "Uttar Pradesh",
    "WB": "West Bengal",
}

NAME_TO_CODE = {name.lower(): code for code, name in STATE_CODE_TO_NAME.items()}
NAME_TO_CODE.update(
    {
        "uttaranchal": "UK",
        "orissa": "OR",
        "jammu & kashmir": "JK",
        "jammu and kashmir": "JK",
        "nct of delhi": "DL",
        "delhi nct": "DL",
        "pondicherry": "PY",
    }
)

TOKEN_ALIAS = {
    "TS": "TG",
    "TEL": "TG",
    "JAM": "JK",
    "NCT": "DL",
    "NCR": "DL",
    "UTR": "UK",
    "UTT": "UK",
}

CROP_ALIAS = {
    "ground nut": "Groundnut",
    "mung bean": "Mungbean",
    "bread wheat": "Bread Wheat",
    "durum wheat": "Durum Wheat",
    "pearl millet": "Pearl Millet",
    "finger millet": "Finger Millet",
    "black gram": "Black Gram",
    "green gram": "Green Gram",
    "pigeon pea": "Pigeonpea",
    "field pea": "Field Pea",
    "brinjal or eggplant": "Brinjal",
}

DOMAIN_SCORE = {
    "icar.org.in": 120,
    "gov.in": 110,
    "nic.in": 110,
    "edu": 100,
    "ac.in": 100,
    "fao.org": 95,
    "cgiar.org": 95,
    "irri.org": 95,
    "springer.com": 92,
    "sciencedirect.com": 92,
    "nature.com": 92,
    "frontiersin.org": 90,
    "wiley.com": 90,
    "researchgate.net": 86,
    "ncbi.nlm.nih.gov": 95,
    "seednet.gov.in": 120,
}


def normalize_crop(raw: str) -> str:
    value = re.sub(r"\s+", " ", str(raw or "").strip())
    if not value:
        return ""
    alias = CROP_ALIAS.get(value.lower())
    if alias:
        return alias
    return value.title()


def parse_states(record: dict) -> tuple[list[str], list[str]]:
    codes: list[str] = []
    names: list[str] = []

    raw_codes = str(record.get("states_acronyms") or "")
    for token in re.split(r"[,/;|\s]+", raw_codes.upper()):
        token = token.strip()
        if not token:
            continue
        token = TOKEN_ALIAS.get(token, token)
        if token in STATE_CODE_TO_NAME and token not in codes:
            codes.append(token)
            names.append(STATE_CODE_TO_NAME[token])

    raw_full = record.get("states_full") or []
    if isinstance(raw_full, str):
        raw_full = [x.strip() for x in re.split(r"[,;|/]+", raw_full) if x.strip()]

    for state_name in raw_full:
        text = str(state_name).strip()
        if not text:
            continue
        lookup = NAME_TO_CODE.get(text.lower())
        if not lookup and len(text) <= 3 and text.upper() in STATE_CODE_TO_NAME:
            lookup = text.upper()
        if lookup and lookup not in codes:
            codes.append(lookup)
            names.append(STATE_CODE_TO_NAME[lookup])
        elif not lookup:
            title = text.title()
            if title not in names:
                names.append(title)

    return codes, names


def build_query_urls(query: str) -> dict[str, str]:
    encoded = quote_plus(query)
    return {
        "google_url": f"https://www.google.com/search?q={encoded}",
        "scholar_url": f"https://scholar.google.com/scholar?q={encoded}",
        "ncbi_url": f"https://www.ncbi.nlm.nih.gov/search/all/?term={encoded}",
    }


def domain_of(url: str) -> str:
    try:
        return (urlparse(url).netloc or "").lower().replace("www.", "")
    except Exception:
        return ""


def score_url(url: str) -> int:
    domain = domain_of(url)
    score = 30
    for key, val in DOMAIN_SCORE.items():
        if key in domain:
            score = max(score, val)
    # Favor canonical docs/papers over site homepages.
    if url.lower().endswith(".pdf"):
        score += 8
    if any(token in url.lower() for token in ["/article/", "/doi/", "publication", "proceedings"]):
        score += 6
    if any(token in domain for token in ["blogspot", "facebook", "youtube", "twitter", "x.com"]):
        score -= 20
    return max(1, min(score, 150))


def enrich_record(record: dict) -> dict:
    rec = dict(record)
    rec["crop_clean"] = normalize_crop(rec.get("crop"))
    state_codes, state_names = parse_states(rec)
    rec["states_codes_clean"] = state_codes
    rec["states_acronyms_clean"] = ", ".join(state_codes)
    rec["states_full_clean"] = state_names

    query_links: list[dict] = []
    query_results = ((rec.get("search_metadata") or {}).get("query_results") or [])
    for idx, item in enumerate(query_results, start=1):
        query = str((item or {}).get("query") or "").strip()
        if not query:
            continue
        urls = build_query_urls(query)
        query_links.append(
            {
                "idx": idx,
                "query": query,
                "query_type": (item or {}).get("query_type", ""),
                "results_count": int((item or {}).get("results_count") or 0),
                "status": (item or {}).get("status", ""),
                **urls,
            }
        )

    rec["query_links"] = query_links
    rec["query_links_count"] = len(query_links)
    rec["source_links_all"] = sorted(
        {url for q in query_links for url in (q["google_url"], q["scholar_url"], q["ncbi_url"])}
    )

    # Extract actual pulled URLs from nested evidence structures.
    direct_links = extract_direct_links(rec)
    rec["direct_source_links"] = direct_links
    rec["direct_source_links_count"] = len(direct_links)
    rec["trusted_stress_types"] = extract_trusted_stress_types(rec)
    ranked = sorted(
        [{"url": u, "domain": domain_of(u), "score": score_url(u)} for u in direct_links],
        key=lambda x: (-x["score"], x["domain"], x["url"]),
    )
    rec["best_direct_links"] = ranked[:25]
    return rec


def extract_direct_links(record: dict) -> list[str]:
    """Collect real source URLs from nested fields (evidence_sources etc.)."""
    found: set[str] = set()

    def walk(node):
        if isinstance(node, dict):
            for value in node.values():
                walk(value)
            return
        if isinstance(node, list):
            for value in node:
                walk(value)
            return
        if isinstance(node, str):
            text = node.strip()
            if text.startswith(("http://", "https://")):
                found.add(text)

    # Prioritize likely evidence-rich blocks first, then full record fallback.
    rd = record.get("research_data") or {}
    far = rd.get("full_analysis_result") or {}
    walk(far)
    walk(rd)
    walk(record.get("seednet_url"))

    # Filter obvious self-links to search engines generated from queries.
    filtered = [
        u
        for u in sorted(found)
        if "google.com/search?q=" not in u
        and "scholar.google.com/scholar?q=" not in u
        and "ncbi.nlm.nih.gov/search/all/?term=" not in u
    ]
    return filtered


def extract_trusted_stress_types(record: dict) -> list[str]:
    """Derive stress tags only from structured analysis blocks, not query hits."""
    rd = record.get("research_data") or {}
    far = rd.get("full_analysis_result") or {}
    st = far.get("stress_tolerance") or {}
    if not isinstance(st, dict):
        return []

    mapping = {
        "drought": "Drought",
        "heat": "Heat",
        "salinity": "Salt",
        "flood": "Flood",
        "submergence": "Submergence",
        "disease_resistance": "Disease",
        "pest_resistance": "Pest",
    }
    trusted: list[str] = []
    for key, label in mapping.items():
        block = st.get(key) or {}
        if not isinstance(block, dict):
            continue
        level = str(block.get("level", "")).strip().lower()
        summary = str(block.get("summary", "")).strip().lower()
        details = str(block.get("details", "")).strip().lower()
        ev_count = len(block.get("evidence_sources") or [])
        has_signal = (
            (level and level not in {"unknown", "none", "not specified", "na", "n/a"})
            or (summary and summary not in {"unknown", "none", "not specified", "na", "n/a"})
            or (details and details not in {"unknown", "none", "not specified", "na", "n/a"})
            or ev_count > 0
        )
        if has_signal:
            trusted.append(label)
    return sorted(set(trusted))


def write_csv(records: list[dict]) -> None:
    fields = [
        "variety_id",
        "crop",
        "crop_clean",
        "variety_name",
        "year_of_release",
        "stress_tolerance",
        "key_attributes",
        "trusted_stress_types",
        "states_acronyms",
        "states_acronyms_clean",
        "states_full_clean",
        "seasons",
        "days_to_maturity",
        "evidence_quality",
        "seednet_available",
        "seednet_url",
        "seednet_variety_id",
        "query_links_count",
        "direct_source_links_count",
        "google_search_url",
        "scholar_search_url",
        "ncbi_search_url",
        "direct_source_links",
        "best_direct_links",
        "all_query_google_urls",
        "all_query_scholar_urls",
        "all_query_ncbi_urls",
    ]

    with OUTPUT_CSV.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fields)
        writer.writeheader()
        for rec in records:
            default_query = f"{rec.get('variety_name','')} {rec.get('crop_clean','')}".strip()
            seed_urls = build_query_urls(default_query) if default_query else {
                "google_url": "",
                "scholar_url": "",
                "ncbi_url": "",
            }
            links = rec.get("query_links") or []
            writer.writerow(
                {
                    "variety_id": rec.get("variety_id", ""),
                    "crop": rec.get("crop", ""),
                    "crop_clean": rec.get("crop_clean", ""),
                    "variety_name": rec.get("variety_name", ""),
                    "year_of_release": rec.get("year_of_release", ""),
                    "stress_tolerance": rec.get("stress_tolerance", ""),
                    "key_attributes": rec.get("key_attributes", ""),
                    "trusted_stress_types": "|".join(rec.get("trusted_stress_types") or []),
                    "states_acronyms": rec.get("states_acronyms", ""),
                    "states_acronyms_clean": rec.get("states_acronyms_clean", ""),
                    "states_full_clean": " | ".join(rec.get("states_full_clean") or []),
                    "seasons": rec.get("seasons", ""),
                    "days_to_maturity": rec.get("days_to_maturity", ""),
                    "evidence_quality": rec.get("evidence_quality", ""),
                    "seednet_available": rec.get("seednet_available", False),
                    "seednet_url": rec.get("seednet_url", ""),
                    "seednet_variety_id": rec.get("seednet_variety_id", ""),
                    "query_links_count": rec.get("query_links_count", 0),
                    "direct_source_links_count": rec.get("direct_source_links_count", 0),
                    "google_search_url": seed_urls["google_url"],
                    "scholar_search_url": seed_urls["scholar_url"],
                    "ncbi_search_url": seed_urls["ncbi_url"],
                    "direct_source_links": " | ".join(rec.get("direct_source_links") or []),
                    "best_direct_links": " | ".join(x["url"] for x in (rec.get("best_direct_links") or [])),
                    "all_query_google_urls": " | ".join(x["google_url"] for x in links),
                    "all_query_scholar_urls": " | ".join(x["scholar_url"] for x in links),
                    "all_query_ncbi_urls": " | ".join(x["ncbi_url"] for x in links),
                }
            )


def write_links_long(records: list[dict]) -> None:
    """One row per variety-link for deep analysis/showcase."""
    fields = [
        "variety_id",
        "crop",
        "crop_clean",
        "variety_name",
        "year_of_release",
        "states_acronyms_clean",
        "evidence_quality",
        "link_rank",
        "link_score",
        "link_domain",
        "link_url",
    ]
    with OUTPUT_LINKS_LONG_CSV.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fields)
        writer.writeheader()
        for rec in records:
            ranked = sorted(
                [{"url": u, "domain": domain_of(u), "score": score_url(u)} for u in (rec.get("direct_source_links") or [])],
                key=lambda x: (-x["score"], x["domain"], x["url"]),
            )
            for idx, link in enumerate(ranked, start=1):
                writer.writerow(
                    {
                        "variety_id": rec.get("variety_id", ""),
                        "crop": rec.get("crop", ""),
                        "crop_clean": rec.get("crop_clean", ""),
                        "variety_name": rec.get("variety_name", ""),
                        "year_of_release": rec.get("year_of_release", ""),
                        "states_acronyms_clean": rec.get("states_acronyms_clean", ""),
                        "evidence_quality": rec.get("evidence_quality", ""),
                        "link_rank": idx,
                        "link_score": link["score"],
                        "link_domain": link["domain"],
                        "link_url": link["url"],
                    }
                )


def write_analysis(records: list[dict]) -> None:
    """High-level showcase summary so users can present data richness quickly."""
    direct_counts = [int(r.get("direct_source_links_count") or 0) for r in records]
    domain_counter: Counter[str] = Counter()
    crop_counter: Counter[str] = Counter()
    for rec in records:
        crop_counter[str(rec.get("crop_clean") or rec.get("crop") or "Unknown")] += 1
        for url in rec.get("direct_source_links") or []:
            domain = domain_of(url)
            if domain:
                domain_counter[domain] += 1

    analysis = {
        "total_varieties": len(records),
        "total_direct_links": sum(direct_counts),
        "direct_links_stats": {
            "min": min(direct_counts) if direct_counts else 0,
            "max": max(direct_counts) if direct_counts else 0,
            "average": round((sum(direct_counts) / len(direct_counts)), 2) if direct_counts else 0,
            "varieties_with_1_plus": sum(1 for c in direct_counts if c >= 1),
            "varieties_with_10_plus": sum(1 for c in direct_counts if c >= 10),
            "varieties_with_20_plus": sum(1 for c in direct_counts if c >= 20),
        },
        "top_crops_by_variety_count": crop_counter.most_common(25),
        "top_domains_by_link_count": domain_counter.most_common(100),
    }
    OUTPUT_ANALYSIS_JSON.write_text(json.dumps(analysis, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    if not INPUT_JSON.exists():
        raise FileNotFoundError(f"Missing input JSON: {INPUT_JSON}")

    records = json.loads(INPUT_JSON.read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise ValueError("Input JSON is not an array.")

    final = [enrich_record(r) for r in records]
    OUTPUT_JSON.write_text(
        json.dumps(final, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    write_csv(final)
    write_links_long(final)
    write_analysis(final)

    print(f"Input records: {len(records)}")
    print(f"Wrote JSON: {OUTPUT_JSON}")
    print(f"Wrote CSV:  {OUTPUT_CSV}")
    print(f"Wrote links long CSV: {OUTPUT_LINKS_LONG_CSV}")
    print(f"Wrote analysis JSON:  {OUTPUT_ANALYSIS_JSON}")


if __name__ == "__main__":
    main()
