#!/usr/bin/env python3
"""Load the GarageBase history (private/local-data/*.json) into the Wents
Workshop Supabase project.

  python3 -I backend/import/import.py --dry-run     # counts only, no network
  python3 -I backend/import/import.py               # the real thing (asks for a 'yes')
  python3 -I backend/import/import.py --only customers,vehicles

Reads:  private/local-data/{customers,vehicles,invoices,payments,quotes,jobsheets}.json
        backend/supabase/project.json          (url)
        private/supabase-service-key.txt       (service role key, pasted by Jenson; never printed)
Writes: nothing locally except private/import-log.json (counts and timings).

Idempotent: every row is upserted on its GarageBase number (customer ref, reg,
invoice no, payment id, quote no, jobsheet no; invoice lines on
(invoice_no, gb_id)), so re-running only overwrites rows with the same data.
Rows the Workshop app has since created (source='app') are untouched.
When done it calls ws_reset_sequences() so new numbers start after the
imported maximums (invoices: 78894).
"""
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(ROOT, "private", "local-data")
KEYFILE = os.path.join(ROOT, "private", "supabase-service-key.txt")
PROJECT = os.path.join(ROOT, "backend", "supabase", "project.json")
LOG = os.path.join(ROOT, "private", "import-log.json")
BATCH = 500


def load(name):
    with open(os.path.join(DATA, name)) as f:
        return json.load(f)


def d(s):
    """'YYYY-MM-DD' or None"""
    return s[:10] if s and re.match(r"^\d{4}-\d\d-\d\d", s) else None


def short(s, n=70):
    s = re.split(r"(?<=[.!?])\s", s or "")[0]
    return s if len(s) <= n else s[: n - 3].rsplit(" ", 1)[0] + "…"


def num(x):
    return None if x in (None, "") else x


# ---------- row builders (same mapping as tools/garagebase/adapt.py) ----------

def rows_customers(cust):
    for c in cust:
        yield {
            "ref": c["ref"], "name": c["name"] or "", "surname": c.get("surname"), "title": c.get("title"), "contact": c.get("contact"),
            "addr": c.get("addr"), "postcode": c.get("postcode"), "phone": c.get("phone"), "mobile": c.get("mobile"),
            "home": c.get("home"), "work": c.get("work"), "phones": c.get("phones") or [], "email": c.get("email"),
            "since": d(c.get("since")), "account": c.get("account"), "terms": num(c.get("terms")), "credit": num(c.get("credit")),
            "rate": num(c.get("rate")), "discount": num(c.get("discount")), "prefs": c.get("prefs") or {}, "heard": c.get("heard"),
            "acc_ref": c.get("accRef"), "inv_addr": c.get("invAddr"), "folded": c.get("folded") or [],
            "notes": ([{"d": "2026-11-20", "t": "Merged from GB Pro refs %s (same phone and surname): %s" % (
                ", ".join(str(f) for f in c["folded"]), "; ".join(c.get("foldedNames") or []))}] if c.get("folded") else [])
                     + [{"d": n.get("d"), "t": n.get("t")} for n in (c.get("notes") or [])],
            "source": "gb",
        }


def rows_vehicles(vehs):
    for v in vehs:
        label = " ".join(x for x in (v.get("make"), v.get("model")) if x) or "Unknown"
        es = v.get("engineSize") or ""
        if es:
            label += " %s" % (es if not es.isdigit() else "%.1f" % (int(es) / 1000.0))
        yield {
            "reg": v["reg"], "cust": v.get("cust"), "make": v.get("make"), "model": v.get("model"), "engine_size": es or None,
            "label": label, "year": num(v.get("year")), "mot": d(v.get("mot")), "vin": v.get("vin"), "engine": v.get("engine"),
            "colour": v.get("colour"), "tyre": v.get("tyre"), "fuel": v.get("fuel"), "miles": num(v.get("miles")),
            "notes": v.get("notes") or [], "prev": v.get("prev") or [], "source": "gb",
        }


def rows_invoices(invs):
    for x in invs:
        yield {
            "no": x["no"], "cust": x.get("cust"), "reg": x.get("reg") or None, "cash": bool(x.get("cash")), "date": d(x.get("date")),
            "due": d(x.get("due")), "title": x.get("title"), "work": x.get("work"), "advise": x.get("advise") or [], "memo": x.get("memo"),
            "job": num(x.get("job")), "status": x.get("status") or "paid", "hold": x.get("hold") or None, "labour": num(x.get("labour")),
            "hours": num(x.get("hours")), "rate": num(x.get("rate")), "parts": num(x.get("parts")), "mot_fee": num(x.get("motFee")),
            "mot_pass": x.get("motPass") if x.get("motPass") in (True, False) else None, "outside": num(x.get("outside")),
            "others": num(x.get("others")), "lubricants": num(x.get("lubricants")), "recovery": num(x.get("recovery")),
            "net": num(x.get("subtotal")), "vat": num(x.get("vat")), "vat_rate": num(x.get("vatRate")), "total": x.get("total") or 0,
            "paid": x.get("paid") or 0, "mechanic": x.get("mechanic") or None, "miles": num(x.get("miles")), "next_service": d(x.get("nextService")),
            "app": ({"serviceAtMiles": x["serviceAtMiles"]} if x.get("serviceAtMiles") else {}), "source": "gb",
        }


