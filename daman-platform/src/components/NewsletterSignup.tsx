import { useState } from 'react';
import { Mail, CheckCircle2 } from 'lucide-react';
import { subscribe, getLocalSubscription, unsubscribe, isValidEmail } from '../services/commentarySubscriptionService';

/**
 * Reusable daily market-commentary / newsletter signup.
 * Used on the AI Strategist wrap-up and the News feed.
 */
export default function NewsletterSignup({ title = 'Daily Market Commentary' }: { title?: string }) {
  const [email, setEmail] = useState('');
  const [frequency, setFrequency] = useState<'daily' | 'weekdays'>('weekdays');
  const [status, setStatus] = useState<{ ok: boolean; message: string } | null>(null);
  const [existing, setExisting] = useState(() => getLocalSubscription());
  const [busy, setBusy] = useState(false);

  const handleSubscribe = async () => {
    if (!isValidEmail(email)) {
      setStatus({ ok: false, message: 'Please enter a valid email address.' });
      return;
    }
    setBusy(true);
    const res = await subscribe(email, frequency);
    setBusy(false);
    setStatus(res);
    if (res.ok) setExisting(getLocalSubscription());
  };

  const handleUnsubscribe = () => {
    setStatus(unsubscribe());
    setExisting(null);
    setEmail('');
  };

  return (
    <div className="bg-gradient-to-br from-daman-blue-600 to-daman-blue-800 rounded-xl p-6 text-white shadow-lg">
      <div className="flex items-center gap-2 mb-2">
        <Mail className="h-5 w-5" />
        <h3 className="text-lg font-bold">{title}</h3>
      </div>

      {existing ? (
        <div>
          <p className="flex items-center gap-2 text-blue-100 mb-3">
            <CheckCircle2 className="h-5 w-5" /> Subscribed as <strong>{existing.email}</strong> ({existing.frequency})
          </p>
          <button onClick={handleUnsubscribe} className="text-sm font-semibold bg-white/15 hover:bg-white/25 px-4 py-2 rounded-lg transition-colors">
            Unsubscribe
          </button>
        </div>
      ) : (
        <>
          <p className="text-blue-100 text-sm mb-4">
            Get Hermes's AI market wrap-up and breaking-news digest delivered to your inbox. Cancel anytime.
          </p>
          <div className="flex flex-col sm:flex-row gap-3">
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSubscribe()}
              placeholder="you@example.com"
              className="flex-1 px-4 py-2.5 rounded-lg text-slate-900 focus:outline-none focus:ring-2 focus:ring-white/50"
            />
            <select
              value={frequency}
              onChange={(e) => setFrequency(e.target.value as 'daily' | 'weekdays')}
              className="px-4 py-2.5 rounded-lg text-slate-900 focus:outline-none focus:ring-2 focus:ring-white/50"
            >
              <option value="weekdays">Weekdays</option>
              <option value="daily">Daily</option>
            </select>
            <button
              onClick={handleSubscribe}
              disabled={busy}
              className="bg-white text-daman-blue-700 font-semibold px-6 py-2.5 rounded-lg hover:bg-blue-50 transition-colors disabled:opacity-60"
            >
              {busy ? 'Subscribing…' : 'Subscribe'}
            </button>
          </div>
        </>
      )}

      {status && <p className={`text-sm mt-3 ${status.ok ? 'text-blue-100' : 'text-rose-200'}`}>{status.message}</p>}
    </div>
  );
}
