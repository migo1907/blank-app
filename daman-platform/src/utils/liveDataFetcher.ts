interface FetchOptions {
  symbol: string;
  interval?: string;
  days?: number;
  includeExtendedHours?: boolean;
  retries?: number;
  retryDelay?: number;
}

interface OHLCVData {
  timestamp: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

interface LiveDataResponse {
  success: boolean;
  symbol: string;
  interval: string;
  dataPoints: number;
  data: OHLCVData[];
  error?: string;
}

const DEFAULT_RETRY_COUNT = 3;
const DEFAULT_RETRY_DELAY = 1000;
const REQUEST_TIMEOUT = 15000;

const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

export async function fetchLiveData(options: FetchOptions): Promise<LiveDataResponse | null> {
  const {
    symbol,
    interval = '5m',
    days = 30,
    includeExtendedHours = false,
    retries = DEFAULT_RETRY_COUNT,
    retryDelay = DEFAULT_RETRY_DELAY,
  } = options;

  const baseUrl = import.meta.env.VITE_SUPABASE_URL;
  const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

  if (!baseUrl || !anonKey) {
    console.error('Missing Supabase configuration');
    return null;
  }

  const url = new URL(`${baseUrl}/functions/v1/fetch-intraday-data`);
  url.searchParams.set('symbol', symbol);
  url.searchParams.set('interval', interval);
  url.searchParams.set('days', days.toString());
  url.searchParams.set('includeExtendedHours', includeExtendedHours.toString());

  let lastError: Error | null = null;

  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT);

      const response = await fetch(url.toString(), {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${anonKey}`,
          'Content-Type': 'application/json',
        },
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data = await response.json() as LiveDataResponse;

      if (!data.success) {
        throw new Error(data.error || 'Unknown API error');
      }

      if (!data.data || data.data.length === 0) {
        console.warn(`No data returned for ${symbol}`);
        return {
          success: true,
          symbol,
          interval,
          dataPoints: 0,
          data: [],
        };
      }

      return data;
    } catch (error) {
      lastError = error instanceof Error ? error : new Error('Unknown error');
      console.error(`Attempt ${attempt + 1}/${retries + 1} failed for ${symbol}:`, lastError.message);

      if (attempt < retries) {
        const delay = retryDelay * Math.pow(2, attempt);
        console.log(`Retrying in ${delay}ms...`);
        await sleep(delay);
      }
    }
  }

  console.error(`Failed to fetch data for ${symbol} after ${retries + 1} attempts:`, lastError?.message);
  return null;
}

export async function fetchMultipleSymbols(
  symbols: string[],
  options: Omit<FetchOptions, 'symbol'> = {}
): Promise<Map<string, LiveDataResponse>> {
  const results = new Map<string, LiveDataResponse>();
  const batchSize = 5;
  const delayBetweenBatches = 200;

  for (let i = 0; i < symbols.length; i += batchSize) {
    const batch = symbols.slice(i, i + batchSize);
    const batchPromises = batch.map(symbol =>
      fetchLiveData({ ...options, symbol })
        .then(data => ({ symbol, data }))
    );

    const batchResults = await Promise.all(batchPromises);

    for (const { symbol, data } of batchResults) {
      if (data && data.success) {
        results.set(symbol, data);
      }
    }

    if (i + batchSize < symbols.length) {
      await sleep(delayBetweenBatches);
    }
  }

  return results;
}

export function calculateIndicators(data: OHLCVData[]): {
  ema20: number;
  ema50: number;
  rsi: number;
  vwap: number;
  atr: number;
} {
  const prices = data.map(d => d.close);
  const highs = data.map(d => d.high);
  const lows = data.map(d => d.low);
  const volumes = data.map(d => d.volume);

  return {
    ema20: calculateEMA(prices, 20),
    ema50: calculateEMA(prices, 50),
    rsi: calculateRSI(prices, 14),
    vwap: calculateVWAP(prices, volumes),
    atr: calculateATR(highs, lows, prices, 14),
  };
}

function calculateEMA(prices: number[], period: number): number {
  if (prices.length < period) return prices[prices.length - 1] || 0;
  const k = 2 / (period + 1);
  let ema = prices.slice(0, period).reduce((a, b) => a + b, 0) / period;
  for (let i = period; i < prices.length; i++) {
    ema = prices[i] * k + ema * (1 - k);
  }
  return ema;
}

function calculateRSI(prices: number[], period: number = 14): number {
  if (prices.length < period + 1) return 50;
  let gains = 0;
  let losses = 0;
  for (let i = prices.length - period; i < prices.length; i++) {
    const diff = prices[i] - prices[i - 1];
    if (diff > 0) gains += diff;
    else losses -= diff;
  }
  const avgGain = gains / period;
  const avgLoss = losses / period;
  const rs = avgGain / (avgLoss + 1e-9);
  return 100 - 100 / (1 + rs);
}

function calculateVWAP(prices: number[], volumes: number[]): number {
  if (prices.length !== volumes.length || prices.length === 0) {
    return prices[prices.length - 1] || 0;
  }
  const pv = prices.reduce((sum, p, i) => sum + p * volumes[i], 0);
  const totalVol = volumes.reduce((a, b) => a + b, 0);
  return totalVol > 0 ? pv / totalVol : prices[prices.length - 1];
}

function calculateATR(highs: number[], lows: number[], closes: number[], period: number = 14): number {
  if (highs.length < period + 1) return 0;
  const trs: number[] = [];
  for (let i = highs.length - period; i < highs.length; i++) {
    const tr = Math.max(
      highs[i] - lows[i],
      Math.abs(highs[i] - closes[i - 1]),
      Math.abs(lows[i] - closes[i - 1])
    );
    trs.push(tr);
  }
  return trs.reduce((a, b) => a + b, 0) / trs.length;
}
