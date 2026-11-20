#!/usr/bin/env python3
"""GarageBase Pro -> normalised JSON.

Reads the Access back-end (private/garagebase/GBProV3_be.accdb, via the pickle
cache that extract.py keeps under private/local-data/raw/) and writes plain JSON
to private/local-data/:

  customers.json  vehicles.json  invoices.json (lines included)  quotes.json
  payments.json   jobsheets.json  merge-log.json  review-list.json  summary.json

Every old number (customer ref, invoice no, quote no, job no, payment no) is kept
as the record id.  Dates are ISO (YYYY-MM-DD).  Money is in pounds (Access keeps
currency as an integer number of 1/10000 pound).

Customers that share a normalised phone number AND a surname are folded into one
account: the lowest ref is kept, the folded refs are listed on it and in
merge-log.json.  Accounts that share a phone but not a surname are NOT merged;
they are listed in review-list.json for a human to look at.

Usage:  tools/garagebase/.venv/bin/python -I tools/garagebase/import.py
Everything written stays under private/ (git-ignored).  No network access.
"""
import json
import os
import re
import sys
import time
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract import load  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "private", "local-data")

TITLES = {"mr", "mrs", "miss", "ms", "dr", "rev", "sir", "lady", "lord", "mr&mrs", "mr/mrs"}
JUNK_REG = re.compile(r"cash|parts|sale|stock|workshop|account|^\W*$", re.I)


# ---------- small helpers -------------------------------------------------
def pounds(v):
    """Access currency (int, 1/10000 pound) -> float pounds."""
    if v is None:
        return 0.0
    if isinstance(v, bool):
        return 0.0
    return round(float(v) / 10000.0, 2)


