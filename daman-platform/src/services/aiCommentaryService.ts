// Client for the Claude-powered ai-market-commentary edge function.
// Falls back to a clearly-labelled DEMO response when the function isn't
// reachable or the ANTHROPIC_API_KEY hasn't been configured yet, so the UI
// is fully usable in development.

export interface KeyLevel {
  index: string;
  support: string;
  resistance: string;
  trend: 'uptrend' | 'downtrend' | 'range' | 'reversal';
}

export interface SwingIdea {
  ticker: string;
  direction: 'long' | 'short';
  thesis: string;
  entry_zone: string;
  stop: string;
  targets: string;
  timeframe: string;
  conviction: 'low' | 'medium' | 'high';
}

export interface DayIdea {
  ticker: string;
  direction: 'long' | 'short';
  setup: string;
  trigger: string;
  risk_note: string;
}

export interface MarketWrapUp {
  headline: string;
  market_tone: 'bullish' | 'bearish' | 'neutral' | 'mixed';
  executive_summary: string;
  technical_analysis: { overview: string; key_levels: KeyLevel[]; indicators: string };
  fundamental_drivers: { title: string; detail: string }[];
  macro_backdrop: string;
  sector_rotation: { sector: string; stance: string; note: string }[];
  swing_trade_ideas: SwingIdea[];
  day_trade_ideas: DayIdea[];
  key_risks: string[];
  what_to_watch: string[];
  audio_script: string;
  disclaimer: string;
}

export interface PortfolioAnalysis {
  headline: string;
  overall_assessment: string;
  risk_level: 'low' | 'moderate' | 'elevated' | 'high';
  diversification: { rating: 'poor' | 'fair' | 'good' | 'excellent'; comment: string };
  holdings_analysis: {
    ticker: string;
    rating: 'strong-buy' | 'buy' | 'hold' | 'reduce' | 'sell';
    fundamental: string;
    technical: string;
  }[];
  suggestions: { action: 'add' | 'trim' | 'hold' | 'hedge' | 'exit' | 'watch'; ticker: string; rationale: string }[];
  risk_warnings: string[];
  audio_script: string;
  disclaimer: string;
}

export interface CommentaryResult<T> {
  data: T;
  generatedAt: string;
  demo: boolean;
  model?: string;
  note?: string;
}

const FN_URL = () => {
  const base = import.meta.env.VITE_SUPABASE_URL;
  return base ? `${base}/functions/v1/ai-market-commentary` : null;
};

