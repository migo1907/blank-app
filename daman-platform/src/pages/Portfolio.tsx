import { useState, useEffect } from 'react';
import { PieChart, TrendingUp, TrendingDown, DollarSign, Plus, X, RefreshCw, Sparkles } from 'lucide-react';
import Reveal from '../components/Reveal';
import Skeleton from '../components/Skeleton';
import { askHermes } from '../lib/hermesBus';

interface Position {
  id: string;
  symbol: string;
  quantity: number;
  avg_cost: number;
  current_price: number;
  market_value: number;
  cost_basis: number;
  unrealized_pl: number;
  unrealized_pl_percent: number;
  day_change: number;
  day_change_percent: number;
}

export default function Portfolio() {
  const [positions, setPositions] = useState<Position[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddForm, setShowAddForm] = useState(false);
  const [newPosition, setNewPosition] = useState({ symbol: '', quantity: '', avgCost: '' });
  const [lastUpdate, setLastUpdate] = useState<Date>(new Date());

  useEffect(() => {
    loadPortfolio();
    const interval = setInterval(updatePrices, 30000);
    return () => clearInterval(interval);
  }, []);

  const loadPortfolio = async () => {
    const saved = localStorage.getItem('portfolio');
    if (saved) {
      const savedPositions = JSON.parse(saved);
      if (savedPositions.length > 0) {
        await updatePrices(savedPositions);
      } else {
        setLoading(false);
      }
    } else {
      setLoading(false);
    }
  };

  const updatePrices = async (savedPositions?: any[]) => {
    const positions = savedPositions || JSON.parse(localStorage.getItem('portfolio') || '[]');
    if (positions.length === 0) {
      setPositions([]);
      setLoading(false);
      return;
    }

    setLoading(true);
    try {
      const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
      const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

      if (!supabaseUrl || !supabaseKey) {
        setLoading(false);
        return;
      }

      const symbols = positions.map((p: any) => p.symbol);
      const apiUrl = `${supabaseUrl}/functions/v1/fetch-market-data`;

      const response = await fetch(apiUrl, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${supabaseKey}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ symbols }),
      });

      if (!response.ok) {
        throw new Error('Failed to fetch quotes');
      }

      const result = await response.json();
      const quotes = result.quotes || [];

      const updatedPositions: Position[] = positions.map((pos: any) => {
        const quote = quotes.find((q: any) => q.symbol === pos.symbol);
        if (!quote) return null;

        const currentPrice = quote.price;
        const marketValue = currentPrice * pos.quantity;
        const costBasis = pos.avg_cost * pos.quantity;
        const unrealizedPL = marketValue - costBasis;
        const unrealizedPLPercent = (unrealizedPL / costBasis) * 100;
        const dayChange = quote.change * pos.quantity;
        const dayChangePercent = quote.changePercent;

        return {
          id: pos.id || `${pos.symbol}-${Date.now()}`,
          symbol: pos.symbol,
          quantity: pos.quantity,
          avg_cost: pos.avg_cost,
          current_price: currentPrice,
          market_value: marketValue,
          cost_basis: costBasis,
          unrealized_pl: unrealizedPL,
          unrealized_pl_percent: unrealizedPLPercent,
          day_change: dayChange,
          day_change_percent: dayChangePercent
        };
      }).filter(Boolean) as Position[];

      setPositions(updatedPositions);
      setLastUpdate(new Date());
    } catch (error) {
      console.error('Error updating prices:', error);
    } finally {
      setLoading(false);
    }
  };

  const addPosition = async () => {
    if (!newPosition.symbol || !newPosition.quantity || !newPosition.avgCost) return;

    try {
      const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
      const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

      if (!supabaseUrl || !supabaseKey) {
        alert('Configuration error. Please check environment variables.');
        return;
      }

      const symbol = newPosition.symbol.toUpperCase();

      // Verify the symbol exists by fetching a quote
      const apiUrl = `${supabaseUrl}/functions/v1/fetch-market-data?symbols=${symbol}`;
      const response = await fetch(apiUrl, {
        headers: {
          'Authorization': `Bearer ${supabaseKey}`,
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        alert('Could not fetch quote for symbol');
        return;
      }

      const result = await response.json();
      if (!result.quotes || result.quotes.length === 0) {
        alert('Invalid symbol. Please check and try again.');
        return;
      }

      const position = {
        symbol: symbol,
        quantity: parseFloat(newPosition.quantity),
        avg_cost: parseFloat(newPosition.avgCost),
        id: `${symbol}-${Date.now()}`
      };

      const saved = JSON.parse(localStorage.getItem('portfolio') || '[]');
      const updated = [...saved, position];
      localStorage.setItem('portfolio', JSON.stringify(updated));

      setNewPosition({ symbol: '', quantity: '', avgCost: '' });
      setShowAddForm(false);
      await updatePrices(updated);
    } catch (error) {
      console.error('Error adding position:', error);
      alert('Failed to add position. Please try again.');
    }
  };

  const removePosition = (id: string) => {
    const saved = JSON.parse(localStorage.getItem('portfolio') || '[]');
    const updated = saved.filter((p: any) => p.id !== id);
    localStorage.setItem('portfolio', JSON.stringify(updated));
    setPositions(positions.filter(p => p.id !== id));
  };

  const totalMarketValue = positions.reduce((sum, p) => sum + p.market_value, 0);
  const totalCostBasis = positions.reduce((sum, p) => sum + p.cost_basis, 0);
  const totalUnrealizedPL = totalMarketValue - totalCostBasis;
  const totalUnrealizedPLPercent = totalCostBasis > 0 ? (totalUnrealizedPL / totalCostBasis) * 100 : 0;
  const totalDayChange = positions.reduce((sum, p) => sum + p.day_change, 0);
  const totalDayChangePercent = totalCostBasis > 0 ? (totalDayChange / totalMarketValue) * 100 : 0;

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-slate-50 dark:bg-gradient-to-br dark:from-slate-900 dark:via-slate-800 dark:to-slate-900 p-4 md:p-8">
      <div className="max-w-7xl mx-auto">
        <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-2xl border border-slate-200 dark:border-slate-700 p-6 md:p-8 mb-6">
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center space-x-3">
              <div className="bg-gradient-to-br from-blue-600 to-blue-700 p-3 rounded-xl">
                <PieChart className="h-7 w-7 text-white" />
              </div>
              <div>
                <h1 className="text-2xl md:text-3xl font-bold text-slate-900 dark:text-white">Portfolio</h1>
                <p className="text-slate-600 dark:text-slate-400 text-sm">Real-time tracking with live P&L</p>
              </div>
            </div>
            <div className="flex items-center space-x-3">
              <div className="flex items-center space-x-2 bg-green-500/20 px-4 py-2 rounded-lg border border-green-500/30">
                <div className="h-2 w-2 bg-green-500 rounded-full animate-pulse"></div>
                <span className="text-sm font-medium text-green-600 dark:text-green-400">Live Data</span>
              </div>
              <button
                onClick={() => updatePrices()}
                disabled={loading}
                className="flex items-center space-x-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-all font-medium disabled:opacity-50"
              >
                <RefreshCw className={`h-5 w-5 ${loading ? 'animate-spin' : ''}`} />
                <span className="hidden md:inline">Refresh</span>
              </button>
              <button
                onClick={() => setShowAddForm(!showAddForm)}
                className="flex items-center space-x-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-all font-medium"
              >
                <Plus className="h-5 w-5" />
                <span className="hidden md:inline">Add Position</span>
              </button>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
            <div className="bg-gradient-to-br from-blue-50 to-blue-100 dark:from-blue-900/20 dark:to-blue-800/20 rounded-xl p-4 border border-blue-200 dark:border-blue-800">
              <div className="flex items-center space-x-2 mb-2">
                <DollarSign className="h-5 w-5 text-blue-600 dark:text-blue-400" />
                <span className="text-sm font-medium text-slate-700 dark:text-slate-300">Total Value</span>
              </div>
              <div className="text-2xl font-bold text-slate-900 dark:text-white">
                ${totalMarketValue.toFixed(2)}
              </div>
              <div className="text-sm text-slate-600 dark:text-slate-400 mt-1">
                Cost: ${totalCostBasis.toFixed(2)}
              </div>
            </div>

            <div className={`bg-gradient-to-br rounded-xl p-4 border ${
              totalUnrealizedPL >= 0
                ? 'from-green-50 to-green-100 dark:from-green-900/20 dark:to-green-800/20 border-green-200 dark:border-green-800'
                : 'from-red-50 to-red-100 dark:from-red-900/20 dark:to-red-800/20 border-red-200 dark:border-red-800'
            }`}>
              <div className="flex items-center space-x-2 mb-2">
                {totalUnrealizedPL >= 0 ? (
                  <TrendingUp className="h-5 w-5 text-green-600 dark:text-green-400" />
                ) : (
                  <TrendingDown className="h-5 w-5 text-red-600 dark:text-red-400" />
                )}
                <span className="text-sm font-medium text-slate-700 dark:text-slate-300">Total P&L</span>
              </div>
              <div className={`text-2xl font-bold ${
                totalUnrealizedPL >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'
              }`}>
                {totalUnrealizedPL >= 0 ? '+' : ''}${totalUnrealizedPL.toFixed(2)}
              </div>
              <div className={`text-sm font-semibold mt-1 ${
                totalUnrealizedPL >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'
              }`}>
                {totalUnrealizedPL >= 0 ? '+' : ''}{totalUnrealizedPLPercent.toFixed(2)}%
              </div>
            </div>

            <div className={`bg-gradient-to-br rounded-xl p-4 border ${
              totalDayChange >= 0
                ? 'from-emerald-50 to-emerald-100 dark:from-emerald-900/20 dark:to-emerald-800/20 border-emerald-200 dark:border-emerald-800'
                : 'from-orange-50 to-orange-100 dark:from-orange-900/20 dark:to-orange-800/20 border-orange-200 dark:border-orange-800'
            }`}>
              <div className="flex items-center space-x-2 mb-2">
                <TrendingUp className={`h-5 w-5 ${
                  totalDayChange >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-orange-600 dark:text-orange-400'
                }`} />
                <span className="text-sm font-medium text-slate-700 dark:text-slate-300">Day Change</span>
              </div>
              <div className={`text-2xl font-bold ${
                totalDayChange >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-orange-600 dark:text-orange-400'
              }`}>
                {totalDayChange >= 0 ? '+' : ''}${totalDayChange.toFixed(2)}
              </div>
              <div className={`text-sm font-semibold mt-1 ${
                totalDayChange >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-orange-600 dark:text-orange-400'
              }`}>
                {totalDayChange >= 0 ? '+' : ''}{totalDayChangePercent.toFixed(2)}%
              </div>
            </div>

            <div className="bg-gradient-to-br from-purple-50 to-purple-100 dark:from-purple-900/20 dark:to-purple-800/20 rounded-xl p-4 border border-purple-200 dark:border-purple-800">
              <div className="flex items-center space-x-2 mb-2">
                <PieChart className="h-5 w-5 text-purple-600 dark:text-purple-400" />
                <span className="text-sm font-medium text-slate-700 dark:text-slate-300">Positions</span>
              </div>
              <div className="text-2xl font-bold text-slate-900 dark:text-white">
                {positions.length}
              </div>
              <div className="text-sm text-slate-600 dark:text-slate-400 mt-1">
                Holdings
              </div>
            </div>
          </div>

          {showAddForm && (
            <div className="bg-slate-50 dark:bg-slate-900 rounded-xl p-6 mb-6 border-2 border-slate-200 dark:border-slate-700">
              <h3 className="font-bold text-lg text-slate-900 dark:text-white mb-4">Add New Position</h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
                <input
                  type="text"
                  value={newPosition.symbol}
                  onChange={(e) => setNewPosition({ ...newPosition, symbol: e.target.value.toUpperCase() })}
                  placeholder="Symbol (e.g., AAPL)"
                  className="px-4 py-3 border-2 border-slate-300 dark:border-slate-600 dark:bg-slate-800 dark:text-white rounded-xl focus:border-blue-500 focus:outline-none font-medium"
                />
                <input
                  type="number"
                  value={newPosition.quantity}
                  onChange={(e) => setNewPosition({ ...newPosition, quantity: e.target.value })}
                  placeholder="Quantity"
                  step="0.01"
                  className="px-4 py-3 border-2 border-slate-300 dark:border-slate-600 dark:bg-slate-800 dark:text-white rounded-xl focus:border-blue-500 focus:outline-none font-medium"
                />
                <input
                  type="number"
                  value={newPosition.avgCost}
                  onChange={(e) => setNewPosition({ ...newPosition, avgCost: e.target.value })}
                  placeholder="Avg Cost per Share"
                  step="0.01"
                  className="px-4 py-3 border-2 border-slate-300 dark:border-slate-600 dark:bg-slate-800 dark:text-white rounded-xl focus:border-blue-500 focus:outline-none font-medium"
                />
              </div>
              <div className="flex space-x-3">
                <button
                  onClick={addPosition}
                  className="flex-1 py-3 bg-green-600 text-white rounded-xl hover:bg-green-700 transition-all font-semibold"
                >
                  Add Position
                </button>
                <button
                  onClick={() => setShowAddForm(false)}
                  className="px-6 py-3 bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-300 rounded-xl hover:bg-slate-300 dark:hover:bg-slate-600 transition-all font-semibold"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          {positions.length > 0 && (
            <div className="text-sm text-slate-500 dark:text-slate-400 mb-4">
              Last updated: {lastUpdate.toLocaleTimeString()} • Updates every 30 seconds
            </div>
          )}
        </div>

        {loading && positions.length === 0 ? (
          <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-2xl border border-slate-200 dark:border-slate-700 p-6 md:p-8">
            <Skeleton className="h-5 w-40 mb-6" />
            <div className="space-y-4">
              {[0, 1, 2, 3, 4].map((i) => (
                <div key={i} className="flex items-center justify-between gap-4">
                  <Skeleton className="h-6 w-20" />
                  <Skeleton className="h-6 w-16 hidden sm:block" />
                  <Skeleton className="h-6 w-24" />
                  <Skeleton className="h-6 w-24 hidden md:block" />
                  <Skeleton className="h-6 w-20" />
                </div>
              ))}
            </div>
          </div>
        ) : positions.length === 0 ? (
          <Reveal className="bg-white dark:bg-slate-800 rounded-2xl shadow-2xl border border-slate-200 dark:border-slate-700 p-12 text-center">
            <PieChart className="h-16 w-16 text-slate-300 dark:text-slate-600 mx-auto mb-4" />
            <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-2">No Positions Yet</h3>
            <p className="text-slate-600 dark:text-slate-400 mb-6">Start tracking your portfolio by adding your first position</p>
            <button
              onClick={() => setShowAddForm(true)}
              className="px-6 py-3 bg-blue-600 text-white rounded-xl hover:bg-blue-700 transition-all font-semibold inline-flex items-center space-x-2"
            >
              <Plus className="h-5 w-5" />
              <span>Add First Position</span>
            </button>
          </Reveal>
        ) : (
          <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-2xl border border-slate-200 dark:border-slate-700 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-slate-50 dark:bg-slate-900">
                  <tr>
                    <th className="px-6 py-4 text-left text-sm font-semibold text-slate-700 dark:text-slate-300">Symbol</th>
                    <th className="px-6 py-4 text-right text-sm font-semibold text-slate-700 dark:text-slate-300">Quantity</th>
                    <th className="px-6 py-4 text-right text-sm font-semibold text-slate-700 dark:text-slate-300">Avg Cost</th>
                    <th className="px-6 py-4 text-right text-sm font-semibold text-slate-700 dark:text-slate-300">Current Price</th>
                    <th className="px-6 py-4 text-right text-sm font-semibold text-slate-700 dark:text-slate-300">Market Value</th>
                    <th className="px-6 py-4 text-right text-sm font-semibold text-slate-700 dark:text-slate-300">Total P&L</th>
                    <th className="px-6 py-4 text-right text-sm font-semibold text-slate-700 dark:text-slate-300">Day Change</th>
                    <th className="px-6 py-4"></th>
                  </tr>
                </thead>
                <tbody>
                  {positions.map((position, idx) => (
                    <tr
                      key={position.id}
                      style={{ animationDelay: `${idx * 50}ms` }}
                      className="border-b border-slate-100 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-900/50 transition-colors animate-fadeIn"
                    >
                      <td className="px-6 py-4 font-bold text-slate-900 dark:text-white">{position.symbol}</td>
                      <td className="px-6 py-4 text-right text-slate-900 dark:text-white">{position.quantity}</td>
                      <td className="px-6 py-4 text-right font-medium text-slate-900 dark:text-white">
                        ${position.avg_cost.toFixed(2)}
                      </td>
                      <td className="px-6 py-4 text-right font-medium text-slate-900 dark:text-white">
                        ${position.current_price.toFixed(2)}
                      </td>
                      <td className="px-6 py-4 text-right font-bold text-slate-900 dark:text-white">
                        ${position.market_value.toFixed(2)}
                      </td>
                      <td className="px-6 py-4 text-right">
                        <div className={`font-bold ${
                          position.unrealized_pl >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'
                        }`}>
                          {position.unrealized_pl >= 0 ? '+' : ''}${position.unrealized_pl.toFixed(2)}
                        </div>
                        <div className={`text-sm font-semibold ${
                          position.unrealized_pl >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'
                        }`}>
                          {position.unrealized_pl >= 0 ? '+' : ''}{position.unrealized_pl_percent.toFixed(2)}%
                        </div>
                      </td>
                      <td className="px-6 py-4 text-right">
                        <div className={`font-bold ${
                          position.day_change >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'
                        }`}>
                          {position.day_change >= 0 ? '+' : ''}${position.day_change.toFixed(2)}
                        </div>
                        <div className={`text-sm font-semibold ${
                          position.day_change >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'
                        }`}>
                          {position.day_change >= 0 ? '+' : ''}{position.day_change_percent.toFixed(2)}%
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex items-center justify-end gap-1">
                          <button
                            onClick={() => askHermes(`Give me your take on ${position.symbol} — fundamentals and technicals, with a bull and bear case. I hold ${position.quantity} shares at avg cost $${position.avg_cost.toFixed(2)}, currently $${position.current_price.toFixed(2)}.`)}
                            className="p-2 text-daman-blue-600 hover:bg-daman-blue-50 dark:hover:bg-slate-700 rounded-lg transition-colors"
                            title="Ask Hermes about this position"
                          >
                            <Sparkles className="h-5 w-5" />
                          </button>
                          <button
                            onClick={() => removePosition(position.id)}
                            className="p-2 text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors"
                          >
                            <X className="h-5 w-5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        <div className="mt-6 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-xl p-4">
          <p className="text-sm text-blue-800 dark:text-blue-300">
            <strong>Live Portfolio Tracking:</strong> All prices update every 30 seconds with real Alpaca data.
            P&L calculations include both unrealized gains/losses and daily performance metrics.
          </p>
        </div>
      </div>
    </div>
  );
}
