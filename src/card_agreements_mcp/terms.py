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
    r'\(apr\)\s*for\s+(?:[A-Za-z0-9\u00ae\u2122&\-/\.\(\)]+\s+){1,6}purchases?\s+\d{1,2}(\.\d+)?\s?%',
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
    r'\bannual\s+percentage\s+rate\s*\(apr\)\s+for\s+\d{1,2}(\.\d+)?\s?%\s+when\s+you\s+open\s+your\s+account',
    r'\bpurchases?\s+(variable|fixed)\s+rate\s*:\s*\d{1,2}(\.\d+)?',
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
_BOUNDARY = re.compile(r'^\s*(penalty\s+apr|paying\s+interest|how\s+to\s+avoid|minimum\s+interest|transaction\s+fees|balance\s+computation|fees\b)', re.I)
NONE_APR = (None, 'agreement', None, None, None, None, None, None, None, None)
EMPTY = (None, 'agreement', None, None, None, None, None, None, None, None)


REGULAR_APR = re.compile(r'\bregular\s+apr\s+(ranges\s+from|is)\s+\d', re.I)


SPANISH_MARGIN = re.compile(r'Margen\s+sumado\s+a\s+la\s+Tasa\s+(Preferencial|[\u00cdI]ndice)', re.I)


def _spanish_margin_rows(pg, pi):
    """Spanish agreements state 'Margen sumado a la Tasa Preferencial ... Tasa APR para compras ... 11.74% - 21.74%'.
    The figure is a margin over the index, not an APR, so it is stored as margin only (basis='margin')."""
    flat = ' '.join(pg.split())
    rows = []
    for m in SPANISH_MARGIN.finditer(flat):
        win = flat[m.start():m.start() + 330]
        win = re.sub(r'm[a\u00e1]xima\s+es\s+del\s+\d{1,2}(?:\.\d+)?\s?%', ' ', win, flags=re.I)  # the cap is not a margin
        head = win[:200].lower()
        kw = re.search(r'compras|adelantos', head)  # first product word after the label decides the term
        if not kw: continue
        if kw.group(0) == 'adelantos': terms = ('cash_advance_apr',)
        else:
            tr = re.search(r'transferencias', head)
            terms = ('purchase_apr', 'balance_transfer_apr') if tr and tr.start() < kw.end() + 12 else ('purchase_apr',)
        allp = list(re.finditer(r'(\d{1,2}\.\d{1,2})\s?%', win))
        if not allp: continue
        pcts = [float(allp[0].group(1))]
        # a second figure is the other end of a margin range only when the first is followed by '-' or 'a' ("11.74% -", "6.74% a 21.74%")
        if len(allp) > 1 and re.match(r'\s*(?:-|\u2013|a)\s', win[allp[0].end():allp[0].end() + 6]):
            pcts.append(float(allp[1].group(1)))
        idx = 'Prime Rate' if m.group(1).lower() == 'preferencial' else 'Index'
        for k in terms:
            rows.append((k, pi, win[:360], '[]', json.dumps(['%.2f%%' % x for x in pcts]), 0, None, 'agreement', None, None, None, 1, idx, min(pcts), max(pcts), 'margin'))
    return rows


_MARGIN_HDR = re.compile(r'\bmargin\b.{0,160}\b(corresponding\s+)?apr\b', re.I | re.S)
_ROW_START = re.compile(r'^\s*(purchases?|balance\s+transfers?|cash\s+advances?|penalty\s+apr)\b', re.I)


