# card-agreements-mcp

An MCP server over the CFPB Credit Card Agreements Database: the credit card agreements that issuers submit to the Consumer Financial Protection Bureau every quarter. It is made for questions across many issuers, not for reading one PDF:

- Which issuers charge an annual fee above $50?
- Compare grace periods across credit unions.
- Pull the late fee from Navy Federal's agreement.
- When did an issuer's penalty APR language change?

## What is in it

Every quarterly archive the CFPB publishes, 2011 Q3 to 2026 Q2 (57 quarters). Each agreement PDF is converted to text (with `pdftotext -layout`), indexed for full-text search, and run through a pattern-based extractor for key terms: annual fee, purchase / cash advance / balance transfer / penalty APR, grace period, foreign transaction fee, late payment fee, returned payment fee, balance transfer fee, cash advance fee and over-limit fee. Issuer name, quarter and, in older quarters, city, state, regulator and effective date come from the CFPB's own files.

Source: https://www.consumerfinance.gov/credit-cards/agreements/archive/ (agreements are public records submitted by issuers; this project is not affiliated with the CFPB).

## Tools

`dataset_info`, `search_issuers`, `list_agreements`, `get_terms`, `compare_terms`, `term_history`, `search_text`, `get_agreement_text`. Call `dataset_info` first: it lists the quarters loaded, term names, counts and caveats.

## Use it

Hosted endpoint (streamable HTTP): https://card-agreements-mcp.fly.dev/mcp (health check: `/healthz`). Rate limited per client.

Or run it yourself:

```
pip install .
python -m card_agreements_mcp.build extract.db serving.db site_issuers.json   # build the serving database
CARDS_DB=serving.db python -m card_agreements_mcp                              # stdio
CARDS_DB=serving.db python -m card_agreements_mcp --http                      # HTTP on :8080
```

## Read this before relying on a number

- Term values are pattern-matched snippets from the agreement text, with the page they came from. They are not a verified rate sheet. One snippet can hold figures for several card products or tiers; read the snippet.
- These are agreements, not live offers. Actual APRs and fees are usually in a separate rate table or the application, and often are not in the agreement at all.
- Issuers with fewer than 10,000 open accounts do not have to submit, so small issuers are missing.
- 2015 Q4 is a small sample (294 files, 11 issuers) that the CFPB published in January 2016.
- Early quarters (2011 to 2014) have flat file names; the issuer comes from the CFPB metadata file.
- OCR: roughly 5% of PDFs are scans with no text layer. They are run through `ocrmypdf` (Tesseract). OCR text and any term found in it are flagged `from_ocr` / `text_from_ocr` in tool output; OCR can misread digits, so check those against the PDF. Coverage is stated in `dataset_info` (`ocr`), and scans that have not been OCR'd show `has_text: false`.

## Reconciliation notes

The CFPB does not publish per-quarter totals of agreements or issuers; it says only "more than 600 card issuers". There is no official count to tie the totals to, so these are the checks that could be done. The numbers are also stored in the database and returned by `dataset_info`.

- Issuers, 2026 Q2: the CFPB site lists 806 issuers; the archive has 806 issuer folders; the names match.
- Files, 2026 Q2: counted per issuer on the CFPB site against PDFs in the zip. See `dataset_info.reconciliation` for the per-issuer differences. Known gap: the site shows 40 files per page and the count was read page by page.
- Every PDF in every zip was processed; the only skipped entries are macOS `__MACOSX` stubs and 2 files `pdftotext` could not read.
- Older quarters: rows in the CFPB metadata CSV are matched to PDFs by the CFPB file name.
- Identical PDFs repeated across quarters are stored once (by SHA-1) and linked to every quarter they appeared in.

## Usage logging

The hosted server keeps a small usage log, with no personal data and no query contents. For each initialize and tool call it stores: UTC timestamp, event, tool name, and the client name and version the client sends in the MCP initialize handshake. No IP addresses, arguments or results are stored. It is a SQLite table (`/data/usage.db`) on the same machine.

Read the stats from the machine:

```
fly ssh console -a card-agreements-mcp -C "python -m card_agreements_mcp.usage 30"
```

The number is the window in days (default 30). It prints calls per tool, per client and version, and per day.

## Licence

MIT for the code. The agreement text belongs to the issuers and comes from the CFPB's public database.
