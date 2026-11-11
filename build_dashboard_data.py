#!/usr/bin/env python3
"""Corrected, cross-platform dashboard data build (replaces running
build_enhanced_data.py + duplicate_varieties.py + build_final_hyperlinked_data.py by hand).

What it fixes versus the Aug-2025 build:
  1. Reads batch files with os.listdir + pathlib (glob.glob breaks on folder names that
     contain [ ] such as "_PROJECT_HANDOVER_[2026-04-27]").
  2. Skips malformed/legacy files instead of silently dropping or crashing.
  3. De-duplicates variety_id (the interrupted/restarted Aug-2025 run wrote 60 ids twice or
     three times): keeps the record whose Gemini analysis succeeded, then the latest timestamp.
  4. Refuses synthetic records (variety_id containing "_DUP_") and NEVER pads the dataset.
  5. Prints and writes a build_report.json with every count so the result can be verified.

Usage:
  python build_dashboard_data.py --input-dir <enhanced_data dir> --output-dir <dashboard dir>
Outputs in --output-dir: varieties_complete.json, varieties_compiled_enhanced.csv,
  final_varieties_hyperlinked.json/.csv, final_varieties_links_long.csv,
  final_varieties_showcase_analysis.json, build_report.json
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_enhanced_data as bed  # original per-record logic, unchanged
import build_final_hyperlinked_data as bfh  # original hyperlink enrichment, unchanged


def load_batches(input_dir: Path, report: dict) -> list[dict]:
    files = sorted(f for f in os.listdir(input_dir) if f.startswith("enhanced_batch_") and f.endswith(".json"))
    skipped = sorted(f for f in os.listdir(input_dir) if f.endswith(".json") and f not in files)
    records, malformed = [], []
    for fn in files:
        text = (input_dir / fn).read_text(encoding="utf-8").replace("NaN", "null")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            malformed.append(f"{fn}: {e}"); continue
        if not isinstance(data, list):
            malformed.append(f"{fn}: top-level is {type(data).__name__}, expected list"); continue
        for r in data:
            r["_source_file"] = fn
        records.extend(data)
    report.update(batch_files=len(files), batch_files_list=files, ignored_non_batch_files=skipped,
                  malformed_batch_files=malformed, raw_records=len(records))
    return records


def analysis_ok(r: dict) -> bool:
    a = r.get("analysis_result")
    return isinstance(a, dict) and "error" not in a and bool(a)


CSC_LIST_PAGE = "https://seednet.gov.in/Material/CSC.aspx"  # Government of India page listing the CSC meeting minutes (the PDFs named in csc_source_document); URL from the 2025 downloader's config
POSITIVE_LEVELS = {"high", "medium", "tolerant", "highly tolerant", "moderate", "moderately tolerant",
                   "medium to high", "moderately resistant", "resistant"}
STRESS_LABELS = {"drought": "Drought", "heat": "Heat", "salinity": "Salt", "flood": "Flood", "submergence": "Submergence"}

def add_strict_stress_fields(rec: dict) -> dict:
    """stress_levels_gemini / stress_types_strict / stress_tolerance_strict: taken ONLY from the Gemini
    analysis 'level' value per stress (not from whether a Google query returned hits, which is what the
    legacy stress_types / stress_tolerance / trusted_stress_types fields do). Blank level -> 'unknown'."""
    far = (rec.get("research_data") or {}).get("full_analysis_result") or {}
    st = far.get("stress_tolerance") if isinstance(far, dict) else None
    levels, strict = {}, []
    for key, label in STRESS_LABELS.items():
        block = st.get(key) if isinstance(st, dict) else None
        lvl = str(block.get("level", "")).strip().lower() if isinstance(block, dict) else ""
        levels[key] = lvl or "unknown"
        if lvl in POSITIVE_LEVELS: strict.append(label)
    rec["stress_levels_gemini"] = levels
    rec["stress_types_strict"] = strict
    rec["stress_tolerance_strict"] = "Yes" if strict else ("Unknown" if not isinstance(st, dict) else "No")
    rec["gemini_analysis_status"] = "ok" if isinstance(st, dict) else "error"
    return rec


NA_VALUES = ("", "nan", "nat", "none", "not specified", "not available", "unknown", "n/a", "na", "not specified in document")
CSC_KEEP = ("crop", "variety_name", "variety_code", "year", "approval_date", "approval_status", "meeting_number", "meeting_title", "source_document_filename", "page_reference",
            "institution", "institution_location", "principal_investigator", "collaborating_institutions", "state_zone", "agro_climatic_zones", "special_traits", "temperature_tolerance",
            "rainfall_requirements", "soil_type_suitability", "parent_material", "breeding_method", "maturity_group", "yield_performance", "quality_parameters", "disease_resistance",
            "pest_tolerance", "additional_notes", "gazette_notification_reference", "similarity_score", "manual_match", "manual_review_status", "csc_raw_id",
            "extraction_timestamp")
CONFIRMATION_LABEL = {"confirmed_multi_source": "Confirmed by 2+ sources", "single_source": "Single source"}


# ---------------------------------------------------------------- contacts (2026-11 data review): blank, split, re-label or drop; never invent
_FAX = re.compile(r"\bfax\b|telefax", re.IGNORECASE)


def clean_phones(values) -> tuple[list[str], list[str], list[str]]:
    """Raw phone strings -> (phones, fax, phone_notes). Each value is split on / , ; 'to' 'or' 'and'; labels and bracketed roles go to
    phone_notes; numbers marked fax go to fax. Kept: 10-digit Indian numbers (after removing +91 / 0091 / 091 / 0 trunk prefix), written
    '+91-<STD>-<number>' when the source separated the STD code, else '+91-<10 digits>'; toll-free numbers '1800-...'; a local number
    written after a full number in the same value ('0422-6611215 / 2451370') gets that number's STD code when the digits then add up to 10.
    A range suffix ('2672080-90', '275536/37/38') keeps the first number. Dropped: extensions, fragments under 6 digits, ISBN-like and
    concatenated strings that are not one number. De-duplicated by the last 10 digits."""
    phones, fax, notes, seen = [], [], [], set()
    for v in values or []:
        v = str(v or "")
        is_fax = bool(_FAX.search(v)) and not re.search(r"\btel\b|phone|\bo\)", v, re.IGNORECASE) or bool(re.search(r"\(\s*fax\s*\)|^\s*fax", v, re.IGNORECASE))
        roles = [x.strip() for x in re.findall(r"\(([^)]*[A-Za-z][^)]*)\)", v) if x.strip() and not re.fullmatch(r"(?i)o|0|off|office|r|res|m|mob|fax|telefax|tel", x.strip())]
        body = re.sub(r"\([^)]*[A-Za-z][^)]*\)|\(\s*0\s*\)", " ", v)
        body = re.sub(r"(?i)\b(phone|tel(?:ephone)?|telefax|fax|mob(?:ile)?|ph|epabx|epbx|extn?\.?\s*[:\-]*\s*\d+|ext[:\-\s]*\d+|office|off|toll ?free|helpline|o)\b\s*[:.\-]*", " ", body)
        body = re.sub(r"(\d{6,8})\s*-\s*\d{1,3}\b(?!\s*-?\d)", r"\1", body)  # '2672080-90' -> '2672080'
        last_std = ""
        for part in re.split(r"[/,;]|\bto\b|\bor\b|\band\b", body):
            raw = part.strip()
            dg = re.sub(r"\D", "", raw)
            if not dg: continue
            if dg.startswith("1800") and 10 <= len(dg) <= 11:
                out = f"1800-{dg[4:7]}-{dg[7:]}"
                if dg not in seen: seen.add(dg); (fax if is_fax else phones).append(out)
                continue
            if dg.startswith("0091"): dg = dg[4:]
            elif dg.startswith("0910") and len(dg) == 14: dg = dg[4:]
            elif len(dg) == 13 and dg.startswith("910"): dg = dg[3:]
            elif len(dg) == 12 and dg.startswith("91"): dg = dg[2:]
            elif len(dg) == 11 and dg.startswith("0"): dg = dg[1:]
            m = re.match(r"^\s*(?:\+?\s*91[\s\-]*|0091[\s\-]*)?\(?\s*0?(\d{2,5})\s*(?:\)\s*[\-–]?\s*|[\s\-–]+)(\d[\d\s]{4,8}\d)\s*$", raw)
            if 6 <= len(dg) <= 8 and last_std and len(last_std) + len(dg) == 10:
                m = None; out = f"+91-{last_std}-{dg}"; dg = last_std + dg
            elif len(dg) != 10 or dg[0] == "0":
                continue
            elif m and len(m.group(1)) + len(re.sub(r"\D", "", m.group(2))) == 10:
                out = f"+91-{m.group(1)}-{re.sub(r'\D', '', m.group(2))}"; last_std = m.group(1)
            else:
                out = f"+91-{dg}"
            if dg in seen: continue
            seen.add(dg)
            (fax if is_fax else phones).append(out)
            for role in roles: notes.append(f"{out}: {role}")
    return phones, fax, notes


_EMAIL_OK = re.compile(r"^[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}$")
_EMAIL_FIND = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_EMAIL_DROP = re.compile(r"^(webmaster|web\.?admin|tech\.?support|journal|editor|noreply|no-reply|donotreply|do-not-reply|info@wix)|"
                         r"@(example|domain|sentry|wixpress)\.|\.(png|jpe?g|gif|svg|webp)$", re.IGNORECASE)


def clean_emails(values) -> list[str]:
    """'[at]' / '(at)' / ' at ' -> '@', '[dot]' -> '.', spaces around '@' removed, every address found in the value kept (so
    'Dr X (AICRP-Rice): name@icar.gov.in' keeps the address), lower case, de-duplicated. Dropped only: website-maintenance and
    publisher addresses (webmaster@, webadmin@, tech.support@, journal@, editor@, no-reply@) and image / placeholder strings.
    Office addresses such as admin@ / hoadmin@ / jd_admin@ are kept."""
    out = []
    for e in values or []:
        t = str(e or "").strip()
        t = re.sub(r"\s*[\[(]\s*at\s*[\])]\s*", "@", t, flags=re.IGNORECASE)
        t = re.sub(r"\s*[\[(]\s*dot\s*[\])]\s*", ".", t, flags=re.IGNORECASE)
        t = re.sub(r"\s*@\s*", "@", t)
        for f in _EMAIL_FIND.findall(t):
            f = f.strip(" .,;:'\"<>()[]").lower()
            if _EMAIL_OK.match(f) and not _EMAIL_DROP.search(f) and f not in out: out.append(f)
    return out


_PERSON = re.compile(r"^(?:(?:Dr|Prof|Mr|Mrs|Ms|Shri|Smt|Er)\.?\s+)*(?:[A-Z][A-Za-z'\-]*\.?\s*){1,6}$")
_NOT_PERSON = re.compile(r"\b(not|no|found|available|specified|unknown|identified|named|evidence|sources?|search|results?|digest|team|university|institute|station|"
                         r"centre|center|department|division|college|research|scientists?|breeders?|genetics|listed|profile|associated|lead|programme|program|icar|aicrp|"
                         r"variety|varieties|developed|released|record|the|of|in|is|are|was|by|with|for|from|and|pvt|ltd|seeds?|result_\d+)\b", re.IGNORECASE)


def person_names(values) -> tuple[list[str], list[str]]:
    """breeder_names -> (person-like names, other text). A kept value looks like a name: up to 6 capitalised words or initials,
    optional Dr/Prof, at most 45 characters, none of the words that mark prose ('not found', 'team', 'university'...).
    Comma-separated lists are split when every piece is a name. 'Not found' texts are dropped entirely."""
    keep, other = [], []
    for v in values or []:
        t = re.sub(r"\s+", " ", str(v or "")).strip(" ;,.")
        if not t: continue
        def isname(x): return bool(x) and bool(_PERSON.match(x)) and not _NOT_PERSON.search(x) and len(x) <= 45 and bool(re.search(r"[a-z]{2,}|[A-Z]{3,}", x))
        if re.search(r"not (found|identified|available|specified|named|mentioned|given|stated)|no (evidence|information|specific)|^unknown", t, re.IGNORECASE) and not isname(t):
            continue  # 'Lead breeder name: Not found in searched sources.' is not data
        if isname(t):
            if t not in keep: keep.append(t)
            continue
        pieces = [x.strip(" ;,.") for x in re.split(r",|;|\band\b|\(", t)]
        all_names = all(isname(x) for x in pieces if x)
        rest = []
        for x in pieces:
            if isname(x) and (all_names or len(re.findall(r"[A-Za-z]+", x)) >= 2):
                if x not in keep: keep.append(x)
            elif x: rest.append(x)
        if rest: other.append(t)
    return keep[:8], other


# ---------------------------------------------------------------- institution contacts (2026-11, second pass)
_RESEARCH_INST_BAD = re.compile(r"not (explicitly )?(stated|specified|found|available|named|given)|inferred|probable|conflict|unverified|evidence is|"
                                r"name-matched|attribution only|various|sponsoring", re.IGNORECASE)
_CONTACT_KEYS = ("institution_official_name", "type", "website", "contact_page", "emails", "phones", "postal_address", "head_or_director", "variety_or_seed_contact", "source_urls", "confidence")


def _has_contact_data(ic: dict) -> bool:
    return bool(ic) and "error" not in ic and any(ic.get(k) not in (None, "", [], "[]") for k in ("emails", "phones", "postal_address", "website", "contact_page"))


class InstitutionIndex:
    """The institution-contact table plus a name index, so a developer can be matched by key (as before) or, when the key gives no
    agreeing contact, by its distinctive words / acronyms (an alias table built only from names present in the table and the records)."""
    def __init__(self, inst: dict, skip, canon):
        from standardize import _acronyms, _letters, _place_words, institution_states, institution_tokens
        self.inst, self.skip, self.canon, self.places = inst, skip, canon, _place_words()
        self.feat, self.by_tok = {}, {}
        for k, ic in inst.items():
            if not _has_contact_data(ic) or _generic_inst_key(k): continue
            name = str(ic.get("institution_official_name") or "").strip() or k
            addr = str(ic.get("postal_address") or "")
            from standardize import _with_former
            f = (_with_former(institution_tokens(name) | _acronyms(name)), institution_tokens(addr), institution_states(name + " ; " + addr), _letters(name), name)
            self.feat[k] = f
            for t in f[0] | f[1]: self.by_tok.setdefault(t, set()).add(k)

    def keys_for(self, texts) -> list[str]:
        out = []
        for t in texts:
            if not t or str(t).strip().lower() in self.skip: continue
            for seg in [str(t)] + re.split(r"[,;/\n]", str(t)):
                k = self.canon(seg)
                if len(k) >= 4 and not _generic_inst_key(k) and k in self.inst and k not in out: out.append(k)
        return out

    def search(self, dev: str):
        """Best contact entry by name. Score: shared acronym with the entry's NAME 2, shared distinctive name word 1, shared place word 0.5,
        a word shared only with the entry's address 0.5. Accepted when the score is >= 2 and at least one non-place word or acronym is shared
        with the NAME. Several entries with the top score are accepted only when they are units of one institution (they share that word);
        the entry with the shortest name (the institution itself) is used. A state conflict excludes an entry."""
        from standardize import _MULTI_INSTITUTE_TOWNS, STATES, _acronyms, _letters, _with_former, institution_states, institution_tokens
        a = _with_former(institution_tokens(dev) | _acronyms(dev)); sa = institution_states(dev); la = _letters(dev); acr = _with_former(_acronyms(dev))
        towns = {x for x in a if x in self.places and x not in _MULTI_INSTITUTE_TOWNS and x not in {y.lower() for y in STATES} and len(x) >= 5}
        caps = {w.lower() for w in re.findall(r"\b[A-Z]{3,7}\b", dev)}
        cands = set()
        for t in a: cands |= self.by_tok.get(t, set())
        scored = []
        for k in sorted(cands):
            nm, ad, sb, lb, name = self.feat[k]
            if sa and sb and not (sa & sb): continue
            sn = a & nm
            core = {x for x in sn if x not in self.places or x in towns}
            core |= {x for x in (acr | nm) - sn if len(x) >= 4 and x.isalpha() and x in la and x in lb and x not in self.places and (x in acr or x in caps or x in nm)}
            if not core: continue
            sc = sum(2 if (x in acr or x in caps or x in towns or (x in nm and len(x) <= 7 and x not in institution_tokens(name.lower()))) else 0.5 if x in self.places else 1 for x in sn)
            sc += 2 * len(core - sn) + 0.5 * len((a & ad) - sn)
            if sc >= 2: scored.append((sc, k, frozenset(core)))
        if not scored: return None, ""
        unit = re.compile(r"^\s*(?:division|department|dept|centre|center|section|unit)\b", re.IGNORECASE)
        dev_unit = bool(re.search(r"\b(?:division|department|dept|centre|center|section)\b", dev, re.IGNORECASE))
        scored.sort(key=lambda t: (-t[0], (not dev_unit) and bool(unit.search(self.feat[t[1]][4])), len(self.feat[t[1]][4]), t[1]))  # the institution, not one of its divisions
        best_sc, best_k, best_core = scored[0]
        tied = [t for t in scored[1:] if t[0] == best_sc]
        fam = {x for x in self.feat[best_k][0] if x not in self.places}
        if tied and not all((t[2] & best_core) or ({x for x in self.feat[t[1]][0] if x not in self.places} & fam) for t in tied):
            return None, f"ambiguous by name ({self.feat[best_k][4][:60]} / {self.feat[tied[0][1]][4][:60]})"
        return best_k, f"matched by name (score {best_sc:g}): " + ", ".join(sorted(best_core)[:3])


def assign_institution_contact(r: dict, sf: dict, bc: dict, ix: InstitutionIndex) -> None:
    """Attach the contact of the institution that developed the variety, never another institution's.
    1. Developer text = CSC developer institution + location + Seednet breeder-seed institution; when these name nothing, the research
       text's institution (unless it is a guess: 'not stated', 'inferred', 'probable' ...), with a leading 'Developing institution:' label removed.
    2. Lookup keys from each of those texts AND each comma/slash segment ('DEPARTMENT OF PLANT BREEDING, CCS HAU, HISSAR' -> 'ccs hau');
       the first key whose contact agrees with the developer text (standardize.institution_agrees) is used.
    3. Otherwise the table is searched by distinctive words / acronyms (InstitutionIndex.search).
    A table entry without any email, phone, address or website is 'no contact found', not a rejection."""
    from standardize import _acronyms, institution_agrees, institution_tokens
    official = [x for x in (r.get("developer_institution_csc"), r.get("developer_location_csc"), sf.get("Institution Responsible for developing Breeder Seed")) if x and str(x).strip().lower() not in ix.skip]
    research = str(bc.get("institution") or "").strip()
    research = re.sub(r"^[^:]{0,40}:\s*", "", research) if ":" in research[:42] else research
    research = "" if (not research or _RESEARCH_INST_BAD.search(research) or research.lower() in ix.skip) else research
    dev = " ; ".join(str(x) for x in official)
    used_research = False
    if not (institution_tokens(dev) | _acronyms(dev)) and research: dev = (dev + " ; " + research).strip(" ;"); used_research = True
    r["institution_contact"] = None
    keys = ix.keys_for([sf.get("Institution Responsible for developing Breeder Seed"), r.get("developer_institution_csc")] + ([research] if research else []))
    tried_reject = ""
    for k in keys:
        ic = ix.inst.get(k) or {}
        if not _has_contact_data(ic): continue
        agree, why = institution_agrees(dev, f"{ic.get('institution_official_name') or k} ; {ic.get('postal_address') or ''} ; {ic.get('website') or ''}")
        if agree:
            r["institution_contact"] = {kk: ic.get(kk) for kk in _CONTACT_KEYS}
            r["institution_contact_check"] = "accepted: " + why + (" (developer named only in the research text)" if used_research else ""); return
        tried_reject = tried_reject or f"rejected {ic.get('institution_official_name') or k}: {why}"
    if dev and (institution_tokens(dev) | _acronyms(dev)):
        k, why = ix.search(dev)
        if k:
            ic = ix.inst[k]
            r["institution_contact"] = {kk: ic.get(kk) for kk in _CONTACT_KEYS}
            r["institution_contact_check"] = "accepted: " + why + (" (developer named only in the research text)" if used_research else ""); return
        if why: tried_reject = tried_reject or "rejected: " + why
    r["institution_contact_check"] = tried_reject.replace("rejected ", "rejected: ", 1) if tried_reject.startswith("rejected ") else (tried_reject or ("no contact found" if keys or dev else "no lookup key"))


# ---------------------------------------------------------------- stress stated in the OFFICIAL text (Seednet / CSC minutes), by rule
OFFICIAL_STRESS_FIELDS = (("seednet", "Reaction to Stress"), ("seednet", "Adaptation and recommended ecology"), ("seednet", "Agronomic Features"),
                          ("csc", "special_traits"), ("csc", "temperature_tolerance"), ("csc", "additional_notes"))
_STRESS_TERMS = {
    "drought": r"drought|moisture[\s-]*stress|water[\s-]*stress|moisture[\s-]*defici\w*|water[\s-]*defici\w*|low[\s-]*moisture|limited[\s-]*moisture",
    "heat": r"heat|high[\s-]*temperatures?|terminal[\s-]*heat|thermo[\s-]*tolerant|thermo[\s-]*tolerance",
    "salinity": r"salt|saline|salinity|sodic|sodicity|alkali|alkaline|alkalinity|usar",
    "flood": r"flash[\s-]*floods?|floods?|flooding|water[\s-]*logg?ing|water[\s-]*logged|water[\s-]*stagnation|stagnant[\s-]*(?:water|flooding)|deep[\s-]*water",
    "submergence": r"submergence|submerged|flash[\s-]*floods?",
}
_TOL_WORD = r"toleran\w*|tolerat\w*|resistan\w*|withstand\w*|withsatand\w*|can\s+stand|thermo[\s-]*tolerant|suitable\s+for|suited\s+(?:to|for)|adapted\s+to|recommended\s+for|torerant"
_NEG = re.compile(r"\b(?:not|cannot|can't|no|nor|non|susceptib\w*|sensitive|does\s+not|poor|escape\w*|avoid\w*|normal|irrigated\s+(?:conditions?|situation)\s+only|"
                  r"likely|may\s+be|probably|as\s+other|like\s+other|like\s+most\s+other|as\s+in\s+other|similar\s+to\s+other|not\s+specified|not\s+evaluated|not\s+tested)\b", re.IGNORECASE)
_CLAUSE_VOID = re.compile(r"not\s+relevant|not\s+applicable|not\s+specified|not\s+evaluated|not\s+tested|like\s+(?:most\s+)?other|as\s+(?:in\s+)?other|similar\s+to\s+other|"
                          r"as\s+compared\s+to\s+(?:gram|other\s+crops?)", re.IGNORECASE)
_PLACEHOLDER_TEXT = re.compile(r"^\s*(?:nil|none|na|n/?a|not\s+applicable|not\s+specified|not\s+evaluated|not\s+available|-+|\.)\s*\.?\s*$", re.IGNORECASE)


def official_stress_tags(r: dict) -> tuple[dict, bool]:
    """Tag a stress from the official fields only when a tolerance word and the stress term stand in the same clause, at most 8 words apart:
    'TOLERANT TO WATER LOGGING' -> flood; 'Tolerates 10 days flash floods' -> flood + submergence; 'salt tolerant' -> salinity.
    A clause with a negation, susceptibility, hedge or crop-generic comparison never tags ('Cannot withstand submerged condition',
    'likely to possess drought tolerance', 'as other varieties', 'escapes high temperature', 'normal conditions').
    Returns ({stress: {"field", "quote"}}, official stress text present at all)."""
    sf = r.get("seednet_fields") or {}; cf = r.get("csc_fields") or {}
    tags, available = {}, False
    for src, field in OFFICIAL_STRESS_FIELDS:
        text = str((sf if src == "seednet" else cf).get(field) or "")
        if not text.strip() or _PLACEHOLDER_TEXT.match(text): continue
        if field in ("Reaction to Stress", "temperature_tolerance"): available = True
        for clause in re.split(r"[.;\n\t]+|\s{3,}|(?<=\w)\.(?=\s*[A-Z])", text):
            c = " ".join(clause.split())
            if len(c) < 4: continue
            if _CLAUSE_VOID.search(c): continue  # 'like other Roselle varieties', 'RESISTANCE TO DROUGHT : NOT RELEVANT'
            neg = _NEG.search(c)
            for stress, term in _STRESS_TERMS.items():
                if stress in tags: continue
                for m in re.finditer(r"(?<![a-z])(?:" + term + r")(?![a-z])", c, re.IGNORECASE):
                    for t in re.finditer(r"(?<![a-z])(?:" + _TOL_WORD + r")", c, re.IGNORECASE):
                        lo, hi = (t.end(), m.start()) if t.start() < m.start() else (m.end(), t.start())
                        between = c[lo:hi]
                        if len(between.split()) > 8: continue
                        if neg and (neg.start() <= max(m.end(), t.end()) and neg.end() >= min(m.start(), t.start()) - 25): continue
                        if re.search(r"\b(?:than|but|except|while)\b", between, re.IGNORECASE): continue
                        tags[stress] = {"field": f"{'Seednet' if src == 'seednet' else 'CSC minutes'}: {field}", "quote": c[:300]}
                        available = True
                        break
                    if stress in tags: break
    return tags, available


# ---------------------------------------------------------------- disease / pest resistance and yield, by rule (2026-11)
DISEASES = [  # (pattern, canonical name). Built from the Seednet / CSC wording in the data; abbreviations as Seednet writes them.
    (r"neck\s+blast|leaf\s+blast|panicle\s+blast|\bblast\b", "Blast"),
    (r"bacterial\s+leaf\s+blight|bacterial\s+blight|\bBLB\b|\bBB\b", "Bacterial blight"),
    (r"banded\s+leaf\s+(?:and|&)\s+sheath\s+blight|\bBLSB\b", "Banded leaf and sheath blight"),
    (r"sheath\s+blight|\bShB\b", "Sheath blight"), (r"sheath\s+rot", "Sheath rot"), (r"brown\s+spot", "Brown spot"),
    (r"tungro|\bRTD\b|\bRTV\b", "Tungro"), (r"false\s+smut", "False smut"), (r"loose\s+smut", "Loose smut"), (r"whip\s+smut|culmicolous\s+smut|\bsmut\b", "Smut"),
    (r"stem\s+rust|black\s+rust", "Stem rust"), (r"leaf\s+rust|brown\s+rust", "Leaf rust"), (r"yellow\s+rust|stripe\s+rust", "Yellow rust"),
    (r"white\s+rust", "White rust"), (r"\brusts?\b", "Rust"), (r"karnal\s+bunt", "Karnal bunt"), (r"\bbunt\b", "Bunt"),
    (r"powdery\s+mildew|\bPM\b", "Powdery mildew"), (r"downy\s+mildew|\bDM\b", "Downy mildew"),
    (r"fusarium\s*wilt|\bf\.?\s*wilt\b", "Fusarium wilt"), (r"bacterial\s*wilt", "Bacterial wilt"), (r"wilt\s+complex|(?<!fusarium )(?<!fusarium)(?<!bacterial )\bwilt\b", "Wilt (pathogen not stated)"), (r"ascochyta", "Ascochyta blight"),
    (r"mungbean\s+yellow\s+mosaic|yellow\s+mosaic|\bMYMV\b|\bYMV\b|\bYMD\b", "Yellow mosaic virus"), (r"yellow\s+vein\s+mosaic|\bYVMV\b", "Yellow vein mosaic virus"),
    (r"leaf\s+curl|\bCLCuV\b|\bCLCuD\b|\bToLCV\b|\bLCV\b", "Leaf curl virus"), (r"anthracnose", "Anthracnose"), (r"alternaria", "Alternaria blight"),
    (r"late\s+blight", "Late blight"), (r"early\s+blight", "Early blight"), (r"red\s+rot", "Red rot"),
    (r"turcicum\s+leaf\s+blight|\bTLB\b", "Turcicum leaf blight"), (r"maydis\s+leaf\s+blight|\bMLB\b", "Maydis leaf blight"),
    (r"post[\s-]*flowering\s+stalk\s+rot|\bPFSR\b", "Post-flowering stalk rot"), (r"charcoal\s+rot", "Charcoal rot"), (r"root\s+rot", "Root rot"),
    (r"stem\s+rot", "Stem rot"), (r"collar\s+rot", "Collar rot"), (r"dry\s+root\s+rot", "Dry root rot"),
    (r"late\s+leaf\s+spot|early\s+leaf\s+spot|tikka|leaf\s+spots?\b", "Leaf spot"), (r"bacterial\s+pustule", "Bacterial pustule"),
    (r"cercospora", "Cercospora leaf spot"), (r"grain\s+mou?ld", "Grain mould"), (r"\bergot\b", "Ergot"), (r"blister\s+blight", "Blister blight"),
    (r"phyllody", "Phyllody"), (r"sterility\s+mosaic", "Sterility mosaic"), (r"bud\s+necrosis", "Bud necrosis"), (r"net\s+blotch", "Net blotch"),
    (r"spot\s+blotch", "Spot blotch"), (r"foliar\s+blight|leaf\s+blight", "Leaf blight"), (r"\bBCMV\b|bean\s+common\s+mosaic", "Bean common mosaic virus"),
    (r"mosaic", "Mosaic virus"), (r"die[\s-]*back", "Dieback"), (r"fruit\s+rot", "Fruit rot"), (r"\bscab\b", "Scab"), (r"canker", "Canker"),
    (r"sclerotinia|scerotina", "Sclerotinia rot"), (r"\bdowny\b", "Downy mildew"), (r"purple\s+blotch", "Purple blotch"), (r"rhizome\s+rot", "Rhizome rot"),
    (r"leaf\s+crinkle", "Leaf crinkle"), (r"\bkoleroga\b", "Koleroga"), (r"wilt\s+and\s+root\s+rot", "Wilt"),
]
PESTS = [
    (r"white[\s-]*backed\s+plant\s*hopper|\bWBPH\b", "White-backed planthopper"), (r"brown\s+\.?\s*plant\s*hopper|\bBPH\b", "Brown planthopper"),
    (r"green\s+leaf\s*hopper|\bGLH\b", "Green leafhopper"), (r"leaf\s*hoppers?", "Leafhopper"), (r"plant\s*hoppers?", "Planthopper"),
    (r"gall\s+midge|gan\s+midge|\bGM\b", "Gall midge"), (r"yellow\s+stem\s+borer|\bYSB\b", "Yellow stem borer"), (r"stem\s*borers?", "Stem borer"),
    (r"leaf\s*folders?", "Leaf folder"), (r"shoot\s*fly", "Shoot fly"), (r"pod\s*borers?|helicoverpa", "Pod borer"), (r"pod\s*fly", "Pod fly"),
    (r"woolly\s+aphids?", "Woolly aphid"), (r"aphids?", "Aphid"), (r"jassids?", "Jassid"), (r"white\s*fly|whiteflies", "Whitefly"),
    (r"pink\s+boll\s*worms?", "Pink bollworm"), (r"boll\s*worms?", "Bollworm"), (r"thrips", "Thrips"), (r"mites?\b", "Mite"), (r"nematodes?", "Nematode"),
    (r"termites?", "Termite"), (r"stem\s*fly", "Stem fly"), (r"leaf\s*miners?|leaf\s*minor", "Leaf miner"), (r"spodoptera", "Spodoptera"), (r"hispa", "Hispa"),
    (r"case\s*worms?", "Caseworm"), (r"sucking\s+pests?", "Sucking pests"), (r"defoliators?", "Defoliators"), (r"bruchids?|pulse\s+beetle", "Bruchid"),
    (r"fruit\s+(?:and|&)\s+shoot\s+borer", "Fruit and shoot borer"), (r"fruit\s*borers?", "Fruit borer"), (r"early\s+shoot\s+borer", "Early shoot borer"),
    (r"top\s+(?:shoot\s+)?borer", "Top borer"), (r"internode\s+borer", "Internode borer"), (r"shoot\s+borer", "Shoot borer"), (r"mealy\s*bugs?", "Mealybug"),
    (r"pyrilla", "Pyrilla"), (r"earhead\s+bug|ear\s+head\s+bug", "Earhead bug"), (r"midge", "Midge"), (r"chilo|partellus", "Stem borer"), (r"antigastra", "Capsule borer"),
    (r"capsule\s+borer", "Capsule borer"), (r"cut\s*worms?", "Cutworm"), (r"semilooper", "Semilooper"), (r"girdle\s+beetle", "Girdle beetle"), (r"storage\s+pests?", "Storage pests"),
]
_RES = re.compile(r"(?<![a-z])(?:moderately\s+|highly\s+|fairly\s+|field\s+)?(?:resistan\w*|toleran\w*|tolerat\w*|immune|immunity)(?![a-z])", re.IGNORECASE)
_RES_RATING = re.compile(r"(?<![A-Za-z])(?:HR|MR|R)(?![A-Za-z])")          # ratings are capitals only
_SUS = re.compile(r"(?<![a-z])(?:moderately\s+|highly\s+)?(?:susceptib\w*|suscepti\w*|sensitive|prone|infested|attacked)(?![a-z])", re.IGNORECASE)
_SUS_RATING = re.compile(r"(?<![A-Za-z])(?:HS|MS|S)(?![A-Za-z])")
_VOID = re.compile(r"not\s+relevant|not\s+applicable|not\s+specified|not\s+evaluated|not\s+tested|like\s+(?:most\s+)?other|as\s+(?:in\s+)?other|similar\s+to\s+other|"
                          r"as\s+compared\s+to\s+(?:gram|other\s+crops?)", re.IGNORECASE)
_PLACEHOLDER_TEXT = re.compile(r"^\s*(?:nil|none|na|n/?a|not\s+applicable|not\s+specified|not\s+evaluated|not\s+available|-+|\.)\s*\.?\s*$", re.IGNORECASE)


def official_stress_tags(r: dict) -> tuple[dict, bool]:
    """Tag a stress from the official fields only when a tolerance word and the stress term stand in the same clause, at most 8 words apart:
    'TOLERANT TO WATER LOGGING' -> flood; 'Tolerates 10 days flash floods' -> flood + submergence; 'salt tolerant' -> salinity.
    A clause with a negation, susceptibility, hedge or crop-generic comparison never tags ('Cannot withstand submerged condition',
    'likely to possess drought tolerance', 'as other varieties', 'escapes high temperature', 'normal conditions').
    Returns ({stress: {"field", "quote"}}, official stress text present at all)."""
    sf = r.get("seednet_fields") or {}; cf = r.get("csc_fields") or {}
    tags, available = {}, False
    for src, field in OFFICIAL_STRESS_FIELDS:
        text = str((sf if src == "seednet" else cf).get(field) or "")
        if not text.strip() or _PLACEHOLDER_TEXT.match(text): continue
        if field in ("Reaction to Stress", "temperature_tolerance"): available = True
        for clause in re.split(r"[.;\n\t]+|\s{3,}|(?<=\w)\.(?=\s*[A-Z])", text):
            c = " ".join(clause.split())
            if len(c) < 4: continue
            if _CLAUSE_VOID.search(c): continue  # 'like other Roselle varieties', 'RESISTANCE TO DROUGHT : NOT RELEVANT'
            neg = _NEG.search(c)
            for stress, term in _STRESS_TERMS.items():
                if stress in tags: continue
                for m in re.finditer(r"(?<![a-z])(?:" + term + r")(?![a-z])", c, re.IGNORECASE):
                    for t in re.finditer(r"(?<![a-z])(?:" + _TOL_WORD + r")", c, re.IGNORECASE):
                        lo, hi = (t.end(), m.start()) if t.start() < m.start() else (m.end(), t.start())
                        between = c[lo:hi]
                        if len(between.split()) > 8: continue
                        if neg and (neg.start() <= max(m.end(), t.end()) and neg.end() >= min(m.start(), t.start()) - 25): continue
                        if re.search(r"\b(?:than|but|except|while)\b", between, re.IGNORECASE): continue
                        tags[stress] = {"field": f"{'Seednet' if src == 'seednet' else 'CSC minutes'}: {field}", "quote": c[:300]}
                        available = True
                        break
                    if stress in tags: break
    return tags, available


# ---------------------------------------------------------------- disease / pest resistance and yield, by rule (2026-11)
DISEASES = [  # (pattern, canonical name). Built from the Seednet / CSC wording in the data; abbreviations as Seednet writes them.
    (r"neck\s+blast|leaf\s+blast|panicle\s+blast|\bblast\b", "Blast"),
    (r"bacterial\s+leaf\s+blight|bacterial\s+blight|\bBLB\b|\bBB\b", "Bacterial blight"),
    (r"banded\s+leaf\s+(?:and|&)\s+sheath\s+blight|\bBLSB\b", "Banded leaf and sheath blight"),
    (r"sheath\s+blight|\bShB\b", "Sheath blight"), (r"sheath\s+rot", "Sheath rot"), (r"brown\s+spot", "Brown spot"),
    (r"tungro|\bRTD\b|\bRTV\b", "Tungro"), (r"false\s+smut", "False smut"), (r"loose\s+smut", "Loose smut"), (r"whip\s+smut|culmicolous\s+smut|\bsmut\b", "Smut"),
    (r"stem\s+rust|black\s+rust", "Stem rust"), (r"leaf\s+rust|brown\s+rust", "Leaf rust"), (r"yellow\s+rust|stripe\s+rust", "Yellow rust"),
    (r"white\s+rust", "White rust"), (r"\brusts?\b", "Rust"), (r"karnal\s+bunt", "Karnal bunt"), (r"\bbunt\b", "Bunt"),
    (r"powdery\s+mildew|\bPM\b", "Powdery mildew"), (r"downy\s+mildew|\bDM\b", "Downy mildew"),
    (r"fusarium\s*wilt|\bf\.?\s*wilt\b", "Fusarium wilt"), (r"bacterial\s*wilt", "Bacterial wilt"), (r"wilt\s+complex|(?<!fusarium )(?<!fusarium)(?<!bacterial )\bwilt\b", "Wilt (pathogen not stated)"), (r"ascochyta", "Ascochyta blight"),
    (r"mungbean\s+yellow\s+mosaic|yellow\s+mosaic|\bMYMV\b|\bYMV\b|\bYMD\b", "Yellow mosaic virus"), (r"yellow\s+vein\s+mosaic|\bYVMV\b", "Yellow vein mosaic virus"),
    (r"leaf\s+curl|\bCLCuV\b|\bCLCuD\b|\bToLCV\b|\bLCV\b", "Leaf curl virus"), (r"anthracnose", "Anthracnose"), (r"alternaria", "Alternaria blight"),
    (r"late\s+blight", "Late blight"), (r"early\s+blight", "Early blight"), (r"red\s+rot", "Red rot"),
    (r"turcicum\s+leaf\s+blight|\bTLB\b", "Turcicum leaf blight"), (r"maydis\s+leaf\s+blight|\bMLB\b", "Maydis leaf blight"),
    (r"post[\s-]*flowering\s+stalk\s+rot|\bPFSR\b", "Post-flowering stalk rot"), (r"charcoal\s+rot", "Charcoal rot"), (r"root\s+rot", "Root rot"),
    (r"stem\s+rot", "Stem rot"), (r"collar\s+rot", "Collar rot"), (r"dry\s+root\s+rot", "Dry root rot"),
    (r"late\s+leaf\s+spot|early\s+leaf\s+spot|tikka|leaf\s+spots?\b", "Leaf spot"), (r"bacterial\s+pustule", "Bacterial pustule"),
    (r"cercospora", "Cercospora leaf spot"), (r"grain\s+mou?ld", "Grain mould"), (r"\bergot\b", "Ergot"), (r"blister\s+blight", "Blister blight"),
    (r"phyllody", "Phyllody"), (r"sterility\s+mosaic", "Sterility mosaic"), (r"bud\s+necrosis", "Bud necrosis"), (r"net\s+blotch", "Net blotch"),
    (r"spot\s+blotch", "Spot blotch"), (r"foliar\s+blight|leaf\s+blight", "Leaf blight"), (r"\bBCMV\b|bean\s+common\s+mosaic", "Bean common mosaic virus"),
    (r"mosaic", "Mosaic virus"), (r"die[\s-]*back", "Dieback"), (r"fruit\s+rot", "Fruit rot"), (r"\bscab\b", "Scab"), (r"canker", "Canker"),
    (r"sclerotinia|scerotina", "Sclerotinia rot"), (r"\bdowny\b", "Downy mildew"), (r"purple\s+blotch", "Purple blotch"), (r"rhizome\s+rot", "Rhizome rot"),
    (r"leaf\s+crinkle", "Leaf crinkle"), (r"\bkoleroga\b", "Koleroga"), (r"wilt\s+and\s+root\s+rot", "Wilt"),
]
PESTS = [
    (r"white[\s-]*backed\s+plant\s*hopper|\bWBPH\b", "White-backed planthopper"), (r"brown\s+\.?\s*plant\s*hopper|\bBPH\b", "Brown planthopper"),
    (r"green\s+leaf\s*hopper|\bGLH\b", "Green leafhopper"), (r"leaf\s*hoppers?", "Leafhopper"), (r"plant\s*hoppers?", "Planthopper"),
    (r"gall\s+midge|gan\s+midge|\bGM\b", "Gall midge"), (r"yellow\s+stem\s+borer|\bYSB\b", "Yellow stem borer"), (r"stem\s*borers?", "Stem borer"),
    (r"leaf\s*folders?", "Leaf folder"), (r"shoot\s*fly", "Shoot fly"), (r"pod\s*borers?|helicoverpa", "Pod borer"), (r"pod\s*fly", "Pod fly"),
    (r"woolly\s+aphids?", "Woolly aphid"), (r"aphids?", "Aphid"), (r"jassids?", "Jassid"), (r"white\s*fly|whiteflies", "Whitefly"),
    (r"pink\s+boll\s*worms?", "Pink bollworm"), (r"boll\s*worms?", "Bollworm"), (r"thrips", "Thrips"), (r"mites?\b", "Mite"), (r"nematodes?", "Nematode"),
    (r"termites?", "Termite"), (r"stem\s*fly", "Stem fly"), (r"leaf\s*miners?|leaf\s*minor", "Leaf miner"), (r"spodoptera", "Spodoptera"), (r"hispa", "Hispa"),
    (r"case\s*worms?", "Caseworm"), (r"sucking\s+pests?", "Sucking pests"), (r"defoliators?", "Defoliators"), (r"bruchids?|pulse\s+beetle", "Bruchid"),
    (r"fruit\s+(?:and|&)\s+shoot\s+borer", "Fruit and shoot borer"), (r"fruit\s*borers?", "Fruit borer"), (r"early\s+shoot\s+borer", "Early shoot borer"),
    (r"top\s+(?:shoot\s+)?borer", "Top borer"), (r"internode\s+borer", "Internode borer"), (r"shoot\s+borer", "Shoot borer"), (r"mealy\s*bugs?", "Mealybug"),
    (r"pyrilla", "Pyrilla"), (r"earhead\s+bug|ear\s+head\s+bug", "Earhead bug"), (r"midge", "Midge"), (r"chilo|partellus", "Stem borer"), (r"antigastra", "Capsule borer"),
    (r"capsule\s+borer", "Capsule borer"), (r"cut\s*worms?", "Cutworm"), (r"semilooper", "Semilooper"), (r"girdle\s+beetle", "Girdle beetle"), (r"storage\s+pests?", "Storage pests"),
]
_RES = re.compile(r"(?<![a-z])(?:moderately\s+|highly\s+|fairly\s+|field\s+)?(?:resistan\w*|toleran\w*|tolerat\w*|immune|immunity)(?![a-z])|(?<![A-Za-z])(?:HR|MR|R)(?![A-Za-z])", re.IGNORECASE)
_SUS = re.compile(r"(?<![a-z])(?:moderately\s+|highly\s+)?(?:susceptib\w*|suscepti\w*|sensitive|prone|infested|attacked)(?![a-z])|(?<![A-Za-z])(?:HS|MS|S)(?![A-Za-z])", re.IGNORECASE)
_VOID = re.compile(r"not\s+(?:specified|recorded|available|applicable|observed|tested|evaluated)|no\s+major\s+(?:disease|pest|insect)|checks?\b|other\s+variet|compared\s+to\s+(?:the\s+)?(?:check|local)|"
                   r"than\s+(?:the\s+)?(?:check|local)|in\s+general|the\s+crop\s+suffers", re.IGNORECASE)


_COMPILED = {}


def _alts(table):
    """Each alternative of a table pattern compiled on its own: abbreviations written in capitals (BLB, PM, GM, BPH) match capitals only,
    words match in any case."""
    key = id(table)
    if key not in _COMPILED:
        def top_split(p_):
            parts, depth, cur = [], 0, ""
            for ch in p_:
                if ch == "(": depth += 1
                elif ch == ")": depth -= 1
                if ch == "|" and depth == 0: parts.append(cur); cur = ""; continue
                cur += ch
            return parts + [cur]
        flat = [(x, name) for pat, name in table for x in top_split(pat)]
        flat.sort(key=lambda t: -len(t[0]))  # longest (most specific) first: 'bacterial wilt' before 'wilt', 'dry root rot' before 'root rot'
        _COMPILED[key] = [([re.compile(x) if re.search(r"[A-Z]{2,}", x) else re.compile(x, re.IGNORECASE)], name) for x, name in flat]
    return _COMPILED[key]


def resistance_tags(text: str, table) -> list[tuple[str, str]]:
    """[(canonical name, clause)] for each disease / pest in `table` that a resistance word governs in the same clause: a rating right after
    the name ('Blast: R', 'BLB (MR)') decides first; otherwise the nearest qualifier before the name (within 70 characters) must be a resistance
    word, not a susceptibility word. Clauses about checks, other varieties, 'not specified' or 'no major disease' never tag."""
    out = []
    for clause in re.split(r"[;\n\t]+|\.(?=\s|$)|\s{3,}", str(text or "")):
        c = " ".join(clause.split())
        if len(c) < 3 or _VOID.search(c): continue
        quals = ([(m.start(), m.end(), "R") for rx in (_RES, _RES_RATING) for m in rx.finditer(c)]
                 + [(m.start(), m.end(), "S") for rx in (_SUS, _SUS_RATING) for m in rx.finditer(c)])
        if not any(q[2] == "R" for q in quals): continue
        taken = []
        for alts, name in _alts(table):
            for rx in alts:
                for m in rx.finditer(c):
                    if any(m.start() < e and m.end() > s_ for s_, e in taken): continue
                    after = [q for q in quals if q[0] >= m.end() and q[0] - m.end() <= 4]
                    before = [q for q in quals if q[1] <= m.start() and m.start() - q[1] <= 70]
                    q = min(after) if after else (max(before, key=lambda t: t[1]) if before else None)
                    taken.append((m.start(), m.end()))
                    if q and q[2] == "R" and name not in [o[0] for o in out]: out.append((name, c[:300]))
    return out


_UNMAPPED = re.compile(r"(?:resistan\w*|toleran\w*)\s+(?:to|against)\s+([A-Za-z][A-Za-z\s-]{3,40}?(?:rot|blight|spot|mosaic|virus|mildew|wilt|rust|smut|mou?ld|scab|canker|necrosis|disease))\b", re.IGNORECASE)


def _resist_block(r: dict, kind: str) -> dict:
    table = DISEASES if kind == "disease" else PESTS
    sf = r.get("seednet_fields") or {}; cf = r.get("csc_fields") or {}
    fields = ([("Seednet", "Reaction to Major Diseases"), ("Seednet", "Reaction to Major Pests"), ("CSC minutes", "disease_resistance"), ("CSC minutes", "special_traits")]
              if kind == "disease" else [("Seednet", "Reaction to Major Pests"), ("Seednet", "Reaction to Major Diseases"), ("CSC minutes", "pest_tolerance"), ("CSC minutes", "special_traits")])
    names, quote = [], {}
    for src, f in fields:
        text = (sf if src == "Seednet" else cf).get(f)
        if not text: continue
        for name, clause in resistance_tags(text, table):
            if name not in names: names.append(name)
            quote = quote or {"field": f"{src}: {f}", "quote": clause}
        if kind == "disease" and f == "Reaction to Major Diseases":
            for m in _UNMAPPED.finditer(str(text)):
                ph = " ".join(m.group(1).split())
                if not any(re.search(p, ph, re.IGNORECASE) for p, _ in table) and ph.title() not in names and not _VOID.search(ph): names.append(ph.title())
    official = list(names)
    far = (r.get("research_data") or {}).get("full_analysis_result") or {}
    blk = ((far.get("stress_tolerance") or {}).get("disease_resistance" if kind == "disease" else "pest_resistance") or {}) if isinstance(far, dict) else {}
    summ = str(blk.get("summary") or "") if isinstance(blk, dict) else ""
    research = [n for n, _ in resistance_tags(summ, table)] if summ and not re.match(r"\s*(no |not |none)", summ, re.IGNORECASE) else []
    for n in research:
        if n not in names: names.append(n)
    level = "both" if official and research else "official text" if official else "research" if research else ""
    srcs = [u for u in (blk.get("evidence_sources") or [] if isinstance(blk, dict) else []) if isinstance(u, str)] if research else []
    return {"level": level, ("diseases" if kind == "disease" else "pests"): names, "official": official, "research": research, "official_quote": quote,
            "research_summary": summ[:1500] if research else "", "sources": srcs}


YIELD_BOUNDS = {  # kg/ha, per crop group; values outside are rejected (unit errors, per-plant or per-tree figures, typos)
    "cereal": (300, 15000), "pulse": (200, 5000), "oilseed": (200, 6000), "cotton": (300, 6000), "fibre": (500, 8000), "sugarcane": (30000, 250000),
    "fodder": (3000, 300000), "vegetable": (1000, 150000), "fruit": (1000, 150000), "tuber": (3000, 100000), "spice": (100, 40000), "other": (100, 200000)}
_CROP_GROUP = {
    "cereal": {"Rice", "Wheat", "Maize", "Sorghum", "Pearl millet", "Barley", "Oat", "Finger millet", "Foxtail millet", "Little millet", "Kodo millet", "Barnyard millet",
               "Proso millet", "Browntop millet", "Triticale", "Buckwheat", "Amaranth", "Quinoa"},
    "pulse": {"Chickpea", "Pigeon pea", "Green gram (mung)", "Black gram (urd)", "Lentil", "Pea", "Cowpea", "Horse gram", "Rajmash (kidney bean)", "Lathyrus", "Moth bean",
              "Faba bean", "Rice bean", "Indian bean (dolichos)", "Adzuki bean"},
    "oilseed": {"Mustard / rapeseed", "Groundnut", "Soybean", "Sesame", "Sunflower", "Safflower", "Castor", "Linseed", "Niger", "Taramira (rocket salad)"},
    "cotton": {"Cotton"}, "fibre": {"Jute", "Mesta (kenaf)", "Sunnhemp", "Roselle", "Ramie"}, "sugarcane": {"Sugarcane"},
    "fodder": {"Berseem", "Lucerne", "Napier grass", "Guinea grass", "Cenchrus (anjan / buffel grass)", "Dhaman grass", "Marvel grass", "Setaria grass", "Dinanath grass",
               "Sewan grass", "Ryegrass", "Tall fescue grass", "White clover", "Maize (fodder)", "Sorghum (fodder)"},
    "tuber": {"Potato", "Cassava (tapioca)", "Sweet potato", "Taro (colocasia)", "Greater yam", "White yam", "Elephant foot yam", "Aerial yam", "Tannia", "Arrowroot", "Yam bean"},
    "spice": {"Coriander", "Cumin", "Fennel", "Fenugreek", "Ajwain", "Dill seed", "Nigella", "Black pepper", "Cardamom", "Turmeric", "Ginger", "Cinnamon / cassia", "Nutmeg"},
}
_HIGH_YIELD = re.compile(r"high[\s-]*yield\w*|higher\s+(?:grain\s+|seed\s+|pod\s+|fibre\s+|cane\s+)?yield|out[\s-]*yield\w*|yield\s+(?:advantage|superiority|increase)|superior\s+(?:in\s+)?yield|"
                         r"\d+(?:\.\d+)?\s*%\s*(?:higher|more|increase|superior)", re.IGNORECASE)


def crop_group(crop: str) -> str:
    for g, s_ in _CROP_GROUP.items():
        if crop in s_: return g
    return "other"


def parse_yield(text, crop: str) -> tuple:
    """'4625.00 to 4692.00 Kg/Ha' -> (4625, 4692); '16-18 q/ha' -> (1600, 1800); '6.5 tons/ha' -> (6500, 6500). Seednet appends ' Kg/Ha' to every
    value, so that suffix is ignored when another unit is written. Unclear units ('HA/Q', per plant, per tree) and out-of-bounds values give None."""
    t = re.sub(r"\s*Kg/Ha\s*$", "", str(text or ""), flags=re.IGNORECASE).strip()
    if not t or not re.search(r"\d", t): return None
    tl = t.lower()
    if re.search(r"ha\s*/\s*q|per\s+(?:plant|tree|palm|vine|hill|bush)|/\s*(?:plant|tree|palm)|g\s*/\s*plant|kg\s*/\s*(?:plant|tree|palm)|nuts?\s*/|fruits?\s*/", tl): return None
    unit = 1000 if re.search(r"\bt(?:on(?:ne)?s?)?\s*/\s*ha|tonnes?\s+per|\bt/ha|tones?\s*/", tl) else 100 if re.search(r"\bq(?:tls?|uintals?|ntl)?\.?\s*/\s*h|quintal|\bq\s*/|\bqtl", tl) else 1
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", t.replace(",", ""))]
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:to|-|–)\s*(\d+(?:\.\d+)?)", t.replace(",", ""), re.IGNORECASE)
    lo, hi = (float(m.group(1)), float(m.group(2))) if m else (nums[0], nums[0])
    if lo > hi: lo, hi = hi, lo
    lo, hi = lo * unit, hi * unit
    b = YIELD_BOUNDS[crop_group(crop)]
    if not (b[0] <= lo <= b[1] and b[0] <= hi <= b[1]): return None
    return (round(lo), round(hi))


def add_resistance_and_yield(final: list[dict], report: dict) -> None:
    for r in final:
        r["disease_resistance"] = _resist_block(r, "disease"); r["pest_resistance"] = _resist_block(r, "pest")
        r["has_disease_resistance"] = bool(r["disease_resistance"]["diseases"]); r["has_pest_resistance"] = bool(r["pest_resistance"]["pests"])
        r["disease_resistance_basis"] = r["disease_resistance"]["level"]; r["pest_resistance_basis"] = r["pest_resistance"]["level"]
        sf = r.get("seednet_fields") or {}; cf = r.get("csc_fields") or {}
        text = sf.get("Average Yield (Kg/Ha)") or ""
        y = parse_yield(text, r.get("crop_clean") or "")
        if not y and cf.get("yield_performance") and re.fullmatch(r"[\d.,\s\-to]+(?:q|qtl|qtls|quintals?|t|tonnes?|kg)\.?\s*/\s*ha\.?(?:\s*\([^)]*\))?", str(cf["yield_performance"]).strip(), re.IGNORECASE):
            y = parse_yield(cf["yield_performance"], r.get("crop_clean") or ""); text = cf["yield_performance"]
        r["yield_text"] = str(text or "")
        r["yield_kg_ha_min"], r["yield_kg_ha_max"] = (y if y else ("", ""))
        official = " ".join(str(x or "") for x in (sf.get("Agronomic Features"), sf.get("Average Yield (Kg/Ha)"), cf.get("yield_performance"), cf.get("special_traits"), cf.get("additional_notes")))
        r["high_yield_stated_officially"] = bool(_HIGH_YIELD.search(official) and re.search(r"\d", official))
    by_crop = {}
    for r in final:
        if r["yield_kg_ha_min"] != "": by_crop.setdefault(r.get("crop_clean"), []).append((r["yield_kg_ha_min"] + r["yield_kg_ha_max"]) / 2)
    cuts = {}
    for crop, v in by_crop.items():
        if len(v) >= 20:
            v = sorted(v); cuts[crop] = (v[len(v) // 4], v[(3 * len(v)) // 4])
    for r in final:
        r["yield_class"] = ""
        if r["yield_kg_ha_min"] != "" and r.get("crop_clean") in cuts:
            mid = (r["yield_kg_ha_min"] + r["yield_kg_ha_max"]) / 2; q1, q3 = cuts[r["crop_clean"]]
            r["yield_class"] = "top quarter for the crop" if mid >= q3 else "bottom quarter" if mid < q1 else "middle half"
    report["disease_resistance"] = dict(collections.Counter(r["disease_resistance_basis"] or "none" for r in final))
    report["pest_resistance"] = dict(collections.Counter(r["pest_resistance_basis"] or "none" for r in final))
    report["records_with_official_yield"] = sum(1 for r in final if r["yield_kg_ha_min"] != "")


# ---------------------------------------------------------------- stress confirmation, deterministic second look (2026-11 data review)
NONE_FOUND = "None found"  # was "No stress tolerance claimed": the searches found no statement; it is NOT evidence that the variety lacks tolerance
_WEAK_BASIS = re.compile(r"inferr|indirect|\bproposal|proposed as|breeding (?:intent|aim|objective|target)|garbled|unverified|not a (?:tolerance )?statement|"
                         r"not a tested|not tested|suitab|suited (?:to|for)|\bparent\b|recurrent parent|donor|derived lines?|introgress\w*|lines derived from|list mention", re.IGNORECASE)
_EXCLUDED = re.compile(r"not counted|excluded|not count|ignored|discarded|does not count|was dropped|not used|removed", re.IGNORECASE)
_MIRRORS = ("scribd.com", "researchgate.net", "academia.edu", "semanticscholar.org", "dokumen.pub", "pdfcoffee.com", "studocu.com", "doku.pub", "vdocuments")
FLOOD_PLAUSIBLE_CROPS = {"Rice", "Jute", "Mesta (kenaf)", "Sugarcane", "Makhana", "Water spinach"}


def _doc_key(url: str) -> str:
    """Same document under another address counts once: mirrors (Scribd, ResearchGate, Academia ...) by title slug, others by host + last path segment."""
    u = str(url or "").strip().lower()
    m = re.match(r"^[a-z]+://(?:www\.)?([^/?#]+)([^?#]*)", u)
    host, path = (m.group(1), m.group(2)) if m else (u, "")
    last = [x for x in path.split("/") if x]
    seg = last[-1] if last else ""
    seg = re.sub(r"\.(pdf|html?|aspx|php)$", "", seg)
    slug = re.sub(r"[^a-z]", "", re.sub(r"^\d+[_-]", "", seg))
    if any(h in host for h in _MIRRORS): return "mirror:" + slug[:60]
    return host + "/" + (seg or path)


def adjust_stress(stresses: dict, *, crop: str, refers_to: str, evidence_urls: dict) -> dict:
    """Second, rule-based look at the model's per-stress verdicts. Never upgrades. A counted source does not count when:
      * the basis calls it inferred / indirect / a proposal / garbled / unverified / not a tolerance statement / suitability, or says the variety
        was a parent / donor / its derived lines (sentences that say such evidence was 'not counted' are ignored);
      * it is a mirror copy of another cited document (Scribd is a mirror of any other cited document);
      * the research text is about another or a mixed variety (only official text then counts);
      * flood / submergence in a crop where that is implausible, unless official Seednet/CSC text states it.
    Returns {stress: {..., verdict, verdict_model, independent_sources, independent_sources_model, verdict_adjusted_reason, label}}."""
    out = {}
    for k, v in (stresses or {}).items():
        v = dict(v or {}); vm = v.get("verdict"); n = int(v.get("independent_sources") or 0); off = bool(v.get("official_support"))
        reasons = []
        if vm in ("confirmed_multi_source", "single_source"):
            weak = [sen for sen in re.split(r"(?<=[.;])\s+", str(v.get("basis") or "")) if _WEAK_BASIS.search(sen) and not _EXCLUDED.search(sen)]
            if weak:
                n = 0; reasons.append("basis describes indirect / inferred / parental / suitability evidence: " + weak[0][:160])
            urls = [u for u in (evidence_urls.get(k) or []) if isinstance(u, str) and u.strip()]
            if urls and n > 0:
                keys = [_doc_key(u) for u in urls]
                non_scribd = [kk for kk, u in zip(keys, urls) if "scribd.com" not in u.lower()]
                docs = set(non_scribd) if non_scribd else set(keys)
                dupes = len(urls) - len(docs)
                if dupes > 0 and n > len(docs) + (1 if off else 0):
                    n = len(docs) + (1 if off else 0); reasons.append(f"{dupes} cited address(es) are copies of the same document (mirror sites counted once)")
            if refers_to in ("other_variety", "mixed") and n > (1 if off else 0):
                n = 1 if off else 0; reasons.append(f"research text refers to {refers_to.replace('_', ' ')}: only official text counts")
            if k in ("flood", "submergence") and crop not in FLOOD_PLAUSIBLE_CROPS and not off and n > 0:
                n = 0; reasons.append(f"{k} tolerance in {crop or 'this crop'} without an official Seednet/CSC statement is not accepted")
        verdict = vm
        if vm in ("confirmed_multi_source", "single_source"):
            verdict = "confirmed_multi_source" if n >= 2 else "single_source" if n == 1 else "weak_or_generic"
        v.update(verdict_model=vm, independent_sources_model=v.get("independent_sources"), independent_sources=n if vm in ("confirmed_multi_source", "single_source") else v.get("independent_sources"),
                 verdict=verdict, verdict_adjusted_reason="; ".join(reasons) if verdict != vm or reasons else "",
                 label=CONFIRMATION_LABEL.get(verdict, "Not confirmed"))
        out[k] = v
    return out


# ---------------------------------------------------------------- display names (2026-11): printed name kept, cleaned name shown
NAME_CORRECTIONS = HERE / "name_corrections.csv"


def load_name_corrections(path: Path = NAME_CORRECTIONS) -> dict:
    """Editable spelling-correction table: crop, name_as_printed, corrected_name, basis, source[, extra_alias]. Matching ignores case and spacing."""
    import csv as _csv
    out = {}
    if path.exists():
        with path.open(encoding="utf-8", newline="") as fh:
            for row in _csv.DictReader(fh):
                k = (str(row.get("crop") or "").strip().lower(), " ".join(str(row.get("name_as_printed") or "").lower().split()))
                if k[1]: out[k] = row
    return out


def name_codes(records: list[dict]) -> set[str]:
    """Letter codes written in capitals inside mixed-case names ('CR Dhan 801', 'Karan Narendra (DBW 222)'): kept in capitals when an
    ALL-CAPS name is title-cased."""
    c = set()
    for r in records:
        n = str(r.get("variety_name") or "")
        c |= {m for m in re.findall(r"(?<![A-Za-z])([A-Z]{2,5})(?=[\s\-.]*\d)", n)}  # letters written next to a number: 'PBW 343', 'HD-2967'
        if re.search(r"[a-z]", n): c |= {m for m in re.findall(r"(?<![A-Za-z])([A-Z]{2,4})(?![A-Za-z])", n)}
    # a token that is also written as an ordinary word ('Pusa', 'Okra', 'Jowar', 'Makka') is a word, not a code
    words = collections.Counter(t for r in records for t in re.findall(r"(?<![A-Za-z])([A-Z][a-z]{2,})(?![A-Za-z])", str(r.get("variety_name") or "")))
    return {x for x in c if words.get(x.title(), 0) < 3}


def display_name(r: dict, codes: set[str], corrections: dict) -> None:
    from standardize import name_quality, standardize_crop
    """variety_name_as_printed = the source spelling; variety_name = display name: spelling from the corrections table (basis recorded),
    spaces collapsed, '- 1' -> '-1', run-together words split only when the split form occurs in the record's own Seednet / CSC / research
    text, ALL-CAPS names title-cased except codes (tokens with digits, known codes, short consonant runs, roman numerals)."""
    printed = " ".join(str(r.get("variety_name") or "").split())
    r["variety_name_as_printed"] = printed
    basis, name = [], printed
    row = corrections.get((str(r.get("crop_clean") or "").lower(), printed.lower()))
    if row:
        if (row.get("corrected_name") or "").strip() and row["corrected_name"].strip() != printed:
            name = row["corrected_name"].strip(); basis.append(f"spelling: {row.get('basis')} [{row.get('source')}]")
        if (row.get("extra_alias") or "").strip(): r["_extra_alias"] = row["extra_alias"].strip(); basis.append(f"alias added: {row['extra_alias'].strip()} ({row.get('basis')})")
    sn_name = str((r.get("seednet_fields") or {}).get("Variety Name") or "")
    if sn_name and "(" not in name and (r.get("seednet_match_status") in ("confirmed_exact", "confirmed_spelling") or r.get("record_source") == "Seednet only"):
        from match_rules import _aliases as _al, _strip_paren as _sp, name_key as _nk
        if _nk(_sp(sn_name)) == _nk(name) or _nk(_sp(sn_name)) == _nk(_sp(name)):
            proper = [a_ for a_ in _al(sn_name) if not re.search(r"\d", a_) and re.search(r"[A-Za-z]{4,}", a_) and name_quality(a_) == "ok"
                      and not re.match(r"(?i)\s*(iet|ic|hybrid|variety|selection|local|kharif|rabi|aerobic|irrigated|rainfed|late|early|medium)\b", a_)]
            if proper:
                name = f"{name} ({proper[0].strip()})"; basis.append("formatting: common name from the Seednet name added in brackets")
    lead = re.match(r"^\s*(rice|paddy|wheat|maize|cotton|mustard|groundnut|soybean|chickpea|sorghum|barley|sesame|sugarcane)\s+(.+)$", name, re.IGNORECASE)
    if lead and standardize_crop(lead.group(1)) == standardize_crop(r.get("crop_clean")) and re.search(r"\d|[A-Z]{2,}", lead.group(2)) and name_quality(lead.group(2)) == "ok":
        name = lead.group(2); basis.append("formatting: leading crop word dropped")  # 'Rice CR Dhan 801' -> 'CR Dhan 801'
    n2 = re.sub(r"\s*-\s+(?=\d)|\s+-\s*(?=\d)", "-", name)
    if n2 != name: basis.append("formatting: spacing around a hyphen"); name = n2
    attest = " ".join(str(x) for x in ((r.get("seednet_fields") or {}).get("Variety Name"), json.dumps(r.get("csc_fields") or {}, ensure_ascii=False),
                                       json.dumps(((r.get("research_data") or {}).get("full_analysis_result") or {}).get("variety_profile") or {}, ensure_ascii=False),
                                       " ".join(str(p.get("title") or "") for p in (r.get("publications_scholar") or [])[:25]))).lower()
    def split_tok(m):
        tok = m.group(0); cand = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", tok)
        return cand if cand != tok and cand.lower() in attest else tok
    n2 = re.sub(r"[A-Za-z]*[a-z][A-Z][A-Za-z]*", split_tok, name)
    if n2 != name: basis.append("formatting: run-together words split as written in the record's own sources"); name = n2
    if not re.search(r"[a-z]", name) and re.search(r"[A-Z]{4,}", name):
        def case_tok(m):
            t = m.group(0)
            if t in codes or re.fullmatch(r"[IVX]{1,4}", t) or (len(t) <= 3 and not re.search(r"[AEIOU]", t)): return t
            return t[:1] + t[1:].lower()
        n2 = re.sub(r"[A-Z]+", case_tok, name)
        if n2 != name: basis.append("formatting: ALL-CAPS name shown in title case (codes kept)"); name = n2
    if re.search(r"[a-z]", name) and not re.search(r"[A-Z]", name):
        n2 = re.sub(r"(?<![A-Za-z])([a-z])", lambda m: m.group(1).upper(), name)
        if n2 != name: basis.append("formatting: all-lower-case name capitalised"); name = n2
    r["variety_name"] = name
    r["name_correction_basis"] = basis


# ---------------------------------------------------------------- ids, search names, text hygiene (2026-11 data review)
def slug(text) -> str:
    t = re.sub(r"\([^)]*\)", lambda m: " " + m.group(0)[1:-1] + " ", str(text or "")).lower()
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t[:80].strip("-") or "x"


def search_names(r: dict) -> list[str]:
    """Names under which the variety can be found, ONLY from the record's own fields: the CSC name, the name without brackets, each bracket
    alias, the linked Seednet name (and its aliases), merged duplicates' names, and spacing/hyphen variants of these ('SWARANA-SUB1' ->
    'SWARANA SUB 1'). Nothing is invented: a spelling form ('Swarna Sub1') is added only when it occurs in one of those fields."""
    from match_rules import _aliases, _strip_paren
    from standardize import name_quality
    src = [r.get("variety_name"), r.get("variety_name_as_printed"), r.pop("_extra_alias", None), (r.get("csc_fields") or {}).get("variety_name"),
           (r.get("csc_fields") or {}).get("variety_code"), (r.get("seednet_fields") or {}).get("Variety Name")]
    src += list(r.get("merged_duplicate_names") or [])
    out, seen = [], set()
    junk = re.compile(r"not applicable|not available|not specified|ocr\s*:|\?|^\s*(aerobic|irrigated|rainfed|upland|lowland|boro|kharif|rabi|late sown|timely sown|"
                      r"early|medium|late|hybrid|variety|composite|local|selection)\s*$", re.IGNORECASE)
    def add(x, main=False):
        x = re.sub(r"\s+", " ", str(x or "")).strip(" -,;:")
        k = x.lower()
        if not x or k in seen or k in ("nan", "none") or not re.search(r"[A-Za-z0-9]", x): return
        if not main and (junk.search(x) or name_quality(x) != "ok"): return  # aliases must be real names (12-11: no placeholders / OCR notes / ecology words)
        seen.add(k); out.append(x)
    for i_, n in enumerate(src):
        if not n or str(n).strip().lower() in NA_VALUES: continue
        add(n, main=i_ < 2); add(_strip_paren(n))
        for a_ in _aliases(n): add(a_)
        for f in [n, _strip_paren(n)]:
            spaced = re.sub(r"(?<=[A-Za-z])(?=\d)|(?<=\d)(?=[A-Za-z])", " ", re.sub(r"[-_/]+", " ", str(f)))
            add(spaced)
    return out


_MOJI = {"â€“": "–", "â€”": "—", "â€™": "’", "â€˜": "‘", "â€œ": "“", "â€\x9d": "”", "Â ": " ", "Â": ""}
_ERR = re.compile(r"HttpError|googleapis\.com|customsearch|[?&]cx=|Quota exceeded|Server tool use", re.IGNORECASE)


def scrub_record(r: dict) -> dict:
    """Publishable text: literal 'nan'/'None'/'null'/'undefined' -> '' everywhere; mojibake dashes fixed; markdown '**' removed; error strings
    (HttpError text, Google search-engine ids, quota messages) removed from search_metadata; 'cx=' ids removed from any URL."""
    def fix(x, in_meta=False):
        if isinstance(x, str):
            if re.fullmatch(r"\s*(nan|NaN|None|null|undefined|NaT)\s*", x): return ""
            for a_, b_ in _MOJI.items():
                if a_ in x: x = x.replace(a_, b_)
            x = x.replace("**", "")
            if x.rstrip().endswith((";", ".;", ",")): x = re.sub(r"[\s.;,]*[;,][\s.;,]*$", "", x.rstrip()) + ("." if re.search(r"\.\s*[;,]\s*$", x) else "")  # trailing '.;' / ';'
            x = re.sub(r"\.\s*;\s+", "; ", x) if len(x) < 2000 else x
            x = re.sub(r"([?&])cx=[A-Za-z0-9:_\-]+&?", r"\1", x)
            if in_meta and _ERR.search(x): return ""
            return x
        if isinstance(x, list): return [fix(v, in_meta) for v in x]
        if isinstance(x, dict):
            d = {k: fix(v, in_meta) for k, v in x.items()}
            if in_meta and "error" in d and not d["error"]: d.pop("error")
            return d
        return x
    return {k: fix(v, k == "search_metadata") for k, v in r.items()}


def _to_candidate(r: dict, status: str, reason: str) -> None:
    """Move the attached Seednet entry aside: kept in seednet_candidate* for review, never shown as this variety's own record."""
    sf = r.get("seednet_fields") or {}; cf = r.get("csc_fields") or {}
    old_url = r.get("seednet_url") or sf.get("source_url") or ""
    if sf.get("Variety Name"):
        r["seednet_candidate"] = {"variety_name": sf.get("Variety Name"), "crop": sf.get("Crop Name"), "url": old_url,
                                  "similarity_score": cf.get("similarity_score"), "manual_match": cf.get("manual_match"), "reason": reason}
        r["seednet_candidate_fields"] = sf
        for k in ("best_direct_links", "direct_source_links", "source_links_all"):
            if isinstance(r.get(k), list):
                r[k] = [x for x in r[k] if not (isinstance(x, dict) and old_url and x.get("url") == old_url) and x != old_url]
                if f"{k}_count" in r: r[f"{k}_count"] = len(r[k])
    r["seednet_fields"] = {}; r["seednet_url"] = ""; r["seednet_variety_id"] = ""; r["seednet_available"] = "No"; r["seednet_match"] = "NO"
    r["seednet_match_status"] = status; r["seednet_match_reason"] = reason


