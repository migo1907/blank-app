const BASE = 'https://blank-app-production-a8bd.up.railway.app'

// API secret is obtained via passcode login (never hardcoded in the bundle).
export const getSecret = () => { try { return localStorage.getItem('app_secret') || '' } catch { return '' } }
export const clearSecret = () => { try { localStorage.removeItem('app_secret') } catch {} }
export async function login(passcode) {
  const url = new URL(BASE + '/auth/login')
  url.searchParams.set('passcode', passcode)
  const r = await fetch(url.toString(), { signal: AbortSignal.timeout(15000) })
  if (!r.ok) throw new Error(r.status === 401 ? 'Incorrect passcode' : `Login failed (${r.status})`)
  const d = await r.json()
  if (!d.secret) throw new Error('Incorrect passcode')
  try { localStorage.setItem('app_secret', d.secret) } catch {}
  return d.secret
}

async function _get(path, params = {}) {
  const url = new URL(BASE + path)
  url.searchParams.set('secret', getSecret())
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
export const getMarketSparklines= ()        => _get('/market/sparklines')
export const getMarketCommentary= ()        => _get('/market/commentary')
export const getOptionsFlow     = ()        => _get('/options/flow')
export const getEconomicCalendar= ()        => _get('/calendar/economic')
export const getEarningsCalendar= ()        => _get('/calendar/earnings')
