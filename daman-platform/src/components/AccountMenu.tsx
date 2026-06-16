import { useState } from 'react';
import { UserCircle, LogOut, UploadCloud, DownloadCloud, ChevronDown } from 'lucide-react';
import { useAuth } from '../hooks/useAuth';
import { supabase } from '../lib/supabase';
import { backupToCloud, restoreFromCloud } from '../services/cloudSyncService';
import AuthModal from './AuthModal';

/**
 * Account control for the nav: sign in / up, then cloud backup + restore of
 * portfolio/watchlist/settings, and sign out. Works once Supabase is configured;
 * in demo mode the modal explains how to enable it.
 */
export default function AccountMenu({ mobile = false }: { mobile?: boolean }) {
  const { user } = useAuth();
  const [showModal, setShowModal] = useState(false);
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState('');
  const [busy, setBusy] = useState(false);

  const backup = async () => {
    if (!user) return;
    setBusy(true);
    setStatus((await backupToCloud(user.id)).message);
    setBusy(false);
  };
  const restore = async () => {
    if (!user) return;
    setBusy(true);
    const r = await restoreFromCloud(user.id);
    setStatus(r.message);
    setBusy(false);
    if (r.ok) setTimeout(() => window.location.reload(), 900);
  };
  const signOut = async () => {
    await supabase.auth.signOut();
    setOpen(false);
    setStatus('');
  };

  // Signed out → a Sign In button (modal handles demo-mode messaging).
  if (!user) {
    return (
      <>
        <button
          onClick={() => setShowModal(true)}
          className={
            mobile
              ? 'flex items-center gap-2 w-full px-4 py-2 rounded-lg text-sm font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700'
              : 'flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors'
          }
        >
          <UserCircle className="h-5 w-5" /> Sign In
        </button>
        {showModal && <AuthModal onClose={() => setShowModal(false)} onAuthSuccess={() => setShowModal(false)} />}
      </>
    );
  }

  const label = user.email?.split('@')[0] ?? 'Account';

  return (
    <div className={mobile ? '' : 'relative'}>
      <button
        onClick={() => setOpen((o) => !o)}
        className={
          mobile
            ? 'flex items-center justify-between gap-2 w-full px-4 py-2 rounded-lg text-sm font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700'
            : 'flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors'
        }
      >
        <span className="flex items-center gap-1.5"><UserCircle className="h-5 w-5" /> {label}</span>
        <ChevronDown className="h-4 w-4" />
      </button>

      {open && (
        <>
          {!mobile && <button className="fixed inset-0 z-40 cursor-default" aria-hidden onClick={() => setOpen(false)} />}
          <div className={mobile ? 'mt-1 space-y-1' : 'absolute right-0 mt-2 w-60 z-50 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl shadow-xl p-2'}>
            <div className="px-3 py-2 text-xs text-slate-500 dark:text-slate-400 truncate">{user.email}</div>
            <button onClick={backup} disabled={busy} className="flex items-center gap-2 w-full px-3 py-2 rounded-lg text-sm text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors disabled:opacity-50">
              <UploadCloud className="h-4 w-4 text-daman-blue-600 dark:text-daman-blue-300" /> Back up to cloud
            </button>
            <button onClick={restore} disabled={busy} className="flex items-center gap-2 w-full px-3 py-2 rounded-lg text-sm text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors disabled:opacity-50">
              <DownloadCloud className="h-4 w-4 text-daman-blue-600 dark:text-daman-blue-300" /> Restore from cloud
            </button>
            <button onClick={signOut} className="flex items-center gap-2 w-full px-3 py-2 rounded-lg text-sm text-rose-600 dark:text-rose-400 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors">
              <LogOut className="h-4 w-4" /> Sign out
            </button>
            {status && <p className="px-3 py-1 text-xs text-slate-500 dark:text-slate-400">{status}</p>}
          </div>
        </>
      )}
    </div>
  );
}
