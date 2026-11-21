"""wentsdiary - read-only mirror of the Wents Diary (wentsdb.azurewebsites.net).

Standard library only; works under `python3 -I`.  Contains no data.

What lives where (all git-ignored, under private/wentsdiary/, mode 700):
  token.json          the sign-in token (mode 600).  Written by login(); only
                      ever sent back to wentsdb.azurewebsites.net.
  days/<date>.json    one cached day sheet per date, exactly as the API sent
                      it, plus when it was fetched.

The API calls this module may make, and nothing else (ALLOWED below):
  POST /api/login                                 sign in (email+password from
                                                  Jenson's browser via serve.py)
  POST /api/refresh                               swap the refresh token for a
                                                  new access token
  GET  /api/Account/CurrentUser                   "am I signed in?"
  POST /api/WorkshopBookings/GetWorkshopDaySheet  one day's bookings/notes/slots
All read-only apart from the sign-in itself.  One request per day sheet with a
pause between requests.
"""
import datetime as _dt
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

try:
    from zoneinfo import ZoneInfo
    LONDON = ZoneInfo("Europe/London")
except Exception:  # pragma: no cover - zoneinfo missing; fall back to UTC
    LONDON = _dt.timezone.utc

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PRIV = os.path.join(ROOT, "private", "wentsdiary")
TOKEN = os.path.join(PRIV, "token.json")
DAYS = os.path.join(PRIV, "days")
BASE = "https://wentsdb.azurewebsites.net"
HOST = "wentsdb.azurewebsites.net"
ALLOWED = {
    ("POST", "/api/login"),
    ("POST", "/api/refresh"),
    ("GET", "/api/Account/CurrentUser"),
    ("POST", "/api/WorkshopBookings/GetWorkshopDaySheet"),
}
PAUSE = 0.6          # seconds between day-sheet requests
TIMEOUT = 30
BACK, AHEAD = 14, 90  # default window in days

# progress of the current / last fetch, read by serve.py's /wd/status
STATE = {"running": False, "done": 0, "total": 0, "error": "", "startedAt": "", "finishedAt": "", "ok": 0}
_lock = threading.Lock()


# ---------------------------------------------------------------- storage
def _ensure_dirs():
    for p in (PRIV, DAYS):
        if not os.path.isdir(p):
            os.makedirs(p, mode=0o700)
    try:
        os.chmod(PRIV, 0o700)
    except OSError:
        pass


def _write_private(path, obj):
    _ensure_dirs()
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _now():
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------- HTTP
class ApiError(Exception):
    def __init__(self, status, msg=""):
        super().__init__("HTTP %s%s" % (status, (" " + msg) if msg else ""))
        self.status = status


def _request(method, path, body=None, token=None, query=None):
    """One request to the diary API.  Only the (method, path) pairs in ALLOWED
    are ever sent.  Returns the parsed JSON body (None when empty)."""
    if (method, path) not in ALLOWED:
        raise ValueError("refusing to call %s %s: not in the read-only allow list" % (method, path))
    url = BASE + path + ("?" + urllib.parse.urlencode(query) if query else "")
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        raise ApiError(e.code)
    except (urllib.error.URLError, OSError) as e:
        raise ApiError(0, "network: %s" % getattr(e, "reason", e))
    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except ValueError:
        raise ApiError(200, "response was not JSON")


# ---------------------------------------------------------------- sign-in / token
def login(email, password):
    """Sign in with the credentials Jenson typed into the local form.  Keeps
    only the returned tokens (token.json, mode 600).  Returns (ok, message);
    the message never contains the credentials or the token."""
    if not email or not password:
        return False, "Email and password are both needed."
    try:
        r = _request("POST", "/api/login", {"email": email, "password": password})
    except ApiError as e:
        if e.status in (400, 401):
            return False, "Sign-in refused by the Wents Diary (wrong email or password)."
        return False, "Could not reach the Wents Diary (%s)." % e
    if not isinstance(r, dict) or not r.get("accessToken"):
        return False, "The Wents Diary did not return a token."
    _save_token(r)
    return True, "Signed in."


