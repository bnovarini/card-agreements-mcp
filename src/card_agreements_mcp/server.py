"""MCP server over the CFPB credit card agreements database (all quarterly archives).

Data: PDF agreements credit card issuers submit to the CFPB each quarter (Regulation Z 1026.58), 2011 Q3 to the latest quarter.
The server reads a SQLite file built by build.py: issuer and agreement metadata, the full text of every agreement, and key terms
(fees, APRs, grace period) pulled from the text with the exact snippet and page they came from.
"""
from __future__ import annotations

import functools
import json
import os
import re
import sqlite3
import sys
import threading
import time
import zlib
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

MAX_ROWS = 100
TERMS = {
    "annual_fee": "Annual fee",
    "purchase_apr": "APR for purchases",
    "cash_advance_apr": "APR for cash advances",
    "balance_transfer_apr": "APR for balance transfers",
    "penalty_apr": "Penalty APR",
    "paying_interest": "Paying interest / grace period",
    "minimum_interest_charge": "Minimum interest charge",
    "foreign_transaction_fee": "Foreign transaction fee",
    "late_payment_fee": "Late payment fee",
    "returned_payment_fee": "Returned payment fee",
    "balance_transfer_fee": "Balance transfer fee",
    "cash_advance_fee": "Cash advance fee",
    "over_limit_fee": "Over-the-limit fee",
}
NOTE = (
    "Data: credit card agreements that card issuers submit to the CFPB every quarter (Regulation Z, 12 CFR 1026.58): the agreements an issuer offered to the public "
    "or had open accounts under, as submitted. Issuers with fewer than 10,000 open card accounts are not required to submit, so small issuers are missing. "
    "These are historical agreements, not live offers. Term values (fees, APRs, grace period) are pulled from the agreement text by pattern matching: every value comes with the "
    "exact snippet and page so it can be checked, but one agreement often covers several cards, so a snippet can hold several products' figures. "
    "The purchase, balance transfer and cash advance APR terms also carry the card product when the table names one (card_name, scope), intro offer (has_intro_rate, intro_rate_pct, intro_period), variable or fixed (is_variable, index_name), and the margin over the index (margin_pct_min/max); apr_pct_min/apr_pct_max give the stated APR as a range when the agreement prints one (X% to Y%, usually creditworthiness-dependent) or the single fixed rate (min = max), including when the snippet also carries a penalty APR, an introductory rate, a margin, a periodic rate or another term's figures and the standing figure for this term is unambiguous, and are null when the cell lists several separate values (see percents), except an introductory figure followed by a standing range (for example 0% intro, then 13.24% to 26.24%), where the standing range is returned; rate_basis says whether the agreement states an APR (stated), only index plus margin (margin), a blank form (unknown), or, for associated, a rate copied from another file of the same CFPB submission (same agreement id and quarter, for example a pricing addendum next to the agreement) when every rate-bearing file in that submission gives the same figures; the snippet names the source file. Margin-only rates are never turned into a computed APR. Spanish-language agreements are read too: figures printed as margin over the Prime Rate are stored as margin, and printed APR ranges as stated. "
    "Use get_agreement_text to read the source page. Scanned PDFs without a text layer were run through OCR (Tesseract); text and terms from them are marked from_ocr / text_from_ocr and can contain recognition errors. Scans that OCR could not read are flagged has_text=false."
)

_local = threading.local()


def db_path() -> str:
    return os.environ.get("CARDS_DB", str(Path.home() / ".cache" / "card-agreements-mcp" / "serving.db"))


def con() -> sqlite3.Connection:
    c = getattr(_local, "c", None)
    if c is None:
        c = sqlite3.connect(f"file:{db_path()}?mode=ro", uri=True, check_same_thread=False)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA query_only=1")
        _local.c = c
    return c


def run(sql: str, p=()) -> list[dict]:
    return [dict(r) for r in con().execute(sql, p).fetchall()]


@functools.lru_cache(maxsize=1)
def quarters() -> list[str]:
    return [r["quarter"] for r in run("SELECT quarter FROM quarters ORDER BY quarter")]


def latest() -> str:
    return quarters()[-1]


