#!/usr/bin/env python3
"""Step 1 of the GarageBase import: read tables out of the Access back-end and cache
them as pickles under private/local-data/raw/ so later steps are fast.
Usage: .venv/bin/python -I tools/garagebase/extract.py [table ...]
Everything written stays under private/ (git-ignored)."""
import os, sys, pickle, time, warnings
warnings.filterwarnings("ignore")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB = os.path.join(ROOT, "private", "garagebase", "GBProV3_be.accdb")
RAW = os.path.join(ROOT, "private", "local-data", "raw")
TABLES = ["CustomerDetails", "CarDetails", "Invoice", "ProductsSold", "Payments",
          "Estimate", "EstimateParts", "EstimateWork", "Jobsheet", "Mechanic",
          "TypeofPayment", "Company Details"]

def load(name, db=None):
    """Return {column: [values]} for a table, from the cache if present."""
    p = os.path.join(RAW, name.replace(" ", "_") + ".pkl")
    if os.path.exists(p):
        with open(p, "rb") as f:
            return pickle.load(f)
    from access_parser import AccessParser
    db = db or AccessParser(DB)
    t0 = time.time()
    data = db.parse_table(name)
    os.makedirs(RAW, exist_ok=True)
    with open(p, "wb") as f:
        pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
    n = len(next(iter(data.values()))) if data else 0
    print(f"  {name}: {n} rows, {len(data)} cols, {time.time()-t0:.0f}s", file=sys.stderr, flush=True)
    return data

if __name__ == "__main__":
    from access_parser import AccessParser
    db = AccessParser(DB)
    for t in (sys.argv[1:] or TABLES):
        load(t, db)
    print("extracted", file=sys.stderr)