def _save_token(r):
    expires = int(r.get("expiresIn") or 3600)
    _write_private(TOKEN, {
        "accessToken": r["accessToken"],
        "refreshToken": r.get("refreshToken", ""),
        "expiresAt": time.time() + expires - 60,
        "savedAt": _now(),
    })


def forget_token():
    try:
        os.remove(TOKEN)
    except OSError:
        pass


def token():
    """The current access token, refreshed through /api/refresh when it has
    expired.  None when not signed in."""
    t = _read_json(TOKEN)
    if not t or not t.get("accessToken"):
        return None
    if time.time() < float(t.get("expiresAt") or 0):
        return t["accessToken"]
    if not t.get("refreshToken"):
        return None
    try:
        r = _request("POST", "/api/refresh", {"refreshToken": t["refreshToken"]})
    except ApiError:
        return None
    if not isinstance(r, dict) or not r.get("accessToken"):
        return None
    _save_token(r)
    return r["accessToken"]


def current_user():
    """(signed_in, display) - display is the account's email or ''."""
    tk = token()
    if not tk:
        return False, ""
    try:
        r = _request("GET", "/api/Account/CurrentUser", token=tk)
    except ApiError:
        return False, ""
    if isinstance(r, dict) and r.get("email"):
        return True, str(r["email"])
    return False, ""


# ---------------------------------------------------------------- fetching
def day_param(d):
    """The workshopDate the Angular app sends: local (London) midnight as an
    ISO instant, e.g. 2026-11-21T00:00:00.000Z in winter."""
    local = _dt.datetime(d.year, d.month, d.day, tzinfo=LONDON)
    u = local.astimezone(_dt.timezone.utc)
    return u.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def fetch_day(d, tk=None):
    """Fetch one day sheet and cache it.  Returns the sheet (dict)."""
    tk = tk or token()
    if not tk:
        raise ApiError(401, "not signed in")
    sheet = _request("POST", "/api/WorkshopBookings/GetWorkshopDaySheet", {}, token=tk,
                     query={"workshopDate": day_param(d)})
    _write_private(os.path.join(DAYS, d.isoformat() + ".json"),
                   {"date": d.isoformat(), "fetchedAt": _now(), "sheet": sheet})
    return sheet


def window_dates(back=BACK, ahead=AHEAD, today=None):
    today = today or _dt.datetime.now(LONDON).date()
    # The garage is closed at weekends, so only Monday to Friday are fetched.
    return [d for d in (today + _dt.timedelta(days=i) for i in range(-back, ahead + 1)) if d.weekday() < 5]


def fetch_window(back=BACK, ahead=AHEAD, progress=None):
    """Fetch every day in the window, one request at a time with PAUSE between
    them.  Updates STATE as it goes.  Returns (fetched, error_message)."""
    with _lock:
        if STATE["running"]:
            return 0, "already running"
        STATE.update(running=True, done=0, ok=0, error="", startedAt=_now(), finishedAt="")
    dates = window_dates(back, ahead)
    STATE["total"] = len(dates)
    err = ""
    try:
        tk = token()
        if not tk:
            err = "not signed in"
            return 0, err
        for i, d in enumerate(dates):
            try:
                fetch_day(d, tk)
                STATE["ok"] += 1
            except ApiError as e:
                if e.status == 401:
                    tk = token()  # try one refresh, then give up
                    if not tk:
                        err = "sign-in expired"
                        break
                    try:
                        fetch_day(d, tk)
                        STATE["ok"] += 1
                    except ApiError as e2:
                        err = "day %s: %s" % (d.isoformat(), e2)
                        break
                else:
                    err = "day %s: %s" % (d.isoformat(), e)
                    # keep going for other days unless the network is gone
                    if e.status == 0:
                        break
            STATE["done"] = i + 1
            if progress:
                progress(i + 1, len(dates))
            if i + 1 < len(dates):
                time.sleep(PAUSE)
        return STATE["ok"], err
    finally:
        STATE.update(running=False, error=err, finishedAt=_now())


