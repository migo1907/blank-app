import { useState, useEffect, useCallback } from 'react';
import {
  Filter, TrendingUp, TrendingDown, Download, Save, Search, X,
  ChevronDown, ChevronUp, BarChart3, DollarSign, Activity, Percent,
  Calendar, Target, AlertCircle, RefreshCw, Zap, Eye, Radar
} from 'lucide-react';
import { supabase } from '../lib/supabase';
import { technicalIndicatorsService } from '../services/technicalIndicatorsService';
import QuantFlowScanner from '../components/QuantFlowScanner';

interface ScreenerFilters {
  priceMin?: number;
  priceMax?: number;
  marketCapMin?: number;
  marketCapMax?: number;
  volumeMin?: number;
  peRatioMin?: number;
  peRatioMax?: number;
  dividendYieldMin?: number;
  betaMin?: number;
  betaMax?: number;
  shortInterestMin?: number;
  shortInterestMax?: number;
  rsiMin?: number;
  rsiMax?: number;
  signal?: string[];
  sectors?: string[];
  exchanges?: string[];
}

interface StockResult {
  symbol: string;
  name: string;
  price: number;
  change: number;
  changePercent: number;
  volume: number;
  marketCap: number;
  peRatio: number;
  dividendYield: number;
  beta: number;
  shortInterest: number;
  rsi14: number;
  signal: string;
  sector: string;
  exchange: string;
}

