"""Sibling-file association for APR terms (rate_basis=associated).

Within one CFPB submission (same agreement id in the same quarter) a file with no APR row of its own gets the
rate of its siblings, but only when every rate-bearing sibling gives the identical figure set. Rows are tagged
basis=associated, scope=submission and the snippet names the source file. Run against the extraction DB and the
APR rows DB; set QUARTER, EXTRACT_DB and ROWS_DB below.
"""
import sqlite3,collections,json
c=sqlite3.connect('file:/tmp/cc/cca.db?mode=ro',uri=True,timeout=60); o=sqlite3.connect('/tmp/cc/apr_rows.db',timeout=100); o.execute("delete from t where basis='associated'")
Q='2026_Q2'  # quarter to associate; TT=('purchase_apr','balance_transfer_apr','cash_advance_apr')
rows=[(r[0],r[1],r[2]) for r in c.execute("select distinct f.sha1,f.agr_id,f.filename from files f join docs d using(sha1) where f.quarter=? and d.chars>200 and f.agr_id is not null and f.agr_id!=''",(Q,))]
fn={s:f for s,_,f in rows}
byi=collections.defaultdict(set)
for s,i,_ in rows: byi[i].add(s)
add=collections.Counter(); iss=collections.defaultdict(set)
for term in TT:
    data=collections.defaultdict(list)
    for r in o.execute("select sha1,page,snippet,amounts,pcts,is_none,card_name,scope,has_intro,intro_rate,intro_period,is_variable,index_name,margin_min,margin_max,basis from t where term=? and basis!='associated'",(term,)): data[r[0]].append(r)
    for i,shas in byi.items():
        have=[s for s in shas if s in data]; miss=[s for s in shas if s not in data]
        if not have or not miss: continue
        sets={r[4] for s in have for r in data[s]}
        if len(sets)!=1: continue
        src=data[have[0]][0]
        for m in miss:
            snip=('[associated from sibling file in the same submission: %s] ' % fn[have[0]])+src[2]
            o.execute('insert into t values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(m,term,src[1],snip[:480],src[3],src[4],src[5],None,'issuer',src[8],src[9],src[10],src[11],src[12],src[13],src[14],'associated'))
            add[term]+=1; iss[term].add(i)
o.commit(); print(dict(add),{k:len(v) for k,v in iss.items()})