def fetch_in_background(back=BACK, ahead=AHEAD):
    """Start fetch_window on a thread (no-op when one is running)."""
    if STATE["running"]:
        return False
    t = threading.Thread(target=fetch_window, args=(back, ahead), daemon=True)
    t.start()
    return True


def cached_days():
    if not os.path.isdir(DAYS):
        return []
    return sorted(f[:-5] for f in os.listdir(DAYS) if re.fullmatch(r"\d{4}-\d\d-\d\d\.json", f))


# ---------------------------------------------------------------- mapping to the mock
def _g(o, *names, default=""):
    """First present, non-empty value among the given keys (case-insensitive)."""
    if not isinstance(o, dict):
        return default
    low = {k.lower(): v for k, v in o.items()}
    for n in names:
        v = low.get(n.lower())
        if v not in (None, ""):
            return v
    return default


def _text(s):
    """Plain text for the mock's templates: drop tags, keep &."""
    s = str(s or "").strip()
    return s.replace("<", "‹").replace(">", "›")


def _phone(s):
    return re.sub(r"[^0-9 +()\-]", "", str(s or "")).strip()


def _hhmm(v):
    """'08:00:00' / '0800' / ISO datetime -> '08:00'."""
    if v in (None, ""):
        return ""
    s = str(v)
    if "T" in s:
        s = s.split("T", 1)[1]
    m = re.match(r"^(\d{1,2}):?(\d{2})", s)
    if not m:
        return ""
    return "%02d:%s" % (int(m.group(1)), m.group(2))


def _truthy(v):
    return v is True or v == 1 or (isinstance(v, str) and v.lower() in ("true", "1", "yes"))


def map_booking(b, kind, date):
    vr = _g(b, "vehicleRecord", default={}) or {}
    reg = str(_g(b, "vehicleRegistration") or _g(vr, "vehicleRegistration")).upper().strip()
    make = " ".join(x for x in [str(_g(b, "vehicleMake") or _g(vr, "vehicleMake")),
                                str(_g(b, "vehicleModel") or _g(vr, "vehicleModel"))] if x).strip()
    first = _g(b, "customerFirstName") or _g(vr, "customerFirstName")
    sur = _g(b, "customerSurname") or _g(vr, "customerSurname")
    name = _g(b, "customerName") or " ".join(str(x) for x in [first, sur] if x).strip()
    ph = _phone(_g(b, "customerContactNumber") or _g(vr, "customerContactNumber"))
    items = _g(b, "serviceItems", default=[])
    if isinstance(items, list):
        items = ", ".join(str(_g(x, "name", "serviceItemName", "description") or x) for x in items if x)
    job = str(_g(b, "serviceItemName", "serviceItem", "workDescription", "description") or items or "")
    if isinstance(_g(b, "serviceItem", default=None), dict):
        job = str(_g(_g(b, "serviceItem"), "name", "serviceItemName") or job)
    notes = str(_g(b, "notes", "note", "comments") or "")
    is_mot = _truthy(_g(b, "isMot", default=False))
    if _truthy(_g(b, "isAdditionalWork", default=False)):
        kind = "xtra"  # the diary's "additional work" flag -> the mock's Extras section
    if kind == "svc" and is_mot:
        job = (job + " · MOT") if job else "MOT"
    if _truthy(_g(b, "cancellationRequested", default=False)):
        notes = (notes + " · " if notes else "") + "Wants an earlier slot"
    out = {
        "id": "wd" + str(_g(b, "id") or (date + "-" + kind + "-" + str(_g(b, "rowOrder") or 0))),
        "k": kind,
        "reg": _text(reg) or "—",
        "make": _text(make),
        "name": _text(name),
        "ph": ph,
        "who": "wd",
    }
    t = _hhmm(_g(b, "motBookingTime", "bookingTime", "time"))
    if kind == "mot":
        out["t"] = t or "—"
    elif t:
        out["t"] = t
    if job:
        out["job"] = _text(job)
    if notes:
        out["nt"] = _text(notes)
    if _truthy(_g(b, "partsIn", default=False)):
        out["parts"] = "in"
    elif _truthy(_g(b, "partsOrdered", default=False)):
        out["parts"] = "ordered"
    if _truthy(_g(b, "loanCar", default=False)):
        out["loan"] = "car"
    elif _truthy(_g(b, "loanVan", default=False)):
        out["loan"] = "van"
    elif _truthy(_g(b, "loanSmallVan", default=False)):
        out["loan"] = "svan"
    if _truthy(_g(b, "motConfirmed", default=False)):
        out["cf"] = {"st": "ok"}
    elif _truthy(_g(b, "motMessaged", default=False)):
        out["cf"] = {"st": "msg"}
    st = str(_g(b, "status") or "").lower()
    if st in ("done", "completed", "complete") or _truthy(_g(b, "isDone", "completed", "done", default=False)):
        out["st"] = "done"
    ro = _g(b, "rowOrder", default=None)
    if ro not in (None, ""):
        out["ro"] = ro
    return out