def _q(q: Optional[str]) -> str:
    if not q:
        return latest()
    q = q.strip().upper().replace("-", "_").replace(" ", "_")
    m = re.match(r"^(\d{4})_?Q([1-4])$", q) or re.match(r"^Q([1-4])_?(\d{4})$", q)
    if m:
        g = m.groups()
        q = f"{g[0]}_Q{g[1]}" if len(g[0]) == 4 else f"{g[1]}_Q{g[0]}"
    if q not in quarters():
        raise ValueError(f"quarter must be one of: {', '.join(quarters())} (format 2026_Q2)")
    return q


def _page(limit: int, offset: int) -> tuple[int, int]:
    return max(1, min(int(limit), MAX_ROWS)), max(0, int(offset))


def _like(s: str) -> str:
    return "%" + s.strip().upper().replace("%", "").replace("_", " ") + "%"


def _wrap(rows: list, limit: int, offset: int, key: str) -> dict:
    more = len(rows) > limit
    rows = rows[:limit]
    return {key: rows, "pagination": {"has_more": more, "next_offset": offset + limit if more else None, "returned": len(rows)}}


def _meta() -> dict:
    return {r["k"]: r["v"] for r in run("SELECT k, v FROM meta")}


@functools.lru_cache(maxsize=1)
def _issuer_names() -> set:
    return {r["issuer"] for r in run("SELECT issuer FROM issuers")}


def _fuzzy_names(name: str) -> list[str]:
    """Typo-tolerant fallback: every query word must match some word of the issuer name
    (substring, or similarity of at least 0.8 with difflib), e.g. 'harvard fedetal' -> HARVARD FEDERAL CREDIT UNION."""
    import difflib, re as _re
    qw = [w for w in _re.split(r"[^A-Z0-9]+", name.upper()) if len(w) > 1]
    if not qw:
        return []
    out = []
    for n in _issuer_names():
        nw = [w for w in _re.split(r"[^A-Z0-9]+", n.upper()) if w]
        if all(any(q in w or difflib.SequenceMatcher(None, q, w).ratio() >= 0.8 for w in nw) for q in qw):
            out.append(n)
    return sorted(out)


def _resolve_issuer(name: str) -> list[str]:
    names = _issuer_names()
    if name in names:
        return [name]
    u = name.strip().upper()
    exact = [n for n in names if n.upper() == u]
    if exact:
        return exact
    sub = sorted(n for n in names if u in n.upper())
    return sub or _fuzzy_names(name)


def _issuer_or_error(name: str) -> str:
    m = _resolve_issuer(name)
    if not m:
        raise ValueError(f"No issuer matching '{name}'. Use search_issuers to find the exact name.")
    if len(m) > 1:
        raise ValueError(f"'{name}' matches {len(m)} issuers: {', '.join(m[:15])}. Pass the exact name.")
    return m[0]


mcp = FastMCP("card-agreements", instructions=NOTE)


@mcp.tool(description="What is loaded: source, quarters covered, agreements and issuers per quarter, how the numbers reconcile to the CFPB, term names, and caveats. Call first if unsure what the tools cover.")
def dataset_info() -> dict:
    qs = run("SELECT quarter, agreements, issuers, unique_docs, no_text FROM quarters ORDER BY quarter")
    return {"note": NOTE, "latest_quarter": latest(), "quarters": qs, "terms": TERMS, "meta": _meta(),
            "source": "CFPB credit card agreement database, https://www.consumerfinance.gov/credit-cards/agreements/archive/"}


@mcp.tool(description="Find card issuers by name (substring), type (credit_union, bank, other) or state (older quarters only carry the state). Returns each issuer's number of agreements in the quarter "
                      "(default: latest) and the first and last quarter it appears. issuer_type is guessed from the name.")
