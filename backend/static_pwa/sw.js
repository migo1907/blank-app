const CACHE = 'migo-v1'
const PRECACHE = ['/app/', '/app/manifest.json']

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
  e.respondWith(
    fetch(e.request).catch(() => caches.match(e.request))
  )
})

self.addEventListener('push', e => {
  const data = e.data ? e.data.json() : { title: 'Migo Sniper', body: 'New alert' }
  e.waitUntil(
    self.registration.showNotification(data.title || 'Migo Sniper Pro', {
      body:    data.body || '',
      icon:    '/app/manifest.json',
      badge:   '/app/manifest.json',
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
