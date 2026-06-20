import React, { useState, useEffect, useCallback, useRef } from 'react'
import { getPulse, getNewsFeed, getHealth, getDashboard, subscribePush, VAPID_PUBLIC } from './api'

const BASE   = 'https://blank-app-production-a8bd.up.railway.app'
const SECRET = 'gold2026'

async function _get(path, params = {}) {
  const url = new URL(BASE + path)
  url.searchParams.set('secret', SECRET)
  Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v))
  const r = await fetch(url.toString(), { signal: AbortSignal.timeout(20000) })
  if (!r.ok) throw new Error(`${path} → ${r.status}`)
  return r.json()
}

const TABS = [
  { id: 'pulse',   ico: '📡', label: 'Pulse'   },
  { id: 'signals', ico: '🧭', label: 'Signals'  },
  { id: 'ml',      ico: '🤖', label: 'ML'       },
  { id: 'swing',   ico: '📈', label: 'Swing'    },
  { id: 'macro',   ico: '🌍', label: 'Macro'    },
  { id: 'news',    ico: '📰', label: 'News'     },
]

const GOLD_POOLS  = ['XAUUSD_2M','XAUUSD_5M','XAUUSD_15M','XAUUSD_30M','XAUUSD_1H']
const STOCK_POOLS = [
  'STOCKS_MOMENTUM_15M','STOCKS_MOMENTUM_30M',
  'STOCKS_QUALITY_15M','STOCKS_QUALITY_30M',
  'STOCKS_INDEX_15M','STOCKS_INDEX_30M',
  'STOCKS_QQQ_15M','STOCKS_QQQ_30M',
  'STOCKS_SPX500_15M','STOCKS_SPX500_30M',
]

// ── Helpers ───────────────────────────────────────────────────────────────────
const bc = b => b === 'BULLISH' ? 'bull' : b === 'BEARISH' ? 'bear' : 'neut'
const bico = b => b === 'BULLISH' ? '▲' : b === 'BEARISH' ? '▼' : '—'
const dc = d => d === 'LONG' ? 'long' : d === 'SHORT' ? 'short' : 'neutral'
const cert = c => ({ HIGH:'🎯', MODERATE:'〰️', LOW:'❓' }[c] || '')
const pct  = v => `${(Number(v||0)*100).toFixed(1)}%`
const num  = (v,d=2) => v != null ? Number(v).toFixed(d) : '—'
const age  = iso => {
  if (!iso) return '—'
  try {
    const mins = Math.floor((Date.now() - new Date(iso)) / 60000)
    return mins < 60 ? `${mins}m` : `${Math.floor(mins/60)}h${mins%60}m`
  } catch { return iso.slice(11,16) }
}

function Spinner() { return <div className="spin">⟳</div> }
function Err({ e }) { return <div style={{padding:20,color:'var(--red)',fontSize:13}}>{String(e)}</div> }

function useLoad(fn, deps=[]) {
  const [data, setData]   = useState(null)
  const [err,  setErr]    = useState(null)
  const [load, setLoad]   = useState(true)
  const load_ = useCallback(async () => {
    setLoad(true)
    try { setData(await fn()); setErr(null) }
    catch(e) { setErr(e.message) }
    finally { setLoad(false) }
  }, deps)
  useEffect(() => { load_() }, [load_])
  return { data, err, load, reload: load_ }
}

// ── Shared UI ─────────────────────────────────────────────────────────────────
function Card({ title, children, style }) {
  return (
    <div className="card" style={style}>
      {title && <div className="card-title">{title}</div>}
      {children}
    </div>
  )
}

