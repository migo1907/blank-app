import React, { useState, useEffect, useCallback, useRef } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  RadialBarChart, RadialBar, Cell,
  AreaChart, Area, LineChart, Line,
  ReferenceLine
} from 'recharts'
import { Crosshair, BarChart3, CalendarDays, Briefcase, Newspaper } from 'lucide-react'
import { getDashboard, subscribePush, VAPID_PUBLIC,
  getMarketOverview, getMarketQuotes, getMarketTicker, getMarketCompare, getMarketWrap, getMarketCommentary,
  getMarketSparklines, getOptionsFlow, getEconomicCalendar, getEarningsCalendar } from './api'

const BASE   = 'https://blank-app-production-a8bd.up.railway.app'
const SECRET = 'gold2026'

const C = { green:'#22c55e', red:'#ef4444', muted:'#64748b', gold:'#f59e0b', blue:'#3b82f6', purple:'#a855f7', indigo:'#6366f1' }

async function api(path, params = {}) {
  const url = new URL(BASE + path)
  url.searchParams.set('secret', SECRET)
  Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v))
  const r = await fetch(url.toString(), { signal: AbortSignal.timeout(20000) })
  if (!r.ok) throw new Error(`${r.status}`)
  return r.json()
}

const BOTTOM_NAV = [
  { id: 'signals',   Icon: Crosshair, label: 'Signals'   },
  { id: 'markets',   Icon: BarChart3, label: 'Markets'   },
  { id: 'calendar',  Icon: CalendarDays, label: 'Calendar' },
  { id: 'portfolio', Icon: Briefcase, label: 'Portfolio' },
  { id: 'news',      Icon: Newspaper, label: 'News'      },
]

const GOLD_POOLS  = ['XAUUSD_2M','XAUUSD_5M','XAUUSD_15M','XAUUSD_30M','XAUUSD_1H']
const STOCK_POOLS = ['STOCKS_MOMENTUM_15M','STOCKS_MOMENTUM_30M','STOCKS_QUALITY_15M','STOCKS_QUALITY_30M','STOCKS_INDEX_15M','STOCKS_INDEX_30M','STOCKS_QQQ_15M','STOCKS_QQQ_30M','STOCKS_SPX500_15M','STOCKS_SPX500_30M']

// ── Utils ──────────────────────────────────────────────────────────────────────
const bc   = b => b==='BULLISH'?'bull':b==='BEARISH'?'bear':'neut'
const bico = b => b==='BULLISH'?'▲':b==='BEARISH'?'▼':'—'
const bclr = b => b==='BULLISH'?'var(--green)':b==='BEARISH'?'var(--red)':'var(--muted)'
const n    = (v,d=2) => v!=null ? Number(v).toFixed(d) : '—'
const pct  = v => `${(Number(v||0)*100).toFixed(1)}%`
const cert = c => ({'HIGH':'🎯','MODERATE':'〰️','LOW':'❓'}[c]||'')
const age  = iso => {
  if (!iso) return '—'
  try {
    const m = Math.floor((Date.now()-new Date(iso))/60000)
    return m<60?`${m}m ago`:`${Math.floor(m/60)}h${m%60}m ago`
  } catch { return '—' }
}
const money = (v,d=2) => v ? `$${Number(v).toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d})}` : '—'
const dirClr = d => d==='LONG'?'var(--green)':d==='SHORT'?'var(--red)':'var(--muted)'

function useLoad(fn, deps=[]) {
  const [data,setData]=useState(null),[err,setErr]=useState(null),[load,setLoad]=useState(true)
  const go = useCallback(async()=>{
    setLoad(true)
    try{setData(await fn());setErr(null)}
    catch(e){setErr(e.message)}
    finally{setLoad(false)}
  },deps)
  useEffect(()=>{go()},[go])
  return {data,err,load,reload:go}
}

function Spinner() {
  return <div className="spin"><svg viewBox="0 0 24 24" fill="none" stroke="var(--gold)" strokeWidth="2"><circle cx="12" cy="12" r="10" strokeOpacity=".2"/><path d="M12 2a10 10 0 0 1 10 10"/></svg></div>
}
function Err({e}) { return <div style={{padding:20,color:'var(--red)',fontSize:13}}>⚠️ {e}</div> }

// Custom tooltip for charts
const ChartTip = ({active,payload,label,fmt}) => {
  if(!active||!payload?.length) return null
  return (
    <div style={{background:'var(--card)',border:'1px solid var(--border)',borderRadius:8,padding:'8px 12px',fontSize:11}}>
      <div style={{color:'var(--muted)',marginBottom:4}}>{label}</div>
      {payload.map((p,i)=>(
        <div key={i} style={{color:p.color||'var(--gold)',fontWeight:700}}>{p.name}: {fmt?fmt(p.value):p.value}</div>
      ))}
    </div>
  )
}

// Score ring (SVG gauge)
function ScoreRing({value,size=80,color,label,sublabel}) {
  const r=30, c=2*Math.PI*r, pct=Math.min(1,Math.max(0,value||0)), dash=pct*c
  return (
    <div className="ring-wrap">
      <svg width={size} height={size} viewBox="0 0 80 80">
        <circle cx="40" cy="40" r={r} fill="none" stroke="rgba(255,255,255,.06)" strokeWidth="8"/>
        <circle cx="40" cy="40" r={r} fill="none" stroke={color||'var(--gold)'} strokeWidth="8"
          strokeDasharray={`${dash} ${c}`} strokeDashoffset={c/4} strokeLinecap="round"
          style={{transition:'stroke-dasharray .6s cubic-bezier(.4,0,.2,1)'}}/>
        <text x="40" y="38" textAnchor="middle" fill={color||'var(--gold)'} fontSize="14" fontWeight="800">{Math.round(pct*100)}%</text>
        {sublabel&&<text x="40" y="52" textAnchor="middle" fill="var(--muted)" fontSize="8">{sublabel}</text>}
      </svg>
      {label&&<div style={{fontSize:10,color:'var(--muted)',marginTop:2,textAlign:'center',fontWeight:700,textTransform:'uppercase',letterSpacing:'.06em'}}>{label}</div>}
    </div>
  )
}

// Diverging bias bar centered on neutral
function BiasBar({value,label,height=8}){
  // value 0..1 ; 0.5 = neutral. Diverging bar centered on neutral.
  const v=Math.min(1,Math.max(0,value??0.5)), p=Math.round(v*100)
  const lbl=v>0.6?'Bullish':v<0.4?'Bearish':'Neutral'
  const clr=v>0.6?'var(--green)':v<0.4?'var(--red)':'var(--gold)'
  return (
    <div style={{width:'100%'}}>
      <div style={{display:'flex',justifyContent:'space-between',fontSize:11,marginBottom:4}}>
        <span style={{color:'var(--muted)',fontWeight:700,textTransform:'uppercase',letterSpacing:'.06em',fontSize:10}}>{label}</span>
        <span style={{color:clr,fontWeight:700}}>{lbl} {p}%</span>
      </div>
      <div style={{background:'rgba(255,255,255,.06)',borderRadius:4,height,position:'relative'}}>
        <div style={{position:'absolute',left:'50%',top:0,bottom:0,width:1,background:'var(--muted)',opacity:.4}}/>
        <div style={{position:'absolute',height,borderRadius:4,left:p>=50?'50%':`${p}%`,width:`${Math.abs(p-50)}%`,background:clr,transition:'all .6s'}}/>
      </div>
    </div>
  )
}

