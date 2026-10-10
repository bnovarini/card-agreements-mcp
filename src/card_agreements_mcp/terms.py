import re, json, sqlite3, sys
T={
 'annual_fee': r'annual\s+fees?\b',
 'purchase_apr': r'(annual\s+percentage\s+rate\s*\(?apr\)?\s*(for|on)\s*purchases?|\(?apr\)?\s+(for|on)\s+purchases?|purchases?\s*\(?apr\)?|purchase\s+(apr|rate)|apr\s*for\s*purchase)',
 'cash_advance_apr': r'(cash\s+advance\s+apr|apr\s+for\s+cash\s+advances?)',
 'balance_transfer_apr': r'(apr\s+for\s+balance\s+transfers?|balance\s+transfer\s+apr)',
 'penalty_apr': r'penalty\s+apr',
 'paying_interest': r'paying\s+interest|grace\s+period',
 'minimum_interest_charge': r'minimum\s+interest\s+charge',
 'foreign_transaction_fee': r'foreign\s+(transaction|currency)(\s+fee)?|international\s+transaction',
 'late_payment_fee': r'late\s+(payment|fee)',
 'returned_payment_fee': r'returned\s+(payment|check)',
 'balance_transfer_fee': r'balance\s+transfer(\s+fee)?\s*[:\-•\s]',
 'cash_advance_fee': r'(cash\s+advance(?!\s+apr)(\s+fee)?|atm\s+cash\s+advance)\s*[:\-•\s]',
 'over_limit_fee': r'(over[\s-]*(the[\s-]*)?limit)',
}
# purchase APR labels split over two lines: "Purchase Annual" / "Percentage Rate (APR)" and "Annual Percentage Rate (APR)" / "for Purchases"
SPLIT_A = re.compile(r'^\s*(annual\s+)?percentage\s+rate\s*\(apr\)', re.I)
SPLIT_A_PREV = re.compile(r'purchases?\s*(annual)?\s*$', re.I)
SPLIT_B = re.compile(r'^\s*[•\-\*]?\s*annual\s+percentage\s+rate\s*\(apr\)', re.I)
SPLIT_C = re.compile(r'^\s*(annual\s+)?percentage\s+rate\s*\(apr\)\s*(for|on)(\s+[A-Za-z0-9\u00ae\u2122&\-/\. ]{1,60})?\s*$', re.I)
SPLIT_C_NEXT = re.compile(r'^\s*purchases?(\s|$)', re.I)
SPLIT_B_NEXT = re.compile(r'^\s*for\s+purchases?\b', re.I)
# sentence and table forms of the purchase APR (found by mining agreements without a hit)
PURCH_EXTRA = [re.compile(x, re.I) for x in (
    r'\(apr\)\s+for\s+\d{1,2}(\.\d+)?\s?%\s+(?:[A-Za-z\-]+\s+){0,3}purchases\b',
    r'\bannual\s+percentage\s+rates?\s*(\(apr\)\s*)?(for|on)\s+purchases?\s+(this|these|prime|\d)',
    r'\bannual\s+percentage\s+rate\s*\(apr\)\s+pu\s+\d{1,2}(\.\d+)?\s?%',
    r'\(apr\)\s*for\s+(?:[A-Za-z0-9\u00ae\u2122&\-/\.]+\s+){1,6}purchases?\s+\d{1,2}(\.\d+)?\s?%',
    r'\b(introductory\s+|variable\s+|current\s+|standard\s+)?purchase\s+apr\s+(is|will\s+be|of)\b',
    r'\bapr\s+for\s+purchases?\s+(is|may)\b',
    r'^\s*(\*\s*)?purchases?\s+\d{1,2}(\.\d+)?\s?%(\s+to\s+\d{1,2}(\.\d+)?\s?%)?\s+(introductory\s+)?apr',
    r'\bpurchases?\s+and\s+balance\s+transfers?\s+\d{1,2}(\.\d+)?\s?%(\s+to\s+\d{1,2}(\.\d+)?\s?%)?\s+apr',
    r'^\s*rate\s*\(apr\)\s+for\s+purchases?',
    r'\bdaily\s+(periodic\s+)?rate\s+for\s+purchases?\s+(is|will)\b',
    r'\bthe\s+apr\s+is\s+\d{1,2}(\.\d+)?\s?%\s+on\s+purchases\b',
    r'^\s*purchase\s+annual\b',
    r'\d\s?%\s+introductory\s+apr\s+for\s+purchases?\s+made\b',
    r'\d\s?%\s+apr\s+for\s+\d+\s+(billing\s+cycles|months)\s+on\s+purchases',
)]
def _split_label(lines, i):
    l = lines[i]
    if SPLIT_A.match(l) and i > 0 and SPLIT_A_PREV.search(lines[i-1].strip()) and len(lines[i-1]) < 120:
        return True
    if any(rx.search(l) for rx in PURCH_EXTRA):
        return True
    if SPLIT_C.match(l) and i + 1 < len(lines) and SPLIT_C_NEXT.match(lines[i+1]):
        return True
    if SPLIT_B.match(l) and i + 1 < len(lines) and SPLIT_B_NEXT.match(lines[i+1]):
        return True
    return False