def apply_match_status(r: dict, rematch: dict | None = None) -> None:
    """Decide whether the attached Seednet entry is the same variety (match_rules.py).
    1. If the entry attached by the 2025 fuzzy match is the same variety (classify), keep it.
    2. Otherwise move it aside to seednet_candidate*; if the strict re-match (rematch_seednet.py) CONFIRMED a Seednet entry for this
       CSC variety, attach that one. A non-confirmed re-match result is only kept as a candidate (never attached).
    Statuses: confirmed_exact / confirmed_spelling (linked), different_variety / same_name_crop_conflict / needs_review (not linked,
    candidate kept with a reason), no_seednet. seednet_match_reason says why."""
    from match_rules import CONFIRMED, classify_reason
    from rematch_seednet import csc_key
    cf = r.get("csc_fields") or {}
    sf = r.get("seednet_fields") or {}
    status, reason = classify_reason(r.get("variety_name"), r.get("crop"), sf.get("Variety Name"), sf.get("Crop Name"))
    hit = (rematch or {}).get(csc_key(cf.get("crop") or r.get("crop"), cf.get("variety_name") or r.get("variety_name")))
    r["seednet_candidate"] = None; r["seednet_candidate_fields"] = {}; r["seednet_rematched"] = False; r["seednet_match_reason"] = reason
    if status in CONFIRMED:
        r["seednet_match_status"] = status; return
    legacy_status, legacy_reason = status, reason
    if sf.get("Variety Name"): _to_candidate(r, status, reason)
    if hit and hit.get("seednet") and hit.get("status") in CONFIRMED:
        row = {k: v for k, v in hit["seednet"].items() if v not in (None, "")}
        r["seednet_fields"] = row; r["seednet_url"] = row.get("source_url", ""); r["seednet_variety_id"] = row.get("variety_id", "")
        r["seednet_available"] = "Yes"; r["seednet_match"] = "YES"; r["seednet_rematched"] = True
        r["seednet_match_status"] = hit["status"]; r["seednet_match_reason"] = hit.get("reason") or "strict re-match"
        return
    if not r["seednet_candidate"] and hit and hit.get("seednet") and hit.get("status") not in ("no_seednet", None):
        row = {k: v for k, v in hit["seednet"].items() if v not in (None, "")}
        r["seednet_fields"] = row; r["seednet_url"] = row.get("source_url", "")
        _to_candidate(r, hit["status"], hit.get("reason") or "")
        return
    if r["seednet_candidate"]:
        r["seednet_match_status"] = legacy_status if legacy_status in ("same_name_crop_conflict",) else "different_variety"; r["seednet_match_reason"] = legacy_reason
    else:
        r["seednet_match_status"] = "no_seednet"; r["seednet_match_reason"] = (hit or {}).get("reason") or "no Seednet entry with this name in this crop"


