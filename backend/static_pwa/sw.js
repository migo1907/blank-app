const CACHE = 'migo-v2'
const PRECACHE = ['/app/', '/app/manifest.json', '/app/icon-192.png', '/app/sniper-logo.jpg']

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(PRECACHE)).then(() => self.skipWaiting()))
})

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  )
})

self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return
  const url = new URL(e.request.url)
  // Only handle the app shell — NEVER cache API/data endpoints (stale prices are worse than slow)
  if (url.origin !== location.origin || !url.pathname.startsWith('/app/')) return

  // Hashed build assets: cache-first (immutable), backfill on first fetch
  if (url.pathname.startsWith('/app/assets/')) {
    e.respondWith(
      caches.match(e.request).then(hit => hit || fetch(e.request).then(res => {
        if (res.ok) { const copy = res.clone(); caches.open(CACHE).then(c => c.put(e.request, copy)) }
        return res
      }))
    )
    return
  }

  // Shell (HTML, manifest, icons): network-first with cache fallback, cache on success
  e.respondWith(
    fetch(e.request).then(res => {
      if (res.ok) { const copy = res.clone(); caches.open(CACHE).then(c => c.put(e.request, copy)) }
      return res
    }).catch(() => caches.match(e.request, { ignoreSearch: url.pathname === '/app/' }))
  )
})

self.addEventListener('push', e => {
  let data = { title: 'Sniper Signals', body: 'New alert' }
  try { if (e.data) data = e.data.json() } catch { try { data.body = e.data.text() } catch {} }
  e.waitUntil(
    self.registration.showNotification(data.title || 'Sniper Signals', {
      body:    data.body || '',
      icon:    '/app/icon-192.png',
      badge:   '/app/icon-192.png',
      data:    { url: data.url || '/app/' },
      vibrate: [200, 100, 200],
    })
  )
})

self.addEventListener('notificationclick', e => {
  e.notification.close()
  const url = e.notification.data?.url || '/app/'
  e.waitUntil(clients.openWindow(url))
})