RX={k:re.compile(r'^[\s•\-\*\u2022\u25cf]*'+v,re.I) for k,v in T.items()}
AMT=re.compile(r'\$\s?\d[\d,]*(?:\.\d+)?'); PCT=re.compile(r'\d{1,3}(?:\.\d+)?\s?%')
APR_TERMS = ('purchase_apr', 'balance_transfer_apr', 'cash_advance_apr')
_X = {'balance_transfer_apr': r'balance\s+transfers?', 'cash_advance_apr': r'cash\s+advances?'}
_APR_TPL = (
    r'^\s*(annual\s+percentage\s+rate\s*)?\(?apr\)?\s*(for|on)\s+{X}\b',
    r'\b{X}\s+apr\s+(is|will\s+be|of)\b',
    r'^\s*(\*\s*)?{X}\s+\d{{1,2}}(\.\d+)?\s?%(\s+to\s+\d{{1,2}}(\.\d+)?\s?%)?\s+(introductory\s+)?apr',
    r'^\s*rate\s*\(apr\)\s+for\s+{X}',
    r'^\s*(\*\s*)?{X}\s+(annual\s+percentage\s+rate|apr)\b',
    r'^\s*\(?apr\)?\s+{X}\b',
)
APR_EXTRA = {k: [re.compile(t.format(X=x), re.I) for t in _APR_TPL] for k, x in _X.items()}
APR_MULTI = [
    (re.compile(r'^\s*annual\s+percentage\s+rates?\s+(for|on)\s+purchases?\s*$', re.I), ('purchase_apr',)),
    (re.compile(r'^\s*annual\s+percentage\s+rates?\s+(for|on)\s+balance\s+transfers?\s*$', re.I), ('balance_transfer_apr',)),
    (re.compile(r'^\s*annual\s+percentage\s+rates?\s+(for|on)\s+cash\s+advances?\s*$', re.I), ('cash_advance_apr',)),
    (re.compile(r'^\s*annual\s+percentage\s+rate\s*\(apr\)\s+pu\s*$', re.I), ('purchase_apr',)),
    (re.compile(r'^\s*apr\s+for\s+(direct\s+deposit\s+and\s+check\s+cash|bank\s+cash\s+advances?)\b', re.I), ('cash_advance_apr',)),
    (re.compile(r'\bpurchases?\s*(?:/|,|and)\s*balance\s+transfers?\s+(?:apr|annual)', re.I), ('purchase_apr', 'balance_transfer_apr')),
    (re.compile(r'\bpurchases?\s+and\s+balance\s+transfers?\s+\d{1,2}(\.\d+)?\s?%', re.I), ('purchase_apr', 'balance_transfer_apr')),
    (re.compile(r'\bapr\s+for\s+purchases?\s*,\s*balance\s+transfers?', re.I), ('purchase_apr', 'balance_transfer_apr', 'cash_advance_apr')),
    (re.compile(r'\bpurchases?,\s*balance\s+transfers?\s*(,|and)\s*cash\s+advances?', re.I), ('purchase_apr', 'balance_transfer_apr', 'cash_advance_apr')),
]
_SPLIT_X = {'balance_transfer_apr': re.compile(r'^\s*for\s+balance\s+transfers?\b', re.I), 'cash_advance_apr': re.compile(r'^\s*for\s+cash\s+advances?\b', re.I)}
_BOUNDARY = re.compile(r'^\s*(paying\s+interest|how\s+to\s+avoid|minimum\s+interest|transaction\s+fees|balance\s+computation|fees\b)', re.I)
NONE_APR = (None, 'agreement', None, None, None, None, None, None, None, None)
EMPTY = (None, 'agreement', None, None, None, None, None, None, None, None)