def rows_lines(invs):
    """The app's line shapes: job text, each part, labour, MOT, then the sundries."""
    for x in invs:
        pos = 0
        n = x["no"]

        def line(kind, descr, qty, price, gb_id, cost=None):
            nonlocal pos
            pos += 1
            return {"invoice_no": n, "pos": pos, "kind": kind, "descr": descr or "", "qty": qty or 0, "price": price or 0,
                    "total": round((qty or 0) * (price or 0), 2), "cost": cost, "gb_id": gb_id}
        if x.get("work"):
            yield line("job", x["work"], 0, 0, "work")
        for l in x.get("lines") or []:
            yield line("prt", l.get("desc"), l.get("qty"), l.get("price"), "l%s" % l.get("id", pos), l.get("cost"))
        if x.get("labour"):
            hrs = x.get("hours") or 1
            yield line("lab", "Labour", hrs, round(x["labour"] / hrs, 2), "labour")
        if x.get("motFee"):
            yield line("mot", "MOT test" + (" · pass" if x.get("motPass") else ""), 1, x["motFee"], "mot")
        for key, label in (("outside", "Outside work"), ("others", "Sundries"), ("lubricants", "Lubricants"), ("recovery", "Recovery")):
            if x.get(key):
                yield line("prt", label, 1, x[key], key)


def rows_payments(pays, inv_nos):
    for p in pays:
        yield {
            "id": p["id"], "invoice_no": p["inv"] if p.get("inv") in inv_nos else None, "cust": p.get("cust"), "date": d(p.get("date")),
            "amount": p.get("amount") or 0, "method": p.get("method"), "method_raw": p.get("methodRaw"), "ref": p.get("ref") or None,
            "source": "gb",
        }


def rows_quotes(quotes):
    for q in quotes:
        lines, fixed_any = [], False
        for w in q.get("work") or []:
            if w.get("fixed"):
                lines.append({"k": "lab", "d": w.get("desc") or "Work", "q": 1, "p": w["fixed"]})
                fixed_any = True
            elif w.get("desc"):
                lines.append({"k": "job", "d": w["desc"], "q": 0, "p": 0})
        if q.get("labour") and not fixed_any:
            hrs = sum(w.get("hours") or 0 for w in q.get("work") or []) or 1
            lines.append({"k": "lab", "d": "Labour", "q": hrs, "p": round(q["labour"] / hrs, 2)})
        for p in q.get("parts") or []:
            lines.append({"k": "prt", "d": p.get("desc"), "q": p.get("qty"), "p": p.get("price")})
        yield {
            "no": q["no"], "cust": q.get("cust"), "reg": q.get("reg") or None, "date": d(q.get("date")), "valid": d(q.get("valid")),
            "status_code": q.get("statusCode"), "status": q.get("status") or "draft", "became_invoice": num(q.get("becameInvoice")),
            "title": q.get("title"), "make": q.get("make"), "model": q.get("model"), "labour": num(q.get("labour")),
            "parts_total": num(q.get("partsTotal")), "total": num(q.get("total")), "work": q.get("work") or [], "parts": q.get("parts") or [],
            "lines": lines, "opts": [], "advise": [],
            "hist": [[d(q.get("date")) or "2019-01-01", "Imported from GB Pro estimate %d (status code %s)" % (q["no"], q.get("statusCode"))]],
            "source": "gb",
        }


def rows_jobsheets(jobs, inv_by_no, cutoff):
    for j in jobs:
        inv = inv_by_no.get(j.get("invoice")) if j.get("invoice") else None
        if j.get("complete") or inv:
            st = "inv"
        elif j.get("date") and j["date"] < cutoff:
            st = "inv"
        else:
            st = "hold"
        yield {
            "no": j["no"], "date": d(j.get("date")), "reg": j.get("reg") or None, "cust": j.get("cust"),
            "title": short(j.get("description") or j.get("workDone") or "Job sheet"), "description": j.get("description"),
            "work_done": j.get("workDone"), "advise": j.get("advise") or [], "problems": j.get("problems"), "mechanic": j.get("mechanic"),
            "complete": bool(j.get("complete")), "hours": num(j.get("hours")), "hours_to_charge": num(j.get("hoursToCharge")),
            "invoice": inv["no"] if inv else None, "status": st, "hold": "Not marked complete in GB Pro" if st == "hold" else None,
            "lines": [{"k": "job", "d": j.get("workDone") or j.get("description") or "Job sheet", "q": 0, "p": 0}],
            "source": "gb",
        }


# ---------- transport ----------

