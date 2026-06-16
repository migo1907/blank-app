import { createClient } from '@supabase/supabase-js';

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

// Whether real Supabase credentials are configured. When false, the app still
// renders (UI + demo content); live data calls simply fail and are handled by
// each feature's own error handling — far better than a white-screen crash.
export const isSupabaseConfigured = Boolean(supabaseUrl && supabaseAnonKey);

if (!isSupabaseConfigured) {
  console.warn(
    '[DAMAN] Supabase environment variables are not set — running in limited/demo mode. ' +
    'Set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY to enable live data.'
  );
}

export const supabase = createClient(
  supabaseUrl || 'https://placeholder.supabase.co',
  supabaseAnonKey || 'public-anon-placeholder-key'
);
