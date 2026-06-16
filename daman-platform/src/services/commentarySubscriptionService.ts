// Daily market-commentary subscription.
// Persists to the `commentary_subscribers` Supabase table when available, and
// always mirrors locally so the UI reflects the user's choice immediately.

const LS_KEY = 'daman_commentary_subscription';

export interface Subscription {
  email: string;
  frequency: 'daily' | 'weekdays';
  subscribedAt: string;
}

export function getLocalSubscription(): Subscription | null {
  try {
    const raw = localStorage.getItem(LS_KEY);
    return raw ? (JSON.parse(raw) as Subscription) : null;
  } catch {
    return null;
  }
}

export function clearLocalSubscription(): void {
  localStorage.removeItem(LS_KEY);
}

export function isValidEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim());
}

export async function subscribe(
  email: string,
  frequency: 'daily' | 'weekdays' = 'weekdays'
): Promise<{ ok: boolean; message: string }> {
  const clean = email.trim().toLowerCase();
  if (!isValidEmail(clean)) return { ok: false, message: 'Please enter a valid email address.' };

  const sub: Subscription = { email: clean, frequency, subscribedAt: new Date().toISOString() };
  localStorage.setItem(LS_KEY, JSON.stringify(sub));

  // Best-effort persistence to Supabase; the local record is the source of truth for the UI.
  const url = import.meta.env.VITE_SUPABASE_URL;
  const key = import.meta.env.VITE_SUPABASE_ANON_KEY;
  if (url && key) {
    try {
      const res = await fetch(`${url}/rest/v1/commentary_subscribers`, {
        method: 'POST',
        headers: {
          apikey: key,
          Authorization: `Bearer ${key}`,
          'Content-Type': 'application/json',
          Prefer: 'resolution=merge-duplicates',
        },
        body: JSON.stringify({ email: clean, frequency }),
      });
      if (res.ok || res.status === 409) {
        return { ok: true, message: "You're subscribed! Daily commentary will arrive by email." };
      }
      // Table may not exist yet — still treat the local subscription as successful.
      return { ok: true, message: "Subscription saved on this device. (Email delivery needs backend setup.)" };
    } catch {
      return { ok: true, message: 'Subscription saved on this device.' };
    }
  }
  return { ok: true, message: 'Subscription saved on this device.' };
}

export function unsubscribe(): { ok: boolean; message: string } {
  clearLocalSubscription();
  return { ok: true, message: 'You have unsubscribed from daily commentary.' };
}