REGULAR_APR = re.compile(r'\bregular\s+apr\s+(ranges\s+from|is)\s+\d', re.I)


def _apr_hits(lines):
    """{line index: set of APR terms whose label sits on that line}."""
    hits = {}
    for i, l in enumerate(lines):
        if len(l) > 400: continue
        for k in APR_TERMS:
            if RX[k].match(l) or (k == 'purchase_apr' and _split_label(lines, i)):
                hits.setdefault(i, set()).add(k)
            elif k in APR_EXTRA and any(rx.search(l) for rx in APR_EXTRA[k]):
                hits.setdefault(i, set()).add(k)
        for rx, ks in APR_MULTI:
            if rx.search(l): hits.setdefault(i, set()).update(ks)
        if REGULAR_APR.search(l):
            win = ' '.join(lines[max(0, i - 4):i + 16])
            if re.search(r'percentage\s+rate', win, re.I) and re.search(r'\bpurchases\b', win, re.I) and re.search(r'\bbalance\b.{0,500}\btransfers?\b', win, re.I):
                hits.setdefault(i, set()).update(APR_TERMS)  # vertical label table: one shared value cell for all rows
        if SPLIT_B.match(l) and i + 1 < len(lines):
            for k, nx in _SPLIT_X.items():
                if nx.match(lines[i + 1]): hits.setdefault(i, set()).add(k)
    return hits


def extract(text):
    from . import apr as A
    out = []
    pages = text.split('\f')
    for pi, pg in enumerate(pages, 1):
        lines = pg.split('\n')
        hits = _apr_hits(lines)
        hit_idx = sorted(hits)
        for i, l in enumerate(lines):
            if len(l) > 400: continue
            for k, rx in RX.items():
                if k in APR_TERMS or not rx.match(l): continue
                snip = ' '.join(' '.join(lines[i:i + 4]).split())[:360]
                if not (AMT.search(snip) or PCT.search(snip) or re.search(r'\bnone\b|\bno\b|\bnot\b|waive|days', snip, re.I)): continue
                out.append((k, pi, snip, json.dumps(AMT.findall(snip)[:6]), json.dumps(PCT.findall(snip)[:6]),
                            int(bool(re.search(r'\bnone\b|\bno\s+(annual|fee|foreign)', snip[:120], re.I)))) + EMPTY)
        for i in hit_idx:
            start = i - 1 if i > 0 and 'annual percentage' in lines[i - 1].lower() and 'annual percentage' not in lines[i].lower() else i
            end = min(i + 14, len(lines))
            for j in hit_idx:
                if j > i and (hits[j] != hits[i] or True) and j < end:
                    end = j; break
            for j in range(i + 1, end):
                if _BOUNDARY.match(lines[j]): end = j; break
            for k in sorted(hits[i]):
                for name, a, b in A.split_cards(lines, start, end, i):
                    snip = ' '.join(' '.join(lines[a:b]).split())[:700]
                    if not (PCT.search(snip) or 'prime' in snip.lower()) or not re.search(r'[A-Za-z]{3}', snip): continue
                    f = A.parse(snip)
                    out.append((k, pi, snip, json.dumps(AMT.findall(snip)[:6]), json.dumps(PCT.findall(snip)[:8]), 0,
                                name, 'card' if name else 'agreement', f['has_intro'], f['intro_rate'], f['intro_period'], f['is_variable'],
                                f['index_name'], f['margin_min'], f['margin_max'], f['basis']))
    cnt = {}; res = []
    seen = set()
    for r in out:
        if r[0] in APR_TERMS:
            # daily periodic rates (4+ decimals, e.g. 0.04792%) are not APRs: drop them from the list, and drop rows that had only those
            ps = json.loads(r[4]); keep = [x for x in ps if not re.search(r'\.\d{4,}', x)]
            if ps and not keep and r[13] is None: continue
            if not keep and r[13] is None and not re.search(r'_{3,}|X\.XX|x\.xx|\b\d{1,2}\.\d{2}\s+(to|-)\s+\d{1,2}\.\d{2}\b', r[2]): continue  # label with no figure at all: noise
            if len(keep) != len(ps): r = r[:4] + (json.dumps(keep),) + r[5:]
        key = (r[0], r[1], r[2][:80], r[6])
        if key in seen: continue
        seen.add(key)
        cnt[r[0]] = cnt.get(r[0], 0) + 1
        if cnt[r[0]] <= (8 if r[0] in APR_TERMS else 3): res.append(r)
    return res
