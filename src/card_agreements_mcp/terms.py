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
SPLIT_B_NEXT = re.compile(r'^\s*for\s+purchases?\b', re.I)
# sentence and table forms of the purchase APR (found by mining agreements without a hit)
PURCH_EXTRA = [re.compile(x, re.I) for x in (
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
    if SPLIT_B.match(l) and i + 1 < len(lines) and SPLIT_B_NEXT.match(lines[i+1]):
        return True
    return False
RX={k:re.compile(r'^[\s•\-\*\u2022\u25cf]*'+v,re.I) for k,v in T.items()}
AMT=re.compile(r'\$\s?\d[\d,]*(?:\.\d+)?'); PCT=re.compile(r'\d{1,3}(?:\.\d+)?\s?%')
def extract(text):
    out=[]
    pages=text.split('\f')
    for pi,pg in enumerate(pages,1):
        lines=pg.split('\n')
        for i,l in enumerate(lines):
            if len(l)>400: continue
            for k,rx in list(RX.items())+([('purchase_apr',None)] if _split_label(lines,i) else []):
                if (rx is None) or rx.match(l):
                    if k=='purchase_apr':
                        snip=' '.join(' '.join(lines[max(i-1,0):i+14]).split())[:700]
                    else:
                        snip=' '.join(' '.join(lines[i:i+4]).split())[:360]
                    if not (AMT.search(snip) or PCT.search(snip) or re.search(r'\bnone\b|\bno\b|\bnot\b|waive|days',snip,re.I)): continue
                    out.append((k,pi,snip,json.dumps(AMT.findall(snip)[:6]),json.dumps(PCT.findall(snip)[:6]),int(bool(re.search(r'\bnone\b|\bno\s+(annual|fee|foreign)',snip[:120],re.I)))))
    # keep up to 3 per term per doc
    cnt={};res=[]
    for r in out:
        cnt[r[0]]=cnt.get(r[0],0)+1
        if cnt[r[0]]<=3: res.append(r)
    return res