def map_sheet(date, sheet):
    """One cached day sheet -> (bookings, notes, slots)."""
    sheet = sheet or {}
    bk = []
    for b in _g(sheet, "motBookings", default=[]) or []:
        bk.append(map_booking(b, "mot", date))
    svc = [map_booking(b, "svc", date) for b in (_g(sheet, "serviceBookings", default=[]) or [])]
    svc.sort(key=lambda x: (x.get("ro") is None, x.get("ro") if isinstance(x.get("ro"), (int, float)) else 0))
    bk.extend(svc)
    for b in bk:
        b.pop("ro", None)
    notes = []
    for n in _g(sheet, "dayNotes", default=[]) or []:
        t = _text(_g(n, "noteText", "text", "note", "description") if isinstance(n, dict) else n)
        if t:
            notes.append(t)
    slots = []
    for s in _g(sheet, "motSlots", default=[]) or []:
        if isinstance(s, dict):
            typ = str(_g(s, "slotType", default="Mot"))
            if typ not in ("Mot", "0", "mot") or (_g(s, "enabled", default=True) is False):
                continue
            t = _hhmm(_g(s, "slotTime", "time"))
        else:
            t = _hhmm(s)
        if t:
            slots.append(t)
    for b in bk:  # an MOT booked outside the slot list still needs a row
        if b["k"] == "mot" and b.get("t") and b["t"] != "—" and b["t"] not in slots:
            slots.append(b["t"])
    slots = sorted(set(slots))
    return bk, notes, slots


def build():
    """Everything the local build needs: {BK, NOTES, SLOTS, meta}."""
    BK, NOTES, SLOTS = {}, {}, {}
    fetched = []
    n_mot = n_svc = n_notes = 0
    for d in cached_days():
        if _dt.date.fromisoformat(d).weekday() > 4:
            continue  # closed at weekends; older caches may still hold them
        rec = _read_json(os.path.join(DAYS, d + ".json")) or {}
        bk, notes, slots = map_sheet(d, rec.get("sheet"))
        if bk:
            BK[d] = bk
        if notes:
            NOTES[d] = notes
        if slots:
            SLOTS[d] = slots
        n_mot += sum(1 for b in bk if b["k"] == "mot")
        n_svc += sum(1 for b in bk if b["k"] == "svc")
        n_notes += len(notes)
        if rec.get("fetchedAt"):
            fetched.append(rec["fetchedAt"])
    days = cached_days()
    today = _dt.datetime.now(LONDON).date().isoformat()
    return {
        "BK": BK, "NOTES": NOTES, "SLOTS": SLOTS,
        "meta": {"days": len(days), "from": days[0] if days else "", "to": days[-1] if days else "",
                 "today": today, "fetchedAt": max(fetched) if fetched else "",
                 "mot": n_mot, "svc": n_svc, "notes": n_notes, "daysWithBookings": len(BK)},
    }


def status():
    """For /wd/status: no token, no data, just counts and the fetch state."""
    days = cached_days()
    return {"days": len(days), "from": days[0] if days else "", "to": days[-1] if days else "",
            "hasToken": os.path.isfile(TOKEN), "fetch": dict(STATE)}
