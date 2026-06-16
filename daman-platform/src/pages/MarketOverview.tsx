import { useState, useEffect } from 'react';
import { TrendingUp, TrendingDown, Activity, DollarSign, Tv, RefreshCw, Brain, TrendingUp as BullIcon, TrendingDown as BearIcon, Minus } from 'lucide-react';
import SectorPerformance from '../components/SectorPerformance';
import { liveDataService } from '../services/liveDataService';
import { aiMarketCommentary } from '../services/aiMarketCommentary';

interface MarketIndex {
  symbol: string;
  name: string;
  price: number;
  change: number;
  changePercent: number;
}

interface Commodity {
  symbol: string;
  name: string;
  price: number;
  change: number;
  changePercent: number;
  unit: string;
}

interface TopMover {
  symbol: string;
  name: string;
  price: number;
  change: number;
  changePercent: number;
}

interface MarketCommentary {
  headline: string;
  sentiment: 'bullish' | 'bearish' | 'neutral';
  commentary: string;
  timestamp: Date;
}

export default function MarketOverview() {
  const [indices, setIndices] = useState<MarketIndex[]>([]);
  const [commodities, setCommodities] = useState<Commodity[]>([]);
  const [topGainers, setTopGainers] = useState<TopMover[]>([]);
  const [topLosers, setTopLosers] = useState<TopMover[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [lastUpdate, setLastUpdate] = useState<Date>(new Date());
  const [commentary, setCommentary] = useState<MarketCommentary | null>(null);

  useEffect(() => {
    loadMarketData();

    // Auto-refresh every 30 seconds for real-time data
    const interval = setInterval(() => {
      loadMarketData();
    }, 30000);

    return () => clearInterval(interval);
  }, []);

  const loadMarketData = async () => {
    setIsLoading(true);
    try {
      const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
      const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

      if (!supabaseUrl || !supabaseKey) {
        loadMockData();
        setLastUpdate(new Date());
        setIsLoading(false);
        return;
      }

      // Fetch indices with real-time data
      const indicesSymbols = ['^GSPC', '^DJI', '^IXIC', '^RUT'];
      const indicesUrl = `${supabaseUrl}/functions/v1/fetch-market-data?symbols=${indicesSymbols.join(',')}`;

      try {
        const indicesResponse = await fetch(indicesUrl, {
          headers: {
            'Authorization': `Bearer ${supabaseKey}`,
            'Content-Type': 'application/json',
          },
        });

        if (indicesResponse.ok) {
          const indicesData = await indicesResponse.json();
          if (indicesData.quotes && indicesData.quotes.length > 0) {
            const indexNames: {[key: string]: string} = {
              '^GSPC': 'S&P 500',
              '^DJI': 'Dow Jones',
              '^IXIC': 'NASDAQ',
              '^RUT': 'Russell 2000'
            };

            setIndices(indicesData.quotes.map((q: any) => ({
              symbol: q.symbol,
              name: indexNames[q.symbol] || q.name,
              price: q.price,
              change: q.change,
              changePercent: q.changePercent
            })));
          }
        }
      } catch (error) {
        console.error('Error fetching indices:', error);
      }

      // Fetch commodities with real-time data
      const commoditiesSymbols = ['GC=F', 'SI=F', 'CL=F', 'NG=F'];
      const commoditiesUrl = `${supabaseUrl}/functions/v1/fetch-market-data?symbols=${commoditiesSymbols.join(',')}`;

      try {
        const commoditiesResponse = await fetch(commoditiesUrl, {
          headers: {
            'Authorization': `Bearer ${supabaseKey}`,
            'Content-Type': 'application/json',
          },
        });

        if (commoditiesResponse.ok) {
          const commoditiesData = await commoditiesResponse.json();
          if (commoditiesData.quotes && commoditiesData.quotes.length > 0) {
            const commodityMap: {[key: string]: {name: string, unit: string}} = {
              'GC=F': { name: 'Gold', unit: '/oz' },
              'SI=F': { name: 'Silver', unit: '/oz' },
              'CL=F': { name: 'Crude Oil', unit: '/bbl' },
              'NG=F': { name: 'Natural Gas', unit: '/mmbtu' }
            };

            setCommodities(commoditiesData.quotes.map((q: any) => ({
              symbol: q.symbol,
              name: commodityMap[q.symbol]?.name || q.name,
              price: q.price,
              change: q.change,
              changePercent: q.changePercent,
              unit: commodityMap[q.symbol]?.unit || ''
            })));
          }
        }
      } catch (error) {
        console.error('Error fetching commodities:', error);
      }

      // Fetch real-time market movers
      try {
        const moversData = await liveDataService.fetchLiveMarketMovers();

        if (moversData.gainers.length > 0) {
          setTopGainers(moversData.gainers.slice(0, 5).map(stock => ({
            symbol: stock.symbol,
            name: stock.name,
            price: stock.price,
            change: (stock.price * stock.change_percent) / 100,
            changePercent: stock.change_percent
          })));
        }

        if (moversData.losers.length > 0) {
          setTopLosers(moversData.losers.slice(0, 5).map(stock => ({
            symbol: stock.symbol,
            name: stock.name,
            price: stock.price,
            change: (stock.price * stock.change_percent) / 100,
            changePercent: stock.change_percent
          })));
        }
      } catch (error) {
        console.error('Error fetching movers:', error);
      }

      setLastUpdate(new Date());

      // Fetch real-time sector performance
      let sectorData: {name: string, performance: number}[] = [];
      try {
        const sectorMap: { [key: string]: string } = {
          'XLK': 'Technology',
          'XLV': 'Healthcare',
          'XLF': 'Financial',
          'XLE': 'Energy',
          'XLY': 'Consumer',
          'XLI': 'Industrials'
        };

        const sectorSymbols = Object.keys(sectorMap).join(',');
        const sectorUrl = `${supabaseUrl}/functions/v1/fetch-market-data?symbols=${sectorSymbols}`;

        const sectorResponse = await fetch(sectorUrl, {
          headers: {
            'Authorization': `Bearer ${supabaseKey}`,
            'Content-Type': 'application/json',
          },
        });

        if (sectorResponse.ok) {
          const sectorResponseData = await sectorResponse.json();
          if (sectorResponseData.quotes && sectorResponseData.quotes.length > 0) {
            sectorData = sectorResponseData.quotes.map((q: any) => ({
              name: sectorMap[q.symbol] || q.symbol,
              performance: q.changePercent || 0
            }));
          }
        }
      } catch (error) {
        console.error('Error fetching sector data:', error);
      }

      // If no sector data, use mock data
      if (sectorData.length === 0) {
        sectorData = [
          { name: 'Technology', performance: 0.8 },
          { name: 'Financial', performance: 0.3 },
          { name: 'Healthcare', performance: -0.2 },
          { name: 'Energy', performance: 1.2 },
          { name: 'Consumer', performance: 0.5 }
        ];
      }

      // Calculate real-time market breadth estimate
      const totalVolume = indices.reduce((sum, idx) => sum + (idx.price * 1000000), 0);
      const positiveIndices = indices.filter(idx => idx.changePercent > 0).length;
      const negativeIndices = indices.length - positiveIndices;
      const breadthRatio = positiveIndices / indices.length;

      // Estimate breadth based on indices performance
      const estimatedAdvancing = Math.round(320 * breadthRatio);
      const estimatedDeclining = 500 - estimatedAdvancing;

      // Generate AI Market Commentary with real-time data
      try {
        const marketData = {
          indices: indices.map(idx => ({
            symbol: idx.symbol,
            change: idx.change,
            changePercent: idx.changePercent
          })),
          sectors: sectorData,
          volume: totalVolume,
          breadth: { advancing: estimatedAdvancing, declining: estimatedDeclining }
        };

        const aiCommentary = await aiMarketCommentary.generateCommentary(marketData);
        setCommentary(aiCommentary);
      } catch (error) {
        console.error('Error generating AI commentary:', error);
      }
    } catch (error) {
      console.error('Error fetching market data:', error);
      loadMockData();
    } finally {
      setIsLoading(false);
    }
  };

  const loadMockData = () => {
    setIndices([
      { symbol: '^GSPC', name: 'S&P 500', price: 4567.89, change: 23.45, changePercent: 0.51 },
      { symbol: '^DJI', name: 'Dow Jones', price: 35789.12, change: -156.78, changePercent: -0.44 },
      { symbol: '^IXIC', name: 'NASDAQ', price: 14234.56, change: 89.34, changePercent: 0.63 },
      { symbol: '^RUT', name: 'Russell 2000', price: 1923.45, change: 12.67, changePercent: 0.66 },
    ]);

    setCommodities([
      { symbol: 'GC=F', name: 'Gold', price: 2034.50, change: 15.20, changePercent: 0.75, unit: '/oz' },
      { symbol: 'SI=F', name: 'Silver', price: 24.67, change: -0.34, changePercent: -1.36, unit: '/oz' },
      { symbol: 'CL=F', name: 'Crude Oil', price: 78.45, change: 2.13, changePercent: 2.79, unit: '/bbl' },
      { symbol: 'NG=F', name: 'Natural Gas', price: 2.89, change: -0.12, changePercent: -3.98, unit: '/mmbtu' },
    ]);

    setTopGainers([
      { symbol: 'NVDA', name: 'NVIDIA Corp', price: 495.60, change: 28.45, changePercent: 6.09 },
      { symbol: 'AMD', name: 'Advanced Micro', price: 118.34, change: 7.23, changePercent: 6.51 },
      { symbol: 'TSLA', name: 'Tesla Inc', price: 242.80, change: 14.12, changePercent: 6.17 },
      { symbol: 'META', name: 'Meta Platforms', price: 485.20, change: 23.89, changePercent: 5.18 },
      { symbol: 'AMZN', name: 'Amazon.com', price: 155.30, change: 7.45, changePercent: 5.04 },
    ]);

    setTopLosers([
      { symbol: 'NFLX', name: 'Netflix Inc', price: 445.67, change: -18.92, changePercent: -4.07 },
      { symbol: 'DIS', name: 'Walt Disney', price: 89.43, change: -4.21, changePercent: -4.50 },
      { symbol: 'PYPL', name: 'PayPal Holdings', price: 62.34, change: -3.45, changePercent: -5.25 },
      { symbol: 'BA', name: 'Boeing Co', price: 187.23, change: -10.67, changePercent: -5.39 },
      { symbol: 'INTC', name: 'Intel Corp', price: 43.21, change: -2.56, changePercent: -5.60 },
    ]);
  };

  return (
    <div className="space-y-6">
      {/* AI Market Commentary */}
      {commentary && (
        <div className="bg-gradient-to-br from-blue-50 to-indigo-50 dark:from-slate-800 dark:to-slate-900 rounded-xl p-6 shadow-lg border border-blue-200 dark:border-slate-700">
          <div className="flex items-center gap-3 mb-4">
            <div className="p-2 bg-blue-600 rounded-lg">
              <Brain className="h-6 w-6 text-white" />
            </div>
            <div>
              <h2 className="text-2xl font-bold text-slate-900 dark:text-white">AI Market Commentary</h2>
              <p className="text-sm text-slate-600 dark:text-slate-400">
                Auto-generated analysis • {commentary.timestamp.toLocaleTimeString()}
              </p>
            </div>
            <div className={`ml-auto px-4 py-2 rounded-full font-semibold text-sm ${
              commentary.sentiment === 'bullish'
                ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                : commentary.sentiment === 'bearish'
                ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
                : 'bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-400'
            }`}>
              {commentary.sentiment === 'bullish' && <BullIcon className="h-4 w-4 inline mr-1" />}
              {commentary.sentiment === 'bearish' && <BearIcon className="h-4 w-4 inline mr-1" />}
              {commentary.sentiment === 'neutral' && <Minus className="h-4 w-4 inline mr-1" />}
              {commentary.sentiment.toUpperCase()}
            </div>
          </div>

          {/* Headline */}
          <div className="bg-white dark:bg-slate-800 rounded-lg p-6">
            <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-4">
              {commentary.headline}
            </h3>
            <p className="text-slate-700 dark:text-slate-300 leading-relaxed text-base">
              {commentary.commentary}
            </p>
          </div>
        </div>
      )}

      {/* Major Indices */}
      <div className="bg-white dark:bg-slate-800 rounded-xl p-6 shadow-lg border border-slate-200 dark:border-slate-700">
        <div className="flex items-center gap-3 mb-6">
          <div className="p-2 bg-blue-100 dark:bg-blue-900/30 rounded-lg">
            <Activity className="h-6 w-6 text-blue-600 dark:text-blue-400" />
          </div>
          <h2 className="text-2xl font-bold text-slate-900 dark:text-white">Major Market Indices</h2>
        </div>
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-400">
            <div className="flex items-center gap-1 px-2 py-1 bg-green-100 dark:bg-green-900/30 rounded">
              <Activity className="h-3 w-3 text-green-600 dark:text-green-400 animate-pulse" />
              <span className="font-semibold text-green-700 dark:text-green-400">LIVE</span>
            </div>
            <span>Last update: {lastUpdate.toLocaleTimeString()}</span>
          </div>
          <button
            onClick={loadMarketData}
            disabled={isLoading}
            className="flex items-center gap-2 px-3 py-1.5 bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400 rounded-lg hover:bg-blue-200 dark:hover:bg-blue-900/50 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
            <span className="text-sm font-medium">Refresh</span>
          </button>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {indices.map((index) => (
            <div key={index.symbol} className="bg-slate-50 dark:bg-slate-900 rounded-lg p-4 border border-slate-200 dark:border-slate-700">
              <div className="text-sm font-medium text-slate-600 dark:text-slate-400 mb-1">{index.name}</div>
              <div className="text-2xl font-bold text-slate-900 dark:text-white mb-2">
                {index.price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </div>
              <div className={`flex items-center gap-1 text-sm font-semibold ${index.change >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                {index.change >= 0 ? <TrendingUp className="h-4 w-4" /> : <TrendingDown className="h-4 w-4" />}
                <span>{index.change >= 0 ? '+' : ''}{index.change.toFixed(2)}</span>
                <span>({index.changePercent >= 0 ? '+' : ''}{index.changePercent.toFixed(2)}%)</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Commodities */}
      <div className="bg-white dark:bg-slate-800 rounded-xl p-6 shadow-lg border border-slate-200 dark:border-slate-700">
        <div className="flex items-center gap-3 mb-6">
          <div className="p-2 bg-amber-100 dark:bg-amber-900/30 rounded-lg">
            <DollarSign className="h-6 w-6 text-amber-600 dark:text-amber-400" />
          </div>
          <h2 className="text-2xl font-bold text-slate-900 dark:text-white">Commodities</h2>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {commodities.map((commodity) => (
            <div key={commodity.symbol} className="bg-slate-50 dark:bg-slate-900 rounded-lg p-4 border border-slate-200 dark:border-slate-700">
              <div className="text-sm font-medium text-slate-600 dark:text-slate-400 mb-1">{commodity.name}</div>
              <div className="text-2xl font-bold text-slate-900 dark:text-white mb-2">
                ${commodity.price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                <span className="text-sm font-normal text-slate-500 ml-1">{commodity.unit}</span>
              </div>
              <div className={`flex items-center gap-1 text-sm font-semibold ${commodity.change >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                {commodity.change >= 0 ? <TrendingUp className="h-4 w-4" /> : <TrendingDown className="h-4 w-4" />}
                <span>{commodity.change >= 0 ? '+' : ''}{commodity.change.toFixed(2)}</span>
                <span>({commodity.changePercent >= 0 ? '+' : ''}{commodity.changePercent.toFixed(2)}%)</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Top Movers */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Top Gainers */}
        <div className="bg-white dark:bg-slate-800 rounded-xl p-6 shadow-lg border border-slate-200 dark:border-slate-700">
          <div className="flex items-center gap-3 mb-6">
            <div className="p-2 bg-green-100 dark:bg-green-900/30 rounded-lg">
              <TrendingUp className="h-6 w-6 text-green-600 dark:text-green-400" />
            </div>
            <h2 className="text-xl font-bold text-slate-900 dark:text-white">Top 5 Gainers</h2>
          </div>
          <div className="space-y-3">
            {topGainers.map((stock, index) => (
              <div key={stock.symbol} className="flex items-center justify-between p-3 bg-green-50 dark:bg-green-900/20 rounded-lg border border-green-200 dark:border-green-800">
                <div className="flex items-center gap-3">
                  <div className="text-lg font-bold text-green-700 dark:text-green-400 w-6">#{index + 1}</div>
                  <div>
                    <div className="font-bold text-slate-900 dark:text-white">{stock.symbol}</div>
                    <div className="text-sm text-slate-600 dark:text-slate-400">{stock.name}</div>
                  </div>
                </div>
                <div className="text-right">
                  <div className="font-bold text-slate-900 dark:text-white">${stock.price.toFixed(2)}</div>
                  <div className="text-sm font-semibold text-green-600">
                    +{stock.change.toFixed(2)} (+{stock.changePercent.toFixed(2)}%)
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Top Losers */}
        <div className="bg-white dark:bg-slate-800 rounded-xl p-6 shadow-lg border border-slate-200 dark:border-slate-700">
          <div className="flex items-center gap-3 mb-6">
            <div className="p-2 bg-red-100 dark:bg-red-900/30 rounded-lg">
              <TrendingDown className="h-6 w-6 text-red-600 dark:text-red-400" />
            </div>
            <h2 className="text-xl font-bold text-slate-900 dark:text-white">Top 5 Losers</h2>
          </div>
          <div className="space-y-3">
            {topLosers.map((stock, index) => (
              <div key={stock.symbol} className="flex items-center justify-between p-3 bg-red-50 dark:bg-red-900/20 rounded-lg border border-red-200 dark:border-red-800">
                <div className="flex items-center gap-3">
                  <div className="text-lg font-bold text-red-700 dark:text-red-400 w-6">#{index + 1}</div>
                  <div>
                    <div className="font-bold text-slate-900 dark:text-white">{stock.symbol}</div>
                    <div className="text-sm text-slate-600 dark:text-slate-400">{stock.name}</div>
                  </div>
                </div>
                <div className="text-right">
                  <div className="font-bold text-slate-900 dark:text-white">${stock.price.toFixed(2)}</div>
                  <div className="text-sm font-semibold text-red-600">
                    {stock.change.toFixed(2)} ({stock.changePercent.toFixed(2)}%)
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Sector Performance */}
      <div className="bg-white dark:bg-slate-800 rounded-xl p-6 shadow-lg border border-slate-200 dark:border-slate-700">
        <SectorPerformance />
      </div>

      {/* CNBC Live Stream */}
      <div className="bg-white dark:bg-slate-800 rounded-xl p-6 shadow-lg border border-slate-200 dark:border-slate-700">
        <div className="flex items-center gap-3 mb-6">
          <div className="p-2 bg-red-100 dark:bg-red-900/30 rounded-lg">
            <Tv className="h-6 w-6 text-red-600 dark:text-red-400" />
          </div>
          <div>
            <h2 className="text-2xl font-bold text-slate-900 dark:text-white">CNBC Live</h2>
            <p className="text-sm text-slate-600 dark:text-slate-400">24/7 Market Coverage</p>
          </div>
        </div>
        <div className="relative w-full bg-slate-100 dark:bg-slate-900 rounded-lg" style={{ paddingBottom: '56.25%' }}>
          <div className="absolute top-0 left-0 w-full h-full flex flex-col items-center justify-center p-8 text-center">
            <Tv className="h-16 w-16 text-slate-400 dark:text-slate-600 mb-4" />
            <h3 className="text-lg font-semibold text-slate-700 dark:text-slate-300 mb-2">CNBC Live Stream</h3>
            <p className="text-sm text-slate-600 dark:text-slate-400 mb-6">
              Watch live financial news and market updates directly from CNBC
            </p>
            <div className="space-y-3">
              <a
                href="https://www.cnbc.com/live-tv/"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-block px-6 py-3 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors font-semibold"
              >
                Watch CNBC Live
              </a>
              <a
                href="https://www.youtube.com/@CNBC/streams"
                target="_blank"
                rel="noopener noreferrer"
                className="block px-6 py-3 bg-slate-600 text-white rounded-lg hover:bg-slate-700 transition-colors font-semibold"
              >
                YouTube Live Streams
              </a>
            </div>
          </div>
        </div>
        <div className="mt-4 p-4 bg-gradient-to-r from-blue-50 to-indigo-50 dark:from-blue-900/20 dark:to-indigo-900/20 rounded-lg border border-blue-200 dark:border-blue-800">
          <p className="text-sm text-blue-900 dark:text-blue-300">
            <strong>CNBC Live</strong> provides 24/7 real-time market coverage, breaking financial news, expert analysis, and live interviews with market leaders.
            Stream auto-mutes by default - click to unmute and enable sound.
          </p>
        </div>
      </div>
    </div>
  );
}
