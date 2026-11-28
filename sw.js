// Izden service worker: cache-first for the whole app (one download, then works in airplane mode).
// Bump CACHE version on every release so phones pick up new files.
const CACHE = 'izden-49a3a47a22';
const ASSETS = [
  './',
  'index.html',
  'manifest.webmanifest',
  'css/style.css',
  'js/app.js',
  'js/engine.js',
  'js/i18n.js',
  'js/qr.js',
  'js/text.js',
  'js/dict.js',
  'data/dict.kk.json',
  'data/dict.ru.json',
  'vendor/qrcode.js',
  'vendor/jsQR.js',
  'data/bank.kk.json',
  'data/bank.ru.json',
  'data/math.kk.json',
  'data/math.ru.json',
  'data/bkt_params.json',
  'data/passport.json',
  'data/trap_cards.json',
  'icons/icon.svg',
  'icons/icon-192.png',
  'icons/icon-512.png',
  'icons/icon-maskable-512.png',
];

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(c => c.addAll(ASSETS)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k.startsWith('izden-') && k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  const req = event.request;
  if (req.method !== 'GET' || new URL(req.url).origin !== self.location.origin || new URL(req.url).pathname.startsWith('/api/')) return;
  if (req.mode === 'navigate') {
    event.respondWith(caches.match('index.html').then(r => r || fetch(req)));
    return;
  }
  event.respondWith(
    caches.match(req, { ignoreSearch: true }).then(hit => hit || fetch(req).then(res => {
      if (res.ok) {
        const copy = res.clone();
        caches.open(CACHE).then(c => c.put(req, copy));
      }
      return res;
    }))
  );
});
