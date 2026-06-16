// Shared market/portfolio context builders for Hermes (AI Strategist + chat).
// Produces concrete, numeric context so Claude reasons from data, not vibes.

import { marketDataService } from './marketDataService';

export interface RawHolding {
  symbol: string;
  quantity: number;
  avg_cost: number;
  current_price?: number;
}

export async function buildMarketContext() {
  try {
    const map = await marketDataService.fetchMarketData(['S&P 500', 'Nasdaq', 'Dow Jones', 'VIX']);
    const quotes = Array.from(map.values());
    if (quotes.length === 0) return undefined;

    const indices = quotes.filter((q) => q.name !== 'VIX');
    const vix = quotes.find((q) => q.name === 'VIX');
    const advancers = indices.filter((q) => q.changePercent >= 0).length;
    const avgChange = indices.length
      ? indices.reduce((s, q) => s + q.changePercent, 0) / indices.length
      : 0;

    return {
      indices: indices.map((q) => ({
        name: q.name,
        price: Number(q.price.toFixed(2)),
        changePercent: Number(q.changePercent.toFixed(2)),
      })),
      volatility: vix
        ? { vix: Number(vix.price.toFixed(2)), vixChangePercent: Number(vix.changePercent.toFixed(2)) }
        : undefined,
      derived: {
        breadth: `${advancers}/${indices.length} indices higher`,
        avg_index_change_pct: Number(avgChange.toFixed(2)),
        risk_gauge: vix
          ? vix.price < 15 ? 'low (complacent)' : vix.price < 22 ? 'normal' : 'elevated (fearful)'
          : 'unknown',
      },
      as_of: new Date().toISOString(),
    };
  } catch {
    return undefined;
  }
}

export function readPortfolio(): RawHolding[] {
  try {
    return JSON.parse(localStorage.getItem('portfolio') || '[]');
  } catch {
    return [];
  }
}

// Enrich holdings with weights, P&L %, and concentration.
export function enrichHoldings(holdings: RawHolding[]) {
  const valued = holdings.map((h) => {
    const price = h.current_price ?? h.avg_cost;
    const marketValue = price * h.quantity;
    const costBasis = h.avg_cost * h.quantity;
    const plPct = costBasis > 0 ? ((marketValue - costBasis) / costBasis) * 100 : 0;
    return { ...h, marketValue, plPct };
  });
  const total = valued.reduce((s, h) => s + h.marketValue, 0) || 1;
  return {
    total_value: Number(total.toFixed(2)),
    positions: valued.map((h) => ({
      ticker: h.symbol,
      quantity: h.quantity,
      avg_cost: h.avg_cost,
      current_price: Number((h.current_price ?? h.avg_cost).toFixed(2)),
      weight_pct: Number(((h.marketValue / total) * 100).toFixed(1)),
      pl_pct: Number(h.plPct.toFixed(2)),
    })),
    largest_position_weight_pct: Number(
      ((Math.max(...valued.map((h) => h.marketValue)) / total) * 100).toFixed(1)
    ),
  };
}

/** Full context object passed to the chat (market + portfolio). */
export async function buildChatContext() {
  const market = await buildMarketContext();
  const holdings = readPortfolio();
  return { market, portfolio: holdings.length ? enrichHoldings(holdings) : undefined };
}
