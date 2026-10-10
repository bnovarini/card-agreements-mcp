"""Build the serving database from the extraction database written by ingest.py.

Usage: python -m card_agreements_mcp.build /path/extract.db /path/serving.db [site_issuers.json]
"""
import csv, io, json, re, sqlite3, sys, zlib
from . import terms as T

def issuer_type(n: str) -> str:
    u = n.upper()
    if re.search(r"CREDIT UNION|\bFCU\b|\bCU\b|FEDERAL CREDIT", u): return "credit_union"
    if re.search(r"\bBANK\b|BANCORP|BANKING|NATIONAL ASSOCIATION|\bN\.?A\.?\b|TRUST|SAVINGS|FINANCIAL INSTITUTION", u): return "bank"
    return "other"

def slug(n: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", n.lower()).strip("-")

def build(src, dst, site=None):
    a = sqlite3.connect(src, timeout=60); b = sqlite3.connect(dst)
    b.executescript("""
    drop table if exists issuers; drop table if exists agreements; drop table if exists docs; drop table if exists terms; drop table if exists quarters; drop table if exists meta;
    drop table if exists fts; drop table if exists docid;
    create table issuers(issuer text primary key, slug text, issuer_type text, state text, city text, regulator text, on_cfpb_site int, first_quarter text, last_quarter text, quarters int);
    create table agreements(quarter text, issuer text, filename text, agreement_id text, sha1 text, size int, pages int, description text, effective_date text, status text);
    create table docs(sha1 text primary key, pages int, chars int, ocr int, ztext blob);
    create table terms(sha1 text, term text, page int, snippet text, amounts text, pcts text, is_none int, card_name text, scope text, has_intro int, intro_rate real, intro_period text, is_variable int, index_name text, margin_min real, margin_max real, basis text);
    create table quarters(quarter text primary key, agreements int, issuers int, unique_docs int, zip_pdfs int, no_text int, metadata_rows int);
    create table meta(k text primary key, v text);
    """)
    sl = {}
    if site:
        for s_, l in json.load(open(site)): sl[l.upper()] = s_
    # older quarters: issuer comes from cc_agreement_meta.csv, keyed by file stem
    csvm, csvn = {}, {}
    for q, path, content in a.execute("select quarter,path,content from meta_files where path not like '%.pdf' order by quarter"):
        head = content[:600].decode("utf-8-sig", "replace")
        if "CFPB Filename" not in head.split("\n")[0]: continue
        dlm = "\t" if "\t" in head.split("\n")[0] else ","
        rd = list(csv.DictReader(io.StringIO(content.decode("utf-8-sig", "replace").replace("\r\n", "\n").replace("\r", "\n"), newline=""), delimiter=dlm))
        csvn[q] = csvn.get(q, 0) + len(rd)
        for r in rd:
            k = next((str(v).strip() for v in r.values() if isinstance(v, str) and re.match(r"^creditcardagreement_\d+$", v.strip())), "")
            if k: csvm[(q, k)] = r
    rows = a.execute("select f.quarter,f.path,f.filename,f.agr_id,f.sha1,f.size,d.pages,d.chars from files f left join docs d using(sha1) where f.sha1 is not null and f.err != 'notpdf'").fetchall()
    out, info = [], {}
    for q, fpath, fn, agr, sha, size, pages, chars in rows:
        pp = fpath.split('/')
        idir = pp[-2] if len(pp) >= 2 and not re.match(r'^(CCADB_Snapshot|Q[1-4]\d{4}$)', pp[-2]) else ''
        desc = eff = st = None
        m = csvm.get((q, re.sub(r"\.pdf$", "", fn, flags=re.I)))
        if m:
            idir = (m.get("Issuer Name") or "").strip() or idir
            desc, eff, st = m.get("Agreement Description"), m.get("Effective Date"), m.get("Status")
            agr = m.get("Agreement #") or m.get("Agreement ID") or agr
            info[idir.upper()] = (m.get("Issuer State"), m.get("Issuer City"), m.get("FFIEC Regulator"))
        elif idir in ("credit-card-agreements", "Agreements", "pdf"):
            idir = "(unknown issuer)"
        out.append((q, " ".join(idir.upper().split()), fn, agr, sha, size, pages, desc, eff, st, idir))
    disp = {}
    for o in sorted(out, key=lambda r: r[0]): disp[o[1]] = o[10]
    b.executemany("insert into agreements values(?,?,?,?,?,?,?,?,?,?)", [o[:10] for o in out])
    iss = {}
    for o in out: iss.setdefault(o[1], set()).add(o[0])
    for i, qs in iss.items():
        qs = sorted(qs); st_, ci, rg = info.get(i, (None, None, None))
        b.execute("insert into issuers values(?,?,?,?,?,?,?,?,?,?)", (i, sl.get(i) or slug(i), issuer_type(i), st_, ci, rg, int(i in sl), qs[0], qs[-1], len(qs)))
    used = set(r[4] for r in rows)
    n = 0
    ocr = {r[0]: r for r in a.execute("select sha1,pages,chars,text from ocr_docs where chars>=50")} if a.execute("select 1 from sqlite_master where name='ocr_docs'").fetchone() else {}
    for sha, pages, chars, text in a.execute("select sha1,pages,chars,text from docs"):
        if sha not in used: continue
        isocr = 0
        if sha in ocr and (chars or 0) < 50:
            _, pages, chars, text = ocr[sha]; isocr = 1
        b.execute("insert into docs values(?,?,?,?,?)", (sha, pages, chars, isocr, zlib.compress((text or "").encode(), 6)))
        if chars and chars >= 50:
            for r in T.extract(text): b.execute("insert into terms values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (sha,) + r)
        n += 1
        if n % 5000 == 0: b.commit(); print(n, flush=True)
    b.execute("create index ag_i on agreements(issuer, quarter)"); b.execute("create index ag_q on agreements(quarter)"); b.execute("create index ag_s on agreements(sha1)")
    b.execute("create index t_s on terms(sha1, term)"); b.execute("create index t_t on terms(term)")
    b.execute("create virtual table fts using fts5(text, content='', detail=full, tokenize='porter unicode61')")
    for rid, (sha,) in enumerate(b.execute("select sha1 from docs").fetchall(), 1): pass
    b.execute("create table docid(rid integer primary key, sha1 text)")
    cur = b.execute("select sha1, ztext from docs").fetchall()
    for rid, (sha, z) in enumerate(cur, 1):
        b.execute("insert into docid values(?,?)", (rid, sha))
        b.execute("insert into fts(rowid,text) values(?,?)", (rid, zlib.decompress(z).decode()))
        if rid % 5000 == 0: b.commit(); print("fts", rid, flush=True)
    b.execute("create index di_s on docid(sha1)")
    for q, zp, nt in a.execute("select quarter, zip_pdfs, 0 from quarters"):
        ag, isu, ud = b.execute("select count(*), count(distinct issuer), count(distinct sha1) from agreements where quarter=?", (q,)).fetchone()
        nt = b.execute("select count(*) from agreements a join docs d using(sha1) where a.quarter=? and d.chars<50", (q,)).fetchone()[0]
        b.execute("insert into quarters values(?,?,?,?,?,?,?)", (q, ag, isu, ud, zp, nt, csvn.get(q)))
    b.commit(); b.execute("vacuum"); b.close()

if __name__ == "__main__":
    build(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