async function callFunction(payload: Record<string, unknown>): Promise<{ success: boolean; data?: unknown; model?: string; generated_at?: string; message?: string }> {
  const url = FN_URL();
  const key = import.meta.env.VITE_SUPABASE_ANON_KEY;
  if (!url || !key) throw new Error('Supabase not configured');

  const res = await fetch(url, {
    method: 'POST',
    headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`Function returned ${res.status}`);
  return res.json();
}

export async function getMarketWrapUp(
  marketData?: unknown,
  focus?: string
): Promise<CommentaryResult<MarketWrapUp>> {
  try {
    const json = await callFunction({ mode: 'wrapup', marketData, focus });
    if (json.success && json.data) {
      return {
        data: json.data as MarketWrapUp,
        generatedAt: json.generated_at || new Date().toISOString(),
        demo: false,
        model: json.model,
      };
    }
    return { data: DEMO_WRAPUP, generatedAt: new Date().toISOString(), demo: true, note: json.message };
  } catch {
    return { data: DEMO_WRAPUP, generatedAt: new Date().toISOString(), demo: true };
  }
}

export async function getPortfolioAnalysis(
  holdings: unknown,
  marketData?: unknown
): Promise<CommentaryResult<PortfolioAnalysis>> {
  try {
    const json = await callFunction({ mode: 'portfolio', holdings, marketData });
    if (json.success && json.data) {
      return {
        data: json.data as PortfolioAnalysis,
        generatedAt: json.generated_at || new Date().toISOString(),
        demo: false,
        model: json.model,
      };
    }
    return { data: DEMO_PORTFOLIO, generatedAt: new Date().toISOString(), demo: true, note: json.message };
  } catch {
    return { data: DEMO_PORTFOLIO, generatedAt: new Date().toISOString(), demo: true };
  }
}

// ---- Demo content (clearly labelled as sample, not live AI) -------------------

const DEMO_WRAPUP: MarketWrapUp = {
  headline: 'Stocks grind higher as megacap tech leads; rates ease into the close',
  market_tone: 'bullish',
  executive_summary:
    'Equities closed broadly higher led by semiconductors and megacap tech, while a softer move in Treasury yields supported risk appetite. Breadth improved into the afternoon but remains narrow, keeping the tape leadership-dependent.',
  technical_analysis: {
    overview:
      'The S&P 500 is holding above its rising 20-day moving average and pressing toward the prior high; the Nasdaq 100 leads while small caps lag, underscoring narrow leadership.',
    key_levels: [
      { index: 'S&P 500', support: 'prior breakout / 20-DMA', resistance: 'recent swing high', trend: 'uptrend' },
      { index: 'Nasdaq 100', support: 'rising 20-DMA', resistance: 'all-time high zone', trend: 'uptrend' },
      { index: 'Russell 2000', support: 'range floor', resistance: 'range ceiling', trend: 'range' },
    ],
    indicators:
      'Daily RSI is elevated but not yet at extreme; MACD remains positive. Breadth (advancers vs decliners) is constructive but not broad — watch for confirmation from equal-weight indices.',
  },
  fundamental_drivers: [
    { title: 'Earnings resilience', detail: 'Megacap results continue to beat on margins, supporting index-level EPS even as guidance turns cautious.' },
    { title: 'Disinflation trend', detail: 'Cooling inflation keeps a rate-cut path plausible, compressing the discount rate applied to long-duration growth names.' },
  ],
  macro_backdrop:
    '10-year yields eased modestly and the dollar softened, a supportive mix for equities. Markets remain sensitive to upcoming inflation and labor prints that could shift rate expectations.',
  sector_rotation: [
    { sector: 'Technology', stance: 'leading', note: 'Semis and software carrying the index.' },
    { sector: 'Financials', stance: 'rotating-in', note: 'Steeper curve narrative aiding banks.' },
    { sector: 'Utilities', stance: 'lagging', note: 'Defensive bid fading as risk appetite returns.' },
  ],
  swing_trade_ideas: [
    {
      ticker: 'NVDA', direction: 'long', thesis: 'Trend-leader holding above rising moving averages with strong relative strength.',
      entry_zone: 'pullback to 20-DMA', stop: 'below the 50-DMA', targets: 'prior high, then measured-move extension',
      timeframe: '2-6 weeks', conviction: 'medium',
    },
    {
      ticker: 'XLF', direction: 'long', thesis: 'Sector rotation into financials with improving breadth.',
      entry_zone: 'breakout retest', stop: 'below the breakout level', targets: 'next resistance shelf',
      timeframe: '3-8 weeks', conviction: 'low',
    },
  ],
  day_trade_ideas: [
    { ticker: 'SPY', direction: 'long', setup: 'Opening-range breakout on strong breadth', trigger: 'reclaim of prior-day high on volume', risk_note: 'Stop below the opening range; size for a tight intraday stop.' },
  ],
  key_risks: [
    'Narrow leadership leaves the index vulnerable if megacaps stumble.',
    'A hot inflation print could reprice rate-cut expectations and pressure long-duration growth.',
    'Elevated RSI raises the odds of a near-term pullback.',
  ],
  what_to_watch: ['Upcoming CPI / PCE inflation data', '10-year Treasury yield', 'Megacap earnings reactions', 'Equal-weight vs cap-weight breadth'],
  audio_script:
    "Here's your market wrap-up. Stocks closed broadly higher today, led once again by megacap technology and semiconductors, while a modest easing in Treasury yields gave risk assets room to run. The S&P 500 is holding above its rising twenty-day average and pressing toward its recent high, with the Nasdaq one hundred leading and small caps still lagging — a reminder that leadership remains narrow. On the fundamentals, resilient megacap earnings and a cooling inflation trend continue to support the tape. The risks: that narrow leadership, a potentially hot inflation print, and a daily RSI that's getting stretched. Watch the next inflation reading, the ten-year yield, and whether breadth broadens out. As always, this is educational commentary, not personalized financial advice.",
  disclaimer:
    'This is AI-generated market commentary for educational purposes only and is NOT personalized investment advice. Trading involves substantial risk of loss.',
};

const DEMO_PORTFOLIO: PortfolioAnalysis = {
  headline: 'Concentrated growth tilt — strong momentum, but watch single-name risk',
  overall_assessment:
    'The portfolio is tilted toward large-cap growth and technology, which has driven strong recent performance but concentrates risk in a single factor. Consider balancing with lower-correlation exposure.',
  risk_level: 'elevated',
  diversification: { rating: 'fair', comment: 'Heavy overlap in tech/growth; limited sector and factor diversification.' },
  holdings_analysis: [
    { ticker: 'AAPL', rating: 'hold', fundamental: 'Premium valuation supported by services growth and buybacks; hardware cycle is the swing factor.', technical: 'Above key moving averages; constructive trend with support at the prior breakout.' },
    { ticker: 'TSLA', rating: 'reduce', fundamental: 'High valuation with margin pressure; delivery growth decelerating.', technical: 'Choppy range; momentum mixed — respect the range boundaries.' },
  ],
  suggestions: [
    { action: 'trim', ticker: 'TSLA', rationale: 'Reduce single-name volatility and lock in some risk given mixed momentum.' },
    { action: 'add', ticker: 'a low-correlation ETF', rationale: 'Improve diversification away from the tech/growth factor.' },
    { action: 'hedge', ticker: 'index puts', rationale: 'Consider a modest hedge given concentration and elevated index RSI.' },
  ],
  risk_warnings: ['High concentration in a single sector/factor.', 'Drawdowns can be sharp when narrow leadership reverses.'],
  audio_script:
    "Here's your portfolio review. Your holdings lean heavily toward large-cap growth and technology, which has worked well recently but concentrates your risk in one factor. Overall risk looks elevated. Apple screens as a hold on solid fundamentals and a constructive trend, while Tesla looks like a candidate to trim given a stretched valuation and choppy momentum. To balance things out, consider adding a lower-correlation position and possibly a modest hedge. Remember, this is educational analysis, not personalized financial advice.",
  disclaimer:
    'This is AI-generated analysis for educational purposes only and is NOT personalized investment advice. Trading involves substantial risk of loss.',
};
