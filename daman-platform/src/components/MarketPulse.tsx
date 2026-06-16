import { useEffect, useState } from 'react';
import { TrendingUp, TrendingDown, Activity, ArrowRight } from 'lucide-react';
import Reveal from './Reveal';
import Skeleton from './Skeleton';
import AnimatedCounter from './AnimatedCounter';

interface MarketPulseProps {
  /** Optional: navigate to another page (e.g. the full Market Overview). */
  onNavigate?: (page: string) => void;
}

interface IndexQuote {
  symbol: string;
  name: string;
  value: number;
  changePct: number;
}

// Representative snapshot for the homepage overview. The live, real-time
// figures live in the Market Overview page; this is an at-a-glance teaser.
const SNAPSHOT: IndexQuote[] = [
  { symbol: 'SPX', name: 'S&P 500', value: 5431.6, changePct: 0.62 },
  { symbol: 'NDX', name: 'Nasdaq 100', value: 19764.2, changePct: 1.14 },
  { symbol: 'DJI', name: 'Dow Jones', value: 38807.1, changePct: -0.21 },
  { symbol: 'RUT', name: 'Russell 2000', value: 2026.4, changePct: 0.38 },
];

export default function MarketPulse({ onNavigate }: MarketPulseProps) {
  const [loading, setLoading] = useState(true);

  // Brief simulated load so the skeleton state is visible on first paint.
  useEffect(() => {
    const t = setTimeout(() => setLoading(false), 900);
    return () => clearTimeout(t);
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
        </Reveal>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
          {loading
            ? SNAPSHOT.map((q) => (
                <div
                  key={q.symbol}
                  className="rounded-xl p-6 border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800"
                >
                  <Skeleton className="h-4 w-24 mb-4" />
                  <Skeleton className="h-8 w-32 mb-3" />
                  <Skeleton className="h-4 w-16" />
                </div>
              ))
            : SNAPSHOT.map((q, i) => {
                const up = q.changePct >= 0;
                return (
                  <Reveal key={q.symbol} delay={i * 90}>
                    <div className="rounded-xl p-6 border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 hover:shadow-xl hover:-translate-y-1 hover:border-daman-blue-300 transition-all duration-300">
                      <div className="flex items-center justify-between mb-3">
                        <span className="text-sm font-medium text-slate-500 dark:text-slate-400">
                          {q.name}
                        </span>
                        <span className="text-xs font-semibold text-slate-400 dark:text-slate-500">
                          {q.symbol}
                        </span>
                      </div>
                      <div className="text-3xl font-bold text-slate-900 dark:text-white mb-2 tabular-nums">
                        <AnimatedCounter value={q.value} decimals={1} />
                      </div>
                      <div
                        className={`inline-flex items-center gap-1 text-sm font-semibold ${
                          up ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'
                        }`}
                      >
                        {up ? <TrendingUp className="h-4 w-4" /> : <TrendingDown className="h-4 w-4" />}
                        {up ? '+' : ''}
                        {q.changePct.toFixed(2)}%
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
