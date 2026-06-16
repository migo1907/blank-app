interface AlpacaQuote {
  symbol: string;
  ask_price: number;
  ask_size: number;
  bid_price: number;
  bid_size: number;
  timestamp: string;
}

interface AlpacaBar {
  symbol: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  timestamp: string;
  vwap?: number;
  trade_count?: number;
}

interface AlpacaSnapshot {
  symbol: string;
  latestTrade: {
    price: number;
    size: number;
    timestamp: string;
  };
  latestQuote: {
    ask_price: number;
    ask_size: number;
    bid_price: number;
    bid_size: number;
    timestamp: string;
  };
  minuteBar: {
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
    timestamp: string;
    vwap: number;
  };
  dailyBar: {
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
    timestamp: string;
    vwap: number;
  };
  prevDailyBar: {
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
    timestamp: string;
  };
}

interface StockQuote {
  symbol: string;
  price: number;
  change: number;
  changePercent: number;
  volume: number;
  bid: number;
  ask: number;
  high: number;
  low: number;
  open: number;
  previousClose: number;
  timestamp: number;
}

const ALPACA_API_KEY = import.meta.env.VITE_ALPACA_API_KEY || '';
const ALPACA_SECRET_KEY = import.meta.env.VITE_ALPACA_SECRET_KEY || '';
const ALPACA_DATA_URL = 'https://data.alpaca.markets/v2';

class AlpacaService {
  private headers: HeadersInit;

  constructor() {
    this.headers = {
      'APCA-API-KEY-ID': ALPACA_API_KEY,
      'APCA-API-SECRET-KEY': ALPACA_SECRET_KEY,
      'Accept': 'application/json'
    };
  }

  async getStockQuote(symbol: string): Promise<StockQuote | null> {
    try {
      const response = await fetch(
        `${ALPACA_DATA_URL}/stocks/${symbol}/snapshot`,
        { headers: this.headers }
      );

      if (!response.ok) {
        console.error(`Alpaca API error for ${symbol}:`, response.status);
        return null;
      }

      const data: AlpacaSnapshot = await response.json();

      const currentPrice = data.latestTrade?.price || data.minuteBar?.close || 0;
      const previousClose = data.prevDailyBar?.close || data.dailyBar?.open || currentPrice;
      const change = currentPrice - previousClose;
      const changePercent = previousClose > 0 ? (change / previousClose) * 100 : 0;

      return {
        symbol,
        price: currentPrice,
        change,
        changePercent,
        volume: data.dailyBar?.volume || 0,
        bid: data.latestQuote?.bid_price || 0,
        ask: data.latestQuote?.ask_price || 0,
        high: data.dailyBar?.high || currentPrice,
        low: data.dailyBar?.low || currentPrice,
        open: data.dailyBar?.open || currentPrice,
        previousClose,
        timestamp: new Date(data.latestTrade?.timestamp || Date.now()).getTime()
      };
    } catch (error) {
      console.error(`Error fetching Alpaca quote for ${symbol}:`, error);
      return null;
    }
  }

  async getMultipleQuotes(symbols: string[]): Promise<StockQuote[]> {
    try {
      const symbolsParam = symbols.join(',');
      const response = await fetch(
        `${ALPACA_DATA_URL}/stocks/snapshots?symbols=${symbolsParam}`,
        { headers: this.headers }
      );

      if (!response.ok) {
        console.error('Alpaca API error:', response.status);
        return [];
      }

      const data: Record<string, AlpacaSnapshot> = await response.json();

      return Object.entries(data).map(([symbol, snapshot]) => {
        const currentPrice = snapshot.latestTrade?.price || snapshot.minuteBar?.close || 0;
        const previousClose = snapshot.prevDailyBar?.close || snapshot.dailyBar?.open || currentPrice;
        const change = currentPrice - previousClose;
        const changePercent = previousClose > 0 ? (change / previousClose) * 100 : 0;

        return {
          symbol,
          price: currentPrice,
          change,
          changePercent,
          volume: snapshot.dailyBar?.volume || 0,
          bid: snapshot.latestQuote?.bid_price || 0,
          ask: snapshot.latestQuote?.ask_price || 0,
          high: snapshot.dailyBar?.high || currentPrice,
          low: snapshot.dailyBar?.low || currentPrice,
          open: snapshot.dailyBar?.open || currentPrice,
          previousClose,
          timestamp: new Date(snapshot.latestTrade?.timestamp || Date.now()).getTime()
        };
      });
    } catch (error) {
      console.error('Error fetching Alpaca quotes:', error);
      return [];
    }
  }

  async getLatestQuote(symbol: string): Promise<AlpacaQuote | null> {
    try {
      const response = await fetch(
        `${ALPACA_DATA_URL}/stocks/${symbol}/quotes/latest`,
        { headers: this.headers }
      );

      if (!response.ok) return null;

      const data = await response.json();
      return data.quote;
    } catch (error) {
      console.error(`Error fetching latest quote for ${symbol}:`, error);
      return null;
    }
  }

  async getBars(symbol: string, timeframe: string = '1Day', limit: number = 100): Promise<AlpacaBar[]> {
    try {
      const response = await fetch(
        `${ALPACA_DATA_URL}/stocks/${symbol}/bars?timeframe=${timeframe}&limit=${limit}`,
        { headers: this.headers }
      );

      if (!response.ok) return [];

      const data = await response.json();
      return data.bars || [];
    } catch (error) {
      console.error(`Error fetching bars for ${symbol}:`, error);
      return [];
    }
  }
}

export const alpacaService = new AlpacaService();
export type { StockQuote, AlpacaQuote, AlpacaBar, AlpacaSnapshot };
