
interface OptionData {
  symbol: string;
  strike: number;
  bid: number;
  ask: number;
  last: number;
  volume: number;
  openInterest: number;
  iv: number;
  delta: number;
  gamma: number;
  theta: number;
  vega: number;
  expiration: string;
}

export interface PolygonOptionsChainResponse {
  underlying: string;
  underlyingPrice: number;
  calls: OptionData[];
  puts: OptionData[];
}

export interface PolygonStockData {
  symbol: string;
  price: number;
  change: number;
  changePercent: number;
  volume: number;
  high: number;
  low: number;
  open: number;
  previousClose: number;
  marketCap?: number;
}

class PolygonService {
  private baseUrl = 'https://api.polygon.io';

  private async fetchWithAuth(url: string): Promise<any> {
    const apiKey = import.meta.env.VITE_POLYGON_API_KEY;

    if (!apiKey || apiKey === 'YOUR_POLYGON_API_KEY_HERE') {
      throw new Error('Polygon.io API key not configured');
    }

    const separator = url.includes('?') ? '&' : '?';
    const fullUrl = `${url}${separator}apiKey=${apiKey}`;

    const response = await fetch(fullUrl);

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Polygon API error: ${response.status} - ${errorText}`);
    }

    return response.json();
  }

  async getOptionsChain(symbol: string): Promise<PolygonOptionsChainResponse> {
    const contractsUrl = `${this.baseUrl}/v3/reference/options/contracts?underlying_ticker=${symbol}&limit=1000`;
    const contractsData = await this.fetchWithAuth(contractsUrl);

    if (!contractsData.results || contractsData.results.length === 0) {
      throw new Error(`No options contracts found for ${symbol}`);
    }

    const underlyingQuote = await this.getStockQuote(symbol);
    const underlyingPrice = underlyingQuote.price;

    const expirationDates = [...new Set(contractsData.results.map((c: any) => c.expiration_date))];
    const nearestExpiration = expirationDates.sort()[0];

    const relevantContracts = contractsData.results.filter(
      (c: any) => c.expiration_date === nearestExpiration
    );

    const optionsWithQuotes = await Promise.all(
      relevantContracts.slice(0, 50).map(async (contract: any) => {
        try {
          const snapshotUrl = `${this.baseUrl}/v3/snapshot/options/${contract.ticker}`;
          const snapshot = await this.fetchWithAuth(snapshotUrl);

          return {
            ...contract,
            last_quote: snapshot.results?.last_quote,
            greeks: snapshot.results?.greeks,
            implied_volatility: snapshot.results?.implied_volatility,
            open_interest: snapshot.results?.open_interest,
            volume: snapshot.results?.day?.volume || 0
          };
        } catch (error) {
          console.warn(`Failed to fetch snapshot for ${contract.ticker}:`, error);
          return contract;
        }
      })
    );

    const calls: OptionData[] = [];
    const puts: OptionData[] = [];

    optionsWithQuotes.forEach((contract: any) => {
      const optionData: OptionData = {
        symbol: contract.ticker,
        strike: contract.strike_price,
        bid: contract.last_quote?.bid || 0,
        ask: contract.last_quote?.ask || 0,
        last: contract.last_quote?.last || 0,
        volume: contract.volume || 0,
        openInterest: contract.open_interest || 0,
        iv: contract.implied_volatility || 0,
        delta: contract.greeks?.delta || 0,
        gamma: contract.greeks?.gamma || 0,
        theta: contract.greeks?.theta || 0,
        vega: contract.greeks?.vega || 0,
        expiration: contract.expiration_date
      };

      if (contract.contract_type === 'call') {
        calls.push(optionData);
      } else {
        puts.push(optionData);
      }
    });

    return {
      underlying: symbol,
      underlyingPrice,
      calls: calls.sort((a, b) => a.strike - b.strike),
      puts: puts.sort((a, b) => a.strike - b.strike)
    };
  }

  async getStockQuote(symbol: string): Promise<PolygonStockData> {
    const url = `${this.baseUrl}/v2/snapshot/locale/us/markets/stocks/tickers/${symbol}`;
    const data = await this.fetchWithAuth(url);

    if (!data.ticker) {
      throw new Error(`No data found for ${symbol}`);
    }

    const ticker = data.ticker;
    const quote = ticker.day;
    const prevClose = ticker.prevDay?.c || quote.c;
    const currentPrice = quote.c || ticker.lastTrade?.p || 0;
    const change = currentPrice - prevClose;
    const changePercent = prevClose ? (change / prevClose) * 100 : 0;

    return {
      symbol: ticker.ticker,
      price: currentPrice,
      change,
      changePercent,
      volume: quote.v || 0,
      high: quote.h || 0,
      low: quote.l || 0,
      open: quote.o || 0,
      previousClose: prevClose
    };
  }

  async getMultipleStockQuotes(symbols: string[]): Promise<PolygonStockData[]> {
    const quotes = await Promise.all(
      symbols.map(async (symbol) => {
        try {
          return await this.getStockQuote(symbol);
        } catch (error) {
          console.warn(`Failed to fetch quote for ${symbol}:`, error);
          return null;
        }
      })
    );

    return quotes.filter((q): q is PolygonStockData => q !== null);
  }

  async getLastTrade(symbol: string): Promise<{ price: number; timestamp: number }> {
    const url = `${this.baseUrl}/v2/last/trade/${symbol}`;
    const data = await this.fetchWithAuth(url);

    return {
      price: data.results?.p || 0,
      timestamp: data.results?.t || Date.now()
    };
  }

  async getAggregates(
    symbol: string,
    timespan: 'minute' | 'hour' | 'day',
    from: string,
    to: string
  ): Promise<any[]> {
    const url = `${this.baseUrl}/v2/aggs/ticker/${symbol}/range/1/${timespan}/${from}/${to}`;
    const data = await this.fetchWithAuth(url);
    return data.results || [];
  }
}

export const polygonService = new PolygonService();
