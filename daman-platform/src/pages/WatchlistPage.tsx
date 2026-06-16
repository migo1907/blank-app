import { useState, useEffect } from 'react';
import { Eye, Plus, X, Bell, BellOff, TrendingUp, TrendingDown, RefreshCw } from 'lucide-react';
import Skeleton from '../components/Skeleton';

interface WatchlistStock {
  symbol: string;
  price: number;
  change: number;
  changePercent: number;
  volume: number;
  high: number;
  low: number;
  open: number;
  alertEnabled: boolean;
  alertPrice?: number;
  alertType?: 'above' | 'below';
}

export default function WatchlistPage() {
  const [stocks, setStocks] = useState<WatchlistStock[]>([]);
  const [loading, setLoading] = useState(false);
  const [newSymbol, setNewSymbol] = useState('');
  const [lastUpdate, setLastUpdate] = useState<Date>(new Date());
  const [showAlertForm, setShowAlertForm] = useState<string | null>(null);
  const [alertPrice, setAlertPrice] = useState('');
  const [alertType, setAlertType] = useState<'above' | 'below'>('above');

  useEffect(() => {
    loadWatchlist();
    const interval = setInterval(updatePrices, 15000);
    return () => clearInterval(interval);
  }, []);

  const loadWatchlist = () => {
    const saved = localStorage.getItem('watchlist_v2');
    if (saved) {
      const watchlist = JSON.parse(saved);
      if (watchlist.length > 0) {
        updatePrices(watchlist);
      }
    }
  };

  const updatePrices = async (savedWatchlist?: any[]) => {
    const watchlist = savedWatchlist || JSON.parse(localStorage.getItem('watchlist_v2') || '[]');
    if (watchlist.length === 0) {
      setStocks([]);
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

      const symbols = watchlist.map((w: any) => w.symbol);
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

      const updatedStocks: WatchlistStock[] = watchlist.map((w: any) => {
        const quote = quotes.find((q: any) => q.symbol === w.symbol);
        if (!quote) return null;

        const stock: WatchlistStock = {
          symbol: quote.symbol,
          price: quote.price,
          change: quote.change,
          changePercent: quote.changePercent,
          volume: quote.volume,
          high: quote.high,
          low: quote.low,
          open: quote.open,
          alertEnabled: w.alertEnabled || false,
          alertPrice: w.alertPrice,
          alertType: w.alertType
        };

        if (stock.alertEnabled && stock.alertPrice) {
          checkAlert(stock);
        }

        return stock;
      }).filter(Boolean) as WatchlistStock[];

      setStocks(updatedStocks);
      setLastUpdate(new Date());
    } catch (error) {
      console.error('Error updating prices:', error);
    } finally {
      setLoading(false);
    }
  };

  const checkAlert = (stock: WatchlistStock) => {
    if (!stock.alertPrice) return;

    const shouldAlert = stock.alertType === 'above'
      ? stock.price >= stock.alertPrice
      : stock.price <= stock.alertPrice;

    if (shouldAlert) {
      if (Notification.permission === 'granted') {
        new Notification(`Price Alert: ${stock.symbol}`, {
          body: `${stock.symbol} is now ${stock.alertType} $${stock.alertPrice}. Current price: $${stock.price.toFixed(2)}`,
          icon: '/logo.svg'
        });
      }

      const alertSound = new Audio('data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQoGAACBhYqFbF1fdJivrJBhNjVgodDbq2EcBj+a2/LDciUFLIHO8tiJNwgZaLvt559NEAxQp+PwtmMcBjiR1/LMeSwFJHfH8N2QQAoUXrTp66hVFApGn+DyvmwhBSiI0O/PfzEGHm7A7+OZURE');
      alertSound.play().catch(() => {});
    }
  };

  const addSymbol = async () => {
    if (!newSymbol.trim()) return;

    const symbol = newSymbol.toUpperCase().trim();
    const saved = JSON.parse(localStorage.getItem('watchlist_v2') || '[]');

    if (saved.find((s: any) => s.symbol === symbol)) {
      alert('Symbol already in watchlist');
      return;
    }

    setLoading(true);
    try {
      const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
      const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

      if (!supabaseUrl || !supabaseKey) {
        alert('Configuration error');
        setLoading(false);
        return;
      }

      const apiUrl = `${supabaseUrl}/functions/v1/fetch-market-data`;
      const response = await fetch(apiUrl, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${supabaseKey}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ symbols: [symbol] }),
      });

      if (!response.ok) {
        const result = await response.json().catch(() => ({}));
        const errorMessage = result.message || result.error || 'Unable to fetch quote';
        alert(`${errorMessage}\n\nSymbol: ${symbol}\n\nPlease verify the symbol is correct and try again.`);
        setLoading(false);
        return;
      }

      const result = await response.json();
      if (!result.success || !result.quotes || result.quotes.length === 0) {
        const errorMessage = result.message || `No quote data found for ${symbol}`;
        alert(`${errorMessage}\n\nPlease verify the symbol is correct and try again.`);
        setLoading(false);
        return;
      }

      const updated = [...saved, { symbol, alertEnabled: false }];
      localStorage.setItem('watchlist_v2', JSON.stringify(updated));
      setNewSymbol('');
      setLoading(false);
      await updatePrices(updated);
    } catch (error) {
      console.error('Error adding symbol:', error);
      alert(`Error adding symbol: ${error instanceof Error ? error.message : 'Unknown error'}`);
      setLoading(false);
    }
  };

  const removeSymbol = (symbol: string) => {
    const saved = JSON.parse(localStorage.getItem('watchlist_v2') || '[]');
    const updated = saved.filter((s: any) => s.symbol !== symbol);
    localStorage.setItem('watchlist_v2', JSON.stringify(updated));
    setStocks(stocks.filter(s => s.symbol !== symbol));
  };

  const setAlert = (symbol: string) => {
    if (!alertPrice) return;

    const saved = JSON.parse(localStorage.getItem('watchlist_v2') || '[]');
    const updated = saved.map((s: any) =>
      s.symbol === symbol
        ? { ...s, alertEnabled: true, alertPrice: parseFloat(alertPrice), alertType }
        : s
    );
    localStorage.setItem('watchlist_v2', JSON.stringify(updated));

    if (Notification.permission === 'default') {
      Notification.requestPermission();
    }

    setShowAlertForm(null);
    setAlertPrice('');
    updatePrices(updated);
  };

  const removeAlert = (symbol: string) => {
    const saved = JSON.parse(localStorage.getItem('watchlist_v2') || '[]');
    const updated = saved.map((s: any) =>
      s.symbol === symbol
        ? { ...s, alertEnabled: false, alertPrice: undefined, alertType: undefined }
        : s
    );
    localStorage.setItem('watchlist_v2', JSON.stringify(updated));
    updatePrices(updated);
  };

  const avgChange = stocks.length > 0
    ? stocks.reduce((sum, s) => sum + s.changePercent, 0) / stocks.length
    : 0;
  const gainers = stocks.filter(s => s.changePercent > 0).length;
  const losers = stocks.filter(s => s.changePercent < 0).length;
  const alertsActive = stocks.filter(s => s.alertEnabled).length;

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-green-50 to-slate-50 dark:bg-gradient-to-br dark:from-slate-900 dark:via-slate-800 dark:to-slate-900 p-4 md:p-8">
      <div className="max-w-7xl mx-auto">
        <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-2xl border border-slate-200 dark:border-slate-700 p-6 md:p-8 mb-6">
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center space-x-3">
              <div className="bg-gradient-to-br from-green-600 to-green-700 p-3 rounded-xl">
                <Eye className="h-7 w-7 text-white" />
              </div>
              <div>
                <h1 className="text-2xl md:text-3xl font-bold text-slate-900 dark:text-white">Watchlist</h1>
                <p className="text-slate-600 dark:text-slate-400 text-sm">Monitor stocks with price alerts</p>
              </div>
            </div>
            <div className="flex items-center space-x-3">
              <div className="flex items-center space-x-2 bg-green-500/20 px-4 py-2 rounded-lg border border-green-500/30">
                <div className="h-2 w-2 bg-green-500 rounded-full animate-pulse"></div>
                <span className="text-sm font-medium text-green-600 dark:text-green-400">Live</span>
              </div>
              <button
                onClick={() => updatePrices()}
                disabled={loading}
                className="flex items-center space-x-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-all font-medium disabled:opacity-50"
              >
                <RefreshCw className={`h-5 w-5 ${loading ? 'animate-spin' : ''}`} />
                <span className="hidden md:inline">Refresh</span>
              </button>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
            <div className="bg-gradient-to-br from-blue-50 to-blue-100 dark:from-blue-900/20 dark:to-blue-800/20 rounded-xl p-4 border border-blue-200 dark:border-blue-800">
              <div className="flex items-center space-x-2 mb-2">
                <Eye className="h-5 w-5 text-blue-600 dark:text-blue-400" />
                <span className="text-sm font-medium text-slate-700 dark:text-slate-300">Watching</span>
              </div>
              <div className="text-2xl font-bold text-slate-900 dark:text-white">{stocks.length}</div>
            </div>

            <div className="bg-gradient-to-br from-purple-50 to-purple-100 dark:from-purple-900/20 dark:to-purple-800/20 rounded-xl p-4 border border-purple-200 dark:border-purple-800">
              <div className="flex items-center space-x-2 mb-2">
                <TrendingUp className="h-5 w-5 text-purple-600 dark:text-purple-400" />
                <span className="text-sm font-medium text-slate-700 dark:text-slate-300">Avg Change</span>
              </div>
              <div className={`text-2xl font-bold ${avgChange >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                {avgChange >= 0 ? '+' : ''}{avgChange.toFixed(2)}%
              </div>
            </div>

            <div className="bg-gradient-to-br from-green-50 to-green-100 dark:from-green-900/20 dark:to-green-800/20 rounded-xl p-4 border border-green-200 dark:border-green-800">
              <div className="flex items-center space-x-2 mb-2">
                <TrendingUp className="h-5 w-5 text-green-600 dark:text-green-400" />
                <span className="text-sm font-medium text-slate-700 dark:text-slate-300">Gainers</span>
              </div>
              <div className="text-2xl font-bold text-green-600 dark:text-green-400">{gainers}</div>
            </div>

            <div className="bg-gradient-to-br from-orange-50 to-orange-100 dark:from-orange-900/20 dark:to-orange-800/20 rounded-xl p-4 border border-orange-200 dark:border-orange-800">
              <div className="flex items-center space-x-2 mb-2">
                <Bell className="h-5 w-5 text-orange-600 dark:text-orange-400" />
                <span className="text-sm font-medium text-slate-700 dark:text-slate-300">Alerts Active</span>
              </div>
              <div className="text-2xl font-bold text-slate-900 dark:text-white">{alertsActive}</div>
            </div>
          </div>

          <div className="bg-slate-50 dark:bg-slate-900 rounded-xl p-4 mb-6 border-2 border-slate-200 dark:border-slate-700">
            <div className="flex space-x-3">
              <input
                type="text"
                value={newSymbol}
                onChange={(e) => setNewSymbol(e.target.value.toUpperCase())}
                onKeyDown={(e) => e.key === 'Enter' && addSymbol()}
                placeholder="Add symbol (e.g., AAPL)"
                className="flex-1 px-4 py-3 border-2 border-slate-300 dark:border-slate-600 dark:bg-slate-800 dark:text-white rounded-xl focus:border-green-500 focus:outline-none font-medium"
              />
              <button
                onClick={addSymbol}
                disabled={loading || !newSymbol.trim()}
                className="flex items-center space-x-2 px-6 py-3 bg-green-600 text-white rounded-xl hover:bg-green-700 transition-all font-semibold disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <Plus className="h-5 w-5" />
                <span>Add</span>
              </button>
            </div>
          </div>

          {stocks.length > 0 && (
            <div className="text-sm text-slate-500 dark:text-slate-400 mb-4">
              Last updated: {lastUpdate.toLocaleTimeString()} • Updates every 15 seconds
            </div>
          )}
        </div>

        {loading && stocks.length === 0 ? (
          <div className="grid grid-cols-1 gap-4">
            {[0, 1, 2].map((i) => (
              <div
                key={i}
                className="bg-white dark:bg-slate-800 rounded-xl shadow-lg border border-slate-200 dark:border-slate-700 p-6"
              >
                <div className="flex items-center justify-between mb-4">
                  <Skeleton className="h-8 w-28" />
                  <Skeleton className="h-6 w-20" />
                </div>
                <Skeleton className="h-9 w-40 mb-4" />
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  {[0, 1, 2, 3].map((j) => (
                    <Skeleton key={j} className="h-10 w-full" />
                  ))}
                </div>
              </div>
            ))}
          </div>
        ) : stocks.length === 0 ? (
          <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-2xl border border-slate-200 dark:border-slate-700 p-12 text-center animate-fadeIn">
            <Eye className="h-16 w-16 text-slate-300 dark:text-slate-600 mx-auto mb-4" />
            <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-2">No Stocks in Watchlist</h3>
            <p className="text-slate-600 dark:text-slate-400 mb-6">Add your first stock to start monitoring with price alerts</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4">
            {stocks.map((stock, idx) => (
              <div
                key={stock.symbol}
                style={{ animationDelay: `${idx * 60}ms` }}
                className="bg-white dark:bg-slate-800 rounded-xl shadow-lg border border-slate-200 dark:border-slate-700 p-6 hover:shadow-2xl hover:-translate-y-0.5 transition-all animate-fadeIn"
              >
                <div className="flex items-start justify-between mb-4">
                  <div className="flex-1">
                    <div className="flex items-center space-x-3 mb-2">
                      <h3 className="text-2xl font-bold text-slate-900 dark:text-white">{stock.symbol}</h3>
                      {stock.changePercent >= 0 ? (
                        <div className="flex items-center space-x-1 bg-green-100 dark:bg-green-900/30 px-3 py-1 rounded-full">
                          <TrendingUp className="h-4 w-4 text-green-600 dark:text-green-400" />
                          <span className="text-green-600 dark:text-green-400 font-bold text-sm">
                            +{stock.changePercent.toFixed(2)}%
                          </span>
                        </div>
                      ) : (
                        <div className="flex items-center space-x-1 bg-red-100 dark:bg-red-900/30 px-3 py-1 rounded-full">
                          <TrendingDown className="h-4 w-4 text-red-600 dark:text-red-400" />
                          <span className="text-red-600 dark:text-red-400 font-bold text-sm">
                            {stock.changePercent.toFixed(2)}%
                          </span>
                        </div>
                      )}
                      {stock.alertEnabled && (
                        <div className="flex items-center space-x-1 bg-orange-100 dark:bg-orange-900/30 px-3 py-1 rounded-full">
                          <Bell className="h-4 w-4 text-orange-600 dark:text-orange-400" />
                          <span className="text-orange-600 dark:text-orange-400 text-sm font-semibold">
                            Alert @ ${stock.alertPrice}
                          </span>
                        </div>
                      )}
                    </div>
                    <div className="flex items-baseline space-x-3">
                      <span className="text-3xl font-bold text-slate-900 dark:text-white">
                        ${stock.price.toFixed(2)}
                      </span>
                      <span className={`text-lg font-semibold ${
                        stock.change >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'
                      }`}>
                        {stock.change >= 0 ? '+' : ''}${stock.change.toFixed(2)}
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center space-x-2">
                    {stock.alertEnabled ? (
                      <button
                        onClick={() => removeAlert(stock.symbol)}
                        className="p-2 text-orange-600 hover:bg-orange-50 dark:hover:bg-orange-900/20 rounded-lg transition-colors"
                        title="Remove alert"
                      >
                        <BellOff className="h-5 w-5" />
                      </button>
                    ) : (
                      <button
                        onClick={() => setShowAlertForm(stock.symbol)}
                        className="p-2 text-slate-600 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg transition-colors"
                        title="Set alert"
                      >
                        <Bell className="h-5 w-5" />
                      </button>
                    )}
                    <button
                      onClick={() => removeSymbol(stock.symbol)}
                      className="p-2 text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors"
                    >
                      <X className="h-5 w-5" />
                    </button>
                  </div>
                </div>

                {showAlertForm === stock.symbol && (
                  <div className="bg-slate-50 dark:bg-slate-900 rounded-lg p-4 mb-4 border border-slate-200 dark:border-slate-700">
                    <h4 className="font-semibold text-slate-900 dark:text-white mb-3">Set Price Alert</h4>
                    <div className="grid grid-cols-2 gap-3 mb-3">
                      <input
                        type="number"
                        value={alertPrice}
                        onChange={(e) => setAlertPrice(e.target.value)}
                        placeholder="Alert price"
                        step="0.01"
                        className="px-4 py-2 border-2 border-slate-300 dark:border-slate-600 dark:bg-slate-800 dark:text-white rounded-lg focus:border-orange-500 focus:outline-none"
                      />
                      <select
                        value={alertType}
                        onChange={(e) => setAlertType(e.target.value as 'above' | 'below')}
                        className="px-4 py-2 border-2 border-slate-300 dark:border-slate-600 dark:bg-slate-800 dark:text-white rounded-lg focus:border-orange-500 focus:outline-none"
                      >
                        <option value="above">Price Above</option>
                        <option value="below">Price Below</option>
                      </select>
                    </div>
                    <div className="flex space-x-2">
                      <button
                        onClick={() => setAlert(stock.symbol)}
                        className="flex-1 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700 transition-all font-semibold text-sm"
                      >
                        Set Alert
                      </button>
                      <button
                        onClick={() => setShowAlertForm(null)}
                        className="px-4 py-2 bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-300 rounded-lg hover:bg-slate-300 dark:hover:bg-slate-600 transition-all font-semibold text-sm"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}

                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div>
                    <div className="text-xs text-slate-500 dark:text-slate-400 mb-1">Open</div>
                    <div className="font-semibold text-slate-900 dark:text-white">${stock.open.toFixed(2)}</div>
                  </div>
                  <div>
                    <div className="text-xs text-slate-500 dark:text-slate-400 mb-1">High</div>
                    <div className="font-semibold text-green-600 dark:text-green-400">${stock.high.toFixed(2)}</div>
                  </div>
                  <div>
                    <div className="text-xs text-slate-500 dark:text-slate-400 mb-1">Low</div>
                    <div className="font-semibold text-red-600 dark:text-red-400">${stock.low.toFixed(2)}</div>
                  </div>
                  <div>
                    <div className="text-xs text-slate-500 dark:text-slate-400 mb-1">Volume</div>
                    <div className="font-semibold text-slate-900 dark:text-white">
                      {(stock.volume / 1000000).toFixed(2)}M
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        <div className="mt-6 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-xl p-4">
          <p className="text-sm text-green-800 dark:text-green-300">
            <strong>Real-Time Monitoring:</strong> Watchlist updates every 15 seconds with real Alpaca data.
            Set price alerts to get notified when stocks hit your target prices.
          </p>
        </div>
      </div>
    </div>
  );
}
