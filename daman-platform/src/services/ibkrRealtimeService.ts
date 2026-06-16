import { ibkrService, OptionChainData } from './ibkrConnectionService';
import { supabase } from '../lib/supabase';

export interface IBKROptionData {
  symbol: string;
  expiration: string;
  strike: number;
  optionType: 'CALL' | 'PUT';
  bid: number;
  ask: number;
  last: number;
  mid: number;
  volume: number;
  openInterest: number;
  impliedVolatility: number;
  delta: number | null;
  gamma?: number | null;
  theta?: number | null;
  vega?: number | null;
  underlyingPrice: number;
  timestamp: string;
}

export class IBKRRealtimeService {
  private isConnected = false;
  private activeSubscriptions = new Map<string, NodeJS.Timeout>();

  async connect(): Promise<boolean> {
    if (this.isConnected) {
      return true;
    }

    try {
      const connected = await ibkrService.connect('127.0.0.1', 7496, 1);
      this.isConnected = connected;
      return connected;
    } catch (error) {
      console.error('Failed to connect to IBKR:', error);
      return false;
    }
  }

  async disconnect(): Promise<void> {
    this.stopAllSubscriptions();
    await ibkrService.disconnect();
    this.isConnected = false;
  }

  async fetchAndStoreOptionsChain(
    symbol: string,
    expiration: string,
    minStrike: number,
    maxStrike: number,
    strikeInterval: number = 5
  ): Promise<void> {
    if (!this.isConnected) {
      throw new Error('Not connected to IBKR');
    }

    try {
      const optionData = await ibkrService.getFullOptionsChain(
        symbol,
        expiration,
        minStrike,
        maxStrike,
        strikeInterval
      );

      await this.storeOptionsData(optionData);
      console.log(`Stored ${optionData.length} option contracts for ${symbol}`);
    } catch (error) {
      console.error('Error fetching and storing options chain:', error);
      throw error;
    }
  }

  private async storeOptionsData(optionData: OptionChainData[]): Promise<void> {
    const records = optionData.map(opt => ({
      symbol: opt.symbol,
      expiration: opt.expiration,
      strike: opt.strike,
      option_type: opt.right,
      bid: opt.bid,
      ask: opt.ask,
      last: opt.last,
      mid: (opt.bid + opt.ask) / 2,
      volume: 0,
      open_interest: 0,
      implied_volatility: opt.impliedVolatility,
      delta: opt.delta,
      gamma: null,
      theta: null,
      vega: null,
      underlying_price: 0,
      timestamp: new Date().toISOString(),
    }));

    const { error } = await supabase
      .from('ibkr_options_realtime')
      .upsert(records, {
        onConflict: 'symbol,expiration,strike,option_type',
        ignoreDuplicates: false,
      });

    if (error) {
      console.error('Error storing options data:', error);
      throw error;
    }
  }

  startRealtimeSubscription(
    symbol: string,
    expiration: string,
    minStrike: number,
    maxStrike: number,
    strikeInterval: number = 5,
    updateIntervalMs: number = 5000
  ): void {
    const key = `${symbol}_${expiration}`;

    if (this.activeSubscriptions.has(key)) {
      console.log(`Subscription already active for ${key}`);
      return;
    }

    const interval = setInterval(async () => {
      try {
        await this.fetchAndStoreOptionsChain(
          symbol,
          expiration,
          minStrike,
          maxStrike,
          strikeInterval
        );
      } catch (error) {
        console.error(`Error updating ${key}:`, error);
      }
    }, updateIntervalMs);

    this.activeSubscriptions.set(key, interval);
    console.log(`Started real-time subscription for ${key}`);

    this.fetchAndStoreOptionsChain(symbol, expiration, minStrike, maxStrike, strikeInterval);
  }

  stopRealtimeSubscription(symbol: string, expiration: string): void {
    const key = `${symbol}_${expiration}`;
    const interval = this.activeSubscriptions.get(key);

    if (interval) {
      clearInterval(interval);
      this.activeSubscriptions.delete(key);
      console.log(`Stopped real-time subscription for ${key}`);
    }
  }

  stopAllSubscriptions(): void {
    for (const [key, interval] of this.activeSubscriptions.entries()) {
      clearInterval(interval);
      console.log(`Stopped subscription for ${key}`);
    }
    this.activeSubscriptions.clear();
  }

  getActiveSubscriptions(): string[] {
    return Array.from(this.activeSubscriptions.keys());
  }

  async getStoredOptionsData(
    symbol: string,
    expiration?: string
  ): Promise<IBKROptionData[]> {
    let query = supabase
      .from('ibkr_options_realtime')
      .select('*')
      .eq('symbol', symbol)
      .order('strike', { ascending: true });

    if (expiration) {
      query = query.eq('expiration', expiration);
    }

    const { data, error } = await query;

    if (error) {
      console.error('Error fetching stored options data:', error);
      throw error;
    }

    return (data || []).map(row => ({
      symbol: row.symbol,
      expiration: row.expiration,
      strike: row.strike,
      optionType: row.option_type === 'C' || row.option_type === 'CALL' ? 'CALL' : 'PUT',
      bid: row.bid,
      ask: row.ask,
      last: row.last,
      mid: row.mid,
      volume: row.volume,
      openInterest: row.open_interest,
      impliedVolatility: row.implied_volatility,
      delta: row.delta,
      gamma: row.gamma,
      theta: row.theta,
      vega: row.vega,
      underlyingPrice: row.underlying_price,
      timestamp: row.timestamp,
    }));
  }
}

export const ibkrRealtimeService = new IBKRRealtimeService();
