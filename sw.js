// Workshop (Garage System mock) offline support: keeps a copy of the app so it opens with no signal.
// Bump VERSION whenever index.html, makes.js, logos or icons change, so installed copies pick up the update.
const VERSION = 'workshop-v2';
const CORE = [
  './',
  'index.html',
  'makes.js',
  'manifest.webmanifest',
  'icons/apple-touch-icon.png',
  'icons/icon-192.png',
  'icons/icon-512.png',
  'icons/icon-maskable-512.png',
  'icons/favicon-32.png',
  'logos/automotive-electrics.svg',
  'logos/barretts.svg',
  'logos/group-tyres.svg',
  'logos/gsf.svg',
  'logos/haynes.svg',
  'logos/hendy.svg',
  'logos/jayar.svg',
  'logos/napa.svg',
  'logos/page-windscreens.svg',
  'logos/phoenix-stationery.svg',
  'logos/se-car-keys.svg',
  'logos/sparshatts.svg',
  'logos/tps.svg'
];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(VERSION).then((cache) => cache.addAll(CORE)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  // The page itself: network first so updates show straight away, saved copy if offline
  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req)
        .then((res) => { const copy = res.clone(); caches.open(VERSION).then((c) => c.put('index.html', copy)); return res; })
        .catch(() => caches.match('index.html'))
    );
    return;
  }
  // Everything else (scripts, logos, icons, fonts): saved copy first, then the network
  event.respondWith(
    caches.match(req).then((hit) => hit || fetch(req).then((res) => {
      if (res.ok || res.type === 'opaque') { const copy = res.clone(); caches.open(VERSION).then((c) => c.put(req, copy)); }
      return res;
    }))
  );
});
