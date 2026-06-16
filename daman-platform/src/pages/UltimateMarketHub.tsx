import { useState, useEffect } from 'react';
import {
  Search, Filter, TrendingUp, TrendingDown, BarChart3, Activity,
  Target, Zap, Download, Eye, Star, Bell, PieChart, TrendingUpIcon,
  AlertCircle, DollarSign, Percent, Calendar, ArrowUpDown, RefreshCw,
  Layers, Brain, Flame, Award, Clock, Globe, Newspaper, X
} from 'lucide-react';
import { supabase } from '../lib/supabase';
import { liveDataService, LiveStockData, SectorPerformance } from '../services/liveDataService';
import MarketOverview from './MarketOverview';
import StockSearch from './StockSearch';
import MarketExpectation from '../components/MarketExpectation';
import PasswordProtection from '../components/PasswordProtection';
import StockSignals from '../components/StockSignals';
import SPXOptionsFlow from '../components/SPXOptionsFlow';
import QuantFilter from '../components/QuantFilter';
import IBKROptionsChain from '../components/IBKROptionsChain';
import FundamentalScanner from '../components/FundamentalScanner';
import { fetchEarningsCalendar, EarningsDay } from '../services/earningsService';
import { getAllScanSymbols } from '../data/marketIndices';
import EventCalendar from '../components/EventCalendar';

interface Stock {
  symbol: string;
  name: string;
  sector: string;
  price: number;
  change_percent: number;
  market_cap: number;
  pe_ratio: number;
  dividend_yield: number;
  rsi_14: number;
  volume: number;
  technical_signal: string;
  above_sma_20: boolean;
  above_sma_50: boolean;
  above_sma_200: boolean;
}

interface MarketMover {
  symbol: string;
  name: string;
  price: number;
  change_percent: number;
  volume: number;
  category: string;
}

interface ScreenerCriteria {
  searchQuery: string;
  sector: string;
  priceMin: number;
  priceMax: number;
  marketCapMin: number;
  marketCapMax: number;
  peRatioMin: number;
  peRatioMax: number;
  dividendYieldMin: number;
  rsiMin: number;
  rsiMax: number;
  volumeMin: number;
  dividendPaying: boolean | null;
  aboveSMA20: boolean | null;
  aboveSMA50: boolean | null;
  aboveSMA200: boolean | null;
  technicalSignal: string;
  sortBy: string;
  sortDirection: 'asc' | 'desc';
}

