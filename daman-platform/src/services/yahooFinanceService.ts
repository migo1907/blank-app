interface YahooOptionContract {
  contractSymbol: string;
  strike: number;
  currency: string;
  lastPrice: number;
  change: number;
  percentChange: number;
  volume: number;
  openInterest: number;
  bid: number;
  ask: number;
  contractSize: string;
  expiration: number;
  lastTradeDate: number;
  impliedVolatility: number;
  inTheMoney: boolean;
}

interface YahooOptionsChain {
  calls: YahooOptionContract[];
  puts: YahooOptionContract[];
  expirationDate: number;
}

interface OptionsData {
  symbol: string;
  expirationDates: number[];
  strikes: number[];
  calls: YahooOptionContract[];
  puts: YahooOptionContract[];
}

interface SPXQuote {
  symbol: string;
  price: number;
  change: number;
  changePercent: number;
  volume: number;
  timestamp: number;
}

const YAHOO_FINANCE_BASE = 'https://query2.finance.yahoo.com';

class YahooFinanceService {
  private async fetchWithRetry(url: string, retries = 3): Promise<Response> {
    for (let i = 0; i < retries; i++) {
      try {
        const response = await fetch(url, {
          headers: {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
          }
        });

        if (response.ok) return response;

        if (i < retries - 1) {
          await new Promise(resolve => setTimeout(resolve, 1000 * (i + 1)));
        }
      } catch (error) {
        if (i === retries - 1) throw error;
        await new Promise(resolve => setTimeout(resolve, 1000 * (i + 1)));
      }
    }
    throw new Error('Max retries reached');
  }

  async getSPXQuote(): Promise<SPXQuote | null> {
    try {
      const response = await this.fetchWithRetry(
        `${YAHOO_FINANCE_BASE}/v8/finance/chart/%5ESPX?interval=1m&range=1d`
      );

      const data = await response.json();
      const result = data.chart?.result?.[0];

      if (!result) return null;

      const meta = result.meta;
      const quote = result.indicators?.quote?.[0];

      if (!meta || !quote) return null;

      const currentPrice = meta.regularMarketPrice || quote.close?.[quote.close.length - 1] || 0;
      const previousClose = meta.chartPreviousClose || meta.previousClose || currentPrice;
      const change = currentPrice - previousClose;
      const changePercent = previousClose > 0 ? (change / previousClose) * 100 : 0;

      return {
        symbol: '^SPX',
        price: currentPrice,
        change,
        changePercent,
        volume: meta.regularMarketVolume || 0,
        timestamp: Date.now()
      };
    } catch (error) {
      console.error('Error fetching SPX quote from Yahoo:', error);
      return null;
    }
  }

  async getOptionsChain(symbol: string, expirationDate?: number): Promise<OptionsData | null> {
    try {
      const dateParam = expirationDate ? `&date=${Math.floor(expirationDate / 1000)}` : '';
      const url = `${YAHOO_FINANCE_BASE}/v7/finance/options/${symbol}?${dateParam}`;

      const response = await this.fetchWithRetry(url);
      const data = await response.json();

      const result = data.optionChain?.result?.[0];
      if (!result) return null;

      const options = result.options?.[0];
      if (!options) return null;

      return {
        symbol,
        expirationDates: result.expirationDates || [],
        strikes: result.strikes || [],
        calls: options.calls || [],
        puts: options.puts || []
      };
    } catch (error) {
      console.error(`Error fetching options chain for ${symbol}:`, error);
      return null;
    }
  }

  async getSPXOptionsChain(expirationDate?: number): Promise<OptionsData | null> {
    return this.getOptionsChain('^SPX', expirationDate);
  }

  async getStockOptionsChain(symbol: string, expirationDate?: number): Promise<OptionsData | null> {
    return this.getOptionsChain(symbol, expirationDate);
  }

  async getMultipleSPXExpirations(numberOfExpirations: number = 5): Promise<OptionsData[]> {
    try {
      const firstChain = await this.getSPXOptionsChain();
      if (!firstChain || !firstChain.expirationDates.length) return [];

      const expirations = firstChain.expirationDates.slice(0, numberOfExpirations);
      const chains = await Promise.all(
        expirations.map(exp => this.getSPXOptionsChain(exp * 1000))
      );

      return chains.filter((chain): chain is OptionsData => chain !== null);
    } catch (error) {
      console.error('Error fetching multiple SPX expirations:', error);
      return [];
    }
  }

  findATMOptions(optionsData: OptionsData, currentPrice: number): {
    atmCall: YahooOptionContract | null;
    atmPut: YahooOptionContract | null;
    atmStrike: number;
  } {
    const strikes = optionsData.strikes.sort((a, b) => a - b);
    let atmStrike = strikes[0];
    let minDiff = Math.abs(strikes[0] - currentPrice);

    for (const strike of strikes) {
      const diff = Math.abs(strike - currentPrice);
      if (diff < minDiff) {
        minDiff = diff;
        atmStrike = strike;
      }
    }

    const atmCall = optionsData.calls.find(c => c.strike === atmStrike) || null;
    const atmPut = optionsData.puts.find(p => p.strike === atmStrike) || null;

    return { atmCall, atmPut, atmStrike };
  }

  calculateImpliedMove(atmCall: YahooOptionContract | null, atmPut: YahooOptionContract | null, currentPrice: number): {
    impliedMove: number;
    impliedMovePercent: number;
  } {
    if (!atmCall || !atmPut) {
      return { impliedMove: 0, impliedMovePercent: 0 };
    }

    const straddlePrice = atmCall.lastPrice + atmPut.lastPrice;
    const impliedMove = straddlePrice;
    const impliedMovePercent = currentPrice > 0 ? (impliedMove / currentPrice) * 100 : 0;

    return { impliedMove, impliedMovePercent };
  }

  async getStockQuote(symbol: string): Promise<SPXQuote | null> {
    try {
      const response = await this.fetchWithRetry(
        `${YAHOO_FINANCE_BASE}/v8/finance/chart/${symbol}?interval=1m&range=1d`
      );

      const data = await response.json();
      const result = data.chart?.result?.[0];

      if (!result) return null;

      const meta = result.meta;
      const quote = result.indicators?.quote?.[0];

      if (!meta || !quote) return null;

      const currentPrice = meta.regularMarketPrice || quote.close?.[quote.close.length - 1] || 0;
      const previousClose = meta.chartPreviousClose || meta.previousClose || currentPrice;
      const change = currentPrice - previousClose;
      const changePercent = previousClose > 0 ? (change / previousClose) * 100 : 0;

      return {
        symbol,
        price: currentPrice,
        change,
        changePercent,
        volume: meta.regularMarketVolume || 0,
        timestamp: Date.now()
      };
    } catch (error) {
      console.error(`Error fetching quote for ${symbol}:`, error);
      return null;
    }
  }

  async getMultipleQuotes(symbols: string[]): Promise<SPXQuote[]> {
    const quotes: SPXQuote[] = [];

    for (const symbol of symbols) {
      try {
        await new Promise(resolve => setTimeout(resolve, 100));
        const quote = await this.getStockQuote(symbol);
        if (quote) {
          quotes.push(quote);
        }
      } catch (error) {
        console.error(`Error fetching quote for ${symbol}:`, error);
      }
    }

    return quotes;
  }
}

export const yahooFinanceService = new YahooFinanceService();
export type { YahooOptionContract, YahooOptionsChain, OptionsData, SPXQuote };
