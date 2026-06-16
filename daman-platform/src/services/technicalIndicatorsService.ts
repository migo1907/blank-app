export interface TechnicalIndicators {
  rsi14: number;
  macd: number;
  macdSignal: number;
  macdHistogram: number;
  sma20: number;
  sma50: number;
  sma200: number;
  ema12: number;
  ema26: number;
  bbUpper: number;
  bbMiddle: number;
  bbLower: number;
  signal: 'strong_buy' | 'buy' | 'neutral' | 'sell' | 'strong_sell';
}

export interface PriceData {
  close: number;
  high?: number;
  low?: number;
  timestamp: Date;
}

class TechnicalIndicatorsService {
  calculateRSI(prices: number[], period: number = 14): number {
    if (prices.length < period + 1) return 50;

    let gains = 0;
    let losses = 0;

    for (let i = prices.length - period; i < prices.length; i++) {
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

    return Math.round(rsi * 100) / 100;
  }

  calculateSMA(prices: number[], period: number): number {
    if (prices.length < period) return prices[prices.length - 1] || 0;

    const slice = prices.slice(-period);
    const sum = slice.reduce((acc, price) => acc + price, 0);
    return Math.round((sum / period) * 100) / 100;
  }

  calculateEMA(prices: number[], period: number): number {
    if (prices.length < period) return this.calculateSMA(prices, period);

    const multiplier = 2 / (period + 1);
    let ema = this.calculateSMA(prices.slice(0, period), period);

    for (let i = period; i < prices.length; i++) {
      ema = (prices[i] - ema) * multiplier + ema;
    }

    return Math.round(ema * 100) / 100;
  }

  calculateMACD(prices: number[]): { macd: number; signal: number; histogram: number } {
    const ema12 = this.calculateEMA(prices, 12);
    const ema26 = this.calculateEMA(prices, 26);
    const macd = ema12 - ema26;

    const macdLine: number[] = [];
    for (let i = 26; i <= prices.length; i++) {
      const slice = prices.slice(0, i);
      const e12 = this.calculateEMA(slice, 12);
      const e26 = this.calculateEMA(slice, 26);
      macdLine.push(e12 - e26);
    }

    const signal = this.calculateEMA(macdLine, 9);
    const histogram = macd - signal;

    return {
      macd: Math.round(macd * 100) / 100,
      signal: Math.round(signal * 100) / 100,
      histogram: Math.round(histogram * 100) / 100,
    };
  }

  calculateBollingerBands(prices: number[], period: number = 20, stdDev: number = 2): {
    upper: number;
    middle: number;
    lower: number;
  } {
    const middle = this.calculateSMA(prices, period);

    if (prices.length < period) {
      return { upper: middle, middle, lower: middle };
    }

    const slice = prices.slice(-period);
    const squaredDiffs = slice.map(price => Math.pow(price - middle, 2));
    const variance = squaredDiffs.reduce((acc, val) => acc + val, 0) / period;
    const standardDeviation = Math.sqrt(variance);

    const upper = middle + (standardDeviation * stdDev);
    const lower = middle - (standardDeviation * stdDev);

    return {
      upper: Math.round(upper * 100) / 100,
      middle: Math.round(middle * 100) / 100,
      lower: Math.round(lower * 100) / 100,
    };
  }

  generateBuySignal(indicators: Partial<TechnicalIndicators>, currentPrice: number):
    'strong_buy' | 'buy' | 'neutral' | 'sell' | 'strong_sell' {
    let score = 0;

    if (indicators.rsi14) {
      if (indicators.rsi14 < 30) score += 2;
      else if (indicators.rsi14 < 40) score += 1;
      else if (indicators.rsi14 > 70) score -= 2;
      else if (indicators.rsi14 > 60) score -= 1;
    }

    if (indicators.macdHistogram) {
      if (indicators.macdHistogram > 0) score += 1;
      else score -= 1;
    }

    if (indicators.sma20 && indicators.sma50) {
      if (indicators.sma20 > indicators.sma50) score += 1;
      else score -= 1;
    }

    if (indicators.sma50 && indicators.sma200) {
      if (indicators.sma50 > indicators.sma200) score += 1;
      else score -= 1;
    }

    if (indicators.sma20 && currentPrice) {
      if (currentPrice > indicators.sma20) score += 1;
      else score -= 1;
    }

    if (indicators.bbLower && indicators.bbUpper && currentPrice) {
      if (currentPrice < indicators.bbLower) score += 1;
      else if (currentPrice > indicators.bbUpper) score -= 1;
    }

    if (score >= 4) return 'strong_buy';
    if (score >= 2) return 'buy';
    if (score <= -4) return 'strong_sell';
    if (score <= -2) return 'sell';
    return 'neutral';
  }

  calculateAllIndicators(prices: number[], currentPrice: number): TechnicalIndicators {
    const rsi14 = this.calculateRSI(prices, 14);
    const macd = this.calculateMACD(prices);
    const sma20 = this.calculateSMA(prices, 20);
    const sma50 = this.calculateSMA(prices, 50);
    const sma200 = this.calculateSMA(prices, 200);
    const ema12 = this.calculateEMA(prices, 12);
    const ema26 = this.calculateEMA(prices, 26);
    const bb = this.calculateBollingerBands(prices, 20, 2);

    const indicators: TechnicalIndicators = {
      rsi14,
      macd: macd.macd,
      macdSignal: macd.signal,
      macdHistogram: macd.histogram,
      sma20,
      sma50,
      sma200,
      ema12,
      ema26,
      bbUpper: bb.upper,
      bbMiddle: bb.middle,
      bbLower: bb.lower,
      signal: 'neutral',
    };

    indicators.signal = this.generateBuySignal(indicators, currentPrice);

    return indicators;
  }

  generateMockHistoricalPrices(currentPrice: number, days: number = 200): number[] {
    const prices: number[] = [];
    let price = currentPrice * 0.85;

    for (let i = 0; i < days; i++) {
      const change = (Math.random() - 0.48) * price * 0.02;
      price = Math.max(price + change, currentPrice * 0.5);
      prices.push(price);
    }

    prices[prices.length - 1] = currentPrice;
    return prices;
  }
}

export const technicalIndicatorsService = new TechnicalIndicatorsService();
