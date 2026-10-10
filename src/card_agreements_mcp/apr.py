"""APR block parsing: per card product, intro rate, variable/fixed, index and margin.

Every value is read from the block of agreement text that follows an APR label and is returned with that snippet.
Margins and stated rates are kept apart: `basis` says whether the block states an APR figure ("stated"), only an index plus margin
("margin"), or neither ("unknown"). Nothing is computed here.
"""
import re

WORDNUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
           "twelve": 12, "fifteen": 15, "eighteen": 18, "twenty-four": 24}
NUM = r"(\d+|" + "|".join(WORDNUM) + r")(?:\s*\(\d+\))?"
PER = r"(billing\s+cycles?|statement\s+cycles?|statement\s+closing\s+dates?|months?)"
INTRO1 = re.compile(r"(\d{1,2}(?:\.\d+)?)\s?%\s*(?:intro\w*|promo\w*)\s*(?:apr|rate)?[^%]{0,70}?\bfor\s+(?:the\s+|your\s+|a\s+period\s+of\s+|a\s+)?(?:first\s+)?" + NUM + r"\s+" + PER, re.I)
INTRO2 = re.compile(r"(?:intro\w*|promo\w*)\s+(?:apr|rate)[^%]{0,40}?(\d{1,2}(?:\.\d+)?)\s?%[^%]{0,60}?\bfor\s+(?:the\s+|your\s+|a\s+period\s+of\s+|a\s+)?(?:first\s+)?" + NUM + r"\s+" + PER, re.I)
INTRO3 = re.compile(r"(\d{1,2}(?:\.\d+)?)\s?%\s*(?:apr\s+)?for\s+(?:the\s+|your\s+|a\s+period\s+of\s+|a\s+)?(?:first\s+)?" + NUM + r"\s+" + PER, re.I)
INTRO_WORD = re.compile(r"(?<!non-)(?<!non )\b(?:intro\w*|promotional|promo)\s+(?:apr|rate|annual|period|purchase\s+apr|interest)\b|\d\s?%\s*(?:intro\w*|promotional|promo)\b", re.I)
MARGIN = [
    re.compile(r"prime(?:\s+rate)?\s*(?:\([^)]{0,30}\))?\s*(?:plus|\+)\s*(?:a\s+margin\s+of\s+)?(\d{1,2}(?:\.\d+)?)\s?%(?:\s*(?:to|-|\u2013|or)\s*(\d{1,2}(?:\.\d+)?)\s?%)?", re.I),
    re.compile(r"add(?:ing)?\s+(?:a\s+margin\s+of\s+)?((?:\d{1,2}(?:\.\d+)?\s?%(?:\s*(?:,|or|and|to|-|\u2013)\s*)?)+)\s+to\s+(?:the\s+)?(?:wsj\s+|wall\s+street\s+journal\s+)?prime", re.I),
    re.compile(r"margin\s+of\s+(\d{1,2}(?:\.\d+)?)\s?%(?:\s*(?:to|-|\u2013|or)\s*(\d{1,2}(?:\.\d+)?)\s?%)?", re.I),
]
PCTRX = re.compile(r"\d{1,3}(?:\.\d+)?\s?%")
NOISE = re.compile(r"(prime(?:\s+rate)?\s+(?:of|is|was)\s+\d[\d.]*\s?%|\d[\d.]*\s?%\s+prime\s+rate|periodic\s+rate\s+of\s+\d[\d.]*\s?%|(?:not\s+(?:exceed|be\s+more\s+than)|never\s+(?:be\s+)?(?:more|exceed)\w*|maximum\s+(?:apr\s+)?(?:is|of)?|up\s+to)\s*\d[\d.]*\s?%|\d[\d.]*\s?%\s*\(\s*dpr|corresponding\s+(?:to\s+)?(?:a\s+)?(?:daily\s+)?periodic\s+rate\s+of\s+\d[\d.]*\s?%)", re.I)
HEAD = re.compile(r"^[A-Z][A-Za-z0-9\u00ae\u2122&/+\- ]{2,40}$")
HSTOP = re.compile(r"\b(apr|rate|rates|fee|fees|interest|annual|percentage|purchase|purchases|balance|cash|advance|advances|transfer|transfers|charges?|table|disclosure|agreement|account|credit|card\s+agreement|the|your|you|will|may|and\s+fees|for|to|of|on|how|what|when)\b", re.I)


