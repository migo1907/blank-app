export interface SPXQuote {
  symbol: string;
  price: number;
  change: number;
  changePercent: number;
  volume: number;
  high: number;
  low: number;
  open: number;
  previousClose: number;
  timestamp: number;
}

export interface SPXOptionsData {
  spotPrice: number;
  gammaFlip: number;
  maxPain: number;
  netGEX: number;
  callOI: number;
  putOI: number;
  putCallRatio: number;
  impliedVolatility: number;
  timestamp: number;
}

class SPXLiveDataService {
  private supabaseUrl: string;
  private supabaseKey: string;
  private updateInterval: number | null = null;
  private lastUpdate: number = 0;
  private readonly UPDATE_FREQUENCY = 1000;

  constructor() {
    this.supabaseUrl = import.meta.env.VITE_SUPABASE_URL || '';
    this.supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY || '';
  }

  async fetchLiveSPXQuote(): Promise<SPXQuote> {
    try {
      const response = await fetch(
        `${this.supabaseUrl}/functions/v1/fetch-stock-data?symbols=SPY&mode=return`,
        {
          headers: {
            'Authorization': `Bearer ${this.supabaseKey}`,
            'Content-Type': 'application/json',
          },
        }
      );

      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }

      const result = await response.json();

      if (result.success && result.data && result.data.length > 0) {
        const quote = result.data[0];
        const spxPrice = quote.price * 10;
        return {
          symbol: 'SPX',
          price: spxPrice,
          change: (quote.change || 0) * 10,
          changePercent: quote.changePercent || 0,
          volume: quote.volume || 0,
          high: (quote.high || quote.price) * 10,
          low: (quote.low || quote.price) * 10,
          open: (quote.open || quote.price) * 10,
          previousClose: spxPrice - ((quote.change || 0) * 10),
          timestamp: Date.now()
        };
      }

      throw new Error('No data returned from API');
    } catch (error) {
      console.error('Error fetching live SPX quote:', error);
      throw error;
    }
  }

  async fetchSPXOptionsData(): Promise<SPXOptionsData> {
    try {
      const spxQuote = await this.fetchLiveSPXQuote();

      const gammaFlip = this.calculateGammaFlip(spxQuote.price);
      const maxPain = this.calculateMaxPain(spxQuote.price);
      const netGEX = this.calculateNetGEX(spxQuote.price, gammaFlip);

      return {
        spotPrice: spxQuote.price,
        gammaFlip,
        maxPain,
        netGEX,
        callOI: 0,
        putOI: 0,
        putCallRatio: 1.0,
        impliedVolatility: 15.0,
        timestamp: Date.now()
      };
    } catch (error) {
      console.error('Error fetching SPX options data:', error);
      throw error;
    }
  }

  private calculateGammaFlip(spotPrice: number): number {
    const nearestStrike = Math.round(spotPrice / 50) * 50;
    return nearestStrike + 10;
  }

  private calculateMaxPain(spotPrice: number): number {
    const nearestStrike = Math.round(spotPrice / 50) * 50;
    return nearestStrike - 10;
  }

  private calculateNetGEX(spotPrice: number, gammaFlip: number): number {
    if (spotPrice > gammaFlip) {
      return Math.abs(spotPrice - gammaFlip) / 100 + 0.5;
    } else {
      return -(Math.abs(spotPrice - gammaFlip) / 100 + 0.5);
    }
  }

  startRealtimeUpdates(callback: (data: SPXOptionsData) => void): void {
    this.stopRealtimeUpdates();

    const update = async () => {
      const now = Date.now();
      if (now - this.lastUpdate < this.UPDATE_FREQUENCY) {
        return;
      }

      try {
        const data = await this.fetchSPXOptionsData();
        this.lastUpdate = now;
        callback(data);
      } catch (error) {
        console.error('Real-time update error:', error);
      }
    };

    update();

    this.updateInterval = window.setInterval(update, this.UPDATE_FREQUENCY);
  }

  stopRealtimeUpdates(): void {
    if (this.updateInterval !== null) {
      clearInterval(this.updateInterval);
      this.updateInterval = null;
    }
  }

  async fetchHistoricalPrices(symbol: string, period: string = '1d'): Promise<number[]> {
    try {
      const response = await fetch(
        `https://query1.finance.yahoo.com/v8/finance/chart/${symbol}?interval=5m&range=${period}`,
        {
          headers: {
            'User-Agent': 'Mozilla/5.0',
          },
        }
      );

      if (!response.ok) {
        throw new Error(`Yahoo Finance API error: ${response.status}`);
      }

      const data = await response.json();
      const result = data.chart?.result?.[0];

      if (!result || !result.indicators?.quote?.[0]?.close) {
        return [];
      }

      return result.indicators.quote[0].close.filter((price: number | null) => price !== null);
    } catch (error) {
      console.error('Error fetching historical prices:', error);
      return [];
    }
  }

  calculateVWAP(prices: number[], volumes: number[]): number {
    if (prices.length === 0 || volumes.length === 0 || prices.length !== volumes.length) {
      return 0;
    }

    let sumPriceVolume = 0;
    let sumVolume = 0;

    for (let i = 0; i < prices.length; i++) {
      sumPriceVolume += prices[i] * volumes[i];
      sumVolume += volumes[i];
    }

    return sumVolume > 0 ? sumPriceVolume / sumVolume : 0;
  }

  calculateEMA(prices: number[], period: number): number {
    if (prices.length === 0) return 0;
    if (prices.length < period) return prices[prices.length - 1];

    const multiplier = 2 / (period + 1);
    let ema = prices[0];

    for (let i = 1; i < prices.length; i++) {
      ema = (prices[i] - ema) * multiplier + ema;
    }

    return ema;
  }

  calculateRSI(prices: number[], period: number = 14): number {
    if (prices.length < period + 1) return 50;

    let gains = 0;
    let losses = 0;

    for (let i = 1; i <= period; i++) {
      const change = prices[i] - prices[i - 1];
      if (change > 0) {
        gains += change;
      } else {
        losses -= change;
      }
    }

    const avgGain = gains / period;
    const avgLoss = losses / period;

    if (avgLoss === 0) return 100;

    const rs = avgGain / avgLoss;
    const rsi = 100 - (100 / (1 + rs));

    return rsi;
  }
}

export const spxLiveDataService = new SPXLiveDataService();
