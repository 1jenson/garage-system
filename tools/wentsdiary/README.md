# Wents Diary mirror (read-only)

Pulls day sheets from the Wents Diary (wentsdb.azurewebsites.net) into the
local real-data build, so the Diary page at http://127.0.0.1:8795 shows the
real bookings, day notes and MOT slots for each day. Nothing is ever written
back: the only endpoints this code can call are the sign-in, token refresh,
`Account/CurrentUser` and `WorkshopBookings/GetWorkshopDaySheet`.

## The two commands

```bash
python3 -I tools/garagebase/serve.py 8795
```

then open http://127.0.0.1:8795/wd/login and sign in. The password goes from
the browser to the local server only, which forwards it once to the diary's
`/api/login`; only the returned token is kept, in
`private/wentsdiary/token.json` (git-ignored, owner-only). On sign-in the
server fetches 14 days back and 90 ahead, weekdays only, in the background (one request per
day, short pause between) into `private/wentsdiary/days/`, then opens the
Diary.

```bash
python3 -I tools/wentsdiary/fetch.py            # re-fetch the default window
python3 -I tools/wentsdiary/fetch.py --status   # signed in? how many days cached?
python3 -I tools/wentsdiary/fetch.py --date 2026-11-20 --shape   # field names only
```

In the browser the bottom banner shows how many days are cached, with a
"Refresh diary" button; `/?refresh=1` does the same. Nothing is re-fetched
otherwise.

## Files

- `wd.py` — sign-in, token store, fetcher, cache and the mapping to the mock's
  `BK` / `NOTES` / `SLOTS` shapes (`build()`).
- `fetch.py` — command line for the above; prints counts only.
- `tools/garagebase/serve.py` serves `/local-diary.js`, `/wd/login`,
  `/wd/status`, `/wd/refresh`, `/wd/diary.json`.
- `tools/garagebase/apply.js` puts the data into the mock: bookings into the
  MOT / Service / Extras sections, day notes, the day's MOT slot list, a real
  week strip and "Find next MOT slot".

## What maps and what doesn't

- MOT bookings → MOT section with the booked slot time; service bookings →
  Service & repairs (job = the diary's service item); "additional work" →
  Extras. Parts ordered / in, loan car / van / small van, messaged / confirmed
  and "cancellation requested" (shown as a note) all carry over.
- Day notes and the per-day enabled MOT slot list carry over.
- The garage is closed at weekends: only Monday to Friday are fetched, the
  week strip shows five days, and a weekend "today" opens on Monday.
- The diary has no tyre, technician or "done" data, so the Tyres list stays
  empty, every booking shows as not given out to anyone (the "Not given out"
  count is kept at 0) and nothing is ticked done.

Real data stays under `private/`; never commit it, screenshot it into the
repo, or put names, regs or phone numbers in commit messages or reports.
