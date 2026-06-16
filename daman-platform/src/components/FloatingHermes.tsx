import { useState } from 'react';
import { Sparkles, X } from 'lucide-react';
import HermesChat from './HermesChat';

/**
 * Global floating "Ask Hermes" launcher — available on every page.
 * Opens a chat panel (bottom-right on desktop, near-fullscreen on mobile)
 * that reuses the persistent, streaming HermesChat.
 */
export default function FloatingHermes() {
  const [open, setOpen] = useState(false);

  return (
    <>
      {/* Launcher button */}
      <button
        onClick={() => setOpen((o) => !o)}
        aria-label={open ? 'Close Ask Hermes' : 'Open Ask Hermes'}
        className="fixed z-[60] bottom-20 md:bottom-6 right-4 md:right-6 h-14 w-14 rounded-full bg-gradient-to-br from-daman-blue-600 to-daman-blue-800 text-white shadow-xl flex items-center justify-center transition-all duration-300 hover:-translate-y-1 focus:outline-none focus:ring-2 focus:ring-daman-blue-500 focus:ring-offset-2"
      >
        {open ? <X className="h-6 w-6" /> : <Sparkles className="h-6 w-6" />}
        {!open && (
          <span className="absolute -top-1 -right-1 h-3 w-3 rounded-full bg-emerald-400 ring-2 ring-white dark:ring-slate-900" />
        )}
      </button>

      {/* Chat panel */}
      {open && (
        <div className="fixed z-[60] inset-x-2 bottom-36 top-16 md:inset-auto md:bottom-24 md:right-6 md:w-[420px] md:h-[600px] md:max-h-[80vh] rounded-2xl shadow-2xl border border-slate-200 dark:border-slate-700 overflow-hidden flex flex-col bg-white dark:bg-slate-800 animate-slideUp">
          <div className="flex items-center justify-between px-4 py-3 bg-gradient-to-r from-daman-blue-600 to-daman-blue-800 text-white">
            <div className="flex items-center gap-2 font-semibold">
              <Sparkles className="h-5 w-5" /> Ask Hermes
            </div>
            <button onClick={() => setOpen(false)} aria-label="Close" className="p-1 rounded hover:bg-white/15 transition-colors">
              <X className="h-5 w-5" />
            </button>
          </div>
          <div className="flex-1 min-h-0">
            <HermesChat compact />
          </div>
        </div>
      )}
    </>
  );
}