def search_issuers(name_contains: Optional[str] = None, issuer_type: Optional[str] = None, state: Optional[str] = None, quarter: Optional[str] = None,
                   limit: int = 25, offset: int = 0) -> dict:
    q = _q(quarter)
    limit, offset = _page(limit, offset)
    w, p = ["a.quarter = ?"], [q]
    fuzzy = None
    if name_contains:
        if any(name_contains.strip().upper().replace("%", "").replace("_", " ") in n.upper() for n in _issuer_names()):
            w.append("UPPER(i.issuer) LIKE ?"); p.append(_like(name_contains))
        else:
            fuzzy = _fuzzy_names(name_contains)
            w.append("i.issuer IN (%s)" % ",".join("?" * len(fuzzy)) if fuzzy else "0"); p.extend(fuzzy)
    if issuer_type:
        if issuer_type not in ("credit_union", "bank", "other"):
            raise ValueError("issuer_type must be credit_union, bank or other")
        w.append("i.issuer_type = ?"); p.append(issuer_type)
    if state:
        w.append("UPPER(i.state) = ?"); p.append(state.strip().upper())
    rows = run(f"""SELECT i.issuer, i.issuer_type, i.state, i.city, i.slug AS cfpb_slug, count(*) AS agreements_in_quarter, i.first_quarter, i.last_quarter, i.quarters AS quarters_present
        FROM issuers i JOIN agreements a ON a.issuer = i.issuer WHERE {' AND '.join(w)} GROUP BY i.issuer ORDER BY i.issuer LIMIT {limit + 1} OFFSET {offset}""", p)
    res = {"quarter": q, **_wrap(rows, limit, offset, "issuers")}
    if fuzzy:
        res["note"] = f"No issuer name contains '{name_contains}'; showing typo-tolerant (fuzzy) matches."
    return res


@mcp.tool(description="List the agreement files an issuer submitted in a quarter (default: latest): file name, agreement id, pages, description (older quarters), whether the PDF has a text layer, and a doc_id for get_agreement_text.")
def list_agreements(issuer: str, quarter: Optional[str] = None, limit: int = 50, offset: int = 0) -> dict:
    name = _issuer_or_error(issuer)
    q = _q(quarter)
    limit, offset = _page(limit, offset)
    rows = run(f"""SELECT a.filename, a.agreement_id, a.description, a.effective_date, a.status, d.pages, (d.chars >= 50) AS has_text, d.ocr AS text_from_ocr, a.sha1 AS doc_id
        FROM agreements a JOIN docs d USING(sha1) WHERE a.issuer = ? AND a.quarter = ? ORDER BY a.filename LIMIT {limit + 1} OFFSET {offset}""", (name, q))
    for r in rows:
        r["has_text"] = bool(r["has_text"]); r["text_from_ocr"] = bool(r["text_from_ocr"])
    return {"issuer": name, "quarter": q, **_wrap(rows, limit, offset, "agreements")}


def _apr_range(r: dict):
    """(min, max) of the stated APR when it is unambiguous: one value (fixed, min = max) or exactly two values
    joined by 'to' / '-' in the snippet (a range). Anything else is (None, None); percents keeps the full list."""
    if r.get("std_min") is not None:
        return r["std_min"], r["std_max"]
    try:
        raw = json.loads(r["pcts"]) if "pcts" in r else list(r.get("percents") or [])
        v = [float(x.rstrip("%").strip()) for x in raw]
    except Exception:
        return None, None
    if r.get("basis") not in ("stated", "associated") or r.get("is_none") or r.get("says_none"):
        return None, None
    ir = r.get("intro_rate")
    if len(v) == 1 and r.get("has_intro") and ir is not None and v[0] == ir:
        return None, None   # the only figure is the introductory rate, so no standing APR is stated here
    if len(v) == 1:
        return v[0], v[0]
    if len(v) == 3 and r.get("has_intro") and ir is not None and v[0] == ir and v[1] <= v[2]:
        # introductory figure first, then the standing range: the range is the stated APR
        a2, b2 = (re.escape(x.strip()) for x in raw[1:])
        if re.search(a2 + r"\s*(?:to|-|\u2013|up\s+to|a|hasta|and|y)\s*" + b2, r.get("snippet") or "", re.I):
            return v[1], v[2]
    if len(v) == 2 and v[0] <= v[1]:
        a2, b2 = (re.escape(x.strip()) for x in raw)
        if re.search(a2 + r"\s*(?:to|-|\u2013|up\s+to|a|hasta)\s*" + b2, r.get("snippet") or "", re.I):
            return v[0], v[1]
    return None, None


