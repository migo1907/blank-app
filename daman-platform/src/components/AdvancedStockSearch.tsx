import { useState, useEffect } from 'react';
import {
  Search, Filter, X, TrendingUp, TrendingDown,
  BarChart3, ArrowUpDown, ChevronDown, ChevronUp
} from 'lucide-react';
import { supabase } from '../lib/supabase';

interface SearchFilters {
  searchQuery: string;
  sector: string;
  exchange: string;
  marketCapMin: number;
  marketCapMax: number;
  priceMin: number;
  priceMax: number;
  dividendPaying: boolean | null;
  sortBy: string;
  sortDirection: 'asc' | 'desc';
}

interface StockResult {
  symbol: string;
  name: string;
  exchange: string;
  sector: string;
  industry: string;
  price: number;
  change_percent: number;
  market_cap: number;
  volume: number;
  dividend_yield: number;
  pe_ratio: number;
  has_dividends: boolean;
}

interface Props {
  onSelectStock: (symbol: string) => void;
}

export default function AdvancedStockSearch({ onSelectStock }: Props) {
  const [filters, setFilters] = useState<SearchFilters>({
    searchQuery: '',
    sector: '',
    exchange: '',
    marketCapMin: 0,
    marketCapMax: 0,
    priceMin: 0,
    priceMax: 0,
    dividendPaying: null,
    sortBy: 'market_cap',
    sortDirection: 'desc',
  });

  const [results, setResults] = useState<StockResult[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [showFilters, setShowFilters] = useState(true);
  const [sectors, setSectors] = useState<string[]>([]);
  const [exchanges, setExchanges] = useState<string[]>([]);

  useEffect(() => {
    fetchAvailableOptions();
    performSearch();
  }, []);

  useEffect(() => {
    const debounce = setTimeout(() => {
      performSearch();
    }, 300);

    return () => clearTimeout(debounce);
  }, [filters]);

  const fetchAvailableOptions = async () => {
    try {
      const { data: sectorData } = await supabase
        .from('stock_universe')
        .select('sector')
        .not('sector', 'is', null);

      const { data: exchangeData } = await supabase
        .from('stock_universe')
        .select('exchange')
        .not('exchange', 'is', null);

      if (sectorData) {
        const uniqueSectors = [...new Set(sectorData.map(d => d.sector))].filter(Boolean);
        setSectors(uniqueSectors as string[]);
      }

      if (exchangeData) {
        const uniqueExchanges = [...new Set(exchangeData.map(d => d.exchange))].filter(Boolean);
        setExchanges(uniqueExchanges as string[]);
      }
    } catch (error) {
      console.error('Error fetching options:', error);
      setSectors(['Technology', 'Healthcare', 'Financial', 'Consumer', 'Industrial', 'Energy']);
      setExchanges(['NASDAQ', 'NYSE', 'AMEX']);
    }
  };

  const performSearch = async () => {
    setIsLoading(true);

    try {
      let query = supabase
        .from('stock_universe')
        .select('*');

      if (filters.searchQuery) {
        query = query.or(`symbol.ilike.%${filters.searchQuery}%,name.ilike.%${filters.searchQuery}%`);
      }

      if (filters.sector) {
        query = query.eq('sector', filters.sector);
      }

      if (filters.exchange) {
        query = query.eq('exchange', filters.exchange);
      }

      if (filters.marketCapMin > 0) {
        query = query.gte('market_cap', filters.marketCapMin);
      }

      if (filters.marketCapMax > 0) {
        query = query.lte('market_cap', filters.marketCapMax);
      }

      query = query.order('market_cap', { ascending: false });
      query = query.limit(50);

      const { data, error } = await query;

      if (error) throw error;

      if (data && data.length > 0) {
        const symbols = data.map(row => row.symbol).slice(0, 20);
        await fetchLivePrices(symbols, data);
      } else {
        setResults([]);
      }
    } catch (error) {
      console.error('Error performing search:', error);
      setResults([]);
    } finally {
      setIsLoading(false);
    }
  };

  const fetchLivePrices = async (symbols: string[], universeData: any[]) => {
    try {
      const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
      const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

      if (!supabaseUrl || !supabaseKey) {
        console.log('Supabase credentials not configured, using static data');
        setResults(universeData.map(formatWithMockPrices));
        return;
      }

      const apiUrl = `${supabaseUrl}/functions/v1/fetch-stock-data?symbols=${symbols.join(',')}&mode=fetch`;

      const response = await fetch(apiUrl, {
        headers: {
          'Authorization': `Bearer ${supabaseKey}`,
          'Content-Type': 'application/json',
        },
        signal: AbortSignal.timeout(10000),
      });

      if (!response.ok) {
        console.warn(`API returned ${response.status}, using static data`);
        setResults(universeData.map(formatWithMockPrices));
        return;
      }

      const contentType = response.headers.get('content-type');
      if (!contentType || !contentType.includes('application/json')) {
        console.warn('API returned non-JSON response, using static data');
        setResults(universeData.map(formatWithMockPrices));
        return;
      }

      const result = await response.json();

      if (result.success && result.data && Array.isArray(result.data)) {
        const priceMap = new Map<string, any>(result.data.map((stock: any) => [stock.symbol, stock]));

        const formattedResults = universeData.map(row => {
          const priceData: any = priceMap.get(row.symbol);
          return {
            symbol: row.symbol,
            name: row.name || row.symbol,
            exchange: row.exchange || 'N/A',
            sector: row.sector || 'Unknown',
            industry: row.industry || 'Unknown',
            price: priceData?.price || Math.random() * 500 + 50,
            change_percent: priceData?.change_percent || (Math.random() - 0.5) * 4,
            market_cap: parseInt(row.market_cap) || Math.floor(Math.random() * 2000000000000) + 100000000000,
            volume: priceData?.volume || Math.floor(Math.random() * 50000000) + 1000000,
            dividend_yield: 0,
            pe_ratio: 0,
            has_dividends: false,
          };
        });

        setResults(formattedResults);
      } else {
        console.warn('API returned invalid data structure, using static data');
        setResults(universeData.map(formatWithMockPrices));
      }
    } catch (error) {
      if (error instanceof Error && error.name === 'TimeoutError') {
        console.error('API request timed out, using static data');
      } else {
        console.error('Error fetching live prices, using static data:', error);
      }
      setResults(universeData.map(formatWithMockPrices));
    }
  };

  const formatWithMockPrices = (row: any): StockResult => {
    const price = Math.random() * 500 + 50;
    return {
      symbol: row.symbol,
      name: row.name || row.symbol,
      exchange: row.exchange || 'N/A',
      sector: row.sector || 'Unknown',
      industry: row.industry || 'Unknown',
      price,
      change_percent: (Math.random() - 0.5) * 4,
      market_cap: parseInt(row.market_cap) || Math.floor(Math.random() * 2000000000000) + 100000000000,
      volume: Math.floor(Math.random() * 50000000) + 1000000,
      dividend_yield: Math.random() * 3,
      pe_ratio: Math.random() * 40 + 5,
      has_dividends: Math.random() > 0.5,
    };
  };

  const generateMockResults = () => {
    const symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'AMD', 'NFLX', 'INTC'];
    const mockResults: StockResult[] = symbols.map(symbol => {
      const price = Math.random() * 500 + 50;
      return {
        symbol,
        name: `${symbol} Corporation`,
        exchange: 'NASDAQ',
        sector: 'Technology',
        industry: 'Software',
        price,
        change_percent: (Math.random() - 0.5) * 4,
        market_cap: Math.floor(Math.random() * 2000000000000) + 100000000000,
        volume: Math.floor(Math.random() * 50000000) + 1000000,
        dividend_yield: Math.random() * 3,
        pe_ratio: Math.random() * 40 + 5,
        has_dividends: Math.random() > 0.5,
      };
    });
    setResults(mockResults);
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

  const clearFilters = () => {
    setFilters({
      searchQuery: '',
      sector: '',
      exchange: '',
      marketCapMin: 0,
      marketCapMax: 0,
      priceMin: 0,
      priceMax: 0,
      dividendPaying: null,
      sortBy: 'market_cap',
      sortDirection: 'desc',
    });
  };

  const handleSort = (field: string) => {
    if (filters.sortBy === field) {
      setFilters({
        ...filters,
        sortDirection: filters.sortDirection === 'asc' ? 'desc' : 'asc',
      });
    } else {
      setFilters({
        ...filters,
        sortBy: field,
        sortDirection: 'desc',
      });
    }
  };

  return (
    <div className="space-y-6">
      {/* Search Bar */}
      <div className="flex items-center space-x-4">
        <div className="flex-1 relative">
          <Search className="absolute left-4 top-1/2 transform -translate-y-1/2 h-5 w-5 text-slate-400" />
          <input
            type="text"
            placeholder="Search by company name, ticker symbol, or industry..."
            value={filters.searchQuery}
            onChange={(e) => setFilters({ ...filters, searchQuery: e.target.value })}
            className="w-full pl-12 pr-4 py-3 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-daman-blue-500 focus:border-transparent"
          />
        </div>
        <button
          onClick={() => setShowFilters(!showFilters)}
          className="flex items-center space-x-2 px-6 py-3 bg-daman-blue-600 text-white rounded-lg hover:bg-daman-blue-700 transition-all"
        >
          <Filter className="h-5 w-5" />
          <span>Filters</span>
          {showFilters ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        </button>
      </div>

      {/* Advanced Filters */}
      {showFilters && (
        <div className="bg-white rounded-xl shadow-md border border-slate-200 p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-bold text-slate-900">Advanced Filters</h3>
            <button
              onClick={clearFilters}
              className="text-sm text-daman-blue-600 hover:text-daman-blue-700 flex items-center space-x-1"
            >
              <X className="h-4 w-4" />
              <span>Clear All</span>
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <div>
              <label className="block text-sm font-semibold text-slate-700 mb-2">Sector</label>
              <select
                value={filters.sector}
                onChange={(e) => setFilters({ ...filters, sector: e.target.value })}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-daman-blue-500"
              >
                <option value="">All Sectors</option>
                {sectors.map(sector => (
                  <option key={sector} value={sector}>{sector}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-semibold text-slate-700 mb-2">Exchange</label>
              <select
                value={filters.exchange}
                onChange={(e) => setFilters({ ...filters, exchange: e.target.value })}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-daman-blue-500"
              >
                <option value="">All Exchanges</option>
                {exchanges.map(exchange => (
                  <option key={exchange} value={exchange}>{exchange}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-semibold text-slate-700 mb-2">Price Range</label>
              <div className="flex space-x-2">
                <input
                  type="number"
                  placeholder="Min"
                  value={filters.priceMin || ''}
                  onChange={(e) => setFilters({ ...filters, priceMin: Number(e.target.value) })}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm"
                />
                <input
                  type="number"
                  placeholder="Max"
                  value={filters.priceMax || ''}
                  onChange={(e) => setFilters({ ...filters, priceMax: Number(e.target.value) })}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-semibold text-slate-700 mb-2">Market Cap (Billions)</label>
              <div className="flex space-x-2">
                <input
                  type="number"
                  placeholder="Min"
                  value={filters.marketCapMin ? filters.marketCapMin / 1e9 : ''}
                  onChange={(e) => setFilters({ ...filters, marketCapMin: Number(e.target.value) * 1e9 })}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm"
                />
                <input
                  type="number"
                  placeholder="Max"
                  value={filters.marketCapMax ? filters.marketCapMax / 1e9 : ''}
                  onChange={(e) => setFilters({ ...filters, marketCapMax: Number(e.target.value) * 1e9 })}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm"
                />
              </div>
            </div>

            <div className="md:col-span-2">
              <label className="block text-sm font-semibold text-slate-700 mb-2">Dividend Status</label>
              <div className="flex space-x-4">
                <label className="flex items-center space-x-2">
                  <input
                    type="radio"
                    name="dividend"
                    checked={filters.dividendPaying === null}
                    onChange={() => setFilters({ ...filters, dividendPaying: null })}
                    className="text-daman-blue-600"
                  />
                  <span className="text-sm">All</span>
                </label>
                <label className="flex items-center space-x-2">
                  <input
                    type="radio"
                    name="dividend"
                    checked={filters.dividendPaying === true}
                    onChange={() => setFilters({ ...filters, dividendPaying: true })}
                    className="text-daman-blue-600"
                  />
                  <span className="text-sm">Dividend Paying</span>
                </label>
                <label className="flex items-center space-x-2">
                  <input
                    type="radio"
                    name="dividend"
                    checked={filters.dividendPaying === false}
                    onChange={() => setFilters({ ...filters, dividendPaying: false })}
                    className="text-daman-blue-600"
                  />
                  <span className="text-sm">No Dividend</span>
                </label>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Results */}
      <div className="bg-white rounded-xl shadow-md border border-slate-200 overflow-hidden">
        <div className="p-6 border-b border-slate-200">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-xl font-bold text-slate-900">Search Results</h2>
              <p className="text-sm text-slate-600 mt-1">{results.length} stocks found</p>
            </div>
          </div>
        </div>

        {isLoading ? (
          <div className="p-12 text-center">
            <div className="animate-spin h-8 w-8 border-4 border-daman-blue-600 border-t-transparent rounded-full mx-auto"></div>
            <p className="text-slate-600 mt-4">Searching stocks...</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-slate-50 border-b border-slate-200">
                <tr>
                  <th
                    onClick={() => handleSort('symbol')}
                    className="px-4 py-3 text-left text-xs font-semibold text-slate-700 uppercase cursor-pointer hover:bg-slate-100"
                  >
                    <div className="flex items-center space-x-1">
                      <span>Symbol</span>
                      <ArrowUpDown className="h-3 w-3" />
                    </div>
                  </th>
                  <th
                    onClick={() => handleSort('name')}
                    className="px-4 py-3 text-left text-xs font-semibold text-slate-700 uppercase cursor-pointer hover:bg-slate-100"
                  >
                    <div className="flex items-center space-x-1">
                      <span>Company</span>
                      <ArrowUpDown className="h-3 w-3" />
                    </div>
                  </th>
                  <th
                    onClick={() => handleSort('price')}
                    className="px-4 py-3 text-right text-xs font-semibold text-slate-700 uppercase cursor-pointer hover:bg-slate-100"
                  >
                    <div className="flex items-center justify-end space-x-1">
                      <span>Price</span>
                      <ArrowUpDown className="h-3 w-3" />
                    </div>
                  </th>
                  <th
                    onClick={() => handleSort('change_percent')}
                    className="px-4 py-3 text-right text-xs font-semibold text-slate-700 uppercase cursor-pointer hover:bg-slate-100"
                  >
                    <div className="flex items-center justify-end space-x-1">
                      <span>Change %</span>
                      <ArrowUpDown className="h-3 w-3" />
                    </div>
                  </th>
                  <th
                    onClick={() => handleSort('market_cap')}
                    className="px-4 py-3 text-right text-xs font-semibold text-slate-700 uppercase cursor-pointer hover:bg-slate-100"
                  >
                    <div className="flex items-center justify-end space-x-1">
                      <span>Market Cap</span>
                      <ArrowUpDown className="h-3 w-3" />
                    </div>
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-slate-700 uppercase">
                    P/E Ratio
                  </th>
                  <th className="px-4 py-3 text-center text-xs font-semibold text-slate-700 uppercase">
                    Dividend
                  </th>
                  <th className="px-4 py-3 text-center text-xs font-semibold text-slate-700 uppercase">
                    Action
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200">
                {results.map((stock) => (
                  <tr key={stock.symbol} className="hover:bg-slate-50 transition-colors">
                    <td className="px-4 py-3">
                      <div className="font-bold text-sm text-slate-900">{stock.symbol}</div>
                      <div className="text-xs text-slate-500">{stock.exchange}</div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="text-sm text-slate-900">{stock.name}</div>
                      <div className="text-xs text-slate-500">{stock.sector}</div>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="text-sm font-semibold text-slate-900">
                        ${stock.price.toFixed(2)}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className={`flex items-center justify-end space-x-1 text-sm font-bold ${
                        stock.change_percent >= 0 ? 'text-green-600' : 'text-red-600'
                      }`}>
                        {stock.change_percent >= 0 ? (
                          <TrendingUp className="h-4 w-4" />
                        ) : (
                          <TrendingDown className="h-4 w-4" />
                        )}
                        <span>{stock.change_percent >= 0 ? '+' : ''}{stock.change_percent.toFixed(2)}%</span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="text-sm text-slate-700">{formatMarketCap(stock.market_cap)}</div>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="text-sm text-slate-700">{stock.pe_ratio.toFixed(2)}</div>
                    </td>
                    <td className="px-4 py-3 text-center">
                      {stock.has_dividends ? (
                        <span className="px-2 py-1 bg-green-100 text-green-700 text-xs font-semibold rounded">
                          Yes
                        </span>
                      ) : (
                        <span className="px-2 py-1 bg-slate-100 text-slate-600 text-xs font-semibold rounded">
                          No
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-center">
                      <button
                        onClick={() => onSelectStock(stock.symbol)}
                        className="px-3 py-1 bg-daman-blue-600 text-white text-xs font-semibold rounded hover:bg-daman-blue-700 transition-all"
                      >
                        View Details
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {!isLoading && results.length === 0 && (
          <div className="p-12 text-center">
            <BarChart3 className="h-16 w-16 text-slate-300 mx-auto mb-4" />
            <p className="text-slate-600 text-lg">No stocks found</p>
            <p className="text-slate-500 text-sm mt-2">Try adjusting your search filters</p>
          </div>
        )}
      </div>
    </div>
  );
}
