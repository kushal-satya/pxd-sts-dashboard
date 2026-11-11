"""Rules that decide whether a CSC variety and a Seednet variety are the SAME variety.

Why this exists: the July-2025 matcher accepted any fuzzy name score >= 80 with no crop check, which paired many
CSC varieties with a different Seednet variety (cashew "BH-6" <-> barley "BH 946", rice "VL Dhan 69" <-> "VL Dhan-65").
A variety number is part of its identity, so different digits always mean a different variety.

classify(csc_name, csc_crop, seednet_name, seednet_crop) -> one of
  confirmed_exact          names equal after normalisation (parenthetical codes ignored, or equal to such a code), crops compatible
  confirmed_spelling       same digits, spelling ratio >= 0.88 AND edit distance <= 2 (<= 1 for short names), crops compatible
                           (e.g. "Ganganagar Acid Lime-1" / "Ganganaga Acid Lime-1")
  same_name_crop_conflict  the same distinctive name, but the two sources give different crops (one of them is wrong; review)
  different_variety        anything else (different number, different name, or different crop)
  no_seednet               no Seednet name given
classify_reason() returns (status, reason). 2026-11 review rules:
  * a form that is only a crop / generic word or 3 letters or fewer without digits ('Sorghum', 'Hybrid', 'CO', 'TMV') never links;
  * a CSC name without digits does not match a Seednet name whose main part (before brackets) has digits ('Paiyur' / 'Paiyur(Ra)2');
  * an empty, 'Unspecified' or 'Unknown' crop is a missing crop and cannot contradict.
crop_word_variant(): CSC name minus a leading/trailing generic word of its own crop ('Sahbhagi Dhan' -> 'Sahbhagi'); rematch_seednet uses it.
Pure standard library plus standardize.py; safe to import anywhere.
"""
from __future__ import annotations

import difflib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from standardize import name_is_distinctive, standardize_crop  # noqa: E402

_GENERIC = {"hybrid", "variety", "vegetable", "fodder", "grain", "seed", "desi", "kabuli", "bt", "rabi", "kharif", "summer", "sweet", "pop", "baby", "forage", "bread", "durum"}
CROP_WORDS_BY_CROP = {  # generic words for a crop that may be dropped from ITS OWN varieties' names ('Sahbhagi Dhan' = Seednet 'SAHBHAGI')
    "Rice": ["dhan", "rice", "paddy", "chawal"], "Wheat": ["gehun", "gehon", "gehu", "wheat"], "Chickpea": ["chana", "gram", "chickpea"],
    "Maize": ["makka", "makki", "maize", "corn"], "Pearl millet": ["bajra"], "Sorghum": ["jowar", "jonna", "sorghum"], "Mustard / rapeseed": ["sarson", "mustard", "rai", "raya"],
    "Pigeon pea": ["arhar", "tur", "pigeonpea"], "Black gram (urd)": ["urd", "urdbean", "mash"], "Green gram (mung)": ["mung", "moong", "mungbean"],
    "Lentil": ["masoor", "masur", "lentil"], "Pea": ["matar", "pea"], "Sesame": ["til", "sesame"], "Groundnut": ["groundnut", "mungphali"], "Cotton": ["kapas", "cotton"],
    "Soybean": ["soya", "soybean"], "Finger millet": ["ragi", "mandua"], "Barley": ["jau", "barley"], "Oat": ["oat", "oats", "jai"]}


def _norm(s) -> str: return re.sub(r"[^a-z0-9]", "", str(s or "").lower())
def name_key(s) -> str:
    """Like _norm but keeps the boundary between two digit groups, so 'MAUS-61-2' (Pratishtha) and 'MAUS 612' stay different."""
    t = re.sub(r"(?<=\d)[^a-z0-9]+(?=\d)", ".", str(s or "").lower().strip())
    return re.sub(r"[^a-z0-9.]", "", t).strip(".")
