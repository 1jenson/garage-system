#!/usr/bin/env python3
"""Serve the CURRENT mock (mock/index.html, unmodified on disk) on
http://127.0.0.1:8795/ with Jenson's real GarageBase data loaded into it.

What it does per request:
  /  or /index.html   -> mock/index.html with three things injected at serve time:
                         a <meta> Content-Security-Policy that blocks every non-local
                         load (no fonts, no network), a style that hides the page
                         until the data is in, and two <script> tags right before
                         </body>: /local-data.js (window.__localData = ...) and
                         /local-apply.js (tools/garagebase/apply.js), which swap the
                         demo seed for the real records and re-render.
  /local-data.js      -> built from private/local-data/*.json via adapt.build().
                         ?years=N (default 5) keeps the last N years of invoices
                         as full records; older ones become vehicle history.
                         ?years=all loads everything (slow).
  /sw.js              -> a tiny service worker that unregisters itself, so the
                         mock's offline cache never serves a stale copy here.
  /local-diary.js     -> window.__localDiary = {...}: the cached Wents Diary day
                         sheets (private/wentsdiary/days) mapped by tools/wentsdiary/wd.py.
  /wd/login           -> sign-in form (GET) / proxy to the diary's /api/login (POST).
                         The password goes browser -> this server -> wentsdb only;
                         only the token is kept (private/wentsdiary/token.json, 600).
  /wd/status          -> JSON: cached days, signed in or not, fetch progress.
  /wd/refresh         -> start a background re-fetch of the diary window.
  /?refresh=1         -> same, then serve the page (apply.js polls /wd/status).
  anything else       -> the file from mock/ (makes.js, icons, logos...).

Binds to 127.0.0.1 only.  Sends Cache-Control: no-store.  Never writes anything.
Usage:  tools/garagebase/.venv/bin/python -I tools/garagebase/serve.py [port]
"""
import json
import os
import sys
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adapt  # noqa: E402
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "wentsdiary"))
import wd  # noqa: E402  (read-only Wents Diary mirror: tools/wentsdiary/README.md)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MOCK = os.path.join(ROOT, "mock")
HERE = os.path.dirname(os.path.abspath(__file__))
HOST, PORT = "127.0.0.1", int(sys.argv[1]) if len(sys.argv) > 1 else 8795

CSP = ('<meta http-equiv="Content-Security-Policy" content="default-src \'self\' \'unsafe-inline\' data: blob:; '
       'connect-src \'self\'; img-src \'self\' data: blob:; font-src \'self\' data:; style-src \'self\' \'unsafe-inline\'; '
       'script-src \'self\' \'unsafe-inline\'">\n'
       '<style>html.local-loading body{visibility:hidden}</style>\n'
       '<script>document.documentElement.classList.add("local-loading")</script>\n')
UNREGISTER_SW = ("self.addEventListener('install',()=>self.skipWaiting());"
                 "self.addEventListener('activate',e=>e.waitUntil(self.registration.unregister()"
                 ".then(()=>caches.keys()).then(ks=>Promise.all(ks.map(k=>caches.delete(k))))));")

_cache = {}
_user = {"at": 0.0, "ok": False, "who": ""}

LOGIN_HTML = """<!doctype html><meta charset="utf-8"><title>Wents Diary sign-in (local)</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{font:16px/1.5 system-ui,sans-serif;max-width:420px;margin:48px auto;padding:0 16px;color:#1b2430}
h1{font-size:22px;margin:0 0 6px}p{margin:8px 0;color:#4a5568}label{display:block;margin:14px 0 4px;font-weight:600}
input{width:100%%;box-sizing:border-box;font:inherit;padding:10px 12px;border:1px solid #c8d0da;border-radius:8px}
button{margin-top:18px;font:inherit;font-weight:600;padding:10px 18px;border:0;border-radius:8px;background:#173E70;color:#fff;cursor:pointer}
.err{background:#fde8e8;color:#9b1c1c;padding:10px 12px;border-radius:8px;margin-top:12px}.ok{background:#e6f6ea;color:#1e6b34;padding:10px 12px;border-radius:8px;margin-top:12px}
small{display:block;margin-top:22px;color:#6b7684}</style>
<h1>Sign in to the Wents Diary</h1>
<p>Read-only mirror for the local build. %(state)s</p>
<form method="post" action="/wd/login" autocomplete="on">
<label for="e">Email</label><input id="e" name="email" type="email" autocomplete="username" required autofocus>
<label for="p">Password</label><input id="p" name="password" type="password" autocomplete="current-password" required>
<button type="submit">Sign in and fetch the diary</button></form>
%(msg)s
<small>Your password goes from this browser to 127.0.0.1:%(port)d, which forwards it once to wentsdb.azurewebsites.net and keeps only the returned token (private/wentsdiary/token.json, owner-only). Nothing is ever written back to the diary.</small>
"""