export default function AdvancedScreener() {
  const [filters, setFilters] = useState<ScreenerFilters>({});
  const [results, setResults] = useState<StockResult[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [expandedFilters, setExpandedFilters] = useState<Set<string>>(new Set(['price', 'technical']));
  const [sortField, setSortField] = useState<string>('marketCap');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('desc');
  const [searchQuery, setSearchQuery] = useState('');
  const [showQuantFlow, setShowQuantFlow] = useState(false);

  const sectors = ['Technology', 'Healthcare', 'Financial', 'Consumer', 'Industrial', 'Energy', 'Materials', 'Utilities', 'Real Estate'];
  const exchanges = ['NASDAQ', 'NYSE', 'AMEX'];
  const signals = ['strong_buy', 'buy', 'neutral', 'sell', 'strong_sell'];

  const toggleFilterSection = (section: string) => {
    setExpandedFilters(prev => {
      const next = new Set(prev);
      if (next.has(section)) {
        next.delete(section);
      } else {
        next.add(section);
      }
      return next;
    });
  };

  const applyFilters = useCallback(async () => {
    setIsLoading(true);

    try {
      let query = supabase
        .from('stock_screener_data')
        .select('*');

      if (filters.priceMin) query = query.gte('price', filters.priceMin);
      if (filters.priceMax) query = query.lte('price', filters.priceMax);
      if (filters.marketCapMin) query = query.gte('market_cap', filters.marketCapMin);
      if (filters.marketCapMax) query = query.lte('market_cap', filters.marketCapMax);
      if (filters.volumeMin) query = query.gte('volume', filters.volumeMin);
      if (filters.peRatioMin) query = query.gte('pe_ratio', filters.peRatioMin);
      if (filters.peRatioMax) query = query.lte('pe_ratio', filters.peRatioMax);
      if (filters.dividendYieldMin) query = query.gte('dividend_yield', filters.dividendYieldMin);
      if (filters.betaMin) query = query.gte('beta', filters.betaMin);
      if (filters.betaMax) query = query.lte('beta', filters.betaMax);
      if (filters.shortInterestMin) query = query.gte('short_interest', filters.shortInterestMin);
      if (filters.shortInterestMax) query = query.lte('short_interest', filters.shortInterestMax);
      if (filters.rsiMin) query = query.gte('rsi_14', filters.rsiMin);
      if (filters.rsiMax) query = query.lte('rsi_14', filters.rsiMax);

      if (filters.signal && filters.signal.length > 0) {
        query = query.in('signal', filters.signal);
      }

      if (filters.sectors && filters.sectors.length > 0) {
        query = query.in('sector', filters.sectors);
      }

      if (filters.exchanges && filters.exchanges.length > 0) {
        query = query.in('exchange', filters.exchanges);
      }

      if (searchQuery) {
        query = query.or(`symbol.ilike.%${searchQuery}%,name.ilike.%${searchQuery}%`);
      }

      query = query.order(sortField, { ascending: sortDirection === 'asc' }).limit(100);

      const { data, error } = await query;

      if (error) throw error;

      const formatted: StockResult[] = (data || []).map(row => ({
        symbol: row.symbol || '',
        name: row.name || '',
        price: parseFloat(row.price) || 0,
        change: parseFloat(row.change) || 0,
        changePercent: parseFloat(row.change_percent) || 0,
        volume: parseInt(row.volume) || 0,
        marketCap: parseInt(row.market_cap) || 0,
        peRatio: parseFloat(row.pe_ratio) || 0,
        dividendYield: parseFloat(row.dividend_yield) || 0,
        beta: parseFloat(row.beta) || 0,
        shortInterest: parseFloat(row.short_interest) || 0,
        rsi14: parseFloat(row.rsi_14) || 50,
        signal: row.signal || 'neutral',
        sector: row.sector || 'Unknown',
        exchange: row.exchange || 'Unknown',
      }));

      setResults(formatted);
    } catch (error) {
      console.error('Error applying filters:', error);
      generateMockResults();
    } finally {
      setIsLoading(false);
    }
  }, [filters, sortField, sortDirection, searchQuery]);

  const generateMockResults = () => {
    const symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'NVDA', 'META', 'AMD', 'NFLX', 'INTC'];
    const mockResults: StockResult[] = symbols.map(symbol => {
      const price = Math.random() * 500 + 50;
      const change = (Math.random() - 0.5) * 10;
      return {
        symbol,
        name: `${symbol} Corporation`,
        price,
        change,
        changePercent: (change / price) * 100,
        volume: Math.floor(Math.random() * 50000000) + 1000000,
        marketCap: Math.floor(Math.random() * 2000000000000) + 100000000000,
        peRatio: Math.random() * 40 + 5,
        dividendYield: Math.random() * 3,
        beta: Math.random() * 2 + 0.5,
        shortInterest: Math.random() * 10,
        rsi14: Math.random() * 100,
        signal: signals[Math.floor(Math.random() * signals.length)],
        sector: sectors[Math.floor(Math.random() * sectors.length)],
        exchange: exchanges[Math.floor(Math.random() * exchanges.length)],
      };
    });
    setResults(mockResults);
  };

  useEffect(() => {
    applyFilters();
  }, [applyFilters]);

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
      case 'strong_buy': return 'bg-green-600 text-white';
      case 'buy': return 'bg-green-500 text-white';
      case 'neutral': return 'bg-slate-400 text-white';
      case 'sell': return 'bg-red-500 text-white';
      case 'strong_sell': return 'bg-red-600 text-white';
      default: return 'bg-slate-300 text-slate-700';
    }
  };

  const getSignalLabel = (signal: string): string => {
    return signal.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
  };

  const exportToCSV = () => {
    const headers = ['Symbol', 'Name', 'Price', 'Change%', 'Volume', 'Market Cap', 'P/E', 'Div Yield', 'Beta', 'Short%', 'RSI', 'Signal'];
    const rows = results.map(r => [
      r.symbol, r.name, r.price.toFixed(2), r.changePercent.toFixed(2),
      r.volume, r.marketCap, r.peRatio.toFixed(2), r.dividendYield.toFixed(2),
      r.beta.toFixed(2), r.shortInterest.toFixed(2), r.rsi14.toFixed(2), r.signal
    ]);

    const csv = [headers, ...rows].map(row => row.join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `screener_results_${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const clearFilters = () => {
    setFilters({});
    setSearchQuery('');
  };

  return (
    <div className="min-h-screen bg-slate-50 py-8">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="mb-8">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center space-x-3">
              <Filter className="h-8 w-8 text-daman-blue-600" />
              <h1 className="text-3xl font-bold text-slate-900">Advanced Stock Screener</h1>
            </div>
            <div className="flex items-center space-x-3">
              <button
                onClick={() => setShowQuantFlow(true)}
                className="flex items-center space-x-2 px-4 py-2 bg-gradient-to-r from-purple-600 to-indigo-600 text-white rounded-lg hover:from-purple-700 hover:to-indigo-700 transition-all shadow-lg"
              >
                <Radar className="h-4 w-4" />
                <span>QuantFlow Pro</span>
              </button>
              <button
                onClick={exportToCSV}
                className="flex items-center space-x-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-all"
              >
                <Download className="h-4 w-4" />
                <span>Export CSV</span>
              </button>
              <button
                className="flex items-center space-x-2 px-4 py-2 bg-daman-blue-600 text-white rounded-lg hover:bg-daman-blue-700 transition-all"
              >
                <Save className="h-4 w-4" />
                <span>Save Preset</span>
              </button>
            </div>
          </div>
          <p className="text-slate-600">
            Filter stocks using technical indicators, fundamentals, and custom criteria
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          {/* Filters Sidebar */}
          <div className="lg:col-span-1">
            <div className="bg-white rounded-xl shadow-md border border-slate-200 p-6 sticky top-4">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-bold text-slate-900">Filters</h2>
                <button
                  onClick={clearFilters}
                  className="text-sm text-daman-blue-600 hover:text-daman-blue-700 flex items-center space-x-1"
                >
                  <X className="h-4 w-4" />
                  <span>Clear</span>
                </button>
              </div>

              {/* Search */}
              <div className="mb-6">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-slate-400" />
                  <input
                    type="text"
                    placeholder="Search symbol or name..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full pl-10 pr-4 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-daman-blue-500"
                  />
                </div>
              </div>

              {/* Price Filter */}
              <div className="mb-4">
                <button
                  onClick={() => toggleFilterSection('price')}
                  className="w-full flex items-center justify-between p-3 bg-slate-50 rounded-lg hover:bg-slate-100 transition-all"
                >
                  <div className="flex items-center space-x-2">
                    <DollarSign className="h-4 w-4 text-daman-blue-600" />
                    <span className="font-semibold text-sm">Price Range</span>
                  </div>
                  {expandedFilters.has('price') ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                </button>
                {expandedFilters.has('price') && (
                  <div className="mt-2 space-y-2 pl-2">
                    <input
                      type="number"
                      placeholder="Min Price"
                      value={filters.priceMin || ''}
                      onChange={(e) => setFilters({ ...filters, priceMin: Number(e.target.value) })}
                      className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm"
                    />
                    <input
                      type="number"
                      placeholder="Max Price"
                      value={filters.priceMax || ''}
                      onChange={(e) => setFilters({ ...filters, priceMax: Number(e.target.value) })}
                      className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm"
                    />
                  </div>
                )}
              </div>

              {/* Market Cap Filter */}
              <div className="mb-4">
                <button
                  onClick={() => toggleFilterSection('marketcap')}
                  className="w-full flex items-center justify-between p-3 bg-slate-50 rounded-lg hover:bg-slate-100 transition-all"
                >
                  <div className="flex items-center space-x-2">
                    <BarChart3 className="h-4 w-4 text-daman-blue-600" />
                    <span className="font-semibold text-sm">Market Cap</span>
                  </div>
                  {expandedFilters.has('marketcap') ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                </button>
                {expandedFilters.has('marketcap') && (
                  <div className="mt-2 space-y-2 pl-2">
                    <input
                      type="number"
                      placeholder="Min (in billions)"
                      value={filters.marketCapMin ? filters.marketCapMin / 1e9 : ''}
                      onChange={(e) => setFilters({ ...filters, marketCapMin: Number(e.target.value) * 1e9 })}
                      className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm"
                    />
                    <input
                      type="number"
                      placeholder="Max (in billions)"
                      value={filters.marketCapMax ? filters.marketCapMax / 1e9 : ''}
                      onChange={(e) => setFilters({ ...filters, marketCapMax: Number(e.target.value) * 1e9 })}
                      className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm"
                    />
                  </div>
                )}
              </div>

              {/* Technical Indicators */}
              <div className="mb-4">
                <button
                  onClick={() => toggleFilterSection('technical')}
                  className="w-full flex items-center justify-between p-3 bg-slate-50 rounded-lg hover:bg-slate-100 transition-all"
                >
                  <div className="flex items-center space-x-2">
                    <Activity className="h-4 w-4 text-daman-blue-600" />
                    <span className="font-semibold text-sm">Technical</span>
                  </div>
                  {expandedFilters.has('technical') ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                </button>
                {expandedFilters.has('technical') && (
                  <div className="mt-2 space-y-2 pl-2">
                    <div className="text-xs font-semibold text-slate-600 mb-1">RSI (14)</div>
                    <input
                      type="number"
                      placeholder="Min RSI"
                      value={filters.rsiMin || ''}
                      onChange={(e) => setFilters({ ...filters, rsiMin: Number(e.target.value) })}
                      className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm"
                    />
                    <input
                      type="number"
                      placeholder="Max RSI"
                      value={filters.rsiMax || ''}
                      onChange={(e) => setFilters({ ...filters, rsiMax: Number(e.target.value) })}
                      className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm"
                    />
                    <div className="text-xs font-semibold text-slate-600 mb-1 mt-3">Signal</div>
                    {signals.map(sig => (
                      <label key={sig} className="flex items-center space-x-2 text-sm">
                        <input
                          type="checkbox"
                          checked={filters.signal?.includes(sig)}
                          onChange={(e) => {
                            const current = filters.signal || [];
                            setFilters({
                              ...filters,
                              signal: e.target.checked
                                ? [...current, sig]
                                : current.filter(s => s !== sig)
                            });
                          }}
                          className="rounded border-slate-300"
                        />
                        <span>{getSignalLabel(sig)}</span>
                      </label>
                    ))}
                  </div>
                )}
              </div>

              {/* Fundamentals */}
              <div className="mb-4">
                <button
                  onClick={() => toggleFilterSection('fundamentals')}
                  className="w-full flex items-center justify-between p-3 bg-slate-50 rounded-lg hover:bg-slate-100 transition-all"
                >
                  <div className="flex items-center space-x-2">
                    <Percent className="h-4 w-4 text-daman-blue-600" />
                    <span className="font-semibold text-sm">Fundamentals</span>
                  </div>
                  {expandedFilters.has('fundamentals') ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                </button>
                {expandedFilters.has('fundamentals') && (
                  <div className="mt-2 space-y-3 pl-2">
                    <div>
                      <div className="text-xs font-semibold text-slate-600 mb-1">P/E Ratio</div>
                      <div className="flex space-x-2">
                        <input
                          type="number"
                          placeholder="Min"
                          value={filters.peRatioMin || ''}
                          onChange={(e) => setFilters({ ...filters, peRatioMin: Number(e.target.value) })}
                          className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm"
                        />
                        <input
                          type="number"
                          placeholder="Max"
                          value={filters.peRatioMax || ''}
                          onChange={(e) => setFilters({ ...filters, peRatioMax: Number(e.target.value) })}
                          className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm"
                        />
                      </div>
                    </div>
                    <div>
                      <div className="text-xs font-semibold text-slate-600 mb-1">Dividend Yield (%)</div>
                      <input
                        type="number"
                        placeholder="Min Yield"
                        value={filters.dividendYieldMin || ''}
                        onChange={(e) => setFilters({ ...filters, dividendYieldMin: Number(e.target.value) })}
                        className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm"
                      />
                    </div>
                    <div>
                      <div className="text-xs font-semibold text-slate-600 mb-1">Beta</div>
                      <div className="flex space-x-2">
                        <input
                          type="number"
                          placeholder="Min"
                          value={filters.betaMin || ''}
                          onChange={(e) => setFilters({ ...filters, betaMin: Number(e.target.value) })}
                          className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm"
                        />
                        <input
                          type="number"
                          placeholder="Max"
                          value={filters.betaMax || ''}
                          onChange={(e) => setFilters({ ...filters, betaMax: Number(e.target.value) })}
                          className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm"
                        />
                      </div>
                    </div>
                    <div>
                      <div className="text-xs font-semibold text-slate-600 mb-1">Short Interest (%)</div>
                      <div className="flex space-x-2">
                        <input
                          type="number"
                          placeholder="Min"
                          value={filters.shortInterestMin || ''}
                          onChange={(e) => setFilters({ ...filters, shortInterestMin: Number(e.target.value) })}
                          className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm"
                        />
                        <input
                          type="number"
                          placeholder="Max"
                          value={filters.shortInterestMax || ''}
                          onChange={(e) => setFilters({ ...filters, shortInterestMax: Number(e.target.value) })}
                          className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm"
                        />
                      </div>
                    </div>
                  </div>
                )}
              </div>

              <button
                onClick={applyFilters}
                disabled={isLoading}
                className="w-full mt-6 flex items-center justify-center space-x-2 bg-daman-blue-600 text-white px-4 py-3 rounded-lg hover:bg-daman-blue-700 transition-all disabled:opacity-50 font-semibold"
              >
                {isLoading ? <RefreshCw className="h-5 w-5 animate-spin" /> : <Filter className="h-5 w-5" />}
                <span>{isLoading ? 'Filtering...' : 'Apply Filters'}</span>
              </button>
            </div>
          </div>

          {/* Results Table */}
          <div className="lg:col-span-3">
            <div className="bg-white rounded-xl shadow-md border border-slate-200 overflow-hidden">
              <div className="p-6 border-b border-slate-200">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-xl font-bold text-slate-900">Screener Results</h2>
                    <p className="text-sm text-slate-600 mt-1">{results.length} stocks found</p>
                  </div>
                  <div className="flex items-center space-x-2 text-sm text-slate-600">
                    <Eye className="h-4 w-4" />
                    <span>Showing top 100 results</span>
                  </div>
                </div>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-slate-50 border-b border-slate-200">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-slate-700 uppercase">Symbol</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-slate-700 uppercase">Name</th>
                      <th className="px-4 py-3 text-right text-xs font-semibold text-slate-700 uppercase">Price</th>
                      <th className="px-4 py-3 text-right text-xs font-semibold text-slate-700 uppercase">Change %</th>
                      <th className="px-4 py-3 text-right text-xs font-semibold text-slate-700 uppercase">Volume</th>
                      <th className="px-4 py-3 text-right text-xs font-semibold text-slate-700 uppercase">Market Cap</th>
                      <th className="px-4 py-3 text-right text-xs font-semibold text-slate-700 uppercase">P/E</th>
                      <th className="px-4 py-3 text-right text-xs font-semibold text-slate-700 uppercase">RSI</th>
                      <th className="px-4 py-3 text-center text-xs font-semibold text-slate-700 uppercase">Signal</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200">
                    {results.map((stock, index) => (
                      <tr key={index} className="hover:bg-slate-50 transition-colors cursor-pointer">
                        <td className="px-4 py-3">
                          <div className="font-bold text-sm text-slate-900">{stock.symbol}</div>
                          <div className="text-xs text-slate-500">{stock.exchange}</div>
                        </td>
                        <td className="px-4 py-3">
                          <div className="text-sm text-slate-700">{stock.name}</div>
                          <div className="text-xs text-slate-500">{stock.sector}</div>
                        </td>
                        <td className="px-4 py-3 text-right">
                          <div className="text-sm font-semibold text-slate-900">
                            ${stock.price.toFixed(2)}
                          </div>
                        </td>
                        <td className="px-4 py-3 text-right">
                          <div className={`text-sm font-bold ${stock.changePercent >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                            {stock.changePercent >= 0 ? '+' : ''}{stock.changePercent.toFixed(2)}%
                          </div>
                        </td>
                        <td className="px-4 py-3 text-right">
                          <div className="text-sm text-slate-700">{formatVolume(stock.volume)}</div>
                        </td>
                        <td className="px-4 py-3 text-right">
                          <div className="text-sm text-slate-700">{formatMarketCap(stock.marketCap)}</div>
                        </td>
                        <td className="px-4 py-3 text-right">
                          <div className="text-sm text-slate-700">{stock.peRatio.toFixed(2)}</div>
                        </td>
                        <td className="px-4 py-3 text-right">
                          <div className="text-sm font-semibold text-slate-900">{stock.rsi14.toFixed(0)}</div>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex justify-center">
                            <span className={`px-2 py-1 rounded-md text-xs font-semibold ${getSignalColor(stock.signal)}`}>
                              {getSignalLabel(stock.signal)}
                            </span>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {results.length === 0 && !isLoading && (
                <div className="p-12 text-center">
                  <AlertCircle className="h-12 w-12 text-slate-300 mx-auto mb-3" />
                  <p className="text-slate-600">No stocks match your filter criteria</p>
                  <p className="text-sm text-slate-500 mt-1">Try adjusting your filters</p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* QuantFlow Pro Scanner Modal */}
      {showQuantFlow && (
        <QuantFlowScanner onClose={() => setShowQuantFlow(false)} />
      )}
    </div>
  );
}