def _margin_table_rows(lines, pi):
    """Pricing-addendum tables: Feature / Margin / Daily Periodic Rate / Corresponding APR.
    Both the stated 'Corresponding APR' and the 'Margin' column are stored; daily periodic rates (4+ decimals) are ignored."""
    out = []
    for i, l in enumerate(lines):
        if not (re.search(r'\bmargin\b', l, re.I) and re.search(r'\b(corresponding\s+)?apr\b', ' '.join(lines[i:i + 3]), re.I)):
            continue
        if not re.search(r'\bfeature\b', ' '.join(lines[max(0, i - 1):i + 2]), re.I): continue
        groups, cur = [], None
        for j in range(i + 1, min(i + 16, len(lines))):
            t = lines[j]
            if not t.strip():
                if cur: groups.append(cur); cur = None
                if groups: break
                continue
            if _ROW_START.match(t):
                if cur: groups.append(cur)
                cur = [t]
            elif cur is not None and not re.match(r'\s*(minimum|summary|fee\b)', t, re.I): cur.append(t)
            elif cur is None and groups: break
        if cur: groups.append(cur)
        for g in groups:
            txt = ' '.join(' '.join(g).split())
            nums = [float(x) for x in re.findall(r'(\d{1,2}\.\d{2})\s?%', re.sub(r'\d{1,2}\.\d{4,}\s?%', ' ', txt))]
            if len(nums) == 4:
                # a row whose ranges wrap shows 'margin lo, APR lo' on the first physical line and 'margin hi, APR hi' on the next;
                # a one-line row shows margin lo/hi then APR lo/hi. Either way APR - margin must agree at both ends.
                per = [[float(x) for x in re.findall(r'(\d{1,2}\.\d{2})\s?%', re.sub(r'\d{1,2}\.\d{4,}\s?%', ' ', ln))] for ln in g]
                per = [x for x in per if x]
                if len(per) == 1: mg, ap = (nums[0], nums[1]), (nums[2], nums[3])
                elif len(per) == 2 and len(per[0]) == 2 and len(per[1]) == 2: mg, ap = (per[0][0], per[1][0]), (per[0][1], per[1][1])
                else: continue
                if not (ap[0] > mg[0] and abs((ap[0] - mg[0]) - (ap[1] - mg[1])) < 0.021): continue
            elif len(nums) == 2 and nums[1] > nums[0]: mg, ap = (nums[0], nums[0]), (nums[1], nums[1])
            else: continue
            label = txt.lower()
            if label.startswith('penalty'): terms = ('penalty_apr',)
            elif label.startswith('cash'): terms = ('cash_advance_apr',)
            elif label.startswith('purchase'): terms = ('purchase_apr', 'balance_transfer_apr') if re.match(r'purchases?\s+(and|&)\s+balance', label) else ('purchase_apr',)
            elif label.startswith('balance'): terms = ('balance_transfer_apr',)
            else: continue
            pcts = sorted(set(['%.2f%%' % ap[0], '%.2f%%' % ap[1]]), key=lambda x: float(x[:-1]))
            ctx = ' '.join(' '.join(lines[max(0, i - 12):i + 1]).split()).lower()
            for k in terms:
                out.append((k, pi, txt[:360], '[]', json.dumps(pcts), 0, None, 'agreement', None, None, None,
                            1 if '(v)' in label else None, 'Prime Rate' if 'prime rate' in ctx else None, mg[0], mg[1], 'stated'))
    return out


_NUM = r'\d{1,2}(?:\.\d+)?\s?%'
_RNG = r'(?:\s*(?:to|up\s+to|-|\u2010|\u2011|\u2012|\u2013|\u2212|WR)\s*' + _NUM + r')?(?!\s*\d{1,2}(?:\.\d+)?\s?%)(?!\s*\*?\s*(?:per\s+month|monthly|days|months|introductory|intro\b|\d+\s?mo))'
_FLAT = [
    # one rate shared by three products: "APR for Purchases, Balance Transfers and 20.75% Cash Advances"
    (re.compile(r'\(APR\)\s+for\s+Purchases,\s+Balance\s+Transfers,?\s+and\s+(' + _NUM + _RNG + r')\s+Cash\s+Advances', re.I),
     ('purchase_apr', 'balance_transfer_apr', 'cash_advance_apr')),
    # value sits between the label and the product word: "Annual Percentage Rate (APR) for 9.40% to 17.40% , when you open your account, based on your Purchases"
    (re.compile(r'(?:annual\s+percentage\s+rates?\s*(?:\(apr\))?|\(apr\))\s+for\s+(?:from\s+)?(' + _NUM + _RNG + r')[^%]{0,130}?(?-i:\b(?:Purchases|PURCHASES)\b)', re.I), ('purchase_apr',)),
    (re.compile(r'\bAPR\s+for\s+Balance\s+Transfers\s+(?:from\s+)?(' + _NUM + _RNG + r')', re.I), ('balance_transfer_apr',)),
    (re.compile(r'\bAPR\s+for\s+Cash\s+Advances\s+(?:from\s+)?(' + _NUM + _RNG + r')', re.I), ('cash_advance_apr',)),
    (re.compile(r'\bANNUAL\s+PERCENTAGE\s+RATE\s+(' + _NUM + _RNG + r')[^%]{0,120}?\bfor\s+(?-i:Purchases|PURCHASES)\b', re.I), ('purchase_apr',)),
    (re.compile(r'\bANNUAL\s+PERCENTAGE\s+RATE\s+(' + _NUM + _RNG + r')\s+for\s+Balance\s+Transfers', re.I), ('balance_transfer_apr',)),
    (re.compile(r'\bANNUAL\s+PERCENTAGE\s+RATE\s+(' + _NUM + _RNG + r')\s+for\s+Cash\s+Advances', re.I), ('cash_advance_apr',)),
]
_INTRO_LIST = re.compile(r'\b(Credit\s+Purchases|Balance\s+Transfers|Cash\s+Advances):\s*(?:(' + _NUM + r')\s+introductory\s+APR\s+for\s+(\d+\s+\w+)\s*After\s+that,\s+your\s+APR\s+will\s+be\s*)?(' + _NUM + _RNG + r')')


