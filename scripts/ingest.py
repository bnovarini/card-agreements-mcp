"""Ingest CFPB quarterly agreement archives into the extraction database.

Input: one <quarter>.zip per quarter in CARDS_ZIPS (download from the CFPB archive page), a text file
listing quarters (first column, e.g. 2026_Q2) in CARDS_QUARTER_LIST. Output: SQLite at CARDS_EXTRACT_DB with
docs (text by SHA-1), files (one row per PDF per quarter), meta_files and quarters. Scans with no text layer are
saved under CARDS_WORK/scanned for OCR. Needs poppler-utils (pdftotext).
Then: python -m card_agreements_mcp.build <extract.db> <serving.db> <site_issuers.json>
"""
import zipfile, sqlite3, hashlib, subprocess, os, sys, re, tempfile, time, threading, json
from multiprocessing import Pool
WORK=os.environ.get('CARDS_WORK', '/tmp/cc')
Z=os.environ.get('CARDS_ZIPS', WORK + '/zips'); DB=os.environ.get('CARDS_EXTRACT_DB', WORK + '/cca.db')
BASE='https://files.consumerfinance.gov/a/assets/bulk_agreements/'
def work(a):
    zp,name=a
    try:
        with zipfile.ZipFile(zp) as z:
            data=z.read(name)
    except Exception as e:
        return name,None,None,0,0,'zip:'+str(e)[:80]
    h=hashlib.sha1(data).hexdigest()
    return name,h,data,len(data),0,''
KNOWN=set()
def setknown(k):
    global KNOWN; KNOWN=k
def extract(a):
    zp,name=a
    name,h,data,size,_,err=work(a)
    if err: return name,None,'',0,0,err
    if h in KNOWN: return name,h,None,size,0,''
    txt='';pages=0;err=''
    if data[:4]!=b'%PDF': err='notpdf'
    else:
        with tempfile.NamedTemporaryFile(suffix='.pdf',dir=WORK) as f:
            f.write(data); f.flush()
            try:
                r=subprocess.run(['pdftotext','-layout','-enc','UTF-8',f.name,'-'],capture_output=True,timeout=90)
                txt=r.stdout.decode('utf-8','replace')
                if r.returncode!=0 and not txt: err='pdftotext rc%d'%r.returncode
                pages=txt.count('\f')
            except subprocess.TimeoutExpired: err='timeout'
    if h and data[:4]==b'%PDF' and len(txt.strip())<50:
        os.makedirs(WORK + '/scanned',exist_ok=True)
        p=WORK + '/scanned/'+h+'.pdf'
        if not os.path.exists(p): open(p,'wb').write(data)
    return name,h,txt,size,pages,err
def init():
    c=sqlite3.connect(DB)
    c.executescript('''
    create table if not exists docs(sha1 text primary key,size int,pages int,chars int,text text,err text);
    create table if not exists files(quarter text,path text,issuer_dir text,filename text,agr_id text,sha1 text,size int,err text);
    create table if not exists meta_files(quarter text,path text,content blob);
    create table if not exists quarters(quarter text primary key,zip_bytes int,zip_entries int,zip_dirs int,zip_pdfs int,zip_other int,processed int,errors int,done_at text);
    ''');c.commit();return c
def do_quarter(q,c):
    zp=f'{Z}/{q}.zip'
    if c.execute('select 1 from quarters where quarter=?',(q,)).fetchone(): return
    z=zipfile.ZipFile(zp); infos=z.infolist(); z.close()
    ents=[i for i in infos if not i.filename.endswith('/')]
    mac=[i for i in ents if i.filename.startswith('__MACOSX/') or '/._' in i.filename or i.filename.split('/')[-1].startswith('._')]
    macn=set(i.filename for i in mac)
    pdfs=[i.filename for i in ents if i.filename.lower().endswith('.pdf') and i.filename not in macn]
    other=len(ents)-len(pdfs)
    c.execute('delete from meta_files where quarter=?',(q,))
    zz=zipfile.ZipFile(zp)
    for i in ents:
        if i.filename in macn or i.filename.lower().endswith(('.pdf','.jpg','.png','.gif','.jpeg')) or i.file_size>30_000_000: continue
        c.execute('insert into meta_files values(?,?,?)',(q,i.filename,zz.read(i.filename)))
    zz.close()
    dirs=len(infos)-len(ents)
    c.execute('delete from files where quarter=?',(q,))
    seen=set(r[0] for r in c.execute('select sha1 from docs'))
    n=0;errs=0
    with Pool(2,initializer=setknown,initargs=(set(seen),)) as p:
        for name,h,txt,size,pages,err in p.imap(extract,[(zp,x) for x in pdfs],chunksize=4):
            parts=name.split('/')
            issuer=parts[1] if len(parts)>=3 else ''
            fn=parts[-1]
            m=re.search(r'-(\d{4,7})(?:_\d+_[0-9A-Za-z]+)?\.pdf$',fn,re.I)
            agr=m.group(1) if m else ''
            if h and txt is not None and h not in seen:
                c.execute('insert or ignore into docs values(?,?,?,?,?,?)',(h,size,pages,len(txt),txt,err));seen.add(h)
            c.execute('insert into files values(?,?,?,?,?,?,?,?)',(q,name,issuer,fn,agr,h,size,err))
            n+=1
            if err: errs+=1
            if n%1000==0: c.commit();print(q,n,len(pdfs),flush=True)
    c.execute('insert into quarters values(?,?,?,?,?,?,?,?,datetime("now"))',(q,os.path.getsize(zp),len(infos),dirs,len(pdfs),other,n,errs))
    c.commit(); print('DONE',q,n,errs,flush=True)
def dl(q):
    zp=f'{Z}/{q}.zip'
    while not os.path.exists(zp): time.sleep(5)
if __name__=='__main__':
    qs=[l.split()[0] for l in open(os.environ.get('CARDS_QUARTER_LIST', WORK + '/sizes.txt'))]
    qs=sorted(qs,key=lambda x:(x!='2026_Q2',x))
    c=init()
    todo=[q for q in qs if not c.execute('select 1 from quarters where quarter=?',(q,)).fetchone()]
    th=None
    for i,q in enumerate(todo):
        if th: th.join()
        dl(q)
        nxt=todo[i+1] if i+1<len(todo) else None
        do_quarter(q,c)
        os.remove(f'{Z}/{q}.zip')
    print('ALLDONE')