def _tonum(x):
    x = x.lower()
    return WORDNUM.get(x) if x in WORDNUM else int(x)


def _heading_ok(s):
    s = s.strip()
    return bool(HEAD.match(s)) and len(s.split()) <= 5 and not re.search(r"\d|%", s) and not HSTOP.search(s)


def card_name_before(lines, start, i):
    """Product heading for a block: text in a right-hand column of the label line, or a short standalone line just above."""
    for l in lines[start:i + 1]:
        m = re.search(r"\S {5,}([A-Z][A-Za-z0-9\u00ae\u2122&/+\- ]{2,40})\s*$", l)
        if m and _heading_ok(m.group(1)):
            return m.group(1).strip()
    for k in range(start - 1, max(start - 4, -1), -1):
        if k < 0 or not lines[k].strip():
            if k >= 0 and k < start - 1:
                break
            continue
        if _heading_ok(lines[k]):
            return lines[k].strip()
        break
    return None


def split_cards(lines, start, end, i):
    """[(card_name or None, first_line, last_line)] inside one APR block; the block is cut at standalone heading lines that follow a blank line."""
    cuts = []
    for k in range(i + 1, end):
        if _heading_ok(lines[k]) and not lines[k - 1].strip() and k + 1 < end and PCTRX.search(" ".join(lines[k + 1:k + 3])):
            cuts.append(k)
    first = card_name_before(lines, start, i)
    segs, s, name = [], start, first
    for c in cuts:
        segs.append((name, s, c)); s, name = c + 1, lines[c].strip()
    segs.append((name, s, end))
    return segs


def parse(text):
    """Flags for one APR block of text (already whitespace-collapsed)."""
    t = " ".join(text.split())
    out = {}
    intro = None
    for rx in (INTRO1, INTRO2, INTRO3):
        m = rx.search(t)
        if m and (rx is not INTRO3 or INTRO_WORD.search(t[max(0, m.start() - 60):m.end() + 30])):
            intro = m; break
    if intro:
        out["has_intro"] = 1; out["intro_rate"] = float(intro.group(1)); out["intro_period"] = "%d %s" % (_tonum(intro.group(2)), " ".join(intro.group(3).lower().split()))
    elif INTRO_WORD.search(t):
        out["has_intro"] = 1; out["intro_rate"] = None; out["intro_period"] = None  # mentioned, details not parsed
    else:
        out["has_intro"] = None; out["intro_rate"] = None; out["intro_period"] = None
    margins = []
    for rx in MARGIN:
        for m in rx.finditer(t):
            for g in m.groups():
                if g: margins += [float(x) for x in re.findall(r"\d{1,2}(?:\.\d+)?", g)]
    low = t.lower()
    idx = None
    if "prime" in low:
        idx = "WSJ Prime Rate" if re.search(r"wsj|wall street journal", low) else "Prime Rate"
    elif "sofr" in low: idx = "SOFR"
    elif "libor" in low: idx = "LIBOR"
    elif re.search(r"treasury", low): idx = "Treasury"
    notvar = re.search(r"\b(?:will|does|do)\s+not\s+vary\b|\bfixed\b", low)
    var = re.search(r"\bvar(?:y|ies|iable)\b|\bprime\b", low)
    out["is_variable"] = (None if (notvar and var) else 0 if notvar else 1 if var else None)
    out["index_name"] = idx if out["is_variable"] == 1 else None
    out["margin_min"] = min(margins) if margins else None
    out["margin_max"] = max(margins) if margins else None
    rest = t
    for rx in MARGIN: rest = rx.sub(" @M@ ", rest)
    rest = re.sub(r"@M@\s*(?:rate\s+)?(?:of|is)\s+\d[\d.]*\s?%", " ", rest, flags=re.I)
    rest = NOISE.sub(" ", rest)
    if intro: rest = rest.replace(intro.group(0), " ")
    rest = re.sub(r"\bprime\s+rate\s+of\s+\d[\d.]*\s?%", " ", rest, flags=re.I)
    stated = bool(PCTRX.search(rest))
    out["basis"] = "stated" if stated else ("margin" if margins else "unknown")
    if out["has_intro"] is None and stated: out["has_intro"] = 0
    return out