def _flat_label_rows(pg, pi):
    """Layouts where whitespace-flattened text reads label, value, product word. Conservative: one value or one range, product word named."""
    flat = ' '.join(pg.split())
    rows = []
    def mk(k, m, grp, intro=None):
        a = max(0, m.start()); sn = flat[a:m.end() + 90][:360]
        pcts = ['%.2f%%' % float(x) if False else x.replace(' ', '') for x in re.findall(_NUM, flat[m.start():m.end()])]
        var = bool(re.search(r'vary\s+with\s+the\s+market', sn, re.I)) or None
        idx = 'Prime Rate' if var and re.search(r'prime', sn, re.I) else None
        return (k, pi, sn, '[]', json.dumps(pcts), 0, None, 'agreement', 1 if intro else None, intro[0] if intro else None, intro[1] if intro else None, var and 1, idx, None, None, 'stated')
    for rx, ks in _FLAT:
        for m in rx.finditer(flat):
            for k in ks: rows.append(mk(k, m, 1))
    for m in _INTRO_LIST.finditer(flat):
        k = {'credit': 'purchase_apr', 'balance': 'balance_transfer_apr', 'cash': 'cash_advance_apr'}[m.group(1).lower().split()[0]]
        intro = (float(m.group(2).rstrip('% ')), m.group(3)) if m.group(2) else None
        if not intro and any(float(x.rstrip('% ')) < 3 for x in re.findall(_NUM, m.group(4))): continue  # monthly periodic rates, not APRs
        rows.append(mk(k, m, 4, intro))
    return rows


_BOFA_ES = re.compile(r'Tasa\s+(?:de\s+Porcentaje\s+Anual\s+\(APR\)\s+para\s+Compras|APR\s+para\s+Transferencias\s+de\s+Saldo)\b(.{0,260}?)'
                      r'Tasa\s+Preferencial\s*\+\s*(\d{1,2}\.\d{2})\s?%\s+al\s+Tasa\s+Preferencial\s*\+\s*(\d{1,2}\.\d{2})\s?%(.{0,120}?)\(APR\)\s+del\s+(\d{1,2}\.\d{2})\s?%\s+al\s+(\d{1,2}\.\d{2})\s?%', re.I)


def _bofa_spanish_rows(pg, pi):
    """Spanish card pages that print 'Tasa Preferencial + a% al Tasa Preferencial + b% ... (APR) del c% al d%': stated range plus margin range."""
    flat = ' '.join(pg.split()); rows = []
    for m in _BOFA_ES.finditer(flat):
        lab = flat[m.start():m.start() + 60].lower()
        k = 'purchase_apr' if 'compras' in lab else 'balance_transfer_apr'
        a, b, c, d = (float(m.group(i)) for i in (2, 3, 5, 6))
        if not (c > a and abs((c - a) - (d - b)) < 0.021): continue
        rows.append((k, pi, flat[m.start():m.end()][:360], '[]', json.dumps(['%.2f%%' % c, '%.2f%%' % d]), 0, None, 'agreement', None, None, None, 1, 'Prime Rate', a, b, 'stated'))
    return rows


_ES_STATED = re.compile(r'Tasa\s+(?:de\s+Porcentaje|Porcentual|Efectiva)\s+Anual\s*\(APR\)\s+para\s+(Compras|Transferencias\s+de\s+Saldo|Adelantos\s+de\s+Efectivo)\s+(\d{1,2}\.\d{2})\s?%(?:\s+(?:a|hasta)\s+(\d{1,2}\.\d{2})\s?%)?', re.I)


