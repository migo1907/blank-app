import { supabase } from '../lib/supabase';

export interface DailyStockData {
  symbol: string;
  name: string;
  price: number;
  SMA50: number;
  SMA200: number;
  RSI2: number;
  MACD: number;
  MACDSignal: number;
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

function calculateSMA(data: number[], period: number): number {
  if (data.length < period) return data[data.length - 1] || 0;

  const sum = data.slice(-period).reduce((a, b) => a + b, 0);
  return sum / period;
}

function calculateRSI(prices: number[], period: number = 2): number {
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

function calculateEMA(data: number[], period: number): number {
  if (data.length < period) return data[data.length - 1] || 0;

  const k = 2 / (period + 1);
  let ema = data.slice(0, period).reduce((a, b) => a + b, 0) / period;

  for (let i = period; i < data.length; i++) {
    ema = data[i] * k + ema * (1 - k);
  }

  return ema;
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

async function fetchDailyBars(symbol: string, days: number = 250): Promise<BarData[]> {
  try {
    const url = `${SUPABASE_URL}/functions/v1/fetch-intraday-data?symbol=${symbol}&interval=1d&days=${days}`;

    const response = await fetch(url, {
      headers: {
        'Authorization': `Bearer ${SUPABASE_ANON_KEY}`,
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      console.error(`Failed to fetch daily data for ${symbol}: ${response.status}`);
      return [];
    }

    const result = await response.json();

    if (result.success && result.data && Array.isArray(result.data)) {
      return result.data;
    }

    return [];
  } catch (error) {
    console.error(`Error fetching daily bars for ${symbol}:`, error);
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

export async function fetchLiveDailyData(symbol: string): Promise<DailyStockData | null> {
  try {
    const [dailyBars, currentPrice] = await Promise.all([
      fetchDailyBars(symbol, 250),
      fetchCurrentPrice(symbol)
    ]);

    if (dailyBars.length < 50) {
      console.log(`Insufficient daily data for ${symbol}`);
      return null;
    }

    const prices = dailyBars.map(b => b.close);

    const sma50 = calculateSMA(prices, 50);
    const sma200 = calculateSMA(prices, 200);
    const rsi2 = calculateRSI(prices, 2);
    const { macd, signal } = calculateMACD(prices);

    const price = currentPrice > 0 ? currentPrice : prices[prices.length - 1];

    return {
      symbol,
      name: `${symbol} Inc.`,
      price,
      SMA50: sma50,
      SMA200: sma200,
      RSI2: rsi2,
      MACD: macd,
      MACDSignal: signal,
      source: 'alpaca'
    };
  } catch (error) {
    console.error(`Error processing daily data for ${symbol}:`, error);
    return null;
  }
}

export async function fetchMultipleDailyData(symbols: string[]): Promise<DailyStockData[]> {
  const results = await Promise.all(
    symbols.map(symbol => fetchLiveDailyData(symbol))
  );

  return results.filter((data): data is DailyStockData => data !== null);
}

export const DEFAULT_DAILY_SCAN_SYMBOLS = [
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