_GENERIC_INST_KEYS = {"agricultural", "agriculture", "agril", "regional", "zonal", "main", "head", "breeder", "scientist", "aicrp on", "aicrp", "research", "station",
                      "agricultural research", "regional agricultural", "vegetable", "rice", "cotton", "pulses", "pulse", "oilseeds", "sorghum", "sugarcane", "jute",
                      "main pulses", "main cotton", "department", "division", "college", "university", "institute", "director"}


def _generic_inst_key(key: str) -> bool:
    """A lookup key that names no institution ('agricultural', 'regional', 'rice', a state name): it pulled one institution's contact onto
    every station with a generic name (SKN Agriculture University, Jobner was attached to 61 unrelated records)."""
    from standardize import STATES, _acronyms, institution_tokens
    k = key.strip().lower()
    return (k in _GENERIC_INST_KEYS or k in {x.lower() for x in STATES} or k in ("orissa", "tamilnadu")
            or not (institution_tokens(k) or _acronyms(k)))


def seednet_only_records(seednet_csv: Path, existing: list[dict], report: dict) -> list[dict]:
    """Seednet varieties that no record links to (popular notified varieties whose CSC minutes are not in hand, e.g. HD 3086, JG 14).
    One record per canonical crop + name: Seednet rows of the same crop whose names are equal without brackets, or equal to a bracket
    alias, are merged (richest row kept, the others listed in seednet_merged_ids). Junk names (name_quality != ok) are skipped.
    Built like the official-data-only stubs, with record_source = 'Seednet only' and seednet_match_status = 'seednet_only'."""
    import pandas as pd
    from match_rules import _aliases, _strip_paren, name_key
    from rematch_seednet import richness
    from standardize import name_is_distinctive, name_quality, standardize_crop
    sn = pd.read_csv(seednet_csv, low_memory=False, dtype=str).fillna("")
    sn["Variety Name"] = sn["Variety Name"].str.replace(r"\s+", " ", regex=True).str.strip()
    linked = set()
    for r in existing:
        for blk in (r.get("seednet_fields") or {},):
            if blk.get("variety_id"): linked.add(str(blk["variety_id"]))
    rows = [row for row in sn.to_dict("records") if row.get("variety_id") and str(row["variety_id"]) not in linked and (row.get("Variety Name") or "").strip()]
    skipped = sum(1 for row in rows if name_quality(row["Variety Name"]) != "ok")
    rows = [row for row in rows if name_quality(row["Variety Name"]) == "ok"]
    def keys(row):
        crop = standardize_crop(row.get("Crop Name")); nm = row["Variety Name"]; ks = {name_key(nm)}
        for f in [_strip_paren(nm)] + _aliases(nm):
            k = name_key(f)
            if k and name_is_distinctive(f) and (re.search(r"\d", k) or len(k) >= 6): ks.add(k)
        return {(crop, k) for k in ks if k}
    parent = list(range(len(rows))); owner = {}
    def find(i):
        while parent[i] != i: parent[i] = parent[parent[i]]; i = parent[i]
        return i
    for i, row in enumerate(rows):
        for k in keys(row):
            if k in owner: parent[find(i)] = find(owner[k])
            else: owner[k] = i
    groups: dict[int, list[dict]] = {}
    for i, row in enumerate(rows): groups.setdefault(find(i), []).append(row)
    template = existing[0]; out = []; now = datetime.now(UTC).year
    for grp in groups.values():
        row = max(grp, key=richness)
        sf = {k: v for k, v in row.items() if v not in (None, "")}
        rec = {kk: ([] if isinstance(v, list) else {} if isinstance(v, dict) else 0 if isinstance(v, (int, float)) and not isinstance(v, bool) else "" if isinstance(v, str) else None) for kk, v in template.items()}
        y = str(sf.get("Year of Release") or "").strip()
        yr = int(y) if re.fullmatch(r"(19|20)\d\d", y) and 1960 <= int(y) <= now else ""
        inst = sf.get("Institution Responsible for developing Breeder Seed") or ""
        rec.update(variety_id="SEEDNET__" + re.sub(r"[^\w\-]", "_", str(sf["variety_id"])), variety_name=sf["Variety Name"], crop=sf.get("Crop Name") or "", crop_clean=sf.get("Crop Name") or "",
                   year_of_release=yr, states_full=[sf["Recommended States"]] if sf.get("Recommended States") else [], states_full_clean=[],
                   developer_institution_csc="", developer_location_csc="", seednet_fields=sf, seednet_url=sf.get("source_url", ""), seednet_variety_id=sf.get("variety_id", ""),
                   seednet_available="Yes", seednet_match="YES", csc_fields={},
                   research_data={"basic_info": {"crop": sf.get("Crop Name") or "", "variety_name": sf["Variety Name"], "data_source": "seednet", "year": yr, "institution": inst or "Not specified"}},
                   stress_tolerance="Unknown", stress_tolerance_strict="Unknown", stress_types=[], stress_types_strict=[], trusted_stress_types=[],
                   stress_levels_gemini={k2: "unknown" for k2 in STRESS_LABELS}, gemini_analysis_status="not_researched", evidence_quality="Not researched",
                   _csc_source_document=None, _csc_meeting=None, _gazette_reference=None, _not_researched=True, record_source="Seednet only",
                   seednet_match_status="seednet_only", seednet_match_reason="Seednet entry not linked to any CSC record", seednet_candidate=None, seednet_candidate_fields={},
                   seednet_rematched=False, seednet_merged_ids=sorted(str(x["variety_id"]) for x in grp if x is not row), name_quality="ok",
                   publications_openalex=[], publications_openalex_count=0, publications_scholar=[], publications_scholar_count=0)
        out.append(rec)
    report["seednet_only_rows_unlinked"] = len(rows) + skipped; report["seednet_only_rows_skipped_junk_names"] = skipped
    report["seednet_only_records_added"] = len(out); report["seednet_only_rows_merged_into_others"] = len(rows) - len(out)
    return out


