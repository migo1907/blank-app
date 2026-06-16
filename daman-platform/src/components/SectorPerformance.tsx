import { useEffect, useState } from 'react';
import { TrendingUp, TrendingDown, Activity } from 'lucide-react';

interface Sector {
  name: string;
  symbol: string;
  performance: number;
  volume: number;
  trend: 'up' | 'down';
}

export default function SectorPerformance() {
  const [sectors, setSectors] = useState<Sector[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    fetchSectorData();
    const interval = setInterval(fetchSectorData, 60000);
    return () => clearInterval(interval);
  }, []);

  const fetchSectorData = async () => {
    try {
      const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
      const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

      if (!supabaseUrl || !supabaseKey) {
        loadMockSectorData();
        return;
      }

      const sectorMap: { [key: string]: string } = {
        'XLK': 'Technology',
        'XLV': 'Healthcare',
        'XLF': 'Financial',
        'XLE': 'Energy',
        'XLY': 'Consumer Discretionary',
        'XLI': 'Industrials',
        'XLB': 'Materials',
        'XLU': 'Utilities',
        'XLRE': 'Real Estate',
        'XLP': 'Consumer Staples',
        'XLC': 'Communication'
      };

      const sectorSymbols = Object.keys(sectorMap).join(',');
      const url = `${supabaseUrl}/functions/v1/fetch-market-data?symbols=${sectorSymbols}`;

      const response = await fetch(url, {
        headers: {
          'Authorization': `Bearer ${supabaseKey}`,
          'Content-Type': 'application/json',
        },
      });

      if (response.ok) {
        const data = await response.json();
        if (data.quotes && data.quotes.length > 0) {
          const sectorData: Sector[] = data.quotes.map((q: any) => ({
            name: sectorMap[q.symbol] || q.symbol,
            symbol: q.symbol,
            performance: q.changePercent || 0,
            volume: q.volume || 0,
            trend: (q.changePercent || 0) >= 0 ? 'up' as const : 'down' as const
          }));

          setSectors(sectorData.sort((a, b) => b.performance - a.performance));
          setIsLoading(false);
          return;
        }
      }

      loadMockSectorData();
    } catch (error) {
      console.error('Error fetching sector data:', error);
      loadMockSectorData();
    }
  };

  const loadMockSectorData = () => {
    const sectorData: Sector[] = [
      { name: 'Technology', symbol: 'XLK', performance: 2.34, volume: 45234567, trend: 'up' },
      { name: 'Healthcare', symbol: 'XLV', performance: 1.12, volume: 23456789, trend: 'up' },
      { name: 'Financial', symbol: 'XLF', performance: -0.45, volume: 34567890, trend: 'down' },
      { name: 'Energy', symbol: 'XLE', performance: 3.21, volume: 28934567, trend: 'up' },
      { name: 'Consumer Discretionary', symbol: 'XLY', performance: 0.89, volume: 19234567, trend: 'up' },
      { name: 'Industrials', symbol: 'XLI', performance: 1.56, volume: 15678901, trend: 'up' },
      { name: 'Materials', symbol: 'XLB', performance: -1.23, volume: 12345678, trend: 'down' },
      { name: 'Utilities', symbol: 'XLU', performance: 0.23, volume: 9876543, trend: 'up' },
      { name: 'Real Estate', symbol: 'XLRE', performance: -0.67, volume: 8765432, trend: 'down' },
      { name: 'Consumer Staples', symbol: 'XLP', performance: 0.45, volume: 11234567, trend: 'up' },
      { name: 'Communication', symbol: 'XLC', performance: 1.78, volume: 21234567, trend: 'up' },
    ];

    setSectors(sectorData.sort((a, b) => b.performance - a.performance));
    setIsLoading(false);
  };

  const formatVolume = (volume: number): string => {
    if (volume >= 1e9) return `${(volume / 1e9).toFixed(2)}B`;
    if (volume >= 1e6) return `${(volume / 1e6).toFixed(2)}M`;
    return `${(volume / 1e3).toFixed(2)}K`;
  };

  const getPerformanceColor = (performance: number): string => {
    if (performance > 2) return 'text-green-700 bg-green-100';
    if (performance > 0) return 'text-green-600 bg-green-50';
    if (performance > -2) return 'text-red-600 bg-red-50';
    return 'text-red-700 bg-red-100';
  };

  const getBarWidth = (performance: number): string => {
    const maxPerformance = Math.max(...sectors.map(s => Math.abs(s.performance)));
    const width = (Math.abs(performance) / maxPerformance) * 100;
    return `${Math.min(width, 100)}%`;
  };

  if (isLoading) {
    return (
      <div className="bg-white rounded-xl shadow-md border border-slate-200 p-6">
        <div className="animate-pulse space-y-4">
          <div className="h-6 bg-slate-200 rounded w-1/3"></div>
          <div className="space-y-3">
            {[...Array(6)].map((_, i) => (
              <div key={i} className="h-12 bg-slate-100 rounded"></div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl shadow-md border border-slate-200 overflow-hidden">
      <div className="p-6 border-b border-slate-200">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <Activity className="h-6 w-6 text-daman-blue-600" />
            <h3 className="text-xl font-bold text-slate-900">Sector Performance</h3>
          </div>
          <span className="text-sm text-slate-500">Last 24 Hours</span>
        </div>
      </div>

      <div className="p-6">
        <div className="space-y-4">
          {sectors.map((sector, index) => (
            <div key={sector.symbol} className="group hover:bg-slate-50 p-3 rounded-lg transition-all">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center space-x-3">
                  <span className="text-xs font-semibold text-slate-400 w-6">{index + 1}</span>
                  <div>
                    <div className="font-semibold text-slate-900">{sector.name}</div>
                    <div className="text-xs text-slate-500">{sector.symbol}</div>
                  </div>
                </div>
                <div className="flex items-center space-x-4">
                  <div className="text-right">
                    <div className={`text-sm font-bold ${sector.performance >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                      {sector.performance >= 0 ? '+' : ''}{sector.performance.toFixed(2)}%
                    </div>
                    <div className="text-xs text-slate-500">Vol: {formatVolume(sector.volume)}</div>
                  </div>
                  {sector.trend === 'up' ? (
                    <TrendingUp className="h-5 w-5 text-green-600" />
                  ) : (
                    <TrendingDown className="h-5 w-5 text-red-600" />
                  )}
                </div>
              </div>

              <div className="relative h-2 bg-slate-100 rounded-full overflow-hidden">
                <div
                  className={`absolute top-0 h-full rounded-full transition-all duration-500 ${
                    sector.performance >= 0 ? 'bg-green-500 left-1/2' : 'bg-red-500 right-1/2'
                  }`}
                  style={{ width: getBarWidth(sector.performance) }}
                />
                <div className="absolute top-0 left-1/2 w-px h-full bg-slate-300"></div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
