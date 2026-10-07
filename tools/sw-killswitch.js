// Emergency stop for the service worker. To use it, publish this file as
// sw.js (see README "Stopping the service worker"). Browsers that have the
// old worker pick it up on their next visit; it then
//   - removes this site's caches,
//   - unregisters itself,
//   - reloads the pages it controlled, so they load without a worker.
// index.html keeps registering sw.js, so a fresh visit installs this file
// again and it removes itself again; the page never ends up controlled.
const PREFIX = 'fukuyama-chiban-';

self.addEventListener('install', () => self.skipWaiting());

self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    // The origin is shared with other sites; only our own caches go.
    const keys = await caches.keys();
    await Promise.all(keys.filter(k => k.startsWith(PREFIX)).map(k => caches.delete(k)));
    await self.registration.unregister();
    // Only pages this worker controls; a page that has just registered it is
    // not controlled, so this never loops.
    const pages = await self.clients.matchAll({ type: 'window' });
    await Promise.all(pages.map(c => c.navigate(c.url).catch(() => {})));
  })());
});