def _apr_fields(r: dict) -> dict:
    """Extra fields on APR terms: card product, intro offer, variable/fixed, index and margin. Stated values, never computed."""
    if r.get("term") not in ("purchase_apr", "balance_transfer_apr", "cash_advance_apr"):
        return {}
    lo, hi = _apr_range(r)
    return {"apr_pct_min": lo, "apr_pct_max": hi, "card_name": r["card_name"], "scope": r["scope"] or "agreement",
            "has_intro_rate": None if r["has_intro"] is None else bool(r["has_intro"]), "intro_rate_pct": r["intro_rate"], "intro_period": r["intro_period"],
            "is_variable": None if r["is_variable"] is None else bool(r["is_variable"]), "index_name": r["index_name"],
            "margin_pct_min": r["margin_min"], "margin_pct_max": r["margin_max"],
            "rate_basis": r["basis"]}


def _term_rows(sha1s: list[str], terms: Optional[list[str]]) -> dict:
    if not sha1s:
        return {}
    qm = ",".join("?" * len(sha1s))
    w, p = f"sha1 IN ({qm})", list(sha1s)
    if terms:
        w += f" AND term IN ({','.join('?' * len(terms))})"; p += terms
    out: dict = {}
    for r in run(f"SELECT t.sha1, t.term, t.page, t.snippet, t.amounts, t.pcts, t.is_none, d.ocr, t.card_name, t.scope, t.has_intro, t.intro_rate, t.intro_period, t.is_variable, t.index_name, t.margin_min, t.margin_max, t.basis, t.std_min, t.std_max FROM terms t JOIN docs d ON d.sha1=t.sha1 WHERE {w.replace('sha1 IN', 't.sha1 IN').replace('AND term IN', 'AND t.term IN')} ORDER BY t.sha1, t.term, t.page", p):
        out.setdefault(r["sha1"], []).append({"term": r["term"], "page": r["page"], "snippet": r["snippet"], "amounts": json.loads(r["amounts"]),
                                              "percents": json.loads(r["pcts"]), "says_none": bool(r["is_none"]), "from_ocr": bool(r["ocr"]), **_apr_fields(r)})
    return out


def _check_terms(terms):
    if terms:
        bad = [t for t in terms if t not in TERMS]
        if bad:
            raise ValueError(f"Unknown term(s) {bad}. Valid: {', '.join(TERMS)}")


@mcp.tool(description="Key terms from an issuer's agreements in a quarter (default: latest): annual fee, purchase/cash/balance-transfer/penalty APR, grace period, foreign transaction, late payment, returned payment, balance transfer, cash advance and over-limit fees. "
                      "Each term comes with the verbatim snippet and page from the PDF plus the dollar amounts and percentages found in it. Pass terms=[...] to limit (names are in dataset_info). Pattern-matched: check the snippet.")
def get_terms(issuer: str, quarter: Optional[str] = None, terms: Optional[list[str]] = None, limit: int = 20, offset: int = 0) -> dict:
    _check_terms(terms)
    name = _issuer_or_error(issuer)
    q = _q(quarter)
    limit, offset = _page(limit, offset)
    ags = run(f"""SELECT a.filename, a.sha1, a.pages FROM agreements a JOIN docs d USING(sha1) WHERE a.issuer=? AND a.quarter=? AND d.chars>=50
                  AND EXISTS (SELECT 1 FROM terms t WHERE t.sha1=a.sha1) ORDER BY a.filename LIMIT {limit + 1} OFFSET {offset}""", (name, q))
    page = ags[:limit]
    tr = _term_rows([a["sha1"] for a in page], terms)
    rows = [{"filename": a["filename"], "doc_id": a["sha1"], "pages": a["pages"], "terms": tr.get(a["sha1"], [])} for a in page]
    return {"issuer": name, "quarter": q, "extraction": "pattern-matched snippets, not a validated field set", **_wrap(rows + ags[limit:], limit, offset, "agreements")}


def _num(s: str) -> float:
    return float(s.replace("$", "").replace(",", "").strip())


