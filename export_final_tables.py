#!/usr/bin/env python3
"""export_final_tables.py - flat CSV + Excel workbook of the final dashboard dataset for analysts.

Sheets / files:
  varieties        one row per variety: identity, Seednet fields, stress levels (evidence-based + legacy), breeder,
                   institution, contacts, publication counts, evidence URL count, enrichment wave, model, links
  stress_evidence  one row per (variety, stress): level, details, evidence URLs
  publications     one row per publication mention (Scholar 2025 + OpenAlex)
  contacts         one row per variety with breeder / institution / contacts / publications text
  data_dictionary  the field dictionary (if data_dictionary.csv is given)
Usage: python export_final_tables.py <final_varieties_hyperlinked.json> <out_dir> [--dictionary data_dictionary.csv]"""
import argparse
import json
import re
from pathlib import Path

import pandas as pd


def urls(lst) -> list[str]:
    out = []
    for u in lst or []:
        if isinstance(u, str): out.append(u)
        elif isinstance(u, dict): out.append(str(u.get("url") or u.get("link") or json.dumps(u, ensure_ascii=False)))
        else: out.append(str(u))
    return out

def _flat(x) -> str:
    """genetics_and_qtl block as one readable cell: 'key: value; key: value'."""
    if not x: return ""
    if isinstance(x, dict): return "; ".join(f"{k}: {_flat(v)}" for k, v in x.items() if v not in (None, "", [], {}) and k != "evidence_sources")
    if isinstance(x, list): return ", ".join(_flat(v) for v in x)
    return str(x)


GENETICS_FIELDS = ("genetic_markers", "qtl_information", "molecular_mechanisms", "genes_introgressed", "parentage_and_pedigree", "breeding_line_designations", "breeding_method", "genome_resources")
KEEP_EVEN_IF_EMPTY = {"record_id", "legacy_id", "variety_id", "record_source", "crop", "variety_name", "year_of_release", "csc_minutes_url", "csc_minutes_archived_url", "csc_minutes_link_basis"}
PHONE_COLS = ("phones", "fax", "institution_phones", "institution_fax", "phone_notes")


def iso_date(v):
    """'06/12/2016' (Seednet, day first) -> '2016-12-06'; anything else unchanged."""
    import re as _re
    m = _re.fullmatch(r"\s*(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\s*", str(v or ""))
    return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}" if m and 1 <= int(m.group(2)) <= 12 and 1 <= int(m.group(1)) <= 31 else v


SEEDNET_ORDER = ("Group Name", "Crop Name", "Variety Name", "Notification Number", "Notification Date", "State Central Variety", "Year of Release",
                 "Institution Responsible for developing Breeder Seed", "Parentage", "Resemblence to Variety", "Adaptation and recommended ecology", "Maturity (in days)",
                 "Agronomic Features", "Seed Rate (Kg/Ha)", "Specific Morphological Characteristics", "General Morphological Characteristics", "Reaction to Stress",
                 "Reaction to Major Diseases", "Reaction to Major Pests", "Average Yield (Kg/Ha)", "Spacing (in Cms)", "Fertiliser Dosage (Kg/Ha)", "Recommended States",
                 "source_url", "variety_id")


def _col(k: str) -> str: return re.sub(r"[^a-z0-9]+", "_", str(k).lower()).strip("_")


