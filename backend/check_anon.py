#!/usr/bin/env python3
"""Prove the Wents Workshop project gives nothing away without a staff login.

Uses only the public anon key (backend/supabase/project.json) and the standard
library.  For every table it tries select, insert, update and delete through
PostgREST, calls every RPC, and tries to sign up a throwaway email through
GoTrue.  Prints PASS/FAIL per check and exits 1 on any FAIL.  Never prints
row data.

  python3 -I backend/check_anon.py            # against project.json
  python3 -I backend/check_anon.py --jwt X    # also test as a signed-in user who is NOT staff (paste a JWT)
"""
import json
import os
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
TABLES = ["staff", "customers", "vehicles", "invoices", "invoice_lines", "payments",
          "quotes", "jobsheets", "bookings", "day_notes", "settings"]
RPCS = {"ws_snapshot": {}, "ws_save_invoice": {"p": {}}, "ws_next_no": {"kind": "quote"},
        "ws_me": {}, "ws_reset_sequences": {}, "is_staff": {}}


def load_project():
    with open(os.path.join(HERE, "supabase", "project.json")) as f:
        return json.load(f)


def call(url, key, method="GET", body=None, jwt=None, extra=None):
    h = {"apikey": key, "Authorization": "Bearer " + (jwt or key), "Content-Type": "application/json", "Accept": "application/json"}
    h.update(extra or {})
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except urllib.error.URLError as e:
        return 0, str(e).encode()


def main():
    jwt = None
    if "--jwt" in sys.argv:
        jwt = sys.argv[sys.argv.index("--jwt") + 1]
    p = load_project()
    base, key = p["url"].rstrip("/"), p["anon"]
    who = "signed-in non-staff user" if jwt else "anon key"
    fails = 0
    print("Checking %s as %s" % (base, who))

    def ok(label, status, body, allow_empty=False):
        nonlocal fails
        rows = None
        try:
            rows = json.loads(body or b"null")
        except Exception:
            rows = None
        leaked = isinstance(rows, list) and len(rows) > 0 or isinstance(rows, dict) and status < 300 and any(
            isinstance(v, list) and v for v in rows.values())
        if status in (401, 403, 404, 405) or (allow_empty and status == 200 and rows == []):
            print("  PASS  %-40s HTTP %s" % (label, status))
        elif status < 300 and not leaked:
            # 200 with nothing in it (RLS filtering) is still a pass, but note it
            print("  PASS  %-40s HTTP %s (empty)" % (label, status))
        else:
            fails += 1
            print("  FAIL  %-40s HTTP %s %s" % (label, status, (body or b"")[:120].decode("utf-8", "replace").replace("\n", " ")))

    for t in TABLES:
        u = "%s/rest/v1/%s" % (base, t)
        s, b = call(u + "?select=*&limit=5", key, jwt=jwt); ok("select " + t, s, b, allow_empty=True)
        s, b = call(u, key, "POST", {}, jwt=jwt); ok("insert " + t, s, b)
        s, b = call(u + "?limit=1", key, "PATCH", {"updated_at": "2000-01-01"}, jwt=jwt); ok("update " + t, s, b)
        s, b = call(u + "?updated_at=lt.1900-01-01", key, "DELETE", jwt=jwt); ok("delete " + t, s, b)
    for fn, args in RPCS.items():
        s, b = call("%s/rest/v1/rpc/%s" % (base, fn), key, "POST", args, jwt=jwt); ok("rpc " + fn, s, b)
    # schema listing (OpenAPI root) should not list tables for anon
    s, b = call(base + "/rest/v1/", key, jwt=jwt)
    try:
        paths = [k for k in json.loads(b).get("paths", {}) if k != "/"]
    except Exception:
        paths = []
    if paths:
        fails += 1
        print("  FAIL  %-40s %d paths visible" % ("openapi listing", len(paths)))
    else:
        print("  PASS  %-40s nothing listed" % "openapi listing")
    # sign-up must be refused
    s, b = call(base + "/auth/v1/signup", key, "POST", {"email": "nobody-%d@example.invalid" % os.getpid(), "password": "x" * 24})
    if s >= 400:
        print("  PASS  %-40s HTTP %s" % ("sign-up refused", s))
    else:
        fails += 1
        print("  FAIL  %-40s HTTP %s (sign-ups are still enabled: Authentication > Sign In / Providers > Email)" % ("sign-up refused", s))
    print("RESULT: %s (%d failing)" % ("PASS" if not fails else "FAIL", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
