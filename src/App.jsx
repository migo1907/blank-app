import { useState, useEffect } from 'react';

// ── Icons ─────────────────────────────────────────────────────────────────────
const RefreshIcon = ({ className = '', spinning = false }) => (
  <svg
    className={className}
    style={{ animation: spinning ? 'spin 1s linear infinite' : 'none' }}
    width="24" height="24" viewBox="0 0 24 24"
    fill="none" stroke="currentColor" strokeWidth="2"
  >
    <polyline points="23 4 23 10 17 10" />
    <polyline points="1 20 1 14 7 14" />
    <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
  </svg>
);

const TrendUpIcon = ({ className = '' }) => (
  <svg className={className} width="24" height="24" viewBox="0 0 24 24"
    fill="none" stroke="currentColor" strokeWidth="2">
    <polyline points="23 6 13.5 15.5 8.5 10.5 1 18" />
    <polyline points="17 6 23 6 23 12" />
  </svg>
);

const TrendDownIcon = ({ className = '' }) => (
  <svg className={className} width="24" height="24" viewBox="0 0 24 24"
    fill="none" stroke="currentColor" strokeWidth="2">
    <polyline points="23 18 13.5 8.5 8.5 13.5 1 6" />
    <polyline points="17 18 23 18 23 12" />
  </svg>
);

const TargetIcon = ({ className = '' }) => (
  <svg className={className} width="24" height="24" viewBox="0 0 24 24"
    fill="none" stroke="currentColor" strokeWidth="2">
    <circle cx="12" cy="12" r="10" />
    <circle cx="12" cy="12" r="6" />
    <circle cx="12" cy="12" r="2" />
  </svg>
);

const ClockIcon = ({ className = '' }) => (
  <svg className={className} width="24" height="24" viewBox="0 0 24 24"
    fill="none" stroke="currentColor" strokeWidth="2">
    <circle cx="12" cy="12" r="10" />
    <polyline points="12 6 12 12 16 14" />
  </svg>
);

const AlertIcon = ({ className = '' }) => (
  <svg className={className} width="24" height="24" viewBox="0 0 24 24"
    fill="none" stroke="currentColor" strokeWidth="2">
    <circle cx="12" cy="12" r="10" />
    <line x1="12" y1="8" x2="12" y2="12" />
    <line x1="12" y1="16" x2="12.01" y2="16" />
  </svg>
);

