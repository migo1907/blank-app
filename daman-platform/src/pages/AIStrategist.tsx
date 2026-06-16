import { useState, useEffect, useRef } from 'react';
import {
  Sparkles, TrendingUp, TrendingDown, Activity, Volume2, Pause, Play, Square,
  AlertTriangle, Eye, Briefcase, RefreshCw, Mail, CheckCircle2, Bot,
  MessageSquare, Send, User,
} from 'lucide-react';
import Reveal from '../components/Reveal';
import Skeleton from '../components/Skeleton';
import { useSpeech } from '../hooks/useSpeech';
import { marketDataService } from '../services/marketDataService';
import { streamChat, ChatTurn } from '../services/aiChatService';
import {
  getMarketWrapUp, getPortfolioAnalysis, MarketWrapUp, PortfolioAnalysis, CommentaryResult,
} from '../services/aiCommentaryService';
import {
  subscribe, getLocalSubscription, unsubscribe, isValidEmail,
} from '../services/commentarySubscriptionService';

type Tab = 'wrapup' | 'portfolio' | 'chat';

const toneStyles: Record<string, string> = {
  bullish: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400',
  bearish: 'bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-400',
  neutral: 'bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-300',
  mixed: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
};

const ratingStyles: Record<string, string> = {
  'strong-buy': 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400',
  buy: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400',
  hold: 'bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-300',
  reduce: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
  sell: 'bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-400',
};

// Richer context: index quotes + derived breadth + a volatility/risk read, so
// Hermes reasons from concrete numbers rather than vibes.
async function buildMarketContext() {
  try {
    const map = await marketDataService.fetchMarketData(['S&P 500', 'Nasdaq', 'Dow Jones', 'VIX']);
    const quotes = Array.from(map.values());
    if (quotes.length === 0) return undefined;

    const indices = quotes.filter((q) => q.name !== 'VIX');
    const vix = quotes.find((q) => q.name === 'VIX');
    const advancers = indices.filter((q) => q.changePercent >= 0).length;
    const avgChange = indices.length
      ? indices.reduce((s, q) => s + q.changePercent, 0) / indices.length
      : 0;

    return {
      indices: indices.map((q) => ({
        name: q.name, price: Number(q.price.toFixed(2)), changePercent: Number(q.changePercent.toFixed(2)),
      })),
      volatility: vix ? { vix: Number(vix.price.toFixed(2)), vixChangePercent: Number(vix.changePercent.toFixed(2)) } : undefined,
      derived: {
        breadth: `${advancers}/${indices.length} indices higher`,
        avg_index_change_pct: Number(avgChange.toFixed(2)),
        risk_gauge: vix ? (vix.price < 15 ? 'low (complacent)' : vix.price < 22 ? 'normal' : 'elevated (fearful)') : 'unknown',
      },
      as_of: new Date().toISOString(),
    };
  } catch {
    return undefined;
  }
}

interface RawHolding { symbol: string; quantity: number; avg_cost: number; current_price?: number; }

function readPortfolio(): RawHolding[] {
  try {
    return JSON.parse(localStorage.getItem('portfolio') || '[]');
  } catch {
    return [];
  }
}

// Enrich holdings with portfolio weights + P&L so Hermes can reason about
// concentration and risk concretely.
function enrichHoldings(holdings: RawHolding[]) {
  const valued = holdings.map((h) => {
    const price = h.current_price ?? h.avg_cost;
    const marketValue = price * h.quantity;
    const costBasis = h.avg_cost * h.quantity;
    const plPct = costBasis > 0 ? ((marketValue - costBasis) / costBasis) * 100 : 0;
    return { ...h, marketValue, plPct };
  });
  const total = valued.reduce((s, h) => s + h.marketValue, 0) || 1;
  return {
    total_value: Number(total.toFixed(2)),
    positions: valued.map((h) => ({
      ticker: h.symbol,
      quantity: h.quantity,
      avg_cost: h.avg_cost,
      current_price: Number((h.current_price ?? h.avg_cost).toFixed(2)),
      weight_pct: Number(((h.marketValue / total) * 100).toFixed(1)),
      pl_pct: Number(h.plPct.toFixed(2)),
    })),
    largest_position_weight_pct: Number(
      (Math.max(...valued.map((h) => h.marketValue)) / total * 100).toFixed(1)
    ),
  };
}