@mcp.tool(description="Compare one term across issuers in a quarter (default: latest). term is one of the names in dataset_info (e.g. annual_fee, late_payment_fee, foreign_transaction_fee, grace period = paying_interest). "
                      "Filters: issuer_type (credit_union, bank, other), name_contains, min_amount/max_amount (dollar amount found in the snippet, e.g. annual_fee min_amount=95), says_none=True to keep only snippets that say None/No. "
                      "One row per issuer and agreement with the snippet and page. Pattern-matched: a snippet can list several cards' values.")
def compare_terms(term: str, quarter: Optional[str] = None, issuer_type: Optional[str] = None, name_contains: Optional[str] = None,
                  min_amount: Optional[float] = None, max_amount: Optional[float] = None, says_none: Optional[bool] = None,
                  has_intro_rate: Optional[bool] = None, is_variable: Optional[bool] = None, index_name_contains: Optional[str] = None, rate_basis: Optional[str] = None,
                  card_name_contains: Optional[str] = None, limit: int = 25, offset: int = 0) -> dict:
    _check_terms([term])
    q = _q(quarter)
    limit, offset = _page(limit, offset)
    w, p = ["a.quarter = ?", "t.term = ?"], [q, term]
    if issuer_type:
        w.append("i.issuer_type = ?"); p.append(issuer_type)
    if name_contains:
        w.append("UPPER(a.issuer) LIKE ?"); p.append(_like(name_contains))
    if says_none is not None:
        w.append("t.is_none = ?"); p.append(int(says_none))
    if (has_intro_rate is not None or is_variable is not None or index_name_contains or rate_basis or card_name_contains) and term not in ("purchase_apr", "balance_transfer_apr", "cash_advance_apr"):
        raise ValueError("has_intro_rate, is_variable, index_name_contains, rate_basis and card_name_contains only apply to purchase_apr, balance_transfer_apr and cash_advance_apr")
    if has_intro_rate is not None:
        w.append("t.has_intro = ?"); p.append(int(has_intro_rate))
    if is_variable is not None:
        w.append("t.is_variable = ?"); p.append(int(is_variable))
    if index_name_contains:
        w.append("UPPER(t.index_name) LIKE ?"); p.append(_like(index_name_contains))
    if rate_basis:
        if rate_basis not in ("stated", "margin", "unknown", "associated"):
            raise ValueError("rate_basis must be stated, margin, unknown or associated")
        w.append("t.basis = ?"); p.append(rate_basis)
    if card_name_contains:
        w.append("UPPER(t.card_name) LIKE ?"); p.append(_like(card_name_contains))
    rows = run(f"""SELECT a.issuer, i.issuer_type, a.filename, a.sha1 AS doc_id, t.term, t.page, t.snippet, t.amounts, t.pcts, t.is_none, d.ocr AS from_ocr,
        t.card_name, t.scope, t.has_intro, t.intro_rate, t.intro_period, t.is_variable, t.index_name, t.margin_min, t.margin_max, t.basis, t.std_min, t.std_max
        FROM agreements a JOIN issuers i ON i.issuer = a.issuer JOIN terms t ON t.sha1 = a.sha1 JOIN docs d ON d.sha1 = a.sha1 WHERE {' AND '.join(w)} ORDER BY a.issuer, a.filename, t.page""", p)
    seen, out = set(), []
    for r in rows:
        r["amounts"] = [_num(x) for x in json.loads(r["amounts"])]
        r["percents"] = json.loads(r.pop("pcts"))
        r["says_none"] = bool(r.pop("is_none")); r["from_ocr"] = bool(r["from_ocr"])
        extra = _apr_fields(r)
        for c in ("card_name", "scope", "has_intro", "intro_rate", "intro_period", "is_variable", "index_name", "margin_min", "margin_max", "basis", "term", "std_min", "std_max"):
            r.pop(c, None)
        r.update(extra)
        if min_amount is not None and not any(a >= min_amount for a in r["amounts"]):
            continue
        if max_amount is not None and not any(a <= max_amount for a in r["amounts"]):
            continue
        k = (r["issuer"], r["doc_id"], r["page"], r.get("card_name"), r.get("snippet", "")[:60])
        if k in seen:
            continue
        seen.add(k); out.append(r)
    total = len(out)
    res = _wrap(out[offset:offset + limit + 1], limit, 0, "rows")
    res["pagination"]["next_offset"] = offset + limit if res["pagination"]["has_more"] else None
    return {"quarter": q, "term": term, "matches": total, **res}


