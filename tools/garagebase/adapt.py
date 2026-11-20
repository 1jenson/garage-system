#!/usr/bin/env python3
"""Normalised GarageBase JSON (private/local-data/*.json, written by import.py)
-> the exact in-memory record shapes mock/index.html uses.

build(years) returns one dict:
  customers, CX, vehicles, VX, invoices, legacy, QUOTES, JOBS, REMS, meta
with the mock's own field names (see the demo seed near the top of the mock).

Invoices dated inside the last `years` years are full records; older ones go
into legacy[reg] as compact history (the mock already shows those as "old
system" entries).  years=None means everything.

Usage:  .venv/bin/python -I tools/garagebase/adapt.py [years|all]   (writes
private/local-data/mock-<years>.json; serve.py calls build() itself).
"""
import datetime as dt
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(ROOT, "private", "local-data")
TODAY = dt.date(2026, 11, 11)   # the mock's own "today" (TD in index.html)


def _load(name):
    with open(os.path.join(DATA, name)) as f:
        return json.load(f)


def cid(ref):
    return "c%d" % ref if ref else ""


def inv_no(no):
    return "INV-%05d" % no


def q_no(no):
    return "Q-%04d" % no


def js_no(no):
    return "JS-%d" % no


def short(s, n=70):
    s = re.split(r"(?<=[.!?])\s", s or "")[0]
    return s if len(s) <= n else s[: n - 3].rsplit(" ", 1)[0] + "…"