export default function UltimateMarketHub() {
  const [activeView, setActiveView] = useState<'overview' | 'screener' | 'compare' | 'heatmap' | 'events'>('overview');
  const [scannerTab, setScannerTab] = useState<'signals' | 'search' | 'spx-flow' | 'stocks' | 'ibkr' | 'fundamental'>('signals');
  const [stocksSubTab, setStocksSubTab] = useState<'intraday' | 'daily'>('intraday');
  const [isScannerUnlocked, setIsScannerUnlocked] = useState(false);
  const [criteria, setCriteria] = useState<ScreenerCriteria>({
    searchQuery: '',
    sector: '',
    priceMin: 0,
    priceMax: 0,
    marketCapMin: 0,
    marketCapMax: 0,
    peRatioMin: 0,
    peRatioMax: 0,
    dividendYieldMin: 0,
    rsiMin: 0,
    rsiMax: 100,
    volumeMin: 0,
    dividendPaying: null,
    aboveSMA20: null,
    aboveSMA50: null,
    aboveSMA200: null,
    technicalSignal: '',
    sortBy: 'market_cap',
    sortDirection: 'desc',
  });

  const [results, setResults] = useState<Stock[]>([]);
  const [marketMovers, setMarketMovers] = useState<{
    gainers: MarketMover[];
    losers: MarketMover[];
    active: MarketMover[];
  }>({ gainers: [], losers: [], active: [] });

  const [selectedStocks, setSelectedStocks] = useState<string[]>([]);
  const [watchlist, setWatchlist] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [showFilters, setShowFilters] = useState(true);
  const [sectors, setSectors] = useState<string[]>([]);
  const [sectorPerformance, setSectorPerformance] = useState<SectorPerformance[]>([]);
  const [isLiveDataActive, setIsLiveDataActive] = useState(true);
  const [compareSearchQuery, setCompareSearchQuery] = useState('');
  const [earningsCalendar, setEarningsCalendar] = useState<EarningsDay[]>([]);
  const [isLoadingEarnings, setIsLoadingEarnings] = useState(false);

  useEffect(() => {
    fetchMarketMovers();
    fetchSectors();
    fetchSectorPerformance();

    if (isLiveDataActive) {
      liveDataService.startLiveUpdates('market-movers', () => {
        fetchMarketMovers();
      }, 30000);

      liveDataService.startLiveUpdates('sector-performance', () => {
        fetchSectorPerformance();
      }, 60000);
    }

    return () => {
      liveDataService.stopAllUpdates();
    };
  }, [isLiveDataActive]);

  useEffect(() => {
    performScreening();
  }, []);

  useEffect(() => {
    const debounce = setTimeout(() => {
      performScreening();
    }, 500);
    return () => clearTimeout(debounce);
  }, [criteria]);

  const fetchMarketMovers = async () => {
    try {
      const data = await liveDataService.fetchLiveMarketMovers();
      setMarketMovers({
        gainers: data.gainers.map(convertLiveData),
        losers: data.losers.map(convertLiveData),
        active: data.active.map(convertLiveData),
      });
    } catch (error) {
      console.error('Error fetching market movers:', error);
      setMarketMovers({
        gainers: generateMockMovers('gainer'),
        losers: generateMockMovers('loser'),
        active: generateMockMovers('active'),
      });
    }
  };

  const convertLiveData = (data: LiveStockData): MarketMover => ({
    symbol: data.symbol,
    name: data.name,
    price: data.price,
    change_percent: data.change_percent,
    volume: data.volume,
    category: '',
  });

  const fetchSectorPerformance = async () => {
    try {
      const data = await liveDataService.fetchLiveSectorPerformance();
      setSectorPerformance(data);
    } catch (error) {
      console.error('Error fetching sector performance:', error);
    }
  };


  const loadEarningsCalendar = async () => {
    setIsLoadingEarnings(true);
    try {
      const calendar = await fetchEarningsCalendar();
      setEarningsCalendar(calendar);
    } catch (error) {
      console.error('Error loading earnings calendar:', error);
    } finally {
      setIsLoadingEarnings(false);
    }
  };

  const generateMockMovers = (type: string): MarketMover[] => {
    const symbols = ['NVDA', 'TSLA', 'AMD', 'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NFLX', 'INTC'];
    return symbols.map((symbol, i) => ({
      symbol,
      name: `${symbol} Corporation`,
      price: 100 + Math.random() * 400,
      change_percent: type === 'gainer' ? Math.random() * 8 : type === 'loser' ? -(Math.random() * 8) : (Math.random() - 0.5) * 10,
      volume: Math.floor(Math.random() * 100000000) + 10000000,
      category: type,
    }));
  };

  const fetchSectors = async () => {
    try {
      const { data } = await supabase
        .from('stock_universe')
        .select('sector')
        .not('sector', 'is', null);

      if (data) {
        const uniqueSectors = [...new Set(data.map(d => d.sector))].filter(Boolean);
        setSectors(uniqueSectors as string[]);
      }
    } catch (error) {
      setSectors(['Technology', 'Healthcare', 'Financial', 'Consumer', 'Industrial', 'Energy', 'Utilities', 'Real Estate']);
    }
  };

  const performScreening = async () => {
    setIsLoading(true);

    try {
      let query = supabase
        .from('stock_screener_data')
        .select('*');

      if (criteria.searchQuery) {
        query = query.or(`symbol.ilike.%${criteria.searchQuery}%,name.ilike.%${criteria.searchQuery}%`);
      }

      if (criteria.sector) query = query.eq('sector', criteria.sector);
      if (criteria.priceMin > 0) query = query.gte('price', criteria.priceMin);
      if (criteria.priceMax > 0) query = query.lte('price', criteria.priceMax);
      if (criteria.marketCapMin > 0) query = query.gte('market_cap', criteria.marketCapMin);
      if (criteria.marketCapMax > 0) query = query.lte('market_cap', criteria.marketCapMax);
      if (criteria.peRatioMin > 0) query = query.gte('pe_ratio', criteria.peRatioMin);
      if (criteria.peRatioMax > 0) query = query.lte('pe_ratio', criteria.peRatioMax);
      if (criteria.dividendYieldMin > 0) query = query.gte('dividend_yield', criteria.dividendYieldMin);
      if (criteria.rsiMin > 0) query = query.gte('rsi_14', criteria.rsiMin);
      if (criteria.rsiMax < 100) query = query.lte('rsi_14', criteria.rsiMax);
      if (criteria.volumeMin > 0) query = query.gte('volume', criteria.volumeMin);
      if (criteria.dividendPaying !== null) {
        if (criteria.dividendPaying) {
          query = query.gt('dividend_yield', 0);
        } else {
          query = query.eq('dividend_yield', 0);
        }
      }
      if (criteria.technicalSignal) query = query.eq('signal', criteria.technicalSignal);

      const sortColumn = criteria.sortBy === 'current_price' ? 'price' :
                         criteria.sortBy === 'technical_signal' ? 'signal' :
                         criteria.sortBy;

      query = query.order(sortColumn, { ascending: criteria.sortDirection === 'asc' });
      query = query.limit(100);

      const { data, error } = await query;

      if (error) throw error;

      if (data && data.length > 0) {
        setResults(data.map(row => ({
          symbol: row.symbol,
          name: row.name,
          sector: row.sector || 'Unknown',
          price: parseFloat(row.price) || 0,
          change_percent: parseFloat(row.change_percent) || 0,
          market_cap: parseInt(row.market_cap) || 0,
          pe_ratio: parseFloat(row.pe_ratio) || 0,
          dividend_yield: parseFloat(row.dividend_yield) || 0,
          rsi_14: parseFloat(row.rsi_14) || 50,
          volume: parseInt(row.volume) || 0,
          technical_signal: row.signal || 'neutral',
          above_sma_20: false,
          above_sma_50: false,
          above_sma_200: false,
        })));
      } else {
        setResults([]);
      }
    } catch (error) {
      console.error('Error screening:', error);
      setResults([]);
    } finally {
      setIsLoading(false);
    }
  };

  const loadPreset = (preset: string) => {
    const presets: Record<string, Partial<ScreenerCriteria>> = {
      growth: {
        marketCapMin: 1000000000,
        rsiMin: 50,
        rsiMax: 70,
        technicalSignal: 'buy',
      },
      value: {
        peRatioMin: 5,
        peRatioMax: 20,
        dividendYieldMin: 1,
      },
      dividend: {
        dividendYieldMin: 2,
        dividendPaying: true,
        marketCapMin: 10000000000,
      },
      momentum: {
        rsiMin: 60,
        rsiMax: 80,
        technicalSignal: 'strong_buy',
      },
    };

    if (presets[preset]) {
      setCriteria({ ...criteria, ...presets[preset], searchQuery: '' });
      setTimeout(() => performScreening(), 100);
    }
  };

  const toggleWatchlist = (symbol: string) => {
    setWatchlist(prev =>
      prev.includes(symbol) ? prev.filter(s => s !== symbol) : [...prev, symbol]
    );
  };

  const toggleCompare = (symbol: string) => {
    setSelectedStocks(prev =>
      prev.includes(symbol) ? prev.filter(s => s !== symbol) : [...prev, symbol].slice(0, 5)
    );
  };

  const exportResults = () => {
    const headers = ['Symbol', 'Name', 'Sector', 'Price', 'Change%', 'Market Cap', 'P/E', 'Div Yield', 'RSI', 'Signal'];
    const rows = results.map(r => [
      r.symbol, r.name, r.sector, r.price.toFixed(2), r.change_percent.toFixed(2),
      r.market_cap, r.pe_ratio.toFixed(2), r.dividend_yield.toFixed(2),
      r.rsi_14.toFixed(2), r.technical_signal
    ]);

    const csv = [headers, ...rows].map(row => row.join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `market_screening_${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
    URL.revokeObjectURL(url);
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

  const getSignalColor = (signal: string) => {
    const colors = {
      strong_buy: 'bg-green-600',
      buy: 'bg-green-500',
      neutral: 'bg-slate-400',
      sell: 'bg-red-500',
      strong_sell: 'bg-red-600',
    };
    return colors[signal as keyof typeof colors] || colors.neutral;
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-slate-50 dark:from-slate-900 dark:via-slate-800 dark:to-slate-900 py-8 transition-colors duration-200">
      <div className="max-w-[1600px] mx-auto px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center space-x-4">
              <div className="p-3 bg-gradient-to-br from-daman-blue-600 to-daman-blue-700 rounded-xl shadow-lg">
                <Layers className="h-8 w-8 text-white" />
              </div>
              <div>
                <h1 className="text-4xl font-bold text-slate-900 dark:text-white">Ultimate Market Hub</h1>
                <p className="text-slate-600 dark:text-slate-400 mt-1">Advanced screening, real-time movers, and professional analysis tools</p>
              </div>
            </div>

            <div className="flex items-center space-x-3">
              <button className="px-4 py-2 bg-white dark:bg-slate-800 border-2 border-slate-200 dark:border-slate-700 rounded-lg hover:border-daman-blue-500 transition-all shadow-sm">
                <Bell className="h-5 w-5 text-slate-600 dark:text-slate-400" />
              </button>
              <button
                onClick={exportResults}
                disabled={results.length === 0}
                className="flex items-center space-x-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:bg-slate-300 transition-all shadow-md"
              >
                <Download className="h-4 w-4" />
                <span>Export</span>
              </button>
            </div>
          </div>

          {/* View Tabs */}
          <div className="flex space-x-2 bg-white dark:bg-slate-800 rounded-xl p-2 shadow-md border border-slate-200 dark:border-slate-700 overflow-x-auto">
            <button
              onClick={() => setActiveView('overview')}
              className={`flex items-center space-x-2 px-6 py-3 rounded-lg font-semibold transition-all whitespace-nowrap ${
                activeView === 'overview'
                  ? 'bg-gradient-to-r from-daman-blue-600 to-daman-blue-700 text-white shadow-lg'
                  : 'text-slate-600 dark:text-slate-400 hover:bg-slate-50'
              }`}
            >
              <Globe className="h-5 w-5" />
              <span>Market Overview</span>
            </button>
            <button
              onClick={() => setActiveView('compare')}
              className={`flex items-center space-x-2 px-6 py-3 rounded-lg font-semibold transition-all ${
                activeView === 'compare'
                  ? 'bg-gradient-to-r from-daman-blue-600 to-daman-blue-700 text-white shadow-lg'
                  : 'text-slate-600 dark:text-slate-400 hover:bg-slate-50'
              }`}
            >
              <Target className="h-5 w-5" />
              <span>Scanner</span>
            </button>
            <button
              onClick={() => {
                setActiveView('heatmap');
                if (earningsCalendar.length === 0) {
                  loadEarningsCalendar();
                }
              }}
              className={`flex items-center space-x-2 px-6 py-3 rounded-lg font-semibold transition-all whitespace-nowrap ${
                activeView === 'heatmap'
                  ? 'bg-gradient-to-r from-daman-blue-600 to-daman-blue-700 text-white shadow-lg'
                  : 'text-slate-600 dark:text-slate-400 hover:bg-slate-50'
              }`}
            >
              <Calendar className="h-5 w-5" />
              <span>Earnings</span>
            </button>
            <button
              onClick={() => setActiveView('events')}
              className={`flex items-center space-x-2 px-6 py-3 rounded-lg font-semibold transition-all whitespace-nowrap ${
                activeView === 'events'
                  ? 'bg-gradient-to-r from-daman-blue-600 to-daman-blue-700 text-white shadow-lg'
                  : 'text-slate-600 dark:text-slate-400 hover:bg-slate-50'
              }`}
            >
              <Globe className="h-5 w-5" />
              <span>Event Calendar</span>
            </button>
          </div>
        </div>


        {/* Main Content */}
        {activeView === 'overview' && <MarketOverview />}



        {/* Scanner View (formerly Compare) */}
        {activeView === 'compare' && (
          <div className="bg-white dark:bg-slate-800 rounded-xl shadow-lg border border-slate-200 dark:border-slate-700 p-6">
            {!isScannerUnlocked ? (
              <PasswordProtection
                onUnlock={() => setIsScannerUnlocked(true)}
                title="Scanner Tools Access"
                description="Enter password to access advanced scanner features"
              />
            ) : (
              <>
                <h2 className="text-2xl font-bold text-slate-900 dark:text-white mb-6 flex items-center space-x-2">
                  <Target className="h-7 w-7 text-daman-blue-600" />
                  <span>Scanner Tools</span>
                </h2>

                {/* Scanner Tabs */}
                <div className="flex space-x-2 mb-6 border-b border-slate-200 dark:border-slate-700">
                  <button
                    onClick={() => setScannerTab('signals')}
                    className={`px-6 py-3 font-semibold transition-all ${
                      scannerTab === 'signals'
                        ? 'border-b-2 border-daman-blue-600 text-daman-blue-600'
                        : 'text-slate-600 dark:text-slate-400 hover:text-slate-900'
                    }`}
                  >
                    Stock Signals
                  </button>
                  <button
                    onClick={() => setScannerTab('search')}
                    className={`px-6 py-3 font-semibold transition-all ${
                      scannerTab === 'search'
                        ? 'border-b-2 border-daman-blue-600 text-daman-blue-600'
                        : 'text-slate-600 dark:text-slate-400 hover:text-slate-900'
                    }`}
                  >
                    Stock Search
                  </button>
                  <button
                    onClick={() => setScannerTab('spx-flow')}
                    className={`px-6 py-3 font-semibold transition-all ${
                      scannerTab === 'spx-flow'
                        ? 'border-b-2 border-daman-blue-600 text-daman-blue-600'
                        : 'text-slate-600 dark:text-slate-400 hover:text-slate-900'
                    }`}
                  >
                    SPX Options Flow
                  </button>
                  <button
                    onClick={() => setScannerTab('stocks')}
                    className={`px-6 py-3 font-semibold transition-all ${
                      scannerTab === 'stocks'
                        ? 'border-b-2 border-daman-blue-600 text-daman-blue-600'
                        : 'text-slate-600 dark:text-slate-400 hover:text-slate-900'
                    }`}
                  >
                    Stocks
                  </button>
                  <button
                    onClick={() => setScannerTab('ibkr')}
                    className={`px-6 py-3 font-semibold transition-all ${
                      scannerTab === 'ibkr'
                        ? 'border-b-2 border-daman-blue-600 text-daman-blue-600'
                        : 'text-slate-600 dark:text-slate-400 hover:text-slate-900'
                    }`}
                  >
                    IBKR Options Chain
                  </button>
                  <button
                    onClick={() => setScannerTab('fundamental')}
                    className={`px-6 py-3 font-semibold transition-all ${
                      scannerTab === 'fundamental'
                        ? 'border-b-2 border-daman-blue-600 text-daman-blue-600'
                        : 'text-slate-600 dark:text-slate-400 hover:text-slate-900'
                    }`}
                  >
                    Fundamental
                  </button>
                </div>

                {/* Scanner Content */}
                {scannerTab === 'signals' && (
                  <div>
                    <StockSignals />
                  </div>
                )}

                {scannerTab === 'search' && (
                  <div>
                    <StockSearch />
                  </div>
                )}

                {scannerTab === 'spx-flow' && (
                  <div>
                    <SPXOptionsFlow />
                  </div>
                )}

                {scannerTab === 'stocks' && (
                  <QuantFilter />
                )}

                {scannerTab === 'ibkr' && (
                  <div>
                    <IBKROptionsChain />
                  </div>
                )}

                {scannerTab === 'fundamental' && (
                  <div>
                    <FundamentalScanner />
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {/* Earnings Calendar View */}
        {activeView === 'heatmap' && (
          <div className="bg-white dark:bg-slate-800 rounded-xl shadow-lg border border-slate-200 dark:border-slate-700 p-6">
            <div className="flex items-center justify-between mb-6">
              <div>
                <h2 className="text-2xl font-bold text-slate-900 dark:text-white mb-1">Earnings Calendar</h2>
                <p className="text-sm text-slate-600 dark:text-slate-400">This Week's Earnings Announcements</p>
              </div>
              <button
                onClick={loadEarningsCalendar}
                disabled={isLoadingEarnings}
                className="flex items-center space-x-2 px-4 py-2 bg-daman-blue-600 text-white rounded-lg hover:bg-daman-blue-700 disabled:opacity-50 transition-all"
              >
                {isLoadingEarnings ? (
                  <>
                    <RefreshCw className="h-4 w-4 animate-spin" />
                    <span>Loading...</span>
                  </>
                ) : (
                  <>
                    <RefreshCw className="h-4 w-4" />
                    <span>Refresh</span>
                  </>
                )}
              </button>
            </div>

            {isLoadingEarnings ? (
              <div className="text-center py-12 bg-slate-50 dark:bg-slate-900 rounded-xl border-2 border-dashed border-slate-200 dark:border-slate-700">
                <Clock className="h-16 w-16 text-daman-blue-600 mx-auto mb-4 animate-spin" />
                <p className="text-slate-600 dark:text-slate-400 text-lg mb-2">Loading earnings calendar...</p>
              </div>
            ) : earningsCalendar.length === 0 ? (
              <div className="text-center py-12 bg-slate-50 dark:bg-slate-900 rounded-xl border-2 border-dashed border-slate-200 dark:border-slate-700">
                <Calendar className="h-16 w-16 text-slate-300 mx-auto mb-4" />
                <p className="text-slate-600 dark:text-slate-400 text-lg mb-2">No earnings data available</p>
                <p className="text-slate-500 dark:text-slate-400 text-sm">Click Refresh to load this week's earnings</p>
              </div>
            ) : (
              <div className="space-y-6">
                {earningsCalendar.map((day) => {
                  const totalEvents = day.bmo.length + day.amc.length + day.during.length;
                  if (totalEvents === 0) return null;

                  const [year, month, dayNum] = day.date.split('-').map(Number);
                  const displayDate = new Date(year, month - 1, dayNum);

                  return (
                    <div key={day.date} className="border-2 border-slate-200 dark:border-slate-700 rounded-xl overflow-hidden">
                      <div className="bg-gradient-to-r from-daman-blue-600 to-daman-blue-700 px-6 py-4">
                        <div className="flex items-center justify-between">
                          <div>
                            <h3 className="text-xl font-bold text-white">{day.dayOfWeek}</h3>
                            <p className="text-sm text-blue-100">{displayDate.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })}</p>
                          </div>
                          <div className="text-white">
                            <span className="text-2xl font-bold">{totalEvents}</span>
                            <span className="text-sm ml-1">event{totalEvents !== 1 ? 's' : ''}</span>
                          </div>
                        </div>
                      </div>

                      <div className="p-6 space-y-6">
                        {day.bmo.length > 0 && (
                          <div>
                            <div className="flex items-center space-x-2 mb-3">
                              <div className="bg-orange-100 p-2 rounded-lg">
                                <Clock className="h-5 w-5 text-orange-600" />
                              </div>
                              <h4 className="font-bold text-slate-900 dark:text-white text-lg">Before Market Open</h4>
                              <span className="text-sm text-slate-500 dark:text-slate-400">({day.bmo.length})</span>
                            </div>
                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                              {day.bmo.map((event) => (
                                <div key={event.symbol} className="bg-orange-50 border-2 border-orange-200 rounded-lg p-4 hover:shadow-md transition-all">
                                  <div className="flex items-start justify-between mb-2">
                                    <div className="font-bold text-orange-900 text-lg">{event.symbol}</div>
                                    {event.lastPrice && (
                                      <div className="text-sm font-semibold text-slate-700 dark:text-slate-300">${event.lastPrice.toFixed(2)}</div>
                                    )}
                                  </div>
                                  <div className="text-sm text-slate-700 dark:text-slate-300 mb-2 line-clamp-2">{event.name}</div>
                                  {event.estimatedEPS && (
                                    <div className="text-xs text-slate-600 dark:text-slate-400">
                                      Est. EPS: <span className="font-semibold">${event.estimatedEPS.toFixed(2)}</span>
                                    </div>
                                  )}
                                  {event.marketCap && (
                                    <div className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                                      MCap: ${(event.marketCap / 1000000000).toFixed(1)}B
                                    </div>
                                  )}
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        {day.amc.length > 0 && (
                          <div>
                            <div className="flex items-center space-x-2 mb-3">
                              <div className="bg-purple-100 p-2 rounded-lg">
                                <Clock className="h-5 w-5 text-purple-600" />
                              </div>
                              <h4 className="font-bold text-slate-900 dark:text-white text-lg">After Market Close</h4>
                              <span className="text-sm text-slate-500 dark:text-slate-400">({day.amc.length})</span>
                            </div>
                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                              {day.amc.map((event) => (
                                <div key={event.symbol} className="bg-purple-50 border-2 border-purple-200 rounded-lg p-4 hover:shadow-md transition-all">
                                  <div className="flex items-start justify-between mb-2">
                                    <div className="font-bold text-purple-900 text-lg">{event.symbol}</div>
                                    {event.lastPrice && (
                                      <div className="text-sm font-semibold text-slate-700 dark:text-slate-300">${event.lastPrice.toFixed(2)}</div>
                                    )}
                                  </div>
                                  <div className="text-sm text-slate-700 dark:text-slate-300 mb-2 line-clamp-2">{event.name}</div>
                                  {event.estimatedEPS && (
                                    <div className="text-xs text-slate-600 dark:text-slate-400">
                                      Est. EPS: <span className="font-semibold">${event.estimatedEPS.toFixed(2)}</span>
                                    </div>
                                  )}
                                  {event.marketCap && (
                                    <div className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                                      MCap: ${(event.marketCap / 1000000000).toFixed(1)}B
                                    </div>
                                  )}
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        {day.during.length > 0 && (
                          <div>
                            <div className="flex items-center space-x-2 mb-3">
                              <div className="bg-blue-100 p-2 rounded-lg">
                                <Clock className="h-5 w-5 text-blue-600" />
                              </div>
                              <h4 className="font-bold text-slate-900 dark:text-white text-lg">During Trading Hours</h4>
                              <span className="text-sm text-slate-500 dark:text-slate-400">({day.during.length})</span>
                            </div>
                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                              {day.during.map((event) => (
                                <div key={event.symbol} className="bg-blue-50 border-2 border-blue-200 rounded-lg p-4 hover:shadow-md transition-all">
                                  <div className="flex items-start justify-between mb-2">
                                    <div className="font-bold text-blue-900 text-lg">{event.symbol}</div>
                                    {event.lastPrice && (
                                      <div className="text-sm font-semibold text-slate-700 dark:text-slate-300">${event.lastPrice.toFixed(2)}</div>
                                    )}
                                  </div>
                                  <div className="text-sm text-slate-700 dark:text-slate-300 mb-2 line-clamp-2">{event.name}</div>
                                  {event.estimatedEPS && (
                                    <div className="text-xs text-slate-600 dark:text-slate-400">
                                      Est. EPS: <span className="font-semibold">${event.estimatedEPS.toFixed(2)}</span>
                                    </div>
                                  )}
                                  {event.marketCap && (
                                    <div className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                                      MCap: ${(event.marketCap / 1000000000).toFixed(1)}B
                                    </div>
                                  )}
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            <div className="mt-6 bg-blue-50 border-l-4 border-blue-500 p-4 rounded">
              <div className="flex items-start">
                <AlertCircle className="h-5 w-5 text-blue-500 mt-0.5 mr-2" />
                <div>
                  <h4 className="text-sm font-semibold text-blue-900 mb-1">About Earnings Calendar</h4>
                  <p className="text-xs text-blue-800 leading-relaxed">
                    This calendar displays earnings announcements for the current week. Companies are sorted by market capitalization within each time slot.
                    Earnings data updates weekly and includes estimated EPS when available. Use this to plan trades around major announcements.
                  </p>
                  <p className="text-xs text-blue-700 mt-2">
                    <strong>Data Source:</strong> Seeking Alpha (<a href="https://seekingalpha.com/earnings/earnings-calendar" target="_blank" rel="noopener noreferrer" className="underline hover:text-blue-900">seekingalpha.com/earnings/earnings-calendar</a>)
                  </p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Event Calendar View */}
        {activeView === 'events' && (
          <div className="bg-white dark:bg-slate-800 rounded-xl shadow-lg border border-slate-200 dark:border-slate-700 p-6">
            <EventCalendar />
          </div>
        )}
      </div>
    </div>
  );
}
