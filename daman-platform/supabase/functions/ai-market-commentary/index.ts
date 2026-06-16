// AI Market Commentary — powered by Claude (Anthropic).
//
// Server-side only: the ANTHROPIC_API_KEY lives in Supabase function secrets and
// never reaches the browser. Two modes:
//   - "wrapup"    → a daily market wrap-up loaded with fundamentals + technicals,
//                   including swing-trade and day-trade ideas.
//   - "portfolio" → "Hermes" portfolio analysis (fundamental + technical) over the
//                   user's holdings.
//
// Returns structured JSON (via Claude structured outputs) so the UI can render
// rich, sectioned commentary. Degrades gracefully if the key is missing.

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Client-Info, Apikey",
};

const ANTHROPIC_URL = "https://api.anthropic.com/v1/messages";
const MODEL = "claude-opus-4-8";

const CONVICTION = ["low", "medium", "high"] as const;

// ---- Structured-output schemas ------------------------------------------------

const wrapupSchema = {
  type: "object",
  additionalProperties: false,
  properties: {
    headline: { type: "string", description: "Punchy one-line headline for the session." },
    market_tone: { type: "string", enum: ["bullish", "bearish", "neutral", "mixed"] },
    executive_summary: { type: "string", description: "2-4 sentence plain-English summary of the session." },
    technical_analysis: {
      type: "object",
      additionalProperties: false,
      properties: {
        overview: { type: "string", description: "Technical read across the major indices." },
        key_levels: {
          type: "array",
          items: {
            type: "object",
            additionalProperties: false,
            properties: {
              index: { type: "string" },
              support: { type: "string" },
              resistance: { type: "string" },
              trend: { type: "string", enum: ["uptrend", "downtrend", "range", "reversal"] },
            },
            required: ["index", "support", "resistance", "trend"],
          },
        },
        indicators: { type: "string", description: "Read on RSI/MACD/moving averages/breadth where relevant." },
      },
      required: ["overview", "key_levels", "indicators"],
    },
    fundamental_drivers: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        properties: {
          title: { type: "string" },
          detail: { type: "string" },
        },
        required: ["title", "detail"],
      },
    },
    macro_backdrop: { type: "string", description: "Rates, dollar, inflation, growth, policy context." },
    sector_rotation: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        properties: {
          sector: { type: "string" },
          stance: { type: "string", enum: ["leading", "lagging", "rotating-in", "rotating-out", "neutral"] },
          note: { type: "string" },
        },
        required: ["sector", "stance", "note"],
      },
    },
    swing_trade_ideas: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        properties: {
          ticker: { type: "string" },
          direction: { type: "string", enum: ["long", "short"] },
          thesis: { type: "string" },
          entry_zone: { type: "string" },
          stop: { type: "string" },
          targets: { type: "string" },
          timeframe: { type: "string" },
          conviction: { type: "string", enum: [...CONVICTION] },
        },
        required: ["ticker", "direction", "thesis", "entry_zone", "stop", "targets", "timeframe", "conviction"],
      },
    },
    day_trade_ideas: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        properties: {
          ticker: { type: "string" },
          direction: { type: "string", enum: ["long", "short"] },
          setup: { type: "string" },
          trigger: { type: "string" },
          risk_note: { type: "string" },
        },
        required: ["ticker", "direction", "setup", "trigger", "risk_note"],
      },
    },
    key_risks: { type: "array", items: { type: "string" } },
    what_to_watch: { type: "array", items: { type: "string" } },
    audio_script: {
      type: "string",
      description: "A natural, spoken-word version of the wrap-up (~150-220 words) suitable for text-to-speech narration.",
    },
    disclaimer: { type: "string" },
  },
  required: [
    "headline", "market_tone", "executive_summary", "technical_analysis",
    "fundamental_drivers", "macro_backdrop", "sector_rotation",
    "swing_trade_ideas", "day_trade_ideas", "key_risks", "what_to_watch",
    "audio_script", "disclaimer",
  ],
};

const portfolioSchema = {
  type: "object",
  additionalProperties: false,
  properties: {
    headline: { type: "string" },
    overall_assessment: { type: "string" },
    risk_level: { type: "string", enum: ["low", "moderate", "elevated", "high"] },
    diversification: {
      type: "object",
      additionalProperties: false,
      properties: {
        rating: { type: "string", enum: ["poor", "fair", "good", "excellent"] },
        comment: { type: "string" },
      },
      required: ["rating", "comment"],
    },
    holdings_analysis: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        properties: {
          ticker: { type: "string" },
          rating: { type: "string", enum: ["strong-buy", "buy", "hold", "reduce", "sell"] },
          fundamental: { type: "string", description: "Valuation, growth, balance sheet, catalysts." },
          technical: { type: "string", description: "Trend, key levels, momentum." },
        },
        required: ["ticker", "rating", "fundamental", "technical"],
      },
    },
    suggestions: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        properties: {
          action: { type: "string", enum: ["add", "trim", "hold", "hedge", "exit", "watch"] },
          ticker: { type: "string" },
          rationale: { type: "string" },
        },
        required: ["action", "ticker", "rationale"],
      },
    },
    risk_warnings: { type: "array", items: { type: "string" } },
    audio_script: { type: "string", description: "Spoken-word summary (~120-180 words) for text-to-speech." },
    disclaimer: { type: "string" },
  },
  required: [
    "headline", "overall_assessment", "risk_level", "diversification",
    "holdings_analysis", "suggestions", "risk_warnings", "audio_script", "disclaimer",
  ],
};

