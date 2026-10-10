"""Reconciliation of the built database against what the CFPB publishes. Writes the result into the serving database (meta table).

Usage: python -m card_agreements_mcp.reconcile /path/extract.db /path/serving.db /path/site_files_full.json
The site file is the per-issuer file list read from https://www.consumerfinance.gov/credit-cards/agreements/issuer/<slug>/ (40 files per page).
"""
import csv, io, json, re, sqlite3, sys, html

def unesc(s):
    s = re.sub(r"\\U([0-9A-Fa-f]{4})", lambda m: chr(int(m.group(1), 16)), s)
    return " ".join(html.unescape(s).upper().split())

def main(src, dst, site):
    a = sqlite3.connect(src, timeout=60); b = sqlite3.connect(dst)
    out = {}
    q = a.execute("select quarter, zip_pdfs, zip_other, processed, errors from quarters order by quarter").fetchall()
    out["zip_listing_vs_processed"] = {"quarters": len(q), "all_pdfs_processed": all(r[1] == r[3] for r in q),
                                       "pdfs_listed": sum(r[1] for r in q), "pdfs_processed": sum(r[3] for r in q),
                                       "extraction_errors": sum(r[4] for r in q),
                                       "note": "errors are macOS resource-fork stubs and PDFs pdftotext could not open"}
    rows = b.execute("select quarter, metadata_rows from quarters where metadata_rows is not null").fetchall()
    meta = {}
    for qq, n in rows:
        pdfs = b.execute("select count(*) from agreements where quarter=?", (qq,)).fetchone()[0]
        meta[qq] = {"metadata_rows": n, "pdfs_in_archive": pdfs, "difference": pdfs - n}
    out["metadata_csv_vs_pdfs"] = meta
    if site:
        res = json.load(open(site))
        s_iss = {unesc(l): [f for f in fl] for _, l, fl in res if fl is not None}
        z_iss = {}
        for (iss, n) in b.execute("select issuer, count(*) from agreements where quarter='2026_Q2' group by 1"): z_iss[iss] = n
        only_s = sorted(set(s_iss) - set(z_iss)); only_z = sorted(set(z_iss) - set(s_iss))
        diff = {k: [len(s_iss[k]), z_iss[k]] for k in s_iss if k in z_iss and len(s_iss[k]) != z_iss[k]}
        out["site_vs_archive_2026_Q2"] = {"issuers_on_site": len(s_iss), "issuers_in_archive": len(z_iss), "issuers_only_on_site": only_s, "issuers_only_in_archive": only_z,
                                          "files_on_site": sum(len(v) for v in s_iss.values()), "files_in_archive": sum(z_iss.values()),
                                          "issuers_with_different_file_count": len(diff), "file_count_differences": dict(list(diff.items())[:50])}
    b.execute("insert or replace into meta values('reconciliation', ?)", (json.dumps(out),))
    b.execute("insert or replace into meta values('built_from', 'CFPB bulk archives 2011_Q3 to 2026_Q2')")
    b.commit()
    print(json.dumps(out, indent=1)[:3000])

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
