"""standardize.py - canonical crop and state names for the dashboard (editable tables, applied at build time).
Crops: Seednet crop name preferred, then CSC crop; synonyms collapse spellings (urd bean / urdbean / black gram -> Black gram (urd)).
States: only names in the official list of Indian states and union territories are kept; LLM caveats in parentheses and prose are dropped."""
from __future__ import annotations

import re

STATES = ["Andaman and Nicobar Islands", "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chandigarh", "Chhattisgarh",
          "Dadra and Nagar Haveli and Daman and Diu", "Delhi", "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jammu and Kashmir", "Jharkhand",
          "Karnataka", "Kerala", "Ladakh", "Lakshadweep", "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Odisha",
          "Puducherry", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal"]
STATE_CODES = {"Andaman and Nicobar Islands": "AN", "Andhra Pradesh": "AP", "Arunachal Pradesh": "AR", "Assam": "AS", "Bihar": "BR", "Chandigarh": "CH",
               "Chhattisgarh": "CG", "Dadra and Nagar Haveli and Daman and Diu": "DN", "Delhi": "DL", "Goa": "GA", "Gujarat": "GJ", "Haryana": "HR",
               "Himachal Pradesh": "HP", "Jammu and Kashmir": "JK", "Jharkhand": "JH", "Karnataka": "KA", "Kerala": "KL", "Ladakh": "LA", "Lakshadweep": "LD",
               "Madhya Pradesh": "MP", "Maharashtra": "MH", "Manipur": "MN", "Meghalaya": "ML", "Mizoram": "MZ", "Nagaland": "NL", "Odisha": "OR",
               "Puducherry": "PY", "Punjab": "PB", "Rajasthan": "RJ", "Sikkim": "SK", "Tamil Nadu": "TN", "Telangana": "TG", "Tripura": "TR",
               "Uttar Pradesh": "UP", "Uttarakhand": "UK", "West Bengal": "WB"}
STATE_SYNONYMS = {"orissa": "Odisha", "uttaranchal": "Uttarakhand", "pondicherry": "Puducherry", "chattisgarh": "Chhattisgarh", "chhatisgarh": "Chhattisgarh",
                  "himachal": "Himachal Pradesh", "hp": "Himachal Pradesh", "j&k": "Jammu and Kashmir", "jammu & kashmir": "Jammu and Kashmir", "jammu and kashmir": "Jammu and Kashmir",
                  "jammu": "Jammu and Kashmir", "kashmir": "Jammu and Kashmir", "andaman": "Andaman and Nicobar Islands", "andaman & nicobar": "Andaman and Nicobar Islands",
                  "andaman nicobar islands": "Andaman and Nicobar Islands", "a&n islands": "Andaman and Nicobar Islands", "nct delhi": "Delhi", "new delhi": "Delhi",
                  "dadra & nagar haveli": "Dadra and Nagar Haveli and Daman and Diu", "daman & diu": "Dadra and Nagar Haveli and Daman and Diu", "tamilnadu": "Tamil Nadu",
                  "telengana": "Telangana", "up": "Uttar Pradesh", "mp": "Madhya Pradesh", "ap": "Andhra Pradesh", "wb": "West Bengal", "tn": "Tamil Nadu", "uk": "Uttarakhand"}
_STATE_INDEX = {s.lower(): s for s in STATES} | STATE_SYNONYMS | {c.lower(): s for s, c in STATE_CODES.items()}
# multi-letter written names (full names and spelled-out synonyms, not 2-letter codes) that are searched as whole phrases
_FULL_NAME_PATTERNS = {k: v for k, v in ({s.lower(): s for s in STATES} | STATE_SYNONYMS).items() if len(k) > 4 and not re.fullmatch(r"[a-z&]{1,4}", k)}


def raw_state_names(text) -> set[str]:
    """Every state written out in full (or by a spelled-out synonym such as 'Orissa') anywhere in the text, as canonical names.
    Used by standardize_states and by the validator to prove no state named in the raw text is lost."""
    raw = str(text or "")
    t = " " + re.sub(r"\s+", " ", raw).lower() + " "
    t = t.replace("&", " and ")
    # Seednet sometimes runs upper-case names together ('DELHIHARYANAHIMACHAL PRADESHJAMMU&KASHMIR'): search those runs without word boundaries
    runs = " ".join(m.group(0) for m in re.finditer(r"(?:[A-Z&]+\s+)*[A-Z&]{12,}(?:\s+[A-Z&]+)*", raw)).lower().replace("&", "and").replace(" ", "")
    out = set()
    for k, v in _FULL_NAME_PATTERNS.items():
        k2 = k.replace("&", " and ")
        k2 = re.sub(r"\s+", " ", k2)
        if re.search(r"(?<![a-z])" + re.escape(k2) + r"(?![a-z])", t): out.add(v)
        elif runs and len(k2) >= 5 and k2.replace(" ", "") in runs: out.add(v)
    return out

def standardize_states(values) -> list[str]:
    """values: list of strings or one comma string. Returns canonical state names (deduped, in canonical order)."""
    if isinstance(values, str): values = [values]
    found = set()
    for v in values or []:
        if not v: continue
        text = re.sub(r"\([^)]*\)", " ", str(v))                       # drop caveats in parentheses
        # full state names first (so "West Bengal" is found BEFORE direction words like "west" are stripped), then the rest
        names_here = raw_state_names(text)
        found |= names_here
        text = re.sub(r"\s+", " ", text.replace("&", " and "))
        for nm in sorted(_FULL_NAME_PATTERNS, key=len, reverse=True):
            if _FULL_NAME_PATTERNS[nm] in names_here:
                text = re.sub(r"(?<![a-z])" + re.escape(re.sub(r"\s+", " ", nm.replace("&", " and "))) + r"(?![a-z])", " ; ", text, flags=re.IGNORECASE)
        text = re.sub(r"\b(eastern|western|northern|southern|central|north|south|east|west|parts of|interior|plains of|hills of)\b", " ", text, flags=re.IGNORECASE)
        for piece in re.split(r"[,;/&]|\band\b|\bor\b", text):
            key = re.sub(r"\s+", " ", piece.strip().lower().strip(". '\"[]"))
            if not key: continue
            key = re.sub(r"^(state of|the)\s+", "", key)
            if key in _STATE_INDEX: found.add(_STATE_INDEX[key]); continue
            for name_l, name in _STATE_INDEX.items():                   # substring match for strings like "uttar pradesh plains"
                if len(name_l) > 4 and name_l in key: found.add(name); break
    return [s for s in STATES if s in found]

CROP_SYNONYMS = {  # lower-cased pattern -> canonical label; first match wins; order matters
    "paddy": "Rice", "rice": "Rice", "dhan": "Rice", "wheat": "Wheat", "gehun": "Wheat", "gehon": "Wheat", "maize": "Maize", "makka": "Maize", "corn": "Maize",
    "bajra": "Pearl millet", "pearl millet": "Pearl millet", "jowar": "Sorghum", "sorghum": "Sorghum", "ragi": "Finger millet", "finger millet": "Finger millet",
    "arhar": "Pigeon pea", "pigeon pea": "Pigeon pea", "pigeonpea": "Pigeon pea", "red gram": "Pigeon pea", "tur": "Pigeon pea",
    "chickpea": "Chickpea", "chick pea": "Chickpea", "bengal gram": "Chickpea", "gram": "Chickpea", "chana": "Chickpea", "kabuli": "Chickpea",
    "urd": "Black gram (urd)", "black gram": "Black gram (urd)", "blackgram": "Black gram (urd)", "mash": "Black gram (urd)",
    "mung": "Green gram (mung)", "moong": "Green gram (mung)", "green gram": "Green gram (mung)", "greengram": "Green gram (mung)",
    "lentil": "Lentil", "masur": "Lentil", "masoor": "Lentil", "field pea": "Field pea", "fieldpea": "Field pea", "pea": "Pea", "cowpea": "Cowpea", "lobia": "Cowpea",
    "horse gram": "Horse gram", "horsegram": "Horse gram", "kulthi": "Horse gram", "lathyrus": "Lathyrus", "khesari": "Lathyrus", "rajmash": "Rajmash (kidney bean)", "kidney bean": "Rajmash (kidney bean)",
    "soybean": "Soybean", "soyabean": "Soybean", "bhat": "Soybean", "groundnut": "Groundnut", "peanut": "Groundnut", "mungfali": "Groundnut",
    "mustard": "Mustard / rapeseed", "rapeseed": "Mustard / rapeseed", "sarson": "Mustard / rapeseed", "raya": "Mustard / rapeseed", "toria": "Mustard / rapeseed", "rai": "Mustard / rapeseed",
    "sesame": "Sesame", "til": "Sesame", "gingelly": "Sesame", "sunflower": "Sunflower", "safflower": "Safflower", "castor": "Castor", "linseed": "Linseed", "flax": "Linseed", "niger": "Niger",
    "cotton": "Cotton", "kapas": "Cotton", "jute": "Jute", "mesta": "Mesta (kenaf)", "kenaf": "Mesta (kenaf)", "sugarcane": "Sugarcane", "sugar cane": "Sugarcane",
    "barley": "Barley", "jau": "Barley", "oat": "Oat", "berseem": "Berseem", "lucerne": "Lucerne", "napier": "Napier grass", "fodder sorghum": "Sorghum (fodder)", "fodder maize": "Maize (fodder)",
    "potato": "Potato", "tomato": "Tomato", "brinjal": "Brinjal (eggplant)", "eggplant": "Brinjal (eggplant)", "okra": "Okra (bhindi)", "bhindi": "Okra (bhindi)", "chilli": "Chilli", "chillies": "Chilli",
    "onion": "Onion", "garlic": "Garlic", "cabbage": "Cabbage", "cauliflower": "Cauliflower", "carrot": "Carrot", "radish": "Radish", "cucumber": "Cucumber", "bottle gourd": "Bottle gourd",
    "bitter gourd": "Bitter gourd", "ridge gourd": "Ridge gourd", "sponge gourd": "Sponge gourd", "ash gourd": "Ash gourd", "pumpkin": "Pumpkin", "watermelon": "Watermelon", "musk melon": "Muskmelon", "muskmelon": "Muskmelon",
    "mango": "Mango", "banana": "Banana", "papaya": "Papaya", "guava": "Guava", "coconut": "Coconut", "cashew": "Cashew", "turmeric": "Turmeric", "ginger": "Ginger", "coriander": "Coriander", "cumin": "Cumin", "fenugreek": "Fenugreek", "fennel": "Fennel",
}
CROP_SYNONYMS.update({  # compound names that must win over their shorter parts, plus spelling variants seen in CSC / Seednet
    "buck wheat": "Buckwheat", "buckwheat": "Buckwheat", "rice bean": "Rice bean", "sweet potato": "Sweet potato", "bajra napier": "Napier grass",
    "mungbean": "Green gram (mung)", "moongbean": "Green gram (mung)", "urdbean": "Black gram (urd)", "urd bean": "Black gram (urd)",
    "field pea": "Pea", "fieldpea": "Pea", "garden pea": "Pea", "pea": "Pea", "matar": "Pea", "ground nut": "Groundnut", "pea nut": "Groundnut",
    "capsicum": "Capsicum (sweet pepper)", "sweet pepper": "Capsicum (sweet pepper)", "bell pepper": "Capsicum (sweet pepper)",
    "guar": "Cluster bean (guar)", "cluster bean": "Cluster bean (guar)", "clusterbean": "Cluster bean (guar)", "amaranth": "Amaranth", "amaranthus": "Amaranth",
    "grape": "Grape", "sunhemp": "Sunnhemp", "sunnhemp": "Sunnhemp", "kodomillet": "Kodo millet", "kodo millet": "Kodo millet", "gobhi sarson": "Mustard / rapeseed", "gobhisarson": "Mustard / rapeseed",
    "taramira": "Taramira (rocket salad)", "rocket salad": "Taramira (rocket salad)", "tapioca": "Cassava (tapioca)", "cassava": "Cassava (tapioca)", "lethyrus": "Lathyrus",
    "rajma": "Rajmash (kidney bean)", "french bean": "Rajmash (kidney bean)", "foxtail millet": "Foxtail millet", "fox tail millet": "Foxtail millet", "italian millet": "Foxtail millet",
    "little millet": "Little millet", "barnyard millet": "Barnyard millet", "banyard millet": "Barnyard millet", "proso millet": "Proso millet", "common millet": "Proso millet",
    "triticale": "Triticale", "broccoli": "Broccoli", "brocolli": "Broccoli", "faba bean": "Faba bean", "broad bean": "Faba bean", "indian bean": "Indian bean (dolichos)", "dolichos": "Indian bean (dolichos)",
})
CROP_SYNONYMS.update({"barely": "Barley", "bottlegourd": "Bottle gourd", "bottle guard": "Bottle gourd", "battole gourd": "Bottle gourd", "ashgourd": "Ash gourd", "bittergourd": "Bitter gourd",
    "ridgegourd": "Ridge gourd", "spongegourd": "Sponge gourd", "water melon": "Watermelon", "prosomillet": "Proso millet", "ricebean": "Rice bean", "knol khol": "Knol-khol", "knol-khol": "Knol-khol",
    "indian mustard": "Mustard / rapeseed", "dill": "Dill seed", "ajowan": "Ajwain", "ajwain": "Ajwain", "pigeon": "Pigeon pea", "cashew nut": "Cashew", "sweet corn": "Maize", "pop corn": "Maize", "baby corn": "Maize",
    "french bean": "Rajmash (kidney bean)", "tobacco": "Tobacco", "fingermillet": "Finger millet", "pearlmillet": "Pearl millet", "foxtailmillet": "Foxtail millet", "littlemillet": "Little millet",
    "browntop millet": "Browntop millet", "oats": "Oat", "isabgol": "Isabgol", "chilly": "Chilli", "clusterbean": "Cluster bean (guar)", "lablab": "Indian bean (dolichos)"})
CROP_SYNONYMS.update({"betelvine": "Betel vine", "jack fruit": "Jackfruit", "longmelon": "Long melon", "mothbean": "Moth bean", "pummeloo": "Pummelo", "snapmelon": "Snap melon",
    "soy bean": "Soybean", "sesamum": "Sesame", "rajmah": "Rajmash (kidney bean)", "asalia": "Asalio", "methi": "Fenugreek", "manila tamarid": "Manila tamarind", "manila tamarind": "Manila tamarind",
    "sewan grass": "Sewan grass", "bach": "Bach (sweet flag)", "french marigold": "Marigold", "perennial moringa": "Moringa", "drumstick": "Moringa", "small cardamom": "Cardamom",
    "melon": "Melon"})
CROP_SYNONYMS.update({  # 2026-11 review: one label per species; fodder/forage use of a crop is the same crop
    "taro": "Taro (colocasia)", "arvi": "Taro (colocasia)", "colocasia": "Taro (colocasia)", "eddoe": "Taro (colocasia)",
    "anjan": "Cenchrus (anjan / buffel grass)", "anjan grass": "Cenchrus (anjan / buffel grass)", "buffel grass": "Cenchrus (anjan / buffel grass)",
    "cenchrus": "Cenchrus (anjan / buffel grass)", "cenchrus grass": "Cenchrus (anjan / buffel grass)", "kolukattai": "Cenchrus (anjan / buffel grass)",
    "black kolukattai grass": "Cenchrus (anjan / buffel grass)", "black kolukattai-grass": "Cenchrus (anjan / buffel grass)",
    "dhaman": "Dhaman grass", "dhaman grass": "Dhaman grass", "bird wood grass": "Dhaman grass",
    "chaulai": "Amaranth", "grain amaranth": "Amaranth", "rajgira": "Amaranth", "dil seed": "Dill seed", "dil": "Dill seed", "dill seed": "Dill seed", "indian dill": "Dill seed",
    "setaria": "Setaria grass", "setaria grass": "Setaria grass", "pigeon grass": "Setaria grass", "nandi grass": "Setaria grass",
    "cassia": "Cinnamon / cassia", "cinnamon": "Cinnamon / cassia", "cinnamomum": "Cinnamon / cassia",
    "asparagus bean": "Yard long bean", "yard long bean": "Yard long bean", "yardlong bean": "Yard long bean",
    "fodder oat": "Oat", "fodder oats": "Oat", "forage oat": "Oat", "fodder bajra": "Pearl millet", "forage pearl millet": "Pearl millet", "bajra fodder": "Pearl millet",
    "fodder maize": "Maize", "forage maize": "Maize", "fodder sorghum": "Sorghum", "forage sorghum": "Sorghum", "fodder cowpea": "Cowpea", "forage cowpea": "Cowpea",
    "indian aster": "Aster", "china aster": "Aster", "aster": "Aster", "mushroom": "Mushroom", "oyster mushroom": "Mushroom", "button mushroom": "Mushroom",
    "lima bean": "Lima bean", "guinea grass": "Guinea grass", "napier grass": "Napier grass", "elephant grass": "Napier grass", "hedge lucerne": "Lucerne",
})
# catch-all words that say nothing about the crop: used ONLY when no real crop word is found (else "Fodder oat" became Unspecified)
CROP_FALLBACK = {"horticultural": "Unspecified", "not explicitly stated": "Unspecified", "fodder": "Unspecified", "forage": "Unspecified",
                 "millet": "Unspecified", "indian": "Unspecified"}
_CROP_PATTERNS = sorted(CROP_SYNONYMS.items(), key=lambda kv: -len(kv[0]))  # longest pattern first: "green gram" before "gram", "rice bean" before "rice"


def _crop_lookup(text: str) -> str | None:
    text = re.sub(r"\s+", " ", text.lower().replace("(", " ").replace(")", " ").replace("/", " ")).strip()
    for pat, label in _CROP_PATTERNS:
        if re.search(r"\b" + re.escape(pat) + r"(?:s|es)?\b", text): return label
    return None


def _crop_fallback(text: str) -> str | None:
    """'Unspecified' only when the text is NOTHING BUT catch-all words ('horticultural', 'Fodder', 'fodder/grass', 'millet')."""
    text = re.sub(r"\s+", " ", str(text).split("(")[0].lower().replace("/", " ")).strip()
    rest = text
    for pat in sorted(CROP_FALLBACK, key=len, reverse=True): rest = re.sub(r"\b" + re.escape(pat) + r"(?:s|es)?\b", " ", rest)
    rest = re.sub(r"\b(crop|crops|grass|grasses|type|sp|spp|and|or|likely|a|an|agricultural|horticultural)\b", " ", rest)
    return "Unspecified" if text and not re.sub(r"[^a-z]", "", rest) else None


def standardize_crop(*cands) -> str:
    """cands: Seednet crop name first (e.g. 'BLACK GRAM (URD BEAN)'), then CSC crop. Returns a canonical label.
    The part before a parenthesis is the crop itself and is tried first; the aliases inside the parenthesis only afterwards
    (so 'GROUNDNUT (PEA NUT/MUNG PHALLI)' is Groundnut, not mung). Longest synonym wins."""
    for c in cands:
        if not c or str(c).strip().lower() in ("nan", "not specified", "unknown", "none", ""): continue
        c = str(c).replace("*", " ").strip()
        head = c.split("(")[0]
        hit = _crop_lookup(head) or _crop_lookup(str(c))
        if hit: return hit
        if _crop_fallback(c): continue  # 'Horticultural' / 'Fodder' alone: try the next candidate before giving up
        base = re.sub(r"\s+", " ", head.split("/")[0]).strip()
        if base: return base[:1].upper() + base[1:].lower()
    for c in cands:
        if c and _crop_fallback(c): return _crop_fallback(c)
    return "Unknown"


# ---------------------------------------------------------------- variety-name quality (2026-11 data review)
_NAME_GENERIC_WORDS = {"hybrid", "hybrids", "hy", "variety", "varieties", "cultivar", "local", "improved", "selection", "composite", "synthetic", "bt", "desi",
                       "sweet", "white", "red", "black", "green", "yellow", "fodder", "forage", "grass", "bread", "durum", "indian", "india", "gujarat", "culture",
                       "line", "type", "three", "species", "grain", "bean", "beans", "tea", "seed", "seeds", "crop", "new", "elephant", "foot", "yam", "guinea",
                       "multicut", "single", "cut", "baby", "pop", "dwarf", "tall", "early", "late", "kabuli", "nut", "sarson", "gobhi", "field", "vegetable", "l",
                       "other", "others", "all", "various", "mixed", "unknown", "sample", "check", "checks", "entries", "entry", "lines", "cultivars", "type"}
_CROP_WORDS = None


def crop_words() -> set[str]:
    """Every word that is part of a crop name or crop synonym (lower case): 'okra', 'gram', 'pea', 'mungbean', 'ashwagandha' ..."""
    global _CROP_WORDS
    if _CROP_WORDS is None:
        w = set()
        for k, v in CROP_SYNONYMS.items(): w |= set(re.findall(r"[a-z]+", k)) | set(re.findall(r"[a-z]+", v.lower()))
        w |= {"ashwagandha", "karonda", "cinnamon", "mushroom", "taro", "tobacco", "niger", "makhana", "betelvine", "cocoa", "cumin", "fennel", "fenugreek",
              "manila", "tamarind", "moong", "mungbean", "urdbean", "pigeonpea", "chickpea", "amaranthus", "toria", "bajra", "maize", "wheat", "rice"}
        _CROP_WORDS = w - {"l", "pusa"}
    return _CROP_WORDS


def name_is_distinctive(text) -> bool:
    """A name form that can identify ONE variety: it has a digit, or it has a word that is not a crop / generic word and more
    than 3 letters in all. 'Cotton', 'Rice (Hybrid)', 'Black gram', 'CO', 'VBN' are not; 'Sahbhagi', 'CO 51', 'Pusa Ujwal' are."""
    t = re.sub(r"\([^)]*\)", " ", str(text or "")) if re.sub(r"\([^)]*\)", " ", str(text or "")).strip() else str(text or "")
    if re.search(r"\d", t): return True
    words = re.findall(r"[a-z]+", t.lower())
    letters = sum(len(x) for x in words)
    if letters <= 3: return False
    return any(x not in crop_words() and x not in _NAME_GENERIC_WORDS for x in words)


def name_quality(name) -> str:
    """ok | generic | truncated | numeric_only. Only 'ok' names are used for Seednet linking and publication matching.
      numeric_only: no letters at all ('4644', '28844').
      generic: only crop / generic words and no digits ('Cotton', 'Maize hybrid', 'Black gram', 'Tea (three species)'), unless a
               bracket alias is itself distinctive ('Cotton (NH-635)' is ok through 'NH-635').
      truncated: 3 letters or fewer and no digits ('CO', 'VBN', 'MPO', 'CSH'), or only a bracket ('(WE/05-146)')."""
    s = re.sub(r"\s+", " ", str(name or "")).strip()
    if not s or s.lower() in ("nan", "none", "null"): return "truncated"
    if s.startswith(",") or s.count(",") >= 2: return "generic"  # a list of several names ('Virat,Batil-11,Swad,Akshat, ...') is not one variety
    outside = re.sub(r"\([^)]*\)", " ", s)
    if outside.count(",") == 1 and all(len(re.sub(r"[^A-Za-z0-9]", "", x)) >= 2 for x in outside.split(",")): return "generic"  # 'Kaveri, Gauri', 'PAC-745,712': two names
    if not re.search(r"[A-Za-z]", s): return "numeric_only"
    core = re.sub(r"\([^)]*\)", " ", s).strip(" -/.,")
    aliases = [a for a in re.findall(r"\(([^)]*)\)", s) if a.strip()]
    if not core: return "truncated"
    if name_is_distinctive(core): return "ok"
    if any(name_is_distinctive(a) and re.search(r"[A-Za-z]{2}", a) for a in aliases): return "ok"
    words = re.findall(r"[a-z]+", core.lower())
    if sum(len(x) for x in words) <= 3: return "truncated"
    return "generic"


# ---------------------------------------------------------------- institutions: does a looked-up contact belong to THIS developer?
_INST_GENERIC = {"agricultural", "agriculture", "agril", "agri", "university", "universities", "institute", "research", "station", "regional", "zonal", "main", "centre", "center",
                 "national", "indian", "india", "icar", "college", "department", "division", "of", "and", "the", "for", "in", "at", "sciences", "science", "krishi", "vidyapeeth",
                 "vidyapeet", "vishwavidyalaya", "viswavidyalaya", "vishwa", "vidyalaya", "aicrp", "all", "coordinated", "project", "network", "on", "crops", "crop", "plant", "breeding",
                 "genetics", "technology", "horticultural", "horticulture", "horticulture", "pvt", "ltd", "limited", "private", "seeds", "seed", "company", "corporation", "co", "inc",
                 "dr", "sri", "shri", "rice", "wheat", "maize", "cotton", "pulses", "pulse", "oilseeds", "vegetable", "vegetables", "fruit", "fruits", "sugarcane", "millets", "sorghum",
                 "potato", "tuber", "farm", "farms", "government", "govt", "state", "district", "dist", "directorate", "director", "scientist", "breeder", "head", "office",
                 "pradesh", "uttar", "madhya", "andhra", "himachal", "arunachal", "west", "east", "north", "south", "tamil", "nadu", "post", "box", "road", "nagar", "po", "tq",
                 "rabi", "kharif", "improvement", "project", "unit", "sub", "group", "programme", "program", "bio", "biotech", "agro", "agrotech", "germplasm", "development", "cell"}
STATE_HINTS = {  # state -> words that place an institution in that state (state names, SAU acronyms, station towns); used only to compare two texts
    "Andhra Pradesh": ["andhra", "angrau", "acharya n", "ranga", "tirupati", "guntur", "maruteru", "nellore", "anakapalle", "lam", "ysrhu", "venkataramannagudem", "kovvur", "ghantasala", "bapatla", "nandyal", "kadiri", "anantapur", "peddapuram"],
    "Telangana": ["telangana", "pjtsau", "jayashankar", "warangal", "jagtial", "jagtiala", "palem", "kunaram", "rajendranagar", "adilabad", "madhira", "khammam", "tandur", "polasa", "rudrur"],
    "Rajasthan": ["rajasthan", "jobner", "sknau", "sriganganagar", "mpuat", "udaipur", "kota", "bikaner", "skrau", "ajmer", "jodhpur", "durgapura", "banswara", "mandor", "nrcss", "cazri", "navgaon", "tabiji"],
    "Karnataka": ["karnataka", "dharwad", "raichur", "gkvk", "bangalore", "bengaluru", "uahs", "shivamogga", "hanumanamatti", "kalaburagi", "gulbarga", "mandya", "bagalkot", "iihr", "hesaraghatta", "uasd", "uasr", "uhs", "mysore", "mysuru", "vc farm", "arabhavi", "nipani", "sankeshwar"],
    "Maharashtra": ["maharashtra", "mpkv", "rahuri", "pdkv", "akola", "vnmkv", "parbhani", "marathwada", "dbskkv", "dapoli", "karjat", "kolhapur", "nagpur", "pune", "badnapur", "amravati", "amaravati", "jalna", "niphad", "padegaon", "mahabeej", "jalgaon", "washim", "nanded", "igatpuri", "sindewahi", "ratnagiri"],
    "Gujarat": ["gujarat", "junagadh", "jau", "anand", "aau", "navsari", "nau", "sdau", "dantiwada", "sardarkrushinagar", "talod", "surat", "amreli", "vyara", "bharuch", "jamnagar", "dhandhuka", "arnej", "derol", "sanand", "vijapur"],
    "Madhya Pradesh": ["madhya pradesh", "jnkvv", "jabalpur", "rvskvv", "gwalior", "indore", "sehore", "rewa", "chhindwara", "khargone", "powarkheda", "tikamgarh", "morena", "mandsaur"],
    "Tamil Nadu": ["tamil nadu", "tamilnadu", "tnau", "coimbatore", "madurai", "aduthurai", "vamban", "paiyur", "bhavanisagar", "killikulam", "tiruchirapalli", "trichy", "periyakulam", "vridhachalam", "vriddhachalam", "kovilpatti", "tindivanam", "ambasamudram", "tirur", "srivilliputtur", "melalathur", "sirugamani", "aliyarnagar", "yethapur", "thogamalai", "nrcb", "palur", "ramanathapuram", "pkm"],
    "Odisha": ["odisha", "orissa", "ouat", "bhubaneswar", "cuttack", "nrri", "crri", "berhampur", "chiplima", "semiliguda", "nayagarh", "bhawanipatna", "kendrapara"],
    "Punjab": ["punjab", "ludhiana", "gurdaspur", "bathinda", "faridkot", "abohar", "kapurthala", "pau"],
    "Haryana": ["haryana", "hisar", "hau", "karnal", "iiwbr", "cssri", "kaul", "bawal", "uchani", "ccshau"],
    "Uttar Pradesh": ["uttar pradesh", "kanpur", "csauat", "csa", "nduat", "narendra deva", "faizabad", "ayodhya", "varanasi", "iivr", "meerut", "modipuram", "masodha", "iipr", "lucknow", "bhu", "banda", "jhansi", "shahjahanpur", "iisr lucknow", "seorahi", "nagina", "bulandshahr"],
    "Uttarakhand": ["uttarakhand", "pantnagar", "g.b. pant", "gbpuat", "gbpua", "almora", "vpkas", "majhera", "ranichauri"],
    "Bihar": ["bihar", "sabour", "rpcau", "dholi", "pusa samastipur", "samastipur", "patna", "mokama"],
    "West Bengal": ["west bengal", "bckv", "ubkv", "kalyani", "barrackpore", "crijaf", "cooch behar", "pundibari", "chinsurah", "hooghly", "mohanpur", "bankura", "uttar banga"],
    "Assam": ["assam", "jorhat", "titabar", "shillongani", "nagaon", "karimganj", "north lakhimpur", "gossaigaon", "aau, jorhat"],
    "Kerala": ["kerala", "kau", "thrissur", "vellanikkara", "pattambi", "moncompu", "kayamkulam", "cpcri", "kasaragod", "ctcri", "thiruvananthapuram", "trivandrum", "kozhikode", "calicut", "ambalavayal", "onattukara", "kumarakom", "vellayani", "mannuthy"],
    "Himachal Pradesh": ["himachal", "palampur", "cskhpkv", "solan", "nauni", "shimla", "y.s. parmar", "parmar", "ysp", "kangra", "bajaura", "dhaulakuan", "malan", "kukumseri"],
    "Jammu and Kashmir": ["jammu", "kashmir", "skuast", "srinagar", "shalimar", "rs pura", "khudwani", "wadura"],
    "Chhattisgarh": ["chhattisgarh", "igkv", "raipur", "bastar", "jagdalpur", "bilaspur", "ambikapur", "rajnandgaon"],
    "Jharkhand": ["jharkhand", "birsa", "ranchi", "bau ranchi", "dumka", "plandu"],
    "Delhi": ["new delhi", "iari", "nbpgr", "delhi"],
    "Manipur": ["manipur", "imphal", "cau"], "Meghalaya": ["meghalaya", "umiam", "barapani", "shillong"], "Tripura": ["tripura", "agartala"],
    "Nagaland": ["nagaland", "medziphema"], "Sikkim": ["sikkim", "gangtok"], "Mizoram": ["mizoram", "aizawl"], "Arunachal Pradesh": ["arunachal", "basar"],
    "Puducherry": ["puducherry", "pondicherry", "karaikal"], "Goa": ["goa"],
}


def institution_states(text) -> set[str]:
    t = " " + re.sub(r"\s+", " ", str(text or "")).lower() + " "
    out = set()
    for st, hints in STATE_HINTS.items():
        if any(re.search(r"(?<![a-z])" + re.escape(h) + r"(?![a-z])", t) for h in hints): out.add(st)
    return out


_ABBREV = [(r"\bagril?\.?(?=\s|$|,)", "agricultural"), (r"\bagri\.?(?=\s|$|,)", "agricultural"), (r"\buniv\.?(?=\s|$|,)", "university"),
           (r"\bres\.(?=\s)", "research"), (r"\bdeptt?\.?(?=\s)", "department"), (r"\bstn\.?(?=\s|$|,)", "station"), (r"\binst\.(?=\s)", "institute"),
           (r"\bpunjabrao\b", "Panjabrao"), (r"\bbanglore\b", "Bangalore"), (r"\bformerly\b|\bnow\b|\bthe\b", " ")]
_INST_GENERIC |= {"univ", "professor", "associate", "senior", "junior", "principal", "assistant", "incharge", "cum", "deptt", "dept", "officer", "section",
                  "scheme", "improvement", "coordinated", "india", "indian", "complex", "region", "regional", "centre", "council", "board", "foundation",
                  "trust", "society", "national", "central", "school", "faculty", "campus", "laboratory", "lab", "agronomist", "botanist", "economic",
                  "pin", "tal", "taluk", "taluka", "dist", "district", "post", "plot", "layout", "house", "near", "opp", "floor", "colony", "village", "street", "lane",
                  "building", "complex", "phase", "sector", "block", "area", "estate", "nagar", "marg", "chowk", "specialist", "breeder", "scientist", "director",
                  "ordinated", "search", "spices", "indo", "american", "international", "global", "hybrid", "agrigenetics", "ars", "rars", "zars", "rrs", "hrs", "mrs", "crs", "krs", "kvk", "sau", "aicrp", "aicrip", "icar", "nsp", "ltd", "pvt", "limited"}


def expand_abbrev(text) -> str:
    t = " " + str(text or "") + " "
    for pat, rep in _ABBREV: t = re.sub(pat, rep, t, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", t).strip()


def institution_tokens(text) -> set[str]:
    """Distinctive words / acronyms of an institution text: 'angrau', 'sknau', 'rasi', 'nuziveedu', 'navsari', 'birsa' ... (generic words removed)."""
    t = expand_abbrev(text)
    toks = {w for w in re.findall(r"[a-z]{3,}", t.lower().replace(".", "")) if w not in _INST_GENERIC}
    toks |= {re.sub(r"[^a-z]", "", a.lower()) for a in re.findall(r"\b[A-Z][A-Z.\-]{2,}[A-Z]\b", t)} - {""}
    return {x for x in toks if x not in _INST_GENERIC and x not in crop_words() and len(x) >= 3}


_STATION = re.compile(r"\b(?:(?:regional|zonal|main|sub|central)\s+)?(?:(?:agricultural|agriculture|horticultural|rice|wheat|cotton|pulses|oilseeds?|sugarcane|vegetable|fruit)\s+)?"
                      r"(?:research|experiment|experimental|regional|zonal|sub|extension)\s+(?:and\s+technology\s+transfer\s+)?(?:sub[\s-]*)?(?:station|centre|center|kendra|farm|unit|cell)\b"
                      r"|\b(?:station|farm|unit|cell)\b", re.IGNORECASE)
FORMER_NAMES = {"dpr": "iipr", "drr": "iirr", "dwr": "iiwbr", "dsr": "iimr", "nrcs": "iimr", "crri": "nrri", "pdkv": "pdkv", "mau": "vnmkv", "rau": "skrau",
                "gau": "jau", "apau": "angrau", "pkv": "pdkv", "iiwr": "iiwbr", "ihr": "iihr", "iihr": "iihr", "nbpgr": "nbpgr", "aphu": "ysrhu", "hau": "ccshau", "csau": "csauat", "ndua": "nduat", "nduat": "anduat", "cicr": "cicr"}


_PLACES = None


def _PLACES_CACHE() -> set[str]:
    global _PLACES
    if _PLACES is None: _PLACES = _place_words()
    return _PLACES


_ACR_ANCHOR = re.compile(r"universit|institute|vidyapeet|vidyalaya|vishwavidyalaya|sansthan|directorate|bureau|college", re.IGNORECASE)


def _acronyms(text) -> set[str]:
    """Initials of each comma/semicolon/slash/bracket/sentence part (ICAR / Dr / formerly ignored, station phrases removed):
    'Indian Agricultural Research Institute' -> 'iari'; 'R.V.S. Krishi Vishwa Vidyalaya' -> 'rvskvv'; 'SD Agricultural University' -> 'sdau'.
    'Vishwavidyalaya' is tried both as one word and as 'Vishwa Vidyalaya' (IGKV vs JNKVV conventions). A part made only of generic words
    gives an acronym only when it names a university / institute / college ('Department of Plant Breeding' and 'Senior Cotton Breeder' give none)."""
    out = set()
    base = expand_abbrev(text)
    variants = {base, re.sub(r"(?i)vi[sh]{1,2}[wv]a\s*vidyalaya", "Vishwa Vidyalaya", base), re.sub(r"(?i)vi[sh]{1,2}[wv]a\s*vidyalaya", "Vishwavidyalaya", base)}
    for v in variants:
        for part in re.split(r"[,;/()\[\]]|(?<=[a-z]{3})\.\s+(?=[A-Z][a-z])", v):
            part = re.sub(r"^\s*(ICAR|M/s\.?|Dr\.?)\s*[-–]?\s*", "", part.strip(), flags=re.IGNORECASE)
            part = _STATION.sub(" ", part)
            words = [w for w in re.findall(r"[A-Za-z]+", part) if w.lower() not in ("of", "and", "the", "for", "in", "at", "on", "dr")]
            while len(words) > 2 and words[-1].lower() in _PLACES_CACHE(): words = words[:-1]  # 'Indian Institute of Pulses Research Kanpur' -> 'iipr'
            if len(words) < 2: continue
            if all(w.lower() in _INST_GENERIC or w.lower() in crop_words() for w in words) and not _ACR_ANCHOR.search(part): continue
            mixed = part != part.upper()
            def ini(ws): return "".join(w.lower() if (mixed and w.isupper() and len(w) <= 4) else w[0].lower() for w in ws)
            letters = ini(words)
            if len(letters) >= 3 and letters not in _INST_GENERIC: out.add(letters)
            # windows that end at 'University' / 'Vidyapeeth' / 'Institute' ...: 'DEPARTMENT OF VEGETABLE CROPS HARYANA AGRICULTURAL UNIVERSITY' -> 'hau'
            for e, w in enumerate(words):
                if not _ACR_ANCHOR.search(w): continue
                for st in range(max(0, e - 5), e - 1):
                    if words[st].lower() in _INST_GENERIC or words[st].lower() in crop_words(): continue
                    acr = ini(words[st:e + 1])
                    if len(acr) >= 3 and acr not in _INST_GENERIC: out.add(acr)
    return out


def _letters(text) -> str: return re.sub(r"[^a-z]", "", expand_abbrev(text).lower())


def _with_former(acrs: set[str]) -> set[str]:
    """Former names of renamed institutes: Directorate of Pulses Research (DPR) = ICAR-IIPR, CRRI = NRRI, MAU = VNMKV, RAU = SKRAU ..."""
    return acrs | {FORMER_NAMES[x] for x in acrs if x in FORMER_NAMES}


_MULTI_INSTITUTE_TOWNS = {"hyderabad", "rajendranagar", "bangalore", "bengaluru", "coimbatore", "delhi", "lucknow", "kanpur", "cuttack", "ludhiana", "karnal", "jodhpur",
                          "pune", "varanasi", "jabalpur", "raipur", "ranchi", "patna", "bhubaneswar", "thiruvananthapuram", "trivandrum", "kozhikode", "calicut",
                          "shimla", "srinagar", "jhansi", "indore", "bhopal", "guwahati", "imphal", "barrackpore", "kalyani", "jorhat", "dharwad", "nagpur", "jaipur",
                          "bikaner", "udaipur", "junagadh", "pantnagar", "almora", "gwalior", "mysore", "mysuru"}
_AMBIGUOUS_ACRONYMS = {"uas", "aau", "bau", "cau", "rau", "hau", "kau", "jau", "nau", "uahs", "uhs", "iari", "icar", "aicrp"}


_HINT_ACRONYMS = {"angrau", "pjtsau", "sknau", "mpuat", "skrau", "uahs", "iihr", "uasd", "uasr", "uhs", "mpkv", "pdkv", "vnmkv", "dbskkv", "jau", "aau", "nau", "sdau",
                  "jnkvv", "rvskvv", "tnau", "ouat", "nrri", "crri", "pau", "hau", "iiwbr", "cssri", "ccshau", "csauat", "csa", "nduat", "iivr", "iipr", "bhu", "gbpuat",
                  "gbpua", "vpkas", "rpcau", "bckv", "ubkv", "crijaf", "kau", "cpcri", "ctcri", "cskhpkv", "ysp", "skuast", "igkv", "bau", "nbpgr", "iari", "cau", "pkm",
                  "nrcb", "nrcss", "cazri", "ysrhu", "mahabeej", "acharya n", "g.b. pant", "y.s. parmar", "parmar", "ranga", "jayashankar", "birsa", "narendra deva"}


def _place_words() -> set[str]:
    return {x.lower() for x in STATES} | {"tamil", "punjab", "haryana", "kerala", "assam", "bihar", "gujarat", "odisha", "orissa", "jammu", "kashmir", "delhi"} | {
        h for hs in STATE_HINTS.values() for h in hs if " " not in h and "." not in h and h not in _HINT_ACRONYMS}


def institution_agrees(developer_text, contact_text) -> tuple[bool, str]:
    """True when a looked-up institution contact plausibly belongs to the developer named in the CSC minutes / Seednet:
    a shared distinctive word or acronym, or (when there is none) the same state. Generic station names alone never agree.
    Returns (agrees, reason)."""
    a, b = institution_tokens(developer_text), institution_tokens(contact_text)
    a = _with_former(a | _acronyms(developer_text)); b = _with_former(b | _acronyms(contact_text))
    places = _place_words()
    na, nb = re.sub(r"[^a-z]", "", str(developer_text).lower()), re.sub(r"[^a-z]", "", str(contact_text).split(";")[0].lower())
    if (len(nb) >= 20 and (nb in na or (len(na) >= 20 and na in nb)) and (institution_tokens(developer_text) | _acronyms(developer_text)) - places) or (
            len(nb) >= 45 and nb in na) or (len(na) >= 45 and na in nb):
        return True, "same institution name"
    sa_, sb_ = institution_states(developer_text), institution_states(contact_text)
    shared = {x for x in a & b if x not in places or x in _acronyms(developer_text) | _acronyms(contact_text)}
    if sa_ and sb_ and not (sa_ & sb_) and not (shared - _AMBIGUOUS_ACRONYMS):  # a distinctive shared name (Rasi, ICRISAT, CICR) wins over a head-office state
        return False, f"different state (developer {', '.join(sorted(sa_))}; contact {', '.join(sorted(sb_))})"
    if shared and shared <= _AMBIGUOUS_ACRONYMS:  # 'UAS' Raichur is not 'UAS' Bangalore: an ambiguous acronym needs the same town too
        ta, tb = {x for x in a if x in places}, {x for x in b if x in places}
        if ta and tb and not (ta & tb): return False, f"same acronym ({', '.join(sorted(shared))}) but different place ({', '.join(sorted(ta))} / {', '.join(sorted(tb))})"
    if shared: return True, "shared name/acronym: " + ", ".join(sorted(shared)[:3])
    la, lb = _letters(developer_text), _letters(contact_text)  # 'JNK VV' = 'JNKVV'; 'CCSHAU' = 'CCS HAU'
    acr = _acronyms(developer_text) | _acronyms(contact_text) | {w.lower() for w in re.findall(r"\b[A-Z]{4,7}\b", f"{developer_text} {contact_text}")
                                                                if w.lower() not in _INST_GENERIC and w.lower() not in crop_words() and w.lower() not in {"seeds", "india", "state"}}
    hit = sorted({x for x in acr if len(x) >= 4 and x not in places and (x in la and x in lb)})
    if hit: return True, "shared acronym: " + ", ".join(hit[:3])
    town = {x for x in a & b if x in places and x not in _MULTI_INSTITUTE_TOWNS and x not in {y.lower() for y in STATES}}
    if town and (not institution_states(developer_text) or institution_states(developer_text) & institution_states(contact_text)):
        return True, "same town: " + ", ".join(sorted(town)[:2])
    sa, sb = institution_states(developer_text), institution_states(contact_text)
    if a and b: return False, "different institution names (no shared distinctive word or acronym)"  # same state alone: Anand AU is not Navsari AU
    if sa and sb:
        if sa & sb: return True, "same state: " + ", ".join(sorted(sa & sb))
        return False, f"different state (developer {', '.join(sorted(sa))}; contact {', '.join(sorted(sb))})"
    return False, "no shared name, acronym or state"


def institution_score(developer_text, contact_text) -> float:
    """How strongly a contact entry names the developer: each shared acronym 2, shared distinctive word 1, shared place-only word 0.5,
    acronym written with spaces in one text and joined in the other ('JNK VV' / 'JNKVV') 2; -inf when both name a state and the states differ.
    Used to search the contact table by name when the lookup key gave no agreeing contact."""
    a, b = institution_tokens(developer_text), institution_tokens(contact_text)
    aa, ab = _acronyms(developer_text), _acronyms(contact_text)
    sa, sb = institution_states(developer_text), institution_states(contact_text)
    if sa and sb and not (sa & sb): return float("-inf")
    caps = {w.lower() for w in re.findall(r"\b[A-Z]{3,}\b", str(developer_text) + " " + str(contact_text))}
    places = {x.lower() for x in STATES} | {h for hs in STATE_HINTS.values() for h in hs if " " not in h}
    score = 0.0
    for x in (a | aa) & (b | ab):
        score += 2 if (x in aa or x in ab or x in caps) else 0.5 if x in places else 1
    la, lb = _letters(developer_text), _letters(contact_text)
    score += 2 * len({x for x in (aa | ab) - ((a | aa) & (b | ab)) if len(x) >= 4 and x in la and x in lb})
    return score
