"""Standing APR for an APR snippet whose figures mix terms (penalty APR, intro rate, margin, periodic rate, other terms).
Every percent figure is classified; any ambiguity returns None and the row keeps its null min/max. Never computes a rate."""
import re,json
TOK=re.compile(r'(?<![\d.])(\d{1,3}(?:\.\d+)?)\s?%')
LAB={'purchase_apr':r'purchases?|compras?','balance_transfer_apr':r'balance\s+transfers?|transferencias?\s+de\s+saldo','cash_advance_apr':r'cash\s+advances?|avances?\s+de\s+efectivo'}
OTHERLAB=r'convenience\s+checks?|cheques?\s+de\s+conveniencia'
ALL=re.compile('|'.join('(?P<%s>%s)'%(k,v) for k,v in LAB.items())+'|(?P<conv>%s)'%OTHERLAB,re.I)
STAND=re.compile(r'(after\s+that|thereafter|then,?|regular|standard|after\s+the\s+intro\w*\s+(?:period|rate|apr)|once\s+the\s+intro)',re.I)
INTRO=re.compile(r'introduct|intro\b|promotion|promo\b',re.I)
def classify(term,snip,intro_rate=None):
    """returns (std_values, reason) or None to abstain. Every % token must be classified."""
    PAIR=re.compile(r'(?<![\d.])(\d{1,3}(?:\.\d+)?)\s?%?\s*(?:to|-|\u2013|up\s+to|a|hasta)\s*(\d{1,3}(?:\.\d+)?)\s?%',re.I)
    units=[]; used=[]
    for m in PAIR.finditer(snip):
        if '%' not in snip[m.start():m.end()].split(m.group(2))[0] and not re.fullmatch(r'\d{1,2}\.\d{2}',m.group(1)): continue
        units.append((m.start(),m.end(),m.group(1),m.group(2))); used.append((m.start(),m.end()))
    for m in TOK.finditer(snip):
        if any(a<=m.start()<b for a,b in used): continue
        units.append((m.start(),m.end(),m.group(1),None))
    units.sort()
    if not units: return None
    if re.search(r'account\s+type|\blevel\s+(?:i{1,3}|[1-3])\b|\btier\b',snip,re.I): return None
    if re.search(r'\d\.\s+\d{1,2}\s?%',snip): return None   # broken numeral (digits split by whitespace)
    margin_seen=bool(re.search(r'margin|prime(?:\s+rate)?\s*(?:plus|\+)|\bplus\b|tasa\s+preferencial\s*\+',snip,re.I))
    std=[];
    for s,e,raw,raw2 in units:
        pre=snip[max(0,s-110):s]; post=snip[e:e+45]; near=pre[-60:]
        v=float(raw)
        if re.match(r'\s*(?:depending|based)\s+on',post,re.I) and re.search(r'\bor\s*$',near[-8:],re.I): return None   # 'X% or Y% depending on', other bound missing
        if v>60 or (s>0 and snip[s-1].isalpha()): return None
        if re.match(r'\s*(?:above|over|more\s+than|higher|greater)',post,re.I): continue   # spread over another APR
        if '.' in raw and len(raw.split('.')[1])>=3:                      # periodic rate figure
            if re.match(r'\s{0,3}\d{1,3}(?:\.\d+)?\s?%',snip[e:e+10]): return None   # garbled: periodic figure directly followed by another figure
            continue
        if re.search(r'(?:over|exceed\w*|maximum(?:\s+apr)?(?:\s+is)?|max\.?|cap(?:ped)?\s+at|limit)\W*$',near[-25:],re.I): continue   # cap, not an APR
        if re.search(r'margin|prime(?:\s+rate)?\s*(?:of|plus|\+|:)|\bplus\b|\+\s*$|\bindex\b|tasa\s+preferencial\s*\+',near[-45:],re.I) or re.match(r'\s*(?:to\s+(?:the\s+)?|over\s+|added\s+to\s+)?(?:the\s+)?(?:u\.?s\.?\s+)?(?:wall\s+street\s+journal\s+)?prime',post,re.I): continue   # margin / index figure, not an APR
        if re.match(r'\s*(?:of\s+(?:the|each|your|any|\$)|per\s+(?:transaction|advance|cash|balance)|fee|minimum)',post,re.I) or re.search(r'fee\W*$|\bfee\b[^.]{0,40}$',near,re.I) and not re.search(r'apr|annual\s+percentage',near,re.I): continue   # fee percentage
        if re.search(r'periodic|daily\s+rate|\bdpr\b|monthly\s+rate|per\s+month|per\s+day',near+' '+post[:25],re.I): continue
        if re.search(r'penalty|default\s+(?:apr|rate)',near,re.I) and not STAND.search(near[-25:]): continue
        # label group nearest before token
        labs=[(m.start(),m.end(),m.lastgroup) for m in ALL.finditer(pre)]
        grp=set()
        if labs:
            last=labs[-1]; grp.add(last[2]); cur=last[0]
            for a,b,g in reversed(labs[:-1]):
                if cur-b<=14 and re.fullmatch(r'\W*(?:and|or|,|/|&)?\W*',pre[b:cur],re.I): grp.add(g); cur=a
                else: break
        isstand=bool(STAND.search(near[-45:]))
        if re.search(r'^\s*(?:apr\s+|rate\s+)?for\s+(?:the\s+)?(?:first\s+)?[\w()]+(?:\s+[\w()]+)?\s+(?:billing\s+cycles?|months?|statement)',post[:70],re.I) and not isstand: continue   # intro period figure
        if re.match(r'\s*(?:after|following|once)\b',post,re.I) or (INTRO.search(near) and not isstand) or re.match(r'[^.]{0,22}intro',post,re.I) and not re.match(r'\s*(?:after|following)',post,re.I):
            # intro figure; must belong to own term or no clear other-term label
            if grp and term not in grp and not (grp&{'conv'}): continue
            if re.match(r'\s*(?:after|following|once)\b',post,re.I) and not INTRO.search(near):
                pass
            elif INTRO.search(near) or re.match(r'[^.]{0,22}intro',post,re.I):
                if intro_rate is not None and abs(v-intro_rate)>1e-9: return None
                continue
        if not grp: return None
        _ll=[m for m in ALL.finditer(pre)][-1]
        if re.search(r'\bapr\s+for\s+(?!a\s+period|the\s+first|\d|\w+\s+(?:\(\d+\)\s+)?(?:billing|months?|statement|cycles?))|\bplans?\b',pre[_ll.end():],re.I): return None   # another product/plan sits between label and figure
        if margin_seen and raw2 is None:
            lm=[m for m in ALL.finditer(pre)]
            if not lm or len(pre)-lm[-1].end()>8: return None
        if not re.search(r'apr|annual\s+percentage|interest\s+rate|tasa|porcentaje',pre,re.I): return None
        if 'conv' in grp and term not in grp: continue
        if term not in grp:
            if isstand: return None
            continue
        std.append(v)
        if raw2 is not None: std.append(float(raw2))
    return std
def std_apr(term,snip,pcts,intro_rate=None):
    r=classify(term,snip,intro_rate)
    if not r: return None
    d=sorted(set(r))
    if re.search(r'margin\s+added\s+to',snip,re.I):
        d=d if len(d)==2 else []
        if not d: return None
    if len(d)==1: return (d[0],d[0],'single')
    if len(d)==2:
        a,b=d
        def f(x): return re.escape(('%g'%x))
        pat=r'(\d+(?:\.\d+)?)\s?%\s*(?:to|-|\u2013|up\s+to|a|hasta)\s*(\d+(?:\.\d+)?)\s?%'
        for m in re.finditer(pat,snip,re.I):
            if sorted([float(m.group(1)),float(m.group(2))])==[a,b]: return (a,b,'range')
    return None
