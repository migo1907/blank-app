import { supabase } from '../lib/supabase';

// localStorage keys that make up a user's portable state.
const SYNC_KEYS = ['portfolio', 'watchlist_v2', 'appSettings'];

export async function backupToCloud(userId: string): Promise<{ ok: boolean; message: string }> {
  const data: Record<string, string> = {};
  for (const k of SYNC_KEYS) {
    const v = localStorage.getItem(k);
    if (v != null) data[k] = v;
  }
  const { error } = await supabase
    .from('user_data')
    .upsert({ user_id: userId, data, updated_at: new Date().toISOString() });
  return error
    ? { ok: false, message: 'Backup failed. Is the user_data table set up?' }
    : { ok: true, message: 'Backed up to your account.' };
}

export async function restoreFromCloud(userId: string): Promise<{ ok: boolean; message: string }> {
  const { data, error } = await supabase
    .from('user_data')
    .select('data')
    .eq('user_id', userId)
    .maybeSingle();

  if (error) return { ok: false, message: 'Restore failed.' };
  if (!data?.data || Object.keys(data.data).length === 0) {
    return { ok: false, message: 'No cloud backup found yet.' };
  }
  for (const [k, v] of Object.entries(data.data as Record<string, string>)) {
    localStorage.setItem(k, v);
  }
  return { ok: true, message: 'Restored from your account. Reloading…' };
}
