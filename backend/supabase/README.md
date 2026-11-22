# Wents Workshop · Supabase backend

The real data store behind `mock/index.html` (the Workshop app). One Supabase
project on the free tier, London region, Postgres with row-level security.
Project ref, URL and anon key: see `project.json` in this folder once the
project exists (the anon key is public by design; the service role key lives
only in `private/` and is never committed).

## Migrations (`migrations/`, applied in order with the Supabase MCP `apply_migration`)

| File | What it does |
|---|---|
| `0001_schema.sql` | Tables `staff`, `customers`, `vehicles`, `invoices`, `invoice_lines`, `payments`, `quotes`, `jobsheets`, `bookings`, `day_notes`, `settings`; sequences `invoice_no_seq` (starts at **78894**, right after the last GarageBase invoice 78893), `quote_no_seq`, `jobsheet_no_seq`, `payment_id_seq` (moved past the imported maximums by `ws_reset_sequences()`); `updated_at` triggers; lines/payments changes bump their invoice |
| `0002_security.sql` | `is_staff()` (security definer: signed in **and** email in `staff` with `active`); every grant revoked from `anon`/`public`; RLS enabled on all tables with one policy per table `for all to authenticated using (is_staff()) with check (is_staff())`; `staff` is read-only for staff |
| `0003_api.sql` | RPCs the app calls: `ws_snapshot(p_years, p_since)` returns the app's in-memory shapes (same as `tools/garagebase/adapt.py`), `ws_save_invoice(p, p_no)` writes an invoice and assigns the next number from the sequence when `p_no` is null, `ws_next_no(kind)`, `ws_me()`, `ws_reset_sequences()` (service role only) |

Primary keys are the GarageBase numbers (customer ref, reg, invoice no, quote no,
jobsheet no, payment id), so the import is idempotent and the app's display ids
(`c123`, `INV-78894`, `Q-0231`, `JS-3929`) are derived, never stored twice.

## Who can see what

- **Anon key, not signed in:** nothing. Every table, sequence and function has
  its grants revoked from `anon`; RLS is on as well. `backend/check_anon.py`
  proves this against the live project (result below).
- **Signed in, email not in `staff`:** nothing (policies all go through `is_staff()`).
- **Signed in, email in `staff` and active:** read and write everything except
  `staff` (read-only) and `ws_reset_sequences` (service role only).
- **Service role key:** bypasses RLS. Only used by `backend/import` on this Mac.
- **Sign-ups:** disabled in the dashboard (Authentication → Sign In / Providers →
  Email → "Allow new users to sign up" off). Even if they were on, a new user is
  not staff and sees nothing.

## Adding a member of staff (Jenson, in the dashboard)

1. Authentication → Users → **Add user** → email + a password you choose → Create.
2. Table editor → `staff` → **Insert row**: `email` (same address), `name`
   (e.g. Jen), `initials` (JW), `who_key` (the app's WHO key: `adam`, `jen`, `karen`, or blank), `active` ticked.
3. Sign in on the Workshop app (More → Sign in).

To lock someone out: untick `active` on their `staff` row (and/or delete the auth user).

## Design notes

- Invoice numbers are the one thing that must be server-assigned, so the app
  creates an invoice with a provisional number, saves through `ws_save_invoice`
  and renames it to the number the sequence hands back. Quote and jobsheet
  numbers come from their sequences through `ws_next_no` on first save.
- `ws_snapshot` returns the last `p_years` (default 2) of invoices in full and
  the rest as compact per-vehicle history (`legacy`), exactly as the local
  real-data build does. Pass `p_since` to get only rows changed since then
  (delta sync), which keeps egress on the free tier (5 GB/month) low.
- Payments imported from GarageBase (`source='gb'`) are never deleted by the
  app; payments taken in the app are matched by date, method, amount and ref.
- Bookings and day notes are stored whole as JSON (`data`, `notes`) so diary
  changes in the app never need a migration.

## How the app connects (`mock/index.html`, last `<script>` block before the service worker)

- Two constants at the top of the block: `WS_URL` (project URL, `https://<ref>.supabase.co`)
  and `WS_ANON` (publishable/anon key). While either is blank the whole layer is
  dormant: no Sign in tile, no requests, the public demo runs exactly as before.
- Signed out: demo data, as now. More → **Sign in** posts email and password only
  to `<WS_URL>/auth/v1/token`; the session (access + refresh token) is kept in
  `localStorage` `ws.session` and refreshed before it expires.
- Signed in: one `ws_snapshot` RPC fills the same arrays the page already reads
  (`customers`, `vehicles`, `invoices`, `legacy`, `QUOTES`, `JOBS`, `BK`, `NOTES`
  …) using the same mapping as `tools/garagebase/apply.js`; the demo badge and
  demo-only panels are hidden (`body.ws-live`). The snapshot is cached in
  IndexedDB (`ws-live`, key `snap:<years>`), so later loads apply the cache and
  then fetch only rows changed since (`p_since`). `?years=all` / `?years=5` or
  `localStorage ws.years` change the full-invoice window (default 2).
- Writes: after each render the layer diffs the records it watches against a
  shadow copy and queues changes: invoices → `ws_save_invoice` (new ones get the
  next sequence number and are renamed from the provisional `INV-…`), quotes and
  jobsheets → upsert (numbers from `ws_next_no`), vehicle edits → `vehicles.app`,
  bookings → `bookings`, day notes → `day_notes`. Failures show "Not saved: …";
  network errors retry when back online; a `beforeunload` warning covers unsaved
  changes. Nothing is cached by the service worker for cross-origin requests.
- Sign-in with an email that is not an active `staff` row is rejected with
  "That email is not on the staff list" and the session is discarded.
- The local real-data build (`tools/garagebase/serve.py`, `local-loading`)
  keeps using its file data; the layer stays dormant there.

Known limitations

- The page's `ME` constant (who stamps notes, holds and diary actions) is still
  the demo `jen`; only the synthetic "Marked paid" payment row (added when an
  invoice is marked paid without a payment, because the server recomputes
  `paid` from payment rows) uses the signed-in staff member's `who_key`.
- Customers created in the app (`c` records) are not yet written back; invoices
  for them save, but the customer row does not. Vehicle edits save only the
  app's `app` blob (notes, flags), not make/model/MOT fields.

## Anon check result

_Filled in after the project exists; see `backend/check_anon.py`._
