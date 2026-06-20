import React, { useState, useEffect, useCallback, useRef } from 'react'
import { getPulse, getNewsFeed, getHealth, subscribePush, VAPID_PUBLIC } from './api'

const TABS = [
  { id: 'pulse',     ico: '📡', label: 'Pulse' },
  { id: 'news',      ico: '📰', label: 'News' },
  { id: 'direction', ico: '🧭', label: 'Direction' },
  { id: 'alerts',    ico: '🔔', label: 'Alerts' },
]

const REFRESH = 60_000  // 60 s auto-refresh

// ── Helpers ──────────────────────────────────────────────────────────────────

function biasClass(b) {
  if (!b) return 'neut'
  return b === 'BULLISH' ? 'bull' : b === 'BEARISH' ? 'bear' : 'neut'
}

function biasEmoji(b) {
  return b === 'BULLISH' ? '▲' : b === 'BEARISH' ? '▼' : '—'
}

function dirClass(d) {
  if (!d) return 'neutral'
  return d === 'LONG' ? 'long' : d === 'SHORT' ? 'short' : 'neutral'
}

function sentClass(s) {
  return s === 'BULLISH' ? 'sent-bull' : s === 'BEARISH' ? 'sent-bear' : 'sent-neut'
}

function sentEmoji(s) {
  return s === 'BULLISH' ? '📈' : s === 'BEARISH' ? '📉' : '•'
}

function velClass(v) {
  if (!v) return 'norm'
  return v === 'ACCELERATING' ? 'acc' : v === 'QUIET' ? 'quiet' : 'norm'
}

function velLabel(v) {
  return v === 'ACCELERATING' ? '⚡ News Accelerating' : v === 'QUIET' ? '🟢 News Quiet' : '📰 News Normal'
}

function sessLabel(s) {
  const MAP = { london: 'London', ny: 'New York', asian: 'Asian', off: 'Off-hours' }
  return MAP[s] || s
}

function ageStr(mins) {
  if (mins < 60) return `${mins}m ago`
  return `${Math.floor(mins / 60)}h ${mins % 60}m ago`
}

function certEmoji(c) {
  return { HIGH: '🎯', MODERATE: '〰️', LOW: '❓' }[c] || ''
}

function useAutoRefresh(fn, ms) {
  useEffect(() => {
    fn()
    const id = setInterval(fn, ms)
    return () => clearInterval(id)
  }, [])
}

// ── Pulse Tab ────────────────────────────────────────────────────────────────