def extra_sheets(recs):
    """The rest of the JSON as sheets: Seednet record, CSC record, research text, sources (long), rejected Seednet entry, official stress text."""
    SN, CR, RT, SO, NU, OT = [], [], [], [], [], []
    for r in recs:
        base = {"record_id": r.get("record_id"), "crop": r.get("crop_clean"), "variety_name": r.get("variety_name")}
        sf = r.get("seednet_fields") or {}
        if sf:
            row = dict(base); row.update({"seednet_" + _col(k): sf.get(k) for k in SEEDNET_ORDER})
            row.update({"seednet_" + _col(k): v for k, v in sf.items() if k not in SEEDNET_ORDER and k not in ("variety_name",)})
            row["seednet_match_status"] = r.get("seednet_match_status"); row["seednet_match_reason"] = r.get("seednet_match_reason"); SN.append(row)
        cf = r.get("csc_fields") or {}; os_ = r.get("official_sources") or {}
        if cf:
            row = dict(base); row.update({"csc_" + _col(k): v for k, v in cf.items()})
            row.update(csc_outcome=r.get("csc_outcome"), csc_minutes_url=os_.get("csc_minutes_url"), csc_minutes_archived_url=os_.get("csc_minutes_archived_url"),
                       csc_minutes_link_basis=os_.get("csc_minutes_link_basis"), csc_minutes_list_page=os_.get("csc_minutes_list_page"),
                       developer_institution_csc=r.get("developer_institution_csc"), developer_location_csc=r.get("developer_location_csc"))
            CR.append(row)
        far = (r.get("research_data") or {}).get("full_analysis_result") or {}
        if isinstance(far, dict) and far:
            row = dict(base)
            for sec, keys in (("agronomic_performance", ("yield", "stability", "adaptation", "maturity_days", "plant_characteristics", "field_trials")),
                              ("genetics_and_qtl", ("genetic_markers", "qtl_information", "molecular_mechanisms", "genes_introgressed", "parentage_and_pedigree",
                                                    "breeding_line_designations", "breeding_method", "genome_resources")),
                              ("breeder_and_contacts", ("breeder", "institution", "contacts", "publications")),
                              ("commercial_availability", ("seed_corporations", "kvk", "private_dealers", "availability_status"))):
                blk = far.get(sec) if isinstance(far.get(sec), dict) else {}
                for k in keys: row[f"{sec}_{k}"] = blk.get(k)
            st = far.get("stress_tolerance") if isinstance(far.get("stress_tolerance"), dict) else {}
            for k in ("disease_resistance", "pest_resistance"): row[f"{k}_summary"] = (st.get(k) or {}).get("summary") if isinstance(st.get(k), dict) else None
            for k in ("drought", "heat", "salinity", "flood", "submergence"): row[f"{k}_details_research"] = (st.get(k) or {}).get("details") if isinstance(st.get(k), dict) else None
            pm = far.get("processing_metadata") or {}
            row.update(research_wave=r.get("enrichment_wave"), research_analysis_date=pm.get("analysis_date"), research_model=pm.get("model"), research_processing_version=pm.get("processing_version"),
                       research_refers_to=r.get("research_refers_to"))
            RT.append(row)
            for sec, blk in far.items():
                if isinstance(blk, dict):
                    for u in urls(blk.get("evidence_sources")): SO.append({**base, "section": sec, "url": u})
                    for k, sub in blk.items():
                        if isinstance(sub, dict):
                            for u in urls(sub.get("evidence_sources")): SO.append({**base, "section": f"{sec}.{k}", "url": u})
            for u in urls(far.get("reference_links")): SO.append({**base, "section": "reference_links", "url": u})
        for k in ("seednet_url", "csc_minutes_url", "csc_minutes_archived_url", "csc_minutes_list_page"):
            if os_.get(k): SO.append({**base, "section": "official_sources." + k, "url": os_[k]})
        for u in urls((r.get("contacts_structured") or {}).get("contact_source_urls")): SO.append({**base, "section": "contacts", "url": u})
        for u in urls((r.get("institution_contact") or {}).get("source_urls")): SO.append({**base, "section": "institution_contact", "url": u})
        for u in urls(r.get("direct_source_links")): SO.append({**base, "section": "direct_source_links (2025 search)", "url": u})
        cand = r.get("seednet_candidate") or {}
        if cand:
            cf2 = r.get("seednet_candidate_fields") or {}
            NU.append({**base, "seednet_match_status": r.get("seednet_match_status"), "reason": cand.get("reason") or r.get("seednet_match_reason"),
                       "seednet_name": cand.get("variety_name"), "seednet_crop": cand.get("crop"), "seednet_year_of_release": cf2.get("Year of Release"),
                       "seednet_url": cand.get("url"), "seednet_institution": cf2.get("Institution Responsible for developing Breeder Seed")})
        for k, t in (r.get("stress_official_text") or {}).items():
            OT.append({**base, "stress": k, "field": t.get("field"), "quote": t.get("quote"), "stress_confirmation_level": r.get("stress_confirmation_level")})
    return SN, CR, RT, SO, NU, OT


