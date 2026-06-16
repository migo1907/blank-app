import { useState } from 'react';
import {
  Sparkles, TrendingUp, TrendingDown, Activity, Volume2, Pause, Play, Square,
  AlertTriangle, Eye, Briefcase, RefreshCw, Bot,
  MessageSquare, Search,
} from 'lucide-react';
import Reveal from '../components/Reveal';
import Skeleton from '../components/Skeleton';
import HermesChat from '../components/HermesChat';
import ShareButtons from '../components/ShareButtons';
import NewsletterSignup from '../components/NewsletterSignup';
import { askHermes } from '../lib/hermesBus';
import { useSpeech } from '../hooks/useSpeech';
import { buildMarketContext, readPortfolio, enrichHoldings } from '../services/marketContext';
import {
  getMarketWrapUp, getPortfolioAnalysis, getTickerResearch,
  MarketWrapUp, PortfolioAnalysis, TickerResearch, CommentaryResult,
} from '../services/aiCommentaryService';

type Tab = 'wrapup' | 'research' | 'compare' | 'portfolio' | 'chat';

// Plain-text serializers for Copy/Share.
function wrapUpToText(w: MarketWrapUp): string {
  return [
    `DAMAN — Market Wrap-Up (${w.market_tone.toUpperCase()})`,
    w.headline, '', w.executive_summary, '',
    `TECHNICAL: ${w.technical_analysis.overview}`,
    `MACRO: ${w.macro_backdrop}`, '',
    'SWING IDEAS:',
    ...w.swing_trade_ideas.map((s) => `• ${s.ticker} ${s.direction.toUpperCase()} — ${s.thesis} (entry ${s.entry_zone}, stop ${s.stop}, targets ${s.targets})`),
    '', 'KEY RISKS:', ...w.key_risks.map((r) => `• ${r}`), '', w.disclaimer,
  ].join('\n');
}
function researchToText(r: TickerResearch): string {
  return [
    `DAMAN — ${r.ticker} research (${r.rating.toUpperCase()})`,
    r.one_liner, '',
    `FUNDAMENTAL: ${r.fundamental.summary}`,
    `TECHNICAL (${r.technical.trend}): ${r.technical.summary}`, '',
    'BULL CASE:', ...r.bull_case.map((b) => `• ${b}`),
    'BEAR CASE:', ...r.bear_case.map((b) => `• ${b}`), '', r.disclaimer,
  ].join('\n');
}

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

  const [research, setResearch] = useState<CommentaryResult<TickerResearch> | null>(null);
  const [researchLoading, setResearchLoading] = useState(false);

  const [compare, setCompare] = useState<{ a: CommentaryResult<TickerResearch>; b: CommentaryResult<TickerResearch> } | null>(null);
  const [compareLoading, setCompareLoading] = useState(false);

  const loadResearch = async (ticker: string) => {
    const sym = ticker.toUpperCase().trim();
    if (!sym) return;
    setResearchLoading(true);
    const ctx = await buildMarketContext();
    setResearch(await getTickerResearch(sym, ctx));
    setResearchLoading(false);
  };

  const loadCompare = async (symA: string, symB: string) => {
    const a = symA.toUpperCase().trim();
    const b = symB.toUpperCase().trim();
    if (!a || !b) return;
    setCompareLoading(true);
    const ctx = await buildMarketContext();
    const [ra, rb] = await Promise.all([getTickerResearch(a, ctx), getTickerResearch(b, ctx)]);
    setCompare({ a: ra, b: rb });
    setCompareLoading(false);
  };

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
          <div className="flex gap-2 mt-6 border-b border-slate-200 dark:border-slate-700 overflow-x-auto scrollbar-hide">
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
              onClick={() => setTab('research')}
              className={`relative flex items-center gap-2 px-4 py-3 text-sm font-semibold transition-colors ${
                tab === 'research' ? 'text-daman-blue-600 dark:text-daman-blue-300' : 'text-slate-500 dark:text-slate-400 hover:text-daman-blue-600'
              }`}
            >
              <Search className="h-4 w-4" /> Ticker Research
              {tab === 'research' && <span className="absolute left-0 right-0 -bottom-px h-0.5 bg-daman-blue-600" />}
            </button>
            <button
              onClick={() => setTab('compare')}
              className={`relative flex items-center gap-2 px-4 py-3 text-sm font-semibold whitespace-nowrap transition-colors ${
                tab === 'compare' ? 'text-daman-blue-600 dark:text-daman-blue-300' : 'text-slate-500 dark:text-slate-400 hover:text-daman-blue-600'
              }`}
            >
              <TrendingUp className="h-4 w-4" /> Compare
              {tab === 'compare' && <span className="absolute left-0 right-0 -bottom-px h-0.5 bg-daman-blue-600" />}
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
        {tab === 'research' && <ResearchTab research={research} loading={researchLoading} onSearch={loadResearch} />}
        {tab === 'compare' && <CompareTab compare={compare} loading={compareLoading} onCompare={loadCompare} />}
        {tab === 'portfolio' && (
          <PortfolioTab port={port} loading={portLoading} error={portError} onGenerate={loadPortfolio} />
        )}
        {tab === 'chat' && <HermesChat />}
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
              <div className="flex items-center gap-3 flex-wrap">
                {wrap.demo && <DemoBadge />}
                <ShareButtons text={wrapUpToText(wrap.data)} title="DAMAN — Market Wrap-Up" />
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

          <Reveal><NewsletterSignup /></Reveal>
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