def summary_counts(final: list[dict], report: dict) -> dict:
    """Every headline count a document would quote, computed from the final records (write next to the JSON as summary_counts.json)."""
    import collections as _c
    def cnt(key, rs=None): return dict(_c.Counter(str(r.get(key)) for r in (rs if rs is not None else final)).most_common())
    csc = [r for r in final if r.get("record_source") != "Seednet only"]; res = [r for r in final if r.get("enrichment_wave") != "not_researched"]
    years = [int(r["year_of_release"]) for r in final if str(r.get("year_of_release") or "").isdigit()]
    years_csc = [int(r["year_of_release"]) for r in csc if str(r.get("year_of_release") or "").isdigit()]
    cs = lambda r, k: bool((r.get("contacts_structured") or {}).get(k))  # noqa: E731
    out = {
        "built_at": report.get("built_at"), "records": len(final), "record_source": cnt("record_source"),
        "csc_records": len(csc), "seednet_only_records": len(final) - len(csc),
        "csc_outcome": cnt("csc_outcome"), "csc_outcome_csc_records": cnt("csc_outcome", csc),
        "seednet_match_status": cnt("seednet_match_status"), "seednet_match_status_csc_records": cnt("seednet_match_status", csc),
        "seednet_links_by_crop_word_dropped": sum(1 for r in final if r.get("seednet_match_reason") == "crop word dropped"),
        "researched_records": len(res), "official_data_only_records": len(final) - len(res), "enrichment_wave": cnt("enrichment_wave"),
        "stress_confirmation_level": cnt("stress_confirmation_level"), "stress_confirmation_level_researched": cnt("stress_confirmation_level", res),
        "stress_confirmation_level_csc_records": cnt("stress_confirmation_level", csc),
        "stress_level_changed_by_rules": sum(1 for r in final if r.get("stress_level_adjusted")),
        "stress_types_confirmed": dict(_c.Counter(t for r in final for t in r.get("stress_types_confirmed") or []).most_common()),
        "research_refers_to": cnt("research_refers_to"),
        "with_institution_contact": sum(1 for r in final if r.get("institution_contact")), "with_institution_contact_csc_records": sum(1 for r in csc if r.get("institution_contact")),
        "institution_contact_rejected_as_other_institution": sum(1 for r in final if str(r.get("institution_contact_check") or "").startswith("rejected")),
        "with_email": sum(1 for r in final if cs(r, "emails")), "with_phone": sum(1 for r in final if cs(r, "phones")), "with_breeder_name": sum(1 for r in final if cs(r, "breeder_names")),
        "with_email_csc_records": sum(1 for r in csc if cs(r, "emails")), "with_phone_csc_records": sum(1 for r in csc if cs(r, "phones")), "with_breeder_name_csc_records": sum(1 for r in csc if cs(r, "breeder_names")),
        "with_scholar_publications": sum(1 for r in final if r.get("publications_scholar")), "with_openalex_publications": sum(1 for r in final if r.get("publications_openalex")),
        "with_any_publication": sum(1 for r in final if r.get("publications_scholar") or r.get("publications_openalex")),
        "publication_entries_listed": sum(len(r.get("publications_scholar") or []) + len(r.get("publications_openalex") or []) for r in final),
        "publication_hits_dropped": {"scholar_not_about_variety": report.get("scholar_hits_dropped_as_not_about_the_variety"), "openalex_not_about_variety": report.get("openalex_hits_dropped_as_not_about_the_variety"),
                                     "duplicate_titles": report.get("publication_duplicate_titles_dropped")},
        "duplicates_merged": report.get("duplicate_crop_name_records_merged"), "records_with_merged_ids": sum(1 for r in final if r.get("merged_duplicate_ids")),
        "seednet_only_rows": {k: report.get(k) for k in ("seednet_only_rows_unlinked", "seednet_only_rows_skipped_junk_names", "seednet_only_rows_merged_into_others", "seednet_only_records_added")},
        "name_quality": cnt("name_quality"),
        "records_with_direct_csc_minutes_link": sum(1 for r in final if (r.get("official_sources") or {}).get("csc_minutes_url") or (r.get("official_sources") or {}).get("csc_minutes_archived_url")),
        "csc_records_without_direct_minutes_link": sum(1 for r in csc if not ((r.get("official_sources") or {}).get("csc_minutes_url") or (r.get("official_sources") or {}).get("csc_minutes_archived_url"))),
        "records_from_minutes_read_in_november_2026": sum(1 for r in final if str((r.get("csc_fields") or {}).get("extraction_timestamp") or "").startswith("2026-11")),
        "stress_graded_from_official_text_only": sum(1 for r in final if r.get("stress_basis") == "official text only" and r.get("stress_types_confirmed")),
        "stress_official_text_tagged_records": sum(1 for r in final if r.get("stress_official_text")),
        "seednet_links_by_alias_merge": report.get("seednet_links_by_alias_merge"),
        "names_changed_for_display": sum(1 for r in final if r.get("variety_name") != r.get("variety_name_as_printed")),
        "names_spelling_corrected": sum(1 for r in final if any(str(b_).startswith("spelling") for b_ in r.get("name_correction_basis") or [])),
        "records_with_related_record_ids": sum(1 for r in final if r.get("related_record_ids")),
        "disease_resistance_by_basis": dict(_c.Counter(r.get("disease_resistance_basis") or "none" for r in final)),
        "pest_resistance_by_basis": dict(_c.Counter(r.get("pest_resistance_basis") or "none" for r in final)),
        "with_disease_resistance": sum(1 for r in final if r.get("has_disease_resistance")), "with_pest_resistance": sum(1 for r in final if r.get("has_pest_resistance")),
        "with_official_yield": sum(1 for r in final if r.get("yield_kg_ha_min") not in ("", None)),
        "yield_class": dict(_c.Counter(r.get("yield_class") or "none" for r in final)),
        "high_yield_stated_officially": sum(1 for r in final if r.get("high_yield_stated_officially")),
        "diseases_resisted_top": dict(_c.Counter(n for r in final for n in (r.get("disease_resistance") or {}).get("diseases") or []).most_common(25)),
        "pests_resisted_top": dict(_c.Counter(n for r in final for n in (r.get("pest_resistance") or {}).get("pests") or []).most_common(25)),
        "with_direct_csc_minutes_link": sum(1 for r in final if (r.get("official_sources") or {}).get("csc_minutes_url") or (r.get("official_sources") or {}).get("csc_minutes_archived_url")),
        "year_of_release": {"min": min(years) if years else None, "max": max(years) if years else None, "blank": len(final) - len(years), "by_year": dict(sorted(_c.Counter(years).items()))},
        "year_of_release_csc_records": {"min": min(years_csc) if years_csc else None, "max": max(years_csc) if years_csc else None, "blank": len(csc) - len(years_csc),
                                        "by_year": dict(sorted(_c.Counter(years_csc).items())), "changed_by_year_rule": sum(1 for r in csc if "year_of_release_raw" in r)},
        "states": {"with_west_bengal": sum(1 for r in final if "West Bengal" in (r.get("states_full_clean") or []))},
        "crop_labels": len({r.get("crop_clean") for r in final}),
    }
    return out