const SYSTEM_PROMPT = `You are "Hermes", the senior markets strategist for DAMAN Securities — a sharp, balanced, institutional-grade voice.

Your analysis is loaded with BOTH fundamentals (valuation, earnings, growth, margins, balance sheet, macro: rates, inflation, the dollar, growth, central-bank policy) AND technicals (trend, support/resistance, moving averages, RSI/MACD, volume, breadth, sector rotation).

Rules:
- Be specific and quantitative where the provided data allows; never invent exact prices you weren't given — describe levels qualitatively if you lack data, and say so.
- Balanced and risk-aware: present both bull and bear cases; flag risks explicitly.
- Trade ideas are educational scenarios, not signals. Always include risk management (stops).
- This is NOT personalized financial advice. Always include a clear disclaimer.
- Write for an informed retail/active-trader audience: confident, clear, no fluff.
- Respond ONLY with the requested JSON structure.`;

interface ClaudeContent {
  type: string;
  text?: string;
}

async function callClaude(apiKey: string, userPrompt: string, schema: unknown): Promise<unknown> {
  const res = await fetch(ANTHROPIC_URL, {
    method: "POST",
    headers: {
      "x-api-key": apiKey,
      "anthropic-version": "2023-06-01",
      "content-type": "application/json",
    },
    body: JSON.stringify({
      model: MODEL,
      max_tokens: 8000,
      thinking: { type: "adaptive" },
      output_config: { effort: "medium", format: { type: "json_schema", schema } },
      system: SYSTEM_PROMPT,
      messages: [{ role: "user", content: userPrompt }],
    }),
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Anthropic API ${res.status}: ${body}`);
  }

  const data = await res.json();

  if (data.stop_reason === "refusal") {
    throw new Error("The model declined to answer this request.");
  }

  // structured outputs guarantee the first text block is valid JSON
  const textBlock = (data.content as ClaudeContent[] | undefined)?.find(
    (b) => b.type === "text" && typeof b.text === "string"
  );
  if (!textBlock?.text) {
    throw new Error("No text content in model response.");
  }
  return JSON.parse(textBlock.text);
}

function buildWrapupPrompt(marketData: unknown, focus?: string): string {
  const ctx = marketData ? JSON.stringify(marketData, null, 2) : "(no live snapshot provided)";
  return `Produce today's MARKET WRAP-UP for US equities (and note relevant FX/commodities/rates where they matter).

Live market snapshot (use these numbers; do not fabricate others):
${ctx}

${focus ? `Pay particular attention to: ${focus}\n` : ""}
Deliver a complete, fundamentals-and-technicals-loaded wrap-up with concrete swing-trade and day-trade IDEAS (educational, with risk management). Fill every field of the schema.`;
}

function buildPortfolioPrompt(holdings: unknown, marketData: unknown): string {
  return `Analyze this portfolio as "Hermes" — both FUNDAMENTAL and TECHNICAL, position by position, then overall.

Holdings (ticker, quantity, avg cost, current price, P&L where available):
${JSON.stringify(holdings, null, 2)}

Market snapshot for context:
${marketData ? JSON.stringify(marketData, null, 2) : "(none provided)"}

Assess diversification and overall risk, rate each holding, and give actionable (educational) suggestions with rationale. Fill every field of the schema.`;
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") {
    return new Response(null, { status: 200, headers: corsHeaders });
  }

  try {
    const apiKey = Deno.env.get("ANTHROPIC_API_KEY");
    const body = req.method === "POST" ? await req.json().catch(() => ({})) : {};
    const mode = body.mode || "wrapup";

    if (!apiKey) {
      // Graceful, explicit signal so the UI can show a "configure key" state
      return new Response(
        JSON.stringify({
          success: false,
          error: "ANTHROPIC_API_KEY not configured",
          message: "Set ANTHROPIC_API_KEY in your Supabase function secrets to enable AI commentary.",
        }),
        { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    let schema: unknown;
    let prompt: string;

    if (mode === "portfolio") {
      schema = portfolioSchema;
      prompt = buildPortfolioPrompt(body.holdings ?? [], body.marketData);
    } else {
      schema = wrapupSchema;
      prompt = buildWrapupPrompt(body.marketData, body.focus);
    }

    const result = await callClaude(apiKey, prompt, schema);

    return new Response(
      JSON.stringify({
        success: true,
        mode,
        model: MODEL,
        generated_at: new Date().toISOString(),
        data: result,
      }),
      { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  } catch (error) {
    console.error("ai-market-commentary error:", error);
    return new Response(
      JSON.stringify({ success: false, error: "commentary_failed", details: String(error) }),
      { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  }
});
