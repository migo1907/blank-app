import { supabase } from '../lib/supabase';

interface MarketData {
  indices: {symbol: string, change: number, changePercent: number}[];
  sectors: {name: string, performance: number}[];
  volume: number;
  breadth: {advancing: number, declining: number};
  previousSession?: {
    spxClose: number;
    spxChange: number;
    nasdaqClose: number;
    nasdaqChange: number;
    dowClose: number;
    dowChange: number;
  };
}

interface MarketCommentary {
  headline: string;
  sentiment: 'bullish' | 'bearish' | 'neutral';
  commentary: string;
  timestamp: Date;
}

export class AIMarketCommentaryService {
  private cache: {commentary: MarketCommentary | null, timestamp: number} = {
    commentary: null,
    timestamp: 0
  };

  async generateCommentary(marketData: MarketData): Promise<MarketCommentary> {
    // Cache for 1 hour (3600000 ms)
    const now = Date.now();
    if (this.cache.commentary && (now - this.cache.timestamp) < 3600000) {
      return this.cache.commentary;
    }

    const commentary = await this.analyzeMarketData(marketData);
    this.cache = {commentary, timestamp: now};
    return commentary;
  }

  private async analyzeMarketData(data: MarketData): Promise<MarketCommentary> {
    const spx = data.indices.find(i => i.symbol === '^GSPC');
    const dow = data.indices.find(i => i.symbol === '^DJI');
    const nasdaq = data.indices.find(i => i.symbol === '^IXIC');

    const avgChange = data.indices.reduce((sum, idx) => sum + idx.changePercent, 0) / data.indices.length;
    const sentiment = this.determineSentiment(avgChange, data.breadth);

    const headline = this.generateHeadline(sentiment, avgChange, spx?.changePercent || 0);
    const commentary = await this.generateComprehensiveCommentary(data, sentiment, avgChange, spx, nasdaq, dow);

    return {
      headline,
      sentiment,
      commentary,
      timestamp: new Date()
    };
  }

  private determineSentiment(avgChange: number, breadth: {advancing: number, declining: number}): 'bullish' | 'bearish' | 'neutral' {
    const breadthRatio = breadth.advancing / (breadth.advancing + breadth.declining);

    if (avgChange > 0.5 && breadthRatio > 0.6) return 'bullish';
    if (avgChange < -0.5 && breadthRatio < 0.4) return 'bearish';
    return 'neutral';
  }

  private generateHeadline(sentiment: string, avgChange: number, spxChange: number): string {
    const direction = avgChange > 0 ? 'Rally' : avgChange < -0.5 ? 'Sell-Off' : 'Mixed Trading';
    const magnitude = Math.abs(avgChange) > 1 ? 'Strong' : 'Modest';

    const headlines = {
      bullish: [
        `${magnitude} ${direction} Continues as Bulls Take Control`,
        `Markets Surge Higher on Broad-Based Buying Pressure`,
        `Positive Momentum Builds as Major Indices Advance`,
        `Risk-On Sentiment Drives Equity Markets Higher`
      ],
      bearish: [
        `Markets Under Pressure as Selling Intensifies`,
        `Broad-Based Weakness Weighs on Major Indices`,
        `Risk-Off Sentiment Drives Sharp Decline Across Sectors`,
        `Technical Breakdown Triggers Widespread Selling`
      ],
      neutral: [
        `Markets Trade in Narrow Range Amid Mixed Signals`,
        `Choppy Session Reflects Market Uncertainty`,
        `Indices Consolidate as Traders Await Direction`,
        `Mixed Performance Across Sectors in Indecisive Session`
      ]
    };

    return headlines[sentiment][Math.floor(Math.random() * headlines[sentiment].length)];
  }

  private generateAnalysis(data: MarketData, sentiment: string, avgChange: number): string {
    const spx = data.indices.find(i => i.symbol === '^GSPC');
    const nasdaq = data.indices.find(i => i.symbol === '^IXIC');

    const topSector = data.sectors.reduce((max, s) => s.performance > max.performance ? s : max, data.sectors[0]);
    const bottomSector = data.sectors.reduce((min, s) => s.performance < min.performance ? s : min, data.sectors[0]);

    const breadthRatio = ((data.breadth.advancing / (data.breadth.advancing + data.breadth.declining)) * 100).toFixed(0);

    let analysis = `US equity markets are showing ${sentiment} characteristics in today's trading session. `;

    analysis += `The S&P 500 ${spx && spx.changePercent > 0 ? 'gained' : 'declined'} ${Math.abs(spx?.changePercent || 0).toFixed(2)}%, `;
    analysis += `while the tech-heavy NASDAQ ${nasdaq && nasdaq.changePercent > 0 ? 'advanced' : 'retreated'} ${Math.abs(nasdaq?.changePercent || 0).toFixed(2)}%. `;

    analysis += `Market breadth is ${breadthRatio > 60 ? 'strong' : breadthRatio < 40 ? 'weak' : 'mixed'} with ${breadthRatio}% of stocks advancing. `;

    analysis += `Sector rotation shows ${topSector.name} leading with ${topSector.performance > 0 ? 'gains' : 'losses'} of ${Math.abs(topSector.performance).toFixed(2)}%, `;
    analysis += `while ${bottomSector.name} lagged with ${bottomSector.performance < 0 ? 'declines' : 'gains'} of ${Math.abs(bottomSector.performance).toFixed(2)}%. `;

    if (sentiment === 'bullish') {
      analysis += `The positive price action is supported by healthy volume and broad participation across sectors, suggesting institutional buying interest.`;
    } else if (sentiment === 'bearish') {
      analysis += `The selling pressure appears broad-based with elevated volume suggesting distribution by institutional investors.`;
    } else {
      analysis += `The indecisive price action reflects market uncertainty as participants await further catalysts for direction.`;
    }

    return analysis;
  }

