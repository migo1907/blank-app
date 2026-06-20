const BASE = 'https://blank-app-production-a8bd.up.railway.app'
const S    = 'gold2026'

async function _get(path, params = {}) {
  const url = new URL(BASE + path)
  Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v))
  const r = await fetch(url.toString(), { signal: AbortSignal.timeout(15000) })
  if (!r.ok) throw new Error(`${path} → ${r.status}`)
  return r.json()
}

export const getPulse   = ()           => _get('/pulse')
export const getNewsFeed = ()          => _get('/news/feed', { secret: S })
export const getHealth  = ()           => _get('/health',   { secret: S })
export const getDashboard = (pool)     => _get('/dashboard', { secret: S, pool })

export async function subscribePush(sub) {
  const r = await fetch(`${BASE}/push/subscribe?secret=${S}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ subscription: sub }),
  })
  return r.json()
}

export const VAPID_PUBLIC = import.meta.env.VITE_VAPID_PUBLIC || ''
