interface MarketQuote {
  symbol: string;
  name: string;
  price: number;
  change: number;
  changePercent: number;
  timestamp: number;
}

interface MarketDataResponse {
  success: boolean;
  data?: MarketQuote[];
  error?: string;
  timestamp: number;
}

const SYMBOL_MAP: Record<string, string> = {
  'S&P 500': '^GSPC',
  'Nasdaq': '^IXIC',
  'Dow Jones': '^DJI',
  'VIX': '^VIX'
};

const FALLBACK_DATA: Record<string, MarketQuote> = {
  'S&P 500': {
    symbol: '^GSPC',
    name: 'S&P 500',
    price: 6711.20,
    change: 22.74,
    changePercent: 0.34,
    timestamp: Date.now()
  },
  'Nasdaq': {
    symbol: '^IXIC',
    name: 'Nasdaq',
    price: 22691.69,
    change: 31.68,
    changePercent: 0.14,
    timestamp: Date.now()
  },
  'Dow Jones': {
    symbol: '^DJI',
    name: 'Dow Jones',
    price: 46441.10,
    change: 43.21,
    changePercent: 0.09,
    timestamp: Date.now()
  },
  'VIX': {
    symbol: '^VIX',
    name: 'VIX',
    price: 16.14,
    change: 0.19,
    changePercent: 1.18,
    timestamp: Date.now()
  }
};

class MarketDataService {
  private cache: Map<string, { data: MarketQuote; timestamp: number }> = new Map();
  private readonly CACHE_DURATION = 60000; // 1 minute cache
  private readonly supabaseUrl: string;
  private readonly supabaseKey: string;

  constructor() {
    this.supabaseUrl = import.meta.env.VITE_SUPABASE_URL || '';
    this.supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY || '';
  }

  private isCacheValid(timestamp: number): boolean {
    return Date.now() - timestamp < this.CACHE_DURATION;
  }

  private getCachedData(name: string): MarketQuote | null {
    const cached = this.cache.get(name);
    if (cached && this.isCacheValid(cached.timestamp)) {
      return cached.data;
    }
    return null;
  }

  private setCachedData(name: string, data: MarketQuote): void {
    this.cache.set(name, { data, timestamp: Date.now() });
  }

  async fetchMarketData(indicatorNames: string[]): Promise<Map<string, MarketQuote>> {
    const result = new Map<string, MarketQuote>();
    const symbolsToFetch: string[] = [];
    const namesToFetch: string[] = [];

    for (const name of indicatorNames) {
      const cached = this.getCachedData(name);
      if (cached) {
        result.set(name, cached);
      } else {
        const symbol = SYMBOL_MAP[name];
        if (symbol) {
          symbolsToFetch.push(symbol);
          namesToFetch.push(name);
        }
      }
    }

    if (symbolsToFetch.length === 0) {
      return result;
    }

    try {
      const apiUrl = `${this.supabaseUrl}/functions/v1/fetch-market-data?symbols=${symbolsToFetch.join(',')}`;

      const response = await fetch(apiUrl, {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${this.supabaseKey}`,
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        throw new Error(`API request failed: ${response.status}`);
      }

      const data: MarketDataResponse = await response.json();

      if (data.success && data.data) {
        data.data.forEach((quote, index) => {
          const name = namesToFetch.find(n => SYMBOL_MAP[n] === quote.symbol) || namesToFetch[index];
          const formattedQuote = {
            ...quote,
            name: name
          };
          result.set(name, formattedQuote);
          this.setCachedData(name, formattedQuote);
        });
      } else {
        throw new Error(data.error || 'Failed to fetch market data');
      }
    } catch (error) {
      console.warn('Failed to fetch real market data, using fallback:', error);

      namesToFetch.forEach(name => {
        if (!result.has(name) && FALLBACK_DATA[name]) {
          result.set(name, {
            ...FALLBACK_DATA[name],
            timestamp: Date.now()
          });
        }
      });
    }

    return result;
  }

  clearCache(): void {
    this.cache.clear();
  }
}

export const marketDataService = new MarketDataService();
export type { MarketQuote };
