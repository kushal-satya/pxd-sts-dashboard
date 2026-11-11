"""pub_relevance.py - is a publication hit really about this crop variety?

A name query returns anything containing the word: "Ksheera" (a rice variety) also means milk and returns medical
theses. A hit is kept only when
  1. the variety name occurs as a whole name in the title or snippet (not inside a longer word or number), AND
  2. the text has context. A distinctive name (it has a digit or several words): the crop or any agricultural term
     anywhere. A one-word name without digits (often an ordinary word, e.g. "Ksheera" =
     milk): a variety word (variety, cultivar, cv., genotype, hybrid ...) within 70 characters of the name AND the crop
     named somewhere in the text. This loses some true hits for such names; precision is preferred.
Pure standard library. Used at build time for Google Scholar and OpenAlex hits alike.
"""
from __future__ import annotations

import re

CROP_ALIASES = {"rice": ["rice", "paddy", "oryza"], "wheat": ["wheat", "triticum"], "maize": ["maize", "corn", "zea mays"], "sorghum": ["sorghum", "jowar"],
                "pearl millet": ["pearl millet", "bajra", "pennisetum"], "finger millet": ["finger millet", "ragi", "eleusine"], "chickpea": ["chickpea", "gram", "cicer", "chana"],
                "pigeon pea": ["pigeonpea", "pigeon pea", "red gram", "arhar", "cajanus", "tur"], "green gram (mung)": ["mungbean", "mung bean", "green gram", "greengram", "vigna radiata", "moong"],
                "black gram (urd)": ["urdbean", "urd bean", "black gram", "blackgram", "vigna mungo"], "groundnut": ["groundnut", "peanut", "arachis"], "soybean": ["soybean", "soyabean", "glycine max"],
                "mustard / rapeseed": ["mustard", "rapeseed", "brassica", "toria", "sarson"], "cotton": ["cotton", "gossypium"], "sugarcane": ["sugarcane", "saccharum"], "okra (bhindi)": ["okra", "bhindi", "abelmoschus"],
                "brinjal (eggplant)": ["brinjal", "eggplant", "solanum melongena"], "chilli": ["chilli", "chili", "capsicum", "pepper"], "tomato": ["tomato", "lycopersic"], "potato": ["potato", "solanum tuberosum"],
                "sesame": ["sesame", "sesamum", "til"], "lentil": ["lentil", "lens culinaris", "masur"], "pea": ["pea", "pisum"], "barley": ["barley", "hordeum"], "oat": ["oat", "avena"],
                "cowpea": ["cowpea", "vigna unguiculata"], "linseed": ["linseed", "flax", "linum"], "jute": ["jute", "corchorus"], "castor": ["castor", "ricinus"], "sunflower": ["sunflower", "helianthus"]}
VARIETY_WORDS = ("variety", "varieties", "cultivar", "genotype", "hybrid", "germplasm", "accession", "landrace", "breeding line")
AG_WORDS = VARIETY_WORDS + ("breeding", "yield", "seed", "agronom", "crop", "kharif", "rabi", "icar", "tolerance", "tolerant", "resistant", "resistance", "qtl", "grain",
                            "sowing", "fertili", "irrigat", "cultivation", "agricultur", "horticultur", "fodder", "forage", "released", "notified", "pest", "blight", "rust", "wilt")


def name_pattern(name: str) -> re.Pattern | None:
    toks = re.findall(r"[A-Za-z]+|\d+", re.sub(r"\([^)]*\)", " ", str(name or "")))
    if not toks or sum(len(t) for t in toks) < 3: return None
    return re.compile(r"(?<![a-z0-9])" + r"[\s\-.]*".join(re.escape(t.lower()) for t in toks) + r"(?![a-z0-9])")


def crop_terms(*crops) -> set[str]:
    out = set()
    for c in crops:
        c = str(c or "").lower()
        if not c or c in ("nan", "unknown", "unspecified"): continue
        base = re.sub(r"\(.*?\)", " ", c)
        for k, al in CROP_ALIASES.items():
            if k.split(" (")[0] in base or any(re.search(r"\b" + re.escape(a) + r"\b", c) for a in al): out.update(al)
        out.update(t for t in re.findall(r"[a-z]{4,}", c) if t not in ("hybrid", "fodder", "vegetable", "grain", "seed", "other"))
    return out


FRONT_MATTER = re.compile(r"guidance|acknowledg|thank|grateful|gratitude|beside me|my (?:friends|parents|family|labmates|seniors|juniors)|dedicated to|"
                          r"\bdedicated\b|certif(?:y|ied) that|declaration|submitted (?:by|to)|bonafide|under (?:the|my) supervision|advisory committee", re.IGNORECASE)
CHEM_CONTEXT = re.compile(r"dioxide|carbon|nanoplastic|nanoparticle|particulate|\bppm\b|\$|\busd\b|us dollar|emission|atmospher|elevated co|"
                          r"\[\s*co\s*2|co\s*2\s*\]|μmol|umol|nitric|sulphur dioxide|sulfur dioxide|concentration|photosynth|stomatal|\bgenes?\b|co-1 to", re.IGNORECASE)
_STOP_NEXT = {"the", "a", "an", "and", "or", "in", "is", "was", "were", "are", "for", "of", "on", "to", "at", "by", "with", "as", "from", "under", "variety",
              "varieties", "cultivar", "cv", "genotype", "genotypes", "hybrid", "rice", "wheat", "paddy", "showed", "recorded", "had", "has", "which", "that", "this"}


