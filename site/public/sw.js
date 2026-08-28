/* Sooth service worker — network-first everywhere.
   A price board must never show stale numbers silently, so the network always
   wins; the cache only answers when the network can't (offline shell). */
// The cache name is a FINGERPRINT of the shell it holds - sha256 of
// desk.js + desk.css, first 12 hex - not a version somebody remembers to
// bump. It used to be a hand-typed counter with a comment saying "bump it
// with any change to desk.css / desk.js". On 2026-08-28 desk.js was changed
// twice in one session and the counter was not touched either time, which is
// what hand-maintained invariants do.
//
// tests/test_service_worker.py recomputes this and fails if it disagrees, so
// a stale shell now turns the gate red instead of quietly surviving in
// somebody's browser. The value below is what that test expects; when it
// fails it prints the string to paste.
const CACHE = 'sooth-81db3fbb9f26';
const SHELL = ['/', '/props', '/edges', '/research', '/trust',
               '/tools', '/engine', '/gamelog', '/ledger', '/methodology', '/whales'];

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