function CompareColumn({ res }: { res: CommentaryResult<TickerResearch> }) {
  const d = res.data;
  return (
    <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-5">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xl font-bold text-slate-900 dark:text-white">{d.ticker}</span>
        <span className={`text-xs font-bold px-2 py-0.5 rounded uppercase ${ratingStyles[d.rating] || ratingStyles.hold}`}>{d.rating}</span>
      </div>
      <p className="text-sm text-slate-700 dark:text-slate-300 mb-3">{d.one_liner}</p>
      <div className="space-y-2 text-sm">
        <div><span className="font-semibold text-daman-blue-600 dark:text-daman-blue-300">Fundamental:</span> <span className="text-slate-700 dark:text-slate-300">{d.fundamental.summary}</span></div>
        <div><span className="font-semibold text-daman-blue-600 dark:text-daman-blue-300">Technical ({d.technical.trend}):</span> <span className="text-slate-700 dark:text-slate-300">{d.technical.summary}</span></div>
      </div>
      <div className="grid grid-cols-2 gap-2 mt-3 text-xs">
        <div>
          <div className="font-semibold text-emerald-600 dark:text-emerald-400 mb-1">Bull</div>
          <ul className="space-y-1 text-slate-600 dark:text-slate-400">{d.bull_case.slice(0, 3).map((b, i) => <li key={i}>• {b}</li>)}</ul>
        </div>
        <div>
          <div className="font-semibold text-rose-600 dark:text-rose-400 mb-1">Bear</div>
          <ul className="space-y-1 text-slate-600 dark:text-slate-400">{d.bear_case.slice(0, 3).map((b, i) => <li key={i}>• {b}</li>)}</ul>
        </div>
      </div>
    </div>
  );
}