// ── Helpers ───────────────────────────────────────────────────────────────────
const formatTime = (seconds) => {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, '0')}`;
};

const confidenceColor = (c) => {
  if (c >= 80) return 'text-green-400';
  if (c >= 65) return 'text-yellow-400';
  return 'text-orange-400';
};

// ── Dashboard ─────────────────────────────────────────────────────────────────
export default function App() {
  const [analysis, setAnalysis]   = useState(null);
  const [loading, setLoading]     = useState(true);
  const [lastUpdate, setLastUpdate] = useState(null);
  const [nextUpdate, setNextUpdate] = useState(30 * 60);
  const [error, setError]         = useState(null);

  const fetchAnalysis = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/analysis', { method: 'POST' });
      if (!res.ok) {
        const e = await res.json();
        throw new Error(e.error || `HTTP ${res.status}`);
      }
      const data = await res.json();
      setAnalysis(data);
      setLastUpdate(new Date());
      setNextUpdate(30 * 60);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // Auto-refresh every 30 min
  useEffect(() => {
    fetchAnalysis();
    const id = setInterval(fetchAnalysis, 30 * 60 * 1000);
    return () => clearInterval(id);
  }, []);

  // Countdown timer
  useEffect(() => {
    const id = setInterval(() => {
      setNextUpdate(p => (p <= 0 ? 30 * 60 : p - 1));
    }, 1000);
    return () => clearInterval(id);
  }, []);

  // ── Loading screen ──────────────────────────────────────────────────────────
  if (loading && !analysis) {
    return (
      <div className="min-h-screen bg-[#0a0e1a] flex items-center justify-center">
        <div className="text-center">
          <RefreshIcon className="w-16 h-16 text-cyan-400 mx-auto mb-4" spinning />
          <div className="text-cyan-400 text-xl font-mono">Generating Analysis…</div>
          <div className="text-gray-500 text-sm mt-2">Fetching live data from multiple sources</div>
        </div>
      </div>
    );
  }

  const a = analysis;

  return (
    <div className="min-h-screen bg-[#0a0e1a] text-gray-100 p-6">

      {/* ── Header ── */}
      <div className="mb-6 border-b border-cyan-900/30 pb-4">
        <div className="flex items-center justify-between flex-wrap gap-4">
          <div>
            <h1 className="text-3xl font-bold text-cyan-400 tracking-wider mb-1">
              XAU/USD LIVE ANALYSIS
            </h1>
            <div className="text-sm text-gray-500">IC Markets | Multi-Source Intelligence</div>
          </div>
          <div className="flex items-center gap-6">
            <div className="text-right">
              <div className="text-xs text-gray-500 mb-1">NEXT UPDATE</div>
              <div className="text-2xl text-cyan-400 font-bold">{formatTime(nextUpdate)}</div>
            </div>
            <button
              onClick={fetchAnalysis}
              disabled={loading}
              className="bg-cyan-600 hover:bg-cyan-500 disabled:bg-gray-700 px-6 py-3 rounded-lg flex items-center gap-2 transition-colors"
            >
              <RefreshIcon className="w-5 h-5" spinning={loading} />
              Refresh
            </button>
          </div>
        </div>
        {lastUpdate && (
          <div className="text-xs text-gray-500 mt-3">
            Last Updated:{' '}
            {lastUpdate.toLocaleString('en-US', { hour12: true, timeZone: 'Asia/Dubai' })} Dubai Time
          </div>
        )}
      </div>

      {/* ── Error ── */}
      {error && (
        <div className="bg-red-900/20 border border-red-500 rounded-lg p-4 mb-6 flex items-center gap-3">
          <AlertIcon className="text-red-400 shrink-0" />
          <div className="text-red-400">{error}</div>
        </div>
      )}

      {a && (
        <div className="space-y-6">

          {/* ── Price cards ── */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="bg-gradient-to-br from-cyan-900/20 to-blue-900/20 border border-cyan-500/30 rounded-lg p-6 glow-border">
              <div className="text-xs text-gray-500 mb-1">CURRENT PRICE</div>
              <div className="text-4xl font-bold text-cyan-400">${a.currentPrice?.toFixed(2)}</div>
              <div className={`text-sm mt-2 ${a.priceChange >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {a.priceChange >= 0 ? '▲' : '▼'} ${Math.abs(a.priceChange ?? 0).toFixed(2)}
              </div>
            </div>

            <div className="bg-gradient-to-br from-purple-900/20 to-pink-900/20 border border-purple-500/30 rounded-lg p-6">
              <div className="text-xs text-gray-500 mb-1">MARKET TREND</div>
              <div className="flex items-center gap-3 mt-2">
                {a.trend === 'BULLISH' ? <TrendUpIcon className="text-green-400 w-8 h-8" /> :
                 a.trend === 'BEARISH' ? <TrendDownIcon className="text-red-400 w-8 h-8" /> :
                 <div className="w-8 h-8 border-2 border-yellow-400 rounded-full" />}
                <div className="text-2xl font-bold">{a.trend}</div>
              </div>
            </div>

            <div className="bg-gradient-to-br from-green-900/20 to-emerald-900/20 border border-green-500/30 rounded-lg p-6">
              <div className="text-xs text-gray-500 mb-1">DIRECTION</div>
              <div className="text-2xl font-bold text-green-400">{a.movementExpectation?.direction}</div>
              <div className="text-sm text-gray-400 mt-1">{a.movementExpectation?.probability}% confidence</div>
            </div>

            <div className="bg-gradient-to-br from-orange-900/20 to-red-900/20 border border-orange-500/30 rounded-lg p-6">
              <div className="text-xs text-gray-500 mb-1">TARGET</div>
              <div className="text-xl font-bold text-orange-400">{a.movementExpectation?.targetRange}</div>
              <div className="text-sm text-gray-400 mt-1">{a.movementExpectation?.timeframe}</div>
            </div>
          </div>

          {/* ── Entry setups ── */}
          <div className="bg-gradient-to-br from-cyan-900/10 to-blue-900/10 border-2 border-cyan-500/50 rounded-lg p-6 glow-border">
            <h2 className="text-xl font-bold text-cyan-400 mb-4 flex items-center gap-2">
              <TargetIcon className="w-6 h-6" />
              HIGH CONFIDENCE SETUPS
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {a.entrySetups?.map((s, i) => (
                <div key={i}
                  className={`border-2 rounded-lg p-5 ${
                    s.type === 'LONG'
                      ? 'bg-green-900/20 border-green-500/50'
                      : 'bg-red-900/20 border-red-500/50'
                  }`}
                >
                  <div className="flex items-center justify-between mb-3">
                    <div className={`text-2xl font-bold ${s.type === 'LONG' ? 'text-green-400' : 'text-red-400'}`}>
                      {s.type}
                    </div>
                    <div className={`text-3xl font-bold ${confidenceColor(s.confidence)}`}>
                      {s.confidence}%
                    </div>
                  </div>
                  <div className="space-y-2 text-sm">
                    <div>
                      <span className="text-gray-500">Entry:</span>
                      <span className="text-cyan-400 ml-2 font-bold">{s.entry}</span>
                    </div>
                    <div>
                      <span className="text-gray-500">Stop:</span>
                      <span className="text-red-400 ml-2 font-bold">${s.stop}</span>
                    </div>
                    <div>
                      <span className="text-gray-500">Targets:</span>
                      <div className="text-green-400 ml-2 font-bold">
                        {s.targets?.map((t, j) => <div key={j}>TP{j + 1}: ${t}</div>)}
                      </div>
                    </div>
                    <div className="pt-2 border-t border-gray-700">
                      <div className="text-gray-400 text-xs">{s.reason}</div>
                      <div className="text-gray-500 text-xs mt-1">⏱ {s.timeframe}</div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* ── Multi-timeframe ── */}
          <div className="bg-gray-900/50 border border-gray-700 rounded-lg p-6">
            <h2 className="text-xl font-bold text-cyan-400 mb-4">MULTI-TIMEFRAME</h2>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              {a.timeframes && Object.entries(a.timeframes).map(([tf, desc]) => (
                <div key={tf} className="bg-gray-800/50 rounded-lg p-4">
                  <div className="text-xs text-gray-500 mb-2 uppercase">{tf}</div>
                  <div className="text-sm text-gray-300">{desc}</div>
                </div>
              ))}
            </div>
          </div>

          {/* ── Key levels ── */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="bg-red-900/20 border border-red-500/30 rounded-lg p-6">
              <h3 className="text-lg font-bold text-red-400 mb-3">RESISTANCE</h3>
              <div className="space-y-2">
                {a.keyLevels?.resistance?.map((lvl, i) => (
                  <div key={i} className="flex items-center justify-between bg-red-900/30 rounded px-3 py-2">
                    <span className="text-gray-400">R{i + 1}</span>
                    <span className="text-red-400 font-bold">${lvl}</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="bg-green-900/20 border border-green-500/30 rounded-lg p-6">
              <h3 className="text-lg font-bold text-green-400 mb-3">SUPPORT</h3>
              <div className="space-y-2">
                {a.keyLevels?.support?.map((lvl, i) => (
                  <div key={i} className="flex items-center justify-between bg-green-900/30 rounded px-3 py-2">
                    <span className="text-gray-400">S{i + 1}</span>
                    <span className="text-green-400 font-bold">${lvl}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* ── Fair Value Gaps ── */}
          <div className="bg-purple-900/20 border border-purple-500/30 rounded-lg p-6">
            <h2 className="text-xl font-bold text-purple-400 mb-4">FAIR VALUE GAPS</h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {a.fvg?.map((gap, i) => (
                <div key={i} className={`rounded-lg p-4 ${gap.type === 'bullish' ? 'bg-green-900/30' : 'bg-red-900/30'}`}>
                  <div className="flex items-center justify-between mb-2">
                    <span className={`font-bold ${gap.type === 'bullish' ? 'text-green-400' : 'text-red-400'}`}>
                      {gap.type.toUpperCase()}
                    </span>
                    <span className="text-xs text-gray-500">P{gap.priority}</span>
                  </div>
                  <div className="text-cyan-400">{gap.zone}</div>
                </div>
              ))}
            </div>
          </div>

          {/* ── Supply / Demand ── */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="bg-gray-900/50 border border-red-500/30 rounded-lg p-6">
              <h3 className="text-lg font-bold text-red-400 mb-3">SUPPLY ZONES</h3>
              <div className="space-y-2">
                {a.supplyDemand?.supply?.map((z, i) => (
                  <div key={i} className="bg-red-900/20 rounded-lg p-3">
                    <div className="text-cyan-400 mb-1">{z.zone}</div>
                    <div className="text-xs text-gray-400">Strength: {z.strength}</div>
                  </div>
                ))}
              </div>
            </div>
            <div className="bg-gray-900/50 border border-green-500/30 rounded-lg p-6">
              <h3 className="text-lg font-bold text-green-400 mb-3">DEMAND ZONES</h3>
              <div className="space-y-2">
                {a.supplyDemand?.demand?.map((z, i) => (
                  <div key={i} className="bg-green-900/20 rounded-lg p-3">
                    <div className="text-cyan-400 mb-1">{z.zone}</div>
                    <div className="text-xs text-gray-400">Strength: {z.strength}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* ── Smart Money ── */}
          <div className="bg-orange-900/20 border border-orange-500/30 rounded-lg p-6">
            <h2 className="text-xl font-bold text-orange-400 mb-4">SMART MONEY</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <h3 className="text-sm font-bold text-gray-400 mb-2">LIQUIDITY ZONES</h3>
                <div className="space-y-2">
                  {a.smartMoney?.liquidityZones?.map((z, i) => (
                    <div key={i} className="bg-orange-900/30 rounded p-3 text-sm text-gray-300">{z}</div>
                  ))}
                </div>
              </div>
              <div>
                <h3 className="text-sm font-bold text-gray-400 mb-2">ORDER BLOCKS</h3>
                <div className="space-y-2">
                  {a.smartMoney?.orderBlocks?.map((b, i) => (
                    <div key={i} className="bg-orange-900/30 rounded p-3 text-sm text-gray-300">{b}</div>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* ── News ── */}
          <div className="bg-yellow-900/20 border border-yellow-500/30 rounded-lg p-6">
            <h2 className="text-xl font-bold text-yellow-400 mb-4 flex items-center gap-2">
              <ClockIcon className="w-6 h-6" />
              NEWS & EVENTS
            </h2>
            <div className="space-y-3">
              {a.news?.map((ev, i) => (
                <div key={i} className="bg-yellow-900/30 rounded-lg p-4 flex items-center justify-between">
                  <div className="flex-1">
                    <div className="font-bold text-yellow-400">{ev.event}</div>
                    <div className="text-sm text-gray-400 mt-1">{ev.expected}</div>
                  </div>
                  <div className="text-right ml-4">
                    <div className="text-sm text-gray-500">{ev.time}</div>
                    <div className={`text-xs font-bold mt-1 ${
                      ev.impact === 'high' ? 'text-red-400' :
                      ev.impact === 'medium' ? 'text-yellow-400' : 'text-green-400'
                    }`}>
                      {ev.impact?.toUpperCase()}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

        </div>
      )}

      {/* ── Footer ── */}
      <div className="mt-8 pt-6 border-t border-cyan-900/30 text-center text-xs text-gray-500">
        <div>Automated Analysis | Updates Every 30 Minutes</div>
        <div className="mt-1">Multi-Source: TradingView • IC Markets • News APIs • Economic Calendar</div>
        <div className="mt-1 text-yellow-500">⚠ Educational purposes. Verify before trading.</div>
      </div>
    </div>
  );
}