def fix_brackets(s) -> str:
    """'MACS JEJURI (MACS 4100 D}' -> 'MACS JEJURI (MACS 4100 D)': other brackets become '(' / ')', an unclosed '(' is closed at the end,
    and trial codes written OUTSIDE brackets in Seednet ('... IET-20266', '... IC 574472') are put in brackets (they are aliases)."""
    s = re.sub(r"[\]}]", ")", re.sub(r"[\[{]", "(", str(s or "")))
    bal, kept = 0, []
    for ch in s:  # drop stray ')' that close nothing
        if ch == ")" and bal == 0: kept.append(" "); continue
        bal += (ch == "(") - (ch == ")"); kept.append(ch)
    s = "".join(kept) + ")" * bal
    out, depth, seg = [], 0, ""
    for ch in s + "\0":  # wrap IET/IC codes only at bracket depth 0
        if ch in "(\0" and depth == 0 and seg:
            if re.sub(r"\b[I0l1]E\s*T\b\.?\s*(No\.?)?\s*[-:]?\s*\d+|\bIC\s*[-:]?\s*\d{4,}", "", seg).strip(" -") or out:
                seg = re.sub(r"\b([I0l1]E\s*T\b\.?\s*(?:No\.?)?\s*[-:]?\s*\d+|IC\s*[-:]?\s*\d{4,})", r"(\1)", seg)
            out.append(seg); seg = ""
        if ch == "\0": break
        seg += ch
        if ch == "(": depth += 1
        elif ch == ")": depth = max(0, depth - 1)
        if depth == 0 and ch == ")": out.append(seg); seg = ""
    return "".join(out)


def _paren_parts(s) -> tuple[str, list[str]]:
    """(text with all brackets removed, contents of every bracket, innermost first); handles nesting like 'Azad Mahak ((KMR (E) 15-2))'."""
    s = fix_brackets(s); parts = []
    while True:
        m = re.search(r"\(([^()]*)\)", s)
        if not m: break
        if m.group(1).strip(): parts.append(m.group(1).strip())
        s = s[:m.start()] + " " + s[m.end():]
    return s, parts


def _strip_paren(s) -> str: return _paren_parts(s)[0]
def _aliases(s) -> list[str]: return _paren_parts(s)[1]
def _digits(s) -> list[str]: return [d.lstrip("0") or "0" for d in re.findall(r"\d+", _strip_paren(s))]


def _blank(v) -> bool: return v is None or str(v).strip().lower() in ("", "nan", "none", "not specified", "unknown", "unspecified")


def edit_distance(a: str, b: str) -> int:
    if a == b: return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1): cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def crops_compatible(csc_crop, seednet_crop) -> bool:
    """True when both crop labels reduce to the same canonical crop (hybrid / type qualifiers ignored).
    A missing crop on either side ('', 'Unspecified', 'Unknown') cannot contradict, so it is treated as compatible."""
    if _blank(csc_crop) or _blank(seednet_crop): return True
    a, b = standardize_crop(csc_crop), standardize_crop(seednet_crop)
    if a in ("Unspecified", "Unknown") or b in ("Unspecified", "Unknown"): return True
    if a == b: return True
    ta = {w for w in re.findall(r"[a-z]+", a.lower()) if w not in _GENERIC}
    tb = {w for w in re.findall(r"[a-z]+", b.lower()) if w not in _GENERIC}
    return bool(ta & tb)


def _forms(name) -> dict[str, str]:
    """normalised form -> the text it came from: full name, name without brackets, each bracket alias."""
    s = fix_brackets(name)
    out = {name_key(s): s, name_key(_strip_paren(s)): _strip_paren(s)}
    for p in _aliases(s): out.setdefault(name_key(p), p)
    out.pop("", None)
    return out


def crop_word_variant(name, crop) -> str:
    """The name without one leading/trailing generic word of its own crop, if the rest is distinctive (>= 6 letters or a digit); else ''."""
    words = str(_strip_paren(name)).replace("-", " ").split()
    cw = CROP_WORDS_BY_CROP.get(standardize_crop(crop), [])
    if len(words) < 2 or not cw: return ""
    for cut in (words[1:] if words[0].lower() in cw else None, words[:-1] if words[-1].lower() in cw else None):
        if cut:
            rest = " ".join(cut)
            if (re.search(r"\d", rest) or len(re.sub(r"[^a-z]", "", rest.lower())) >= 6) and name_is_distinctive(rest): return rest
    return ""