function AudioBar({ script }: { script: string }) {
  const { supported, speaking, paused, speak, pause, resume, stop } = useSpeech();
  if (!supported) return null;
  return (
    <div className="flex items-center gap-2 flex-wrap">
      {!speaking ? (
        <button
          onClick={() => speak(script)}
          className="inline-flex items-center gap-2 bg-daman-blue-600 hover:bg-daman-blue-700 text-white text-sm font-semibold px-4 py-2 rounded-lg transition-colors"
        >
          <Volume2 className="h-4 w-4" /> Listen
        </button>
      ) : (
        <>
          {paused ? (
            <button onClick={resume} className="inline-flex items-center gap-2 bg-daman-blue-600 hover:bg-daman-blue-700 text-white text-sm font-semibold px-4 py-2 rounded-lg transition-colors">
              <Play className="h-4 w-4" /> Resume
            </button>
          ) : (
            <button onClick={pause} className="inline-flex items-center gap-2 bg-slate-200 dark:bg-slate-700 text-slate-800 dark:text-slate-200 text-sm font-semibold px-4 py-2 rounded-lg transition-colors">
              <Pause className="h-4 w-4" /> Pause
            </button>
          )}
          <button onClick={stop} className="inline-flex items-center gap-2 bg-slate-200 dark:bg-slate-700 text-slate-800 dark:text-slate-200 text-sm font-semibold px-4 py-2 rounded-lg transition-colors">
            <Square className="h-4 w-4" /> Stop
          </button>
          <span className="inline-flex items-center gap-1.5 text-sm text-daman-blue-600 dark:text-daman-blue-300">
            <span className="h-2 w-2 rounded-full bg-daman-blue-500 animate-pulse" /> Narrating…
          </span>
        </>
      )}
    </div>
  );
}

function Section({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <Reveal className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-6">
      <h3 className="flex items-center gap-2 text-lg font-bold text-slate-900 dark:text-white mb-3">
        {icon} {title}
      </h3>
      {children}
    </Reveal>
  );
}

function LoadingState() {
  return (
    <div className="space-y-4">
      {[0, 1, 2].map((i) => (
        <div key={i} className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-6">
          <Skeleton className="h-5 w-48 mb-4" />
          <Skeleton className="h-4 w-full mb-2" />
          <Skeleton className="h-4 w-5/6 mb-2" />
          <Skeleton className="h-4 w-2/3" />
        </div>
      ))}
    </div>
  );
}

function DemoBadge() {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">
      <AlertTriangle className="h-3.5 w-3.5" /> Sample output — add ANTHROPIC_API_KEY for live Claude analysis
    </span>
  );
}

