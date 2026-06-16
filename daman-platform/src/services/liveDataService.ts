import { supabase } from '../lib/supabase';

export interface LiveStockData {
  symbol: string;
  name: string;
  price: number;
  change_percent: number;
  volume: number;
  sector?: string;
  market_cap?: number;
}

export interface SectorPerformance {
  sector: string;
  change_percent: number;
  total_volume: number;
  stock_count: number;
}

class LiveDataService {
  private updateIntervals: Map<string, number> = new Map();
  private supabaseUrl: string;
  private supabaseKey: string;

  constructor() {
    this.supabaseUrl = import.meta.env.VITE_SUPABASE_URL || '';
    this.supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY || '';
  }

  async fetchLiveMarketMovers(): Promise<{
    gainers: LiveStockData[];
    losers: LiveStockData[];
    active: LiveStockData[];
  }> {
    try {
      const apiUrl = `${this.supabaseUrl}/functions/v1/fetch-stock-data?mode=movers`;

      const response = await fetch(apiUrl, {
        headers: {
          'Authorization': `Bearer ${this.supabaseKey}`,
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }

      const result = await response.json();

      if (result.gainers && result.losers && result.active) {
        return {
          gainers: result.gainers.slice(0, 10),
          losers: result.losers.slice(0, 10),
          active: result.active.slice(0, 10),
        };
      }

      return await this.fetchMarketMoversFromDB();
    } catch (error) {
      console.error('Error fetching live market movers:', error);
      return await this.fetchMarketMoversFromDB();
    }
  }

  private async fetchMarketMoversFromDB(): Promise<{
    gainers: LiveStockData[];
    losers: LiveStockData[];
    active: LiveStockData[];
  }> {
    try {
      const { data: tickData } = await supabase
        .from('tick_data')
        .select('*')
        .order('last_updated', { ascending: false })
        .limit(100);

      if (!tickData || tickData.length === 0) {
        return { gainers: [], losers: [], active: [] };
      }

      const stocks = tickData.map((tick: any) => ({
        symbol: tick.symbol,
        name: tick.company_name || tick.symbol,
        price: parseFloat(tick.price) || 0,
        change_percent: parseFloat(tick.change_percent) || 0,
        volume: parseInt(tick.volume) || 0,
        sector: tick.sector,
        market_cap: parseInt(tick.market_cap) || 0,
      }));

      const gainers = [...stocks]
        .filter(s => s.change_percent > 0)
        .sort((a, b) => b.change_percent - a.change_percent)
        .slice(0, 10);

      const losers = [...stocks]
        .filter(s => s.change_percent < 0)
        .sort((a, b) => a.change_percent - b.change_percent)
        .slice(0, 10);

      const active = [...stocks]
        .sort((a, b) => b.volume - a.volume)
        .slice(0, 10);

      return { gainers, losers, active };
    } catch (error) {
      console.error('Error fetching from DB:', error);
      return { gainers: [], losers: [], active: [] };
    }
  }

  async fetchLiveSectorPerformance(): Promise<SectorPerformance[]> {
    try {
      const { data, error } = await supabase
        .from('tick_data')
        .select('sector, change_percent, volume, market_cap')
        .not('sector', 'is', null);

      if (error) throw error;

      const sectorMap = new Map<string, { total: number; count: number; volume: number }>();

      data?.forEach((row: any) => {
        const sector = row.sector;
        if (!sector) return;

        const current = sectorMap.get(sector) || { total: 0, count: 0, volume: 0 };
        current.total += parseFloat(row.change_percent) || 0;
        current.count += 1;
        current.volume += parseInt(row.volume) || 0;
        sectorMap.set(sector, current);
      });

      return Array.from(sectorMap.entries()).map(([sector, stats]) => ({
        sector,
        change_percent: stats.count > 0 ? stats.total / stats.count : 0,
        total_volume: stats.volume,
        stock_count: stats.count,
      })).sort((a, b) => b.change_percent - a.change_percent);
    } catch (error) {
      console.error('Error fetching sector performance:', error);
      return [];
    }
  }

  startLiveUpdates(key: string, callback: () => void, interval: number = 30000): void {
    this.stopLiveUpdates(key);

    callback();

    const intervalId = window.setInterval(() => {
      callback();
    }, interval);

    this.updateIntervals.set(key, intervalId);
  }

  stopLiveUpdates(key: string): void {
    const intervalId = this.updateIntervals.get(key);
    if (intervalId) {
      clearInterval(intervalId);
      this.updateIntervals.delete(key);
    }
  }

  stopAllUpdates(): void {
    this.updateIntervals.forEach(id => clearInterval(id));
    this.updateIntervals.clear();
  }

  private formatMoverData(data: any): LiveStockData {
    return {
      symbol: data.symbol,
      name: data.name || data.symbol,
      price: parseFloat(data.price) || 0,
      change_percent: parseFloat(data.change_percent) || 0,
      volume: parseInt(data.volume) || 0,
      sector: data.sector,
      market_cap: parseInt(data.market_cap) || 0,
    };
  }
}

export const liveDataService = new LiveDataService();