def csc_year(r: dict):
    """Release year from the CSC decision only: approval date, else the year in the meeting title / minutes file name,
    else the extracted CSC 'year' unless those digits are part of the variety name (IPC 2004-98 is not from 2004). Never from the name."""
    cf = r.get("csc_fields") or {}
    now = datetime.now(UTC).year
    def ok(y): return y is not None and 1960 <= int(y) <= now
    m = re.match(r"\s*((?:19|20)\d\d)[-/]", str(cf.get("approval_date") or ""))
    if m and ok(m.group(1)): return int(m.group(1))
    m = re.search(r"(?:^|\D)(\d{1,2})[-/.](\d{1,2})[-/.]((?:19|20)\d\d)(?:\D|$)", str(cf.get("approval_date") or ""))
    if m and ok(m.group(3)): return int(m.group(3))
    for src in (cf.get("meeting_title"), cf.get("source_document_filename"), (r.get("official_sources") or {}).get("csc_source_document")):
        ys = [int(y) for y in re.findall(r"(?<!\d)((?:19|20)\d\d)(?!\d)", str(src or "")) if ok(y)]
        if ys: return max(ys)
    y = str(cf.get("year") or "").replace(".0", "").strip()
    if y.isdigit() and ok(y) and y not in re.findall(r"\d+", str(r.get("variety_name") or "") + " " + str(cf.get("variety_name") or "")): return int(y)
    return ""