def user_state():
    """Signed-in check, cached for a minute so /wd/status can be polled."""
    if time.time() - _user["at"] > 60:
        ok, who = wd.current_user()
        _user.update(at=time.time(), ok=ok, who=who)
    return _user["ok"], _user["who"]


def local_data_js(years):
    key = "all" if years is None else years
    if key not in _cache:
        t0 = time.time()
        d = adapt.build(years)
        body = ("window.__localData=" + json.dumps(d, ensure_ascii=False, separators=(",", ":")) + ";").encode("utf-8")
        _cache[key] = body
        print("built local-data years=%s: %.1f MB in %.1fs  %s" % (key, len(body) / 1e6, time.time() - t0, json.dumps(d["meta"])), flush=True)
    return _cache[key]


class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=MOCK, **kw)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):
        # keep the terminal quiet apart from errors; never log query strings with data in them
        if args and str(args[1]).startswith(("4", "5")):
            super().log_message(fmt, *args)

    def _send(self, body, ctype):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlsplit(self.path)
        qs = parse_qs(u.query)
        if u.path in ("/", "/index.html"):
            years = adapt.parse_years(qs.get("years", ["5"])[0])
            with open(os.path.join(MOCK, "index.html"), "rb") as f:
                html = f.read().decode("utf-8")
            if qs.get("refresh", ["0"])[0] not in ("0", "", "no") and user_state()[0]:
                wd.fetch_in_background()
            tag = ('<script src="/local-data.js?years=%s"></script>\n<script src="/local-diary.js"></script>\n'
                   '<script src="/local-apply.js"></script>\n</body>' % ("all" if years is None else years))
            if "</body>" not in html or "<head>" not in html:
                self.send_error(500, "mock/index.html has no <head> or </body> to inject into")
                return
            html = html.replace("<head>", "<head>\n" + CSP, 1)
            html = html.replace("</body>", tag, 1)   # first (and only) </body>
            return self._send(html.encode("utf-8"), "text/html; charset=utf-8")
        if u.path == "/local-data.js":
            return self._send(local_data_js(adapt.parse_years(qs.get("years", ["5"])[0])), "application/javascript; charset=utf-8")
        if u.path == "/local-apply.js":
            with open(os.path.join(HERE, "apply.js"), "rb") as f:
                return self._send(f.read(), "application/javascript; charset=utf-8")
        if u.path == "/sw.js":
            return self._send(UNREGISTER_SW.encode(), "application/javascript; charset=utf-8")
        if u.path == "/local-diary.js":
            body = "window.__localDiary=" + json.dumps(wd.build(), ensure_ascii=False, separators=(",", ":")) + ";"
            return self._send(body.encode("utf-8"), "application/javascript; charset=utf-8")
        if u.path == "/wd/diary.json":
            return self._send(json.dumps(wd.build(), ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        if u.path == "/wd/status":
            ok, who = user_state()
            st = wd.status()
            st.update(signedIn=ok, user=who)
            return self._send(json.dumps(st).encode("utf-8"), "application/json; charset=utf-8")
        if u.path == "/wd/refresh":
            ok, _ = user_state()
            started = wd.fetch_in_background() if ok else False
            st = wd.status()
            st.update(signedIn=ok, started=started)
            return self._send(json.dumps(st).encode("utf-8"), "application/json; charset=utf-8")
        if u.path == "/wd/login":
            return self._login_page()
        return super().do_GET()

    def _login_page(self, msg=""):
        ok, who = user_state()
        state = ("Currently signed in as %s; signing in again replaces the token." % who) if ok else "Not signed in."
        html = LOGIN_HTML % {"state": state, "msg": msg, "port": PORT}
        return self._send(html.encode("utf-8"), "text/html; charset=utf-8")

    def do_POST(self):
        u = urlsplit(self.path)
        if u.path != "/wd/login":
            self.send_error(404)
            return
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > 4096:
            self.send_error(400)
            return
        form = parse_qs(self.rfile.read(n).decode("utf-8", "replace"))
        email = (form.get("email") or [""])[0].strip()
        password = (form.get("password") or [""])[0]
        ok, msg = wd.login(email, password)
        del password, form
        _user["at"] = 0.0  # re-check on the next status call
        if ok:
            wd.fetch_in_background()
            self.send_response(303)
            self.send_header("Location", "/?fresh=%d&refresh=1#/diary" % int(time.time()))
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        return self._login_page('<div class="err">%s</div>' % msg)


if __name__ == "__main__":
    if not os.path.isdir(os.path.join(ROOT, "private", "local-data")):
        sys.exit("private/local-data not found: run import.py first")
    local_data_js(5)   # warm the default so the first page load is quick
    srv = ThreadingHTTPServer((HOST, PORT), H)
    print("serving the mock with real data on http://%s:%d/  (Ctrl-C to stop; ?years=all for everything)" % (HOST, PORT), flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