function PulseTab({ data, loading, error }) {
  if (loading) return <div className="spin">⟳</div>
  if (error)   return <div style={{ padding: 20, color: 'var(--red)' }}>{error}</div>
  if (!data)   return null

  const goldPct  = Math.abs(data.gold_score  || 0) * 100
  const stockPct = Math.abs(data.stocks_score || 0) * 100
  const evt      = data.next_event || {}
  const vel      = data.news_velocity || {}

  return (
    <div className="content">
      {/* Overall bias */}
      <div className="card">
        <div className="card-title">Overall Market Bias</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14 }}>
          <span className={`bias ${biasClass(data.overall_bias)}`}>
            {biasEmoji(data.overall_bias)} {data.overall_bias || 'NEUTRAL'}
          </span>
          <span style={{ fontSize: 12, color: 'var(--muted)' }}>
            <span className="sess-dot" style={{ marginRight: 4 }}
              data-on={data.session !== 'off'} />
            {sessLabel(data.session)}
          </span>
        </div>
        <div className="metrics">
          <div className="metric">
            <div className={`metric-val ${biasClass(data.gold_bias) === 'bull' ? '' : biasClass(data.gold_bias) === 'bear' ? 'red' : ''}`}
              style={{ color: data.gold_bias === 'BULLISH' ? 'var(--green)' : data.gold_bias === 'BEARISH' ? 'var(--red)' : 'var(--gold)' }}>
              {biasEmoji(data.gold_bias)}
            </div>
            <div className="metric-lbl">🥇 Gold</div>
          </div>
          <div className="metric">
            <div style={{ color: data.stocks_bias === 'BULLISH' ? 'var(--green)' : data.stocks_bias === 'BEARISH' ? 'var(--red)' : 'var(--gold)', fontSize: 18, fontWeight: 700 }}>
              {biasEmoji(data.stocks_bias)}
            </div>
            <div className="metric-lbl">📈 Stocks</div>
          </div>
          {data.vix != null && (
            <div className="metric">
              <div className="metric-val">{Number(data.vix).toFixed(1)}</div>
              <div className="metric-lbl">VIX</div>
            </div>
          )}
          {data.macro_label && (
            <div className="metric">
              <div className="metric-val" style={{ fontSize: 11 }}>{data.macro_label}</div>
              <div className="metric-lbl">Macro</div>
            </div>
          )}
        </div>
      </div>

      {/* Score bars */}
      <div className="card">
        <div className="card-title">Signal Strength</div>
        <div style={{ marginBottom: 10 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 4 }}>
            <span>🥇 Gold</span><span style={{ color: 'var(--muted)' }}>{goldPct.toFixed(0)}%</span>
          </div>
          <div className="bar-wrap">
            <div className="bar-fill" style={{
              width: `${goldPct}%`,
              background: data.gold_bias === 'BULLISH' ? 'var(--green)' : data.gold_bias === 'BEARISH' ? 'var(--red)' : 'var(--muted)'
            }} />
          </div>
        </div>
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 4 }}>
            <span>📈 Stocks</span><span style={{ color: 'var(--muted)' }}>{stockPct.toFixed(0)}%</span>
          </div>
          <div className="bar-wrap">
            <div className="bar-fill" style={{
              width: `${stockPct}%`,
              background: data.stocks_bias === 'BULLISH' ? 'var(--green)' : data.stocks_bias === 'BEARISH' ? 'var(--red)' : 'var(--muted)'
            }} />
          </div>
        </div>
      </div>

      {/* Event + news velocity */}
      {evt && evt.detected && (
        <div className="card" style={{ borderColor: 'rgba(245,158,11,.4)' }}>
          <div className="card-title">⚡ High-Impact Event</div>
          <span className="event-badge">{evt.name || 'Event'}</span>
          {evt.minutes_away != null && (
            <span style={{ marginLeft: 8, fontSize: 12, color: 'var(--muted)' }}>
              in {evt.minutes_away}m
            </span>
          )}
        </div>
      )}

      {vel.label && (
        <div className={`velocity ${velClass(vel.label)}`}>
          {velLabel(vel.label)}
          {vel.multiplier && vel.multiplier !== 1 && (
            <span style={{ marginLeft: 'auto', opacity: .7 }}>×{Number(vel.multiplier).toFixed(1)}</span>
          )}
        </div>
      )}

      <div style={{ padding: '6px 12px', fontSize: 10, color: 'var(--muted)' }}>
        Updated {data.updated_at ? new Date(data.updated_at).toLocaleTimeString() : '—'}
      </div>
    </div>
  )
}

// ── News Tab ─────────────────────────────────────────────────────────────────

