import { useEffect, useState } from 'react';
import { Download, X } from 'lucide-react';

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
}

/**
 * "Add to Home Screen" prompt. Captures the browser's beforeinstallprompt
 * event and surfaces a tasteful, dismissible banner. No-ops where unsupported
 * (e.g. iOS Safari) or when already installed.
 */
export default function InstallPrompt() {
  const [deferred, setDeferred] = useState<BeforeInstallPromptEvent | null>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (sessionStorage.getItem('pwa_install_dismissed')) return;
    // Already installed?
    if (window.matchMedia && window.matchMedia('(display-mode: standalone)').matches) return;

    const handler = (e: Event) => {
      e.preventDefault();
      setDeferred(e as BeforeInstallPromptEvent);
      setVisible(true);
    };
    window.addEventListener('beforeinstallprompt', handler);
    window.addEventListener('appinstalled', () => setVisible(false));
    return () => window.removeEventListener('beforeinstallprompt', handler);
  }, []);

  const install = async () => {
    if (!deferred) return;
    await deferred.prompt();
    await deferred.userChoice.catch(() => undefined);
    setVisible(false);
    setDeferred(null);
  };

  const dismiss = () => {
    setVisible(false);
    try { sessionStorage.setItem('pwa_install_dismissed', '1'); } catch { /* ignore */ }
  };

  if (!visible) return null;

  return (
    <div className="fixed z-[55] top-20 left-1/2 -translate-x-1/2 w-[calc(100%-2rem)] max-w-md animate-slideUp">
      <div className="flex items-center gap-3 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 shadow-2xl rounded-xl px-4 py-3">
        <div className="bg-gradient-to-br from-daman-blue-600 to-daman-blue-800 p-2 rounded-lg shrink-0">
          <Download className="h-5 w-5 text-white" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="font-semibold text-slate-900 dark:text-white text-sm">Install DAMAN</p>
          <p className="text-xs text-slate-500 dark:text-slate-400">Add to your home screen for a faster, app-like experience.</p>
        </div>
        <button onClick={install} className="shrink-0 bg-daman-blue-600 hover:bg-daman-blue-700 text-white text-sm font-semibold px-4 py-2 rounded-lg transition-colors">
          Install
        </button>
        <button onClick={dismiss} aria-label="Dismiss" className="shrink-0 p-1 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200">
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