def stub_records(master: Path, rematch: dict, existing: list[dict]) -> list[dict]:
    """CSC varieties that are in the master file but have no record yet (never matched in 2025, or collapsed into another
    record by the old Seednet-keyed id). They enter the dataset with their official CSC (and, when re-matched, Seednet)
    data and enrichment_wave = 'not_researched', so they can be found; `run_pipeline.py --stage enrich` researches them."""
    import pandas as pd
    from rematch_seednet import csc_key
    df = pd.read_excel(master) if master.suffix.lower() in (".xlsx", ".xls") else pd.read_csv(master, low_memory=False)
    existing = [r for r in existing if not r.get("_seednet_only_research")]  # a researched Seednet-only record is not a CSC row
    have = {csc_key((r.get("csc_fields") or {}).get("crop") or r.get("crop"), (r.get("csc_fields") or {}).get("variety_name") or r.get("variety_name")) for r in existing}
    ids = {r["variety_id"] for r in existing}
    def rank(row):  # prefer an approved decision, then the latest year
        st = str(row.get("approval_status") or "").lower()
        return (("approv" in st or "recommend" in st) and "defer" not in st and "not " not in st, float(row.get("year") or 0) if str(row.get("year")).replace(".", "").isdigit() else 0)
    groups: dict[str, list[dict]] = {}
    for row in df.to_dict("records"):
        k = csc_key(row.get("crop"), row.get("variety_name"))
        if k in have or not k.split("|")[1]: continue
        groups.setdefault(k, []).append(row)
    template = existing[0]; out = []
    for k, rows in sorted(groups.items()):
        row = max(rows, key=rank)
        od = {kk: (None if (isinstance(v, float) and v != v) else v) for kk, v in row.items()}
        rec = {kk: ([] if isinstance(v, list) else {} if isinstance(v, dict) else 0 if isinstance(v, (int, float)) and not isinstance(v, bool) else "" if isinstance(v, str) else None) for kk, v in template.items()}
        vid = "CSC__" + re.sub(r"[^\w\-]", "_", f"{str(od.get('crop'))[:20]}__{str(od.get('variety_name'))[:50]}")
        while vid in ids: vid += "_x"
        ids.add(vid)
        yr = od.get("year"); yr = int(yr) if yr is not None and str(yr).replace(".0", "").isdigit() else ""
        inst = od.get("institution"); inst = inst if inst and str(inst).strip().lower() not in NA_VALUES else ""
        loc = od.get("institution_location"); loc = loc if loc and str(loc).strip().lower() not in NA_VALUES else ""
        rec.update(variety_id=vid, variety_name=str(od.get("variety_name")), crop=str(od.get("crop") or ""), crop_clean=str(od.get("crop") or ""), year_of_release=yr,
                   states_full=[str(od.get("state_zone"))] if od.get("state_zone") and str(od.get("state_zone")).lower() not in NA_VALUES else [], states_full_clean=[],
                   developer_institution_csc=inst, developer_location_csc=loc, seednet_fields={}, seednet_url="", seednet_available="No", seednet_match="NO",
                   csc_fields={kk: (str(od[kk]) if not isinstance(od[kk], (int, float, str)) else od[kk]) for kk in CSC_KEEP if od.get(kk) is not None and str(od.get(kk)).strip().lower() not in NA_VALUES},
                   research_data={"basic_info": {"crop": str(od.get("crop") or ""), "variety_name": str(od.get("variety_name")), "data_source": "csc", "year": yr, "institution": inst or "Not specified"}},
                   stress_tolerance="Unknown", stress_tolerance_strict="Unknown", stress_types=[], stress_types_strict=[], trusted_stress_types=[],
                   stress_levels_gemini={k2: "unknown" for k2 in STRESS_LABELS}, gemini_analysis_status="not_researched", evidence_quality="Not researched",
                   _csc_source_document=od.get("source_document_filename") or od.get("source_file"), _csc_meeting=od.get("meeting_title") or od.get("meeting_number"),
                   _gazette_reference=od.get("gazette_notification_reference"), _not_researched=True)
        rec["csc_fields"]["meetings_considered"] = len(rows)
        out.append(rec)
    return out


