import { useEffect, useState } from 'react';
import { Activity, TrendingUp, AlertTriangle } from 'lucide-react';

interface VolatilityData {
  symbol: string;
  name: string;
  currentVol: number;
  avgVol: number;
  percentChange: number;
  trend: 'increasing' | 'decreasing' | 'stable';
}

export default function VolatilityAnalysis() {
  const [volatilityData, setVolatilityData] = useState<VolatilityData[]>([]);
  const [vixData, setVixData] = useState<{ current: number; change: number; trend: 'up' | 'down' }>({ current: 16.5, change: 0.8, trend: 'up' });

  useEffect(() => {
    fetchVolatilityData();
    const interval = setInterval(fetchVolatilityData, 120000);
    return () => clearInterval(interval);
  }, []);

  const fetchVolatilityData = async () => {
    try {
      const mockData: VolatilityData[] = [
        { symbol: 'SPY', name: 'S&P 500 ETF', currentVol: 18.5, avgVol: 15.2, percentChange: 21.7, trend: 'increasing' },
        { symbol: 'QQQ', name: 'Nasdaq ETF', currentVol: 22.3, avgVol: 19.1, percentChange: 16.8, trend: 'increasing' },
        { symbol: 'NVDA', name: 'NVIDIA Corp', currentVol: 45.6, avgVol: 38.2, percentChange: 19.4, trend: 'increasing' },
        { symbol: 'TSLA', name: 'Tesla Inc', currentVol: 52.8, avgVol: 55.3, percentChange: -4.5, trend: 'decreasing' },
        { symbol: 'AAPL', name: 'Apple Inc', currentVol: 24.1, avgVol: 22.8, percentChange: 5.7, trend: 'increasing' },
      ];

      setVolatilityData(mockData);

      setVixData({
        current: 14 + Math.random() * 6,
        change: (Math.random() - 0.5) * 2,
        trend: Math.random() > 0.5 ? 'up' : 'down'
      });
    } catch (error) {
      console.error('Error fetching volatility data:', error);
    }
  };

  const getVolatilityLevel = (vol: number): { label: string; color: string } => {
    if (vol < 15) return { label: 'Low', color: 'text-green-600 bg-green-100' };
    if (vol < 25) return { label: 'Moderate', color: 'text-yellow-600 bg-yellow-100' };
    if (vol < 40) return { label: 'High', color: 'text-orange-600 bg-orange-100' };
    return { label: 'Extreme', color: 'text-red-600 bg-red-100' };
  };

  const getTrendIcon = (trend: string) => {
    if (trend === 'increasing') return <TrendingUp className="h-4 w-4 text-red-600" />;
    if (trend === 'decreasing') return <TrendingUp className="h-4 w-4 text-green-600 transform rotate-180" />;
    return <Activity className="h-4 w-4 text-slate-600" />;
  };

  return (
    <div className="bg-white rounded-xl shadow-md border border-slate-200 overflow-hidden">
      <div className="p-6 border-b border-slate-200">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <AlertTriangle className="h-6 w-6 text-daman-blue-600" />
            <div>
              <h3 className="text-xl font-bold text-slate-900">Volatility Analysis</h3>
              <p className="text-sm text-slate-600">Market volatility indicators</p>
            </div>
          </div>
        </div>
      </div>

      {/* VIX Overview */}
      <div className="p-6 bg-gradient-to-r from-slate-50 to-white border-b border-slate-200">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm font-semibold text-slate-600 uppercase tracking-wide mb-1">
              CBOE Volatility Index (VIX)
            </div>
            <div className="flex items-center space-x-3">
              <span className="text-4xl font-bold text-slate-900">{vixData.current.toFixed(2)}</span>
              <span className={`text-lg font-bold ${vixData.change >= 0 ? 'text-red-600' : 'text-green-600'}`}>
                {vixData.change >= 0 ? '+' : ''}{vixData.change.toFixed(2)}
              </span>
            </div>
          </div>
          <div className={`px-4 py-2 rounded-lg ${getVolatilityLevel(vixData.current).color}`}>
            <div className="text-xs font-semibold uppercase tracking-wide">Market Fear</div>
            <div className="text-lg font-bold">{getVolatilityLevel(vixData.current).label}</div>
          </div>
        </div>
      </div>

      {/* Individual Asset Volatility */}
      <div className="p-6">
        <div className="space-y-4">
          {volatilityData.map((item) => {
            const volLevel = getVolatilityLevel(item.currentVol);
            return (
              <div key={item.symbol} className="p-4 hover:bg-slate-50 rounded-lg transition-all border border-slate-100">
                <div className="flex items-center justify-between mb-3">
                  <div>
                    <div className="font-bold text-slate-900">{item.symbol}</div>
                    <div className="text-xs text-slate-600">{item.name}</div>
                  </div>
                  <div className="flex items-center space-x-2">
                    {getTrendIcon(item.trend)}
                    <span className={`text-xs font-semibold px-2 py-1 rounded ${volLevel.color}`}>
                      {volLevel.label}
                    </span>
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-4 mb-3">
                  <div>
                    <div className="text-xs text-slate-600">Current Vol</div>
                    <div className="text-lg font-bold text-slate-900">{item.currentVol.toFixed(1)}%</div>
                  </div>
                  <div>
                    <div className="text-xs text-slate-600">Avg Vol</div>
                    <div className="text-lg font-bold text-slate-700">{item.avgVol.toFixed(1)}%</div>
                  </div>
                  <div>
                    <div className="text-xs text-slate-600">Change</div>
                    <div className={`text-lg font-bold ${item.percentChange >= 0 ? 'text-red-600' : 'text-green-600'}`}>
                      {item.percentChange >= 0 ? '+' : ''}{item.percentChange.toFixed(1)}%
                    </div>
                  </div>
                </div>

                {/* Volatility Bar */}
                <div className="relative h-2 bg-slate-100 rounded-full overflow-hidden">
                  <div
                    className={`h-full transition-all duration-500 ${
                      item.currentVol < 15 ? 'bg-green-500' :
                      item.currentVol < 25 ? 'bg-yellow-500' :
                      item.currentVol < 40 ? 'bg-orange-500' : 'bg-red-500'
                    }`}
                    style={{ width: `${Math.min((item.currentVol / 60) * 100, 100)}%` }}
                  ></div>
                </div>
              </div>
            );
          })}
        </div>

        {/* Volatility Scale Reference */}
        <div className="mt-6 p-4 bg-slate-50 rounded-lg">
          <div className="text-xs font-semibold text-slate-600 uppercase tracking-wide mb-3">Volatility Scale</div>
          <div className="flex items-center justify-between text-xs">
            <div className="flex items-center space-x-2">
              <div className="w-3 h-3 bg-green-500 rounded"></div>
              <span className="text-slate-700">Low (&lt;15%)</span>
            </div>
            <div className="flex items-center space-x-2">
              <div className="w-3 h-3 bg-yellow-500 rounded"></div>
              <span className="text-slate-700">Moderate (15-25%)</span>
            </div>
            <div className="flex items-center space-x-2">
              <div className="w-3 h-3 bg-orange-500 rounded"></div>
              <span className="text-slate-700">High (25-40%)</span>
            </div>
            <div className="flex items-center space-x-2">
              <div className="w-3 h-3 bg-red-500 rounded"></div>
              <span className="text-slate-700">Extreme (&gt;40%)</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