class Client:
    def __init__(self, url, key):
        self.url, self.key = url.rstrip("/"), key

    def req(self, path, body, method="POST", extra=None):
        h = {"apikey": self.key, "Authorization": "Bearer " + self.key, "Content-Type": "application/json", "Prefer": "return=minimal"}
        h.update(extra or {})
        data = json.dumps(body, ensure_ascii=False).encode()
        for attempt in range(4):
            req = urllib.request.Request(self.url + path, data=data, headers=h, method=method)
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    return r.status, r.read()
            except urllib.error.HTTPError as e:
                msg = e.read()[:300].decode("utf-8", "replace")
                if e.code in (429, 500, 502, 503, 504) and attempt < 3:
                    time.sleep(2 * (attempt + 1))
                    continue
                raise SystemExit("HTTP %d on %s: %s" % (e.code, path, msg))
            except urllib.error.URLError as e:
                if attempt < 3:
                    time.sleep(2 * (attempt + 1))
                    continue
                raise SystemExit("network error on %s: %s" % (path, e))

    def upsert(self, table, rows, on_conflict):
        return self.req("/rest/v1/%s?on_conflict=%s" % (table, on_conflict), rows,
                        extra={"Prefer": "return=minimal,resolution=merge-duplicates"})

    def rpc(self, fn, args=None):
        s, b = self.req("/rest/v1/rpc/%s" % fn, args or {}, extra={"Prefer": "return=representation"})
        return json.loads(b or b"null")


def batches(it, n=BATCH):
    buf = []
    for r in it:
        buf.append(r)
        if len(buf) >= n:
            yield buf
            buf = []
    if buf:
        yield buf


def main():
    dry = "--dry-run" in sys.argv
    only = None
    if "--only" in sys.argv:
        only = set(sys.argv[sys.argv.index("--only") + 1].split(","))
    t0 = time.time()
    cust, vehs, invs = load("customers.json"), load("vehicles.json"), load("invoices.json")
    pays, quotes, jobs = load("payments.json"), load("quotes.json"), load("jobsheets.json")
    inv_nos = {x["no"] for x in invs}
    inv_by_no = {x["no"]: x for x in invs}
    cutoff = (dt.date(2026, 11, 11) - dt.timedelta(days=365 * 5)).isoformat()

    plan = [
        ("customers", "ref", lambda: rows_customers(cust), len(cust)),
        ("vehicles", "reg", lambda: rows_vehicles(vehs), len(vehs)),
        ("invoices", "no", lambda: rows_invoices(invs), len(invs)),
        ("invoice_lines", "invoice_no,gb_id", lambda: rows_lines(invs), None),
        ("payments", "id", lambda: rows_payments(pays, inv_nos), len(pays)),
        ("quotes", "no", lambda: rows_quotes(quotes), len(quotes)),
        ("jobsheets", "no", lambda: rows_jobsheets(jobs, inv_by_no, cutoff), len(jobs)),
    ]
    counts = {}
    for name, _, gen, n in plan:
        counts[name] = n if n is not None else sum(1 for _ in gen())
    print("Rows to load:")
    for k, v in counts.items():
        print("  %-14s %7d" % (k, v))
    print("  invoice numbers %d..%d, next new invoice will be %d" % (min(inv_nos), max(inv_nos), max(78893, max(inv_nos)) + 1))
    print("  quotes up to %d, jobsheets up to %d, payment ids up to %d" % (max(q["no"] for q in quotes), max(j["no"] for j in jobs), max(p["id"] for p in pays)))
    print("  batches of %d, about %d requests" % (BATCH, sum((v + BATCH - 1) // BATCH for v in counts.values())))
    if dry:
        print("Dry run: nothing sent.")
        return 0

    if not os.path.exists(KEYFILE):
        raise SystemExit("Service role key not found at %s (paste it there, one line, from Dashboard > Project Settings > API keys)" % KEYFILE)
    with open(KEYFILE) as f:
        key = f.read().strip()
    if not key or len(key) < 40:
        raise SystemExit("Service role key file looks empty")
    with open(PROJECT) as f:
        url = json.load(f)["url"]
    print("Target: %s" % url)
    if os.environ.get("WS_IMPORT_YES") != "1":
        if input("Type yes to load the rows above: ").strip().lower() != "yes":
            print("Stopped.")
            return 1
    c = Client(url, key)
    log = {"at": dt.datetime.utcnow().isoformat() + "Z", "url": url, "counts": counts, "sent": {}, "errors": []}
    for name, conflict, gen, _ in plan:
        if only and name not in only:
            continue
        sent, t1 = 0, time.time()
        for b in batches(gen()):
            c.upsert(name, b, conflict)
            sent += len(b)
            print("\r  %-14s %7d / %d" % (name, sent, counts[name]), end="", flush=True)
        print("\r  %-14s %7d / %d  %.0fs" % (name, sent, counts[name], time.time() - t1))
        log["sent"][name] = sent
    seq = c.rpc("ws_reset_sequences")
    print("Sequences:", json.dumps(seq))
    log["sequences"] = seq
    log["seconds"] = round(time.time() - t0)
    with open(LOG, "w") as f:
        json.dump(log, f, indent=1)
    print("Done in %ds; log at %s" % (log["seconds"], LOG))
    return 0


if __name__ == "__main__":
    sys.exit(main())