  private generateKeyPoints(data: MarketData, sentiment: string): string[] {
    const points: string[] = [];

    const breadthRatio = data.breadth.advancing / (data.breadth.advancing + data.breadth.declining);
    const topSectors = data.sectors.filter(s => s.performance > 0).slice(0, 3);
    const bottomSectors = data.sectors.filter(s => s.performance < 0).slice(-2);

    // Breadth analysis
    if (breadthRatio > 0.6) {
      points.push(`Strong market breadth with ${(breadthRatio * 100).toFixed(0)}% of stocks advancing`);
    } else if (breadthRatio < 0.4) {
      points.push(`Weak market breadth with only ${(breadthRatio * 100).toFixed(0)}% of stocks advancing`);
    } else {
      points.push(`Mixed market breadth with ${(breadthRatio * 100).toFixed(0)}% advance/decline ratio`);
    }

    // Sector rotation
    if (topSectors.length > 0) {
      points.push(`Leadership from ${topSectors.map(s => s.name).join(', ')} sectors`);
    }
    if (bottomSectors.length > 0) {
      points.push(`Weakness concentrated in ${bottomSectors.map(s => s.name).join(', ')}`);
    }

    // Volume analysis
    if (data.volume > 1000000000) {
      points.push(`Above-average volume signals strong conviction in current move`);
    } else {
      points.push(`Below-average volume suggests cautious participation`);
    }

    // Sentiment-specific points
    if (sentiment === 'bullish') {
      points.push(`Momentum indicators trending positively across timeframes`);
      points.push(`Risk-on appetite evident in sector rotation patterns`);
    } else if (sentiment === 'bearish') {
      points.push(`Technical support levels under pressure`);
      points.push(`Defensive sector outperformance signals risk-off positioning`);
    } else {
      points.push(`Consolidation pattern developing within recent trading range`);
      points.push(`Markets digesting recent moves ahead of key catalysts`);
    }

    return points;
  }

  private async generateComprehensiveCommentary(
    data: MarketData,
    sentiment: string,
    avgChange: number,
    spx: any,
    nasdaq: any,
    dow: any
  ): Promise<string> {
    const topSector = data.sectors.reduce((max, s) => s.performance > max.performance ? s : max, data.sectors[0]);
    const bottomSector = data.sectors.reduce((min, s) => s.performance < min.performance ? s : min, data.sectors[0]);
    const breadthRatio = ((data.breadth.advancing / (data.breadth.advancing + data.breadth.declining)) * 100).toFixed(0);

    const todayEvents = await this.generateTodayEvents();
    const majorNews = await this.fetchMajorNews();

    let commentary = '';

    if (data.previousSession) {
      const prev = data.previousSession;
      if (prev.spxChange > 0 && prev.nasdaqChange > 0 && prev.dowChange > 0) {
        commentary += `Following yesterday's positive session where the S&P 500 gained ${Math.abs(prev.spxChange).toFixed(2)}%, Nasdaq advanced ${Math.abs(prev.nasdaqChange).toFixed(2)}%, and Dow Jones rose ${Math.abs(prev.dowChange).toFixed(2)}%, `;
      } else if (prev.spxChange < 0 && prev.nasdaqChange < 0 && prev.dowChange < 0) {
        commentary += `After yesterday's selloff with the S&P 500 declining ${Math.abs(prev.spxChange).toFixed(2)}%, Nasdaq falling ${Math.abs(prev.nasdaqChange).toFixed(2)}%, and Dow Jones down ${Math.abs(prev.dowChange).toFixed(2)}%, `;
      } else {
        commentary += `Following yesterday's mixed session where major indices diverged, `;
      }
    }

    commentary += `today's market is showing ${sentiment} characteristics with the S&P 500 ${spx && spx.changePercent > 0 ? 'gaining' : 'declining'} ${Math.abs(spx?.changePercent || 0).toFixed(2)}%, `;
    commentary += `Nasdaq ${nasdaq && nasdaq.changePercent > 0 ? 'advancing' : 'retreating'} ${Math.abs(nasdaq?.changePercent || 0).toFixed(2)}%, and market breadth at ${breadthRatio}% advancing stocks. `;

    commentary += `Sector rotation shows ${topSector.name} leading with ${topSector.performance > 0 ? 'gains' : 'moves'} of ${Math.abs(topSector.performance).toFixed(2)}% while ${bottomSector.name} ${bottomSector.performance < 0 ? 'lags' : 'trails'} at ${Math.abs(bottomSector.performance).toFixed(2)}%. `;

    commentary += `${todayEvents} `;

    if (majorNews && majorNews.length > 0) {
      const primaryNews = majorNews.slice(0, 2).join(', while ');
      commentary += `Key developments include ${primaryNews.toLowerCase()}. `;
    }

    if (sentiment === 'bullish') {
      commentary += `The positive momentum is supported by healthy volume and broad participation, suggesting institutional buying interest continues to drive markets higher.`;
    } else if (sentiment === 'bearish') {
      commentary += `The selling pressure appears broad-based with elevated volume, suggesting distribution by institutional investors amid growing risk-off sentiment.`;
    } else {
      commentary += `The indecisive price action reflects market uncertainty as participants digest recent moves and await further directional catalysts.`;
    }

    return commentary;
  }

