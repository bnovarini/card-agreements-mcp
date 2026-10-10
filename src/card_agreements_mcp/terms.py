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
RX={k:re.compile(r'^[\s•\-\*\u2022\u25cf]*'+v,re.I) for k,v in T.items()}
AMT=re.compile(r'\$\s?\d[\d,]*(?:\.\d+)?'); PCT=re.compile(r'\d{1,3}(?:\.\d+)?\s?%')
def extract(text):
    out=[]
    pages=text.split('\f')
    for pi,pg in enumerate(pages,1):
        lines=pg.split('\n')
        for i,l in enumerate(lines):
            if len(l)>400: continue
            for k,rx in RX.items():
                if rx.match(l):
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
