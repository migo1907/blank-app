// Scheduled daily market-commentary email.
//
// Reads active subscribers from `commentary_subscribers`, generates today's
// AI wrap-up (via the ai-market-commentary function), and emails it via Resend.
// Protected by a shared secret so it can't be triggered by anyone.
//
// Required secrets (Supabase function env):
//   - DAILY_EMAIL_SECRET   (you choose; passed as ?secret=...)
//   - RESEND_API_KEY        (https://resend.com)
//   - RESEND_FROM           (e.g. "Hermes <hermes@yourdomain.com>")
//   - SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY  (auto-provided in functions)
//
// Trigger daily via cron (GitHub Actions workflow included) or Supabase cron.

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Client-Info, Apikey",
};

interface Subscriber { email: string; frequency: string; active: boolean }

function isWeekday(d: Date) {
  const day = d.getUTCDay();
  return day >= 1 && day <= 5;
}

function renderEmail(wrap: Record<string, unknown>): string {
  const w = wrap as {
    headline?: string; executive_summary?: string; market_tone?: string;
    swing_trade_ideas?: { ticker: string; direction: string; thesis: string }[];
    key_risks?: string[]; disclaimer?: string;
  };
  const swings = (w.swing_trade_ideas || [])
    .map((s) => `<li><b>${s.ticker}</b> (${s.direction}) — ${s.thesis}</li>`)
    .join("");
  const risks = (w.key_risks || []).map((r) => `<li>${r}</li>`).join("");
  return `
  <div style="font-family:system-ui,sans-serif;max-width:640px;margin:0 auto;color:#0f172a">
    <h1 style="color:#14539C">DAMAN — Daily Market Wrap-Up</h1>
    <p style="font-weight:600">${w.headline ?? ""} <span style="color:#64748b">(${w.market_tone ?? ""})</span></p>
    <p>${w.executive_summary ?? ""}</p>
    ${swings ? `<h3>Swing-trade ideas</h3><ul>${swings}</ul>` : ""}
    ${risks ? `<h3>Key risks</h3><ul>${risks}</ul>` : ""}
    <p style="font-size:12px;color:#94a3b8;margin-top:24px">${w.disclaimer ?? "AI-generated, educational only — not financial advice."}</p>
  </div>`;
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response(null, { status: 200, headers: corsHeaders });

  const url = new URL(req.url);
  const secret = url.searchParams.get("secret");
  if (!secret || secret !== Deno.env.get("DAILY_EMAIL_SECRET")) {
    return new Response(JSON.stringify({ error: "unauthorized" }), {
      status: 401, headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }

  const resendKey = Deno.env.get("RESEND_API_KEY");
  const from = Deno.env.get("RESEND_FROM") || "Hermes <onboarding@resend.dev>";
  const supabaseUrl = Deno.env.get("SUPABASE_URL");
  const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");

  if (!resendKey || !supabaseUrl || !serviceKey) {
    return new Response(JSON.stringify({ error: "missing_config", message: "Set RESEND_API_KEY and run inside Supabase functions." }), {
      status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }

  try {
    // 1. Subscribers
    const subRes = await fetch(`${supabaseUrl}/rest/v1/commentary_subscribers?active=eq.true&select=email,frequency,active`, {
      headers: { apikey: serviceKey, Authorization: `Bearer ${serviceKey}` },
    });
    const subs: Subscriber[] = subRes.ok ? await subRes.json() : [];
    const today = new Date();
    const recipients = subs.filter((s) => s.frequency === "daily" || (s.frequency === "weekdays" && isWeekday(today)));

    if (recipients.length === 0) {
      return new Response(JSON.stringify({ success: true, sent: 0, message: "No recipients for today." }), {
        status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    // 2. Generate today's wrap-up once
    const genRes = await fetch(`${supabaseUrl}/functions/v1/ai-market-commentary`, {
      method: "POST",
      headers: { Authorization: `Bearer ${serviceKey}`, "Content-Type": "application/json" },
      body: JSON.stringify({ mode: "wrapup" }),
    });
    const gen = await genRes.json();
    const html = renderEmail(gen?.data || {});
    const subject = `DAMAN Daily Wrap-Up — ${today.toUTCString().slice(0, 16)}`;

    // 3. Send via Resend
    let sent = 0;
    for (const r of recipients) {
      const send = await fetch("https://api.resend.com/emails", {
        method: "POST",
        headers: { Authorization: `Bearer ${resendKey}`, "Content-Type": "application/json" },
        body: JSON.stringify({ from, to: r.email, subject, html }),
      });
      if (send.ok) sent++;
    }

    return new Response(JSON.stringify({ success: true, sent, total: recipients.length }), {
      status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  } catch (error) {
    return new Response(JSON.stringify({ success: false, error: String(error) }), {
      status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }
});