function Table({ cols, rows, small }) {
  if (!rows?.length) return <div style={{color:'var(--muted)',fontSize:12}}>No data.</div>
  return (
    <div style={{overflowX:'auto'}}>
      <table style={{width:'100%',borderCollapse:'collapse',fontSize:small?10:12}}>
        <thead>
          <tr>{cols.map(c=><th key={c} style={{textAlign:'left',padding:'4px 6px',color:'var(--muted)',fontWeight:600,borderBottom:'1px solid var(--border)',whiteSpace:'nowrap'}}>{c}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r,i)=>(
            <tr key={i} style={{borderBottom:'1px solid var(--border)'}}>
              {r.map((c,j)=><td key={j} style={{padding:'5px 6px',whiteSpace:'nowrap'}}>{c}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Badge({ label, color }) {
  const colors = { bull:'rgba(34,197,94,.15)', bear:'rgba(239,68,68,.15)', gold:'rgba(245,158,11,.15)', blue:'rgba(59,130,246,.15)', muted:'rgba(107,114,128,.15)' }
  const text   = { bull:'var(--green)', bear:'var(--red)', gold:'var(--gold)', blue:'var(--blue)', muted:'var(--muted)' }
  return <span style={{background:colors[color]||colors.muted, color:text[color]||text.muted, padding:'2px 8px', borderRadius:20, fontSize:11, fontWeight:700}}>{label}</span>
}

function ScoreBar({ value, bias }) {
  const pct = Math.min(100, Math.abs(Number(value||0))*100)
  const bg = bias==='BULLISH'?'var(--green)':bias==='BEARISH'?'var(--red)':'var(--muted)'
  return <div className="bar-wrap"><div className="bar-fill" style={{width:`${pct}%`,background:bg}}/></div>
}

// ══════════════════════════════════════════════════════════════
// TAB 1 — PULSE
// ══════════════════════════════════════════════════════════════
function PulseTab({ pulse, health }) {
  const pd = pulse.data
  const hd = health.data
  if (pulse.load && !pd) return <Spinner/>
  if (pulse.err && !pd) return <Err e={pulse.err}/>

  const macro  = hd?.macro || {}
  const imkt   = hd?.intermarket || {}
  const vel    = pd?.news_velocity || {}
  const evt    = pd?.next_event   || {}

  return (
    <div className="content">
      {/* Overall bias */}
      <Card title="Overall Market Bias">
        <div style={{display:'flex',gap:10,flexWrap:'wrap',marginBottom:12}}>
          <span className={`bias ${bc(pd?.overall_bias)}`}>{bico(pd?.overall_bias)} {pd?.overall_bias||'—'}</span>
          <span style={{fontSize:12,color:'var(--muted)',alignSelf:'center'}}>
            Session: <strong style={{color:'var(--text)'}}>{pd?.session?.toUpperCase()||'—'}</strong>
          </span>
          {imkt.vix != null && <span style={{fontSize:12,color:'var(--muted)',alignSelf:'center'}}>VIX: <strong style={{color:'var(--gold)'}}>{num(imkt.vix,1)}</strong></span>}
        </div>

        <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:10}}>
          <div>
            <div style={{fontSize:11,color:'var(--muted)',marginBottom:4}}>🥇 Gold — <span className={bc(pd?.gold_bias)}>{bico(pd?.gold_bias)} {pd?.gold_bias||'—'}</span></div>
            <ScoreBar value={pd?.gold_score} bias={pd?.gold_bias}/>
          </div>
          <div>
            <div style={{fontSize:11,color:'var(--muted)',marginBottom:4}}>📈 Stocks — <span className={bc(pd?.stocks_bias)}>{bico(pd?.stocks_bias)} {pd?.stocks_bias||'—'}</span></div>
            <ScoreBar value={pd?.stocks_score} bias={pd?.stocks_bias}/>
          </div>
        </div>
      </Card>

      {/* Macro */}
      {(pd?.macro_label || pd?.macro_bias != null) && (
        <Card title="Macro Intelligence (Gold)">
          <div style={{display:'flex',gap:12,flexWrap:'wrap'}}>
            <div className="metric"><div className="metric-val" style={{fontSize:14}}>{pd?.macro_label||'—'}</div><div className="metric-lbl">Macro Bias</div></div>
            <div className="metric"><div className="metric-val" style={{fontSize:14}}>{pd?.macro_bias != null ? (pd.macro_bias > 0 ? '+' : '')+num(pd.macro_bias,2) : '—'}</div><div className="metric-lbl">Score</div></div>
            {imkt.vix != null && <div className="metric"><div className="metric-val" style={{fontSize:14}}>{num(imkt.vix,1)}</div><div className="metric-lbl">VIX</div></div>}
            {imkt.dxy_break != null && <div className="metric"><div className="metric-val" style={{fontSize:14}}>{imkt.dxy_break ? '✅':'❌'}</div><div className="metric-lbl">DXY Break</div></div>}
          </div>
        </Card>
      )}

      {/* Event */}
      {evt?.detected && (
        <Card style={{borderColor:'rgba(245,158,11,.4)'}}>
          <div style={{display:'flex',alignItems:'center',gap:8}}>
            <span style={{fontSize:18}}>⚡</span>
            <div>
              <div style={{fontWeight:700,color:'var(--gold)'}}>{evt.name||'High-impact event'}</div>
              {evt.minutes_away != null && <div style={{fontSize:11,color:'var(--muted)'}}>in {evt.minutes_away} min · urgency {num(evt.urgency,2)}</div>}
            </div>
          </div>
        </Card>
      )}

      {/* News velocity */}
      {vel.label && (
        <div className={`velocity ${vel.label==='ACCELERATING'?'acc':vel.label==='QUIET'?'quiet':'norm'}`} style={{margin:'0 12px 8px'}}>
          {vel.label==='ACCELERATING'?'⚡ News Accelerating':vel.label==='QUIET'?'🟢 News Quiet':'📰 News Normal'}
          {vel.multiplier && <span style={{marginLeft:'auto',opacity:.7}}>×{num(vel.multiplier,1)}</span>}
        </div>
      )}

      {/* System health quick row */}
      {hd && (
        <Card title="System">
          <div className="metrics">
            <div className="metric"><div className="metric-val" style={{fontSize:12}}>{hd.status?.toUpperCase()||'—'}</div><div className="metric-lbl">Status</div></div>
            <div className="metric"><div className="metric-val" style={{fontSize:12}}>{hd.scheduler?.toUpperCase()||'—'}</div><div className="metric-lbl">Scheduler</div></div>
            <div className="metric"><div className="metric-val" style={{fontSize:12}}>{hd.version||'—'}</div><div className="metric-lbl">Version</div></div>
          </div>
        </Card>
      )}

      <div style={{padding:'4px 12px',fontSize:10,color:'var(--muted)'}}>
        Updated {pd?.updated_at ? new Date(pd.updated_at).toLocaleTimeString() : '—'}
        {' · '}<span style={{cursor:'pointer',color:'var(--gold)'}} onClick={pulse.reload}>↻ Refresh</span>
      </div>
    </div>
  )
}

// ══════════════════════════════════════════════════════════════
// TAB 2 — SIGNALS (all pools + per-pool detail)
// ══════════════════════════════════════════════════════════════
function PoolDetail({ pool }) {
  const { data, err, load } = useLoad(() => getDashboard(pool), [pool])
  if (load) return <div style={{padding:'8px 0',color:'var(--muted)',fontSize:12}}>Loading…</div>
  if (err)  return <div style={{padding:'8px 0',color:'var(--red)',fontSize:12}}>{err}</div>
  if (!data) return null

  const m = data.model || {}
  const rf = data.rf   || {}

  return (
    <div style={{padding:'8px 0 4px',borderTop:'1px solid var(--border)'}}>
      <div style={{display:'grid',gridTemplateColumns:'repeat(3,1fr)',gap:6,marginBottom:8}}>
        <div className="metric"><div className="metric-val" style={{fontSize:13}}>{num(m.win_rate,0)}%</div><div className="metric-lbl">Win Rate</div></div>
        <div className="metric"><div className="metric-val" style={{fontSize:13}}>{m.total_trades||0}</div><div className="metric-lbl">Trades</div></div>
        <div className="metric"><div className="metric-val" style={{fontSize:13}}>{(data.news_sentiment>=0?'+':'')+num(data.news_sentiment,2)}</div><div className="metric-lbl">News Sent.</div></div>
      </div>

      <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:8,marginBottom:8}}>
        {m.top_features?.length > 0 && (
          <div>
            <div style={{fontSize:10,color:'var(--muted)',fontWeight:600,marginBottom:4}}>KNN Features</div>
            {m.top_features.slice(0,5).map((f,i) => (
              <div key={i} style={{fontSize:10,display:'flex',justifyContent:'space-between',padding:'2px 0',borderBottom:'1px solid var(--border)'}}>
                <span style={{color:'var(--text)'}}>{f.name}</span>
                <span style={{color:'var(--gold)'}}>{num(f.weight,3)}</span>
              </div>
            ))}
          </div>
        )}
        {rf.top_features?.length > 0 && (
          <div>
            <div style={{fontSize:10,color:'var(--muted)',fontWeight:600,marginBottom:4}}>RF Features</div>
            {rf.top_features.slice(0,5).map((f,i) => (
              <div key={i} style={{fontSize:10,display:'flex',justifyContent:'space-between',padding:'2px 0',borderBottom:'1px solid var(--border)'}}>
                <span style={{color:'var(--text)'}}>{f.name}</span>
                <span style={{color:'var(--blue)'}}>{num(f.importance,3)}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {data.recent_trades?.length > 0 && (
        <div>
          <div style={{fontSize:10,color:'var(--muted)',fontWeight:600,marginBottom:4}}>Recent Trades</div>
          {data.recent_trades.slice(0,5).map((t,i) => (
            <div key={i} style={{fontSize:11,display:'flex',gap:8,padding:'2px 0',borderBottom:'1px solid var(--border)'}}>
              <span style={{color:t.direction==='LONG'?'var(--green)':'var(--red)',fontWeight:700,width:36}}>{t.direction==='LONG'?'▲ L':'▼ S'}</span>
              <span style={{color:t.outcome==='WIN'?'var(--green)':t.outcome==='LOSS'?'var(--red)':'var(--muted)',width:50}}>{t.outcome}</span>
              <span style={{color:'var(--muted)'}}>{age(t.created_at)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function SignalsTab({ pulse }) {
  const [expanded, setExpanded] = useState(null)
  const pools = pulse.data?.pools || {}

  function PoolCard({ name }) {
    const info  = pools[name] || {}
    const short = name.replace('XAUUSD_','').replace('STOCKS_','')
    const isExp = expanded === name
    return (
      <div style={{background:'var(--bg)',border:'1px solid var(--border)',borderRadius:8,padding:'8px 10px',borderLeft:`3px solid ${info.direction==='LONG'?'var(--green)':info.direction==='SHORT'?'var(--red)':'var(--border)'}`}}
        onClick={() => setExpanded(isExp ? null : name)}>
        <div style={{fontSize:10,color:'var(--muted)',marginBottom:3}}>{short}</div>
        <div style={{fontSize:13,fontWeight:700,color:info.direction==='LONG'?'var(--green)':info.direction==='SHORT'?'var(--red)':'var(--muted)'}}>
          {info.direction==='LONG'?'▲ LONG':info.direction==='SHORT'?'▼ SHORT':'— NEUT'}
          {info.certainty && <span style={{marginLeft:4,fontSize:11}}>{cert(info.certainty)}</span>}
        </div>
        <div style={{fontSize:10,color:'var(--muted)'}}>{((info.confidence||0)*100).toFixed(0)}% · {isExp?'▲ hide':'▼ detail'}</div>
        {isExp && <PoolDetail pool={name}/>}
      </div>
    )
  }

  if (pulse.load && !pulse.data) return <Spinner/>

  return (
    <div className="content">
      <div style={{padding:'10px 12px 2px',fontSize:11,color:'var(--muted)'}}>Tap a pool to see win rate, features & recent trades.</div>

      <div className="section-h">🥇 Gold Pools</div>
      <div style={{margin:'0 12px',display:'flex',flexDirection:'column',gap:6}}>
        {GOLD_POOLS.map(n => <PoolCard key={n} name={n}/>)}
      </div>

      <div className="section-h">📈 Stock Pools</div>
      <div style={{margin:'0 12px',display:'grid',gridTemplateColumns:'1fr 1fr',gap:6,paddingBottom:16}}>
        {STOCK_POOLS.map(n => {
          const info  = pools[n] || {}
          const short = n.replace('STOCKS_','')
          const isExp = expanded === n
          return (
            <div key={n} style={{background:'var(--bg)',border:'1px solid var(--border)',borderRadius:8,padding:'8px 10px',borderLeft:`3px solid ${info.direction==='LONG'?'var(--green)':info.direction==='SHORT'?'var(--red)':'var(--border)'}`,gridColumn:isExp?'1/-1':'auto'}}
              onClick={() => setExpanded(isExp ? null : n)}>
              <div style={{fontSize:10,color:'var(--muted)',marginBottom:3}}>{short}</div>
              <div style={{fontSize:12,fontWeight:700,color:info.direction==='LONG'?'var(--green)':info.direction==='SHORT'?'var(--red)':'var(--muted)'}}>
                {info.direction==='LONG'?'▲ LONG':info.direction==='SHORT'?'▼ SHORT':'— NEUT'}
                {info.certainty && <span style={{marginLeft:4,fontSize:10}}>{cert(info.certainty)}</span>}
              </div>
              <div style={{fontSize:10,color:'var(--muted)'}}>{((info.confidence||0)*100).toFixed(0)}%</div>
              {isExp && <PoolDetail pool={n}/>}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ══════════════════════════════════════════════════════════════
// TAB 3 — ML MODELS
// ══════════════════════════════════════════════════════════════
function MLTab({ health }) {
  const [fPool, setFPool] = useState('XAUUSD_2M')
  const { data: fi, load: fiLoad } = useLoad(() => _get('/feature-importance', {pool: fPool}), [fPool])

  const { data: hd, err, load } = health
  if (load && !hd) return <Spinner/>
  if (err && !hd)  return <Err e={err}/>

  const ml    = hd?.ml    || {}
  const pools = ml.pools  || {}
  const dir   = hd?.directive || {}
  const phases = dir.improvement_phases || {}

  const poolRows = Object.entries(pools).map(([pool, p]) => {
    const ci   = p.conformal_interval || []
    const cert_= p.ml_certainty || ''
    return [
      <span style={{fontSize:10}}>{pool.replace('STOCKS_','')}</span>,
      p.rf_trained  ? '✅':'❌',
      p.gbm_trained ? '✅':'❌',
      p.oos_accuracy ? `${(p.oos_accuracy*100).toFixed(1)}%` : '—',
      num(p.threshold,2),
      cert_ ? `${cert(cert_)} ${cert_}` : '—',
      p.retrain_count || 0,
      age(p.last_retrain),
    ]
  })

  return (
    <div className="content">
      <Card title="Pool ML Quality">
        <Table small
          cols={['Pool','RF','GBM','OOS Acc','Thresh','Certainty','Retrain','Last']}
          rows={poolRows}
        />
      </Card>

      <Card title="Joint & Advanced Models">
        <div className="metrics">
          <div className="metric"><div className="metric-val" style={{fontSize:14}}>{ml.joint_gold_trained?'✅':'❌'}</div><div className="metric-lbl">JointGold</div></div>
          <div className="metric"><div className="metric-val" style={{fontSize:14}}>{ml.joint_stocks_trained?'✅':'❌'}</div><div className="metric-lbl">JointStocks</div></div>
          <div className="metric"><div className="metric-val" style={{fontSize:14}}>{ml.tabpfn_available?'✅':'❌'}</div><div className="metric-lbl">TabPFN</div></div>
          <div className="metric"><div className="metric-val" style={{fontSize:14}}>{ml.lgbm_available?'✅':'❌'}</div><div className="metric-lbl">LightGBM</div></div>
          <div className="metric"><div className="metric-val" style={{fontSize:14}}>{ml.optuna_available?'✅':'❌'}</div><div className="metric-lbl">Optuna</div></div>
          <div className="metric"><div className="metric-val" style={{fontSize:14}}>{ml.shap_available?'✅':'❌'}</div><div className="metric-lbl">SHAP</div></div>
        </div>
      </Card>

      <Card title="Improvement Phases">
        <div className="metrics">
          <div className="metric"><div className="metric-val" style={{fontSize:14}}>{phases.phase1_active?'✅':'❌'}</div><div className="metric-lbl">Phase 1</div></div>
          <div className="metric"><div className="metric-val" style={{fontSize:14}}>{phases.phase4_joint?'✅':'❌'}</div><div className="metric-lbl">Phase 4</div></div>
          <div className="metric"><div className="metric-val" style={{fontSize:14}}>{ml.joint_gold_trained?'✅':'❌'}</div><div className="metric-lbl">JointGold</div></div>
        </div>
      </Card>

      <Card title="Feature Importance">
        <div style={{marginBottom:8}}>
          <select value={fPool} onChange={e=>setFPool(e.target.value)}
            style={{background:'var(--bg)',color:'var(--text)',border:'1px solid var(--border)',borderRadius:6,padding:'6px 8px',fontSize:12,width:'100%'}}>
            {[...GOLD_POOLS,...STOCK_POOLS].map(p=><option key={p} value={p}>{p}</option>)}
          </select>
        </div>
        {fiLoad ? <div style={{color:'var(--muted)',fontSize:12}}>Loading…</div> : fi && (
          <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:12}}>
            <div>
              <div style={{fontSize:10,color:'var(--muted)',fontWeight:700,marginBottom:6}}>RF TOP FEATURES</div>
              {(fi.rf?.top_features||[]).slice(0,8).map((f,i)=>(
                <div key={i} style={{fontSize:11,display:'flex',justifyContent:'space-between',padding:'3px 0',borderBottom:'1px solid var(--border)'}}>
                  <span>{f.name||f.feature}</span><span style={{color:'var(--green)'}}>{num(f.importance,3)}</span>
                </div>
              ))}
            </div>
            <div>
              <div style={{fontSize:10,color:'var(--muted)',fontWeight:700,marginBottom:6}}>GBM TOP FEATURES</div>
              {(fi.gbm?.top_features||[]).slice(0,8).map((f,i)=>(
                <div key={i} style={{fontSize:11,display:'flex',justifyContent:'space-between',padding:'3px 0',borderBottom:'1px solid var(--border)'}}>
                  <span>{f.name||f.feature}</span><span style={{color:'var(--blue)'}}>{num(f.importance,3)}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </Card>
    </div>
  )
}

// ══════════════════════════════════════════════════════════════
// TAB 4 — SWING BRAIN
// ══════════════════════════════════════════════════════════════
function SwingTab() {
  const stats = useLoad(() => _get('/swing/trades'))
  const cands = useLoad(() => _get('/swing/candidates'))
  const [showThesis, setShowThesis] = useState(false)

  const ss   = stats.data  || {}
  const list = cands.data?.candidates || []

  if (stats.load && !ss.open && !ss.closed) return <Spinner/>

  const top = list[0]

  return (
    <div className="content">
      <Card title="Swing ML Training">
        <div className="metrics">
          <div className="metric"><div className="metric-val">{ss.open||0}</div><div className="metric-lbl">Open</div></div>
          <div className="metric"><div className="metric-val">{ss.closed||0}</div><div className="metric-lbl">Closed</div></div>
          <div className="metric"><div className="metric-val">{ss.win_rate!=null?pct(ss.win_rate):'—'}</div><div className="metric-lbl">Win Rate</div></div>
          <div className="metric">
            <div className="metric-val" style={{fontSize:12}}>{ss.ready?'✅ READY':`⏳ ${50-(ss.closed||0)} more`}</div>
            <div className="metric-lbl">ML Gate</div>
          </div>
        </div>
      </Card>

      {top && (
        <Card style={{borderColor:'rgba(245,158,11,.4)'}}>
          <div style={{display:'flex',justifyContent:'space-between',alignItems:'flex-start',marginBottom:8}}>
            <div>
              <div style={{fontSize:11,color:'var(--muted)'}}>Top Pick</div>
              <div style={{fontSize:18,fontWeight:700,color:'var(--gold)'}}>{top.ticker}</div>
            </div>
            <div style={{textAlign:'right'}}>
              <Badge label={top.conviction||'—'} color={top.conviction==='STRONG'?'bull':top.conviction==='GOOD'?'blue':'muted'}/>
              <div style={{fontSize:12,color:'var(--gold)',marginTop:4}}>{((top.combined_score||0)*100).toFixed(0)}% score</div>
            </div>
          </div>
          <div style={{display:'grid',gridTemplateColumns:'repeat(3,1fr)',gap:6,marginBottom:8}}>
            <div className="metric"><div className="metric-val" style={{fontSize:12}}>{top.entry?`$${num(top.entry,2)}`:'—'}</div><div className="metric-lbl">Entry</div></div>
            <div className="metric"><div className="metric-val" style={{fontSize:12,color:'var(--green)'}}>{top.tp?`$${num(top.tp,2)}`:'—'}</div><div className="metric-lbl">TP</div></div>
            <div className="metric"><div className="metric-val" style={{fontSize:12,color:'var(--red)'}}>{top.sl?`$${num(top.sl,2)}`:'—'}</div><div className="metric-lbl">SL</div></div>
          </div>
          {top.thesis && (
            <>
              <button onClick={()=>setShowThesis(!showThesis)}
                style={{background:'var(--border)',border:'none',color:'var(--text)',padding:'6px 12px',borderRadius:6,fontSize:12,cursor:'pointer',width:'100%'}}>
                {showThesis?'▲ Hide Thesis':'▼ Show Thesis'}
              </button>
              {showThesis && <div style={{marginTop:10,fontSize:12,lineHeight:1.6,color:'var(--text)',borderTop:'1px solid var(--border)',paddingTop:10}}>{top.thesis}</div>}
            </>
          )}
        </Card>
      )}

      <Card title={`Swing Candidates (${list.length})`}>
        {cands.load && !list.length ? <div style={{color:'var(--muted)',fontSize:12}}>Loading…</div> :
        !list.length ? <div style={{color:'var(--muted)',fontSize:12}}>No candidates cached. Trigger /swing/now.</div> :
        <Table small
          cols={['Ticker','Score','Conv.','Fund.','Tech.','Entry','TP','SL']}
          rows={list.slice(0,20).map(c=>[
            <span style={{color:'var(--gold)',fontWeight:700}}>{c.ticker}</span>,
            `${((c.combined_score||0)*100).toFixed(0)}%`,
            <Badge label={c.conviction||'—'} color={c.conviction==='STRONG'?'bull':c.conviction==='GOOD'?'blue':'muted'}/>,
            `${((c.fundamental_score||0)*100).toFixed(0)}%`,
            `${((c.technical_score||0)*100).toFixed(0)}%`,
            c.entry?`$${num(c.entry,2)}`:'—',
            c.tp?`$${num(c.tp,2)}`:'—',
            c.sl?`$${num(c.sl,2)}`:'—',
          ])}
        />}
      </Card>
    </div>
  )
}

// ══════════════════════════════════════════════════════════════
// TAB 5 — MACRO & REGIME
// ══════════════════════════════════════════════════════════════
function MacroTab({ health }) {
  const opts = useLoad(() => _get('/options/trades'))
  const { data: hd, err, load } = health

  if (load && !hd) return <Spinner/>
  if (err && !hd)  return <Err e={err}/>

  const regimes  = hd?.regimes    || {}
  const mtf      = hd?.mtf        || {}
  const imkt     = hd?.intermarket || {}
  const postev   = hd?.post_event || {}
  const macro    = hd?.macro      || {}

  // Macro components from health
  const macroComp = macro.components || {}

  const od   = opts.data || {}
  const optPools = od.pools || {}

  return (
    <div className="content">
      {/* Macro components */}
      {Object.keys(macroComp).length > 0 && (
        <Card title="Macro Drivers (Gold)">
          <Table small
            cols={['Driver','Value','Signal']}
            rows={Object.entries(macroComp).map(([k,v])=>[
              k.replace(/_/g,' '),
              typeof v === 'number' ? num(v,3) : String(v??'—'),
              '',
            ])}
          />
        </Card>
      )}

      {/* Intermarket */}
      <Card title="Intermarket">
        <div className="metrics">
          {imkt.vix     != null && <div className="metric"><div className="metric-val">{num(imkt.vix,1)}</div><div className="metric-lbl">VIX</div></div>}
          {imkt.dxy_break != null && <div className="metric"><div className="metric-val">{imkt.dxy_break?'✅':'❌'}</div><div className="metric-lbl">DXY Break</div></div>}
          {imkt.yield_spread != null && <div className="metric"><div className="metric-val" style={{fontSize:13}}>{num(imkt.yield_spread,2)}</div><div className="metric-lbl">Yield Spread</div></div>}
          {imkt.real_yield   != null && <div className="metric"><div className="metric-val" style={{fontSize:13}}>{num(imkt.real_yield,2)}%</div><div className="metric-lbl">Real Yield</div></div>}
        </div>
      </Card>

      {/* Regimes */}
      {Object.keys(regimes).length > 0 && (
        <Card title="Market Regimes">
          <Table
            cols={['Asset','Regime','Label','Conf']}
            rows={Object.entries(regimes).map(([asset,r])=>[
              asset,
              <Badge label={r.regime||'—'} color={r.regime?.includes('BULL')?'bull':r.regime?.includes('BEAR')?'bear':'muted'}/>,
              r.label||'—',
              `${((r.confidence||0)*100).toFixed(0)}%`,
            ])}
          />
        </Card>
      )}

      {/* MTF */}
      {Object.keys(mtf).length > 0 && (
        <Card title="MTF Confluence">
          <Table
            cols={['Asset','Alignment','Bull','Bear']}
            rows={Object.entries(mtf).map(([asset,m])=>[
              asset,
              <Badge label={m.alignment||'—'} color={m.alignment==='BULLISH'?'bull':m.alignment==='BEARISH'?'bear':'muted'}/>,
              num(m.bull_score,2),
              num(m.bear_score,2),
            ])}
          />
        </Card>
      )}

      {/* Post-event volatility */}
      {Object.keys(postev).length > 0 && (
        <Card title="Post-Event Volatility">
          <Table
            cols={['Asset','State','Since']}
            rows={Object.entries(postev).map(([asset,ev])=>[
              asset,
              ev.state||'—',
              age(ev.event_time),
            ])}
          />
        </Card>
      )}

      {/* Options paper trades */}
      <Card title="SPX Options Paper Trades">
        {opts.load && !od.pools ? <div style={{color:'var(--muted)',fontSize:12}}>Loading…</div> :
        Object.keys(optPools).length === 0 ? <div style={{color:'var(--muted)',fontSize:12}}>No options data yet.</div> : (
          <Table
            cols={['Pool','Open','Closed','Win Rate','ML Gate','Last']}
            rows={Object.entries(optPools).map(([pool,ps])=>[
              pool,
              ps.open||0,
              ps.closed||0,
              `${((ps.win_rate||0)*100).toFixed(1)}%`,
              ps.ml_gate_active ? <Badge label="Active" color="bull"/> : <span style={{color:'var(--muted)',fontSize:11}}>⏳ {50-(ps.closed||0)} more</span>,
              age(ps.last_trade),
            ])}
          />
        )}
        <div style={{fontSize:10,color:'var(--muted)',marginTop:8}}>SPX 0-1DTE paper trades. ML gate activates at ≥50 closed per pool.</div>
      </Card>

      {od.open_positions?.length > 0 && (
        <Card title={`Options Open Positions (${od.open_positions.length})`}>
          <Table
            cols={['Pool','Dir','Strike','DTE','Entry $','Age']}
            rows={od.open_positions.map(p=>[
              p.pool||'',
              <span style={{color:p.direction==='CALL'?'var(--green)':'var(--red)',fontWeight:700}}>{p.direction}</span>,
              p.strike||'—',
              p.dte||'—',
              `$${num(p.entry_premium,2)}`,
              age(p.entry_time),
            ])}
          />
        </Card>
      )}
    </div>
  )
}

// ══════════════════════════════════════════════════════════════
// TAB 6 — NEWS
// ══════════════════════════════════════════════════════════════
function NewsTab() {
  const { data, err, load, reload } = useLoad(() => _get('/news/feed'))

  if (load && !data) return <Spinner/>
  if (err && !data)  return <Err e={err}/>

  const vel   = data?.velocity || ''
  const items = data?.items    || []

  const sentC = s => s==='BULLISH'?'var(--green)':s==='BEARISH'?'var(--red)':'var(--muted)'
  const sentI = s => s==='BULLISH'?'📈':s==='BEARISH'?'📉':'•'

  return (
    <div className="content">
      {vel && (
        <div className={`velocity ${vel==='ACCELERATING'?'acc':vel==='QUIET'?'quiet':'norm'}`} style={{margin:'10px 12px 4px'}}>
          {vel==='ACCELERATING'?'⚡ News Accelerating':vel==='QUIET'?'🟢 Quiet':'📰 Normal'}
          <span style={{marginLeft:'auto',fontSize:12}}>Agg {data.agg_score>=0?'+':''}{((data.agg_score||0)*100).toFixed(0)}%</span>
        </div>
      )}

      {data.high_impact_event?.detected && (
        <div style={{margin:'4px 12px 8px',background:'rgba(245,158,11,.1)',border:'1px solid rgba(245,158,11,.3)',borderRadius:8,padding:'8px 12px',display:'flex',gap:8,alignItems:'center'}}>
          <span>⚡</span>
          <div>
            <div style={{fontWeight:700,color:'var(--gold)',fontSize:13}}>{data.high_impact_event.name||'Event'}</div>
            {data.high_impact_event.urgency != null && <div style={{fontSize:11,color:'var(--muted)'}}>urgency {num(data.high_impact_event.urgency,2)}</div>}
          </div>
        </div>
      )}

      <Card title={`Headlines (${items.length})`}>
        <div style={{display:'flex',justifyContent:'flex-end',marginBottom:8}}>
          <span style={{fontSize:11,color:'var(--gold)',cursor:'pointer'}} onClick={reload}>↻ Refresh</span>
        </div>
        {items.length === 0 ? <div style={{color:'var(--muted)',fontSize:13}}>No recent news.</div> :
        items.map((item,i) => (
          <div key={i} style={{borderBottom:'1px solid var(--border)',padding:'10px 0'}}>
            <div style={{fontSize:13,lineHeight:1.4,marginBottom:4}}>
              {item.url
                ? <a href={item.url} target="_blank" rel="noopener noreferrer" style={{color:'var(--text)',textDecoration:'none'}}>{item.headline}</a>
                : item.headline}
            </div>
            <div style={{fontSize:11,color:'var(--muted)',display:'flex',gap:10,flexWrap:'wrap'}}>
              <span>{item.source}</span>
              <span>{item.age_min}m ago</span>
              <span style={{color:sentC(item.sentiment)}}>{sentI(item.sentiment)} {item.sentiment}</span>
              <span style={{color:'var(--muted)'}}>{item.score>=0?'+':''}{((item.score||0)*100).toFixed(0)}%</span>
            </div>
          </div>
        ))}
      </Card>
    </div>
  )
}

// ══════════════════════════════════════════════════════════════
// ALERTS TAB (push notifications)
// ══════════════════════════════════════════════════════════════
function AlertsTab() {
  const [status,  setStatus]  = useState('idle')
  const [message, setMessage] = useState('')

  useEffect(() => {
    if (!('Notification' in window) || !('serviceWorker' in navigator)) { setStatus('unsupported'); return }
    if (Notification.permission === 'granted') setStatus('on')
  }, [])

  async function toggle() {
    if (status === 'on') { setMessage('To disable, revoke notification permission in browser settings.'); return }
    if (status === 'unsupported') return
    setStatus('requesting')
    try {
      const perm = await Notification.requestPermission()
      if (perm !== 'granted') { setStatus('idle'); setMessage('Permission denied.'); return }
      const reg = await navigator.serviceWorker.ready
      if (!VAPID_PUBLIC) { setStatus('on'); setMessage('Alerts enabled (foreground only — no VAPID key configured).'); return }
      const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: VAPID_PUBLIC })
      await subscribePush(sub.toJSON())
      setStatus('on'); setMessage('Background alerts active!')
    } catch(e) { setStatus('error'); setMessage(`Error: ${e.message}`) }
  }

  return (
    <div className="content">
      <Card title="Push Notifications">
        <p style={{fontSize:13,color:'var(--muted)',marginBottom:14,lineHeight:1.5}}>
          Background alerts when a high-confidence signal fires (≥65%), a regime shift is detected, or news velocity spikes.
        </p>
        {status === 'unsupported'
          ? <div style={{color:'var(--red)',fontSize:13}}>Not supported in this browser.</div>
          : <button className={`alert-btn ${status==='on'?'on':'off'}`} onClick={toggle}>
              {status==='on'?'🔔 Alerts ON':status==='requesting'?'…':'🔕 Enable Alerts'}
            </button>}
        {message && <p style={{marginTop:12,fontSize:12,color:'var(--muted)'}}>{message}</p>}
      </Card>

      <Card title="Alert Triggers">
        <ul style={{fontSize:13,color:'var(--muted)',lineHeight:1.8,paddingLeft:16}}>
          <li>Signal confidence ≥ 65% (any pool)</li>
          <li>Market regime shift detected</li>
          <li>High-impact economic event imminent</li>
          <li>News velocity → ACCELERATING</li>
        </ul>
      </Card>

      <Card title="Install as App">
        <p style={{fontSize:13,color:'var(--muted)',lineHeight:1.6}}>
          <strong style={{color:'var(--text)'}}>iPhone:</strong> tap Share → Add to Home Screen<br/>
          <strong style={{color:'var(--text)'}}>Android:</strong> tap ⋮ → Add to Home Screen
        </p>
      </Card>
    </div>
  )
}

// ══════════════════════════════════════════════════════════════
// APP ROOT
// ══════════════════════════════════════════════════════════════
export default function App() {
  const [tab, setTab] = useState('pulse')

  const pulse  = useLoad(() => getPulse(),              [])
  const health = useLoad(() => _get('/health'),         [])

  // Auto-refresh pulse every 60s, health every 120s
  useEffect(() => { const id = setInterval(pulse.reload,  60_000); return () => clearInterval(id) }, [])
  useEffect(() => { const id = setInterval(health.reload, 120_000); return () => clearInterval(id) }, [])

  return (
    <>
      <nav className="nav">
        {TABS.map(t => (
          <button key={t.id} className={tab===t.id?'active':''} onClick={()=>setTab(t.id)}>
            <span className="ico">{t.ico}</span>
            {t.label}
          </button>
        ))}
      </nav>

      <div style={{flex:1}}>
        {tab==='pulse'   && <PulseTab   pulse={pulse} health={health}/>}
        {tab==='signals' && <SignalsTab pulse={pulse}/>}
        {tab==='ml'      && <MLTab      health={health}/>}
        {tab==='swing'   && <SwingTab/>}
        {tab==='macro'   && <MacroTab   health={health}/>}
        {tab==='news'    && <NewsTab/>}
      </div>
    </>
  )
}
