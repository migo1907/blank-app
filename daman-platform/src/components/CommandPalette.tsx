import { useEffect, useMemo, useRef, useState } from 'react';
import { Search, Home, TrendingUp, Sparkles, PieChart, Eye, Settings as SettingsIcon, CornerDownLeft } from 'lucide-react';
import { askHermes } from '../lib/hermesBus';

interface Props {
  onNavigate: (page: string) => void;
}

const PAGES = [
  { id: 'home', label: 'Home', icon: Home },
  { id: 'market-overview', label: 'Market Overview', icon: TrendingUp },
  { id: 'ai-strategist', label: 'AI Strategist (Hermes)', icon: Sparkles },
  { id: 'portfolio', label: 'Portfolio', icon: PieChart },
  { id: 'watchlist', label: 'Watchlist', icon: Eye },
  { id: 'settings', label: 'Settings', icon: SettingsIcon },
];

/**
 * Global command palette — open with Ctrl/Cmd+K. Jump to any page or ask Hermes
 * from anywhere.
 */
export default function CommandPalette({ onNavigate }: Props) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setOpen((o) => !o);
      } else if (e.key === 'Escape') {
        setOpen(false);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  useEffect(() => {
    if (open) {
      setQuery('');
      setTimeout(() => inputRef.current?.focus(), 30);
    }
  }, [open]);

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? PAGES.filter((p) => p.label.toLowerCase().includes(q)) : PAGES;
  }, [query]);

  if (!open) return null;

  const go = (id: string) => { onNavigate(id); setOpen(false); };
  const ask = () => {
    if (!query.trim()) return;
    askHermes(query.trim());
    setOpen(false);
  };

  return (
    <div className="fixed inset-0 z-[70] flex items-start justify-center pt-[15vh] px-4 bg-black/40 backdrop-blur-sm" onClick={() => setOpen(false)}>
      <div className="w-full max-w-lg bg-white dark:bg-slate-800 rounded-xl shadow-2xl border border-slate-200 dark:border-slate-700 overflow-hidden animate-slideUp" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-3 px-4 py-3 border-b border-slate-200 dark:border-slate-700">
          <Search className="h-5 w-5 text-slate-400" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') { if (matches.length) go(matches[0].id); else ask(); } }}
            placeholder="Jump to a page, or type a question for Hermes…"
            className="flex-1 bg-transparent text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none"
          />
          <kbd className="hidden sm:block text-[11px] text-slate-400 border border-slate-300 dark:border-slate-600 rounded px-1.5 py-0.5">Esc</kbd>
        </div>

        <div className="max-h-80 overflow-y-auto py-2">
          {matches.map((p) => {
            const Icon = p.icon;
            return (
              <button
                key={p.id}
                onClick={() => go(p.id)}
                className="w-full flex items-center gap-3 px-4 py-2.5 text-left text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
              >
                <Icon className="h-4 w-4 text-daman-blue-600 dark:text-daman-blue-300" />
                <span className="flex-1">{p.label}</span>
              </button>
            );
          })}

          {query.trim() && (
            <button
              onClick={ask}
              className="w-full flex items-center gap-3 px-4 py-2.5 text-left text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors border-t border-slate-100 dark:border-slate-700 mt-1"
            >
              <Sparkles className="h-4 w-4 text-daman-blue-600 dark:text-daman-blue-300" />
              <span className="flex-1">Ask Hermes: <span className="font-semibold">"{query.trim()}"</span></span>
              <CornerDownLeft className="h-4 w-4 text-slate-400" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