@mcp.tool(description="How an issuer's value for one term changed across quarters: one row per quarter with the distinct snippets found in that quarter's agreements. Use to see when a fee or APR language changed.")
def term_history(issuer: str, term: str, limit: int = 40) -> dict:
    _check_terms([term])
    name = _issuer_or_error(issuer)
    rows = run("""SELECT a.quarter, a.filename, t.page, t.snippet, t.amounts, t.pcts FROM agreements a JOIN terms t ON t.sha1=a.sha1 WHERE a.issuer=? AND t.term=? ORDER BY a.quarter, a.filename, t.page""", (name, term))
    by: dict = {}
    for r in rows:
        d = by.setdefault(r["quarter"], {})
        d.setdefault(r["snippet"], {"quarter": r["quarter"], "snippet": r["snippet"], "filename": r["filename"], "page": r["page"], "amounts": json.loads(r["amounts"]), "percents": json.loads(r["pcts"])})
    out = [{"quarter": q, "distinct_snippets": list(d.values())[:5], "snippets_in_quarter": len(d)} for q, d in sorted(by.items())]
    return {"issuer": name, "term": term, "quarters_with_term": len(out), "history": out[:min(limit, MAX_ROWS)]}


def _snip(text: str, words: list[str], width: int = 260) -> tuple[str, int]:
    low = text.lower()
    pos = [low.find(w) for w in words if low.find(w) >= 0]
    i = min(pos) if pos else 0
    page = text.count("\f", 0, i) + 1
    s = " ".join(text[max(0, i - width // 3): i + width].split())
    return s, page


@mcp.tool(description="Full-text search across agreement text (SQLite FTS5: words, \"exact phrases\", OR, NEAR, prefix*). Optional issuer_contains and quarter (default: latest; pass quarter='all' for every quarter). "
                      "Returns the issuer, file, page and a snippet around the first hit. Examples: '\"foreign transaction\" waived', 'arbitration NEAR opt', '\"skip a payment\"'.")
def search_text(query: str, issuer_contains: Optional[str] = None, quarter: Optional[str] = None, limit: int = 10, offset: int = 0) -> dict:
    limit, offset = _page(limit, offset)
    q = None if (quarter or "").lower() == "all" else _q(quarter)
    try:
        hits = run("SELECT rowid FROM fts WHERE fts MATCH ? ORDER BY rowid LIMIT 5000", (query,))
    except sqlite3.OperationalError as e:
        raise ValueError(f"Bad search syntax: {e}")
    if not hits:
        return {"quarter": q or "all", "results": [], "pagination": {"has_more": False, "next_offset": None, "returned": 0}}
    ids = [h["rowid"] for h in hits]
    w, p = [], []
    if q:
        w.append("a.quarter = ?"); p.append(q)
    if issuer_contains:
        w.append("UPPER(a.issuer) LIKE ?"); p.append(_like(issuer_contains))
    out, skipped = [], 0
    words = [x.lower() for x in re.findall(r"[A-Za-z0-9']{3,}", query) if x.upper() not in ("AND", "OR", "NOT", "NEAR")]
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        rows = run(f"""SELECT a.issuer, a.quarter, a.filename, a.sha1 AS doc_id FROM docid di JOIN agreements a ON a.sha1 = di.sha1
                       WHERE di.rid IN ({','.join('?' * len(chunk))}) {'AND ' + ' AND '.join(w) if w else ''} ORDER BY a.issuer, a.quarter, a.filename""", chunk + p)
        out.extend(rows)
        if len(out) > offset + limit + 5:
            break
    seen, uniq = set(), []
    for r in out:
        k = (r["issuer"], r["quarter"], r["doc_id"])
        if k not in seen:
            seen.add(k); uniq.append(r)
    page = uniq[offset:offset + limit]
    for r in page:
        z = con().execute("SELECT ztext FROM docs WHERE sha1=?", (r["doc_id"],)).fetchone()[0]
        r["snippet"], r["page"] = _snip(zlib.decompress(z).decode(), words)
    return {"quarter": q or "all", "results": page, "pagination": {"has_more": len(uniq) > offset + limit, "next_offset": offset + limit if len(uniq) > offset + limit else None, "returned": len(page)}}


@mcp.tool(description="Read the text of one agreement (doc_id from list_agreements, get_terms or search_text), optionally one page. Text comes from the PDF text layer, with table columns kept in layout order. max_chars caps the reply (default 12000).")
def get_agreement_text(doc_id: str, page: Optional[int] = None, max_chars: int = 12000) -> dict:
    r = con().execute("SELECT pages, chars, ztext FROM docs WHERE sha1=?", (doc_id,)).fetchone()
    if not r:
        raise ValueError("Unknown doc_id. Get one from list_agreements, get_terms or search_text.")
    text = zlib.decompress(r["ztext"]).decode()
    pgs = text.split("\f")
    if page is not None:
        if not 1 <= page <= len(pgs):
            raise ValueError(f"page must be between 1 and {len(pgs)}")
        text = pgs[page - 1]
    max_chars = max(500, min(int(max_chars), 40000))
    used = run("SELECT quarter, issuer, filename FROM agreements WHERE sha1=? ORDER BY quarter DESC LIMIT 5", (doc_id,))
    return {"doc_id": doc_id, "pages": r["pages"], "page": page, "truncated": len(text) > max_chars, "text": text[:max_chars],
            "appears_in": used, "has_text": r["chars"] >= 50}


class RateLimit:
    def __init__(self, app, per_minute: int):
        self.app, self.per_minute, self.hits = app, per_minute, {}

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"] != "/healthz":
            h = dict(scope["headers"])
            ip = (h.get(b"fly-client-ip") or h.get(b"x-forwarded-for", b"").split(b",")[0] or b"?").decode().strip()
            now = time.time()
            q_ = [t for t in self.hits.get(ip, []) if now - t < 60]
            if len(q_) >= self.per_minute:
                await send({"type": "http.response.start", "status": 429, "headers": [(b"content-type", b"application/json"), (b"retry-after", b"60")]})
                await send({"type": "http.response.body", "body": b'{"error":"rate limit exceeded, try again in a minute"}'})
                return
            q_.append(now)
            self.hits[ip] = q_
            if len(self.hits) > 5000:
                self.hits = {k: v for k, v in self.hits.items() if v and now - v[-1] < 60}
        await self.app(scope, receive, send)


def _forbid_extra_arguments() -> None:
    for t in mcp._tool_manager.list_tools():
        model = t.fn_metadata.arg_model
        model.model_config["extra"] = "forbid"
        model.model_rebuild(force=True)


_forbid_extra_arguments()


def http_app():
    from mcp.server.transport_security import TransportSecuritySettings
    from starlette.responses import JSONResponse
    hosts = [h for h in os.environ.get("CARDS_ALLOWED_HOSTS", "").split(",") if h]
    mcp.settings.stateless_http = True
    mcp.settings.json_response = True
    mcp.settings.transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=bool(hosts), allowed_hosts=hosts, allowed_origins=["*"] if hosts else [])

    @mcp.custom_route("/healthz", methods=["GET"])
    async def healthz(request):
        return JSONResponse({"ok": True, "latest_quarter": latest()})

    app = RateLimit(mcp.streamable_http_app(), int(os.environ.get("CARDS_RATE_PER_MIN", "60")))
    if os.environ.get("CARDS_USAGE_LOG", "1") != "0":
        from .usage import UsageLog
        app = UsageLog(app, [t.name for t in mcp._tool_manager.list_tools()])
    return app


def main() -> None:
    argv = sys.argv[1:]
    if "--check" in argv:
        print(json.dumps(dataset_info())[:2000])
        return
    if "--http" in argv:
        import uvicorn
        uvicorn.run(http_app(), host=os.environ.get("HOST", "0.0.0.0"), port=int(os.environ.get("PORT", "8080")), log_level="warning", timeout_keep_alive=5)
        return
    mcp.run()


if __name__ == "__main__":
    main()