def _spanish_stated_rows(pg, pi):
    """Plain Spanish stated-rate lines: 'Tasa Porcentual Anual (APR) para Compras 28.99%' or '16.74% a 29.74%'.
    The figure must directly follow the label (so intro wording never matches) and not be followed by another bare percentage."""
    flat = ' '.join(pg.split()); rows = []
    for m in _ES_STATED.finditer(flat):
        tail = flat[m.end():m.end() + 25]
        if re.match(r'\s*(?:-|\u2013|y|o)?\s*\d{1,2}(?:\.\d+)?\s?%', tail): continue
        lab = m.group(1).lower()
        k = 'purchase_apr' if lab.startswith('compras') else 'balance_transfer_apr' if lab.startswith('transf') else 'cash_advance_apr'
        pcts = [float(m.group(2))] + ([float(m.group(3))] if m.group(3) else [])
        if min(pcts) < 3 or (len(pcts) == 2 and pcts[1] <= pcts[0]): continue
        rows.append((k, pi, flat[m.start():m.end() + 40][:360], '[]', json.dumps(['%.2f%%' % x for x in pcts]), 0, None, 'agreement', None, None, None, None, None, None, None, 'stated'))
    return rows


_AMEX_POT = re.compile(r'Annual\s+Percentage\s+Rate\s*\(APR\)\s+for\s+Pay(?:\s+Over\s+Time)?\s+Prime\s+Rate\s*\+\s*(\d{1,2}\.\d{2})\s?%(?:\s+to\s+Prime\s+Rate\s*\+\s*(\d{1,2}\.\d{2})\s?%)?', re.I)


def _amex_pay_over_time_rows(pg, pi):
    """American Express 'APR for Pay Over Time Prime Rate + X% to Prime Rate + Y%': stored as a purchase APR, margin only (never a computed APR)."""
    flat = ' '.join(pg.split()); rows = []
    for m in _AMEX_POT.finditer(flat):
        pcts = [float(m.group(1))] + ([float(m.group(2))] if m.group(2) else [])
        rows.append(('purchase_apr', pi, flat[m.start():m.end() + 10][:360], '[]', json.dumps(['%.2f%%' % x for x in pcts]), 0, None, 'agreement', None, None, None, 1, 'Prime Rate', min(pcts), max(pcts), 'margin'))
    return rows


_PV = r'(\d{1,2}\.\d{2})\s?%'
_FOR_PURCH = re.compile(r'Annual\s+Percentage\s+Rate\s*\(APR\)\s+' + _PV + r'(?:\s+to\s+' + _PV + r')?\s+for\s+Purchases\b', re.I)
_AMEX_PURCH = re.compile(r'Annual\s+Percentage\s+Rate\s*\(APR\)\s+for\s+Prime\s+Rate\s*\+\s*' + _PV + r'(?:\s+to\s+Prime\s+Rate\s*\+\s*' + _PV + r')?\s+Purchases\b', re.I)
_CHASE_ES = re.compile(r'Tasa\s+Efectiva\s+Anual\s*\(APR\)\s+' + _PV + r'\s+(?:hasta|a)\s+' + _PV + r'\.(?:(?!\(APR\)|APR\s+para).){0,110}?\bpara\s+Compras\b', re.I)
_BOFA_ES2 = re.compile(r'Tasa\s+de\s+Porcentaje\s+Anual\s*\(APR\)\s+para\s+Compras(?:(?!Transferencias|Adelantos).){0,90}?Tasa\s+Preferencial\s*\+\s*' + _PV + r'\s*\(APR\)\s*' + _PV, re.I)
_LIST3 = re.compile(r'Annual\s+Percentage\s+Rate\s*\(APR\)\s+for\s+' + _PV + r',\s+' + _PV + r',?\s+or\s+' + _PV + r',?\s+based\s+on\s+your\s+creditworthiness\.\s+Purchases\b', re.I)


