import { useState } from 'react';
import { Copy, Check, Share2 } from 'lucide-react';

/**
 * Copy-to-clipboard + native Share for AI output.
 * Share uses the Web Share API when available (mobile); otherwise just copy.
 */
export default function ShareButtons({ text, title = 'DAMAN — Hermes AI' }: { text: string; title?: string }) {
  const [copied, setCopied] = useState(false);
  const canShare = typeof navigator !== 'undefined' && !!navigator.share;

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      /* clipboard blocked — no-op */
    }
  };

  const share = async () => {
    try {
      await navigator.share({ title, text });
    } catch {
      /* user cancelled or unsupported */
    }
  };

  return (
    <div className="flex items-center gap-2">
      <button
        onClick={copy}
        className="inline-flex items-center gap-1.5 text-sm font-semibold px-3 py-1.5 rounded-lg bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200 hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors"
      >
        {copied ? <Check className="h-4 w-4 text-emerald-500" /> : <Copy className="h-4 w-4" />}
        {copied ? 'Copied' : 'Copy'}
      </button>
      {canShare && (
        <button
          onClick={share}
          className="inline-flex items-center gap-1.5 text-sm font-semibold px-3 py-1.5 rounded-lg bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200 hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors"
        >
          <Share2 className="h-4 w-4" /> Share
        </button>
      )}
    </div>
  );
}
