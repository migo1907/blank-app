import { supabase } from '../lib/supabase';

export interface IntradayStockData {
  symbol: string;
  name: string;
  price: number;
  EMA20_15m: number;
  EMA50_15m: number;
  RSI3_5m: number;
  MACD_5m: number;
  MACDSignal_5m: number;
  source: string;
}

interface BarData {
  timestamp: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL;
const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY;

function calculateEMA(data: number[], period: number): number {
  if (data.length < period) return data[data.length - 1] || 0;

  const k = 2 / (period + 1);
  let ema = data.slice(0, period).reduce((a, b) => a + b, 0) / period;

  for (let i = period; i < data.length; i++) {
    ema = data[i] * k + ema * (1 - k);
  }

  return ema;
}

function calculateRSI(prices: number[], period: number = 3): number {
  if (prices.length < period + 1) return 50;

  const changes = [];
  for (let i = 1; i < prices.length; i++) {
    changes.push(prices[i] - prices[i - 1]);
  }

  let gains = 0;
  let losses = 0;

  for (let i = 0; i < period; i++) {
    if (changes[i] > 0) gains += changes[i];
    else losses -= changes[i];
  }

  let avgGain = gains / period;
  let avgLoss = losses / period;

  for (let i = period; i < changes.length; i++) {
    const change = changes[i];
    avgGain = (avgGain * (period - 1) + (change > 0 ? change : 0)) / period;
    avgLoss = (avgLoss * (period - 1) + (change < 0 ? -change : 0)) / period;
  }

  if (avgLoss === 0) return 100;
  const rs = avgGain / avgLoss;
  return 100 - (100 / (1 + rs));
}

function calculateMACD(prices: number[]): { macd: number; signal: number } {
  if (prices.length < 26) return { macd: 0, signal: 0 };

  const ema12 = calculateEMA(prices, 12);
  const ema26 = calculateEMA(prices, 26);
  const macd = ema12 - ema26;

  const macdLine: number[] = [];
  for (let i = 26; i <= prices.length; i++) {
    const slice = prices.slice(0, i);
    const e12 = calculateEMA(slice, 12);
    const e26 = calculateEMA(slice, 26);
    macdLine.push(e12 - e26);
  }

  const signal = calculateEMA(macdLine, 9);

  return { macd, signal };
}

async function fetchIntradayBars(symbol: string, interval: string, days: number = 5): Promise<BarData[]> {
  try {
    const url = `${SUPABASE_URL}/functions/v1/fetch-intraday-data?symbol=${symbol}&interval=${interval}&days=${days}`;

    const response = await fetch(url, {
      headers: {
        'Authorization': `Bearer ${SUPABASE_ANON_KEY}`,
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      console.error(`Failed to fetch intraday data for ${symbol}: ${response.status}`);
      return [];
    }

    const result = await response.json();

    if (result.success && result.data && Array.isArray(result.data)) {
      return result.data;
    }

    return [];
  } catch (error) {
    console.error(`Error fetching intraday bars for ${symbol}:`, error);
    return [];
  }
}

async function fetchCurrentPrice(symbol: string): Promise<number> {
  try {
    const url = `${SUPABASE_URL}/functions/v1/fetch-stock-data?symbols=${symbol}&mode=return`;

    const response = await fetch(url, {
      headers: {
        'Authorization': `Bearer ${SUPABASE_ANON_KEY}`,
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      return 0;
    }

    const result = await response.json();

    if (result.success && result.data && result.data.length > 0) {
      return result.data[0].price || 0;
    }

    return 0;
  } catch (error) {
    console.error(`Error fetching price for ${symbol}:`, error);
    return 0;
  }
}

export async function fetchLiveIntradayData(symbol: string): Promise<IntradayStockData | null> {
  try {
    const [bars_5m, bars_15m, currentPrice] = await Promise.all([
      fetchIntradayBars(symbol, '5m', 5),
      fetchIntradayBars(symbol, '15m', 5),
      fetchCurrentPrice(symbol)
    ]);

    if (bars_5m.length === 0 || bars_15m.length === 0) {
      console.log(`Insufficient data for ${symbol}`);
      return null;
    }

    const prices_5m = bars_5m.map(b => b.close);
    const prices_15m = bars_15m.map(b => b.close);

    const ema20_15m = calculateEMA(prices_15m, 20);
    const ema50_15m = calculateEMA(prices_15m, 50);
    const rsi3_5m = calculateRSI(prices_5m, 3);
    const { macd, signal } = calculateMACD(prices_5m);

    const price = currentPrice > 0 ? currentPrice : prices_5m[prices_5m.length - 1];

    return {
      symbol,
      name: `${symbol} Inc.`,
      price,
      EMA20_15m: ema20_15m,
      EMA50_15m: ema50_15m,
      RSI3_5m: rsi3_5m,
      MACD_5m: macd,
      MACDSignal_5m: signal,
      source: 'alpaca'
    };
  } catch (error) {
    console.error(`Error processing intraday data for ${symbol}:`, error);
    return null;
  }
}

export async function fetchMultipleIntradayData(symbols: string[]): Promise<IntradayStockData[]> {
  const results = await Promise.all(
    symbols.map(symbol => fetchLiveIntradayData(symbol))
  );

  return results.filter((data): data is IntradayStockData => data !== null);
}

export const DEFAULT_SCAN_SYMBOLS = [
  'AAPL', 'MSFT', 'GOOGL', 'META', 'AMZN', 'TSLA', 'NVDA', 'AMD', 'INTC', 'NFLX',
  'SMCI', 'UPST', 'SPY', 'QQQ', 'IWM', 'DIA', 'COIN', 'SHOP', 'SQ', 'PYPL',
  'ADBE', 'CRM', 'ORCL', 'CSCO', 'AVGO', 'TXN', 'QCOM', 'NOW', 'INTU', 'AMAT',
  'MU', 'LRCX', 'KLAC', 'ASML', 'TSM', 'MRVL', 'SNPS', 'CDNS', 'ADI', 'MCHP',
  'JPM', 'BAC', 'WFC', 'GS', 'MS', 'C', 'BLK', 'SCHW', 'AXP', 'USB',
  'PNC', 'TFC', 'COF', 'BK', 'STT', 'FITB', 'HBAN', 'RF', 'CFG', 'KEY',
  'JNJ', 'UNH', 'PFE', 'ABBV', 'TMO', 'ABT', 'DHR', 'LLY', 'BMY', 'AMGN',
  'GILD', 'CVS', 'CI', 'HUM', 'ANTM', 'WBA', 'BAX', 'BDX', 'SYK', 'BSX',
  'XOM', 'CVX', 'COP', 'SLB', 'EOG', 'MPC', 'PSX', 'VLO', 'OXY', 'HAL',
  'BKR', 'DVN', 'FANG', 'MRO', 'APA', 'HES', 'NOV', 'HP', 'CTRA', 'EQT',
  'BA', 'GE', 'HON', 'CAT', 'MMM', 'LMT', 'RTX', 'UPS', 'DE', 'GD',
  'NOC', 'EMR', 'ETN', 'ITW', 'PH', 'CMI', 'FDX', 'CSX', 'NSC', 'UNP',
  'WM', 'PG', 'KO', 'PEP', 'PM', 'MO', 'MDLZ', 'CL', 'COST', 'WMT',
  'HD', 'LOW', 'TGT', 'TJX', 'DG', 'DLTR', 'ROST', 'BBY', 'EBAY', 'ETSY',
  'DIS', 'CMCSA', 'CHTR', 'T', 'VZ', 'TMUS', 'NFLX', 'SPOT', 'PARA', 'WBD',
  'NKE', 'SBUX', 'MCD', 'CMG', 'YUM', 'DPZ', 'QSR', 'DNKN', 'WEN', 'JACK',
  'F', 'GM', 'RIVN', 'LCID', 'NIO', 'XPEV', 'LI', 'GOEV', 'FSR', 'RIDE',
  'PLTR', 'SNOW', 'NET', 'DDOG', 'CRWD', 'ZS', 'OKTA', 'PANW', 'FTNT', 'CYBR',
  'SQ', 'SOFI', 'AFRM', 'UPST', 'LC', 'NU', 'VIRT', 'HOOD', 'COIN', 'MARA',
  'RIOT', 'CLSK', 'BITF', 'HUT', 'BTBT', 'CAN', 'MSTR', 'SI', 'CIFR', 'HIVE'
];
