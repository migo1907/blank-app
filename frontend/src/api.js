const BASE = 'https://blank-app-production-a8bd.up.railway.app'
const S    = 'gold2026'

async function _get(path, params = {}) {
  const url = new URL(BASE + path)
  url.searchParams.set('secret', S)
  Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v))
  const r = await fetch(url.toString(), { signal: AbortSignal.timeout(20000) })
  if (!r.ok) throw new Error(`${path} → ${r.status}`)
  return r.json()
}

export const getPulse    = ()       => fetch(`${BASE}/pulse`, { signal: AbortSignal.timeout(15000) }).then(r => r.json())
export const getNewsFeed = ()       => _get('/news/feed')
export const getHealth   = ()       => _get('/health')
export const getDashboard = (pool)  => _get('/dashboard', { pool })

export async function subscribePush(sub) {
  const r = await fetch(`${BASE}/push/subscribe?secret=${S}`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ subscription: sub }),
  })
  return r.json()
}

export const VAPID_PUBLIC = import.meta.env.VITE_VAPID_PUBLIC || ''

export const getMarketOverview  = ()        => _get('/market/overview')
export const getMarketQuotes    = (symbols) => _get('/market/quotes', { symbols })
export const getMarketTicker    = (symbol)  => _get(`/market/ticker/${symbol}`)
export const getMarketCompare   = (symbols) => _get('/market/compare', { symbols })
export const getMarketWrap      = ()        => _get('/market/wrap')
export const getMarketCommentary= ()        => _get('/market/commentary')