def classify_reason(csc_name, csc_crop, seednet_name, seednet_crop) -> tuple[str, str]:
    if _blank(seednet_name): return "no_seednet", "no Seednet name"
    fa, fb = _forms(csc_name), _forms(seednet_name)
    shared = [k for k in fa if k in fb and name_is_distinctive(fa[k]) and name_is_distinctive(fb[k])]
    da_all = {d.lstrip("0") or "0" for d in re.findall(r"\d+", fix_brackets(csc_name))}
    db_all = {d.lstrip("0") or "0" for d in re.findall(r"\d+", fix_brackets(seednet_name))}
    if da_all and db_all and not (da_all & db_all): return "different_variety", "the two names carry different numbers"
    if not crops_compatible(csc_crop, seednet_crop):
        strong = [k for k in shared if re.search(r"\d", fa[k]) or len(re.findall(r"[A-Za-z]{2,}", fa[k])) >= 2]
        if strong: return "same_name_crop_conflict", f"same name '{fa[strong[0]].strip()}' but crops differ ({csc_crop} / {seednet_crop})"
        return "different_variety", "different crop"
    if shared:
        csc_has_digit = bool(re.search(r"\d", str(csc_name or "")))
        sn_main_digit = bool(re.search(r"\d", _strip_paren(seednet_name)))
        alias_hit = any(k in {name_key(p) for p in _aliases(seednet_name)} or k == name_key(seednet_name) or k == name_key(_strip_paren(seednet_name)) for k in shared)
        if csc_has_digit or not sn_main_digit or alias_hit: return "confirmed_exact", f"same name '{fa[shared[0]].strip()}'"
    sn = fix_brackets(seednet_name)
    head, tail = (sn.split("(", 1) + [""])[:2]
    rest = _strip_paren("(" + tail) if tail else ""
    if (_norm(head) and _norm(head) == _norm(_strip_paren(csc_name)) and name_is_distinctive(head)
            and rest.strip() and re.match(r"[A-Za-z]", rest.strip(" ,;-"))):
        return "confirmed_exact", "same name; Seednet adds breeding codes"  # 'Uttar Lakshmi (IET 24173) UBKVR-15'; not 'Paiyur(Ra)2'
    if (_norm(head) and _norm(head) == _norm(_strip_paren(csc_name)) and re.search(r"\d", head) and name_is_distinctive(head)):
        return "confirmed_exact", "same name and number; Seednet adds codes"  # 'CO 55 (CB 15714) 4 (IET 27873)'
    if any(k in fb for k in fa):  # equal only through a generic / too-short form ('Sorghum', 'Hybrid', 'cotton')
        return "different_variety", "names agree only on a crop/generic word or a code of 3 letters or fewer"
    if _digits(csc_name) != _digits(seednet_name): return "different_variety", "different variety number"
    a2, b2 = _norm(_strip_paren(csc_name)), _norm(_strip_paren(seednet_name))
    if not (name_is_distinctive(_strip_paren(csc_name)) and name_is_distinctive(_strip_paren(seednet_name))): return "different_variety", "name not distinctive"
    if not re.search(r"\d", str(csc_name or "")) and re.search(r"\d", _strip_paren(seednet_name)): return "different_variety", "Seednet name has a number the CSC name lacks"
    dist = edit_distance(a2, b2); limit = 1 if min(len(a2), len(b2)) < 10 else 2
    if difflib.SequenceMatcher(None, a2, b2).ratio() >= 0.88 and dist <= limit: return "confirmed_spelling", f"spelling variant (edit distance {dist})"
    return "different_variety", "different name"


def classify(csc_name, csc_crop, seednet_name, seednet_crop) -> str:
    return classify_reason(csc_name, csc_crop, seednet_name, seednet_crop)[0]


CONFIRMED = ("confirmed_exact", "confirmed_spelling")
NOT_LINKED_WITH_CANDIDATE = ("different_variety", "same_name_crop_conflict", "needs_review")