def _layout_purchase_rows(pg, pi):
    """Purchase APR label layouts where the figure sits between the label and the word Purchases (or after the Spanish label in a different order).
    Every figure is printed verbatim in the snippet; margin-only rows keep index and margin and never an APR."""
    flat = ' '.join(pg.split()); rows = []

    def row(m, pcts, variable=None, idx=None, mg=None, basis='stated'):
        rows.append(('purchase_apr', pi, flat[m.start():m.end() + 70][:360], '[]', json.dumps(['%.2f%%' % x for x in pcts]), 0, None, 'agreement',
                     None, None, None, variable, idx, mg[0] if mg else None, mg[1] if mg else None, basis))
    for m in _FOR_PURCH.finditer(flat):
        pcts = [float(g) for g in m.groups() if g]
        if min(pcts) < 3 or (len(pcts) == 2 and pcts[1] <= pcts[0]): continue
        var = bool(re.search(r'will\s+vary\s+with\s+the\s+market', flat[m.end():m.end() + 80], re.I))
        row(m, pcts, 1 if var else None, 'Prime Rate' if var and re.search(r'Prime\s+Rate', flat[m.end():m.end() + 140], re.I) else None)
    for m in _AMEX_PURCH.finditer(flat):
        pcts = [float(g) for g in m.groups() if g]
        row(m, pcts, 1, 'Prime Rate', (min(pcts), max(pcts)), 'margin')
    for m in _CHASE_ES.finditer(flat):
        pcts = [float(m.group(1)), float(m.group(2))]
        if pcts[1] > pcts[0] >= 3: row(m, pcts, 1 if re.search(r'variar', m.group(0), re.I) else None, 'Prime Rate' if re.search(r'tasa\s+Prime', m.group(0), re.I) else None)
    for m in _BOFA_ES2.finditer(flat):
        mg, ap = float(m.group(1)), float(m.group(2))
        if ap > mg: row(m, [ap], 1, 'Prime Rate', (mg, mg))
    for m in _LIST3.finditer(flat):
        pcts = [float(g) for g in m.groups()]
        if min(pcts) >= 3: row(m, pcts, 1 if re.search(r'Prime\s+Rate', flat[m.end():m.end() + 120], re.I) else None, 'Prime Rate' if re.search(r'Prime\s+Rate', flat[m.end():m.end() + 120], re.I) else None)
    return rows


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
        # 'Annual Percentage Rate (APR) for' / 'APR for' / '<value>' / 'Purchases': the value cell sits between the label and the product word
        lab = re.search(r'(^|\s)((annual\s+)?percentage\s+rate\s*\(apr\)|apr)\s*for\s*(\d{1,2}(\.\d+)?\s?%.*)?$', l, re.I) or \
            (re.search(r'annual\s+percentage\s*$', l, re.I) and i + 1 < len(lines) and re.match(r'\s*rate\s*\(apr\)\s*for\s*$', lines[i + 1], re.I))
        if lab and len(l) < 120:
            nxt = lines[i + 1:i + 7]
            for pj, x in enumerate(nxt):
                mm = re.match(r'\s*(for\s+)?(purchases?|balance\s+transfers?|cash\s+advances?)(\s{3,}\S.*)?$', x, re.I)
                if not mm: continue
                if re.match(r'\s*(for\s+)?(purchases?|balance\s+transfers?|cash\s+advances?)\s+(not\s+(allowed|available)|n/?a\b)', x, re.I): break
                if re.search(r'\d\s?%', l) or any(re.search(r'\d{1,2}(\.\d+)?\s?%', y) for y in nxt[:pj]):
                    w = mm.group(2).lower()
                    hits.setdefault(i, set()).add('purchase_apr' if w.startswith('purch') else 'balance_transfer_apr' if w.startswith('bal') else 'cash_advance_apr')
                break
        wl = re.match(r'\s*apr\s+for\s+(balance|cash)\s+(\d{1,2}(\.\d+)?\s?%.*)$', l, re.I)  # 'APR for Balance   13.25% ...' / 'Transfers'
        if wl and i + 1 < len(lines) and re.match(r'\s*(transfers?|advances?)\b', lines[i + 1], re.I):
            hits.setdefault(i, set()).add('balance_transfer_apr' if wl.group(1).lower() == 'balance' else 'cash_advance_apr')
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
        out.extend(_spanish_margin_rows(pg, pi))
        out.extend(_margin_table_rows(lines, pi))
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
    have = {(r[0], r[1], tuple(json.loads(r[4])[:1])) for r in out if r[0] in APR_TERMS}
    for pi, pg in enumerate(pages, 1):
        for r in _flat_label_rows(pg, pi) + _bofa_spanish_rows(pg, pi) + _spanish_stated_rows(pg, pi) + _amex_pay_over_time_rows(pg, pi) + _layout_purchase_rows(pg, pi):
            key = (r[0], r[1], tuple(json.loads(r[4])[:1]))
            if key not in have: have.add(key); out.append(r)
    # when a margin table states the rates, drop other pattern hits for the same term whose figures match nothing in the table (stray sample rates, section numbers)
    tab = {}
    for r in out:
        if r[0] in APR_TERMS and r[15] == 'stated' and r[13] is not None and r[6] is None and re.match(r'\s*(purchases?|balance|cash|penalty)', r[2], re.I) and re.search(r'\b\d{1,2}\.\d{4,}\s?%', r[2]):
            tab.setdefault(r[0], set()).update(float(x[:-1]) for x in json.loads(r[4]))
            tab[r[0]].update([r[13], r[14]])
    if tab:
        out = [r for r in out if r[0] not in tab or (r[15] == 'stated' and r[13] is not None and re.search(r'\b\d{1,2}\.\d{4,}\s?%', r[2]))
               or any(float(x[:-1]) in tab[r[0]] for x in json.loads(r[4]))]
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


