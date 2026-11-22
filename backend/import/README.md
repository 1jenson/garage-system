# GarageBase → Supabase import

`import.py` loads the normalised GarageBase export in `private/local-data/`
into the Wents Workshop Supabase project. Standard library only; run it with
`python3 -I` from the repo root.

```bash
python3 -I backend/import/import.py --dry-run
```

prints the row counts per table and the number the next new invoice will get,
without touching the network. The real run:

```bash
python3 -I backend/import/import.py
```

needs two files that are **not** in git:

- `backend/supabase/project.json` (`url` and `anon`; written when the project was created; the anon key is fine to keep)
- `private/supabase-service-key.txt`: the **service role** key pasted by Jenson
  (Dashboard → Project Settings → API keys → service_role → Reveal → copy).
  One line, nothing else. The script never prints it.

It asks for `yes`, then upserts in batches of 500 (customers, vehicles,
invoices, invoice lines, payments, quotes, jobsheets, in that order so foreign
keys resolve) and finally calls `ws_reset_sequences()` so new invoice numbers
start at 78894 and quote/jobsheet/payment numbers start after the imported
maximums. Re-running is safe: every row is keyed on its GarageBase number.
`--only invoices,invoice_lines` limits a re-run to some tables.

Counts and timings go to `private/import-log.json`. No customer data is
printed.
