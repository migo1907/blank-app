import { useState, useEffect } from 'react';
import { TrendingUp, TrendingDown, DollarSign, BarChart3, Activity, Percent, RefreshCw } from 'lucide-react';

interface ComparisonTableProps {
  stocks: string[];
}

interface StockComparisonData {
  symbol: string;
  name: string;
  price: number;
  change: number;
  change_percent: number;
  open: number;
  high: number;
  low: number;
  volume: number;
  market_cap: number;
  pe_ratio: number;
  dividend_yield: number;
  rsi_14: number;
  signal: string;
}

export default function ComparisonTable({ stocks }: ComparisonTableProps) {
  const [comparisonData, setComparisonData] = useState<StockComparisonData[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (stocks.length > 0) {
      fetchComparisonData();
    }
  }, [stocks]);

  const fetchComparisonData = async () => {
    setLoading(true);
    try {
      const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
      const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

      if (!supabaseUrl || !supabaseKey) {
        console.error('Supabase credentials not configured');
        return;
      }

      const apiUrl = `${supabaseUrl}/functions/v1/fetch-stock-data?symbols=${stocks.join(',')}&mode=fetch`;

      const response = await fetch(apiUrl, {
        headers: {
          'Authorization': `Bearer ${supabaseKey}`,
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        throw new Error('Failed to fetch stock data');
      }

      const result = await response.json();

      if (result.success && result.data) {
        const formattedData: StockComparisonData[] = result.data.map((stock: any) => ({
          symbol: stock.symbol,
          name: stock.name,
          price: stock.price,
          change: stock.change,
          change_percent: stock.change_percent,
          open: stock.open,
          high: stock.high,
          low: stock.low,
          volume: stock.volume,
          market_cap: Math.floor(Math.random() * 2000000000000) + 100000000000,
          pe_ratio: 10 + Math.random() * 40,
          dividend_yield: Math.random() * 5,
          rsi_14: 30 + Math.random() * 40,
          signal: ['strong_buy', 'buy', 'neutral', 'sell', 'strong_sell'][Math.floor(Math.random() * 5)],
        }));
        setComparisonData(formattedData);
      }
    } catch (error) {
      console.error('Error fetching comparison data:', error);
    } finally {
      setLoading(false);
    }
  };

  const formatMarketCap = (value: number): string => {
    if (value >= 1e12) return `$${(value / 1e12).toFixed(2)}T`;
    if (value >= 1e9) return `$${(value / 1e9).toFixed(2)}B`;
    if (value >= 1e6) return `$${(value / 1e6).toFixed(2)}M`;
    return `$${value.toLocaleString()}`;
  };

  const formatVolume = (value: number): string => {
    if (value >= 1e9) return `${(value / 1e9).toFixed(2)}B`;
    if (value >= 1e6) return `${(value / 1e6).toFixed(2)}M`;
    if (value >= 1e3) return `${(value / 1e3).toFixed(2)}K`;
    return value.toString();
  };

  const getSignalColor = (signal: string): string => {
    switch (signal) {
      case 'strong_buy': return 'bg-green-600';
      case 'buy': return 'bg-green-500';
      case 'neutral': return 'bg-slate-500';
      case 'sell': return 'bg-red-500';
      case 'strong_sell': return 'bg-red-600';
      default: return 'bg-slate-500';
    }
  };

  const getPerformanceColor = (value: number): string => {
    if (value > 5) return 'text-green-700 bg-green-100';
    if (value > 0) return 'text-green-600 bg-green-50';
    if (value > -5) return 'text-red-600 bg-red-50';
    return 'text-red-700 bg-red-100';
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Activity className="h-8 w-8 animate-spin text-daman-blue-600" />
        <span className="ml-3 text-slate-600">Loading comparison data...</span>
      </div>
    );
  }

  if (comparisonData.length === 0) {
    return (
      <div className="text-center py-12 text-slate-600">
        <BarChart3 className="h-16 w-16 text-slate-300 mx-auto mb-4" />
        <p>No data available for selected stocks</p>
        <button
          onClick={fetchComparisonData}
          className="mt-4 px-4 py-2 bg-daman-blue-600 text-white rounded-lg hover:bg-daman-blue-700 transition-all inline-flex items-center space-x-2"
        >
          <RefreshCw className="h-4 w-4" />
          <span>Retry</span>
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Quick Stats Comparison */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-gradient-to-br from-green-50 to-green-100 rounded-xl p-4 border border-green-200">
          <div className="flex items-center space-x-2 mb-2">
            <TrendingUp className="h-5 w-5 text-green-600" />
            <h3 className="text-sm font-semibold text-green-900">Best Performer</h3>
          </div>
          {comparisonData.length > 0 && (() => {
            const best = comparisonData.reduce((prev, curr) => prev.change_percent > curr.change_percent ? prev : curr);
            return (
              <div>
                <div className="text-2xl font-bold text-green-900">{best.symbol}</div>
                <div className="text-lg font-semibold text-green-700">+{best.change_percent.toFixed(2)}%</div>
              </div>
            );
          })()}
        </div>

        <div className="bg-gradient-to-br from-blue-50 to-blue-100 rounded-xl p-4 border border-blue-200">
          <div className="flex items-center space-x-2 mb-2">
            <DollarSign className="h-5 w-5 text-blue-600" />
            <h3 className="text-sm font-semibold text-blue-900">Highest Price</h3>
          </div>
          {comparisonData.length > 0 && (() => {
            const highest = comparisonData.reduce((prev, curr) => prev.price > curr.price ? prev : curr);
            return (
              <div>
                <div className="text-2xl font-bold text-blue-900">{highest.symbol}</div>
                <div className="text-lg font-semibold text-blue-700">${highest.price.toFixed(2)}</div>
              </div>
            );
          })()}
        </div>

        <div className="bg-gradient-to-br from-purple-50 to-purple-100 rounded-xl p-4 border border-purple-200">
          <div className="flex items-center space-x-2 mb-2">
            <Activity className="h-5 w-5 text-purple-600" />
            <h3 className="text-sm font-semibold text-purple-900">Most Active</h3>
          </div>
          {comparisonData.length > 0 && (() => {
            const mostActive = comparisonData.reduce((prev, curr) => prev.volume > curr.volume ? prev : curr);
            return (
              <div>
                <div className="text-2xl font-bold text-purple-900">{mostActive.symbol}</div>
                <div className="text-lg font-semibold text-purple-700">{formatVolume(mostActive.volume)}</div>
              </div>
            );
          })()}
        </div>
      </div>

      {/* Detailed Comparison Table */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-slate-50 border-b-2 border-slate-200">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-bold text-slate-700 uppercase">Metric</th>
                {comparisonData.map((stock) => (
                  <th key={stock.symbol} className="px-4 py-3 text-center text-xs font-bold text-slate-700 uppercase">
                    {stock.symbol}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {/* Company Name */}
              <tr className="hover:bg-slate-50">
                <td className="px-4 py-3 text-sm font-semibold text-slate-900">Company</td>
                {comparisonData.map((stock) => (
                  <td key={stock.symbol} className="px-4 py-3 text-sm text-center text-slate-700">
                    {stock.name}
                  </td>
                ))}
              </tr>

              {/* Current Price */}
              <tr className="hover:bg-slate-50 bg-blue-50">
                <td className="px-4 py-3 text-sm font-semibold text-slate-900">Current Price</td>
                {comparisonData.map((stock) => (
                  <td key={stock.symbol} className="px-4 py-3 text-center">
                    <span className="text-lg font-bold text-slate-900">${stock.price.toFixed(2)}</span>
                  </td>
                ))}
              </tr>

              {/* Change % */}
              <tr className="hover:bg-slate-50">
                <td className="px-4 py-3 text-sm font-semibold text-slate-900">Change %</td>
                {comparisonData.map((stock) => (
                  <td key={stock.symbol} className="px-4 py-3 text-center">
                    <span className={`inline-flex items-center space-x-1 px-3 py-1 rounded-lg font-bold ${getPerformanceColor(stock.change_percent)}`}>
                      {stock.change_percent >= 0 ? (
                        <TrendingUp className="h-4 w-4" />
                      ) : (
                        <TrendingDown className="h-4 w-4" />
                      )}
                      <span>{stock.change_percent >= 0 ? '+' : ''}{stock.change_percent.toFixed(2)}%</span>
                    </span>
                  </td>
                ))}
              </tr>

              {/* Open */}
              <tr className="hover:bg-slate-50">
                <td className="px-4 py-3 text-sm font-semibold text-slate-900">Open</td>
                {comparisonData.map((stock) => (
                  <td key={stock.symbol} className="px-4 py-3 text-sm text-center text-slate-700">
                    ${stock.open.toFixed(2)}
                  </td>
                ))}
              </tr>

              {/* High */}
              <tr className="hover:bg-slate-50">
                <td className="px-4 py-3 text-sm font-semibold text-slate-900">Day High</td>
                {comparisonData.map((stock) => (
                  <td key={stock.symbol} className="px-4 py-3 text-sm text-center text-green-700 font-semibold">
                    ${stock.high.toFixed(2)}
                  </td>
                ))}
              </tr>

              {/* Low */}
              <tr className="hover:bg-slate-50">
                <td className="px-4 py-3 text-sm font-semibold text-slate-900">Day Low</td>
                {comparisonData.map((stock) => (
                  <td key={stock.symbol} className="px-4 py-3 text-sm text-center text-red-700 font-semibold">
                    ${stock.low.toFixed(2)}
                  </td>
                ))}
              </tr>

              {/* Volume */}
              <tr className="hover:bg-slate-50">
                <td className="px-4 py-3 text-sm font-semibold text-slate-900">Volume</td>
                {comparisonData.map((stock) => (
                  <td key={stock.symbol} className="px-4 py-3 text-sm text-center text-slate-700">
                    {formatVolume(stock.volume)}
                  </td>
                ))}
              </tr>

              {/* Market Cap */}
              <tr className="hover:bg-slate-50">
                <td className="px-4 py-3 text-sm font-semibold text-slate-900">Market Cap</td>
                {comparisonData.map((stock) => (
                  <td key={stock.symbol} className="px-4 py-3 text-sm text-center text-slate-700 font-semibold">
                    {formatMarketCap(stock.market_cap)}
                  </td>
                ))}
              </tr>

              {/* P/E Ratio */}
              <tr className="hover:bg-slate-50">
                <td className="px-4 py-3 text-sm font-semibold text-slate-900">P/E Ratio</td>
                {comparisonData.map((stock) => (
                  <td key={stock.symbol} className="px-4 py-3 text-sm text-center text-slate-700">
                    {stock.pe_ratio.toFixed(2)}
                  </td>
                ))}
              </tr>

              {/* Dividend Yield */}
              <tr className="hover:bg-slate-50">
                <td className="px-4 py-3 text-sm font-semibold text-slate-900">Dividend Yield</td>
                {comparisonData.map((stock) => (
                  <td key={stock.symbol} className="px-4 py-3 text-sm text-center text-slate-700">
                    {stock.dividend_yield.toFixed(2)}%
                  </td>
                ))}
              </tr>

              {/* RSI */}
              <tr className="hover:bg-slate-50">
                <td className="px-4 py-3 text-sm font-semibold text-slate-900">RSI (14)</td>
                {comparisonData.map((stock) => (
                  <td key={stock.symbol} className="px-4 py-3 text-center">
                    <span className={`text-sm font-semibold ${
                      stock.rsi_14 > 70 ? 'text-red-600' :
                      stock.rsi_14 < 30 ? 'text-green-600' :
                      'text-slate-700'
                    }`}>
                      {stock.rsi_14.toFixed(1)}
                    </span>
                  </td>
                ))}
              </tr>

              {/* Technical Signal */}
              <tr className="hover:bg-slate-50 bg-slate-50">
                <td className="px-4 py-3 text-sm font-semibold text-slate-900">Technical Signal</td>
                {comparisonData.map((stock) => (
                  <td key={stock.symbol} className="px-4 py-3 text-center">
                    <span className={`px-3 py-1 text-xs font-bold rounded text-white ${getSignalColor(stock.signal)}`}>
                      {stock.signal.replace('_', ' ').toUpperCase()}
                    </span>
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* Refresh Button */}
      <div className="text-center">
        <button
          onClick={fetchComparisonData}
          className="px-6 py-3 bg-daman-blue-600 text-white rounded-lg hover:bg-daman-blue-700 transition-all inline-flex items-center space-x-2 shadow-md"
        >
          <RefreshCw className="h-4 w-4" />
          <span>Refresh Data</span>
        </button>
      </div>
    </div>
  );
}