# --- ordered-column assignment for multi-card rate tables -------------------
_OC_PCT = re.compile(r"\d{1,2}(?:\.\d{1,3})?\s?%")
_OC_CARDKW = re.compile(r"\b(visa|mastercard|master\s?card|platinum|classic|gold|rewards|secured|signature|premier|preferred|standard|card|cash\s?back|select|student|business|advantage|world)\b", re.I)
_OC_TERMS = (("purchase_apr", re.compile(r"purchase", re.I)),
             ("balance_transfer_apr", re.compile(r"balance\s+transfer", re.I)),
             ("cash_advance_apr", re.compile(r"cash\s+advance", re.I)))


def _oc_header(line):
    """Card-name header: no digits/%/$, 2-6 segments separated by 3+ spaces, each with a card keyword."""
    s = line.strip()
    if not s or re.search(r"[\d%$]", s):
        return None
    segs = [x.strip() for x in re.split(r"\s{3,}", line.strip())]
    # the leftmost segment may be a row-label column; keep only segments with card keywords
    names = [x for x in segs if _OC_CARDKW.search(x) and 2 <= len(x) <= 40]
    if len(names) < 2 or len(names) > 6 or len({n.lower() for n in names}) != len(names):
        return None
    return names


def ordered_column_rows(text):
    """Per-card APR rows from tables whose columns are cards (header names, then one row per APR type with
    one value per card, same order). Returns [] for the whole document when any APR value row does not fit:
    wrong count, unreadable right side, no header, or an ambiguous label."""
    out = []
    for pno, page in enumerate(text.split("\f"), 1):
        lines = page.split("\n")
        header = None; hidx = -1
        for i, ln in enumerate(lines):
            h = _oc_header(ln)
            if h:
                header, hidx = h, i; continue
            ps = list(_OC_PCT.finditer(ln))
            if not ps:
                continue
            left = ln[:ps[0].start()]
            if not left.strip() or not re.search(r"\s{3,}$", left):
                continue  # prose or a value-only line, not a table row
            if len(left) > 45 or (len(ps) == 1 and header is None):
                continue
            nxt = []
            for j in range(i + 1, min(i + 3, len(lines))):
                if not lines[j].strip() or _OC_PCT.search(lines[j]):
                    break
                nxt.append(lines[j][:45])
            label = left + " " + " ".join(nxt)
            hits = [t for t, rx in _OC_TERMS if rx.search(label)]
            if not hits and i > 0 and lines[i - 1].strip() and not _OC_PCT.search(lines[i - 1]):
                label = lines[i - 1][:45] + " " + left
                hits = [t for t, rx in _OC_TERMS if rx.search(label)]
            if len(hits) != 1 or not re.search(r"apr|percentage|rate|purchase|transfer|advance", label, re.I):
                continue
            if "$" in ln or re.search(r"\bof\b", ln[ps[0].start():], re.I) and len(ps) == 1:
                continue
            if len(ps) < 2:
                continue  # single value: not a multi-card row
            right = ln[ps[0].start():]
            if re.search(r"[A-Za-z$]", _OC_PCT.sub("", right)):
                return []  # APR row with words/ranges beside the values
            if header is None or hidx < 0 or i - hidx > 14 or len(ps) != len(header):
                return []  # no header, stale header or wrong count: null the whole doc
            snip = (" ".join(lines[hidx].split()) + " | " + " ".join(ln.split()))[:400]
            for k, m in enumerate(ps):
                out.append((hits[0], pno, snip, "[]", '["%s"]' % m.group(0).replace(" ", ""), 0, header[k], "card",
                            0, None, None, None, None, None, None, "stated"))
    return out


