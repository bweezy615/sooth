/* Sooth service worker — network-first everywhere.
   A price board must never show stale numbers silently, so the network always
   wins; the cache only answers when the network can't (offline shell). */
const CACHE = 'sooth-v3';
const SHELL = ['/', '/props', '/edges', '/research', '/trust',
               '/tools', '/engine', '/gamelog', '/ledger', '/methodology'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  e.respondWith(
    fetch(e.request).then(res => {
      if (res.ok) {
        const copy = res.clone();
        caches.open(CACHE).then(c => c.put(e.request, copy));
      }
      return res;
    }).catch(() =>
      caches.match(e.request, {ignoreSearch: true}).then(hit =>
        hit || (e.request.mode === 'navigate'
          ? caches.match('/')
          : Response.error()))
    )
  );
});