function CompareTab({
  compare, loading, onCompare,
}: {
  compare: { a: CommentaryResult<TickerResearch>; b: CommentaryResult<TickerResearch> } | null;
  loading: boolean;
  onCompare: (a: string, b: string) => void;
}) {
  const [a, setA] = useState('');
  const [b, setB] = useState('');

  return (
    <div className="space-y-4">
      <Reveal className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-6">
        <h2 className="text-lg font-bold text-slate-900 dark:text-white mb-1">Compare two stocks</h2>
        <p className="text-slate-600 dark:text-slate-400 text-sm mb-4">Side-by-side fundamentals + technicals, with a Hermes verdict.</p>
        <div className="flex flex-col sm:flex-row gap-2">
          <input value={a} onChange={(e) => setA(e.target.value.toUpperCase())} placeholder="Ticker A (e.g. AAPL)" className="flex-1 px-4 py-2.5 rounded-lg bg-slate-50 dark:bg-slate-900 border border-slate-300 dark:border-slate-600 text-slate-900 dark:text-white focus:outline-none focus:border-daman-blue-500" />
          <span className="self-center text-slate-400 font-bold">vs</span>
          <input value={b} onChange={(e) => setB(e.target.value.toUpperCase())} placeholder="Ticker B (e.g. MSFT)" className="flex-1 px-4 py-2.5 rounded-lg bg-slate-50 dark:bg-slate-900 border border-slate-300 dark:border-slate-600 text-slate-900 dark:text-white focus:outline-none focus:border-daman-blue-500" />
          <button onClick={() => onCompare(a, b)} disabled={loading || !a.trim() || !b.trim()} className="bg-daman-blue-600 hover:bg-daman-blue-700 disabled:opacity-50 text-white font-semibold px-5 py-2.5 rounded-lg transition-colors">
            Compare
          </button>
        </div>
      </Reveal>

      {loading && <LoadingState />}

      {compare && !loading && (
        <>
          <div className="grid md:grid-cols-2 gap-4">
            <CompareColumn res={compare.a} />
            <CompareColumn res={compare.b} />
          </div>
          <Reveal className="text-center">
            <button
              onClick={() => askHermes(`Compare ${compare.a.data.ticker} vs ${compare.b.data.ticker} — which is the better buy right now and why? Cover valuation, growth, technicals, and risk.`)}
              className="inline-flex items-center gap-2 bg-gradient-to-r from-daman-blue-600 to-daman-blue-800 text-white font-semibold px-6 py-3 rounded-lg shadow-lg transition-all hover:-translate-y-0.5"
            >
              <Sparkles className="h-5 w-5" /> Ask Hermes: which is the better buy?
            </button>
          </Reveal>
        </>
      )}
    </div>
  );
}