def dedupe(records: list[dict], report: dict) -> list[dict]:
    synthetic = [r for r in records if "_DUP_" in str(r.get("variety_id", ""))]
    records = [r for r in records if "_DUP_" not in str(r.get("variety_id", ""))]
    best: dict[str, dict] = {}
    for r in records:
        vid = r["variety_id"]
        cur = best.get(vid)
        key = (analysis_ok(r), str(r.get("processing_timestamp", "")))
        if cur is None or key > (analysis_ok(cur), str(cur.get("processing_timestamp", ""))):
            best[vid] = r
    dup_ids = sorted(vid for vid in {r["variety_id"] for r in records}
                     if sum(1 for x in records if x["variety_id"] == vid) > 1)
    report.update(synthetic_records_rejected=len(synthetic), duplicate_variety_ids=len(dup_ids),
                  duplicate_variety_ids_list=dup_ids, unique_varieties=len(best),
                  varieties_with_gemini_analysis=sum(analysis_ok(r) for r in best.values()),
                  varieties_with_gemini_error=sum(not analysis_ok(r) for r in best.values()))
    return [best[k] for k in sorted(best)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input-dir", required=True, type=Path, nargs="+", help="one or more folders of enhanced_batch_*.json (e.g. the Aug-2025 run and a completion run)")
    ap.add_argument("--output-dir", required=True, type=Path)
    ap.add_argument("--expect", type=int, default=None, help="fail (exit 2) unless unique variety count equals this")
    ap.add_argument("--scholar", type=Path, default=None, help="publications_scholar.json from enrich/scholar_publications.py; adds publications_scholar[_count] per record")
    ap.add_argument("--institutions", type=Path, default=None, help="institution_contacts.json from enrich/institution_contacts.py; adds institution_contact per record")
    ap.add_argument("--scholar-by-csc", type=Path, default=None, help="publications_scholar_by_csc_key.json (scholar_publications.py --by-csc-key); replaces --scholar with a strict per-variety name filter and covers CSC-only records")
    ap.add_argument("--master", type=Path, default=None, help="master CSC xlsx/csv; with --seednet-rematch, CSC varieties that have no record yet are added as official-data-only records")
    ap.add_argument("--seednet-rematch", type=Path, default=None, help="seednet_rematch.json from dashboard/rematch_seednet.py (strict CSC -> Seednet matching)")
    ap.add_argument("--stress-confirmation", type=Path, default=None, help="stress_confirmation.json from enrich/confirm_stress.py; adds stress_confirmation, stress_types_confirmed, stress_confirmation_level")
    ap.add_argument("--add-seednet-only", action="store_true", help="add one record per Seednet variety that no CSC record links to (record_source = 'Seednet only'); needs --seednet-raw")
    ap.add_argument("--seednet-raw", type=Path, default=None, help="seednet_data.csv (the full Seednet table) for --add-seednet-only")
    ap.add_argument("--csc-links", type=Path, default=None, help="csc_document_links.csv: direct URLs of CSC minutes PDFs (rows with confidence high/medium are used)")
    ap.add_argument("--openalex", type=Path, default=None, help="publications_openalex.json from enrich/openalex_publications.py; adds publications_openalex[_count] per record")
    a = ap.parse_args()
    a.output_dir.mkdir(parents=True, exist_ok=True)
    report = {"built_at": datetime.now(UTC).isoformat(), "input_dirs": [str(d.resolve()) for d in a.input_dir]}

    raw, per_dir = [], []
    for d in a.input_dir:
        sub = {}
        raw += load_batches(d, sub); per_dir.append({"input_dir": str(d.resolve()), **sub})
    report.update(per_input_dir=per_dir, batch_files=sum(x["batch_files"] for x in per_dir), raw_records=len(raw),
                  malformed_batch_files=[m for x in per_dir for m in x["malformed_batch_files"]])
    if not raw:
        print("ERROR: no enhanced_batch_*.json records found in", [str(d) for d in a.input_dir]); return 2
    unique = dedupe(raw, report)

    processed, errors = [], []
    for i, v in enumerate(unique):
        try:
            rec = bed.process_single_variety(v, i); od = v.get("original_data") or {}
            rec["_csc_source_document"] = od.get("source_document_filename") or od.get("source_file"); rec["_csc_meeting"] = od.get("meeting_title") or od.get("meeting_number")
            rec["_gazette_reference"] = od.get("gazette_notification_reference")
            rec["csc_fields"] = {k: od.get(k) for k in CSC_KEEP if od.get(k) is not None and str(od.get(k)).strip().lower() not in NA_VALUES}
            # developing institution as recorded in the CSC release minutes (official, ~90% filled)
            inst_csc = od.get("institution"); loc_csc = od.get("institution_location")
            rec["developer_institution_csc"] = inst_csc if inst_csc and str(inst_csc).strip().lower() not in ("nan", "not specified", "none", "unknown") else ""
            rec["developer_location_csc"] = loc_csc if loc_csc and str(loc_csc).strip().lower() not in ("nan", "not specified", "none", "unknown") else ""
            # a research batch for a Seednet-only variety (redo wave) carries an original_data built from the final record, not from the CSC minutes
            rec["_seednet_only_research"] = bool(str(v.get("variety_id", "")).startswith("SEEDNET__") or (od.get("redo_reason") and not od.get("source_document_filename")))
            if rec["_seednet_only_research"]:
                rec["csc_fields"] = {}; rec["developer_institution_csc"] = ""; rec["developer_location_csc"] = ""
                rec["_csc_source_document"] = None; rec["_csc_meeting"] = None; rec["_gazette_reference"] = None
            processed.append(rec)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{v.get('variety_id')}: {e}")
    report.update(records_processed=len(processed), processing_errors=errors)

    # stage 1 outputs (same names as the original builder)
    bed.write_csv(processed, str(a.output_dir / "varieties_compiled_enhanced.csv"))
    bed.write_json(processed, str(a.output_dir / "varieties_complete.json"))

    # stage 2: hyperlink enrichment, redirected to output_dir
    bfh.BASE_DIR = a.output_dir
    bfh.INPUT_JSON = a.output_dir / "varieties_complete.json"
    bfh.OUTPUT_JSON = a.output_dir / "final_varieties_hyperlinked.json"
    import tempfile as _tf  # the researched-only flat CSV of the 2025 builder is not written any more (the tables in out_v4/tables cover all records)
    bfh.OUTPUT_CSV = Path(_tf.mkdtemp()) / "final_varieties_hyperlinked.csv"
    (a.output_dir / "final_varieties_hyperlinked.csv.SUPERSEDED.txt").write_text(
        "final_varieties_hyperlinked.csv is no longer written (it held only the researched records); use tables/STS_India_*.csv or STS_India_varieties_FINAL.xlsx.\n", encoding="utf-8")
    bfh.OUTPUT_LINKS_LONG_CSV = a.output_dir / "final_varieties_links_long.csv"
    bfh.OUTPUT_ANALYSIS_JSON = a.output_dir / "final_varieties_showcase_analysis.json"
    bfh.main()

    final = [add_strict_stress_fields(r) for r in json.loads(bfh.OUTPUT_JSON.read_text(encoding="utf-8"))]
    if a.openalex:
        oa = json.loads(a.openalex.read_text(encoding="utf-8"))
        for r in final:
            pubs = oa.get(r["variety_id"], [])
            r["_openalex_all"] = pubs; r["publications_openalex"] = pubs[:25]; r["publications_openalex_count"] = len(pubs)
        report["openalex_varieties_with_publications"] = sum(1 for r in final if r["publications_openalex_count"])
    if a.scholar:
        sc = json.loads(a.scholar.read_text(encoding="utf-8"))
        for r in final:
            pubs = sc.get(r["variety_id"], [])
            r["publications_scholar"] = pubs[:25]; r["publications_scholar_count"] = len(pubs)
        report["scholar_varieties_with_publications"] = sum(1 for r in final if r["publications_scholar_count"])
    inst = json.loads(a.institutions.read_text(encoding="utf-8")) if a.institutions and a.institutions.exists() else {}
    if inst:
        import importlib.util as _il
        spec = _il.spec_from_file_location("institution_contacts", HERE.parent / "enrich" / "institution_contacts.py"); mod = _il.module_from_spec(spec); spec.loader.exec_module(mod)
        inst_index = InstitutionIndex(inst, mod.SKIP, mod.canon)
    rematch = json.loads(a.seednet_rematch.read_text(encoding="utf-8")) if a.seednet_rematch and a.seednet_rematch.exists() else {}
    if a.master and rematch:
        stubs = stub_records(a.master, rematch, final); final += stubs; report["csc_only_records_added"] = len(stubs)
        for r in final:
            r.setdefault("publications_openalex", []); r.setdefault("publications_openalex_count", 0); r.setdefault("publications_scholar", []); r.setdefault("publications_scholar_count", 0)
    for r in final: apply_match_status(r, rematch)
    from match_rules import CONFIRMED as _CONF
    from standardize import name_quality
    for r in final:  # 2026-11: name quality, release year from the CSC decision, and two link gates (name quality, Seednet year far before CSC year)
        r["name_quality"] = name_quality(r.get("variety_name"))
        y_old = r.get("year_of_release"); y_new = csc_year(r)
        if str(y_old or "") != str(y_new or ""): r["year_of_release_raw"] = y_old
        r["year_of_release"] = y_new
        if r.get("seednet_match_status") in _CONF:
            sf = r.get("seednet_fields") or {}; sy = str(sf.get("Year of Release") or "").strip()
            if r["name_quality"] != "ok":
                _to_candidate(r, "needs_review", f"CSC variety name is {r['name_quality']} ('{r.get('variety_name')}'), so a name match cannot identify one variety")
            elif re.fullmatch(r"(19|20)\d\d", sy) and y_new and int(y_new) - int(sy) >= 5:
                _to_candidate(r, "needs_review", f"Seednet release year {sy} is {int(y_new) - int(sy)} years before the CSC year {y_new}: probably an older variety of the same name")
    for r in final:
        if r.get("_seednet_only_research"):  # researched Seednet-only variety: still not from the CSC minutes
            r["record_source"] = "Seednet only"; r["seednet_match_status"] = "seednet_only"; r["seednet_match_reason"] = "Seednet entry researched; not in the CSC minutes held"
            sf_ = r.get("seednet_fields") or {}; y_ = str(sf_.get("Year of Release") or "").strip()
            r["year_of_release"] = int(y_) if re.fullmatch(r"(19|20)\d\d", y_) and 1960 <= int(y_) <= datetime.now(UTC).year else ""
            continue
        r["record_source"] = "CSC minutes and Seednet" if r.get("seednet_match_status") in _CONF else "CSC minutes only"
    if a.add_seednet_only:
        if not (a.seednet_raw and a.seednet_raw.exists()): print("ERROR: --add-seednet-only needs --seednet-raw <seednet_data.csv>"); return 2
        final += seednet_only_records(a.seednet_raw, final, report)
    report["name_quality"] = {k: sum(1 for r in final if r["name_quality"] == k) for k in ("ok", "generic", "truncated", "numeric_only")}
    report["seednet_crop_word_dropped_links"] = sum(1 for r in final if r.get("seednet_match_reason") == "crop word dropped")
    _n = lambda x: re.sub(r"[^a-z0-9]", "", str(x or "").lower())  # noqa: E731
    sch = json.loads(a.scholar_by_csc.read_text(encoding="utf-8")) if a.scholar_by_csc and a.scholar_by_csc.exists() else None
    from rematch_seednet import csc_key as _ck
    from pub_relevance import relevant, title_key
    from standardize import name_quality as _nq
    dropped_pubs = dropped_oa = dropped_dupes = 0
    for r in final:  # publications must be about THIS variety: drop hits that were found by querying a wrongly attached Seednet name
        cf = r.get("csc_fields") or {}; allowed = {_n(r.get("variety_name")), _n(cf.get("variety_name")), _n((r.get("seednet_fields") or {}).get("Variety Name"))} - {""}
        names_ = [x for x in {r.get("variety_name"), cf.get("variety_name"), (r.get("seednet_fields") or {}).get("Variety Name"), cf.get("variety_code")} if x and str(x).lower() not in NA_VALUES]
        names_ += [c for n in list(names_) for c in re.findall(r"\(([^)]{3,})\)", str(n))]
        names_ = [x for x in names_ if _nq(x) == "ok"]  # generic / truncated names ('Cotton', 'CO', a Seednet 'Field pea') never search
        crops_ = [r.get("crop"), cf.get("crop"), (r.get("seednet_fields") or {}).get("Crop Name")]
        ok_name = r["name_quality"] == "ok" and bool(names_)
        oa_all = r.pop("_openalex_all", None)
        oa_all = oa_all if oa_all is not None else (r.get("publications_openalex") or [])
        oa_ = [w for w in oa_all if ok_name and (not w.get("query_name") or _n(w.get("query_name")) in allowed) and relevant(names_, crops_, w.get("title"), w.get("snippet"), aliases=names_)]
        dropped_oa += len(oa_all) - len(oa_)
        pubs = r.get("publications_scholar") or []
        if sch is not None:
            pubs = sch.get(_ck(cf.get("crop") or r.get("crop"), cf.get("variety_name") or r.get("variety_name")), [])
            dropped_pubs += len(pubs); pubs = [w for w in pubs if ok_name and relevant(names_, crops_, w.get("title"), w.get("snippet"), aliases=names_)]; dropped_pubs -= len(pubs)
        seen = set(); oa_d = []
        for w in oa_:  # one entry per title: OpenAlex first (it has a DOI), then Scholar entries whose title is not already listed
            k = title_key(w.get("title"))
            if k and k in seen: dropped_dupes += 1; continue
            seen.add(k); oa_d.append(w)
        sc_d = []
        for w in pubs:
            k = title_key(w.get("title"))
            if k and k in seen: dropped_dupes += 1; continue
            seen.add(k); sc_d.append(w)
        r["publications_openalex_total"] = len(oa_d); r["publications_openalex"] = oa_d[:25]; r["publications_openalex_count"] = len(r["publications_openalex"])
        r["publications_scholar_total"] = len(sc_d); r["publications_scholar"] = sc_d[:25]; r["publications_scholar_count"] = len(r["publications_scholar"])
    report["scholar_hits_dropped_as_not_about_the_variety"] = dropped_pubs
    report["openalex_hits_dropped_as_not_about_the_variety"] = dropped_oa
    report["publication_duplicate_titles_dropped"] = dropped_dupes
    report["scholar_varieties_with_publications"] = sum(1 for r in final if r.get("publications_scholar_count")); report["openalex_varieties_with_publications"] = sum(1 for r in final if r.get("publications_openalex_count"))
    report["seednet_rematched_records"] = sum(1 for r in final if r.get("seednet_rematched"))
    report["seednet_match_status"] = {k: sum(1 for r in final if r["seednet_match_status"] == k) for k in sorted({r["seednet_match_status"] for r in final})}
    csc_links: dict[str, dict] = {}
    if a.csc_links and a.csc_links.exists():
        import csv as _csv
        with a.csc_links.open(encoding="utf-8-sig", newline="") as fh:
            for row in _csv.DictReader(fh):
                if str(row.get("confidence") or "").strip().lower() in ("high", "medium") and (row.get("url") or row.get("wayback_url")):
                    csc_links[str(row.get("csc_source_document") or "").strip()] = row
    report["csc_minutes_links_loaded"] = len(csc_links)
    for r in final:
        # official government sources behind the record: Seednet page, CSC meeting document, Gazette notification
        od = (r.get("research_data") or {}).get("basic_info") or {}
        sf = r.get("seednet_fields") or {}
        r["official_sources"] = {k: v for k, v in {
            "seednet_url": r.get("seednet_url"), "seednet_notification_number": sf.get("Notification Number"), "seednet_notification_date": sf.get("Notification Date"),
            "csc_source_document": r.get("_csc_source_document"), "csc_meeting": r.get("_csc_meeting"), "gazette_reference": r.get("_gazette_reference"), "csc_minutes_list_page": CSC_LIST_PAGE}.items() if v not in (None, "") and str(v).strip().lower() not in ("nan", "not specified", "none", "unknown")}
        for k in ("_csc_source_document", "_csc_meeting", "_gazette_reference"): r.pop(k, None)
        lk = csc_links.get(str(r["official_sources"].get("csc_source_document") or "").strip())
        if lk:
            r["official_sources"].update({k: v for k, v in (("csc_minutes_url", lk.get("url")), ("csc_minutes_archived_url", lk.get("wayback_url")),
                                                              ("csc_minutes_link_basis", f"{lk.get('match_basis') or ''} (confidence {lk.get('confidence')})".strip())) if v})
        if inst:
            far = (r.get("research_data") or {}).get("full_analysis_result") or {}; bc = far.get("breeder_and_contacts") if isinstance(far, dict) else {}
            assign_institution_contact(r, sf, bc if isinstance(bc, dict) else {}, inst_index)
        report["records_with_institution_contact"] = sum(1 for r in final if r.get("institution_contact"))
    from standardize import STATE_CODES, standardize_crop, standardize_states
    BAD = re.compile("[\ufffd]+")  # mojibake from the CSC PDF extraction (e.g. an en dash read as bytes)
    def unmoji(v):
        if v is None: return v
        if not isinstance(v, str): v = str(v)   # some CSC names are numeric codes; keep everything a string
        return BAD.sub("-", v)
    SECRET = re.compile(r"AIza[0-9A-Za-z_-]{35}|sk-ant-[A-Za-z0-9_-]{20,}|(?<=[?&]key=)[A-Za-z0-9_-]{20,}|(?<=[?&]api_key=)[A-Za-z0-9_-]{20,}")
    def deep_unmoji(x):  # every string anywhere in the record; also redacts API keys that old error messages quoted inside request URLs
        if isinstance(x, str): return SECRET.sub("REDACTED", BAD.sub("-", x))
        if isinstance(x, list): return [deep_unmoji(v) for v in x]
        if isinstance(x, dict): return {k: deep_unmoji(v) for k, v in x.items()}
        return x
    final = [deep_unmoji(r) for r in final]
    for r in final:
        for k in ("variety_name", "crop", "crop_clean"):
            r[k] = unmoji(r.get(k))
    for r in final:  # canonical crop and state names (originals kept as *_raw)
        sf = r.get("seednet_fields") or {}
        r["crop_raw"] = r.get("crop"); r["crop_clean_raw"] = r.get("crop_clean")
        r["crop_clean"] = standardize_crop(sf.get("Crop Name"), r.get("crop"))
        r["states_full_raw"] = r.get("states_full_clean")
        states = standardize_states((r.get("states_full_clean") or []) + (r.get("states_full") or []) + [sf.get("Recommended States") or ""])
        r["states_full_clean"] = states; r["states_codes_clean"] = [STATE_CODES[s] for s in states]; r["states_acronyms_clean"] = ", ".join(r["states_codes_clean"])
    EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"); PHONE = re.compile(r"(?:\+91[\s-]?)?(?:\(?0?\d{2,5}\)?[\s-]?)?\d{3,4}[\s-]?\d{3,4}(?:[\s-]?\d{2,4})?")
    PHONE_CTX = re.compile(r"(?:phone|tel(?:ephone)?|mob(?:ile)?|fax|ph|contact(?: no)?|call)\s*[.:#-]*\s*((?:\+?\d[\d\s()/,-]{8,40}))", re.IGNORECASE)
    BAD_EMAIL = re.compile(r"(example\.|\.png$|\.jpg$|\.gif$|sentry|wixpress|@2x|noreply|no-reply)", re.IGNORECASE)
    def _phones(text):  # 10+ digits, not a year range or a date
        out = set()
        for m in PHONE.findall(text):
            dg = sum(ch.isdigit() for ch in m)
            if 10 <= dg <= 13: out.add(re.sub(r"\s+", " ", m.strip()))
        return out
    for r in final:  # contacts as SEPARATE fields, mined from EVERYTHING pulled for the record: research text, Seednet, CSC minutes, institution lookup
        far = (r.get("research_data") or {}).get("full_analysis_result") or {}; bc = far.get("breeder_and_contacts") if isinstance(far, dict) else {}; bc = bc if isinstance(bc, dict) else {}
        ic = r.get("institution_contact") or {}; sf = r.get("seednet_fields") or {}; cf = r.get("csc_fields") or {}
        txt = " ".join(str(bc.get(k) or "") for k in ("breeder", "contacts", "institution"))
        everything = json.dumps([r.get("research_data"), sf, cf], ensure_ascii=False)
        everything = re.sub(r"\s*[\[(]\s*at\s*[\])]\s*", "@", re.sub(r"\s*[\[(]\s*dot\s*[\])]\s*", ".", everything), flags=re.IGNORECASE)
        ic = {**ic, "emails": [re.sub(r"\s*[\[(]\s*at\s*[\])]\s*", "@", re.sub(r"\s*[\[(]\s*dot\s*[\])]\s*", ".", str(e), flags=re.IGNORECASE), flags=re.IGNORECASE) for e in (ic.get("emails") or []) if e]}
        ic_txt = " ".join(str(ic.get(k) or "") for k in ("variety_or_seed_contact", "head_or_director", "postal_address", "contact_page"))
        emails = sorted(e for e in ({e.lower().rstrip(".") for e in EMAIL.findall(everything + " " + ic_txt)} | {str(e).lower() for e in (ic.get("emails") or []) if e}) if not BAD_EMAIL.search(e))
        ctx_phones = set()
        for m in PHONE_CTX.findall(everything + " " + ic_txt): ctx_phones |= _phones(m)
        phones = sorted(_phones(txt) | ctx_phones | {str(pn) for pn in (ic.get("phones") or []) if pn})
        br = str(bc.get("breeder") or ""); names = [] if br.lower().startswith(("not found", "no ", "none", "not specified")) else [n.strip() for n in re.split(r";|\band\b|,(?=\s*(?:Dr|Prof|Mr|Ms|Shri|Smt)\.?)", br) if n.strip()][:6]
        pi = cf.get("principal_investigator")
        if pi and str(pi) not in names: names.append(str(pi))
        names, _other = person_names(names)
        phones, fax, phone_notes = clean_phones(phones); emails = clean_emails(emails)
        if r.get("institution_contact"):
            ip, ifax, _ = clean_phones(r["institution_contact"].get("phones")); r["institution_contact"]["phones"] = ip; r["institution_contact"]["fax"] = ifax
            r["institution_contact"]["emails"] = clean_emails(r["institution_contact"].get("emails"))
        note = str(bc.get("contacts") or "")[:600]
        if (emails or phones) and re.search(r"no (specific )?contact (information|details)|no information available|not found in (the )?(searched|provided)|no (email|phone)", note, re.IGNORECASE): note = ""
        if _other: note = (note + " | " if note else "") + "Breeder text (not a person name): " + " / ".join(_other)[:400]
        r["contacts_structured"] = {"breeder_names": names, "emails": emails, "phones": phones, "fax": fax, "phone_notes": phone_notes,
            "addresses": [a for a in [ic.get("postal_address")] if a], "institution": ic.get("institution_official_name") or r.get("developer_institution_csc") or bc.get("institution") or "",
            "institution_type": ic.get("type") or "", "head_or_director": ic.get("head_or_director") or "", "variety_or_seed_contact": ic.get("variety_or_seed_contact") or "",
            "breeder_seed_institution_seednet": sf.get("Institution Responsible for developing Breeder Seed") or "", "institution_location_csc": r.get("developer_location_csc") or "",
            "website": ic.get("website") or "", "contact_page": ic.get("contact_page") or "", "contact_source_urls": ic.get("source_urls") or [], "notes": note}
    report["records_with_email"] = sum(1 for r in final if r["contacts_structured"]["emails"]); report["records_with_phone"] = sum(1 for r in final if r["contacts_structured"]["phones"])
    report["crop_labels"] = len({r["crop_clean"] for r in final}); report["state_labels"] = len({s for r in final for s in r["states_full_clean"]})
    conf = json.loads(a.stress_confirmation.read_text(encoding="utf-8")) if a.stress_confirmation and a.stress_confirmation.exists() else {}
    for r in final:  # secondary confirmation of each stress claim (enrich/confirm_stress.py); never upgrades a claim, only grades it
        c = conf.get(r["variety_id"])
        wave_now = "not_researched" if r.get("_not_researched") else (r.get("research_data") or {}).get("full_analysis_result", {}).get("processing_metadata", {}).get("processing_version") or "enhanced_v2.1_20250808"
        if c and (c.get("wave") != wave_now if c.get("wave") else "_redo_" in wave_now): c = None  # grade was made for an earlier research wave
        if not c:
            r["stress_confirmation"] = None; r["stress_types_confirmed"] = []; r["stress_types_multi_source"] = []; r["research_refers_to"] = "not checked"
            r["stress_confirmation_level"] = ("Not graded" if r.get("record_source") == "Seednet only" else "Not researched" if r.get("_not_researched") else NONE_FOUND if conf and not r.get("stress_types_strict") else "Not checked"); continue
        far_ = (r.get("research_data") or {}).get("full_analysis_result") or {}; sblk = far_.get("stress_tolerance") if isinstance(far_, dict) else {}
        ev = {k: (blk or {}).get("evidence_sources") or [] for k, blk in (sblk or {}).items() if isinstance(blk, dict)}
        r["research_refers_to"] = c.get("research_refers_to", "unclear"); r["stress_confirmation_note"] = c.get("note", "")
        st = adjust_stress(c.get("stresses") or {}, crop=r.get("crop_clean") or "", refers_to=r["research_refers_to"], evidence_urls=ev)
        r["stress_confirmation"] = st
        r["stress_types_confirmed"] = [STRESS_LABELS[k] for k in STRESS_LABELS if (st.get(k) or {}).get("verdict") in ("confirmed_multi_source", "single_source")]
        r["stress_types_multi_source"] = [STRESS_LABELS[k] for k in STRESS_LABELS if (st.get(k) or {}).get("verdict") == "confirmed_multi_source"]
        claimed = bool(r.get("stress_types_strict")) or any((v or {}).get("verdict_model") not in (None, "not_claimed") for v in st.values())
        r["stress_confirmation_level"] = ("Confirmed by 2+ sources" if r["stress_types_multi_source"] else "Single source" if r["stress_types_confirmed"]
                                          else "Claimed, not confirmed" if claimed else NONE_FOUND)
        r["stress_basis"] = "official text only" if r.get("_not_researched") else "research and official text"
        r["stress_level_adjusted"] = any((v or {}).get("verdict") != (v or {}).get("verdict_model") for v in st.values())
    gained = {}
    for r in final:  # official Seednet / CSC text, tagged by rule: grades records that have no model grade, adds a source where a grade missed it
        tags, avail = official_stress_tags(r)
        r["stress_official_text"] = tags; r["stress_text_available"] = avail
        if not tags: continue
        sc = r.get("stress_confirmation")
        if not sc:
            r["stress_types_confirmed"] = [STRESS_LABELS[k] for k in STRESS_LABELS if k in tags]; r["stress_types_multi_source"] = []
            r["stress_confirmation_level"] = "Single source"; r["stress_basis"] = "official text only"
            gained[r.get("record_source")] = gained.get(r.get("record_source"), 0) + 1
            continue
        changed = False
        for k, tag in tags.items():
            v = sc.get(k) or {"verdict": "not_claimed", "independent_sources": 0, "official_support": False, "research_support": False, "basis": ""}
            if v.get("verdict") in ("confirmed_multi_source", "single_source"): continue
            n = int(v.get("independent_sources") or 0) if v.get("verdict_model") in ("confirmed_multi_source", "single_source") else 0
            n += 1
            v.update(verdict_model=v.get("verdict_model", v.get("verdict")), verdict="confirmed_multi_source" if n >= 2 else "single_source", independent_sources=n, official_support=True,
                     verdict_adjusted_reason=((v.get("verdict_adjusted_reason") or "") + "; " if v.get("verdict_adjusted_reason") else "") + f"official text states it ({tag['field']}: \"{tag['quote'][:120]}\")")
            v["label"] = CONFIRMATION_LABEL.get(v["verdict"], "Not confirmed"); sc[k] = v; changed = True
        if changed:
            r["stress_types_confirmed"] = [STRESS_LABELS[k] for k in STRESS_LABELS if (sc.get(k) or {}).get("verdict") in ("confirmed_multi_source", "single_source")]
            r["stress_types_multi_source"] = [STRESS_LABELS[k] for k in STRESS_LABELS if (sc.get(k) or {}).get("verdict") == "confirmed_multi_source"]
            r["stress_confirmation_level"] = "Confirmed by 2+ sources" if r["stress_types_multi_source"] else "Single source"
            r["stress_level_adjusted"] = True
            gained["graded record, official text added"] = gained.get("graded record, official text added", 0) + 1
    report["stress_official_text_grades"] = gained
    for r in final:  # vocabulary: 'Not graded' / 'Not researched' only for records WITHOUT web research
        researched = not r.get("_not_researched")
        lvl = r.get("stress_confirmation_level")
        if researched and lvl in ("Not graded", "Not researched", "Not checked"):
            r["stress_confirmation_level"] = "Claimed, not confirmed" if r.get("stress_types_strict") else NONE_FOUND
        elif not researched and lvl in ("Not graded", "Not researched", "Not checked"):
            r["stress_confirmation_level"] = "Not researched" if r.get("stress_text_available") else "Not graded"
    if conf:
        report["stress_confirmation_level"] = {k: sum(1 for r in final if r["stress_confirmation_level"] == k) for k in sorted({r["stress_confirmation_level"] for r in final})}
    for r in final:  # provenance of the enrichment wave, surfaced at top level
        if r.pop("_not_researched", False): r["enrichment_wave"] = "not_researched"; continue
        r["enrichment_wave"] = (r.get("research_data") or {}).get("full_analysis_result", {}).get("processing_metadata", {}).get("processing_version") or "enhanced_v2.1_20250808"
    # ---- final clean-up: one record per (canonical crop, variety name), tidy types ----
    def _tidy(v):  # CSC values as plain text: no time-of-day on dates, no Python list syntax
        if isinstance(v, float) and v == int(v): return int(v)
        if not isinstance(v, str): return v
        v = re.sub(r"\s+00:00:00(\.0+)?", "", v).strip()
        if re.fullmatch(r"\[.*\]", v): v = ", ".join(x.strip(" '\"") for x in v[1:-1].split(",") if x.strip(" '\""))
        return v
    for r in final:
        if isinstance(r.get("csc_fields"), dict): r["csc_fields"] = {k: _tidy(v) for k, v in r["csc_fields"].items()}
    for r in final:
        r["seednet_available"] = bool((r.get("seednet_fields") or {}).get("Variety Name"))
        y = str(r.get("year_of_release") or "").replace(".0", "").strip()
        if not (y.isdigit() and 1960 <= int(y) <= datetime.now(UTC).year):
            if "year_of_release_raw" not in r: r["year_of_release_raw"] = r.get("year_of_release")
            y = ""
        r["year_of_release"] = int(y) if y else ""
        r["variety_name"] = re.sub(r"\s+", " ", str(r.get("variety_name") or "")).strip(" -")
        if r["enrichment_wave"] == "not_researched": r["stress_tolerance"] = ""; r["evidence_quality"] = ""
    def _outcome(st) -> str:
        """CSC decision in four classes, from the free-text approval_status of the minutes."""
        t = str(st or "").lower()
        if not t.strip() or t.strip() in NA_VALUES: return "Not stated"
        if re.search(r"reject|not approved|not recommended|not accepted|not agreed|not considered|withdrawn|dropped|declin", t): return "Rejected"
        if re.search(r"defer|pending|kept in abeyance|resubmit|re-submit|revised proposal|postpon|to be reconsidered|received for consideration|under consideration", t): return "Deferred"
        if re.search(r"approv|recommend|notif|released|accepted|agreed|identified|extension", t): return "Approved"
        return "Not stated"
    for r in final: r["csc_outcome"] = "Not in the CSC minutes held" if r.get("record_source") == "Seednet only" else _outcome((r.get("csc_fields") or {}).get("approval_status"))
    report["csc_outcome"] = {k: sum(1 for r in final if r["csc_outcome"] == k) for k in ("Approved", "Deferred", "Rejected", "Not stated", "Not in the CSC minutes held")}
    # blank means "not stated": placeholder words from the sources and the models are removed from the official and contact fields
    PLACEHOLDER = re.compile(r"^\s*(unknown|not specified.*|not found.*|not available.*|n/?a|nan|nat|none|null|not stated.*|not mentioned.*|no information.*|-+|—|#+|kg/ha|days)\s*\.?\s*$", re.IGNORECASE)
    def _blank(v): return "" if isinstance(v, str) and PLACEHOLDER.match(v) else v
    for r in final:
        for k in ("seednet_fields", "seednet_candidate_fields"):
            if isinstance(r.get(k), dict) and str(r[k].get("Year of Release") or "").strip() in ("0", "0000", "00"): r[k]["Year of Release"] = ""
    for r in final:
        for k in ("seednet_fields", "seednet_candidate_fields", "csc_fields", "contacts_structured", "official_sources"):
            if isinstance(r.get(k), dict): r[k] = {kk: _blank(vv) for kk, vv in r[k].items()}
        for k in ("seasons", "days_to_maturity", "developer_institution_csc", "developer_location_csc", "key_attributes"):
            r[k] = _blank(r.get(k)) if r.get(k) is not None else ""
        if isinstance(r.get("contacts_structured"), dict):
            cs = r["contacts_structured"]; cs["breeder_names"] = [n for n in cs.get("breeder_names") or [] if n and not PLACEHOLDER.match(str(n)) and len(str(n)) <= 80]
    _INST_PLACEHOLDER = re.compile(r"not (explicitly )?(stated|specified|available|mentioned|given)|inferred|implied|^n/?a\b|unknown|^central varieties$|for central varieties", re.IGNORECASE)
    from standardize import STATES as _STATES
    for r in final:  # placeholder institution names: blank (the original is kept in *_raw)
        v = str(r.get("developer_institution_csc") or "").strip()
        if v and (_INST_PLACEHOLDER.search(v) or v.lower() in {x.lower() for x in _STATES} or re.fullmatch(r"[A-Za-z ]+\s*/\s*\d{4}|[A-Za-z ]+ \d{4}", v)):
            r["developer_institution_csc_raw"] = v; r["developer_institution_csc"] = ""
            if isinstance(r.get("contacts_structured"), dict) and r["contacts_structured"].get("institution") == v: r["contacts_structured"]["institution"] = ""
        r.setdefault("stress_basis", "not researched" if r["enrichment_wave"] == "not_researched" else "")
    final = [scrub_record(r) for r in final]
    corrections = load_name_corrections(); codes = name_codes(final)
    for r in final: display_name(r, codes, corrections)
    report["names_changed_for_display"] = sum(1 for r in final if r["variety_name"] != r["variety_name_as_printed"])
    report["names_spelling_corrected"] = sum(1 for r in final if any(b_.startswith("spelling") for b_ in r.get("name_correction_basis") or []))
    # ---- duplicates: within one canonical crop, records are the same variety when a normalised name of one equals a name / bracket alias /
    # breeding code ('HD 3086', 'PBW 343') / crop-word-stripped name of the other. Seednet-only rows merge into the CSC record (and become its
    # Seednet link when it has none, status confirmed_spelling, reason 'alias'). Parental-line codes inside a name are NOT keys (they join
    # different hybrids that share a parent); a bracket alias is. Two CSC records with a different outcome or year are not
    # merged but linked through related_record_ids; a Seednet row that the strict rules rejected for a CSC record never merges into it.
    from match_rules import CONFIRMED as _C2, _aliases, _strip_paren, crop_word_variant, fix_brackets, name_key
    from standardize import name_is_distinctive
    def _rank(r): return (r.get("record_source") != "Seednet only", r["enrichment_wave"] != "not_researched", r["seednet_available"], len(json.dumps(r.get("research_data") or {})), len(r.get("csc_fields") or {}))
    _CODE = re.compile(r"(?<![A-Za-z])([A-Z]{2,6})\s*[-.]?\s*(\d{3,6}[A-Za-z]?)(?![\d])")
    from standardize import name_quality as _nq2
    def _forms(nm: str, crop: str) -> set[str]:
        ks = {name_key(nm)} if _nq2(nm) == "ok" else set()  # 'Bajra', 'Barley', 'CO' never join two records
        for form in [_strip_paren(nm)] + _aliases(nm) + [crop_word_variant(nm, crop)]:
            f = name_key(form)
            if f and name_is_distinctive(form) and (re.search(r"\d", f) or len(f) >= 6): ks.add(f)
        return {k for k in ks if k}
    def _skeleton(nm: str) -> str:
        """Spelling skeleton for long names with a number: 'Bhadshabhog Selection-1' = 'Badshabhog Selection-1' (h after a consonant, doubled letters)."""
        core = _strip_paren(nm).lower()
        if not re.search(r"\d", core) or len(re.sub(r"[^a-z]", "", core)) < 10: return ""
        t = re.sub(r"(?<=[bcdgjkpstr])h", "", core); t = re.sub(r"([a-z])\1+", r"\1", t)
        return "sk:" + name_key(t)
    def _keys(r):
        # keys come ONLY from the name itself (as printed and as displayed) and its bracket aliases, and the linked Seednet name; never from
        # free-text fields such as csc_fields.variety_code ('Not Applicable' once joined 20 rice varieties) or a spelling skeleton
        crop = r["crop_clean"]; ks = _forms(r["variety_name"], crop) | _forms(str(r.get("variety_name_as_printed") or ""), crop)
        if r.get("record_source") != "Seednet only" and r.get("seednet_match_status") in _C2:
            ks |= _forms(str((r.get("seednet_fields") or {}).get("Variety Name") or ""), crop)  # the linked Seednet entry's own aliases
        return {(crop.lower(), k) for k in ks}
    def _core_keys(r):  # phase 1: the variety's own name (without brackets / crop word); phase 2 adds aliases and the linked Seednet name
        crop = r["crop_clean"]; ks = set()
        for nm in (r["variety_name"], str(r.get("variety_name_as_printed") or "")):
            for form in (nm, _strip_paren(nm), crop_word_variant(nm, crop)):
                f = name_key(form)
                if f and _nq2(form) == "ok" and (re.search(r"\d", f) or len(f) >= 6): ks.add(f)
        return {(crop.lower(), k) for k in ks}
    final = sorted(final, key=lambda r: r["variety_id"])  # deterministic order (set / hash order must never decide a merge)
    parent = list(range(len(final))); owner = {}
    members = {i: [i] for i in range(len(final))}
    related: dict[int, set[int]] = {}
    def _find(i):
        while parent[i] != i: parent[i] = parent[parent[i]]; i = parent[i]
        return i
    def _csc(i): return final[i].get("record_source") != "Seednet only"
    def _conflict(i, j) -> bool:
        a_, b_ = final[i], final[j]
        if _csc(i) and _csc(j):
            ya, yb = str(a_.get("year_of_release") or ""), str(b_.get("year_of_release") or "")
            return a_.get("csc_outcome") != b_.get("csc_outcome") or (ya and yb and ya != yb)
        if _csc(i) != _csc(j):
            c, n = (a_, b_) if _csc(i) else (b_, a_)
            cand = (c.get("seednet_candidate") or {}); sid = str((n.get("seednet_fields") or {}).get("variety_id") or "")
            if c.get("seednet_match_status") in ("needs_review", "same_name_crop_conflict", "different_variety") and cand: return True  # the rules said no
            if sid and sid in str(cand.get("url") or ""): return True
            if c.get("seednet_match_status") in _C2 and str((c.get("seednet_fields") or {}).get("variety_id") or "") == sid: return False
        return False
    _phase_keys = [[sorted(_core_keys(r)) for r in final], [sorted(_keys(r) - _core_keys(r)) for r in final]]
    for i, k in [(i, k) for ph in (0, 1) for i in range(len(final)) for k in _phase_keys[ph][i]]:
        j = owner.get(k)
        if j is None: owner[k] = i; continue
        gi, gj = _find(i), _find(j)
        if gi == gj: continue
        if any(_conflict(x, y) for x in members[gi] for y in members[gj]):
            for x in members[gi]:
                for y in members[gj]:
                    if _csc(x) and _csc(y): related.setdefault(x, set()).add(y); related.setdefault(y, set()).add(x)
            continue
        parent[gi] = gj; members[gj] += members.pop(gi)
    groups: dict[int, list[int]] = {}
    for i in range(len(final)): groups.setdefault(_find(i), []).append(i)
    deduped = []; alias_links = 0; keep_of = {}
    def _ids(r):  # name cores and bracket aliases (own name as printed / displayed, linked Seednet name), crop words dropped
        crop = r["crop_clean"]; cores, als = set(), set()
        names = [r["variety_name"], str(r.get("variety_name_as_printed") or "")] + ([str((r.get("seednet_fields") or {}).get("Variety Name") or "")] if r.get("seednet_match_status") in _C2 or r.get("record_source") == "Seednet only" else [])
        for nm in names:
            if not nm: continue
            core = _strip_paren(nm); cw = crop_word_variant(nm, crop) or core
            for c_ in (core, cw):
                if _nq2(c_) == "ok": cores.add((re.sub(r"[^a-z0-9]", "", c_.lower()), tuple(re.findall(r"\d+", c_))))
            for a_ in _aliases(nm):
                if _nq2(a_) == "ok": als.add((re.sub(r"[^a-z0-9]", "", a_.lower()), tuple(re.findall(r"\d+", a_))))
        return cores, als
    def _same(a_, b_) -> bool:
        ca, aa = _ids(a_); cb, ab = _ids(b_)
        return bool(ca & cb) or bool(ca & ab) or bool(cb & aa)
    undone = []
    for gk in list(groups):
        idx = groups[gk]
        if len(idx) < 2: continue
        best_i = max(idx, key=lambda i: _rank(final[i]))
        keep = [i for i in idx if i == best_i or _same(final[best_i], final[i])]
        for i in idx:
            if i not in keep: undone.append((final[best_i]["variety_name"], final[i]["variety_name"], final[i]["crop_clean"])); groups[("split", i)] = [i]
        groups[gk] = keep
    report["merges_undone_by_name_audit"] = len(undone); report["merges_undone_examples"] = undone[:60]
    for idx in groups.values():
        rs = [final[i] for i in idx]
        best = max(rs, key=_rank)
        sn_rows = [x for x in rs if x is not best and x.get("record_source") == "Seednet only"]
        if best.get("record_source") != "Seednet only" and best.get("seednet_match_status") not in _C2 and sn_rows and best.get("name_quality") == "ok":
            donor = max(sn_rows, key=lambda x: len(x.get("seednet_fields") or {}))
            sf_ = donor.get("seednet_fields") or {}
            best["seednet_fields"] = sf_; best["seednet_url"] = sf_.get("source_url", ""); best["seednet_variety_id"] = sf_.get("variety_id", "")
            best["seednet_available"] = True; best["seednet_match"] = "YES"; best["seednet_match_status"] = "confirmed_spelling"
            best["seednet_match_reason"] = f"alias: '{best['variety_name']}' = Seednet '{sf_.get('Variety Name')}'"; best["record_source"] = "CSC minutes and Seednet"
            best.setdefault("official_sources", {})["seednet_url"] = best["seednet_url"]
            st_ = standardize_states((best.get("states_full_clean") or []) + [sf_.get("Recommended States") or ""])
            best["states_full_clean"] = st_; best["states_codes_clean"] = [STATE_CODES[x] for x in st_]; best["states_acronyms_clean"] = ", ".join(best["states_codes_clean"])
            if sf_.get("Notification Number"): best["official_sources"]["seednet_notification_number"] = sf_.get("Notification Number")
            if sf_.get("Notification Date"): best["official_sources"]["seednet_notification_date"] = sf_.get("Notification Date")
            alias_links += 1
        best["merged_duplicate_ids"] = sorted(set(best.get("merged_duplicate_ids") or []) | {x["variety_id"] for x in rs if x is not best} | {m for x in rs if x is not best for m in (x.get("merged_duplicate_ids") or [])})
        best["merged_duplicate_names"] = sorted({x["variety_name"] for x in rs if x is not best and x["variety_name"] != best["variety_name"]})
        for i in idx: keep_of[i] = best
        deduped.append(best)
    code_idx = {}
    for i, r in enumerate(final):
        if r.get("record_source") != "Seednet only" and _nq2(r["variety_name"]) == "ok":
            code_idx.setdefault((r["crop_clean"].lower(), re.sub(r"[^a-z0-9]", "", _strip_paren(r["variety_name"]).lower())), []).append(i)
    for i, r in enumerate(final):  # a CSC code naming another CSC record of the crop ('Pusa Borlaug (HD 2967)') links the two; it never merges them
        code = str((r.get("csc_fields") or {}).get("variety_code") or "")
        if r.get("record_source") == "Seednet only" or not code or _nq2(code) != "ok" or re.search(r"not applicable|not available|not specified", code, re.IGNORECASE): continue
        own = re.sub(r"[^a-z0-9]", "", _strip_paren(r["variety_name"]).lower())
        if not own or own not in re.sub(r"[^a-z0-9]", "", code.lower()): continue  # the code must be written for THIS variety ('Pusa Borlaug (HD 2967)' on HD 2967), not a neighbouring row
        for f in [_strip_paren(code)] + _aliases(code):
            for j in code_idx.get((r["crop_clean"].lower(), re.sub(r"[^a-z0-9]", "", f.lower())), []):
                if keep_of.get(j) is not None and keep_of.get(i) is not None and keep_of[j] is not keep_of[i]:
                    related.setdefault(i, set()).add(j); related.setdefault(j, set()).add(i)
    for i, rel in related.items():
        keep_of[i].setdefault("_related", set()).update(id(keep_of[j]) for j in rel if keep_of[j] is not keep_of[i])
    report["seednet_links_by_alias_merge"] = alias_links
    report["duplicate_crop_name_records_merged"] = len(final) - len(deduped)
    final = sorted(deduped, key=lambda r: r["variety_id"])
    add_resistance_and_yield(final, report)
    # ---- ids and search names
    used: set[str] = set()
    for r in final:
        base = slug(r.get("crop_clean")) + "--" + slug(r.get("variety_name")); rid = base; i = 2
        while rid in used: rid = f"{base}-{i}"; i += 1
        used.add(rid); r["record_id"] = rid; r["legacy_id"] = r["variety_id"]
        r["search_names"] = search_names(r)
        r.pop("_seednet_only_research", None)
        if "trusted_stress_types" in r: r["legacy_2025_trusted_stress_types"] = r.pop("trusted_stress_types")
    by_obj = {id(r): r["record_id"] for r in final}
    for r in final:
        rel = r.pop("_related", set()); r["related_record_ids"] = sorted(by_obj[x] for x in rel if x in by_obj)
    final = [{"record_id": r["record_id"], **{k: v for k, v in r.items() if k != "record_id"}} for r in final]
    report["records_with_direct_csc_minutes_link"] = sum(1 for r in final if (r.get("official_sources") or {}).get("csc_minutes_url") or (r.get("official_sources") or {}).get("csc_minutes_archived_url"))
    report["record_source"] = {k: sum(1 for r in final if r.get("record_source") == k) for k in ("CSC minutes and Seednet", "CSC minutes only", "Seednet only")}
    report["researched_records"] = sum(1 for r in final if r["enrichment_wave"] != "not_researched"); report["official_data_only_records"] = sum(1 for r in final if r["enrichment_wave"] == "not_researched")
    report["seednet_match_status"] = {k: sum(1 for r in final if r["seednet_match_status"] == k) for k in sorted({r["seednet_match_status"] for r in final})}
    report["name_quality"] = {k: sum(1 for r in final if r.get("name_quality") == k) for k in ("ok", "generic", "truncated", "numeric_only")}
    report["stress_confirmation_level"] = {k: sum(1 for r in final if r["stress_confirmation_level"] == k) for k in sorted({r["stress_confirmation_level"] for r in final})}
    report["csc_outcome"] = {k: sum(1 for r in final if r["csc_outcome"] == k) for k in sorted({r["csc_outcome"] for r in final})}
    bfh.OUTPUT_JSON.write_text(json.dumps(final, indent=2, ensure_ascii=False), encoding="utf-8")
    (a.output_dir / "summary_counts.json").write_text(json.dumps(summary_counts(final, report), indent=2, ensure_ascii=False), encoding="utf-8")
    ids = [r["variety_id"] for r in final]
    report.update(final_records=len(final), final_unique_ids=len(set(ids)),
                  final_synthetic=sum("_DUP_" in i for i in ids))
    (a.output_dir / "build_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("\n=== BUILD REPORT ===")
    for k in ("batch_files", "raw_records", "duplicate_variety_ids", "synthetic_records_rejected",
              "unique_varieties", "varieties_with_gemini_analysis", "varieties_with_gemini_error",
              "final_records", "final_unique_ids", "final_synthetic"):
        print(f"{k:35s} {report[k]}")
    if report["malformed_batch_files"]: print("malformed files skipped:", report["malformed_batch_files"])
    ok = report["final_records"] == report["final_unique_ids"] and report["final_synthetic"] == 0
    if a.expect is not None and report["final_unique_ids"] != a.expect:
        print(f"FAIL: expected {a.expect} unique varieties, got {report['final_unique_ids']}"); return 2
    print("OK" if ok else "FAIL: duplicates or synthetic records in output"); return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
