export interface OptionPrice {
  strike: number;
  bid: number;
  ask: number;
  last: number;
  mid?: number;
  volume: number;
  openInterest: number;
  impliedVolatility: number;
}

export interface LiveOptionsPrices {
  underlying: string;
  underlyingPrice: number;
  timestamp: string;
  calls: OptionPrice[];
  puts: OptionPrice[];
}

export async function fetchLiveOptionsPrices(
  symbol: string,
  expiration?: string
): Promise<LiveOptionsPrices | null> {
  try {
    const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
    const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

    const response = await fetch(
      `${supabaseUrl}/functions/v1/fetch-options-prices?symbol=${symbol}`,
      {
        headers: {
          'Authorization': `Bearer ${supabaseKey}`,
          'Content-Type': 'application/json',
        },
      }
    );

    if (!response.ok) {
      throw new Error(`Failed to fetch options data: ${response.status}`);
    }

    const result = await response.json();

    if (!result.success || !result.data) {
      throw new Error('No option chain data available');
    }

    const data = result.data;

    const calls: OptionPrice[] = data.calls?.map((call: any) => ({
      strike: call.strike,
      bid: call.bid || 0,
      ask: call.ask || 0,
      last: call.last || 0,
      mid: call.mid || (call.bid && call.ask ? (call.bid + call.ask) / 2 : call.last || 0),
      volume: call.volume || 0,
      openInterest: call.openInterest || 0,
      impliedVolatility: call.impliedVolatility || call.iv || 0,
    })) || [];

    const puts: OptionPrice[] = data.puts?.map((put: any) => ({
      strike: put.strike,
      bid: put.bid || 0,
      ask: put.ask || 0,
      last: put.last || 0,
      mid: put.mid || (put.bid && put.ask ? (put.bid + put.ask) / 2 : put.last || 0),
      volume: put.volume || 0,
      openInterest: put.openInterest || 0,
      impliedVolatility: put.impliedVolatility || put.iv || 0,
    })) || [];

    return {
      underlying: data.underlying || symbol,
      underlyingPrice: data.underlyingPrice || 0,
      timestamp: data.timestamp || new Date().toISOString(),
      calls,
      puts,
    };
  } catch (error) {
    console.error('Error fetching live options prices:', error);
    return null;
  }
}

export function findClosestStrike(
  options: OptionPrice[],
  targetStrike: number
): OptionPrice | null {
  if (!options || options.length === 0) return null;

  let closest = options[0];
  let minDiff = Math.abs(options[0].strike - targetStrike);

  for (const option of options) {
    const diff = Math.abs(option.strike - targetStrike);
    if (diff < minDiff) {
      minDiff = diff;
      closest = option;
    }
  }

  return closest;
}

export function calculateMidPrice(bid: number, ask: number): number {
  if (bid === 0 && ask === 0) return 0;
  if (bid === 0) return ask;
  if (ask === 0) return bid;
  return (bid + ask) / 2;
}

export async function getOptionPriceForStrike(
  symbol: string,
  expiration: string,
  strike: number,
  optionType: 'CALL' | 'PUT'
): Promise<number> {
  try {
    const pricesData = await fetchLiveOptionsPrices(symbol, expiration);

    if (!pricesData) {
      return simulateFallbackPrice(strike, optionType);
    }

    const options = optionType === 'CALL' ? pricesData.calls : pricesData.puts;
    const closestOption = findClosestStrike(options, strike);

    if (!closestOption) {
      return simulateFallbackPrice(strike, optionType);
    }

    const midPrice = calculateMidPrice(closestOption.bid, closestOption.ask);

    if (midPrice === 0 && closestOption.last > 0) {
      return closestOption.last;
    }

    return midPrice > 0 ? midPrice : simulateFallbackPrice(strike, optionType);
  } catch (error) {
    console.error('Error getting option price:', error);
    return simulateFallbackPrice(strike, optionType);
  }
}

function simulateFallbackPrice(strike: number, optionType: 'CALL' | 'PUT'): number {
  const basePrice = 50 + Math.random() * 100;
  return parseFloat(basePrice.toFixed(2));
}

export async function getSPXOptionPrice(
  strike: number,
  expirationDate: string,
  optionType: 'CALL' | 'PUT'
): Promise<number> {
  const expirationTimestamp = Math.floor(new Date(expirationDate).getTime() / 1000);
  return getOptionPriceForStrike('^SPX', expirationTimestamp.toString(), strike, optionType);
}