function NewsTab({ data, loading, error }) {
  if (loading) return <div className="spin">⟳</div>
  if (error)   return <div style={{ padding: 20, color: 'var(--red)' }}>{error}</div>
  if (!data)   return null

  const vel = data.velocity
  const items = data.items || []

  return (
    <div className="content">
      {vel && (
        <div className={`velocity ${velClass(vel)}`} style={{ marginTop: 10 }}>
          {velLabel(vel)}
          <span style={{ marginLeft: 'auto', fontSize: 12 }}>
            Sentiment {data.agg_score > 0 ? '+' : ''}{(data.agg_score * 100).toFixed(0)}%
          </span>
        </div>
      )}

      {data.high_impact_event?.detected && (
        <div className="card" style={{ borderColor: 'rgba(245,158,11,.4)', margin: '6px 12px' }}>
          <span className="event-badge">⚡ {data.high_impact_event.name || 'Event'}</span>
          {data.high_impact_event.urgency != null && (
            <span style={{ fontSize: 11, color: 'var(--muted)', marginLeft: 8 }}>
              urgency {Number(data.high_impact_event.urgency).toFixed(2)}
            </span>
          )}
        </div>
      )}

      <div className="card">
        <div className="card-title">Latest Headlines ({items.length})</div>
        {items.length === 0 ? (
          <div style={{ color: 'var(--muted)', fontSize: 13 }}>No recent news.</div>
        ) : items.map((item, i) => (
          <div key={i} className="news-item">
            <div className="news-hl">
              {item.url ? (
                <a href={item.url} target="_blank" rel="noopener noreferrer"
                  style={{ color: 'var(--text)', textDecoration: 'none' }}>
                  {item.headline}
                </a>
              ) : item.headline}
            </div>
            <div className="news-meta">
              <span>{item.source}</span>
              <span>{ageStr(item.age_min)}</span>
              <span className={sentClass(item.sentiment)}>
                {sentEmoji(item.sentiment)} {item.sentiment}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Direction Tab ─────────────────────────────────────────────────────────────

function DirectionTab({ data, loading, error }) {
  if (loading) return <div className="spin">⟳</div>
  if (error)   return <div style={{ padding: 20, color: 'var(--red)' }}>{error}</div>
  if (!data)   return null

  const pools = data.pools || {}
  const goldPools  = Object.entries(pools).filter(([k]) => k.startsWith('XAUUSD'))
  const stockPools = Object.entries(pools).filter(([k]) => k.startsWith('STOCKS'))

  function PoolCard([name, info]) {
    const short = name.replace('STOCKS_', '').replace('XAUUSD_', '')
    return (
      <div key={name} className={`pool-item ${dirClass(info.direction)}`}>
        <div className="pool-name">{short}</div>
        <div className="pool-dir" style={{
          color: info.direction === 'LONG' ? 'var(--green)' : info.direction === 'SHORT' ? 'var(--red)' : 'var(--muted)'
        }}>
          {info.direction === 'LONG' ? '▲ LONG' : info.direction === 'SHORT' ? '▼ SHORT' : '— NEUTRAL'}
          {info.certainty && <span style={{ marginLeft: 4, fontSize: 10 }}>{certEmoji(info.certainty)}</span>}
        </div>
        <div className="pool-conf">{(info.confidence * 100).toFixed(0)}% conf</div>
      </div>
    )
  }

  return (
    <div className="content">
      <div className="section-h">🥇 Gold Pools</div>
      <div style={{ margin: '0 12px' }}>
        <div className="pool-grid">{goldPools.map(PoolCard)}</div>
      </div>

      <div className="section-h">📈 Stock Pools</div>
      <div style={{ margin: '0 12px' }}>
        <div className="pool-grid">{stockPools.map(PoolCard)}</div>
      </div>
    </div>
  )
}

// ── Alerts Tab ────────────────────────────────────────────────────────────────

function AlertsTab() {
  const [status,  setStatus]  = useState('idle')  // idle | requesting | on | unsupported | error
  const [message, setMessage] = useState('')

  useEffect(() => {
    if (!('Notification' in window) || !('serviceWorker' in navigator)) {
      setStatus('unsupported')
      return
    }
    if (Notification.permission === 'granted') {
      setStatus('on')
    }
  }, [])

  async function handleToggle() {
    if (status === 'on') {
      setMessage('To turn off alerts, revoke notification permission in browser settings.')
      return
    }
    if (!('Notification' in window) || !('serviceWorker' in navigator)) {
      setStatus('unsupported'); return
    }
    setStatus('requesting')
    try {
      const perm = await Notification.requestPermission()
      if (perm !== 'granted') {
        setStatus('idle'); setMessage('Permission denied.'); return
      }
      const reg = await navigator.serviceWorker.ready
      if (!VAPID_PUBLIC) {
        setStatus('on'); setMessage('Alerts enabled (no push server configured — foreground only).')
        return
      }
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: VAPID_PUBLIC,
      })
      await subscribePush(sub.toJSON())
      setStatus('on'); setMessage('Background alerts active!')
    } catch (e) {
      setStatus('error'); setMessage(`Error: ${e.message}`)
    }
  }

  return (
    <div className="content">
      <div className="card">
        <div className="card-title">Push Notifications</div>
        <p style={{ fontSize: 13, color: 'var(--muted)', marginBottom: 14, lineHeight: 1.5 }}>
          Get background alerts when a high-confidence signal fires (≥65%) or a regime shift is detected — even when the app is closed.
        </p>
        {status === 'unsupported' ? (
          <div style={{ color: 'var(--red)', fontSize: 13 }}>
            Push notifications not supported in this browser.
          </div>
        ) : (
          <button
            className={`alert-btn ${status === 'on' ? 'on' : 'off'}`}
            onClick={handleToggle}
          >
            {status === 'on'         ? '🔔 Alerts ON' :
             status === 'requesting' ? '…Requesting…' :
                                       '🔕 Enable Alerts'}
          </button>
        )}
        {message && <p style={{ marginTop: 12, fontSize: 12, color: 'var(--muted)' }}>{message}</p>}
      </div>

      <div className="card">
        <div className="card-title">What triggers an alert?</div>
        <ul style={{ fontSize: 13, color: 'var(--muted)', lineHeight: 1.8, paddingLeft: 16 }}>
          <li>High-confidence signal ≥ 65% (any pool)</li>
          <li>Market regime shift detected</li>
          <li>High-impact economic event imminent</li>
          <li>News velocity spikes to ACCELERATING</li>
        </ul>
      </div>

      <div className="card">
        <div className="card-title">Install as App</div>
        <p style={{ fontSize: 13, color: 'var(--muted)', lineHeight: 1.5 }}>
          On iPhone: tap <strong style={{ color: 'var(--text)' }}>Share → Add to Home Screen</strong>.<br />
          On Android: tap <strong style={{ color: 'var(--text)' }}>⋮ → Add to Home Screen</strong>.
        </p>
      </div>
    </div>
  )
}

// ── App Root ──────────────────────────────────────────────────────────────────

export default function App() {
  const [tab,        setTab]        = useState('pulse')
  const [pulse,      setPulse]      = useState(null)
  const [pulseErr,   setPulseErr]   = useState(null)
  const [pulseLoad,  setPulseLoad]  = useState(true)
  const [news,       setNews]       = useState(null)
  const [newsErr,    setNewsErr]    = useState(null)
  const [newsLoad,   setNewsLoad]   = useState(false)
  const newsLoaded = useRef(false)

  const loadPulse = useCallback(async () => {
    try {
      const d = await getPulse()
      setPulse(d); setPulseErr(null)
    } catch (e) {
      setPulseErr(e.message)
    } finally {
      setPulseLoad(false)
    }
  }, [])

  const loadNews = useCallback(async () => {
    setNewsLoad(true)
    try {
      const d = await getNewsFeed()
      setNews(d); setNewsErr(null)
    } catch (e) {
      setNewsErr(e.message)
    } finally {
      setNewsLoad(false)
    }
  }, [])

  useAutoRefresh(loadPulse, REFRESH)

  useEffect(() => {
    if (tab === 'news' && !newsLoaded.current) {
      newsLoaded.current = true
      loadNews()
    }
  }, [tab])

  // Auto-refresh news every 2 min when on that tab
  useEffect(() => {
    if (tab !== 'news') return
    const id = setInterval(loadNews, 120_000)
    return () => clearInterval(id)
  }, [tab])

  return (
    <>
      <nav className="nav">
        {TABS.map(t => (
          <button key={t.id} className={tab === t.id ? 'active' : ''} onClick={() => setTab(t.id)}>
            <span className="ico">{t.ico}</span>
            {t.label}
          </button>
        ))}
      </nav>

      <div style={{ flex: 1 }}>
        {tab === 'pulse'     && <PulseTab     data={pulse} loading={pulseLoad} error={pulseErr} />}
        {tab === 'news'      && <NewsTab      data={news}  loading={newsLoad}  error={newsErr}  />}
        {tab === 'direction' && <DirectionTab data={pulse} loading={pulseLoad} error={pulseErr} />}
        {tab === 'alerts'    && <AlertsTab />}
      </div>
    </>
  )
}
