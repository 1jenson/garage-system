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
            tag = ('<script src="/local-data.js?years=%s"></script>\n<script src="/local-apply.js"></script>\n</body>'
                   % ("all" if years is None else years))
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
        return super().do_GET()


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