// Horizontal bar chart for features/candidates
function HBar({data,color,fmt,maxItems=8}) {
  if(!data?.length) return <div style={{color:'var(--muted)',fontSize:12,padding:'8px 0'}}>No data.</div>
  const rows = data.slice(0,maxItems)
  const max  = Math.max(...rows.map(d=>Math.abs(d.value||0)))
  return (
    <div style={{display:'flex',flexDirection:'column',gap:5}}>
      {rows.map((d,i)=>(
        <div key={i}>
          <div style={{display:'flex',justifyContent:'space-between',fontSize:11,marginBottom:2}}>
            <span style={{color:'var(--text)',maxWidth:'60%',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{d.name}</span>
            <span style={{color:color||'var(--gold)',fontWeight:700}}>{fmt?fmt(d.value):n(d.value,3)}</span>
          </div>
          <div className="bar-wrap">
            <div className="bar-fill" style={{width:`${max>0?(Math.abs(d.value)/max*100):0}%`,background:color||'var(--gold)'}}/>
          </div>
        </div>
      ))}
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════
// TAB 1 — MORNING BRIEF
// ══════════════════════════════════════════════════════════════════
function BriefTab() {
  const {data,err,load,reload} = useLoad(()=>api('/brief/data'))
  const [asset,setAsset] = useState('XAUUSD')

  if(load&&!data) return <Spinner/>
  if(err&&!data)  return <Err e={err}/>
  if(!data) return null

  const ASSET_LABELS = {XAUUSD:'🥇 Gold',SPY:'📈 SPY',QQQ:'📊 QQQ'}
  const tc    = data.assets?.[asset] || {}
  const lvl   = data.levels?.[asset] || {}
  const mac   = data.macro    || {}
  const evts  = data.events_list || []

  const bias  = tc.composite_bias ?? tc.bias ?? null
  const biasP = bias != null ? Math.round(bias*100) : null
  const biasLabel = bias==null?'—':bias>0.6?'Bullish':bias<0.4?'Bearish':'Neutral'
  const biasClr = bias==null?'var(--muted)':bias>0.6?'var(--green)':bias<0.4?'var(--red)':'var(--gold)'

  const mom   = tc.momentum_20d ?? tc.momentum ?? null
  const rsi   = tc.rsi ?? null
  const rngP  = tc.range_position_60d ?? tc.range_position ?? null
  const ma20  = tc.ma20, ma50=tc.ma50, ma200=tc.ma200
  const trend = tc.trend ?? tc.trend_stack ?? null

  const pivot = lvl.pivot, r1=lvl.r1, r2=lvl.r2, r3=lvl.r3, s1=lvl.s1, s2=lvl.s2, s3=lvl.s3

  return (
    <div className="content">
      {/* Header */}
      <div className="grad-header" style={{display:'flex',justifyContent:'space-between',alignItems:'flex-start'}}>
        <div>
          <div style={{fontSize:11,color:'var(--muted)',fontWeight:700,letterSpacing:'.08em',textTransform:'uppercase',marginBottom:4}}>Morning Brief</div>
          <div style={{fontSize:13,color:'var(--text)',fontWeight:600}}>{new Date().toLocaleDateString('en-US',{weekday:'long',day:'numeric',month:'short',year:'numeric'})}</div>
          {data.generated_at && <div style={{fontSize:10,color:'var(--muted)',marginTop:2}}>Updated {new Date(data.generated_at).toLocaleTimeString()}</div>}
        </div>
        <button onClick={reload} style={{background:'rgba(245,158,11,.12)',border:'1px solid rgba(245,158,11,.3)',color:'var(--gold)',borderRadius:8,padding:'6px 12px',fontSize:11,fontWeight:700,cursor:'pointer'}}>↻ Refresh</button>
      </div>

      {/* Asset selector */}
      <div className="filter-bar">
        {Object.entries(ASSET_LABELS).map(([k,v])=>(
          <button key={k} className={`filter-chip ${asset===k?'active':''}`} onClick={()=>setAsset(k)}>{v}</button>
        ))}
      </div>

      {/* Technical snapshot */}
      <div className="card">
        <div className="card-title">{ASSET_LABELS[asset]} — Technical Snapshot</div>
        <div style={{display:'flex',gap:16,alignItems:'center',marginBottom:16}}>
          <ScoreRing value={bias} size={80} color={biasClr} label="Bias" sublabel={biasLabel}/>
          <div style={{flex:1}}>
            {trend && <div style={{fontSize:13,fontWeight:700,color:biasClr,marginBottom:4}}>{trend}</div>}
            {mom!=null && <div style={{fontSize:12,color:'var(--text)',marginBottom:3}}>20d Momentum: <span style={{color:mom>=0?'var(--green)':'var(--red)',fontWeight:700}}>{mom>=0?'+':''}{n(mom,2)}%</span></div>}
            {rsi!=null && <div style={{fontSize:12,color:'var(--text)',marginBottom:3}}>RSI: <span style={{color:'var(--gold)',fontWeight:700}}>{n(rsi,1)}</span></div>}
            {rngP!=null && <div style={{fontSize:12,color:'var(--text)'}}>60d Range: <span style={{color:'var(--gold)',fontWeight:700}}>{n(rngP,0)}%</span></div>}
          </div>
        </div>

        {/* Moving averages */}
        {(ma20||ma50||ma200) && (
          <div style={{display:'grid',gridTemplateColumns:'repeat(3,1fr)',gap:6,marginBottom:12}}>
            {[[ma20,'MA20'],[ma50,'MA50'],[ma200,'MA200']].map(([v,l])=>v&&(
              <div key={l} style={{background:'rgba(0,0,0,.3)',borderRadius:8,padding:'8px',textAlign:'center'}}>
                <div style={{fontSize:9,color:'var(--muted)',fontWeight:700,textTransform:'uppercase',marginBottom:2}}>{l}</div>
                <div style={{fontSize:12,fontWeight:700,color:'var(--gold)'}}>{money(v)}</div>
              </div>
            ))}
          </div>
        )}

        {/* Bias bar */}
        {biasP!=null && (
          <div>
            <div style={{display:'flex',justifyContent:'space-between',fontSize:11,marginBottom:4}}>
              <span style={{color:'var(--red)',fontWeight:700}}>Bearish</span>
              <span style={{color:biasClr,fontWeight:700}}>{biasP}% {biasLabel}</span>
              <span style={{color:'var(--green)',fontWeight:700}}>Bullish</span>
            </div>
            <div style={{background:'rgba(255,255,255,.06)',borderRadius:4,height:8,position:'relative'}}>
              <div style={{position:'absolute',left:'50%',top:0,bottom:0,width:1,background:'var(--muted)',opacity:.4}}/>
              <div style={{
                position:'absolute', height:8, borderRadius:4,
                left: biasP>=50 ? '50%' : `${biasP}%`,
                width: `${Math.abs(biasP-50)}%`,
                background: biasP>=50?'var(--green)':'var(--red)',
                transition:'all .6s'
              }}/>
            </div>
          </div>
        )}
      </div>

      {/* Pivot levels */}
      {pivot && (
        <div className="card">
          <div className="card-title">Key Levels</div>
          <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:8}}>
            <div>
              <div style={{fontSize:10,color:'var(--red)',fontWeight:700,marginBottom:6,textTransform:'uppercase',letterSpacing:'.06em'}}>🔴 Resistance</div>
              {[[r3,'R3'],[r2,'R2'],[r1,'R1']].map(([v,l])=>v&&(
                <div key={l} className="level-row">
                  <span style={{color:'var(--muted)',fontWeight:700,fontSize:10}}>{l}</span>
                  <span style={{color:'var(--red)',fontWeight:700}}>{money(v,asset==='XAUUSD'?2:2)}</span>
                </div>
              ))}
              <div className="level-row" style={{borderTop:'1px solid rgba(245,158,11,.3)',marginTop:4,paddingTop:8}}>
                <span style={{color:'var(--gold)',fontWeight:800,fontSize:11}}>PIVOT</span>
                <span style={{color:'var(--gold)',fontWeight:800}}>{money(pivot)}</span>
              </div>
              {[[s1,'S1'],[s2,'S2'],[s3,'S3']].map(([v,l])=>v&&(
                <div key={l} className="level-row">
                  <span style={{color:'var(--muted)',fontWeight:700,fontSize:10}}>{l}</span>
                  <span style={{color:'var(--green)',fontWeight:700}}>{money(v)}</span>
                </div>
              ))}
            </div>
            <div>
              <div style={{fontSize:10,color:'var(--muted)',fontWeight:700,marginBottom:6,textTransform:'uppercase',letterSpacing:'.06em'}}>Bias Zones</div>
              <div style={{fontSize:12,color:'var(--text)',lineHeight:1.8}}>
                {pivot && <div><span style={{color:'var(--green)',fontWeight:700}}>Above {money(pivot)}</span><br/><span style={{color:'var(--muted)',fontSize:11}}>→ Bullish bias</span></div>}
                {pivot && <div style={{marginTop:8}}><span style={{color:'var(--red)',fontWeight:700}}>Below {money(pivot)}</span><br/><span style={{color:'var(--muted)',fontSize:11}}>→ Bearish bias</span></div>}
              </div>
              {tc.atr && <div style={{marginTop:12,background:'rgba(0,0,0,.3)',borderRadius:8,padding:'8px'}}>
                <div style={{fontSize:9,color:'var(--muted)',fontWeight:700,textTransform:'uppercase',marginBottom:2}}>ATR (Expected Range)</div>
                <div style={{fontSize:13,fontWeight:700,color:'var(--gold)'}}>{money(tc.atr)}</div>
              </div>}
            </div>
          </div>
        </div>
      )}

      {/* Macro (gold only) */}
      {asset==='XAUUSD' && (
        <div className="card">
          <div className="card-title">Macro Intelligence</div>
          <div className="metrics" style={{marginBottom:12}}>
            <div className="metric">
              <div className="metric-val" style={{fontSize:13}}>{mac.label||'—'}</div>
              <div className="metric-lbl">Macro Bias</div>
            </div>
            {mac.vix!=null&&<div className="metric"><div className="metric-val" style={{fontSize:14}}>{n(mac.vix,1)}</div><div className="metric-lbl">VIX</div></div>}
            {mac.real_yield!=null&&<div className="metric"><div className="metric-val" style={{fontSize:13}}>{n(mac.real_yield,2)}%</div><div className="metric-lbl">Real Yield</div></div>}
          </div>
          {mac.components && Object.keys(mac.components).length>0 && (
            <HBar
              data={Object.entries(mac.components).map(([k,v])=>({name:k.replace(/_/g,' '),value:typeof v==='number'?v:0}))}
              color="var(--gold)"
            />
          )}
        </div>
      )}

      {/* Economic calendar */}
      {evts.length>0 && (
        <div className="card">
          <div className="card-title">📆 Economic Calendar (Dubai Time)</div>
          {evts.map((e,i)=>(
            <div key={i} style={{display:'flex',gap:10,padding:'8px 0',borderBottom:i<evts.length-1?'1px solid var(--border)':'none',alignItems:'center'}}>
              <span style={{color:'var(--gold)',fontWeight:700,fontSize:12,minWidth:42,fontVariantNumeric:'tabular-nums'}}>{e.time_dubai}</span>
              <span style={{flex:1,fontSize:12,color:'var(--text)'}}>{e.name}</span>
              <span style={{fontSize:10,padding:'2px 8px',borderRadius:20,background:'rgba(239,68,68,.12)',color:'var(--red)',fontWeight:700}}>HIGH</span>
            </div>
          ))}
        </div>
      )}

      {/* News sentiment */}
      <div className="card">
        <div className="card-title">News Sentiment</div>
        <div style={{display:'flex',gap:12,alignItems:'center'}}>
          <ScoreRing
            value={(data.news_sentiment+1)/2}
            size={70}
            color={data.news_sentiment>0.1?'var(--green)':data.news_sentiment<-0.1?'var(--red)':'var(--muted)'}
            sublabel={data.news_sentiment>0.1?'Bullish':data.news_sentiment<-0.1?'Bearish':'Neutral'}
          />
          <div>
            <div style={{fontSize:13,fontWeight:700,color:'var(--text)',marginBottom:4}}>
              Aggregate Score: <span style={{color:'var(--gold)'}}>{data.news_sentiment>=0?'+':''}{n(data.news_sentiment,3)}</span>
            </div>
            {data.news_velocity?.label && (
              <div style={{fontSize:12,color:'var(--muted)'}}>
                Velocity: <span style={{color:data.news_velocity.label==='ACCELERATING'?'var(--red)':data.news_velocity.label==='QUIET'?'var(--green)':'var(--muted)',fontWeight:700}}>
                  {data.news_velocity.label}
                </span>
                {data.news_velocity.multiplier&&<span style={{color:'var(--muted)'}}> ×{n(data.news_velocity.multiplier,1)}</span>}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════
// TAB 2 — PULSE
// ══════════════════════════════════════════════════════════════════
function PulseTab({pulse,health}) {
  const pd = pulse.data, hd=health.data
  if(pulse.load&&!pd) return <Spinner/>
  if(pulse.err&&!pd)  return <Err e={pulse.err}/>

  const pools = pd?.pools || {}
  const imkt  = hd?.intermarket || {}
  const vel   = pd?.news_velocity || {}

  // Pool confidence chart data
  const poolChart = [...GOLD_POOLS,...STOCK_POOLS]
    .filter(p=>pools[p])
    .map(p=>({
      name: p.replace('XAUUSD_','').replace('STOCKS_',''),
      conf: Math.round((pools[p].confidence||0)*100),
      dir:  pools[p].direction,
      fill: pools[p].direction==='LONG'?C.green:pools[p].direction==='SHORT'?C.red:C.muted
    }))

  return (
    <div className="content">
      {/* Bias rings */}
      <div className="card">
        <div className="card-title">Market Pulse</div>
        <div style={{display:'flex',flexDirection:'column',gap:12,marginBottom:16}}>
          <BiasBar value={(pd?.gold_score||0)+0.5} label="Gold"/>
          <BiasBar value={pd?.overall_score!=null?(pd.overall_score+0.5):(((pd?.gold_score||0)+(pd?.stocks_score||0))/2+0.5)} label="Overall"/>
          <BiasBar value={(pd?.stocks_score||0)+0.5} label="Stocks"/>
        </div>
        <div style={{display:'flex',gap:10,flexWrap:'wrap',justifyContent:'center'}}>
          <span className={`bias ${bc(pd?.gold_bias)}`}>{bico(pd?.gold_bias)} Gold</span>
          <span className={`bias ${bc(pd?.overall_bias)}`}>{bico(pd?.overall_bias)} Overall</span>
          <span className={`bias ${bc(pd?.stocks_bias)}`}>{bico(pd?.stocks_bias)} Stocks</span>
        </div>
      </div>

      {/* Pool confidence chart */}
      <div className="card">
        <div className="card-title">Pool Confidence Chart</div>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={poolChart} layout="vertical" margin={{left:0,right:16,top:0,bottom:0}}>
            <XAxis type="number" domain={[0,100]} tick={{fill:'#64748b',fontSize:10}} tickFormatter={v=>`${v}%`}/>
            <YAxis type="category" dataKey="name" tick={{fill:'#94a3b8',fontSize:9}} width={80}/>
            <Tooltip content={<ChartTip fmt={v=>`${v}%`}/>}/>
            <Bar dataKey="conf" radius={3} name="Confidence">
              {poolChart.map((e,i)=><Cell key={i} fill={e.fill}/>)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Metrics row */}
      <div className="card">
        <div className="card-title">Market Context</div>
        <div className="metrics">
          <div className="metric"><div className="metric-val" style={{fontSize:13}}>{pd?.session?.toUpperCase()||'—'}</div><div className="metric-lbl">Session</div></div>
          {imkt.vix!=null&&<div className="metric"><div className="metric-val">{n(imkt.vix,1)}</div><div className="metric-lbl">VIX</div></div>}
          {pd?.macro_label&&<div className="metric"><div className="metric-val" style={{fontSize:12}}>{pd.macro_label}</div><div className="metric-lbl">Macro</div></div>}
          {pd?.macro_bias!=null&&<div className="metric"><div className="metric-val" style={{fontSize:13}}>{pd.macro_bias>=0?'+':''}{n(pd.macro_bias,2)}</div><div className="metric-lbl">Macro Score</div></div>}
          {imkt.dxy_break!=null&&<div className="metric"><div className="metric-val" style={{fontSize:14}}>{imkt.dxy_break?'✅':'❌'}</div><div className="metric-lbl">DXY Break</div></div>}
          {hd&&<div className="metric"><div className="metric-val" style={{fontSize:12}}>{hd.status?.toUpperCase()||'—'}</div><div className="metric-lbl">System</div></div>}
        </div>
      </div>

      {pd?.next_event?.detected&&(
        <div className="event-card">
          <span style={{fontSize:20}}>⚡</span>
          <div>
            <div style={{fontWeight:700,color:'var(--gold)',fontSize:13}}>{pd.next_event.name||'High-impact event'}</div>
            {pd.next_event.minutes_away!=null&&<div style={{fontSize:11,color:'var(--muted)'}}>in {pd.next_event.minutes_away} min</div>}
          </div>
        </div>
      )}

      {vel.label&&(
        <div className={`vel ${vel.label==='ACCELERATING'?'acc':vel.label==='QUIET'?'quiet':'norm'}`}>
          {vel.label==='ACCELERATING'?'⚡ News Accelerating':vel.label==='QUIET'?'🟢 News Quiet':'📰 News Normal'}
          {vel.multiplier&&<span style={{marginLeft:'auto',opacity:.7}}>×{n(vel.multiplier,1)}</span>}
        </div>
      )}

      <div style={{padding:'4px 12px 0',fontSize:10,color:'var(--muted)',display:'flex',justifyContent:'space-between'}}>
        <span>Updated {pd?.updated_at?new Date(pd.updated_at).toLocaleTimeString():'—'}</span>
        <span style={{color:'var(--gold)',cursor:'pointer'}} onClick={pulse.reload}>↻ Refresh</span>
      </div>
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════
// TAB 3 — SIGNALS
// ══════════════════════════════════════════════════════════════════
function PoolDetail({pool}) {
  const {data,err,load} = useLoad(()=>getDashboard(pool),[pool])
  if(load) return <div style={{padding:'8px 0',color:'var(--muted)',fontSize:12}}>Loading…</div>
  if(err||!data) return null
  const m=data.model||{}, rf=data.rf||{}
  return (
    <div style={{paddingTop:10,borderTop:'1px solid var(--border)',marginTop:8}}>
      <div style={{display:'grid',gridTemplateColumns:'repeat(3,1fr)',gap:6,marginBottom:10}}>
        <div className="metric"><div className="metric-val" style={{fontSize:14}}>{n(m.win_rate,0)}%</div><div className="metric-lbl">Win Rate</div></div>
        <div className="metric"><div className="metric-val" style={{fontSize:14}}>{m.total_trades||0}</div><div className="metric-lbl">Trades</div></div>
        <div className="metric"><div className="metric-val" style={{fontSize:12}}>{rf.trained?'✅':'⏳'}</div><div className="metric-lbl">RF Trained</div></div>
      </div>
      {m.top_features?.length>0&&(
        <div style={{marginBottom:8}}>
          <div style={{fontSize:9,color:'var(--muted)',fontWeight:700,textTransform:'uppercase',letterSpacing:'.08em',marginBottom:6}}>KNN Top Features</div>
          <HBar data={m.top_features.slice(0,5).map(f=>({name:f.name,value:f.weight}))} color="var(--gold)"/>
        </div>
      )}
      {rf.top_features?.length>0&&(
        <div style={{marginBottom:8}}>
          <div style={{fontSize:9,color:'var(--muted)',fontWeight:700,textTransform:'uppercase',letterSpacing:'.08em',marginBottom:6}}>RF Top Features</div>
          <HBar data={rf.top_features.slice(0,5).map(f=>({name:f.name,value:f.importance}))} color="var(--blue)"/>
        </div>
      )}
      {data.recent_trades?.length>0&&(
        <div>
          <div style={{fontSize:9,color:'var(--muted)',fontWeight:700,textTransform:'uppercase',letterSpacing:'.08em',marginBottom:6}}>Recent Trades</div>
          {data.recent_trades.slice(0,5).map((t,i)=>(
            <div key={i} style={{display:'flex',gap:8,padding:'4px 0',borderBottom:'1px solid rgba(30,30,58,.5)',fontSize:11,alignItems:'center'}}>
              <span style={{color:dirClr(t.direction),fontWeight:700,width:40}}>{t.direction==='LONG'?'▲ L':'▼ S'}</span>
              <span style={{color:t.outcome==='WIN'?'var(--green)':t.outcome==='LOSS'?'var(--red)':'var(--muted)',fontWeight:700,width:52}}>{t.outcome}</span>
              <span style={{color:'var(--muted)'}}>{age(t.created_at)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

const TF_LABELS = {'2':'2M','5':'5M','15':'15M','30':'30M','60':'1H','240':'4H'}

function SignalsTab() {
  const {data, load, reload} = useLoad(()=>api('/signals/feed'))
  const [dirFilter, setDirFilter] = useState('ALL')
  const [tfFilter,  setTfFilter]  = useState('ALL')

  useEffect(()=>{ const id=setInterval(reload,30_000); return()=>clearInterval(id) },[])

  const signals = (data?.signals || []).filter(s=>{
    if(dirFilter!=='ALL' && s.direction!==dirFilter) return false
    if(tfFilter!=='ALL'  && String(s.timeframe)!==tfFilter) return false
    return true
  })

  const tierClr = t => t==='HIGH'?'var(--green)':t==='MED'?'var(--gold)':'var(--muted)'

  if(load && !data) return <Spinner/>

  return (
    <div className="content">
      {/* Filters */}
      <div className="filter-bar">
        {['ALL','5','15','30','60','240'].map(tf=>(
          <button key={tf} className={`filter-chip${tfFilter===tf?' active':''}`} onClick={()=>setTfFilter(tf)}>
            {tf==='ALL'?'All TF':TF_LABELS[tf]||tf+'M'}
          </button>
        ))}
      </div>
      <div className="filter-bar" style={{paddingTop:0}}>
        {['ALL','LONG','SHORT'].map(d=>(
          <button key={d} className={`filter-chip${dirFilter===d?' active':''}`} onClick={()=>setDirFilter(d)}
            style={dirFilter===d?{}:{color:d==='LONG'?'var(--green)':d==='SHORT'?'var(--red)':undefined}}>
            {d==='LONG'?'▲ Long':d==='SHORT'?'▼ Short':'All'}
          </button>
        ))}
        <button onClick={reload} style={{marginLeft:'auto',background:'none',border:'1px solid var(--border)',color:'var(--muted)',borderRadius:4,padding:'4px 10px',fontSize:11,cursor:'pointer'}}>↻</button>
      </div>

      {/* Signal cards */}
      {signals.length===0 ? (
        <div style={{padding:'40px 20px',textAlign:'center',color:'var(--muted)'}}>
          <div style={{fontSize:32,marginBottom:12}}>🧭</div>
          <div style={{fontSize:14,fontWeight:600,marginBottom:6}}>No signals yet</div>
          <div style={{fontSize:12}}>Signals appear here the moment TradingView fires an entry — same data as Telegram.</div>
        </div>
      ) : (
        <div style={{padding:'0 10px 16px',display:'flex',flexDirection:'column',gap:10}}>
          {signals.map((s,i)=>{
            const isLong = s.direction==='LONG'
            const clr    = isLong?'var(--green)':'var(--red)'
            const tf     = TF_LABELS[String(s.timeframe)] || `${s.timeframe}M`
            const qs     = s.quality_score
            const qClr   = qs==null?'var(--muted)':qs>=0.55?'var(--green)':qs>=0.40?'var(--gold)':'var(--red)'
            const qLbl   = qs==null?'—':qs>=0.55?'STRONG':qs>=0.40?'FAIR':'WEAK'
            const rr     = (s.entry_price&&s.sl&&s.tp1) ? Math.abs(s.tp1-s.entry_price)/Math.max(1e-9,Math.abs(s.entry_price-s.sl)) : null
            const rrClr  = rr==null?'var(--muted)':rr>=2?'var(--green)':rr>=1?'var(--gold)':'var(--red)'
            // Price ladder normalization
            const ladder = [['SL',s.sl,'var(--red)'],['Entry',s.entry_price,'var(--gold)'],['TP1',s.tp1,'var(--green)'],['TP2',s.tp2,'var(--green)'],['TP3',s.tp3,'var(--green)']]
              .filter(([,v])=>v!=null)
            const lvVals = ladder.map(([,v])=>v)
            const lvMin  = lvVals.length?Math.min(...lvVals):0
            const lvMax  = lvVals.length?Math.max(...lvVals):1
            const lvSpan = Math.max(1e-9,lvMax-lvMin)
            // Telegram-style fields
            const isGold     = ['XAUUSD','GOLD','GC'].includes(String(s.symbol||'').toUpperCase())
            const assetEmoji = isGold?'🥇':'📊'
            const dirEmoji   = isLong?'🟢':'🔴'
            const conf       = qs   // ML P(reach TP1+) → shown as Confidence
            const convHdr    = conf==null?null:conf>=1.0?'‼️ MAXIMUM CONVICTION':conf>=0.75?'‼️ HIGH CONVICTION':null
            const utcStamp   = s.fired_at ? (()=>{const d=new Date(s.fired_at);const p=x=>String(x).padStart(2,'0');const mon=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][d.getUTCMonth()];return `${p(d.getUTCHours())}:${p(d.getUTCMinutes())} UTC — ${d.getUTCDate()} ${mon} ${d.getUTCFullYear()}`})() : ''
            return (
              <div key={i} style={{
                background:'var(--surface)',border:`1px solid var(--border)`,
                borderLeft:`3px solid ${clr}`,borderRadius:6,padding:'12px'
              }}>
                {/* Conviction header */}
                {convHdr&&<div style={{fontSize:11,fontWeight:800,color:'var(--gold)',letterSpacing:'.04em',marginBottom:6}}>{convHdr}</div>}

                {/* Header row */}
                <div style={{display:'flex',justifyContent:'space-between',alignItems:'flex-start',marginBottom:8}}>
                  <div>
                    <div style={{fontSize:15,fontWeight:800,color:clr,letterSpacing:'.02em'}}>
                      {dirEmoji} {isLong?'LONG':'SHORT'} <span style={{color:'var(--text)'}}>— {assetEmoji} {s.symbol}</span>
                    </div>
                    <div style={{fontSize:12,color:'var(--text-mut)',fontWeight:600,marginTop:3}}>
                      {tf}{s.htf_context==='htf_direct'&&<span style={{marginLeft:6,fontSize:10,color:'var(--purple)',fontWeight:700}}>🏔 HTF</span>}
                    </div>
                  </div>
                  <div style={{display:'flex',alignItems:'center',gap:8}}>
                    {rr!=null&&(
                      <span style={{fontSize:10,fontWeight:700,color:rrClr,border:`1px solid ${rrClr}`,borderRadius:3,padding:'2px 7px',whiteSpace:'nowrap'}}>
                        R:R 1:{rr.toFixed(1)}
                      </span>
                    )}
                    <span style={{fontSize:10,color:tierClr(s.tier),fontWeight:700}}>{s.tier||'—'}</span>
                  </div>
                </div>

                {/* Confidence · Session · Event */}
                <div style={{display:'flex',flexWrap:'wrap',gap:'4px 14px',marginBottom:10,fontSize:12}}>
                  <span style={{color:'var(--text-mut)'}}>Confidence: <span style={{color:qClr,fontWeight:800}}>{conf!=null?`${(conf*100).toFixed(0)}%`:'—'}</span>{conf!=null&&<span style={{color:qClr,fontWeight:700,marginLeft:5,fontSize:10}}>{qLbl}</span>}</span>
                  {s.session&&<span style={{color:'var(--text-mut)'}}>Session: <span style={{color:'var(--text)',fontWeight:600}}>{s.session}</span></span>}
                  {s.event&&<span style={{color:'var(--red)',fontWeight:700}}>⚡ {s.event}</span>}
                </div>

                {/* Price ladder */}
                {ladder.length>1&&(
                  <div style={{position:'relative',height:26,marginBottom:10}}>
                    <div style={{position:'absolute',left:0,right:0,top:12,height:2,background:'var(--surface2)',borderRadius:2}}/>
                    {ladder.map(([lbl,val,c])=>{
                      const left=((val-lvMin)/lvSpan)*100
                      const op=lbl==='TP1'?1:lbl==='TP2'?0.7:lbl==='TP3'?0.45:1
                      return (
                        <div key={lbl} title={`${lbl} ${n(val,2)}`} style={{position:'absolute',left:`${left}%`,top:5,transform:'translateX(-50%)'}}>
                          <div style={{width:2,height:16,background:c,opacity:op,borderRadius:1}}/>
                        </div>
                      )
                    })}
                  </div>
                )}

                {/* Levels grid */}
                <div style={{display:'grid',gridTemplateColumns:'repeat(5,1fr)',gap:4,marginBottom:10}}>
                  {[['Entry',s.entry_price,'var(--text)',1],['TP1',s.tp1,'var(--green)',1],['TP2',s.tp2,'var(--green)',0.7],['TP3',s.tp3,'var(--green)',0.45],['SL',s.sl,'var(--red)',1]].map(([lbl,val,c,op])=>(
                    <div key={lbl} style={{background:'var(--surface2)',borderRadius:4,padding:'6px 4px',textAlign:'center'}}>
                      <div className="mono" style={{fontSize:11,fontWeight:700,color:c,opacity:op}}>{val?n(val,2):'—'}</div>
                      <div style={{fontSize:9,color:'var(--muted)',fontWeight:600,marginTop:1}}>{lbl}</div>
                    </div>
                  ))}
                </div>

                {/* Footer: velocity/HTF + UTC timestamp (Telegram style) */}
                <div style={{display:'flex',gap:8,flexWrap:'wrap',alignItems:'center',marginTop:2}}>
                  {s.velocity&&s.velocity!=='NORMAL'&&<span style={{fontSize:10,color:'var(--muted)',fontWeight:600}}>{s.velocity}</span>}
                  {s.htf_bias&&<span style={{fontSize:10,color:'var(--green)',fontWeight:600}}>HTF bias ✓</span>}
                  <span style={{marginLeft:'auto',fontSize:10,color:'var(--text-mut)'}}>⏰ {utcStamp}</span>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════
// TAB 5 — SWING
// ══════════════════════════════════════════════════════════════════
function SwingTab() {
  const stats=useLoad(()=>api('/swing/trades'))
  const cands=useLoad(()=>api('/swing/candidates'))
  const [showThesis,setShowThesis]=useState(false)
  const [convFilter,setConvFilter]=useState('ALL')
  const [sortBy,setSortBy]=useState('combined_score')

  const ss  = stats.data||{}
  const all = cands.data?.candidates||[]

  const filtered = all
    .filter(c=>convFilter==='ALL'||(c.conviction||'')==convFilter)
    .sort((a,b)=>(b[sortBy]||0)-(a[sortBy]||0))

  const top = all[0]

  // Score chart
  const chartData = filtered.slice(0,10).map(c=>({
    name: c.ticker,
    score: Math.round((c.combined_score||0)*100),
    fund:  Math.round((c.fundamental_score||0)*100),
    tech:  Math.round((c.technical_score||0)*100),
  }))

  if(stats.load&&!ss.open&&!ss.closed) return <Spinner/>

  return (
    <div className="content">
      {/* Stats */}
      <div className="card">
        <div className="card-title">Swing ML Training Pipeline</div>
        <div className="metrics">
          <div className="metric"><div className="metric-val">{ss.open||0}</div><div className="metric-lbl">Open</div></div>
          <div className="metric"><div className="metric-val">{ss.closed||0}</div><div className="metric-lbl">Closed</div></div>
          <div className="metric"><div className="metric-val">{ss.win_rate!=null?pct(ss.win_rate):'—'}</div><div className="metric-lbl">Win Rate</div></div>
          <div className="metric">
            <div className="metric-val" style={{fontSize:12,color:ss.ready?'var(--green)':'var(--gold)'}}>{ss.ready?'✅':'⏳'}</div>
            <div className="metric-lbl">{ss.ready?'ML Ready':`${50-(ss.closed||0)} left`}</div>
          </div>
        </div>
        {!ss.ready&&(
          <div style={{marginTop:10}}>
            <div style={{display:'flex',justifyContent:'space-between',fontSize:11,marginBottom:4}}>
              <span style={{color:'var(--muted)'}}>Progress to ML gate</span>
              <span style={{color:'var(--gold)',fontWeight:700}}>{ss.closed||0}/50</span>
            </div>
            <div className="bar-wrap"><div className="bar-fill" style={{width:`${((ss.closed||0)/50*100).toFixed(0)}%`,background:'var(--gold)'}}/></div>
          </div>
        )}
      </div>

      {/* Top pick */}
      {top&&(
        <div className="card" style={{borderColor:'rgba(245,158,11,.3)'}}>
          <div style={{display:'flex',justifyContent:'space-between',alignItems:'flex-start',marginBottom:12}}>
            <div>
              <div style={{fontSize:10,color:'var(--muted)',fontWeight:700,textTransform:'uppercase',marginBottom:4}}>Top Pick</div>
              <div style={{fontSize:26,fontWeight:800,color:'var(--gold)',letterSpacing:'-.01em'}}>{top.ticker}</div>
            </div>
            <div style={{textAlign:'right'}}>
              <ScoreRing value={top.combined_score||0} size={70} color={top.conviction==='STRONG'?'var(--green)':'var(--gold)'} sublabel={top.conviction||''}/>
            </div>
          </div>
          <div style={{display:'grid',gridTemplateColumns:'repeat(3,1fr)',gap:8,marginBottom:10}}>
            <div className="metric"><div className="metric-val" style={{fontSize:12}}>{top.entry?money(top.entry):'—'}</div><div className="metric-lbl">Entry</div></div>
            <div className="metric"><div className="metric-val" style={{fontSize:12,color:'var(--green)'}}>{top.tp?money(top.tp):'—'}</div><div className="metric-lbl">Target</div></div>
            <div className="metric"><div className="metric-val" style={{fontSize:12,color:'var(--red)'}}>{top.sl?money(top.sl):'—'}</div><div className="metric-lbl">Stop</div></div>
          </div>
          {top.thesis&&(
            <>
              <button onClick={()=>setShowThesis(!showThesis)}
                style={{background:'rgba(245,158,11,.1)',border:'1px solid rgba(245,158,11,.3)',color:'var(--gold)',borderRadius:8,padding:'8px 12px',fontSize:12,fontWeight:700,cursor:'pointer',width:'100%'}}>
                {showThesis?'▲ Hide Analysis':'▼ View Analysis & Thesis'}
              </button>
              {showThesis&&<div style={{marginTop:12,fontSize:12,lineHeight:1.7,color:'var(--text)',borderTop:'1px solid var(--border)',paddingTop:12}}>{top.thesis}</div>}
            </>
          )}
        </div>
      )}

      {/* Score comparison chart */}
      {chartData.length>0&&(
        <div className="card">
          <div className="card-title">Candidate Score Comparison (Top 10)</div>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={chartData} layout="vertical" margin={{left:0,right:8,top:0,bottom:0}}>
              <XAxis type="number" domain={[0,100]} tick={{fill:'#64748b',fontSize:9}} tickFormatter={v=>`${v}%`}/>
              <YAxis type="category" dataKey="name" tick={{fill:'#f59e0b',fontSize:10,fontWeight:700}} width={50}/>
              <Tooltip content={<ChartTip fmt={v=>`${v}%`}/>}/>
              <Bar dataKey="fund" name="Fundamental" fill={C.indigo} radius={[0,0,0,0]} stackId="a"/>
              <Bar dataKey="tech"  name="Technical"   fill={C.green} radius={[0,3,3,0]} stackId="a"/>
            </BarChart>
          </ResponsiveContainer>
          <div style={{display:'flex',gap:16,justifyContent:'center',marginTop:8}}>
            <span style={{fontSize:10,color:'var(--blue)'}}>■ Fundamental</span>
            <span style={{fontSize:10,color:'var(--green)'}}>■ Technical</span>
          </div>
        </div>
      )}

      {/* Filters + table */}
      <div className="section-h">
        Candidates ({filtered.length})
        <div style={{display:'flex',gap:6}}>
          <select className="pro" style={{width:'auto',padding:'4px 8px',fontSize:10}} value={sortBy} onChange={e=>setSortBy(e.target.value)}>
            <option value="combined_score">Sort: Score</option>
            <option value="fundamental_score">Sort: Fundamental</option>
            <option value="technical_score">Sort: Technical</option>
          </select>
        </div>
      </div>
      <div className="filter-bar">
        {['ALL','STRONG','GOOD','MODERATE','WEAK'].map(c=>(
          <button key={c} className={`filter-chip ${convFilter===c?'active':''}`} onClick={()=>setConvFilter(c)}>{c}</button>
        ))}
      </div>
      <div className="card" style={{padding:0,overflow:'hidden'}}>
        <div style={{overflowX:'auto'}}>
          <table className="tbl">
            <thead><tr>
              <th>Ticker</th><th>Score</th><th>Conv.</th><th>Fund.</th><th>Tech.</th><th>Entry</th><th>TP</th><th>SL</th>
            </tr></thead>
            <tbody>
              {filtered.slice(0,20).map((c,i)=>(
                <tr key={i}>
                  <td style={{color:'var(--gold)',fontWeight:800,fontSize:13}}>{c.ticker}</td>
                  <td style={{color:'var(--green)',fontWeight:700}}>{((c.combined_score||0)*100).toFixed(0)}%</td>
                  <td><span className={`bdg bdg-${c.conviction==='STRONG'?'bull':c.conviction==='GOOD'?'blue':'muted'}`}>{c.conviction||'—'}</span></td>
                  <td style={{color:'var(--blue)'}}>{((c.fundamental_score||0)*100).toFixed(0)}%</td>
                  <td style={{color:'var(--green)'}}>{((c.technical_score||0)*100).toFixed(0)}%</td>
                  <td style={{color:'var(--text)'}}>{c.entry?money(c.entry):'—'}</td>
                  <td style={{color:'var(--green)'}}>{c.tp?money(c.tp):'—'}</td>
                  <td style={{color:'var(--red)'}}>{c.sl?money(c.sl):'—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════
// TAB 6 — MACRO & REGIME
// ══════════════════════════════════════════════════════════════════
function MacroTab({health}) {
  const {data:hd,err,load}=health
  if(load&&!hd) return <Spinner/>
  if(err&&!hd)  return <Err e={err}/>

  const reg=hd?.regimes||{}, mtf=hd?.mtf||{}, imkt=hd?.intermarket||{}, postev=hd?.post_event||{}

  const regData = Object.entries(reg).map(([asset,r])=>({
    name: asset, label: r.label||r.regime||'—',
    conf: Math.round((r.confidence||0)*100),
    color: r.regime?.includes('BULL')?C.green:r.regime?.includes('BEAR')?C.red:C.muted
  }))

  const mtfData = Object.entries(mtf).map(([asset,m])=>({
    name: asset, alignment: m.alignment||'—',
    bull: Math.round((m.bull_score||0)*100), bear: Math.round((m.bear_score||0)*100)
  }))

  return (
    <div className="content">
      {/* Regime confidence chart */}
      {regData.length>0&&(
        <div className="card">
          <div className="card-title">Market Regimes — Confidence</div>
          <ResponsiveContainer width="100%" height={140}>
            <BarChart data={regData} margin={{left:-20,right:8,top:4,bottom:0}}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(30,30,58,.8)"/>
              <XAxis dataKey="name" tick={{fill:'#94a3b8',fontSize:11}}/>
              <YAxis tick={{fill:'#64748b',fontSize:9}} domain={[0,100]} tickFormatter={v=>`${v}%`}/>
              <Tooltip content={<ChartTip fmt={v=>`${v}%`}/>}/>
              <Bar dataKey="conf" name="Confidence" radius={4}>
                {regData.map((e,i)=><Cell key={i} fill={e.color}/>)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <div style={{overflowX:'auto',marginTop:8}}>
            <table className="tbl">
              <thead><tr><th>Asset</th><th>Regime</th><th>Label</th><th>Conf</th></tr></thead>
              <tbody>
                {Object.entries(reg).map(([asset,r])=>(
                  <tr key={asset}>
                    <td style={{fontWeight:700}}>{asset}</td>
                    <td><span className={`bdg bdg-${r.regime?.includes('BULL')?'bull':r.regime?.includes('BEAR')?'bear':'muted'}`}>{r.regime||'—'}</span></td>
                    <td style={{color:'var(--muted)'}}>{r.label||'—'}</td>
                    <td style={{color:'var(--gold)',fontWeight:700}}>{Math.round((r.confidence||0)*100)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* MTF Confluence */}
      {mtfData.length>0&&(
        <div className="card">
          <div className="card-title">MTF Confluence</div>
          <ResponsiveContainer width="100%" height={120}>
            <BarChart data={mtfData} margin={{left:-20,right:8,top:4,bottom:0}}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(30,30,58,.8)"/>
              <XAxis dataKey="name" tick={{fill:'#94a3b8',fontSize:11}}/>
              <YAxis tick={{fill:'#64748b',fontSize:9}} domain={[0,100]} tickFormatter={v=>`${v}%`}/>
              <Tooltip content={<ChartTip fmt={v=>`${v}%`}/>}/>
              <Bar dataKey="bull" name="Bull" fill={C.green} radius={[3,3,0,0]} stackId="a"/>
              <Bar dataKey="bear" name="Bear" fill={C.red} radius={[0,0,3,3]} stackId="a"/>
            </BarChart>
          </ResponsiveContainer>
          <div style={{display:'flex',gap:16,justifyContent:'center',marginTop:6}}>
            <span style={{fontSize:10,color:'var(--green)'}}>■ Bull Score</span>
            <span style={{fontSize:10,color:'var(--red)'}}>■ Bear Score</span>
          </div>
        </div>
      )}

      {/* Intermarket */}
      <div className="card">
        <div className="card-title">Intermarket</div>
        <div className="metrics">
          {imkt.vix!=null&&<div className="metric"><div className="metric-val">{n(imkt.vix,1)}</div><div className="metric-lbl">VIX</div></div>}
          {imkt.dxy_break!=null&&<div className="metric"><div className="metric-val" style={{fontSize:16}}>{imkt.dxy_break?'✅':'❌'}</div><div className="metric-lbl">DXY Break</div></div>}
          {imkt.real_yield!=null&&<div className="metric"><div className="metric-val" style={{fontSize:13}}>{n(imkt.real_yield,2)}%</div><div className="metric-lbl">Real Yield</div></div>}
          {imkt.yield_spread!=null&&<div className="metric"><div className="metric-val" style={{fontSize:13}}>{n(imkt.yield_spread,2)}</div><div className="metric-lbl">Yield Spread</div></div>}
        </div>
      </div>

      {/* Post-event volatility */}
      {Object.keys(postev).length>0&&(
        <div className="card">
          <div className="card-title">⚡ Post-Event Volatility</div>
          <table className="tbl"><thead><tr><th>Asset</th><th>State</th><th>Since</th></tr></thead>
          <tbody>{Object.entries(postev).map(([a,ev])=>(
            <tr key={a}><td style={{fontWeight:700}}>{a}</td><td style={{color:'var(--gold)'}}>{ev.state||'—'}</td><td style={{color:'var(--muted)'}}>{age(ev.event_time)}</td></tr>
          ))}</tbody></table>
        </div>
      )}

    </div>
  )
}

// ══════════════════════════════════════════════════════════════════
// TAB 7 — NEWS
// ══════════════════════════════════════════════════════════════════
function NewsTab() {
  const {data,err,load,reload}=useLoad(()=>api('/news/feed'))
  const [sentFilter,setSentFilter]=useState('ALL')
  const [search,setSearch]=useState('')

  if(load&&!data) return <Spinner/>
  if(err&&!data)  return <Err e={err}/>

  const vel=data?.velocity||''
  const items=(data?.items||[])
    .filter(i=>sentFilter==='ALL'||i.sentiment===sentFilter)
    .filter(i=>!search||i.headline?.toLowerCase().includes(search.toLowerCase())||i.source?.toLowerCase().includes(search.toLowerCase()))

  const sentClr = s => s==='BULLISH'?'var(--green)':s==='BEARISH'?'var(--red)':'var(--muted)'
  const sentIco = s => s==='BULLISH'?'📈':s==='BEARISH'?'📉':'📄'

  // Sentiment breakdown
  const allItems=data?.items||[]
  const sentCounts={BULLISH:allItems.filter(i=>i.sentiment==='BULLISH').length,BEARISH:allItems.filter(i=>i.sentiment==='BEARISH').length,NEUTRAL:allItems.filter(i=>i.sentiment==='NEUTRAL').length}
  const sentRows=[
    {name:'Bullish',value:sentCounts.BULLISH,fill:C.green},
    {name:'Bearish',value:sentCounts.BEARISH,fill:C.red},
    {name:'Neutral',value:sentCounts.NEUTRAL,fill:C.muted},
  ].filter(d=>d.value>0)

  return (
    <div className="content">
      {/* Velocity */}
      {vel&&(
        <div className={`vel ${vel==='ACCELERATING'?'acc':vel==='QUIET'?'quiet':'norm'}`} style={{marginTop:10}}>
          {vel==='ACCELERATING'?'⚡ Accelerating':vel==='QUIET'?'🟢 Quiet':'📰 Normal velocity'}
          <span style={{marginLeft:'auto',fontSize:12}}>Agg {data.agg_score>=0?'+':''}{((data.agg_score||0)*100).toFixed(0)}%</span>
        </div>
      )}

      {data?.high_impact_event?.detected&&(
        <div className="event-card">
          <span style={{fontSize:18}}>⚡</span>
          <div>
            <div style={{fontWeight:700,color:'var(--gold)',fontSize:13}}>{data.high_impact_event.name||'Event'}</div>
            {data.high_impact_event.urgency!=null&&<div style={{fontSize:11,color:'var(--muted)'}}>urgency {n(data.high_impact_event.urgency,2)}</div>}
          </div>
        </div>
      )}

      {/* Net sentiment */}
      {sentRows.length>0&&(
        <div className="card">
          <div className="card-title">Sentiment Distribution</div>
          <div style={{marginBottom:14}}>
            <BiasBar value={((data?.agg_score||0)+1)/2} label="Net Sentiment"/>
          </div>
          <div>
            {sentRows.map((s,i)=>(
              <div key={i} style={{display:'flex',justifyContent:'space-between',fontSize:12,padding:'3px 0'}}>
                <span style={{color:s.fill,fontWeight:700}}>■ {s.name}</span>
                <span style={{color:'var(--text)',fontWeight:700}}>{s.value}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Search + filters */}
      <div style={{padding:'0 12px 6px'}}>
        <input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search headlines…"
          style={{width:'100%',background:'var(--card)',border:'1px solid var(--border)',color:'var(--text)',borderRadius:8,padding:'8px 12px',fontSize:12,outline:'none',marginBottom:8}}/>
      </div>
      <div className="filter-bar">
        {['ALL','BULLISH','BEARISH','NEUTRAL'].map(s=>(
          <button key={s} className={`filter-chip ${sentFilter===s?'active':''}`} onClick={()=>setSentFilter(s)}
            style={sentFilter===s?{}:{color:sentClr(s)}}>
            {s==='ALL'?'All':s==='BULLISH'?'📈 Bull':s==='BEARISH'?'📉 Bear':'📄 Neutral'}
          </button>
        ))}
        <span style={{marginLeft:'auto',alignSelf:'center',fontSize:11,color:'var(--muted)',flexShrink:0}}>{items.length} results</span>
      </div>

      <div className="card">
        <div style={{display:'flex',justifyContent:'flex-end',marginBottom:8}}>
          <span style={{fontSize:11,color:'var(--gold)',cursor:'pointer',fontWeight:700}} onClick={reload}>↻ Refresh</span>
        </div>
        {items.length===0?<div style={{color:'var(--muted)',fontSize:13,padding:'8px 0'}}>No headlines match filters.</div>:
        items.map((item,i)=>(
          <div key={i} className="news-item">
            <div style={{fontSize:13,lineHeight:1.45,marginBottom:5,fontWeight:500}}>
              {item.url
                ?<a href={item.url} target="_blank" rel="noopener noreferrer" style={{color:'var(--text)',textDecoration:'none'}}>{item.headline}</a>
                :item.headline}
            </div>
            <div style={{display:'flex',gap:10,flexWrap:'wrap',alignItems:'center'}}>
              <span style={{fontSize:10,color:'var(--muted)',background:'rgba(255,255,255,.04)',padding:'2px 6px',borderRadius:4}}>{item.source}</span>
              <span style={{fontSize:10,color:'var(--muted)'}}>{item.age_min}m ago</span>
              <span style={{fontSize:10,color:sentClr(item.sentiment),fontWeight:700}}>{sentIco(item.sentiment)} {item.sentiment}</span>
              <span style={{fontSize:10,color:'var(--muted)',marginLeft:'auto'}}>{item.score>=0?'+':''}{((item.score||0)*100).toFixed(0)}%</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════
// NEW TABS — MARKETS, PORTFOLIO, WATCHLIST, RESEARCH, COMPARE, WRAP
// ══════════════════════════════════════════════════════════════════
function CommentaryInline() {
  const {data,load} = useLoad(()=>getMarketCommentary())
  if(load) return <div style={{color:'var(--muted)',fontSize:13}}>Loading commentary…</div>
  if(!data?.commentary) return null
  const paras = String(data.commentary).split(/\n{2,}/).map(p=>p.trim()).filter(Boolean)
  return (
    <div>
      <div style={{display:'flex',alignItems:'center',gap:8,marginBottom:8}}>
        <span style={{fontSize:10,fontWeight:700,letterSpacing:'.1em',textTransform:'uppercase',color:'var(--gold)'}}>Desk Commentary</span>
        {data.fallback&&<span style={{fontSize:9,color:'var(--text-dim)'}}>· data view</span>}
      </div>
      <div style={{display:'flex',flexDirection:'column',gap:8}}>
        {paras.map((p,i)=>(
          <div key={i} style={{color:'var(--text)',fontSize:13,lineHeight:1.65}}>{p}</div>
        ))}
      </div>
    </div>
  )
}

// Lightweight inline SVG sparkline (no chart lib — cheap for many rows)
function Spark({data,w=70,h=24}){
  if(!data||data.length<2) return <span style={{color:'var(--muted)',fontSize:10}}>—</span>
  const min=Math.min(...data), max=Math.max(...data), span=(max-min)||1
  const pts=data.map((v,i)=>`${(i/(data.length-1))*w},${(h-2)-((v-min)/span)*(h-4)+2}`).join(' ')
  const up=data[data.length-1]>=data[0]
  const c=up?'var(--green)':'var(--red)'
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" style={{display:'block'}}>
      <polyline points={pts} fill="none" stroke={c} strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round"/>
    </svg>
  )
}

function MarketsGridTab() {
  const {data,err,load} = useLoad(()=>getMarketOverview())
  const spark = useLoad(()=>getMarketSparklines())
  const series = spark.data?.series || {}
  const [grpFilter,setGrpFilter] = useState('All')
  if(load) return <Spinner/>
  if(err)  return <Err e={err}/>
  const groups = Object.entries(data||{})
  // Flatten all instruments for the Market Movers chart, sort by % change desc
  const movers = groups.flatMap(([,items])=>items)
    .filter(it=>!it.error&&it.change_pct!=null)
    .map(it=>({name:it.name,chg:Number(it.change_pct)||0}))
    .sort((a,b)=>b.chg-a.chg)
  const chips = ['All',...groups.map(([g])=>g)]
  const visible = grpFilter==='All'?groups:groups.filter(([g])=>g===grpFilter)
  return (
    <div>
      <div className="commentary-card" style={{margin:'10px 10px'}}>
        <CommentaryInline/>
      </div>

      {/* Market Movers — hero bar chart */}
      {movers.length>0&&(
        <div className="card">
          <div className="card-title">Market Movers</div>
          <ResponsiveContainer width="100%" height={Math.max(160,movers.length*26)}>
            <BarChart data={movers} layout="vertical" margin={{top:4,right:16,left:8,bottom:4}}>
              <XAxis type="number" tick={{fill:'var(--text-mut)',fontSize:10}} tickFormatter={v=>`${v}%`} axisLine={false} tickLine={false}/>
              <YAxis type="category" dataKey="name" width={86} tick={{fill:'var(--text-mut)',fontSize:10}} axisLine={false} tickLine={false}/>
              <ReferenceLine x={0} stroke="var(--border-2)"/>
              <Tooltip cursor={{fill:'rgba(255,255,255,.04)'}} content={<ChartTip fmt={v=>`${v>=0?'+':''}${Number(v).toFixed(2)}%`}/>}/>
              <Bar dataKey="chg" name="Change" radius={[0,3,3,0]}>
                {movers.map((m,i)=><Cell key={i} fill={m.chg>=0?'var(--green)':'var(--red)'}/>)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Group filter */}
      <div className="filter-bar">
        {chips.map(c=>(
          <button key={c} className={`filter-chip ${grpFilter===c?'active':''}`} onClick={()=>setGrpFilter(c)}>{c}</button>
        ))}
      </div>

      {/* Per-group tables */}
      {visible.map(([grp,items])=>(
        <div key={grp} className="card" style={{overflowX:'auto'}}>
          <div className="card-title">{grp}</div>
          <table className="tbl" style={{width:'100%'}}>
            <thead><tr><th>Instrument</th><th className="num">Price</th><th className="num">Change</th><th>30D</th><th>Day Range</th></tr></thead>
            <tbody>
              {items.map(item=>{
                const up=(item.change_pct||0)>=0
                const clr=up?'var(--green)':'var(--red)'
                const rng=(!item.error&&item.day_high!=null&&item.day_low!=null)?(item.day_high-item.day_low):0
                const pos=rng>0?Math.min(1,Math.max(0,(item.price-item.day_low)/rng)):null
                return (
                  <tr key={item.symbol}>
                    <td><strong style={{color:'var(--text-hi)'}}>{item.name}</strong><br/><small style={{color:'var(--text-mut)'}}>{item.symbol}</small></td>
                    <td className="num">{item.error?'—':item.price?.toLocaleString('en-US',{maximumFractionDigits:2})}</td>
                    <td className="num" style={{color:item.error?'var(--muted)':clr}}>{item.error?'—':`${up?'▲':'▼'} ${Math.abs(item.change_pct||0).toFixed(2)}%`}</td>
                    <td>{item.error?<span style={{color:'var(--muted)'}}>—</span>:<Spark data={series[item.symbol]}/>}</td>
                    <td>
                      {pos==null?<span style={{color:'var(--muted)'}}>—</span>:(
                        <div style={{position:'relative',height:4,borderRadius:2,background:'rgba(255,255,255,.08)',minWidth:60}}>
                          <div style={{position:'absolute',top:-1,height:6,width:6,borderRadius:3,transform:'translateX(-50%)',left:`${pos*100}%`,background:clr}}/>
                        </div>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  )
}

function MarketsTab({pulse, health}) {
  const [sub,setSub] = useState('overview')
  return (
    <div className="content">
      <div className="sub-tabs">
        <button className={`sub-tab${sub==='overview'?' active':''}`} onClick={()=>setSub('overview')}>Overview</button>
        <button className={`sub-tab${sub==='pulse'?' active':''}`} onClick={()=>setSub('pulse')}>Pulse &amp; Regime</button>
        <button className={`sub-tab${sub==='wrap'?' active':''}`} onClick={()=>setSub('wrap')}>Wrap</button>
      </div>
      {sub==='overview' && <><MarketsGridTab/><BriefTab/></>}
      {sub==='pulse'    && <><PulseTab pulse={pulse} health={health}/><MacroTab health={health}/></>}
      {sub==='wrap'     && <WrapTab/>}
    </div>
  )
}

function PortfolioTab() {
  const [holdings,setHoldings] = useState(()=>{try{return JSON.parse(localStorage.getItem('portfolio')||'[]')}catch{return[]}})
  const [quotes,setQuotes]     = useState({})
  const [adding,setAdding]     = useState(false)
  const [form,setForm]         = useState({symbol:'',shares:'',avg_cost:'',name:''})
  const [loading,setLoading]   = useState(false)
  const [lastRefresh,setLastRefresh] = useState(null)

  const refresh = useCallback(async()=>{
    if(!holdings.length) return
    setLoading(true)
    try{const q=await getMarketQuotes(holdings.map(h=>h.symbol).join(','));setQuotes(q);setLastRefresh(new Date())}
    catch(e){console.error(e)}finally{setLoading(false)}
  },[holdings])
  useEffect(()=>{refresh()},[refresh])
  useEffect(()=>{const t=setInterval(refresh,30000);return()=>clearInterval(t)},[refresh])

  const save=(h)=>{setHoldings(h);localStorage.setItem('portfolio',JSON.stringify(h))}
  const remove=(i)=>{const h=[...holdings];h.splice(i,1);save(h)}
  const addHolding=()=>{
    const sym=form.symbol.trim().toUpperCase()
    if(!sym||!form.shares||!form.avg_cost) return
    save([...holdings,{symbol:sym,shares:Number(form.shares),avg_cost:Number(form.avg_cost),name:form.name||sym}])
    setForm({symbol:'',shares:'',avg_cost:'',name:''});setAdding(false)
  }

  let totalCost=0,totalValue=0
  holdings.forEach(h=>{const price=quotes[h.symbol]?.price||0;totalCost+=h.shares*h.avg_cost;totalValue+=h.shares*price})
  const totalPnL=totalValue-totalCost,totalPnLPct=totalCost>0?totalPnL/totalCost*100:0

  return (
    <div className="content">
      <div className="card">
        <div style={{display:'flex',gap:24,flexWrap:'wrap',alignItems:'center'}}>
          <div><div style={{color:'var(--muted)',fontSize:11}}>PORTFOLIO VALUE</div><div style={{fontSize:24,fontWeight:700,color:'var(--gold)'}}>${totalValue.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2})}</div></div>
          <div><div style={{color:'var(--muted)',fontSize:11}}>TOTAL P&L</div><div style={{fontSize:20,fontWeight:700,color:totalPnL>=0?'var(--green)':'var(--red)'}}>{totalPnL>=0?'+':''}{totalPnL.toFixed(2)} ({totalPnLPct>=0?'+':''}{totalPnLPct.toFixed(2)}%)</div></div>
          <div><div style={{color:'var(--muted)',fontSize:11}}>COST BASIS</div><div style={{fontSize:16,fontWeight:600}}>${totalCost.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2})}</div></div>
          <div style={{marginLeft:'auto',display:'flex',gap:8,alignItems:'center',flexWrap:'wrap'}}>
            {loading&&<span style={{color:'var(--muted)',fontSize:12}}>↻</span>}
            {lastRefresh&&<span style={{color:'var(--muted)',fontSize:11}}>Updated {lastRefresh.toLocaleTimeString()}</span>}
            <button className="btn-sm" onClick={refresh}>Refresh</button>
            <button className="btn-sm gold" onClick={()=>setAdding(!adding)}>{adding?'Cancel':'+ Add'}</button>
          </div>
        </div>
      </div>
      {adding&&(
        <div className="card">
          <h3 style={{color:'var(--gold)',marginBottom:12,fontSize:14}}>Add Holding</h3>
          <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(140px,1fr))',gap:10}}>
            <input className="inp" placeholder="Symbol (e.g. AAPL)" value={form.symbol} onChange={e=>setForm({...form,symbol:e.target.value.toUpperCase()})}/>
            <input className="inp" placeholder="Shares" type="number" value={form.shares} onChange={e=>setForm({...form,shares:e.target.value})}/>
            <input className="inp" placeholder="Avg Cost ($)" type="number" value={form.avg_cost} onChange={e=>setForm({...form,avg_cost:e.target.value})}/>
            <input className="inp" placeholder="Name (optional)" value={form.name} onChange={e=>setForm({...form,name:e.target.value})}/>
          </div>
          <button className="btn-sm gold" style={{marginTop:10}} onClick={addHolding}>Add</button>
        </div>
      )}
      {holdings.length===0?(
        <div className="card" style={{textAlign:'center',color:'var(--muted)',padding:40}}>No holdings yet. Click "+ Add" to track your portfolio.</div>
      ):(
        <div className="card" style={{overflowX:'auto'}}>
          <table className="tbl" style={{width:'100%'}}>
            <thead><tr><th>Symbol</th><th>Shares</th><th>Avg Cost</th><th>Price</th><th>Change</th><th>Value</th><th>P&L</th><th>P&L %</th><th></th></tr></thead>
            <tbody>
              {holdings.map((h,i)=>{
                const q=quotes[h.symbol]||{},price=q.price||0,val=h.shares*price,cost=h.shares*h.avg_cost,pnl=val-cost,pnlp=cost>0?pnl/cost*100:0,up=pnl>=0
                return(
                  <tr key={i}>
                    <td><strong style={{color:'var(--gold)'}}>{h.symbol}</strong><br/><small style={{color:'var(--muted)'}}>{h.name}</small></td>
                    <td>{h.shares}</td><td>${h.avg_cost.toFixed(2)}</td>
                    <td>{price?`$${price.toFixed(2)}`:'—'}</td>
                    <td style={{color:q.change_pct>=0?'var(--green)':'var(--red)'}}>{q.change_pct!=null?`${q.change_pct>=0?'+':''}${q.change_pct.toFixed(2)}%`:'—'}</td>
                    <td>{price?`$${val.toFixed(2)}`:'—'}</td>
                    <td style={{color:up?'var(--green)':'var(--red)'}}>{price?`${up?'+':''}$${pnl.toFixed(2)}`:'—'}</td>
                    <td style={{color:up?'var(--green)':'var(--red)'}}>{price?`${up?'+':''}${pnlp.toFixed(2)}%`:'—'}</td>
                    <td><button className="btn-sm" style={{color:'var(--red)'}} onClick={()=>remove(i)}>✕</button></td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function WatchlistTab() {
  const [list,setList]   = useState(()=>{try{return JSON.parse(localStorage.getItem('watchlist')||'[]')}catch{return[]}})
  const [quotes,setQuotes]= useState({})
  const [input,setInput] = useState('')
  const [loading,setLoading]=useState(false)
  const [lastRefresh,setLastRefresh]=useState(null)

  const refresh=useCallback(async()=>{
    if(!list.length) return
    setLoading(true)
    try{setQuotes(await getMarketQuotes(list.join(',')));setLastRefresh(new Date())}
    catch(e){console.error(e)}finally{setLoading(false)}
  },[list])
  useEffect(()=>{refresh()},[refresh])
  useEffect(()=>{const t=setInterval(refresh,30000);return()=>clearInterval(t)},[refresh])

  const saveList=(l)=>{setList(l);localStorage.setItem('watchlist',JSON.stringify(l))}
  const add=()=>{const sym=input.trim().toUpperCase();if(!sym||list.includes(sym))return;saveList([...list,sym]);setInput('')}
  const remove=(sym)=>saveList(list.filter(s=>s!==sym))

  return (
    <div className="content">
      <div className="card">
        <div style={{display:'flex',gap:10,alignItems:'center',flexWrap:'wrap'}}>
          <input className="inp" style={{flex:'1 1 160px'}} placeholder="Add symbol (e.g. TSLA)" value={input}
            onChange={e=>setInput(e.target.value.toUpperCase())} onKeyDown={e=>e.key==='Enter'&&add()}/>
          <button className="btn-sm gold" onClick={add}>Add</button>
          <button className="btn-sm" onClick={refresh}>{loading?'↻':'Refresh'}</button>
          {lastRefresh&&<span style={{color:'var(--muted)',fontSize:11}}>Updated {lastRefresh.toLocaleTimeString()}</span>}
        </div>
      </div>
      {list.length===0?(
        <div className="card" style={{textAlign:'center',color:'var(--muted)',padding:40}}>Watchlist is empty. Add symbols above.</div>
      ):(
        <div className="card" style={{overflowX:'auto'}}>
          <table className="tbl" style={{width:'100%'}}>
            <thead><tr><th>Symbol</th><th>Name</th><th>Price</th><th>Change</th><th>Change %</th><th></th></tr></thead>
            <tbody>
              {list.map(sym=>{
                const q=quotes[sym]||{},up=(q.change_pct||0)>=0
                return(
                  <tr key={sym}>
                    <td><strong style={{color:'var(--gold)'}}>{sym}</strong></td>
                    <td style={{color:'var(--muted)',fontSize:12}}>{q.name||'—'}</td>
                    <td>{q.price!=null?`$${q.price.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2})}`:'—'}</td>
                    <td style={{color:up?'var(--green)':'var(--red)'}}>{q.change!=null?`${up?'+':''}${q.change.toFixed(2)}`:'—'}</td>
                    <td style={{color:up?'var(--green)':'var(--red)'}}>{q.change_pct!=null?`${up?'+':''}${q.change_pct.toFixed(2)}%`:'—'}</td>
                    <td><button className="btn-sm" style={{color:'var(--red)'}} onClick={()=>remove(sym)}>✕</button></td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function ResearchTab() {
  const [symbol,setSymbol]=useState(''),[query,setQuery]=useState(''),[data,setData]=useState(null)
  const [loading,setLoading]=useState(false),[err,setErr]=useState(null)

  const search=async()=>{
    const sym=query.trim().toUpperCase()
    if(!sym) return
    setLoading(true);setErr(null);setData(null);setSymbol(sym)
    try{setData(await getMarketTicker(sym))}catch(e){setErr(e.message)}finally{setLoading(false)}
  }

  const f=data?.fundamentals||{},p=data?.price_data||{},up=(p.change_pct||0)>=0
  const fmtPct=v=>v!=null?`${(v*100).toFixed(1)}%`:'—'
  const fmtNum=(v,d=2)=>v!=null?Number(v).toFixed(d):'—'
  const fmtB=v=>{if(v==null)return'—';if(v>=1e12)return`$${(v/1e12).toFixed(2)}T`;if(v>=1e9)return`$${(v/1e9).toFixed(1)}B`;if(v>=1e6)return`$${(v/1e6).toFixed(1)}M`;return`$${v}`}

  return (
    <div className="content">
      <div className="card">
        <div style={{display:'flex',gap:10,alignItems:'center'}}>
          <input className="inp" style={{flex:1}} placeholder="Enter ticker (e.g. AAPL, MSFT, GLD)" value={query}
            onChange={e=>setQuery(e.target.value.toUpperCase())} onKeyDown={e=>e.key==='Enter'&&search()}/>
          <button className="btn-sm gold" onClick={search} disabled={loading}>{loading?'…':'Search'}</button>
        </div>
      </div>
      {err&&<Err e={err}/>}
      {data&&(
        <div>
          <div className="card">
            <div style={{display:'flex',justifyContent:'space-between',flexWrap:'wrap',gap:12}}>
              <div><h2 style={{margin:0,fontSize:20,color:'var(--gold)'}}>{data.name}</h2><div style={{color:'var(--muted)',fontSize:13}}>{symbol} · {f.sector} · {f.industry}</div></div>
              <div style={{textAlign:'right'}}><div style={{fontSize:26,fontWeight:700}}>${p.price?.toFixed(2)||'—'}</div><div style={{color:up?'var(--green)':'var(--red)',fontSize:14}}>{up?'▲':'▼'} {Math.abs(p.change_pct||0).toFixed(2)}%</div></div>
            </div>
            <div style={{display:'flex',gap:24,marginTop:12,flexWrap:'wrap',fontSize:12,color:'var(--muted)'}}>
              <span>Day H: <b>${p.day_high?.toFixed(2)||'—'}</b></span>
              <span>Day L: <b>${p.day_low?.toFixed(2)||'—'}</b></span>
              <span>52W H: <b>${p.week52_high?.toFixed(2)||'—'}</b></span>
              <span>52W L: <b>${p.week52_low?.toFixed(2)||'—'}</b></span>
              <span>Mkt Cap: <b>{fmtB(p.market_cap)}</b></span>
            </div>
          </div>
          <div className="card">
            <h3 style={{color:'var(--gold)',marginBottom:12,fontSize:14}}>Fundamentals</h3>
            <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(140px,1fr))',gap:10}}>
              {[['P/E (TTM)',fmtNum(f.pe)],['P/E (Fwd)',fmtNum(f.forward_pe)],['P/B',fmtNum(f.pb)],['P/S',fmtNum(f.ps)],['EV/EBITDA',fmtNum(f.ev_ebitda)],['ROE',fmtPct(f.roe)],['Rev Growth',fmtPct(f.revenue_growth)],['Gross Margin',fmtPct(f.gross_margin)],['Net Margin',fmtPct(f.profit_margin)],['Debt/Equity',fmtNum(f.debt_to_equity)],['Div Yield',fmtPct(f.dividend_yield)],['Beta',fmtNum(f.beta)]].map(([label,val])=>(
                <div key={label} style={{background:'var(--bg)',borderRadius:8,padding:'10px 12px',border:'1px solid var(--border)'}}>
                  <div style={{color:'var(--muted)',fontSize:10,marginBottom:3}}>{label}</div>
                  <div style={{fontWeight:600,fontSize:14}}>{val}</div>
                </div>
              ))}
            </div>
          </div>
          {f.description&&<div className="card"><h3 style={{color:'var(--gold)',marginBottom:8,fontSize:14}}>About</h3><p style={{margin:0,color:'var(--muted)',fontSize:13,lineHeight:1.7}}>{f.description}</p></div>}
          {data.news?.length>0&&(
            <div className="card">
              <h3 style={{color:'var(--gold)',marginBottom:12,fontSize:14}}>Recent News</h3>
              <div style={{display:'flex',flexDirection:'column',gap:8}}>
                {data.news.map((item,i)=>(
                  <a key={i} href={item.url} target="_blank" rel="noopener" style={{display:'block',color:'var(--text)',textDecoration:'none',padding:'10px 12px',background:'var(--bg)',borderRadius:8,border:'1px solid var(--border)',fontSize:13,lineHeight:1.5}}>
                    {item.headline}<span style={{color:'var(--muted)',fontSize:11,marginLeft:8}}>{new Date(item.datetime*1000).toLocaleDateString()}</span>
                  </a>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function CompareTab() {
  const [input,setInput]=useState(''),[data,setData]=useState(null),[loading,setLoading]=useState(false),[err,setErr]=useState(null)

  const compare=async()=>{if(!input.trim())return;setLoading(true);setErr(null);setData(null);try{setData(await getMarketCompare(input.trim()))}catch(e){setErr(e.message)}finally{setLoading(false)}}

  const fmtPct=v=>v!=null?`${(v*100).toFixed(1)}%`:'—'
  const fmtNum=(v,d=2)=>v!=null?Number(v).toFixed(d):'—'
  const fmtB=v=>{if(v==null)return'—';if(v>=1e12)return`${(v/1e12).toFixed(2)}T`;if(v>=1e9)return`${(v/1e9).toFixed(1)}B`;return`${(v/1e6).toFixed(0)}M`}

  const metrics=[
    ['Price',d=>`$${d.price?.toFixed(2)||'—'}`],
    ['Change %',d=>{const up=(d.change_pct||0)>=0;return<span style={{color:up?'var(--green)':'var(--red)'}}>{up?'+':''}{d.change_pct?.toFixed(2)||'—'}%</span>}],
    ['Market Cap',d=>fmtB(d.market_cap)],['P/E (TTM)',d=>fmtNum(d.pe)],['P/E (Fwd)',d=>fmtNum(d.forward_pe)],
    ['P/B',d=>fmtNum(d.pb)],['ROE',d=>fmtPct(d.roe)],['Rev Growth',d=>fmtPct(d.revenue_growth)],
    ['Gross Margin',d=>fmtPct(d.gross_margin)],['Beta',d=>fmtNum(d.beta)],['Div Yield',d=>fmtPct(d.dividend_yield)],
    ['52W High',d=>`$${d.week52_high?.toFixed(2)||'—'}`],['52W Low',d=>`$${d.week52_low?.toFixed(2)||'—'}`],['Sector',d=>d.sector||'—'],
  ]

  return (
    <div className="content">
      <div className="card">
        <div style={{color:'var(--muted)',fontSize:12,marginBottom:8}}>Enter up to 6 symbols separated by commas</div>
        <div style={{display:'flex',gap:10}}>
          <input className="inp" style={{flex:1}} placeholder="e.g. AAPL, MSFT, GOOGL, AMZN" value={input}
            onChange={e=>setInput(e.target.value)} onKeyDown={e=>e.key==='Enter'&&compare()}/>
          <button className="btn-sm gold" onClick={compare} disabled={loading}>{loading?'…':'Compare'}</button>
        </div>
      </div>
      {err&&<Err e={err}/>}
      {data?.length>0&&(
        <div className="card" style={{overflowX:'auto'}}>
          <table className="tbl" style={{width:'100%',minWidth:400}}>
            <thead><tr>
              <th style={{textAlign:'left',color:'var(--muted)'}}>Metric</th>
              {data.map(d=><th key={d.symbol} style={{color:'var(--gold)'}}>{d.symbol}<br/><span style={{fontSize:10,fontWeight:400,color:'var(--muted)'}}>{d.name}</span></th>)}
            </tr></thead>
            <tbody>
              {metrics.map(([label,fn])=>(
                <tr key={label}>
                  <td style={{color:'var(--muted)',fontSize:12}}>{label}</td>
                  {data.map(d=><td key={d.symbol}>{d.error?'—':fn(d)}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function WrapTab() {
  const {data,err,load}=useLoad(()=>getMarketWrap())
  if(load) return <Spinner/>
  if(err)  return <Err e={err}/>
  const s=data?.sections||{}
  return (
    <div className="content">
      <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',padding:'10px 12px 4px'}}>
        <h2 style={{margin:0,fontSize:16,color:'var(--gold)'}}>🗞️ Daily Market Wrap-Up</h2>
        <span style={{color:'var(--muted)',fontSize:12}}>{data?.date}{data?.cached?' (cached)':''}</span>
      </div>
      {s.overview&&<div className="card"><h3 style={{color:'var(--gold)',marginBottom:8,fontSize:13}}>Market Overview</h3><p style={{margin:0,color:'var(--text)',lineHeight:1.7,fontSize:14}}>{s.overview}</p></div>}
      {s.themes?.length>0&&<div className="card"><h3 style={{color:'var(--gold)',marginBottom:10,fontSize:13}}>Key Themes</h3><ul style={{margin:0,padding:'0 0 0 18px',color:'var(--text)',lineHeight:2,fontSize:14}}>{s.themes.map((t,i)=><li key={i}>{t}</li>)}</ul></div>}
      {s.outlook&&<div className="card"><h3 style={{color:'var(--gold)',marginBottom:8,fontSize:13}}>Outlook</h3><p style={{margin:0,color:'var(--text)',lineHeight:1.7,fontSize:14}}>{s.outlook}</p></div>}
      {!s.overview&&!s.themes?.length&&!s.outlook&&data?.wrap&&<div className="card"><p style={{margin:0,color:'var(--text)',lineHeight:1.7,fontSize:14,whiteSpace:'pre-wrap'}}>{data.wrap}</p></div>}
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════
// WRAPPER COMPONENTS — merged tab groups
// ══════════════════════════════════════════════════════════════════
function SignalsHub() {
  const [subTab, setSubTab] = useState('intraday')
  return (
    <div className="content">
      <div className="sub-tabs">
        <button className={`sub-tab${subTab==='intraday'?' active':''}`} onClick={()=>setSubTab('intraday')}>Intraday</button>
        <button className={`sub-tab${subTab==='swing'?' active':''}`} onClick={()=>setSubTab('swing')}>Swing</button>
        <button className={`sub-tab${subTab==='options'?' active':''}`} onClick={()=>setSubTab('options')}>Options</button>
      </div>
      {subTab==='intraday' && <SignalsTab/>}
      {subTab==='swing'    && <SwingTab/>}
      {subTab==='options'  && <OptionsTab/>}
    </div>
  )
}

function CalendarTab() {
  const eco = useLoad(()=>getEconomicCalendar())
  const ern = useLoad(()=>getEarningsCalendar())
  const [view,setView] = useState('economic')

  const events = eco.data?.events || []
  // group economic events by date
  const byDay = {}
  events.forEach(e=>{ (byDay[e.date]=byDay[e.date]||[]).push(e) })
  const days = Object.keys(byDay).sort()
  const todayStr = new Date().toISOString().slice(0,10)

  const earnings = ern.data?.earnings || []
  const ernByDay = {}
  earnings.forEach(e=>{ (ernByDay[e.date]=ernByDay[e.date]||[]).push(e) })
  const ernDays = Object.keys(ernByDay).sort()

  const impClr = i => i==='high'?'var(--red)':i==='medium'?'var(--gold)':'var(--muted)'

  return (
    <div className="content">
      <div className="filter-bar">
        <button className={`filter-chip${view==='economic'?' active':''}`} onClick={()=>setView('economic')}>📆 Economic</button>
        <button className={`filter-chip${view==='earnings'?' active':''}`} onClick={()=>setView('earnings')}>📊 Earnings</button>
      </div>

      {view==='economic' && (
        eco.load&&!eco.data ? <Spinner/> :
        days.length===0 ? <div className="card" style={{textAlign:'center',color:'var(--muted)',padding:32,fontSize:13}}>No high-impact US events this week.</div> :
        days.map(d=>{
          const dd = byDay[d]
          const lbl = new Date(d+'T00:00:00').toLocaleDateString('en-US',{weekday:'long',day:'numeric',month:'short'})
          return (
            <div key={d} className="card">
              <div className="card-title" style={{color:d===todayStr?'var(--gold)':'var(--muted)'}}>{d===todayStr?'● Today · ':''}{lbl}</div>
              {dd.map((e,i)=>(
                <div key={i} style={{display:'flex',gap:10,alignItems:'center',padding:'7px 0',borderBottom:i<dd.length-1?'1px solid var(--border)':'none'}}>
                  <span className="mono" style={{color:'var(--gold)',fontWeight:700,fontSize:12,minWidth:44}}>{e.time_dubai}</span>
                  <span style={{flex:1,fontSize:12,color:'var(--text)'}}>{e.name}</span>
                  {(e.forecast||e.previous)&&(
                    <span style={{fontSize:10,color:'var(--muted)',whiteSpace:'nowrap'}}>
                      {e.forecast?`Est ${e.forecast}`:''}{e.forecast&&e.previous?' · ':''}{e.previous?`Prev ${e.previous}`:''}
                    </span>
                  )}
                  <span style={{fontSize:9,fontWeight:700,padding:'2px 7px',borderRadius:'var(--r-pill)',background:`${impClr(e.impact)}22`,color:impClr(e.impact),textTransform:'uppercase'}}>{e.impact}</span>
                </div>
              ))}
            </div>
          )
        })
      )}

      {view==='earnings' && (
        ern.load&&!ern.data ? <Spinner/> :
        ern.data?.error ? <div className="card" style={{textAlign:'center',color:'var(--muted)',padding:24,fontSize:12}}>{ern.data.error}</div> :
        ernDays.length===0 ? <div className="card" style={{textAlign:'center',color:'var(--muted)',padding:32,fontSize:13}}>No major-cap earnings in the next 7 days.</div> :
        ernDays.map(d=>{
          const dd = ernByDay[d]
          const lbl = new Date(d+'T00:00:00').toLocaleDateString('en-US',{weekday:'long',day:'numeric',month:'short'})
          return (
            <div key={d} className="card">
              <div className="card-title" style={{color:d===todayStr?'var(--gold)':'var(--muted)'}}>{d===todayStr?'● Today · ':''}{lbl}</div>
              <table className="tbl" style={{width:'100%'}}>
                <thead><tr><th>Ticker</th><th>Company</th><th>When</th><th className="num">EPS Est.</th></tr></thead>
                <tbody>
                  {dd.map((e,i)=>(
                    <tr key={i}>
                      <td style={{color:'var(--gold)',fontWeight:800}}>{e.symbol}</td>
                      <td style={{color:'var(--text)'}}>{e.name}</td>
                      <td style={{color:'var(--muted)',fontSize:10}}>{e.when||'—'}</td>
                      <td className="num" style={{color:'var(--text)'}}>{e.eps_estimate!=null?e.eps_estimate:'—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        })
      )}
    </div>
  )
}

function PortfolioHub() {
  const [subTab, setSubTab] = useState('holdings')
  return (
    <div className="content">
      <div className="sub-tabs">
        <button className={`sub-tab${subTab==='holdings'?' active':''}`} onClick={()=>setSubTab('holdings')}>Holdings</button>
        <button className={`sub-tab${subTab==='watchlist'?' active':''}`} onClick={()=>setSubTab('watchlist')}>Watchlist</button>
        <button className={`sub-tab${subTab==='research'?' active':''}`} onClick={()=>setSubTab('research')}>Research</button>
        <button className={`sub-tab${subTab==='compare'?' active':''}`} onClick={()=>setSubTab('compare')}>Compare</button>
      </div>
      {subTab==='holdings'  && <PortfolioTab/>}
      {subTab==='watchlist' && <WatchlistTab/>}
      {subTab==='research'  && <ResearchTab/>}
      {subTab==='compare'   && <CompareTab/>}
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════
// TAB — OPTIONS FLOW (Polygon)
// ══════════════════════════════════════════════════════════════════
function OptionsTab() {
  const { data, err, load } = useLoad(() => getOptionsFlow())
  const opts = useLoad(()=>api('/options/trades'))
  if (load) return <Spinner/>
  if (err)  return <Err e={err}/>

  const vix    = data?.vix || {}
  const flow   = data?.flow || []
  const open   = data?.open_trades || []
  const closed = data?.closed_recent || []
  const pc     = data?.put_call_ratio
  const od     = opts.data||{}, optPools = od.pools||{}

  return (
    <div className="content">
      {/* Status bar */}
      <div className="card" style={{marginBottom:12}}>
        <div style={{display:'flex',gap:20,flexWrap:'wrap',alignItems:'flex-start'}}>
          {[
            ['SPX SPOT',      data?.spot ? data.spot.toLocaleString() : '—', null],
            ['ATM IV',        data?.atm_iv != null ? `${data.atm_iv}%` : '—', null],
            ['IV RANK',       data?.iv_rank != null ? `${data.iv_rank}%` : '—',
              data?.iv_rank != null ? (data.iv_rank < 50 ? 'var(--green)' : 'var(--red)') : null],
            ['VIX',           vix.vix ?? '—', vix.backwardation ? 'var(--red)' : vix.half_size ? 'var(--gold)' : null],
            ['EXP MOVE',      data?.expected_move != null ? `±${data.expected_move}` : '—', null],
            ['OPEN POS',      data?.open_positions ?? 0, data?.open_positions ? 'var(--gold)' : null],
          ].map(([label, val, color]) => (
            <div key={label}>
              <div style={{color:'var(--muted)',fontSize:10,marginBottom:2}}>{label}</div>
              <div style={{fontSize:18,fontWeight:700,color:color||'var(--text)'}}>{val}</div>
              {label==='IV RANK' && data?.iv_rank != null &&
                <div style={{fontSize:10,color:'var(--muted)'}}>{data.iv_rank < 50 ? '✓ buy prem ok' : '✗ IV too high'}</div>}
              {label==='VIX' && vix.backwardation &&
                <div style={{fontSize:10,color:'var(--red)'}}>⚠ backwardation</div>}
            </div>
          ))}
        </div>
      </div>

      {/* Put/Call Ratio */}
      {pc && (
        <div className="card" style={{marginBottom:12}}>
          <div className="card-title">Put / Call Ratio</div>
          <div style={{display:'flex',gap:20,flexWrap:'wrap',alignItems:'center'}}>
            <div>
              <div style={{fontSize:28,fontWeight:800,
                color: pc.put_call_ratio < 0.7 ? 'var(--green)' : pc.put_call_ratio > 1.2 ? 'var(--red)' : 'var(--text)'}}>
                {pc.put_call_ratio?.toFixed(3)}
              </div>
              <div style={{fontSize:11,color:'var(--muted)'}}>
                {pc.put_call_ratio < 0.7 ? '📈 Bullish (low P/C)' : pc.put_call_ratio > 1.2 ? '📉 Bearish (high P/C)' : '↔ Neutral'}
              </div>
            </div>
            {[
              ['CALL VOL', pc.call_volume?.toLocaleString(), 'var(--green)'],
              ['PUT VOL',  pc.put_volume?.toLocaleString(),  'var(--red)'],
              ['TOTAL',    pc.total_volume?.toLocaleString(), 'var(--muted)'],
            ].map(([l,v,c]) => (
              <div key={l}>
                <div style={{color:'var(--muted)',fontSize:10}}>{l}</div>
                <div style={{fontWeight:700,fontSize:15,color:c}}>{v ?? '—'}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Options Flow */}
      {flow.length > 0 ? (
        <div className="card" style={{marginBottom:12,overflowX:'auto'}}>
          <div className="card-title">Options Flow — Top Volume</div>
          <table className="tbl" style={{width:'100%',minWidth:520}}>
            <thead><tr>
              <th>Type</th><th>Strike</th><th>Expiry</th>
              <th>Volume</th><th>OI</th><th>Vol/OI</th>
              <th>IV</th><th>Delta</th><th>Last</th>
            </tr></thead>
            <tbody>
              {flow.map((f,i) => (
                <tr key={i}>
                  <td><span style={{color:f.type==='call'?'var(--green)':'var(--red)',fontWeight:700,textTransform:'uppercase'}}>{f.type}</span></td>
                  <td style={{fontWeight:600}}>{f.strike?.toLocaleString()}</td>
                  <td style={{fontSize:11,color:'var(--muted)'}}>{f.expiry}</td>
                  <td style={{fontWeight:600}}>{f.volume?.toLocaleString() ?? '—'}</td>
                  <td style={{color:'var(--muted)'}}>{f.oi?.toLocaleString() ?? '—'}</td>
                  <td style={{color:(f.vol_oi_ratio||0)>2?'var(--gold)':'var(--text)',fontWeight:(f.vol_oi_ratio||0)>2?700:400}}>
                    {f.vol_oi_ratio ?? '—'}{(f.vol_oi_ratio||0)>2?' 🔥':''}
                  </td>
                  <td>{f.iv != null ? `${f.iv}%` : '—'}</td>
                  <td style={{color:'var(--muted)',fontSize:12}}>{f.delta ?? '—'}</td>
                  <td>{f.last != null ? `$${f.last.toFixed(2)}` : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="card" style={{marginBottom:12,color:'var(--muted)',textAlign:'center',padding:24,fontSize:13}}>
          {data?.polygon_available
            ? 'No flow data available for today yet.'
            : 'Set POLYGON_API_KEY in Railway env to enable live options flow with Greeks.'}
        </div>
      )}

      {/* Open Positions */}
      {open.length > 0 && (
        <div className="card" style={{marginBottom:12}}>
          <div className="card-title">Open Paper Positions ({open.length})</div>
          {open.map((t,i) => (
            <div key={i} style={{background:'var(--surface)',borderRadius:10,padding:'10px 14px',marginBottom:8,
              borderLeft:`3px solid ${t.direction==='LONG'?'var(--green)':'var(--red)'}`}}>
              <div style={{display:'flex',justifyContent:'space-between',flexWrap:'wrap',gap:6}}>
                <div>
                  <span style={{color:'var(--gold)',fontWeight:700,fontSize:13}}>{t.pool}</span>
                  <span style={{marginLeft:10,color:t.direction==='LONG'?'var(--green)':'var(--red)',fontWeight:600}}>
                    {t.direction} {t.option_type?.toUpperCase()}
                  </span>
                  <span style={{marginLeft:8,color:'var(--muted)',fontSize:12}}>Strike {t.strike} · {t.expiry}</span>
                </div>
                <div style={{fontSize:12,color:'var(--muted)'}}>
                  Entry {t.entry_premium ? `$${t.entry_premium.toFixed(2)}` : '—'} ·
                  Conf {t.confidence ? ` ${(t.confidence*100).toFixed(0)}%` : '—'}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Recent Closed */}
      {closed.length > 0 && (
        <div className="card">
          <div className="card-title">Recent Closed Trades</div>
          <div style={{overflowX:'auto'}}>
            <table className="tbl" style={{width:'100%'}}>
              <thead><tr><th>Pool</th><th>Dir</th><th>Strike</th><th>Entry</th><th>Exit</th><th>P&amp;L</th><th>Outcome</th></tr></thead>
              <tbody>
                {closed.map((t,i) => {
                  const pnl = t.exit_premium && t.entry_premium ? t.exit_premium - t.entry_premium : null
                  return (
                    <tr key={i}>
                      <td style={{fontSize:11}}>{t.pool}</td>
                      <td style={{color:t.direction==='LONG'?'var(--green)':'var(--red)',fontWeight:600,fontSize:12}}>{t.direction}</td>
                      <td>{t.strike}</td>
                      <td>{t.entry_premium ? `$${t.entry_premium.toFixed(2)}` : '—'}</td>
                      <td>{t.exit_premium  ? `$${t.exit_premium.toFixed(2)}`  : '—'}</td>
                      <td style={{color: pnl==null?'var(--muted)':pnl>=0?'var(--green)':'var(--red)',fontWeight:600}}>
                        {pnl != null ? `${pnl>=0?'+':''}$${pnl.toFixed(2)}` : '—'}
                      </td>
                      <td><span style={{color:t.outcome==='WIN'?'var(--green)':'var(--red)',fontWeight:700,fontSize:12}}>{t.outcome||'—'}</span></td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* SPX 0-1DTE paper-trade pools */}
      <div className="card" style={{marginBottom:12}}>
        <div className="card-title">SPX 0-1DTE Options Paper Trades</div>
        {opts.load&&!od.pools?<div style={{color:'var(--muted)',fontSize:12}}>Loading…</div>:
        Object.keys(optPools).length===0?<div style={{color:'var(--muted)',fontSize:12}}>No options data yet.</div>:(
          <table className="tbl"><thead><tr><th>Pool</th><th>Open</th><th>Closed</th><th>Win%</th><th>Gate</th></tr></thead>
          <tbody>{Object.entries(optPools).map(([pool,ps])=>(
            <tr key={pool}>
              <td style={{fontSize:10,fontWeight:700}}>{pool}</td>
              <td>{ps.open||0}</td>
              <td>{ps.closed||0}</td>
              <td style={{color:(ps.win_rate||0)>0.5?'var(--green)':'var(--red)',fontWeight:700}}>{((ps.win_rate||0)*100).toFixed(1)}%</td>
              <td>{ps.ml_gate_active?<span className="bdg bdg-bull">Active</span>:<span style={{color:'var(--muted)',fontSize:10}}>⏳{50-(ps.closed||0)}</span>}</td>
            </tr>
          ))}</tbody></table>
        )}
        <div style={{fontSize:10,color:'var(--muted)',marginTop:8}}>ML gate activates at ≥50 closed trades per pool.</div>
      </div>

      {od.open_positions?.length>0&&(
        <div className="card">
          <div className="card-title">Open Options Positions ({od.open_positions.length})</div>
          <table className="tbl"><thead><tr><th>Pool</th><th>Dir</th><th>Strike</th><th>DTE</th><th>Entry</th><th>Age</th></tr></thead>
          <tbody>{od.open_positions.map((p,i)=>(
            <tr key={i}>
              <td style={{fontSize:10}}>{p.pool||''}</td>
              <td style={{color:p.direction==='CALL'?'var(--green)':'var(--red)',fontWeight:700}}>{p.direction}</td>
              <td style={{color:'var(--gold)'}}>{p.strike||'—'}</td>
              <td>{p.dte||'—'}</td>
              <td>${n(p.entry_premium,2)}</td>
              <td style={{color:'var(--muted)',fontSize:10}}>{age(p.entry_time)}</td>
            </tr>
          ))}</tbody></table>
        </div>
      )}
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════
// COVER / SPLASH SCREEN
// ══════════════════════════════════════════════════════════════════
function Splash({onEnter}) {
  const [leaving,setLeaving] = useState(false)
  const enter = () => { if(leaving) return; setLeaving(true); setTimeout(onEnter,460) }
  return (
    <div className={`splash${leaving?' leaving':''}`} onClick={enter}>
      <div className="splash-glow"/>
      <div className="splash-inner">
        <img className="splash-logo" src="/app/sniper-logo.jpg" alt="Sniper Signals"
          fetchpriority="high" decoding="async"
          onError={e=>{e.currentTarget.style.display='none'}}/>
        <div className="splash-name">SNIPER SIGNALS</div>
        <div className="splash-tag">Global Market Insights</div>
        <button className="splash-enter" onClick={e=>{e.stopPropagation();enter()}}>Enter →</button>
        <div className="splash-hint">tap anywhere to continue</div>
      </div>
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════
// APP ROOT
// ══════════════════════════════════════════════════════════════════
export default function App() {
  const [entered,setEntered] = useState(false)
  const [tab,setTab] = useState('signals')
  const pulse  = useLoad(()=>fetch(`${BASE}/pulse`,{signal:AbortSignal.timeout(15000)}).then(r=>r.json()))
  const health = useLoad(()=>api('/health'))

  useEffect(()=>{ const id=setInterval(pulse.reload,  60_000); return()=>clearInterval(id) },[])
  useEffect(()=>{ const id=setInterval(health.reload,120_000); return()=>clearInterval(id) },[])

  if(!entered) return <Splash onEnter={()=>setEntered(true)}/>

  return (
    <>
      <div style={{flex:1, paddingBottom:64}}>
        {tab==='signals'   && <SignalsHub/>}
        {tab==='markets'   && <MarketsTab pulse={pulse} health={health}/>}
        {tab==='calendar'  && <CalendarTab/>}
        {tab==='portfolio' && <PortfolioHub/>}
        {tab==='news'      && <NewsTab/>}
      </div>

      {/* Fixed bottom nav */}
      <nav className="bottom-nav">
        {BOTTOM_NAV.map(item=>(
          <button key={item.id}
            className={tab===item.id?'active':''}
            onClick={()=>setTab(item.id)}>
            <item.Icon size={20} strokeWidth={2}/>
            <span>{item.label}</span>
          </button>
        ))}
      </nav>
    </>
  )
}