def resistance_rows(recs):
    """Long sheet: one row per record and disease / pest, with the basis and the quoted official clause or the research summary."""
    out = []
    for r in recs:
        base = {"record_id": r.get("record_id"), "crop": r.get("crop_clean"), "variety_name": r.get("variety_name")}
        for kind, key, lst in (("disease", "disease_resistance", "diseases"), ("pest", "pest_resistance", "pests")):
            blk = r.get(key) or {}
            off, res = set(blk.get("official") or []), set(blk.get("research") or [])
            for n in blk.get(lst) or []:
                basis = "both" if n in off and n in res else "official text" if n in off else "research"
                q = blk.get("official_quote") or {}
                out.append({**base, "kind": kind, "name": n, "basis": basis, "official_field": q.get("field") if n in off else "",
                            "official_quote": q.get("quote") if n in off else "", "research_summary": blk.get("research_summary") if n in res else "",
                            "research_sources": " | ".join(blk.get("sources") or []) if n in res else ""})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("final", type=Path); ap.add_argument("out", type=Path); ap.add_argument("--dictionary", type=Path)
    a = ap.parse_args(); a.out.mkdir(parents=True, exist_ok=True)
    recs = json.loads(a.final.read_text(encoding="utf-8"))
    V, S, P, C = [], [], [], []
    for r in recs:
        sf = r.get("seednet_fields") or {}; rd = r.get("research_data") or {}; far = rd.get("full_analysis_result") or {}
        st = far.get("stress_tolerance") if isinstance(far, dict) else {}; st = st if isinstance(st, dict) else {}
        bc = far.get("breeder_and_contacts") if isinstance(far, dict) else {}; bc = bc if isinstance(bc, dict) else {}
        ag = far.get("agronomic_performance") if isinstance(far, dict) else {}; ag = ag if isinstance(ag, dict) else {}
        lv = r.get("stress_levels_gemini") or {}; cf = r.get("csc_fields") or {}
        gq = far.get("genetics_and_qtl") if isinstance(far, dict) else None
        url_set = {u for blk in st.values() if isinstance(blk, dict) for u in urls(blk.get("evidence_sources"))}
        os_ = r.get("official_sources") or {}; cand = r.get("seednet_candidate") or {}; lvl = r.get("stress_confirmation_level")
        gen = {f"genetics_{k}": (gq or {}).get(k) for k in GENETICS_FIELDS} if isinstance(gq, dict) else {f"genetics_{k}": None for k in GENETICS_FIELDS}
        V.append({"record_id": r.get("record_id"), "legacy_id": r.get("legacy_id") or r["variety_id"], "record_source": r.get("record_source"), "name_quality": r.get("name_quality"),
                  "variety_name_as_printed": r.get("variety_name_as_printed"), "name_correction_basis": "; ".join(r.get("name_correction_basis") or []),
                  "related_record_ids": "; ".join(r.get("related_record_ids") or []), "stress_text_available": r.get("stress_text_available"),
                  "stress_official_text_types": ", ".join(sorted((r.get("stress_official_text") or {}).keys())),
                  "has_disease_resistance": r.get("has_disease_resistance"), "disease_resistance_basis": r.get("disease_resistance_basis"),
                  "diseases_resisted": "; ".join((r.get("disease_resistance") or {}).get("diseases") or []),
                  "has_pest_resistance": r.get("has_pest_resistance"), "pest_resistance_basis": r.get("pest_resistance_basis"),
                  "pests_resisted": "; ".join((r.get("pest_resistance") or {}).get("pests") or []),
                  "yield_kg_ha_min": r.get("yield_kg_ha_min"), "yield_kg_ha_max": r.get("yield_kg_ha_max"), "yield_text": r.get("yield_text"),
                  "yield_class": r.get("yield_class"), "high_yield_stated_officially": r.get("high_yield_stated_officially"),
                  "search_names": "; ".join(r.get("search_names") or []),
                  "stress_tolerance_confirmed": "Yes" if lvl in ("Confirmed by 2+ sources", "Single source") else "No" if lvl in ("None found", "Claimed, not confirmed") else "",
                  "stress_basis": r.get("stress_basis"), "stress_level_adjusted_by_rules": r.get("stress_level_adjusted"),
                  "seednet_match_reason": r.get("seednet_match_reason"), "seednet_candidate_reason": cand.get("reason"), "seednet_merged_ids": "; ".join(r.get("seednet_merged_ids") or []),
                  "year_of_release_raw": r.get("year_of_release_raw"), "csc_minutes_url": os_.get("csc_minutes_url"), "csc_minutes_archived_url": os_.get("csc_minutes_archived_url"),
                  "csc_minutes_link_basis": os_.get("csc_minutes_link_basis"), "institution_contact_check": r.get("institution_contact_check"),
                  "publications_scholar_total": r.get("publications_scholar_total"), "publications_openalex_total": r.get("publications_openalex_total"), **gen,
                  "variety_id": r["variety_id"], "crop": r.get("crop_clean") or r.get("crop"), "variety_name": r.get("variety_name"), "seednet_variety_name": sf.get("Variety Name"),
                  "year_of_release": r.get("year_of_release"), "seednet_year_of_release": sf.get("Year of Release"), "notification_number": sf.get("Notification Number"), "notification_date": iso_date(sf.get("Notification Date")),
                  "central_or_state": sf.get("State Central Variety"), "recommended_states": r.get("states_acronyms_clean"), "recommended_states_full": "; ".join(r.get("states_full_clean") or []),
                  "institution_seednet": sf.get("Institution Responsible for developing Breeder Seed"), "institution_csc_minutes": r.get("developer_institution_csc"), "institution_location_csc_minutes": r.get("developer_location_csc"), "parentage": sf.get("Parentage"), "maturity_days_seednet": sf.get("Maturity (in days)"),
                  "average_yield_seednet": sf.get("Average Yield (Kg/Ha)"), "reaction_to_stress_seednet": sf.get("Reaction to Stress"),
                  "legacy_2025_model_stress_tolerance": r.get("stress_tolerance_strict"), "legacy_2025_model_stress_types": ", ".join(r.get("stress_types_strict") or []),
                  "legacy_2025_model_level_drought": lv.get("drought"), "legacy_2025_model_level_heat": lv.get("heat"), "legacy_2025_model_level_salinity": lv.get("salinity"),
                  "legacy_2025_model_level_flood": lv.get("flood"), "legacy_2025_model_level_submergence": lv.get("submergence"),
                  "legacy_2025_query_hit_stress_tolerance": r.get("stress_tolerance"), "legacy_2025_query_hit_stress_types": ", ".join(r.get("stress_types") or []), "legacy_2025_evidence_quality": r.get("evidence_quality"),
                  "breeder": bc.get("breeder"), "institution_research": bc.get("institution"), "contact_details": bc.get("contacts"), "publications_text": bc.get("publications"),
                  "field_trials": ag.get("field_trials"), "yield_research": ag.get("yield"),
                  "publications_scholar_count": r.get("publications_scholar_count", 0), "publications_openalex_count": r.get("publications_openalex_count", 0),
                  "evidence_urls_count": len(url_set), "enrichment_wave": r.get("enrichment_wave"), "analysis_model": (far.get("processing_metadata") or {}).get("model") if isinstance(far, dict) else None,
                  "gemini_analysis_status": r.get("gemini_analysis_status"), "seednet_url": r.get("seednet_url"), "seednet_code": r.get("seednet_variety_id"),
                  "csc_source_document": (r.get("official_sources") or {}).get("csc_source_document"), "csc_meeting": (r.get("official_sources") or {}).get("csc_meeting"),
                  "gazette_reference": (r.get("official_sources") or {}).get("gazette_reference"),
                  "institution_contact_name": (r.get("institution_contact") or {}).get("institution_official_name"), "institution_website": (r.get("institution_contact") or {}).get("website"),
                  "institution_emails": "; ".join((r.get("institution_contact") or {}).get("emails") or []), "institution_phones": "; ".join((r.get("institution_contact") or {}).get("phones") or []),
                  "institution_address": (r.get("institution_contact") or {}).get("postal_address"), "institution_contact_sources": " | ".join((r.get("institution_contact") or {}).get("source_urls") or []),
                  "csc_outcome": r.get("csc_outcome"), "research_status": "official data only" if r.get("enrichment_wave") == "not_researched" else "researched",
                  "seednet_match_status": r.get("seednet_match_status"), "seednet_link_corrected_2026": r.get("seednet_rematched"),
                  "seednet_nearest_different_variety": (r.get("seednet_candidate") or {}).get("variety_name"), "seednet_nearest_different_crop": (r.get("seednet_candidate") or {}).get("crop"),
                  "stress_confirmation_level": r.get("stress_confirmation_level"), "stress_types_confirmed": ", ".join(r.get("stress_types_confirmed") or []),
                  "stress_types_confirmed_2plus_sources": ", ".join(r.get("stress_types_multi_source") or []), "research_refers_to": r.get("research_refers_to"), "stress_confirmation_note": r.get("stress_confirmation_note"),
 "parentage_or_parent_material_csc": cf.get("parent_material"), "breeding_method_csc": cf.get("breeding_method"),
                  "special_traits_csc": cf.get("special_traits"), "approval_status_csc": cf.get("approval_status"), "principal_investigator_csc": cf.get("principal_investigator"),
                  "csc_meeting_number": cf.get("meeting_number"), "csc_page_reference": cf.get("page_reference"), "csc_minutes_list_page": (r.get("official_sources") or {}).get("csc_minutes_list_page"),
                  "merged_duplicate_ids": "; ".join(r.get("merged_duplicate_ids") or []), "merged_duplicate_names": "; ".join(r.get("merged_duplicate_names") or []),
                  "crop_as_printed": r.get("crop_raw"), "states_as_printed": "; ".join(str(x) for x in (r.get("states_full_raw") or [])),
                  "developer_institution_csc_as_printed": r.get("developer_institution_csc_raw"),
                  "legacy_2025_days_to_maturity": r.get("days_to_maturity"), "legacy_2025_key_attributes": r.get("key_attributes")})
        sc = r.get("stress_confirmation") or {}
        for k, blk in st.items():
            if isinstance(blk, dict):
                c = sc.get(k) or {}
                S.append({"record_id": r.get("record_id"), "variety_id": r["variety_id"], "crop": r.get("crop_clean"), "variety_name": r.get("variety_name"), "stress": k, "level": blk.get("level"), "summary_or_details": blk.get("details") or blk.get("summary"), "evidence_urls": " | ".join(urls(blk.get("evidence_sources"))),
                          "confirmation": c.get("label"), "confirmation_verdict": c.get("verdict"), "confirmation_verdict_model": c.get("verdict_model"), "verdict_adjusted_reason": c.get("verdict_adjusted_reason"), "independent_sources": c.get("independent_sources"), "official_support": c.get("official_support"), "research_support": c.get("research_support"), "confirmation_basis": c.get("basis")})
        for w in r.get("publications_scholar") or []:
            P.append({"record_id": r.get("record_id"), "crop": r.get("crop_clean"), "variety_name": r.get("variety_name"), "variety_id": r["variety_id"], "source": "google_scholar_2025", "title": w.get("title"), "authors_venue_year": w.get("publication_info"), "year": None, "doi_or_link": w.get("link"), "cited_by": w.get("cited_by"), "matched_on": w.get("matched_on")})
        for w in r.get("publications_openalex") or []:
            P.append({"record_id": r.get("record_id"), "crop": r.get("crop_clean"), "variety_name": r.get("variety_name"), "variety_id": r["variety_id"], "source": "openalex", "title": w.get("title"), "authors_venue_year": " - ".join(x for x in (", ".join(w.get("authors") or []), w.get("venue") or "") if x), "year": w.get("year"), "doi_or_link": w.get("doi") or w.get("landing_page"), "cited_by": w.get("cited_by_count"), "matched_on": w.get("matched_on")})
        ic = r.get("institution_contact") or {}; cs = r.get("contacts_structured") or {}
        C.append({"record_id": r.get("record_id"), "variety_id": r["variety_id"], "record_source": r.get("record_source"), "breeder_names": "; ".join(cs.get("breeder_names") or []), "emails": "; ".join(cs.get("emails") or []), "phones": "; ".join(cs.get("phones") or []),
                  "fax": "; ".join(cs.get("fax") or []), "phone_notes": "; ".join(cs.get("phone_notes") or []), "institution_contact_check": r.get("institution_contact_check"), "addresses": "; ".join(cs.get("addresses") or []), "institution_std": cs.get("institution"), "website": cs.get("website"), "contact_page": cs.get("contact_page"), "institution_type": cs.get("institution_type"), "head_or_director": cs.get("head_or_director"), "variety_or_seed_contact": cs.get("variety_or_seed_contact"), "breeder_seed_institution_seednet": cs.get("breeder_seed_institution_seednet"), "principal_investigator_csc": (r.get("csc_fields") or {}).get("principal_investigator"), "crop": r.get("crop_clean") or r.get("crop"), "variety_name": r.get("variety_name"), "breeder": bc.get("breeder"), "institution": bc.get("institution"), "institution_csc_minutes": r.get("developer_institution_csc"), "institution_location_csc_minutes": r.get("developer_location_csc"), "contacts": bc.get("contacts"), "publications": bc.get("publications"), "evidence_urls": " | ".join(urls(bc.get("evidence_sources"))),
                  "institution_official_name": ic.get("institution_official_name"), "institution_website": ic.get("website"), "institution_contact_page": ic.get("contact_page"), "institution_emails": "; ".join(ic.get("emails") or []), "institution_phones": "; ".join(ic.get("phones") or []), "institution_fax": "; ".join(ic.get("fax") or []), "institution_address": ic.get("postal_address"), "institution_head": ic.get("head_or_director"), "institution_seed_contact": ic.get("variety_or_seed_contact"), "institution_sources": " | ".join(ic.get("source_urls") or []),
                  "seednet_url": r.get("seednet_url"), "csc_source_document": (r.get("official_sources") or {}).get("csc_source_document")})
    SN, CR, RT, SO, NU, OT = extra_sheets(recs)
    dfs = {"varieties": pd.DataFrame(V), "stress_evidence": pd.DataFrame(S), "publications": pd.DataFrame(P), "contacts": pd.DataFrame(C),
           "seednet_record": pd.DataFrame(SN), "csc_record": pd.DataFrame(CR), "research_text": pd.DataFrame(RT), "sources": pd.DataFrame(SO),
           "seednet_not_used": pd.DataFrame(NU), "official_stress_text": pd.DataFrame(OT), "disease_pest_resistance": pd.DataFrame(resistance_rows(recs))}
    for name in list(dfs):  # record_id, crop, variety_name lead every sheet
        df = dfs[name]
        if df.empty: continue
        lead = [c for c in ("record_id", "crop", "variety_name") if c in df.columns]
        dfs[name] = df[lead + [c for c in df.columns if c not in lead]]
    front = ["record_id", "crop", "variety_name", "variety_name_as_printed", "name_correction_basis", "legacy_id", "variety_id", "record_source", "name_quality", "search_names", "year_of_release", "year_of_release_raw", "csc_outcome",
             "seednet_match_status", "seednet_match_reason", "stress_confirmation_level", "stress_tolerance_confirmed", "stress_types_confirmed", "stress_types_confirmed_2plus_sources"]
    v = dfs["varieties"]; dfs["varieties"] = v[[c for c in front if c in v.columns] + [c for c in v.columns if c not in front]]
    if a.dictionary and a.dictionary.exists(): dfs["data_dictionary"] = pd.read_csv(a.dictionary)
    import re as _re
    ph = _re.compile(r"^\s*(unknown|not specified.*|not found.*|not available.*|n/?a|nan|none|null|not stated.*|not mentioned.*|no information.*|-+|—)\s*\.?\s*$", _re.IGNORECASE)
    for name, df in dfs.items():  # blank means "not stated" in every table
        if name == "data_dictionary": continue
        for c in df.columns:
            if df[c].dtype == object and not c.endswith("_level"): df[c] = df[c].map(lambda v: "" if isinstance(v, str) and ph.match(v) else v)
    dropped_cols = {}
    for name in list(dfs):
        if name == "data_dictionary": continue
        df = dfs[name]
        drop = [c for c in df.columns if c not in KEEP_EVEN_IF_EMPTY and df[c].map(lambda v: "" if v is None or (isinstance(v, float) and v != v) else str(v)).nunique() <= 1]
        df = df.drop(columns=drop); dropped_cols[name] = drop
        legacy = [c for c in df.columns if c.startswith("legacy_2025_")]
        dfs[name] = df[[c for c in df.columns if c not in legacy] + legacy]
    for name, df in dfs.items():
        d = df.copy()
        for c in d.columns:  # CSV: a leading '+' makes spreadsheet programs read a phone number as a formula; the CSV writes '91-...' (the JSON and xlsx keep '+91-')
            if c in PHONE_COLS: d[c] = d[c].map(lambda v: "; ".join(x.strip()[1:] if x.strip().startswith("+") else x.strip() for x in str(v).split(";")) if isinstance(v, str) and v else v)
        d.to_csv(a.out / f"STS_India_{name}.csv", index=False, encoding="utf-8-sig")
    from openpyxl.utils import get_column_letter
    with pd.ExcelWriter(a.out / "STS_India_varieties_FINAL.xlsx", engine="openpyxl") as xw:
        for name, df in dfs.items():
            d = df.copy()
            cut_cols = []
            for c in d.columns:
                if d[c].dtype == object:
                    s_ = d[c].astype(str).replace({"None": "", "nan": ""})
                    if (s_.str.len() > 32000).any(): cut_cols.append(c)
                    d[c] = s_.str.slice(0, 32000)
            if cut_cols:  # Excel cell limit: the CSV keeps the whole text
                d["xlsx_cells_cut_at_32000_chars"] = [", ".join(c for c in cut_cols if len(str(df.iloc[i][c] or "")) > 32000) for i in range(len(df))]
            d.to_excel(xw, sheet_name=name[:31], index=False)
            ws = xw.sheets[name[:31]]
            text_cols = [i + 1 for i, c in enumerate(d.columns) if d[c].dtype == object]
            for ci in text_cols:  # every text column is a TEXT cell: Excel keeps '+91-...', leading zeros and long codes as written
                col = get_column_letter(ci)
                for cell in ws[col][1:]:
                    cell.number_format = "@"
                    if isinstance(cell.value, str) and cell.value.startswith("="): cell.data_type = "s"  # never a formula
    print("dropped empty/constant columns:", {k: v for k, v in dropped_cols.items() if v})
    print({k: len(v) for k, v in dfs.items()}, "->", a.out)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