export default function AIStrategist() {
  const [tab, setTab] = useState<Tab>('wrapup');

  const [wrap, setWrap] = useState<CommentaryResult<MarketWrapUp> | null>(null);
  const [wrapLoading, setWrapLoading] = useState(false);

  const [port, setPort] = useState<CommentaryResult<PortfolioAnalysis> | null>(null);
  const [portLoading, setPortLoading] = useState(false);
  const [portError, setPortError] = useState<string | null>(null);

  const loadWrap = async () => {
    setWrapLoading(true);
    const ctx = await buildMarketContext();
    setWrap(await getMarketWrapUp(ctx));
    setWrapLoading(false);
  };

  const loadPortfolio = async () => {
    const holdings = readPortfolio();
    if (!holdings || holdings.length === 0) {
      setPortError('No portfolio positions found. Add holdings on the Portfolio page first.');
      setPort(null);
      return;
    }
    setPortError(null);
    setPortLoading(true);
    const ctx = await buildMarketContext();
    setPort(await getPortfolioAnalysis(enrichHoldings(holdings), ctx));
    setPortLoading(false);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-slate-50 dark:from-slate-900 dark:via-slate-800 dark:to-slate-900 p-4 md:p-8">
      <div className="max-w-5xl mx-auto">
        {/* Header */}
        <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-xl border border-slate-200 dark:border-slate-700 p-6 md:p-8 mb-6">
          <div className="flex items-center gap-3 mb-2">
            <div className="bg-gradient-to-br from-daman-blue-600 to-daman-blue-800 p-3 rounded-xl">
              <Sparkles className="h-7 w-7 text-white" />
            </div>
            <div>
              <h1 className="text-2xl md:text-3xl font-bold text-slate-900 dark:text-white flex items-center gap-2">
                Hermes — AI Strategist
              </h1>
              <p className="text-slate-600 dark:text-slate-400 text-sm flex items-center gap-1.5">
                <Bot className="h-4 w-4" /> Market intelligence powered by Claude
              </p>
            </div>
          </div>

          {/* Tabs */}
          <div className="flex gap-2 mt-6 border-b border-slate-200 dark:border-slate-700">
            <button
              onClick={() => setTab('wrapup')}
              className={`relative flex items-center gap-2 px-4 py-3 text-sm font-semibold transition-colors ${
                tab === 'wrapup' ? 'text-daman-blue-600 dark:text-daman-blue-300' : 'text-slate-500 dark:text-slate-400 hover:text-daman-blue-600'
              }`}
            >
              <Activity className="h-4 w-4" /> Market Wrap-Up
              {tab === 'wrapup' && <span className="absolute left-0 right-0 -bottom-px h-0.5 bg-daman-blue-600" />}
            </button>
            <button
              onClick={() => setTab('portfolio')}
              className={`relative flex items-center gap-2 px-4 py-3 text-sm font-semibold transition-colors ${
                tab === 'portfolio' ? 'text-daman-blue-600 dark:text-daman-blue-300' : 'text-slate-500 dark:text-slate-400 hover:text-daman-blue-600'
              }`}
            >
              <Briefcase className="h-4 w-4" /> Portfolio Analysis
              {tab === 'portfolio' && <span className="absolute left-0 right-0 -bottom-px h-0.5 bg-daman-blue-600" />}
            </button>
            <button
              onClick={() => setTab('chat')}
              className={`relative flex items-center gap-2 px-4 py-3 text-sm font-semibold transition-colors ${
                tab === 'chat' ? 'text-daman-blue-600 dark:text-daman-blue-300' : 'text-slate-500 dark:text-slate-400 hover:text-daman-blue-600'
              }`}
            >
              <MessageSquare className="h-4 w-4" /> Ask Hermes
              {tab === 'chat' && <span className="absolute left-0 right-0 -bottom-px h-0.5 bg-daman-blue-600" />}
            </button>
          </div>
        </div>

        {tab === 'wrapup' && <WrapUpTab wrap={wrap} loading={wrapLoading} onGenerate={loadWrap} />}
        {tab === 'portfolio' && (
          <PortfolioTab port={port} loading={portLoading} error={portError} onGenerate={loadPortfolio} />
        )}
        {tab === 'chat' && <ChatTab />}
      </div>
    </div>
  );
}