function ResearchTab({
  research, loading, onSearch,
}: {
  research: CommentaryResult<TickerResearch> | null;
  loading: boolean;
  onSearch: (t: string) => void;
}) {
  const [sym, setSym] = useState('');
  const examples = ['AAPL', 'NVDA', 'TSLA', 'MSFT', 'SPY'];

  return (
    <div className="space-y-4">
      <Reveal className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-6">
        <h2 className="text-lg font-bold text-slate-900 dark:text-white mb-1">Research any ticker</h2>
        <p className="text-slate-600 dark:text-slate-400 text-sm mb-4">Fundamental + technical deep-dive with a bull/bear case — by Claude.</p>
        <div className="flex gap-2">
          <input
            value={sym}
            onChange={(e) => setSym(e.target.value.toUpperCase())}
            onKeyDown={(e) => e.key === 'Enter' && onSearch(sym)}
            placeholder="Enter a symbol, e.g. AAPL"
            className="flex-1 px-4 py-2.5 rounded-lg bg-slate-50 dark:bg-slate-900 border border-slate-300 dark:border-slate-600 text-slate-900 dark:text-white focus:outline-none focus:border-daman-blue-500"
          />
          <button
            onClick={() => onSearch(sym)}
            disabled={loading || !sym.trim()}
            className="inline-flex items-center gap-2 bg-daman-blue-600 hover:bg-daman-blue-700 disabled:opacity-50 text-white font-semibold px-5 py-2.5 rounded-lg transition-colors"
          >
            <Search className="h-4 w-4" /> Research
          </button>
        </div>
        <div className="flex flex-wrap gap-2 mt-3">
          {examples.map((e) => (
            <button key={e} onClick={() => { setSym(e); onSearch(e); }} className="text-xs font-semibold px-2.5 py-1 rounded-full bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 hover:bg-daman-blue-100 dark:hover:bg-slate-600 transition-colors">
              {e}
            </button>
          ))}
        </div>
      </Reveal>

      {loading && <LoadingState />}

      {research && !loading && (
        <>
          <Reveal className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-6">
            <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
              <div className="flex items-center gap-3">
                <span className="text-2xl font-bold text-slate-900 dark:text-white">{research.data.ticker}</span>
                <span className={`text-xs font-bold px-2.5 py-1 rounded uppercase ${ratingStyles[research.data.rating] || ratingStyles.hold}`}>{research.data.rating}</span>
              </div>
              <div className="flex items-center gap-3 flex-wrap">
                {research.demo && <DemoBadge />}
                <ShareButtons text={researchToText(research.data)} title={`DAMAN — ${research.data.ticker}`} />
              </div>
            </div>
            <p className="text-slate-500 dark:text-slate-400 text-sm mb-1">{research.data.company}</p>
            <p className="text-slate-800 dark:text-slate-200 font-medium mb-4">{research.data.one_liner}</p>
            <AudioBar script={research.data.audio_script} />
          </Reveal>

          <Section title="Fundamental View" icon={<TrendingUp className="h-5 w-5 text-daman-blue-600" />}>
            <p className="text-slate-700 dark:text-slate-300 mb-3">{research.data.fundamental.summary}</p>
            <dl className="grid sm:grid-cols-3 gap-3 text-sm">
              <div className="bg-slate-50 dark:bg-slate-900 rounded-lg p-3 border border-slate-200 dark:border-slate-700"><dt className="text-slate-400 mb-1">Valuation</dt><dd className="text-slate-700 dark:text-slate-300">{research.data.fundamental.valuation}</dd></div>
              <div className="bg-slate-50 dark:bg-slate-900 rounded-lg p-3 border border-slate-200 dark:border-slate-700"><dt className="text-slate-400 mb-1">Growth &amp; Profitability</dt><dd className="text-slate-700 dark:text-slate-300">{research.data.fundamental.growth_profitability}</dd></div>
              <div className="bg-slate-50 dark:bg-slate-900 rounded-lg p-3 border border-slate-200 dark:border-slate-700"><dt className="text-slate-400 mb-1">Balance Sheet</dt><dd className="text-slate-700 dark:text-slate-300">{research.data.fundamental.balance_sheet}</dd></div>
            </dl>
          </Section>

          <Section title="Technical View" icon={<Activity className="h-5 w-5 text-daman-blue-600" />}>
            <div className="flex items-center gap-2 mb-2">
              <span className="text-xs font-bold px-2 py-0.5 rounded bg-daman-blue-100 text-daman-blue-700 dark:bg-daman-blue-900/30 dark:text-daman-blue-300 capitalize">{research.data.technical.trend}</span>
            </div>
            <p className="text-slate-700 dark:text-slate-300 mb-3">{research.data.technical.summary}</p>
            <dl className="grid grid-cols-3 gap-3 text-sm">
              <div><dt className="text-slate-400">Support</dt><dd className="text-slate-700 dark:text-slate-300">{research.data.technical.support}</dd></div>
              <div><dt className="text-slate-400">Resistance</dt><dd className="text-slate-700 dark:text-slate-300">{research.data.technical.resistance}</dd></div>
              <div><dt className="text-slate-400">Momentum</dt><dd className="text-slate-700 dark:text-slate-300">{research.data.technical.momentum}</dd></div>
            </dl>
          </Section>

          <div className="grid md:grid-cols-2 gap-4">
            <Section title="Bull Case" icon={<TrendingUp className="h-5 w-5 text-emerald-600" />}>
              <ul className="space-y-2">{research.data.bull_case.map((b, i) => <li key={i} className="flex gap-2 text-sm text-slate-700 dark:text-slate-300"><span className="text-emerald-500">▲</span> {b}</li>)}</ul>
            </Section>
            <Section title="Bear Case" icon={<TrendingDown className="h-5 w-5 text-rose-600" />}>
              <ul className="space-y-2">{research.data.bear_case.map((b, i) => <li key={i} className="flex gap-2 text-sm text-slate-700 dark:text-slate-300"><span className="text-rose-500">▼</span> {b}</li>)}</ul>
            </Section>
          </div>

          <div className="grid md:grid-cols-2 gap-4">
            <Section title="Catalysts" icon={<Sparkles className="h-5 w-5 text-daman-blue-600" />}>
              <ul className="space-y-2">{research.data.catalysts.map((c, i) => <li key={i} className="flex gap-2 text-sm text-slate-700 dark:text-slate-300"><span className="text-daman-blue-500">•</span> {c}</li>)}</ul>
            </Section>
            <Section title="Risks" icon={<AlertTriangle className="h-5 w-5 text-amber-600" />}>
              <ul className="space-y-2">{research.data.risks.map((r, i) => <li key={i} className="flex gap-2 text-sm text-slate-700 dark:text-slate-300"><span className="text-amber-500">•</span> {r}</li>)}</ul>
            </Section>
          </div>

          <p className="text-xs text-slate-500 dark:text-slate-400 italic px-2">{research.data.disclaimer}</p>
        </>
      )}
    </div>
  );
}
