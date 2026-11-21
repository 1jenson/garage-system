#!/usr/bin/env python3
"""Fetch the Wents Diary day sheets into the local cache (private/wentsdiary/days/).

  python3 -I tools/wentsdiary/fetch.py                 14 days back, 90 ahead
  python3 -I tools/wentsdiary/fetch.py --back 7 --ahead 30
  python3 -I tools/wentsdiary/fetch.py --date 2026-11-21   one day only
  python3 -I tools/wentsdiary/fetch.py --status         what is cached, and are we signed in

Needs a sign-in first: run serve.py and open http://127.0.0.1:8795/wd/login.
Prints counts only - never a name, reg, phone or the token.
"""
import argparse
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wd  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--back", type=int, default=wd.BACK, help="days before today (default %d)" % wd.BACK)
    ap.add_argument("--ahead", type=int, default=wd.AHEAD, help="days after today (default %d)" % wd.AHEAD)
    ap.add_argument("--date", help="fetch this one date (YYYY-MM-DD) instead of the window")
    ap.add_argument("--status", action="store_true", help="show cache and sign-in state, fetch nothing")
    ap.add_argument("--shape", action="store_true", help="with --date: print the field names (not values) of the cached sheet")
    a = ap.parse_args()

    signed, who = wd.current_user()
    print("signed in:", "yes" if signed else "no (open http://127.0.0.1:8795/wd/login)")
    if a.status:
        s = wd.status()
        print("cached days: %d  (%s to %s)" % (s["days"], s["from"] or "-", s["to"] or "-"))
        return 0
    if not signed:
        return 2

    if a.date:
        d = dt.date.fromisoformat(a.date)
        sheet = wd.fetch_day(d)
        bk, notes, slots = wd.map_sheet(a.date, sheet)
        print("%s: %d bookings (%d MOT, %d service), %d notes, %d MOT slots" % (
            a.date, len(bk), sum(1 for b in bk if b["k"] == "mot"), sum(1 for b in bk if b["k"] == "svc"), len(notes), len(slots)))
        if a.shape:
            print(shape(sheet))
        return 0

    def prog(i, n):
        if i % 10 == 0 or i == n:
            print("  %d / %d days" % (i, n), flush=True)
    ok, err = wd.fetch_window(a.back, a.ahead, prog)
    m = wd.build()["meta"]
    print("fetched %d day sheets%s" % (ok, (" - stopped: " + err) if err else ""))
    print("cache: %d days, %d with bookings, %d MOT, %d service, %d notes" % (m["days"], m["daysWithBookings"], m["mot"], m["svc"], m["notes"]))
    return 1 if err else 0


def shape(o, depth=0, seen_lists=True):
    """Field names and value types only - no values."""
    pad = "  " * depth
    if isinstance(o, dict):
        return "\n".join("%s%s: %s" % (pad, k, shape(v, depth + 1).lstrip() if isinstance(v, (dict, list)) else type(v).__name__)
                         for k, v in o.items())
    if isinstance(o, list):
        return ("list[%d]" % len(o)) + ("\n" + shape(o[0], depth + 1) if o and isinstance(o[0], (dict, list)) else "")
    return type(o).__name__


if __name__ == "__main__":
    sys.exit(main())