function WrapUpTab({
  wrap, loading, onGenerate,
}: {
  wrap: CommentaryResult<MarketWrapUp> | null;
  loading: boolean;
  onGenerate: () => void;
}) {
  return (
    <div className="space-y-4">
      {!wrap && !loading && (
        <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-10 text-center">
          <Sparkles className="h-12 w-12 text-daman-blue-500 mx-auto mb-4" />
          <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-2">Generate today's market wrap-up</h2>
          <p className="text-slate-600 dark:text-slate-400 mb-6 max-w-lg mx-auto">
            A fundamentals-and-technicals-loaded session recap with swing-trade and day-trade ideas — written and narrated by Claude.
          </p>
          <button
            onClick={onGenerate}
            className="inline-flex items-center gap-2 bg-daman-blue-600 hover:bg-daman-blue-700 text-white font-semibold px-6 py-3 rounded-lg shadow-lg transition-all hover:-translate-y-0.5"
          >
            <Sparkles className="h-5 w-5" /> Generate Wrap-Up
          </button>
        </div>
      )}

      {loading && <LoadingState />}

      {wrap && !loading && (
        <>
          <Reveal className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-6">
            <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
              <span className={`text-xs font-bold px-3 py-1 rounded-full uppercase tracking-wide ${toneStyles[wrap.data.market_tone] || toneStyles.neutral}`}>
                {wrap.data.market_tone}
              </span>
              <div className="flex items-center gap-3">
                {wrap.demo && <DemoBadge />}
                <button onClick={onGenerate} className="inline-flex items-center gap-1.5 text-sm text-daman-blue-600 dark:text-daman-blue-300 hover:underline">
                  <RefreshCw className="h-4 w-4" /> Regenerate
                </button>
              </div>
            </div>
            <h2 className="text-2xl font-bold text-slate-900 dark:text-white mb-3">{wrap.data.headline}</h2>
            <p className="text-slate-700 dark:text-slate-300 leading-relaxed mb-4">{wrap.data.executive_summary}</p>
            <AudioBar script={wrap.data.audio_script} />
          </Reveal>

          <Section title="Technical Analysis" icon={<Activity className="h-5 w-5 text-daman-blue-600" />}>
            <p className="text-slate-700 dark:text-slate-300 mb-4">{wrap.data.technical_analysis.overview}</p>
            <div className="overflow-x-auto mb-4">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-slate-500 dark:text-slate-400">
                    <th className="py-2 pr-4 font-semibold">Index</th>
                    <th className="py-2 pr-4 font-semibold">Support</th>
                    <th className="py-2 pr-4 font-semibold">Resistance</th>
                    <th className="py-2 font-semibold">Trend</th>
                  </tr>
                </thead>
                <tbody>
                  {wrap.data.technical_analysis.key_levels.map((k, i) => (
                    <tr key={i} className="border-t border-slate-100 dark:border-slate-700 text-slate-800 dark:text-slate-200">
                      <td className="py-2 pr-4 font-semibold">{k.index}</td>
                      <td className="py-2 pr-4">{k.support}</td>
                      <td className="py-2 pr-4">{k.resistance}</td>
                      <td className="py-2 capitalize">{k.trend}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="text-slate-600 dark:text-slate-400 text-sm">{wrap.data.technical_analysis.indicators}</p>
          </Section>

          <Section title="Fundamental Drivers" icon={<TrendingUp className="h-5 w-5 text-daman-blue-600" />}>
            <div className="space-y-3">
              {wrap.data.fundamental_drivers.map((d, i) => (
                <div key={i} className="border-l-2 border-daman-blue-500 pl-4">
                  <div className="font-semibold text-slate-900 dark:text-white">{d.title}</div>
                  <div className="text-slate-600 dark:text-slate-400 text-sm">{d.detail}</div>
                </div>
              ))}
            </div>
            <p className="text-slate-700 dark:text-slate-300 mt-4">{wrap.data.macro_backdrop}</p>
          </Section>

          <Section title="Sector Rotation" icon={<RefreshCw className="h-5 w-5 text-daman-blue-600" />}>
            <div className="grid sm:grid-cols-2 gap-3">
              {wrap.data.sector_rotation.map((s, i) => (
                <div key={i} className="bg-slate-50 dark:bg-slate-900 rounded-lg p-3 border border-slate-200 dark:border-slate-700">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-slate-900 dark:text-white">{s.sector}</span>
                    <span className="text-xs font-semibold text-daman-blue-600 dark:text-daman-blue-300 capitalize">{s.stance}</span>
                  </div>
                  <div className="text-slate-600 dark:text-slate-400 text-sm mt-1">{s.note}</div>
                </div>
              ))}
            </div>
          </Section>

          <Section title="Swing Trade Ideas" icon={<TrendingUp className="h-5 w-5 text-daman-blue-600" />}>
            <div className="grid md:grid-cols-2 gap-4">
              {wrap.data.swing_trade_ideas.map((s, i) => (
                <div key={i} className="bg-slate-50 dark:bg-slate-900 rounded-lg p-4 border border-slate-200 dark:border-slate-700">
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-bold text-slate-900 dark:text-white">{s.ticker}</span>
                    <span className={`inline-flex items-center gap-1 text-xs font-bold px-2 py-0.5 rounded ${s.direction === 'long' ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400' : 'bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-400'}`}>
                      {s.direction === 'long' ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
                      {s.direction.toUpperCase()}
                    </span>
                  </div>
                  <p className="text-slate-700 dark:text-slate-300 text-sm mb-3">{s.thesis}</p>
                  <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
                    <div><dt className="text-slate-400 inline">Entry: </dt><dd className="inline text-slate-700 dark:text-slate-300">{s.entry_zone}</dd></div>
                    <div><dt className="text-slate-400 inline">Stop: </dt><dd className="inline text-slate-700 dark:text-slate-300">{s.stop}</dd></div>
                    <div><dt className="text-slate-400 inline">Targets: </dt><dd className="inline text-slate-700 dark:text-slate-300">{s.targets}</dd></div>
                    <div><dt className="text-slate-400 inline">Timeframe: </dt><dd className="inline text-slate-700 dark:text-slate-300">{s.timeframe}</dd></div>
                  </dl>
                  <div className="mt-2 text-xs font-semibold text-daman-blue-600 dark:text-daman-blue-300">Conviction: <span className="capitalize">{s.conviction}</span></div>
                </div>
              ))}
            </div>
          </Section>

          <Section title="Day Trade Ideas" icon={<Activity className="h-5 w-5 text-daman-blue-600" />}>
            <div className="space-y-3">
              {wrap.data.day_trade_ideas.map((d, i) => (
                <div key={i} className="bg-slate-50 dark:bg-slate-900 rounded-lg p-4 border border-slate-200 dark:border-slate-700">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-bold text-slate-900 dark:text-white">{d.ticker}</span>
                    <span className={`text-xs font-bold px-2 py-0.5 rounded ${d.direction === 'long' ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400' : 'bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-400'}`}>{d.direction.toUpperCase()}</span>
                  </div>
                  <p className="text-slate-700 dark:text-slate-300 text-sm"><span className="font-semibold">Setup:</span> {d.setup}</p>
                  <p className="text-slate-700 dark:text-slate-300 text-sm"><span className="font-semibold">Trigger:</span> {d.trigger}</p>
                  <p className="text-amber-700 dark:text-amber-400 text-sm mt-1"><span className="font-semibold">Risk:</span> {d.risk_note}</p>
                </div>
              ))}
            </div>
          </Section>

          <div className="grid md:grid-cols-2 gap-4">
            <Section title="Key Risks" icon={<AlertTriangle className="h-5 w-5 text-amber-600" />}>
              <ul className="space-y-2">
                {wrap.data.key_risks.map((r, i) => (
                  <li key={i} className="flex gap-2 text-sm text-slate-700 dark:text-slate-300"><span className="text-amber-500">•</span> {r}</li>
                ))}
              </ul>
            </Section>
            <Section title="What to Watch" icon={<Eye className="h-5 w-5 text-daman-blue-600" />}>
              <ul className="space-y-2">
                {wrap.data.what_to_watch.map((w, i) => (
                  <li key={i} className="flex gap-2 text-sm text-slate-700 dark:text-slate-300"><span className="text-daman-blue-500">•</span> {w}</li>
                ))}
              </ul>
            </Section>
          </div>

          <p className="text-xs text-slate-500 dark:text-slate-400 italic px-2">{wrap.data.disclaimer}</p>

          <SubscribeCard />
        </>
      )}
    </div>
  );
}

function PortfolioTab({
  port, loading, error, onGenerate,
}: {
  port: CommentaryResult<PortfolioAnalysis> | null;
  loading: boolean;
  error: string | null;
  onGenerate: () => void;
}) {
  return (
    <div className="space-y-4">
      {!port && !loading && (
        <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-10 text-center">
          <Briefcase className="h-12 w-12 text-daman-blue-500 mx-auto mb-4" />
          <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-2">Hermes portfolio analysis</h2>
          <p className="text-slate-600 dark:text-slate-400 mb-6 max-w-lg mx-auto">
            A fundamental + technical review of your holdings, with diversification, risk, and actionable suggestions.
          </p>
          {error && <p className="text-amber-600 dark:text-amber-400 text-sm mb-4">{error}</p>}
          <button
            onClick={onGenerate}
            className="inline-flex items-center gap-2 bg-daman-blue-600 hover:bg-daman-blue-700 text-white font-semibold px-6 py-3 rounded-lg shadow-lg transition-all hover:-translate-y-0.5"
          >
            <Sparkles className="h-5 w-5" /> Analyze My Portfolio
          </button>
        </div>
      )}

      {loading && <LoadingState />}

      {port && !loading && (
        <>
          <Reveal className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-6">
            <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
              <span className="text-xs font-bold px-3 py-1 rounded-full uppercase tracking-wide bg-daman-blue-100 text-daman-blue-700 dark:bg-daman-blue-900/30 dark:text-daman-blue-300">
                Risk: {port.data.risk_level}
              </span>
              <div className="flex items-center gap-3">
                {port.demo && <DemoBadge />}
                <button onClick={onGenerate} className="inline-flex items-center gap-1.5 text-sm text-daman-blue-600 dark:text-daman-blue-300 hover:underline">
                  <RefreshCw className="h-4 w-4" /> Re-analyze
                </button>
              </div>
            </div>
            <h2 className="text-2xl font-bold text-slate-900 dark:text-white mb-3">{port.data.headline}</h2>
            <p className="text-slate-700 dark:text-slate-300 leading-relaxed mb-2">{port.data.overall_assessment}</p>
            <p className="text-sm text-slate-600 dark:text-slate-400 mb-4">
              <span className="font-semibold">Diversification ({port.data.diversification.rating}):</span> {port.data.diversification.comment}
            </p>
            <AudioBar script={port.data.audio_script} />
          </Reveal>

          <Section title="Holdings Analysis" icon={<Briefcase className="h-5 w-5 text-daman-blue-600" />}>
            <div className="space-y-4">
              {port.data.holdings_analysis.map((h, i) => (
                <div key={i} className="bg-slate-50 dark:bg-slate-900 rounded-lg p-4 border border-slate-200 dark:border-slate-700">
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-bold text-slate-900 dark:text-white">{h.ticker}</span>
                    <span className={`text-xs font-bold px-2 py-0.5 rounded uppercase ${ratingStyles[h.rating] || ratingStyles.hold}`}>{h.rating}</span>
                  </div>
                  <p className="text-sm text-slate-700 dark:text-slate-300 mb-1"><span className="font-semibold text-daman-blue-600 dark:text-daman-blue-300">Fundamental:</span> {h.fundamental}</p>
                  <p className="text-sm text-slate-700 dark:text-slate-300"><span className="font-semibold text-daman-blue-600 dark:text-daman-blue-300">Technical:</span> {h.technical}</p>
                </div>
              ))}
            </div>
          </Section>

          <Section title="Suggestions" icon={<Sparkles className="h-5 w-5 text-daman-blue-600" />}>
            <div className="space-y-2">
              {port.data.suggestions.map((s, i) => (
                <div key={i} className="flex items-start gap-3 bg-slate-50 dark:bg-slate-900 rounded-lg p-3 border border-slate-200 dark:border-slate-700">
                  <span className="text-xs font-bold px-2 py-0.5 rounded uppercase bg-daman-blue-600 text-white shrink-0">{s.action}</span>
                  <div className="text-sm">
                    <span className="font-semibold text-slate-900 dark:text-white">{s.ticker}</span>
                    <span className="text-slate-600 dark:text-slate-400"> — {s.rationale}</span>
                  </div>
                </div>
              ))}
            </div>
          </Section>

          {port.data.risk_warnings.length > 0 && (
            <Section title="Risk Warnings" icon={<AlertTriangle className="h-5 w-5 text-amber-600" />}>
              <ul className="space-y-2">
                {port.data.risk_warnings.map((r, i) => (
                  <li key={i} className="flex gap-2 text-sm text-slate-700 dark:text-slate-300"><span className="text-amber-500">•</span> {r}</li>
                ))}
              </ul>
            </Section>
          )}

          <p className="text-xs text-slate-500 dark:text-slate-400 italic px-2">{port.data.disclaimer}</p>
        </>
      )}
    </div>
  );
}

const SUGGESTED = [
  'What is the market tone today and why?',
  'Give me a swing-trade idea on a large-cap tech name with risk levels.',
  'Analyze the risk in my current portfolio.',
  'Explain what rising yields mean for growth stocks.',
];

function ChatTab() {
  const [messages, setMessages] = useState<ChatTurn[]>([]);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const abortRef = useRef<(() => void) | null>(null);
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => () => abortRef.current?.(), []);

  const send = async (text: string) => {
    const content = text.trim();
    if (!content || streaming) return;
    setInput('');

    const history: ChatTurn[] = [...messages, { role: 'user', content }];
    setMessages([...history, { role: 'assistant', content: '' }]);
    setStreaming(true);

    const marketCtx = await buildMarketContext();
    const holdings = readPortfolio();
    const context = {
      market: marketCtx,
      portfolio: holdings.length ? enrichHoldings(holdings) : undefined,
    };

    abortRef.current = streamChat(history, context, {
      onToken: (t) =>
        setMessages((prev) => {
          const next = [...prev];
          next[next.length - 1] = { role: 'assistant', content: next[next.length - 1].content + t };
          return next;
        }),
      onDone: () => setStreaming(false),
      onError: (msg) =>
        setMessages((prev) => {
          const next = [...prev];
          next[next.length - 1] = { role: 'assistant', content: `⚠️ ${msg}` };
          return next;
        }),
    });
  };

  return (
    <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 flex flex-col h-[70vh]">
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <div className="h-full flex flex-col items-center justify-center text-center px-4">
            <div className="bg-gradient-to-br from-daman-blue-600 to-daman-blue-800 p-3 rounded-xl mb-3">
              <MessageSquare className="h-7 w-7 text-white" />
            </div>
            <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-1">Ask Hermes anything</h3>
            <p className="text-slate-600 dark:text-slate-400 text-sm mb-5 max-w-md">
              Tickers, macro, strategy, or your portfolio — answers blend fundamentals and technicals, streamed live.
            </p>
            <div className="grid sm:grid-cols-2 gap-2 w-full max-w-2xl">
              {SUGGESTED.map((s) => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  className="text-left text-sm bg-slate-50 dark:bg-slate-900 hover:bg-daman-blue-50 dark:hover:bg-slate-700 border border-slate-200 dark:border-slate-700 rounded-lg px-3 py-2 text-slate-700 dark:text-slate-300 transition-colors"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} className={`flex gap-3 ${m.role === 'user' ? 'flex-row-reverse' : ''}`}>
            <div className={`shrink-0 h-8 w-8 rounded-full flex items-center justify-center ${m.role === 'user' ? 'bg-slate-200 dark:bg-slate-700' : 'bg-gradient-to-br from-daman-blue-600 to-daman-blue-800'}`}>
              {m.role === 'user' ? <User className="h-4 w-4 text-slate-600 dark:text-slate-300" /> : <Sparkles className="h-4 w-4 text-white" />}
            </div>
            <div className={`max-w-[80%] rounded-2xl px-4 py-2.5 text-sm whitespace-pre-wrap leading-relaxed ${
              m.role === 'user'
                ? 'bg-daman-blue-600 text-white'
                : 'bg-slate-100 dark:bg-slate-900 text-slate-800 dark:text-slate-200'
            }`}>
              {m.content || (streaming && i === messages.length - 1 ? <span className="inline-block animate-pulse">▍</span> : '')}
            </div>
          </div>
        ))}
        <div ref={endRef} />
      </div>

      <div className="border-t border-slate-200 dark:border-slate-700 p-3">
        <div className="flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && send(input)}
            placeholder="Ask Hermes about markets, a ticker, or your portfolio…"
            className="flex-1 px-4 py-2.5 rounded-lg bg-slate-50 dark:bg-slate-900 border border-slate-300 dark:border-slate-600 text-slate-900 dark:text-white focus:outline-none focus:border-daman-blue-500"
          />
          <button
            onClick={() => send(input)}
            disabled={streaming || !input.trim()}
            className="bg-daman-blue-600 hover:bg-daman-blue-700 disabled:opacity-50 text-white px-4 py-2.5 rounded-lg transition-colors"
            aria-label="Send"
          >
            <Send className="h-5 w-5" />
          </button>
        </div>
        <p className="text-[11px] text-slate-400 mt-2 text-center">
          Hermes is an AI assistant. Educational only — not personalized financial advice.
        </p>
      </div>
    </div>
  );
}

function SubscribeCard() {
  const [email, setEmail] = useState('');
  const [frequency, setFrequency] = useState<'daily' | 'weekdays'>('weekdays');
  const [status, setStatus] = useState<{ ok: boolean; message: string } | null>(null);
  const [existing, setExisting] = useState(() => getLocalSubscription());
  const [busy, setBusy] = useState(false);

  const handleSubscribe = async () => {
    if (!isValidEmail(email)) {
      setStatus({ ok: false, message: 'Please enter a valid email address.' });
      return;
    }
    setBusy(true);
    const res = await subscribe(email, frequency);
    setBusy(false);
    setStatus(res);
    if (res.ok) setExisting(getLocalSubscription());
  };

  const handleUnsubscribe = () => {
    const res = unsubscribe();
    setStatus(res);
    setExisting(null);
    setEmail('');
  };

  return (
    <Reveal className="bg-gradient-to-br from-daman-blue-600 to-daman-blue-800 rounded-xl p-6 text-white">
      <div className="flex items-center gap-2 mb-2">
        <Mail className="h-5 w-5" />
        <h3 className="text-lg font-bold">Daily Market Commentary</h3>
      </div>

      {existing ? (
        <div>
          <p className="flex items-center gap-2 text-blue-100 mb-3">
            <CheckCircle2 className="h-5 w-5" /> Subscribed as <strong>{existing.email}</strong> ({existing.frequency})
          </p>
          <button onClick={handleUnsubscribe} className="text-sm font-semibold bg-white/15 hover:bg-white/25 px-4 py-2 rounded-lg transition-colors">
            Unsubscribe
          </button>
        </div>
      ) : (
        <>
          <p className="text-blue-100 text-sm mb-4">Get Hermes's wrap-up delivered to your inbox. Cancel anytime.</p>
          <div className="flex flex-col sm:flex-row gap-3">
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              className="flex-1 px-4 py-2.5 rounded-lg text-slate-900 focus:outline-none focus:ring-2 focus:ring-white/50"
            />
            <select
              value={frequency}
              onChange={(e) => setFrequency(e.target.value as 'daily' | 'weekdays')}
              className="px-4 py-2.5 rounded-lg text-slate-900 focus:outline-none focus:ring-2 focus:ring-white/50"
            >
              <option value="weekdays">Weekdays</option>
              <option value="daily">Daily</option>
            </select>
            <button
              onClick={handleSubscribe}
              disabled={busy}
              className="bg-white text-daman-blue-700 font-semibold px-6 py-2.5 rounded-lg hover:bg-blue-50 transition-colors disabled:opacity-60"
            >
              {busy ? 'Subscribing…' : 'Subscribe'}
            </button>
          </div>
        </>
      )}

      {status && (
        <p className={`text-sm mt-3 ${status.ok ? 'text-blue-100' : 'text-rose-200'}`}>{status.message}</p>
      )}
    </Reveal>
  );
}
