import { useEffect, useState } from 'react';
import { TrendingUp, TrendingDown, Minus, ThumbsUp, ThumbsDown } from 'lucide-react';

interface SentimentData {
  overall: 'bullish' | 'bearish' | 'neutral';
  score: number;
  bullish: number;
  bearish: number;
  neutral: number;
  fearGreedIndex: number;
  volatilityIndex: number;
  putCallRatio: number;
}

export default function MarketSentiment() {
  const [sentiment, setSentiment] = useState<SentimentData>({
    overall: 'neutral',
    score: 50,
    bullish: 45,
    bearish: 35,
    neutral: 20,
    fearGreedIndex: 52,
    volatilityIndex: 16.5,
    putCallRatio: 0.95,
  });

  useEffect(() => {
    fetchSentimentData();
    const interval = setInterval(fetchSentimentData, 300000);
    return () => clearInterval(interval);
  }, []);

  const fetchSentimentData = async () => {
    try {
      const mockData: SentimentData = {
        overall: Math.random() > 0.6 ? 'bullish' : Math.random() > 0.3 ? 'neutral' : 'bearish',
        score: Math.round(30 + Math.random() * 40),
        bullish: Math.round(30 + Math.random() * 30),
        bearish: Math.round(20 + Math.random() * 30),
        neutral: Math.round(10 + Math.random() * 20),
        fearGreedIndex: Math.round(30 + Math.random() * 40),
        volatilityIndex: Math.round((12 + Math.random() * 10) * 10) / 10,
        putCallRatio: Math.round((0.7 + Math.random() * 0.5) * 100) / 100,
      };
      setSentiment(mockData);
    } catch (error) {
      console.error('Error fetching sentiment data:', error);
    }
  };

  const getSentimentColor = (overall: string): string => {
    switch (overall) {
      case 'bullish': return 'text-green-600 bg-green-100';
      case 'bearish': return 'text-red-600 bg-red-100';
      default: return 'text-slate-600 bg-slate-100';
    }
  };

  const getSentimentIcon = (overall: string) => {
    switch (overall) {
      case 'bullish': return <ThumbsUp className="h-6 w-6" />;
      case 'bearish': return <ThumbsDown className="h-6 w-6" />;
      default: return <Minus className="h-6 w-6" />;
    }
  };

  const getFearGreedLabel = (score: number): string => {
    if (score >= 75) return 'Extreme Greed';
    if (score >= 55) return 'Greed';
    if (score >= 45) return 'Neutral';
    if (score >= 25) return 'Fear';
    return 'Extreme Fear';
  };

  const getFearGreedColor = (score: number): string => {
    if (score >= 75) return 'bg-green-600';
    if (score >= 55) return 'bg-green-500';
    if (score >= 45) return 'bg-yellow-500';
    if (score >= 25) return 'bg-orange-500';
    return 'bg-red-600';
  };

  return (
    <div className="bg-white rounded-xl shadow-md border border-slate-200 overflow-hidden">
      <div className="p-6 border-b border-slate-200">
        <h3 className="text-xl font-bold text-slate-900">Market Sentiment</h3>
        <p className="text-sm text-slate-600 mt-1">Real-time sentiment analysis</p>
      </div>

      <div className="p-6">
        {/* Overall Sentiment */}
        <div className="mb-6">
          <div className={`inline-flex items-center space-x-3 px-6 py-4 rounded-xl ${getSentimentColor(sentiment.overall)}`}>
            {getSentimentIcon(sentiment.overall)}
            <div>
              <div className="text-sm font-semibold uppercase tracking-wide">Overall Sentiment</div>
              <div className="text-2xl font-bold capitalize">{sentiment.overall}</div>
            </div>
          </div>
        </div>

        {/* Sentiment Breakdown */}
        <div className="space-y-4 mb-6">
          <div>
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center space-x-2">
                <TrendingUp className="h-4 w-4 text-green-600" />
                <span className="text-sm font-semibold text-slate-700">Bullish</span>
              </div>
              <span className="text-sm font-bold text-green-600">{sentiment.bullish}%</span>
            </div>
            <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
              <div className="h-full bg-green-500 rounded-full transition-all duration-500" style={{ width: `${sentiment.bullish}%` }}></div>
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center space-x-2">
                <TrendingDown className="h-4 w-4 text-red-600" />
                <span className="text-sm font-semibold text-slate-700">Bearish</span>
              </div>
              <span className="text-sm font-bold text-red-600">{sentiment.bearish}%</span>
            </div>
            <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
              <div className="h-full bg-red-500 rounded-full transition-all duration-500" style={{ width: `${sentiment.bearish}%` }}></div>
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center space-x-2">
                <Minus className="h-4 w-4 text-slate-600" />
                <span className="text-sm font-semibold text-slate-700">Neutral</span>
              </div>
              <span className="text-sm font-bold text-slate-600">{sentiment.neutral}%</span>
            </div>
            <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
              <div className="h-full bg-slate-400 rounded-full transition-all duration-500" style={{ width: `${sentiment.neutral}%` }}></div>
            </div>
          </div>
        </div>

        {/* Fear & Greed Index */}
        <div className="mb-6 p-4 bg-gradient-to-r from-red-50 via-yellow-50 to-green-50 rounded-lg">
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm font-semibold text-slate-700">Fear & Greed Index</span>
            <span className="text-2xl font-bold text-slate-900">{sentiment.fearGreedIndex}</span>
          </div>
          <div className="relative h-3 bg-gradient-to-r from-red-600 via-yellow-500 to-green-600 rounded-full">
            <div
              className="absolute top-1/2 -translate-y-1/2 w-4 h-4 bg-white border-2 border-slate-700 rounded-full shadow-lg transition-all duration-500"
              style={{ left: `calc(${sentiment.fearGreedIndex}% - 8px)` }}
            ></div>
          </div>
          <div className="flex justify-between mt-2 text-xs font-semibold text-slate-600">
            <span>Fear</span>
            <span className={`${getFearGreedColor(sentiment.fearGreedIndex)} text-white px-2 py-1 rounded`}>
              {getFearGreedLabel(sentiment.fearGreedIndex)}
            </span>
            <span>Greed</span>
          </div>
        </div>

        {/* Key Metrics */}
        <div className="grid grid-cols-2 gap-4">
          <div className="p-4 bg-slate-50 rounded-lg">
            <div className="text-xs font-semibold text-slate-600 uppercase tracking-wide mb-1">VIX Index</div>
            <div className="text-2xl font-bold text-slate-900">{sentiment.volatilityIndex}</div>
            <div className="text-xs text-slate-500 mt-1">Market Volatility</div>
          </div>

          <div className="p-4 bg-slate-50 rounded-lg">
            <div className="text-xs font-semibold text-slate-600 uppercase tracking-wide mb-1">Put/Call Ratio</div>
            <div className="text-2xl font-bold text-slate-900">{sentiment.putCallRatio}</div>
            <div className="text-xs text-slate-500 mt-1">Options Activity</div>
          </div>
        </div>
      </div>
    </div>
  );
}
