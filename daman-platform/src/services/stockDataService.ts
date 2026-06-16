import { supabase } from '../lib/supabase';

export interface StockData {
  symbol: string;
  name: string;
  price: number;
  change: number;
  changePercent: number;
  volume: number;
  exchange?: string;
  sector?: string;
}

export interface StockUniverse {
  symbol: string;
  name: string;
  exchange: string;
  sector: string;
  industry: string;
  is_sp500: boolean;
  is_nasdaq: boolean;
  market_cap: number;
}

export type StockFilter = 'all' | 'sp500' | 'nasdaq';

class StockDataService {
  private updateInterval: number | null = null;
  private cache: Map<string, { data: StockData; timestamp: number }> = new Map();
  private cacheTimeout = 30000;

  async fetchTopGainers(limit: number = 5): Promise<StockData[]> {
    try {
      const { data, error } = await supabase
        .from('top_gainers')
        .select('*')
        .limit(limit);

      if (error) throw error;

      return (data || []).map(this.formatStockData);
    } catch (error) {
      console.error('Error fetching top gainers:', error);
      return this.getMockGainers(limit);
    }
  }

  async fetchTopLosers(limit: number = 5): Promise<StockData[]> {
    try {
      const { data, error } = await supabase
        .from('top_losers')
        .select('*')
        .limit(limit);

      if (error) throw error;

      return (data || []).map(this.formatStockData);
    } catch (error) {
      console.error('Error fetching top losers:', error);
      return this.getMockLosers(limit);
    }
  }

  async fetchStockUniverse(filter: StockFilter = 'all', search: string = ''): Promise<StockUniverse[]> {
    try {
      let query = supabase.from('stock_universe').select('*');

      if (filter === 'sp500') {
        query = query.eq('is_sp500', true);
      } else if (filter === 'nasdaq') {
        query = query.eq('is_nasdaq', true);
      }

      if (search) {
        query = query.or(`symbol.ilike.%${search}%,name.ilike.%${search}%`);
      }

      query = query.order('symbol');

      const { data, error } = await query;

      if (error) throw error;

      return data || [];
    } catch (error) {
      console.error('Error fetching stock universe:', error);
      return [];
    }
  }

  async fetchLatestPrices(symbols: string[]): Promise<StockData[]> {
    if (symbols.length === 0) return [];

    try {
      const { data, error } = await supabase
        .from('latest_stock_prices')
        .select('*')
        .in('symbol', symbols);

      if (error) throw error;

      if (!data || data.length === 0) {
        return await this.fetchFromAPI(symbols);
      }

      const joined = await this.joinWithUniverse(data);
      return joined.map(this.formatStockData);
    } catch (error) {
      console.error('Error fetching latest prices:', error);
      return await this.fetchFromAPI(symbols);
    }
  }

  private async joinWithUniverse(prices: any[]): Promise<any[]> {
    const symbols = prices.map(p => p.symbol);
    const { data: universe } = await supabase
      .from('stock_universe')
      .select('symbol, name, exchange, sector')
      .in('symbol', symbols);

    const universeMap = new Map(universe?.map(u => [u.symbol, u]) || []);

    return prices.map(p => ({
      ...p,
      name: universeMap.get(p.symbol)?.name || p.symbol,
      exchange: universeMap.get(p.symbol)?.exchange || 'UNKNOWN',
      sector: universeMap.get(p.symbol)?.sector || '',
    }));
  }

  async fetchFromAPI(symbols: string[]): Promise<StockData[]> {
    try {
      const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
      const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

      if (!supabaseUrl || !supabaseKey) {
        throw new Error('Supabase credentials not configured');
      }

      const apiUrl = `${supabaseUrl}/functions/v1/fetch-stock-data?symbols=${symbols.join(',')}&mode=fetch`;

      const response = await fetch(apiUrl, {
        headers: {
          'Authorization': `Bearer ${supabaseKey}`,
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }

      const result = await response.json();
      return result.data || [];
    } catch (error) {
      console.error('Error fetching from API:', error);
      return [];
    }
  }

  async syncStockData(symbols: string[]): Promise<void> {
    try {
      const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
      const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

      const apiUrl = `${supabaseUrl}/functions/v1/fetch-stock-data?symbols=${symbols.join(',')}&mode=update`;

      await fetch(apiUrl, {
        headers: {
          'Authorization': `Bearer ${supabaseKey}`,
          'Content-Type': 'application/json',
        },
      });
    } catch (error) {
      console.error('Error syncing stock data:', error);
    }
  }

  startAutoUpdate(symbols: string[], interval: number = 30000, callback?: () => void): void {
    this.stopAutoUpdate();

    this.syncStockData(symbols);

    this.updateInterval = window.setInterval(() => {
      this.syncStockData(symbols);
      if (callback) callback();
    }, interval);
  }

  stopAutoUpdate(): void {
    if (this.updateInterval !== null) {
      clearInterval(this.updateInterval);
      this.updateInterval = null;
    }
  }

  private formatStockData(data: any): StockData {
    return {
      symbol: data.symbol,
      name: data.name || data.symbol,
      price: parseFloat(data.price) || 0,
      change: parseFloat(data.change) || 0,
      changePercent: parseFloat(data.change_percent) || 0,
      volume: parseInt(data.volume) || 0,
      exchange: data.exchange,
      sector: data.sector,
    };
  }

  private getMockGainers(limit: number): StockData[] {
    const stocks = [
      { symbol: 'NVDA', name: 'NVIDIA Corporation', basePrice: 875.20 },
      { symbol: 'AMD', name: 'Advanced Micro Devices', basePrice: 164.50 },
      { symbol: 'TSLA', name: 'Tesla Inc.', basePrice: 242.80 },
      { symbol: 'META', name: 'Meta Platforms Inc.', basePrice: 488.90 },
      { symbol: 'NFLX', name: 'Netflix Inc.', basePrice: 612.30 },
    ];

    return stocks.slice(0, limit).map((stock, i) => {
      const changePercent = 7 - (i * 1.2);
      const change = (stock.basePrice * changePercent) / 100;
      return {
        symbol: stock.symbol,
        name: stock.name,
        price: stock.basePrice + change,
        change,
        changePercent,
        volume: Math.floor(Math.random() * 50000000) + 10000000,
      };
    });
  }

  private getMockLosers(limit: number): StockData[] {
    const stocks = [
      { symbol: 'PFE', name: 'Pfizer Inc.', basePrice: 28.60 },
      { symbol: 'DIS', name: 'The Walt Disney Company', basePrice: 92.50 },
      { symbol: 'BA', name: 'Boeing Company', basePrice: 175.60 },
      { symbol: 'WMT', name: 'Walmart Inc.', basePrice: 73.40 },
      { symbol: 'JPM', name: 'JPMorgan Chase & Co.', basePrice: 186.20 },
    ];

    return stocks.slice(0, limit).map((stock, i) => {
      const changePercent = -(7 - (i * 1.2));
      const change = (stock.basePrice * changePercent) / 100;
      return {
        symbol: stock.symbol,
        name: stock.name,
        price: stock.basePrice + change,
        change,
        changePercent,
        volume: Math.floor(Math.random() * 50000000) + 10000000,
      };
    });
  }
}

export const stockDataService = new StockDataService();
