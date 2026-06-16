import { useMemo } from 'react';
import Reveal from './Reveal';
import { askHermes } from '../lib/hermesBus';

// Illustrative sector snapshot. Swap for a live sector feed when available.
const SECTORS: { name: string; change: number }[] = [
  { name: 'Technology', change: 1.42 },
  { name: 'Financials', change: 0.63 },
  { name: 'Health Care', change: -0.21 },
  { name: 'Energy', change: -0.88 },
  { name: 'Consumer Disc.', change: 0.94 },
  { name: 'Industrials', change: 0.38 },
  { name: 'Communications', change: 1.05 },
  { name: 'Utilities', change: -0.42 },
  { name: 'Materials', change: 0.12 },
  { name: 'Real Estate', change: -0.55 },
  { name: 'Consumer Staples', change: 0.07 },
  { name: 'Semiconductors', change: 2.13 },
];

function tileStyle(change: number): React.CSSProperties {
  const mag = Math.min(Math.abs(change) / 2.2, 1); // normalize ~0..1
  const alpha = 0.18 + mag * 0.62;
  return {
    backgroundColor: change >= 0
      ? `rgba(16, 185, 129, ${alpha})`   // emerald
      : `rgba(244, 63, 94, ${alpha})`,   // rose
  };
}

export default function MarketHeatmap() {
  const sectors = useMemo(() => [...SECTORS].sort((a, b) => b.change - a.change), []);

  return (
    <section className="py-16 bg-slate-50 dark:bg-slate-900">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <Reveal className="text-center mb-8">
          <h2 className="text-3xl font-bold text-slate-900 dark:text-white mb-2">Sector Heatmap</h2>
          <p className="text-slate-600 dark:text-slate-400">Today's leaders and laggards at a glance — tap a sector to ask Hermes.</p>
        </Reveal>

        <Reveal>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
            {sectors.map((s) => {
              const up = s.change >= 0;
              return (
                <button
                  key={s.name}
                  onClick={() => askHermes(`What's driving the ${s.name} sector today, and how should I position around it?`)}
                  style={tileStyle(s.change)}
                  className="rounded-xl p-4 text-left transition-transform hover:-translate-y-1 hover:shadow-lg border border-black/5 dark:border-white/5"
                >
                  <div className="font-semibold text-slate-900 dark:text-white text-sm">{s.name}</div>
                  <div className={`text-lg font-bold ${up ? 'text-emerald-800 dark:text-emerald-200' : 'text-rose-800 dark:text-rose-200'}`}>
                    {up ? '+' : ''}{s.change.toFixed(2)}%
                  </div>
                </button>
              );
            })}
          </div>
        </Reveal>

        <p className="text-center text-xs text-slate-400 mt-4">Illustrative sector data — connect a live feed for real-time moves.</p>
      </div>
    </section>
  );
}
