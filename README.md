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

## APR terms: per card, intro offers, variable rates, index and margin

`purchase_apr`, `balance_transfer_apr` and `cash_advance_apr` rows carry extra fields, all read from the snippet they come with:

| field | meaning |
|---|---|
| `card_name`, `scope` | the card product the rate is tied to when the table names one (for example `Platinum` or `Platinum Rewards`), with `scope: card`. When the agreement does not name a product for that rate, `card_name` is null and `scope` is `agreement`. |
| `has_intro_rate`, `intro_rate_pct`, `intro_period` | an introductory or promotional rate is mentioned; the rate and period (for example 1.99% for `12 billing cycles`) when they could be parsed. `has_intro_rate` is false only when a rate is stated and no intro wording appears; null when unknown. |
| `is_variable`, `index_name` | `true` when the text says the rate varies or is tied to an index, `false` when it says fixed or "will not vary", null when it says neither. `index_name` is `Prime Rate`, `WSJ Prime Rate`, `SOFR`, `LIBOR` or `Treasury` when the text names it. |
| `margin_pct_min`, `margin_pct_max` | the margin over the index when the agreement states "prime plus 9.99%" or "we add 8.74% to the Prime Rate". Kept even when no absolute APR is stated. |
| `rate_basis` | `stated` (an APR figure appears), `margin` (only index plus margin appears) or `unknown` (a label with no figure, for example a blank form). A margin-only row has no APR figure in the agreement and none is computed here. |

`compare_terms` takes `has_intro_rate`, `is_variable`, `index_name_contains`, `rate_basis` and `card_name_contains` for these three terms, for questions such as "credit union cards with no intro offer" or "fixed-rate cards".

Limits: card names come from headings near the rate table and are missed when a table is laid out in an unusual way; a margin range (for example 8.74% to 14.74%) covers several tiers or cards in one row; the current value of the index is not stored.

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