def iso(v):
    """'YYYY-MM-DD HH:MM:SS' (or anything else) -> 'YYYY-MM-DD' or ''."""
    s = str(v or "").strip()
    return s[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", s) else ""


def txt(v):
    return re.sub(r"\s+", " ", str(v)).strip() if v is not None else ""


def lines_of(v):
    """Free text -> list of sentences/lines (for advisories)."""
    if not v:
        return []
    s = str(v).replace("\r", "\n")
    parts = [p.strip(" .;") for p in re.split(r"\n+|(?<=[.!?])\s+(?=[A-Z])", s)]
    return [p for p in parts if len(p) > 1]


def norm_phone(v):
    """Digits only; +44/44 prefix -> leading 0.  '' if too short to be a phone."""
    d = re.sub(r"\D", "", str(v or ""))
    if d.startswith("44") and len(d) >= 12:
        d = "0" + d[2:]
    if d.startswith("0044"):
        d = "0" + d[4:]
    return d if len(d) >= 10 else ""


def fmt_phone(v):
    """Keep what GB Pro stored, minus any name tacked on the end, lightly tidied."""
    s = txt(v)
    m = re.match(r"^(\+?[\d\s()\-]{6,})", s)
    if not m:
        return s
    d = norm_phone(m.group(1))
    if len(d) == 11 and d.startswith("07"):
        return d[:5] + " " + d[5:]
    if len(d) == 11:
        return d[:5] + " " + d[5:]
    return m.group(1).strip()


def surname(name):
    toks = [t for t in re.split(r"[\s,]+", str(name or "").lower()) if t]
    toks = [t for t in toks if t.replace(".", "") not in TITLES]
    if not toks:
        return ""
    s = re.sub(r"[^a-z\-']", "", toks[-1])
    return s if len(s) >= 2 else ""


def clean_reg(v):
    s = re.sub(r"\s+", " ", str(v or "").strip().upper())
    return s


def cols(table, *names):
    """Row iterator over selected columns of an access-parser table dict."""
    arrs = [table.get(n, [None] * len(next(iter(table.values())))) for n in names]
    return zip(*arrs)


# ---------- customers + merge ---------------------------------------------
def build_customers():
    t = load("CustomerDetails")
    rows = {}
    for (ref, name, title, ini, a1, a2, town, county, pc, home, work, mob, email, since,
         acct, terms, credit, rate, disc, stmts, mail, motrem, contact, inv1, inv2, invt,
         invc, invpc, remarks, other, heard, export) in cols(
            t, "CustomerRefNo", "Name", "Title", "Initials", "AddressLine1", "AddressLine2",
            "Town", "County", "Postcode", "Home Tel number", "Work Tel number",
            "Mobile Tel number", "Email", "Customer Since", "TypeOfAccount", "PaymentTerms",
            "CreditLimit", "AgreedHourlyRate", "CurrentDiscount", "SendStatements", "Mailshot",
            "SendMOT Reminders", "Contact Name", "Invoice Address1", "Invoice Address2",
            "InvoiceTown", "InvoiceCounty", "InvoicePostcode", "remarks", "Other",
            "Advert Seen in", "ExportRef"):
        if ref is None:
            continue
        nm = txt(name)
        tt = txt(title)
        full = nm if (not tt or nm.lower().startswith(tt.lower())) else f"{tt} {nm}"
        phones = [p for p in (norm_phone(mob), norm_phone(home), norm_phone(work)) if p]
        try:
            terms_n = int(float(str(terms or "0").strip() or 0))
        except ValueError:
            terms_n = 0
        is_account = ("account" in str(acct or "").lower()) or terms_n > 0
        notes = []
        for src, lbl in ((remarks, "Remarks"), (other, "Other")):
            if txt(src):
                notes.append({"d": iso(since) or "2004-01-01", "t": f"{lbl} (GB Pro): {txt(src)}"})
        rows[int(ref)] = {
            "ref": int(ref),
            "name": full,
            "surname": surname(nm),
            "title": tt,
            "contact": txt(contact),
            "addr": ", ".join(x for x in (txt(a1), txt(a2), txt(town), txt(county), txt(pc)) if x),
            "postcode": txt(pc),
            "phone": fmt_phone(mob) or fmt_phone(home) or fmt_phone(work),
            "mobile": fmt_phone(mob),
            "home": fmt_phone(home),
            "work": fmt_phone(work),
            "phones": sorted(set(phones)),
            "email": txt(email) if "@" in txt(email) else "",
            "since": iso(since),
            "account": "Account" if is_account else "Private",
            "terms": terms_n,
            "credit": pounds(credit),
            "rate": pounds(rate),
            "discount": float(disc or 0),
            "prefs": {"rem": 1 if motrem else 0, "stmt": 1 if stmts else 0, "mail": 1 if mail else 0},
            "heard": txt(heard),
            "accRef": txt(export),
            "invAddr": ", ".join(x for x in (txt(inv1), txt(inv2), txt(invt), txt(invc), txt(invpc)) if x),
            "notes": notes,
            "folded": [],
        }
    return rows


def merge_customers(cust):
    """Union-find on (phone, surname).  Returns (alias map ref->kept ref, merge log, review list)."""
    parent = {r: r for r in cust}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            lo, hi = min(ra, rb), max(ra, rb)
            parent[hi] = lo

    by_key = defaultdict(list)
    by_phone = defaultdict(set)
    for r, c in cust.items():
        for p in c["phones"]:
            by_phone[p].add(r)
            if c["surname"]:
                by_key[(p, c["surname"])].append(r)
    for key, refs in by_key.items():
        for other in refs[1:]:
            union(refs[0], other)

    alias = {r: find(r) for r in cust}
    groups = defaultdict(list)
    for r, k in alias.items():
        if r != k:
            groups[k].append(r)
    log = []
    for keep, folded in sorted(groups.items()):
        cust[keep]["folded"] = sorted(folded)
        for f in folded:
            fc = cust[f]
            # keep anything the folded record had that the kept one lacks
            for fld in ("email", "addr", "postcode", "mobile", "home", "work", "phone", "contact", "heard", "accRef", "invAddr"):
                if not cust[keep][fld] and fc[fld]:
                    cust[keep][fld] = fc[fld]
            cust[keep]["phones"] = sorted(set(cust[keep]["phones"]) | set(fc["phones"]))
            cust[keep]["notes"] += fc["notes"]
            if fc["since"] and (not cust[keep]["since"] or fc["since"] < cust[keep]["since"]):
                cust[keep]["since"] = fc["since"]
        log.append({"keep": keep, "name": cust[keep]["name"], "folded": sorted(folded),
                    "foldedNames": [cust[f]["name"] for f in sorted(folded)],
                    "surname": cust[keep]["surname"], "phones": cust[keep]["phones"]})
    review = []
    for p, refs in sorted(by_phone.items()):
        kept = sorted({alias[r] for r in refs})
        if len(kept) > 1:
            review.append({"phone": p, "accounts": [{"ref": k, "name": cust[k]["name"], "surname": cust[k]["surname"]} for k in kept]})
    return alias, log, review


# ---------- vehicles -------------------------------------------------------
def build_vehicles(alias):
    t = load("CarDetails")
    out = {}  # reg -> record (one per reg; previous owners folded into 'prev')
    for (ref, reg, make, model, year, mot, vin, chassis, eng, colour, tyre, esize, fuel, other) in cols(
            t, "CustomerRefNo", "CarRegNo", "Make", "Model", "YearofManafacture", "MOT ExpiryDate",
            "VIN", "Chassisnumber", "Enginenumber", "Colour", "TyreSize", "Enginesize", "FuelType", "Other"):
        r = clean_reg(reg)
        if not r or JUNK_REG.search(r) or ref is None:
            continue
        cust = alias.get(int(ref), int(ref))
        tyre_s = txt(tyre)
        if re.fullmatch(r"Front:\s*Rear:", tyre_s):
            tyre_s = ""
        fuel_s = txt(fuel)
        if not re.match(r"^(Diesel|Petrol|Electric|Hybrid|LPG)", fuel_s):
            fuel_s = ""
        rec = {
            "reg": r,
            "cust": cust,
            "make": txt(make),
            "model": txt(model),
            "year": int(year) if year and 1900 < int(year) < 2100 else None,
            "mot": iso(mot),
            "vin": txt(vin) if len(txt(vin)) >= 11 else "",
            "engine": txt(eng) if txt(eng) not in ("", ".", "0") and "USE" not in txt(eng).upper() else "",
            "engineSize": txt(esize) if re.fullmatch(r"\d{3,5}", txt(esize)) else "",
            "colour": txt(colour),
            "tyre": tyre_s,
            "fuel": fuel_s,
            "notes": [txt(other)] if txt(other) else [],
            "prev": [],
        }
        if r in out:
            # same reg on two accounts: keep the higher ref (newer account) as current owner
            old = out[r]
            keep, prev = (rec, old) if rec["cust"] >= old["cust"] else (old, rec)
            if prev["cust"] != keep["cust"]:
                keep["prev"].append({"cust": prev["cust"]})
            for f in ("make", "model", "year", "mot", "vin", "engine", "engineSize", "colour", "tyre", "fuel"):
                if not keep[f] and prev[f]:
                    keep[f] = prev[f]
            keep["notes"] += prev["notes"]
            out[r] = keep
        else:
            out[r] = rec
    return out


# ---------- invoices, lines, payments -------------------------------------
PAY_METHOD = {
    "visa debit": "Card", "visa": "Card", "master card": "Card", "credit card": "Card", "amex": "Card",
    "payment sense": "Card", "bacs payment": "Bank transfer", "bacs": "Bank transfer",
    "cash": "Cash", "cheque": "Cheque", "setup entry": "Opening balance", "setup": "Opening balance",
}


def build_invoices(alias, vehicles):
    inv = load("Invoice")
    ps = load("ProductsSold")
    pay = load("Payments")

    lines_by_inv = defaultdict(list)
    for (ino, name, q, price, total, disc, sold, ref) in cols(
            ps, "SoldtoInvoiceNo", "ProductInvName", "Quantitysold", "SoldPrice", "totalprice",
            "Discount", "DateSold", "UniqueSaleRefNo"):
        if not ino:
            continue
        qty = float(q or 0)
        if qty > 100000 and qty % 10000 == 0:
            qty = qty / 10000.0   # the odd scaled quantity
        tot = pounds(total)
        unit = round(tot / qty, 4) if qty else pounds(price)
        lines_by_inv[int(ino)].append({
            "id": int(ref), "desc": txt(name) or "Part", "qty": qty if qty else 1.0,
            "price": unit, "total": tot, "discount": pounds(disc),
        })

    pays_by_inv = defaultdict(list)
    unlinked = []
    payments = []
    for (pno, cref, ino, d, amt, typ, com) in cols(
            pay, "PaymentInRefNo", "CustomerRefNo", "PaytoInvNo", "DateOfPayment", "AmountOfPayment",
            "TypeOfPayment", "Comments"):
        a = pounds(amt)
        rec = {"id": int(pno), "cust": alias.get(int(cref), int(cref)) if cref is not None else None,
               "inv": int(ino) if ino else None, "date": iso(d), "amount": a,
               "method": PAY_METHOD.get(str(typ or "").strip().lower(), txt(typ) or "Other"),
               "methodRaw": txt(typ), "ref": txt(com)}
        payments.append(rec)
        if rec["inv"]:
            pays_by_inv[rec["inv"]].append(rec)
        else:
            unlinked.append(rec)

    out = {}
    cash_regs = 0
    for (no, cref, reg, labour, parts, outside, others, lub, recov, motfee, motpass, date, total,
         sub, vat, vatpc, paid, miles, work, advise, mech, jobref, payby, hrs, rate, hold, holdwhy,
         memo, nextsvc, svcmiles) in cols(
            inv, "InvoiceNo", "CustomerRefNo", "CarRegno", "Labour", "Parts", "Outside", "Others",
            "Lubricants", "RecoveryCosts", "MOTFee", "MOTPass", "Date", "Total", "Sub total",
            "VAT Amount", "VATPercentage", "Paid", "Miles Now", "WorkDone", "Advise", "Mechanic Name",
            "Jobrefno", "Pay by date", "Total Hrs", "Hourlyrate", "InvHold", "HoldReason", "Memo",
            "Next Service reminder", "Service at miles"):
        if no is None:
            continue
        no = int(no)
        r = clean_reg(reg)
        cash = bool(JUNK_REG.search(r)) or r not in vehicles
        if cash and JUNK_REG.search(r):
            cash_regs += 1
        d = iso(date)
        due = iso(payby) or d
        lines = lines_by_inv.get(no, [])
        lab = pounds(labour)
        hrs_f = float(hrs or 0)
        work_s = txt(work)
        adv = lines_of(advise)
        plist = pays_by_inv.get(no, [])
        paid_amt = round(sum(p["amount"] for p in plist), 2)
        tot = pounds(total)
        if paid:
            status = "paid"
        elif hold:
            status = "hold"
        else:
            status = "owed"
        title = work_s
        if not title:
            title = "MOT" if pounds(motfee) else ("Parts" if lines else "Invoice")
        title = re.split(r"(?<=[.!?])\s", title)[0]
        if len(title) > 70:
            title = title[:67].rsplit(" ", 1)[0] + "…"
        out[no] = {
            "no": no,
            "cust": alias.get(int(cref), int(cref)),
            "reg": "" if JUNK_REG.search(r) else r,
            "cash": cash,
            "date": d,
            "due": due,
            "title": title,
            "work": work_s,
            "advise": adv,
            "memo": txt(memo),
            "mechanic": txt(mech),
            "job": int(jobref) if jobref else None,
            "miles": int(miles) if miles else 0,
            "status": status,
            "hold": txt(holdwhy),
            "labour": lab,
            "hours": hrs_f,
            "rate": pounds(rate),
            "parts": pounds(parts),
            "outside": pounds(outside),
            "others": pounds(others),
            "lubricants": pounds(lub),
            "recovery": pounds(recov),
            "motFee": pounds(motfee),
            "motPass": bool(motpass),
            "subtotal": pounds(sub),
            "vat": pounds(vat),
            "vatRate": float(vatpc or 0),
            "total": tot,
            "paid": tot if paid else min(paid_amt, tot),
            "payments": [{"id": p["id"], "date": p["date"], "amount": p["amount"], "method": p["method"], "ref": p["ref"]} for p in plist],
            "lines": lines,
            "nextService": iso(nextsvc),
            "serviceAtMiles": int(svcmiles) if svcmiles else 0,
        }

    # second pass: payments that were never linked to an invoice (mostly pre-2015):
    # match to the same customer's invoice of the same amount within 60 days, once.
    by_cust = defaultdict(list)
    for i in out.values():
        by_cust[i["cust"]].append(i)
    matched = 0
    for p in unlinked:
        if not p["cust"] or not p["date"] or p["amount"] <= 0:
            continue
        cands = [i for i in by_cust.get(p["cust"], []) if abs(i["total"] - p["amount"]) < 0.005
                 and not i["payments"] and i["date"] and abs(_days(i["date"], p["date"])) <= 60]
        if cands:
            i = min(cands, key=lambda x: abs(_days(x["date"], p["date"])))
            i["payments"].append({"id": p["id"], "date": p["date"], "amount": p["amount"], "method": p["method"], "ref": p["ref"]})
            p["inv"] = i["no"]
            p["matched"] = "by amount and date"
            matched += 1
    return out, payments, {"unlinked": len(unlinked), "matchedByAmount": matched, "cashRegs": cash_regs}


def _days(a, b):
    import datetime as dt
    try:
        return (dt.date.fromisoformat(a) - dt.date.fromisoformat(b)).days
    except ValueError:
        return 9999


# ---------- estimates -> quotes -------------------------------------------
def build_quotes(alias, vehicles, invoices):
    est = load("Estimate")
    ep = load("EstimateParts")
    ew = load("EstimateWork")
    parts = defaultdict(list)
    for (eno, name, q, price, tot) in cols(ep, "ESTno", "EstimateParts", "ESTQan", "ESTPrice", "ESTLinetotal"):
        if eno:
            qty = float(q or 0) or 1.0
            parts[int(eno)].append({"desc": txt(name) or "Part", "qty": qty, "price": pounds(price), "total": pounds(tot)})
    work = defaultdict(list)
    for (eno, hrs, des, fixedyn, fixed, who) in cols(ew, "EstRefNo", "ESTHrs", "EstimateDes", "EstJobLineFixedPriceYN", "EstJobLineFixedPrice", "EstWrkPerson"):
        if eno:
            work[int(eno)].append({"desc": txt(des), "hours": float(hrs or 0), "fixed": pounds(fixed) if fixedyn else None})
    inv_by_reg = defaultdict(list)
    for i in invoices.values():
        if i["reg"]:
            inv_by_reg[i["reg"]].append(i)
    out = {}
    for (no, cref, d, valid, total, lab, prt, st, reg, make, model, cname) in cols(
            est, "EstimateRefNo", "CustomerRefNo", "EstimateDate", "EstimateValidUntil", "EstimateTotal",
            "Estimatelabour", "EstimateParts", "EstimateStatus", "EVehicleReg", "Make", "Model", "CustomerName"):
        if no is None:
            continue
        no = int(no)
        r = clean_reg(reg)
        if JUNK_REG.search(r):
            r = ""
        di = iso(d)
        # an invoice for the same vehicle within 120 days after the estimate = accepted
        became = None
        if r and di:
            later = [i for i in inv_by_reg.get(r, []) if i["date"] and 0 <= _days(i["date"], di) <= 120]
            if later:
                became = min(later, key=lambda i: i["date"])["no"]
        code = int(float(st or 0))
        if became:
            status = "accepted"
        elif code == 4:
            status = "declined"
        elif iso(valid) and iso(valid) < "2026-11-11":
            status = "expired"
        elif code == 0:
            status = "draft"
        else:
            status = "sent"
        w = work.get(no, [])
        title = next((x["desc"] for x in w if x["desc"]), "") or next((x["desc"] for x in parts.get(no, [])), "") or "Estimate"
        title = re.split(r"(?<=[.!?])\s", title)[0]
        if len(title) > 70:
            title = title[:67].rsplit(" ", 1)[0] + "…"
        out[no] = {
            "no": no, "cust": alias.get(int(cref), int(cref)), "reg": r, "date": di, "valid": iso(valid),
            "statusCode": code, "status": status, "becameInvoice": became, "title": title,
            "make": txt(make), "model": txt(model),
            "labour": pounds(lab), "partsTotal": pounds(prt), "total": pounds(total),
            "work": w, "parts": parts.get(no, []),
        }
    return out


# ---------- jobsheets -----------------------------------------------------
def build_jobs(alias, vehicles, invoices):
    js = load("Jobsheet")
    inv_by_job = {i["job"]: i for i in invoices.values() if i["job"]}
    out = {}
    for (no, d, reg, desc, done, adv, probs, mech, complete, hrs, hrs_charge) in cols(
            js, "JobRefNo", "Jobstartdate", "JobVehicleRegno", "JobDescription", "JobWorkdone", "JobAdvise",
            "JobProplems", "JobMechanic", "Jobcomplete", "JobhoursAcutual", "jobhourstocharge"):
        if no is None:
            continue
        no = int(no)
        r = clean_reg(reg)
        if JUNK_REG.search(r):
            r = ""
        inv = inv_by_job.get(no)
        cust = inv["cust"] if inv else (vehicles[r]["cust"] if r in vehicles else None)
        out[no] = {
            "no": no, "date": iso(d), "reg": r, "cust": cust, "description": txt(desc), "workDone": txt(done),
            "advise": lines_of(adv), "problems": txt(probs), "mechanic": txt(mech), "complete": bool(complete),
            "hours": float(hrs or 0), "hoursToCharge": float(hrs_charge or 0),
            "invoice": inv["no"] if inv else None,
        }
    return out


# ---------- main ----------------------------------------------------------
def dump(name, obj):
    p = os.path.join(OUT, name)
    with open(p, "w") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    return os.path.getsize(p)


def main():
    t0 = time.time()
    os.makedirs(OUT, exist_ok=True)
    cust = build_customers()
    alias, log, review = merge_customers(cust)
    kept = {r: c for r, c in cust.items() if alias[r] == r}
    vehicles = build_vehicles(alias)
    invoices, payments, pstats = build_invoices(alias, vehicles)
    # mileage on the vehicle = latest invoice mileage for that reg
    latest = {}
    for i in invoices.values():
        if i["reg"] and i["miles"] and (i["reg"] not in latest or i["date"] > latest[i["reg"]][0]):
            latest[i["reg"]] = (i["date"], i["miles"])
    for r, v in vehicles.items():
        v["miles"] = latest.get(r, ("", 0))[1]
    quotes = build_quotes(alias, vehicles, invoices)
    jobs = build_jobs(alias, vehicles, invoices)

    sizes = {
        "customers.json": dump("customers.json", sorted(kept.values(), key=lambda c: c["ref"])),
        "vehicles.json": dump("vehicles.json", sorted(vehicles.values(), key=lambda v: v["reg"])),
        "invoices.json": dump("invoices.json", [invoices[k] for k in sorted(invoices)]),
        "quotes.json": dump("quotes.json", [quotes[k] for k in sorted(quotes)]),
        "payments.json": dump("payments.json", payments),
        "jobsheets.json": dump("jobsheets.json", [jobs[k] for k in sorted(jobs)]),
        "merge-log.json": dump("merge-log.json", log),
        "review-list.json": dump("review-list.json", review),
    }
    summary = {
        "importedAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "customersInGBPro": len(cust),
        "customersAfterMerge": len(kept),
        "mergeGroups": len(log),
        "accountsFolded": sum(len(g["folded"]) for g in log),
        "reviewGroups": len(review),
        "vehicles": len(vehicles),
        "invoices": len(invoices),
        "invoiceLines": sum(len(i["lines"]) for i in invoices.values()),
        "invoicesOwed": sum(1 for i in invoices.values() if i["status"] == "owed"),
        "owedTotal": round(sum(i["total"] - i["paid"] for i in invoices.values() if i["status"] == "owed"), 2),
        "payments": len(payments),
        "paymentsUnlinked": pstats["unlinked"],
        "paymentsMatchedByAmount": pstats["matchedByAmount"],
        "quotes": len(quotes),
        "jobsheets": len(jobs),
        "invoiceDateRange": [min(i["date"] for i in invoices.values() if i["date"]), max(i["date"] for i in invoices.values() if i["date"])],
        "bytes": sizes,
        "seconds": round(time.time() - t0, 1),
    }
    dump("summary.json", summary)
    for k, v in summary.items():
        if k != "bytes":
            print(f"{k:26} {v}")
    for k, v in sizes.items():
        print(f"  {k:22} {v/1e6:6.1f} MB")


if __name__ == "__main__":
    main()
