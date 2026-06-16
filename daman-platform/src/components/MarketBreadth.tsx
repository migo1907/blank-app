import { useEffect, useState } from 'react';
import { BarChart3, TrendingUp, TrendingDown } from 'lucide-react';

interface BreadthData {
  advancers: number;
  decliners: number;
  unchanged: number;
  advanceDeclineRatio: number;
  newHighs: number;
  newLows: number;
  upVolume: number;
  downVolume: number;
}

export default function MarketBreadth() {
  const [breadth, setBreadth] = useState<BreadthData>({
    advancers: 1845,
    decliners: 1234,
    unchanged: 245,
    advanceDeclineRatio: 1.49,
    newHighs: 142,
    newLows: 38,
    upVolume: 3.8e9,
    downVolume: 2.1e9,
  });

  useEffect(() => {
    fetchBreadthData();
    const interval = setInterval(fetchBreadthData, 60000);
    return () => clearInterval(interval);
  }, []);

  const fetchBreadthData = async () => {
    try {
      const total = 3000 + Math.floor(Math.random() * 500);
      const advancers = Math.floor(total * (0.4 + Math.random() * 0.3));
      const decliners = Math.floor(total * (0.3 + Math.random() * 0.3));
      const unchanged = total - advancers - decliners;

      const mockData: BreadthData = {
        advancers,
        decliners,
        unchanged,
        advanceDeclineRatio: parseFloat((advancers / decliners).toFixed(2)),
        newHighs: Math.floor(50 + Math.random() * 150),
        newLows: Math.floor(20 + Math.random() * 80),
        upVolume: (2 + Math.random() * 3) * 1e9,
        downVolume: (1.5 + Math.random() * 2.5) * 1e9,
      };

      setBreadth(mockData);
    } catch (error) {
      console.error('Error fetching breadth data:', error);
    }
  };

  const formatVolume = (volume: number): string => {
    return `${(volume / 1e9).toFixed(2)}B`;
  };

  const getTotalStocks = () => breadth.advancers + breadth.decliners + breadth.unchanged;

  const getAdvancerPercentage = () => (breadth.advancers / getTotalStocks()) * 100;
  const getDeclinerPercentage = () => (breadth.decliners / getTotalStocks()) * 100;
  const getUnchangedPercentage = () => (breadth.unchanged / getTotalStocks()) * 100;

  const getBreadthSentiment = (): { label: string; color: string } => {
    const ratio = breadth.advanceDeclineRatio;
    if (ratio >= 2) return { label: 'Very Bullish', color: 'text-green-700 bg-green-100' };
    if (ratio >= 1.5) return { label: 'Bullish', color: 'text-green-600 bg-green-50' };
    if (ratio >= 0.8) return { label: 'Neutral', color: 'text-slate-600 bg-slate-100' };
    if (ratio >= 0.5) return { label: 'Bearish', color: 'text-red-600 bg-red-50' };
    return { label: 'Very Bearish', color: 'text-red-700 bg-red-100' };
  };

  const sentiment = getBreadthSentiment();

  return (
    <div className="bg-white rounded-xl shadow-md border border-slate-200 overflow-hidden">
      <div className="p-6 border-b border-slate-200">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <BarChart3 className="h-6 w-6 text-daman-blue-600" />
            <div>
              <h3 className="text-xl font-bold text-slate-900">Market Breadth</h3>
              <p className="text-sm text-slate-600">Internal market strength</p>
            </div>
          </div>
          <div className={`px-4 py-2 rounded-lg text-center ${sentiment.color}`}>
            <div className="text-xs font-semibold uppercase tracking-wide">Breadth</div>
            <div className="text-sm font-bold">{sentiment.label}</div>
          </div>
        </div>
      </div>

      <div className="p-6">
        {/* Advance/Decline Ratio */}
        <div className="mb-6 p-4 bg-gradient-to-r from-green-50 to-red-50 rounded-lg">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-semibold text-slate-700">Advance/Decline Ratio</span>
            <span className="text-3xl font-bold text-slate-900">{breadth.advanceDeclineRatio.toFixed(2)}</span>
          </div>
          <div className="text-xs text-slate-600">
            Ratio above 1.0 indicates more advancing stocks
          </div>
        </div>

        {/* Advancers vs Decliners */}
        <div className="space-y-4 mb-6">
          <div>
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center space-x-2">
                <TrendingUp className="h-4 w-4 text-green-600" />
                <span className="text-sm font-semibold text-slate-700">Advancing Stocks</span>
              </div>
              <span className="text-sm font-bold text-green-600">
                {breadth.advancers.toLocaleString()} ({getAdvancerPercentage().toFixed(1)}%)
              </span>
            </div>
            <div className="h-3 bg-slate-100 rounded-full overflow-hidden">
              <div
                className="h-full bg-green-500 transition-all duration-500"
                style={{ width: `${getAdvancerPercentage()}%` }}
              ></div>
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center space-x-2">
                <TrendingDown className="h-4 w-4 text-red-600" />
                <span className="text-sm font-semibold text-slate-700">Declining Stocks</span>
              </div>
              <span className="text-sm font-bold text-red-600">
                {breadth.decliners.toLocaleString()} ({getDeclinerPercentage().toFixed(1)}%)
              </span>
            </div>
            <div className="h-3 bg-slate-100 rounded-full overflow-hidden">
              <div
                className="h-full bg-red-500 transition-all duration-500"
                style={{ width: `${getDeclinerPercentage()}%` }}
              ></div>
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-semibold text-slate-700">Unchanged</span>
              <span className="text-sm font-bold text-slate-600">
                {breadth.unchanged.toLocaleString()} ({getUnchangedPercentage().toFixed(1)}%)
              </span>
            </div>
            <div className="h-3 bg-slate-100 rounded-full overflow-hidden">
              <div
                className="h-full bg-slate-400 transition-all duration-500"
                style={{ width: `${getUnchangedPercentage()}%` }}
              ></div>
            </div>
          </div>
        </div>

        {/* New Highs vs New Lows */}
        <div className="grid grid-cols-2 gap-4 mb-6">
          <div className="p-4 bg-green-50 rounded-lg border border-green-200">
            <div className="text-xs font-semibold text-green-700 uppercase tracking-wide mb-1">
              52-Week New Highs
            </div>
            <div className="text-3xl font-bold text-green-700">{breadth.newHighs}</div>
            <div className="text-xs text-green-600 mt-1">Stocks at peak</div>
          </div>

          <div className="p-4 bg-red-50 rounded-lg border border-red-200">
            <div className="text-xs font-semibold text-red-700 uppercase tracking-wide mb-1">
              52-Week New Lows
            </div>
            <div className="text-3xl font-bold text-red-700">{breadth.newLows}</div>
            <div className="text-xs text-red-600 mt-1">Stocks at trough</div>
          </div>
        </div>

        {/* Volume Analysis */}
        <div className="p-4 bg-slate-50 rounded-lg">
          <div className="text-sm font-semibold text-slate-700 mb-4">Volume Analysis</div>

          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <div className="w-3 h-3 bg-green-500 rounded"></div>
                <span className="text-sm text-slate-700">Up Volume</span>
              </div>
              <span className="text-sm font-bold text-green-600">{formatVolume(breadth.upVolume)}</span>
            </div>

            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <div className="w-3 h-3 bg-red-500 rounded"></div>
                <span className="text-sm text-slate-700">Down Volume</span>
              </div>
              <span className="text-sm font-bold text-red-600">{formatVolume(breadth.downVolume)}</span>
            </div>

            <div className="pt-2 border-t border-slate-200">
              <div className="flex items-center justify-between">
                <span className="text-sm font-semibold text-slate-700">Volume Ratio</span>
                <span className="text-sm font-bold text-slate-900">
                  {(breadth.upVolume / breadth.downVolume).toFixed(2)}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Interpretation */}
        <div className="mt-6 p-4 bg-daman-blue-50 border border-daman-blue-200 rounded-lg">
          <div className="text-xs font-semibold text-daman-blue-900 uppercase tracking-wide mb-2">
            Interpretation
          </div>
          <p className="text-sm text-daman-blue-800">
            {breadth.advanceDeclineRatio > 1.5
              ? 'Strong market breadth suggests broad-based participation in the rally. This is a healthy sign for continued upward momentum.'
              : breadth.advanceDeclineRatio < 0.8
              ? 'Weak market breadth indicates selling pressure across many stocks. This suggests caution and possible market weakness ahead.'
              : 'Neutral market breadth shows mixed participation. Watch for clearer directional signals before making major decisions.'}
          </p>
        </div>
      </div>
    </div>
  );
}
