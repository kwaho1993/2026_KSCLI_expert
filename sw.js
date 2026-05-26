const CACHE = 'kscli-2026-v1';

self.addEventListener('install', () => self.skipWaiting());

self.addEventListener('activate', e => {
    e.waitUntil(
        caches.keys().then(keys =>
            Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
        )
    );
    self.clients.claim();
});

self.addEventListener('fetch', e => {
    const url = new URL(e.request.url);

    // WebP 이미지 → cache-first (변경 없음)
    if (url.pathname.endsWith('.webp')) {
        e.respondWith(cacheFirst(e.request));
        return;
    }

    // metadata.json → stale-while-revalidate (즉시 응답 + 백그라운드 갱신)
    if (url.pathname.endsWith('metadata.json')) {
        e.respondWith(staleWhileRevalidate(e.request));
        return;
    }

    // index.html, sw.js 등 → network-first (항상 최신 유지)
    e.respondWith(networkFirst(e.request));
});

async function cacheFirst(req) {
    const cached = await caches.match(req);
    if (cached) return cached;
    const res = await fetch(req);
    if (res.ok) (await caches.open(CACHE)).put(req, res.clone());
    return res;
}

async function staleWhileRevalidate(req) {
    const cache = await caches.open(CACHE);
    const cached = await cache.match(req);
    const fresh = fetch(req).then(res => { if (res.ok) cache.put(req, res.clone()); return res; });
    return cached ?? fresh;
}

async function networkFirst(req) {
    try {
        const res = await fetch(req);
        if (res.ok) (await caches.open(CACHE)).put(req, res.clone());
        return res;
    } catch {
        return (await caches.match(req)) ?? Response.error();
    }
}
