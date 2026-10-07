// Service worker for page navigations only.
//
// The page itself always comes from the network; offline.html (the only
// cached file) is shown when that fails. Every other request (PMTiles, GSI
// tiles, unpkg, search JSON) is left alone: PMTiles reads with HTTP Range and
// the Cache API cannot store 206 responses. See README "Installing as an app".
//
// Keep VERSION equal to APP.version in index.html (checked by tools/pwa-test).
const VERSION = '1.1.0';
const PREFIX = 'fukuyama-chiban-';
const CACHE = PREFIX + VERSION;
const OFFLINE_URL = new URL('offline.html', self.location).href;

self.addEventListener('install', event => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE);
    await cache.add(new Request(OFFLINE_URL, { cache: 'reload' }));
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    if (self.registration.navigationPreload) await self.registration.navigationPreload.enable();
    // The origin (<user>.github.io) is shared with other sites, so only our
    // own old caches are removed.
    const keys = await caches.keys();
    await Promise.all(keys.filter(k => k.startsWith(PREFIX) && k !== CACHE).map(k => caches.delete(k)));
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', event => {
  if (event.request.mode !== 'navigate') return;
  event.respondWith((async () => {
    try {
      const preloaded = await event.preloadResponse;
      if (preloaded) return preloaded;
      return await fetch(event.request);
    } catch {
      const offline = await caches.match(OFFLINE_URL, { cacheName: CACHE });
      return offline || Response.error();
    }
  })());
});
