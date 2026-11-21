# garagebase — the mock with real GarageBase Pro data, locally only

Runs the current `mock/index.html` on this Mac with the real customers,
vehicles, invoices, quotes, payments and job sheets from the GarageBase Pro
back-end, so the new layout can be clicked through with real records.
Nothing here is deployed; the public mock keeps its demo data.

Everything real stays under `private/` (git-ignored). These scripts contain
no data. `mock/index.html` is not modified: the data is injected at serve
time.

## Two commands

One-off setup (Python 3.9+, no internet needed after the install):

```bash
python3 -m venv tools/garagebase/.venv && tools/garagebase/.venv/bin/pip install access-parser
```

1. Import — reads `private/garagebase/GBProV3_be.accdb` and writes normalised
   JSON to `private/local-data/` (about 80 MB, roughly a minute the first time
   while `extract.py` caches each Access table; seconds after that):

```bash
tools/garagebase/.venv/bin/python -I tools/garagebase/import.py
```

2. Serve — the mock with the real data on http://127.0.0.1:8795/ (loopback
   only; standard library only, so plain `python3` is fine):

```bash
python3 -I tools/garagebase/serve.py
```

Open http://127.0.0.1:8795/?fresh=1 — any query string works; it only stops a
cached copy from an earlier visit being used. Ctrl-C stops the server.

## What the importer does

- Keeps every old number as the record id: invoice `INV-00042` is GB Pro
  invoice 42, `Q-0231` is estimate 231, `JS-1187` is job sheet 1187, and the
  customer ref shown next to the name is the GB Pro customer ref.
- Dates become ISO (`2026-11-11`); money becomes pounds (Access stores it in
  ten-thousandths of a pound).
- Invoice lines: one `job` line with the work-done text, one `prt` line per
  part sold, a `lab` line from labour/hours, an `mot` line from the MOT fee,
  and outside work, sundries, lubricants and recovery as parts lines. Advise
  text becomes the advisories list. Payments are the GB Pro payments linked to
  the invoice (GB Pro only linked them from 2015 on; the 6,253 unlinked ones
  are all zero-amount placeholders, so nothing is lost).
- Merges customers that share a normalised phone number (spaces removed,
  +44 to 0) AND a surname into one account: the lowest ref is kept, the
  folded refs are listed on the account ("Merged from GB Pro refs…" in the
  notes) and in `private/local-data/merge-log.json`. Groups that share a
  phone but not a surname are NOT merged; they are listed in
  `private/local-data/review-list.json` for a human to look at.
- Junk "vehicles" (`CASH SALE`, `PARTS` and the like) become cash-sale
  invoices with no reg. A reg that appears under two customers belongs to
  the higher ref; the earlier owner is noted on the vehicle.
- Prints the counts at the end and writes them to `summary.json`.

`adapt.py` turns that JSON into the exact record shapes the mock seeds
(`customers`, `CX`, `vehicles`, `VX`, `invoices`, `legacy`, `QUOTES`, `JOBS`,
`REMS`). `serve.py` imports it; running it by hand writes
`private/local-data/mock-<years>.json` for inspection.

## How the data gets in without touching the mock

`serve.py` serves `mock/index.html` from disk with three things added on the
way out: a Content-Security-Policy meta tag that allows only `self`
(so the Google Fonts link and anything else off-box is blocked — the page
falls back to system fonts), a style that hides the page until the data is
in, and two script tags just before `</body>`:

- `/local-data.js` — `window.__localData = {...}` built by `adapt.py`;
- `/local-apply.js` — `apply.js`, which empties the mock's demo arrays and
  objects in place and refills them with the real records, clears the
  demo-only structures that point at demo cars (bookings, promises, drop
  and go, ring-backs, waitlist, tyre diary, audit trail, extra payments),
  then calls the mock's own `go()` to render.

`/sw.js` is replaced by a tiny worker that unregisters itself, so the mock's
offline cache never serves a stale copy on this port.

No hook was needed in `mock/index.html`. Two workarounds live in `apply.js`
because a few things in the mock are hard-coded rather than derived:

- some screens name demo regs literally (the home page's "recent" strip, for
  one); while a screen renders, any such reg without a real vehicle gets a
  placeholder so the screen does not throw;
- the invoice list renders every row (24,000 for five years), which took
  3.5 s, so with no search text and the "All" tab it shows the newest 1,000
  and says so. Searching or picking a tab still runs over everything.

## Performance and the years switch

Measured in the app's browser pane on this Mac:

| window | invoices in view | page load | invoice list |
|---|---|---|---|
| last 5 years (default) | 24,120 | 1.2 s | 3.5 s (now capped) |
| `?years=all` | 78,487 | 4.1 s | 9.2 s (now capped) |

So the default is the last five years of invoices as full records. Older
invoices are not dropped: they appear on the vehicle and customer pages as
"old system" history (date, title, total, mileage, invoice number), the way
the mock already shows legacy work. Add `?years=all` to the URL to load every
invoice in full, or `?years=N` for another window.

## Limits (what still looks like the demo)

- The eyebrow on the invoices page ("… owed · last number INV-0043"), the
  "6,503 customers" and "7,912 vehicles" labels and a few other headline
  numbers are literal strings in the mock, so they do not change. The blue
  bar at the bottom of the page shows the real counts and the real owed
  total instead.
- Search finds a customer by their kept ref, not by a folded ref; the
  folded refs are shown on the account.
- Estimate status: GB Pro's status codes have no reliable meaning, so a
  quote is "accepted" when an invoice for the same reg follows within 120
  days (the invoice is linked), "declined" for code 4, "expired" when past
  its valid-until date, "draft" for code 0, otherwise "sent".
- Job sheets have no mechanic in the mock's sense (no "who"); open ones are
  shown on hold.
- "Account ref" on a customer is GB Pro's export field, whatever it held.
- The mock's "today" is fixed at 11 Nov 2026; MOT-due and overdue figures
  are relative to that.
- Email is kept only when it contains an `@`; phone numbers are shown as
  stored, digits only for matching.

The importer's merge rule is deliberately strict; the review list is where
the judgement calls are.

## Wents Diary mirror

Sign in at http://127.0.0.1:8795/wd/login to fill the Diary page with the real
Wents Diary bookings (read-only). See `tools/wentsdiary/README.md`.