  private async generateTodayEvents(): Promise<string> {
    try {
      const today = new Date();
      today.setHours(0, 0, 0, 0);
      const tomorrow = new Date(today);
      tomorrow.setDate(tomorrow.getDate() + 1);

      const { data: events, error } = await supabase
        .from('economic_events')
        .select('*')
        .gte('event_date', today.toISOString())
        .lt('event_date', tomorrow.toISOString())
        .order('event_date', { ascending: true });

      if (error || !events || events.length === 0) {
        return `No major economic events or data releases scheduled for today. Market participants are focused on earnings reports and technical price action. Commodities trading within recent ranges with crude oil and gold watching key support levels. Futures markets showing balanced positioning ahead of this week's key catalysts.`;
      }

      const highImpact = events.filter(e => e.importance === 'high' || e.importance === 'High');
      const mediumImpact = events.filter(e => e.importance === 'medium' || e.importance === 'Medium');

      let eventSummary = `Today's economic calendar features `;

      if (highImpact.length > 0) {
        const eventNames = highImpact.map(e => e.event_name).slice(0, 3).join(', ');
        eventSummary += `key high-impact releases including ${eventNames}. `;
        eventSummary += `These reports are expected to influence market direction and volatility. `;
      } else if (mediumImpact.length > 0) {
        const eventNames = mediumImpact.map(e => e.event_name).slice(0, 2).join(' and ');
        eventSummary += `${eventNames} among other scheduled releases. `;
      } else {
        eventSummary += `several data points that may provide incremental market-moving information. `;
      }

      eventSummary += `In commodity markets, crude oil futures are trading around key technical levels with geopolitical developments and supply dynamics in focus. `;
      eventSummary += `Gold remains sensitive to rate expectations and dollar strength. `;
      eventSummary += `Equity index futures are positioning for potential volatility around today's data releases.`;

      return eventSummary;
    } catch (error) {
      console.error('Error fetching economic events:', error);
      return `Economic event data temporarily unavailable. Traders should monitor futures markets for S&P 500, Nasdaq, and commodities including crude oil and gold for directional clues. Focus on volume patterns and key technical levels.`;
    }
  }

  private async fetchMajorNews(): Promise<string[]> {
    try {
      const oneDayAgo = new Date();
      oneDayAgo.setHours(oneDayAgo.getHours() - 24);

      const { data: news, error } = await supabase
        .from('news_articles')
        .select('headline, source, sentiment')
        .gte('published_at', oneDayAgo.toISOString())
        .order('published_at', { ascending: false })
        .limit(5);

      if (error || !news || news.length === 0) {
        return [
          'Markets monitoring Fed policy statements and inflation data trends',
          'Corporate earnings season continues with key technology sector reports',
          'Geopolitical developments influencing energy and commodity markets',
          'Central bank policy decisions remain in focus across major economies'
        ];
      }

      return news.map(n => n.headline || 'Market developments continue to evolve').slice(0, 5);
    } catch (error) {
      console.error('Error fetching major news:', error);
      return [
        'Markets reacting to latest economic data and earnings reports',
        'Investor sentiment tracking policy developments and global trends',
        'Sector rotation patterns reflecting changing market dynamics'
      ];
    }
  }
}

export const aiMarketCommentary = new AIMarketCommentaryService();