def _title_case(text: str) -> bool:
    words = re.findall(r"[A-Za-z]{3,}", text)
    return bool(words) and sum(w[0].isupper() for w in words) >= 0.6 * len(words)


def _prefix_of_longer_name(orig: str, end: int, aliases_norm: set[str], matched: str) -> bool:
    """The match is the start of a longer variety name: 'Unnat' in 'Unnat Halna' / 'Unnat PBW 343'. Next token (after spaces or a hyphen only)
    is a code with digits, an ALL-CAPS code, or (in sentence-case text) a capitalised word, and name+next is not one of the variety's own names."""
    m = re.match(r"[ \t]*-?[ \t]*([A-Za-z0-9][A-Za-z0-9\-/.]*)", orig[end:])
    if not m or (end < len(orig) and orig[end] not in " -\t"): return False
    nxt = m.group(1).rstrip(".-/")
    if not nxt: return False
    if orig[end:end + 1] == "-" and re.fullmatch(r"[a-z]+", nxt): return True             # 'top class-level': an ordinary compound word
    if nxt.lower() in _STOP_NEXT: return False
    if re.sub(r"[^a-z0-9]", "", (matched + nxt).lower()) in aliases_norm: return False
    if re.fullmatch(r"\d{1,4}[A-Za-z]?", nxt) and not re.search(r"\d", matched): return True  # 'DRR Dhan' in 'DRR Dhan 62', 'Paiyur' in 'Paiyur 2'
    if re.search(r"\d", nxt) and re.search(r"[A-Za-z]", nxt): return True             # 'PBW343'-style code
    if re.fullmatch(r"[A-Z]{2,}", nxt) and len(nxt) <= 6: return True                   # 'PBW', 'HD'
    if nxt[0].isupper() and nxt[1:].islower() and not _title_case(orig): return True    # 'Halna' in a sentence
    return False


def relevant(names: list[str], crops: list[str], title: str, snippet: str = "", aliases: list[str] | None = None) -> bool:
    """Is this publication hit about THIS variety? Title and snippet are checked SEPARATELY (context never crosses the joint).
    2026-11 rules: reject acknowledgement / thesis front-matter contexts; reject chemistry/currency collisions for 2-letter+digit codes
    ('CO 2' = carbon dioxide, 'US 380' = dollars); for names without digits reject a match that is the start of a longer variety name;
    for distinctive names (digits / several words) require a crop alias somewhere in the text (an agricultural word only when the crop
    has no alias list); for one-word names a variety word next to the name AND the crop in the text."""
    names = [str(n) for n in names if n is not None and str(n).strip()]
    names = names + [n.replace("(", " ").replace(")", " ") for n in names if "(" in n]  # "CO (On) 5" is written with its brackets in papers
    aliases_norm = {re.sub(r"[^a-z0-9]", "", str(x).lower()) for x in (aliases or []) + names}
    pats = [(n, p) for n in names if (p := name_pattern(n))]
    full = f"{title or ''} {snippet or ''}"; full_l = full.lower()
    cterms = crop_terms(*crops)
    has_alias_list = any(k.split(" (")[0] in re.sub(r"\(.*?\)", " ", str(c or "").lower()) or any(re.search(r"\b" + re.escape(a) + r"\b", str(c or "").lower()) for a in al)
                         for c in crops for k, al in CROP_ALIASES.items())
    def has(terms, t): return any(re.search(r"(?<![a-z])" + re.escape(x) + r"(?![a-z])", t) for x in terms)
    def _core(n): return re.sub(r"\([^)]*\)", " ", n)
    crop_ok = has(cterms, full_l) if (cterms and has_alias_list) else (has(cterms, full_l) or any(w in full_l for w in AG_WORDS))
    for part in (str(title or ""), str(snippet or "")):
        if not part.strip(): continue
        low = part.lower() if len(part.lower()) == len(part) else part.casefold()
        if len(low) != len(part): low = part.lower(); part = low  # rare: lower() changed the length; case tests are skipped
        front = bool(FRONT_MATTER.search(part))
        for n, p in pats:
            core = _core(n).strip()
            distinctive = bool(re.search(r"\d", core)) or len(re.findall(r"[A-Za-z]{2,}", core)) >= 2
            code2 = re.fullmatch(r"[A-Za-z]{2}\s*-?\s*\d+", core)
            for m in p.finditer(low):
                if front: continue
                if code2 and CHEM_CONTEXT.search(part): continue
                if not re.search(r"\d", core) and _prefix_of_longer_name(part, m.end(), aliases_norm, core): continue
                if distinctive:
                    if crop_ok: return True
                    continue
                near = low[max(0, m.start() - 70): m.end() + 70]
                if (any(w in near for w in VARIETY_WORDS) or re.search(r"\bcvs?\b\.?", near)) and (has(cterms, full_l) or not cterms): return True
    return False


def title_key(title) -> str:
    """Normalised title for de-duplication within and across Scholar / OpenAlex."""
    t = re.sub(r"<[^>]+>", " ", str(title or "")).lower()
    t = re.sub(r"^[\W_]*(\[[a-z]+\]\s*)*", "", t)
    return re.sub(r"[^a-z0-9]", "", t)[:120]