def build(years=5):
    cust = _load("customers.json")
    vehs = _load("vehicles.json")
    invs = _load("invoices.json")
    quotes = _load("quotes.json")
    jobs = _load("jobsheets.json")

    cutoff = "" if years is None else (TODAY - dt.timedelta(days=365 * years)).isoformat()
    names = {c["ref"]: c["name"] for c in cust}

    # customers + CX
    customers, CX = [], {}
    for c in cust:
        i = cid(c["ref"])
        customers.append({
            "id": i, "name": c["name"], "phone": c["phone"], "email": c["email"],
            "addr": c["addr"], "since": (c["since"] or "")[:4],
        })
        notes = [{"d": n["d"], "t": n["t"]} for n in c["notes"]]
        if c["folded"]:
            notes.insert(0, {"d": "2026-11-20", "t": "Merged from GB Pro refs %s (same phone and surname): %s" % (
                ", ".join(str(f) for f in c["folded"]), "; ".join(c.get("foldedNames", [])) if c.get("foldedNames") else "")})
        CX[i] = {
            "ref": c["ref"], "acct": c["account"], "terms": c["terms"], "rate": c["rate"] or 68,
            "disc": c["discount"], "tel": c["home"], "mob": c["mobile"] or c["phone"],
            "inv": c["invAddr"] or (c["name"] if c["account"] == "Account" else ""),
            "prefs": c["prefs"], "via": "Text", "heard": c["heard"], "accRef": c["accRef"],
            "notes": notes, "files": [], "also": c["folded"], "contact": c["contact"],
        }

    # vehicles + VX
    vehicles, VX = [], {}
    for v in vehs:
        make = " ".join(x for x in (v["make"], v["model"]) if x) or "Unknown"
        if v["engineSize"]:
            make += " %s" % (v["engineSize"] if not v["engineSize"].isdigit() else "%.1f" % (int(v["engineSize"]) / 1000.0))
        vehicles.append({
            "reg": v["reg"], "make": make, "year": v["year"] or "", "cust": cid(v["cust"]),
            "miles": v["miles"], "mot": v["mot"], "fuel": v["fuel"], "colour": v["colour"],
        })
        notes = list(v["notes"])
        for p in v["prev"]:
            notes.append("Previously on GB Pro ref %d (%s)" % (p["cust"], names.get(p["cust"], "")))
        VX[v["reg"]] = {
            "vin": v["vin"] or "—", "eng": v["engine"] or "—", "tyre": v["tyre"] or "—", "oil": "—",
            "key": "", "tax": "", "nuts": "—", "prev": [], "notes": notes,
        }

    # invoices -> full records (window) or legacy history (older)
    job_nos = {j["no"] for j in jobs}
    invoices, legacy = [], {}
    n_full = n_legacy = n_dropped = 0
    for x in invs:
        if cutoff and x["date"] < cutoff:
            if x["reg"]:
                legacy.setdefault(x["reg"], []).append({"d": x["date"], "t": x["title"], "a": x["total"], "m": x["miles"], "n": inv_no(x["no"])})
                n_legacy += 1
            else:
                n_dropped += 1
            continue
        lines = []
        if x["work"]:
            lines.append({"k": "job", "d": x["work"], "q": 0, "p": 0})
        for l in x["lines"]:
            lines.append({"k": "prt", "d": l["desc"], "q": l["qty"], "p": l["price"]})
        if x["labour"]:
            hrs = x["hours"] or 1
            lines.append({"k": "lab", "d": "Labour", "q": hrs, "p": round(x["labour"] / hrs, 2)})
        if x["motFee"]:
            lines.append({"k": "mot", "d": "MOT test" + (" · pass" if x["motPass"] else ""), "q": 1, "p": x["motFee"]})
        for key, label in (("outside", "Outside work"), ("others", "Sundries"), ("lubricants", "Lubricants"), ("recovery", "Recovery")):
            if x[key]:
                lines.append({"k": "prt", "d": label, "q": 1, "p": x[key]})
        rec = {
            "n": inv_no(x["no"]), "cust": cid(x["cust"]), "reg": x["reg"], "date": x["date"], "due": x["due"],
            "title": x["title"], "status": x["status"], "total": x["total"], "paid": x["paid"], "miles": x["miles"],
            "adv": x["advise"], "lines": lines, "note": x["memo"],
            "pays": [{"d": p["date"], "m": p["method"], "a": p["amount"], "ref": p["ref"]} for p in x["payments"]],
        }
        if x["job"] and x["job"] in job_nos:
            rec["js"] = js_no(x["job"])
        if x["hold"]:
            rec["hold"] = x["hold"]
        if x["cash"] and not x["reg"]:
            rec["cash"] = True
        if x["mechanic"]:
            rec["mech"] = x["mechanic"]
        invoices.append(rec)
        n_full += 1
    for r in legacy:
        legacy[r].sort(key=lambda h: h["d"], reverse=True)

    # estimates -> QUOTES
    QUOTES = []
    for q in quotes:
        lines = []
        fixed_any = False
        for w in q["work"]:
            if w["fixed"]:
                lines.append({"k": "lab", "d": w["desc"] or "Work", "q": 1, "p": w["fixed"]})
                fixed_any = True
            elif w["desc"]:
                lines.append({"k": "job", "d": w["desc"], "q": 0, "p": 0})
        if q["labour"] and not fixed_any:
            hrs = sum(w["hours"] for w in q["work"]) or 1
            lines.append({"k": "lab", "d": "Labour", "q": hrs, "p": round(q["labour"] / hrs, 2)})
        for p in q["parts"]:
            lines.append({"k": "prt", "d": p["desc"], "q": p["qty"], "p": p["price"]})
        rec = {
            "id": q_no(q["no"]), "c": cid(q["cust"]), "r": q["reg"], "t": q["title"], "st": q["status"],
            "d": q["date"] or "2019-01-01", "valid": q["valid"] or q["date"], "note": "", "inote": "",
            "lines": lines, "opts": [], "hist": [[q["date"] or "2019-01-01", "Imported from GB Pro estimate %d (status code %d)" % (q["no"], q["statusCode"])]],
        }
        if q["becameInvoice"]:
            rec["inv"] = inv_no(q["becameInvoice"])
        QUOTES.append(rec)

    # jobsheets -> JOBS
    inv_by_no = {x["no"]: x for x in invs}
    JOBS = []
    for j in jobs:
        inv = inv_by_no.get(j["invoice"]) if j["invoice"] else None
        if j["complete"] or inv:
            st = "inv"
        elif cutoff and j["date"] and j["date"] < cutoff:
            st = "inv"
        else:
            st = "hold"
        rec = {
            "id": js_no(j["no"]), "t": short(j["description"] or j["workDone"] or "Job sheet"), "c": cid(j["cust"]),
            "r": j["reg"], "st": st, "a": inv["total"] if inv else 0, "who": "", "miles": inv["miles"] if inv else 0,
            "keys": "", "req": j["description"], "found": j["workDone"], "adv": j["advise"], "auth": "",
            "lines": [{"k": "job", "d": j["workDone"] or j["description"] or "Job sheet", "q": 0, "p": 0}],
        }
        if inv:
            rec["n"] = inv_no(inv["no"])
        if j["problems"]:
            rec["found"] = (rec["found"] + " Problems: " + j["problems"]).strip()
        if st == "hold":
            rec["hold"] = "Not marked complete in GB Pro"
        JOBS.append(rec)

    REMS = [{"id": "m" + v["reg"].replace(" ", ""), "reg": v["reg"], "type": "mot", "due": v["mot"], "st": "new", "log": []}
            for v in vehicles if v["mot"]]

    meta = {
        "years": years, "cutoff": cutoff, "customers": len(customers), "vehicles": len(vehicles),
        "invoicesFull": n_full, "invoicesLegacy": n_legacy, "invoicesDroppedNoReg": n_dropped,
        "quotes": len(QUOTES), "jobs": len(JOBS), "lastInvoice": inv_no(max(x["no"] for x in invs)),
        "owedTotal": round(sum(i["total"] - i["paid"] for i in invoices if i["status"] == "owed"), 2),
    }
    return {"customers": customers, "CX": CX, "vehicles": vehicles, "VX": VX, "invoices": invoices,
            "legacy": legacy, "QUOTES": QUOTES, "JOBS": JOBS, "REMS": REMS, "meta": meta}


def parse_years(s):
    s = str(s or "5").strip().lower()
    if s in ("all", "0", "none", ""):
        return None
    try:
        return max(1, min(30, int(s)))
    except ValueError:
        return 5


if __name__ == "__main__":
    y = parse_years(sys.argv[1] if len(sys.argv) > 1 else "5")
    d = build(y)
    p = os.path.join(DATA, "mock-%s.json" % ("all" if y is None else y))
    with open(p, "w") as f:
        json.dump(d, f, ensure_ascii=False, separators=(",", ":"))
    print(json.dumps(d["meta"], indent=1))
    print("wrote", p, "%.1f MB" % (os.path.getsize(p) / 1e6))
