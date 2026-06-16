import { useEffect, useState } from 'react';
import { TrendingUp, TrendingDown, Activity, ArrowRight } from 'lucide-react';
import Reveal from './Reveal';
import Skeleton from './Skeleton';
import AnimatedCounter from './AnimatedCounter';
import { marketDataService, MarketQuote } from '../services/marketDataService';

interface MarketPulseProps {
  /** Optional: navigate to another page (e.g. the full Market Overview). */
  onNavigate?: (page: string) => void;
}

// Index names the shared marketDataService knows how to resolve + short labels.
const INDICES: { name: string; label: string }[] = [
  { name: 'S&P 500', label: 'SPX' },
  { name: 'Nasdaq', label: 'IXIC' },
  { name: 'Dow Jones', label: 'DJI' },
  { name: 'VIX', label: 'VIX' },
];
const INDEX_NAMES = INDICES.map((i) => i.name);
const REFRESH_MS = 60000;

export default function MarketPulse({ onNavigate }: MarketPulseProps) {
  const [quotes, setQuotes] = useState<MarketQuote[]>([]);
  const [loading, setLoading] = useState(true);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);

  useEffect(() => {
    let active = true;

    const load = async () => {
      try {
        // Service handles caching and falls back to last-known values on error.
        const map = await marketDataService.fetchMarketData(INDEX_NAMES);
        if (!active) return;
        const list = INDEX_NAMES.map((n) => map.get(n)).filter(Boolean) as MarketQuote[];
        if (list.length) {
          setQuotes(list);
          setUpdatedAt(new Date());
        }
      } catch {
        /* keep previous quotes; service already degrades gracefully */
      } finally {
        if (active) setLoading(false);
      }
    };

    load();
    // Refresh while the tab is visible only — saves requests/battery.
    const interval = setInterval(() => {
      if (!document.hidden) load();
    }, REFRESH_MS);

    return () => {
      active = false;
      clearInterval(interval);
    };
  }, []);

  return (
    <section className="py-20 bg-white dark:bg-slate-900">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <Reveal className="text-center mb-12">
          <div className="inline-flex items-center gap-2 text-daman-blue-600 dark:text-daman-blue-300 font-semibold mb-3">
            <Activity className="h-5 w-5" />
            <span>Markets at a Glance</span>
          </div>
          <h2 className="text-4xl font-bold text-slate-900 dark:text-white mb-4">
            Stay on Top of Global Indices
          </h2>
          <p className="text-xl text-slate-600 dark:text-slate-300 max-w-3xl mx-auto">
            A live snapshot of the indices that move the market. Dive into the
            Market Overview for full real-time data and analytics.
          </p>
          {updatedAt && (
            <div className="inline-flex items-center gap-2 mt-4 text-xs font-medium text-slate-500 dark:text-slate-400">
              <span className="h-2 w-2 rounded-full bg-green-500 animate-pulse" />
              Updated {updatedAt.toLocaleTimeString()}
            </div>
          )}
        </Reveal>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
          {loading
            ? INDICES.map((idx) => (
                <div
                  key={idx.label}
                  className="rounded-xl p-6 border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800"
                >
                  <Skeleton className="h-4 w-24 mb-4" />
                  <Skeleton className="h-8 w-32 mb-3" />
                  <Skeleton className="h-4 w-16" />
                </div>
              ))
            : quotes.map((q, i) => {
                const up = q.changePercent >= 0;
                const label = INDICES.find((idx) => idx.name === q.name)?.label ?? q.symbol;
                return (
                  <Reveal key={q.name} delay={i * 90}>
                    <div className="rounded-xl p-6 border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 hover:shadow-xl hover:-translate-y-1 hover:border-daman-blue-300 transition-all duration-300">
                      <div className="flex items-center justify-between mb-3">
                        <span className="text-sm font-medium text-slate-500 dark:text-slate-400">
                          {q.name}
                        </span>
                        <span className="text-xs font-semibold text-slate-400 dark:text-slate-500">
                          {label}
                        </span>
                      </div>
                      <div className="text-3xl font-bold text-slate-900 dark:text-white mb-2 tabular-nums">
                        <AnimatedCounter value={q.price} decimals={2} />
                      </div>
                      <div
                        className={`inline-flex items-center gap-1 text-sm font-semibold ${
                          up ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'
                        }`}
                      >
                        {up ? <TrendingUp className="h-4 w-4" /> : <TrendingDown className="h-4 w-4" />}
                        {up ? '+' : ''}
                        {q.changePercent.toFixed(2)}%
                      </div>
                    </div>
                  </Reveal>
                );
              })}
        </div>

        {onNavigate && (
          <Reveal className="text-center mt-12">
            <button
              onClick={() => onNavigate('market-overview')}
              className="inline-flex items-center gap-2 bg-daman-blue-600 hover:bg-daman-blue-700 text-white font-semibold px-8 py-3 rounded-lg shadow-lg transition-all hover:-translate-y-0.5 focus:outline-none focus:ring-2 focus:ring-daman-blue-500 focus:ring-offset-2"
            >
              View Full Market Overview
              <ArrowRight className="h-4 w-4" />
            </button>
          </Reveal>
        )}
      </div>
    </section>
  );
}