# --- range-aware column assignment ------------------------------------------
_RG_CELL = re.compile(r"(\d{1,2}(?:\.\d{1,3})?)\s?%\s*(?:(?:to|-|\u2013|up\s+to)\s*(\d{1,2}(?:\.\d{1,3})?)\s?%)?", re.I)
_RG_INTRO = re.compile(r"introductory", re.I)
_RG_PERIOD = re.compile(r"(?:for|through)\s+(?:the\s+first\s+)?(\w+(?:\s*\(\d+\))?\s+(?:months?|days?|billing\s+cycles?|statement\s+cycles?))", re.I)


def _rg_header(line):
    names = _oc_header(line)
    if not names:
        return None
    pos = []
    for n in names:
        k = line.find(n)
        if k < 0:
            return None
        pos.append(k)
    return names, pos


def range_column_rows(text):
    """Per-card APR rows where each card's cell is one value or a 'X% to Y%' range, aligned by character
    position under the card header. Fills pct_min/pct_max in `pcts` as [min,max]; for fixed rates min=max.
    'Introductory APR' cells go to intro_rate/intro_period. Returns [] for the whole doc when an APR row with
    a term label has the wrong cell count or a cell outside its header column."""
    out = []
    for pno, page in enumerate(text.split("\f"), 1):
        lines = page.split("\n")
        hdr = None; hidx = -1
        for i, ln in enumerate(lines):
            h = _rg_header(ln)
            if h:
                hdr, hidx = h, i; continue
            if hdr is None:
                continue
            cells = list(_RG_CELL.finditer(ln))
            if not cells:
                continue
            first = cells[0].start()
            left = ln[:first]
            if not left.strip() or not re.search(r"\s{3,}$", left) or len(left) > 45:
                continue
            nxt = []
            for j in range(i + 1, min(i + 3, len(lines))):
                if not lines[j].strip() or _RG_CELL.search(lines[j][:46]):
                    break
                nxt.append(lines[j][:first])
            label = left + " " + " ".join(nxt)
            hits = [t for t, rx in _OC_TERMS if rx.search(label)]
            if len(hits) != 1 or not re.search(r"apr|percentage|rate", label, re.I):
                continue
            names, pos = hdr
            if i - hidx > 14:
                return []
            rest = _RG_CELL.sub("", ln[first:])
            intro = bool(_RG_INTRO.search(rest))
            if re.search(r"[A-Za-z$]", rest) and not intro:
                return []
            if len(cells) != len(names):
                return []
            cen = [p + len(n) / 2 for p, n in zip(pos, names)]
            bounds = [-1] + [(cen[q] + cen[q + 1]) / 2 for q in range(len(cen) - 1)] + [10 ** 6]
            for k, m in enumerate(cells):
                mid = (m.start() + m.end()) / 2
                if not (bounds[k] <= mid < bounds[k + 1]):
                    return []
            term = hits[0]
            for k, m in enumerate(cells):
                lo, hi = m.group(1), m.group(2) or m.group(1)
                a, b = float(lo), float(hi)
                if a > b:
                    return []
                snip = (" ".join(lines[hidx].split()) + " | " + " ".join(ln.split()))[:400]
                if intro:
                    per = None
                    blob = " ".join(" ".join(lines[j][max(int(bounds[k]), 0):int(min(bounds[k + 1], 10 ** 5))].split()) for j in range(i, min(i + 4, len(lines))))
                    mp = _RG_PERIOD.search(blob)
                    if mp:
                        per = mp.group(1)
                    out.append((term, pno, snip, "[]", "[]", 0, names[k], "card", 1, a if b == a else None, per, None, None, None, None, "stated"))
                else:
                    pc = ['%s%%' % lo] if lo == hi else ['%s%%' % lo, '%s%%' % hi]
                    out.append((term, pno, snip, "[]", json.dumps(pc), 0, names[k], "card", 0, None, None, None, None, None, None, "stated"))
    return out
