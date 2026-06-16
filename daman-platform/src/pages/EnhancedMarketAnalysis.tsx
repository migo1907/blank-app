import { useState, useEffect } from 'react';
import {
  TrendingUp, Activity, BarChart3, Newspaper, PieChart, Globe,
  Clock, Zap, Target, Award, Flame, AlertCircle
} from 'lucide-react';
import AdvancedTabSystem, { TabConfig } from '../components/AdvancedTabSystem';
import MarketDataTable from '../components/MarketDataTable';
import SectorPerformance from '../components/SectorPerformance';
import MarketSentiment from '../components/MarketSentiment';
import VolatilityAnalysis from '../components/VolatilityAnalysis';
import MarketBreadth from '../components/MarketBreadth';
import NewsCard from '../components/NewsCard';
import { supabase } from '../lib/supabase';

/**
 * Enhanced Market Analysis with Advanced Tab System
 *
 * Features:
 * - Professional multi-tab interface
 * - Drag & drop tab reordering
 * - Keyboard navigation
 * - State persistence
 * - Lazy loading
 * - Favorites and recent tabs
 */

interface NewsArticle {
  id: string;
  title: string;
  description: string;
  url: string;
  source: string;
  publishedAt: string;
  category: string;
  imageUrl?: string;
}

export default function EnhancedMarketAnalysis() {
  const [news, setNews] = useState<NewsArticle[]>([]);
  const [newsCategory, setNewsCategory] = useState('all');
  const [refreshKey, setRefreshKey] = useState(0);

  // Fetch news data
  useEffect(() => {
    fetchNews();
  }, []);

  const fetchNews = async () => {
    try {
      const { data } = await supabase
        .from('news_articles')
        .select('*')
        .order('published_at', { ascending: false })
        .limit(20);

      if (data) {
        setNews(data.map(article => ({
          id: article.id,
          title: article.title,
          description: article.description || '',
          url: article.url,
          source: article.source,
          publishedAt: article.published_at,
          category: article.category || 'general',
          imageUrl: article.image_url,
        })));
      } else {
        setNews(generateMockNews());
      }
    } catch (error) {
      console.error('Error fetching news:', error);
      setNews(generateMockNews());
    }
  };

  const generateMockNews = (): NewsArticle[] => {
    return [
      {
        id: '1',
        title: 'Tech Stocks Rally as AI Investments Surge',
        description: 'Major technology companies see significant gains following record AI sector investments.',
        url: 'https://www.cnbc.com',
        source: 'CNBC',
        publishedAt: new Date(Date.now() - 1000 * 60 * 30).toISOString(),
        category: 'technology',
      },
      {
        id: '2',
        title: 'Federal Reserve Signals Rate Decision',
        description: 'Markets react to latest Federal Reserve commentary on interest rate policy.',
        url: 'https://www.bloomberg.com',
        source: 'Bloomberg',
        publishedAt: new Date(Date.now() - 1000 * 60 * 60).toISOString(),
        category: 'economy',
      },
      {
        id: '3',
        title: 'Energy Sector Rebounds on Supply Concerns',
        description: 'Oil and gas stocks gain momentum amid global supply chain disruptions.',
        url: 'https://www.reuters.com',
        source: 'Reuters',
        publishedAt: new Date(Date.now() - 1000 * 60 * 90).toISOString(),
        category: 'energy',
      },
    ];
  };

  // Define tabs configuration
  const tabs: TabConfig[] = [
    {
      id: 'overview',
      label: 'Market Overview',
      icon: <TrendingUp className="h-4 w-4" />,
      badge: 'Live',
      content: (
        <div className="space-y-6">
          <div className="bg-gradient-to-r from-blue-600 to-blue-700 rounded-xl p-6 text-white">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-2xl font-bold">Global Markets Dashboard</h2>
              <div className="flex items-center space-x-2 text-blue-100">
                <Clock className="h-4 w-4" />
                <span className="text-sm">Updated {new Date().toLocaleTimeString()}</span>
              </div>
            </div>
            <p className="text-blue-100">
              Real-time market data, indices, and key indicators for comprehensive market analysis
            </p>
          </div>

          <MarketDataTable />

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="bg-white rounded-xl shadow-lg border border-slate-200 p-6">
              <h3 className="text-lg font-bold text-slate-900 mb-4 flex items-center space-x-2">
                <Activity className="h-5 w-5 text-blue-600" />
                <span>Market Breadth</span>
              </h3>
              <MarketBreadth />
            </div>

            <div className="bg-white rounded-xl shadow-lg border border-slate-200 p-6">
              <h3 className="text-lg font-bold text-slate-900 mb-4 flex items-center space-x-2">
                <Zap className="h-5 w-5 text-blue-600" />
                <span>Volatility Analysis</span>
              </h3>
              <VolatilityAnalysis />
            </div>
          </div>
        </div>
      ),
      closeable: false,
    },
    {
      id: 'sectors',
      label: 'Sector Analysis',
      icon: <PieChart className="h-4 w-4" />,
      content: (
        <div className="space-y-6">
          <div className="bg-gradient-to-r from-purple-600 to-purple-700 rounded-xl p-6 text-white">
            <h2 className="text-2xl font-bold mb-2">Sector Performance</h2>
            <p className="text-purple-100">
              Track sector rotation, relative strength, and industry-specific trends
            </p>
          </div>

          <SectorPerformance />

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {['Technology', 'Healthcare', 'Financial', 'Energy', 'Consumer', 'Industrial'].map((sector) => (
              <div key={sector} className="bg-white rounded-xl shadow-lg border border-slate-200 p-6">
                <h4 className="font-bold text-slate-900 mb-2">{sector}</h4>
                <div className="flex items-center justify-between">
                  <span className="text-2xl font-bold text-green-600">+{(Math.random() * 5).toFixed(2)}%</span>
                  <TrendingUp className="h-6 w-6 text-green-500" />
                </div>
                <div className="mt-4 text-sm text-slate-600">
                  <div className="flex justify-between">
                    <span>Gainers:</span>
                    <span className="font-semibold">{Math.floor(Math.random() * 50) + 20}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Losers:</span>
                    <span className="font-semibold">{Math.floor(Math.random() * 30) + 10}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      ),
      closeable: true,
      lazy: true,
    },
    {
      id: 'sentiment',
      label: 'Market Sentiment',
      icon: <Activity className="h-4 w-4" />,
      badge: 'AI',
      content: (
        <div className="space-y-6">
          <div className="bg-gradient-to-r from-green-600 to-green-700 rounded-xl p-6 text-white">
            <h2 className="text-2xl font-bold mb-2">AI-Powered Sentiment Analysis</h2>
            <p className="text-green-100">
              Advanced sentiment tracking from news, social media, and market behavior
            </p>
          </div>

          <MarketSentiment />

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="bg-white rounded-xl shadow-lg border border-slate-200 p-6">
              <h3 className="text-lg font-bold text-slate-900 mb-4">Fear & Greed Index</h3>
              <div className="flex items-center justify-center">
                <div className="relative w-48 h-48">
                  <svg className="transform -rotate-90 w-48 h-48">
                    <circle
                      cx="96"
                      cy="96"
                      r="80"
                      stroke="#e5e7eb"
                      strokeWidth="16"
                      fill="none"
                    />
                    <circle
                      cx="96"
                      cy="96"
                      r="80"
                      stroke="#10b981"
                      strokeWidth="16"
                      fill="none"
                      strokeDasharray={`${Math.PI * 160 * 0.65} ${Math.PI * 160}`}
                      className="transition-all duration-1000"
                    />
                  </svg>
                  <div className="absolute inset-0 flex flex-col items-center justify-center">
                    <span className="text-4xl font-bold text-green-600">65</span>
                    <span className="text-sm text-slate-600">Greed</span>
                  </div>
                </div>
              </div>
            </div>

            <div className="bg-white rounded-xl shadow-lg border border-slate-200 p-6">
              <h3 className="text-lg font-bold text-slate-900 mb-4">Sentiment Drivers</h3>
              <div className="space-y-3">
                {[
                  { label: 'News Sentiment', value: 72, color: 'green' },
                  { label: 'Social Media', value: 58, color: 'blue' },
                  { label: 'Options Activity', value: 65, color: 'purple' },
                  { label: 'Institutional Flow', value: 70, color: 'orange' },
                ].map((item) => (
                  <div key={item.label}>
                    <div className="flex justify-between mb-1">
                      <span className="text-sm text-slate-600">{item.label}</span>
                      <span className="text-sm font-semibold">{item.value}%</span>
                    </div>
                    <div className="w-full bg-slate-200 rounded-full h-2">
                      <div
                        className={`bg-${item.color}-500 h-2 rounded-full transition-all duration-500`}
                        style={{ width: `${item.value}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      ),
      closeable: true,
      lazy: true,
    },
    {
      id: 'news',
      label: 'Market News',
      icon: <Newspaper className="h-4 w-4" />,
      badge: news.length,
      content: (
        <div className="space-y-6">
          <div className="bg-gradient-to-r from-orange-600 to-orange-700 rounded-xl p-6 text-white">
            <h2 className="text-2xl font-bold mb-2">Latest Market News</h2>
            <p className="text-orange-100">
              Real-time news from trusted financial sources and market commentary
            </p>
          </div>

          {/* News Categories */}
          <div className="flex flex-wrap gap-2">
            {['all', 'technology', 'economy', 'energy', 'healthcare'].map((category) => (
              <button
                key={category}
                onClick={() => setNewsCategory(category)}
                className={`px-4 py-2 rounded-lg font-semibold transition-all ${
                  newsCategory === category
                    ? 'bg-orange-600 text-white shadow-lg'
                    : 'bg-white text-slate-700 border border-slate-200 hover:border-orange-300'
                }`}
              >
                {category.charAt(0).toUpperCase() + category.slice(1)}
              </button>
            ))}
          </div>

          {/* News Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {news
              .filter(article => newsCategory === 'all' || article.category === newsCategory)
              .map((article) => (
                <NewsCard
                  key={article.id}
                  title={article.title}
                  description={article.description}
                  url={article.url}
                  source={article.source}
                  publishedAt={article.publishedAt}
                  category={article.category}
                  imageUrl={article.imageUrl}
                />
              ))}
          </div>
        </div>
      ),
      closeable: true,
      lazy: true,
    },
    {
      id: 'volatility',
      label: 'Volatility Metrics',
      icon: <BarChart3 className="h-4 w-4" />,
      content: (
        <div className="space-y-6">
          <div className="bg-gradient-to-r from-red-600 to-red-700 rounded-xl p-6 text-white">
            <h2 className="text-2xl font-bold mb-2">Volatility & Risk Metrics</h2>
            <p className="text-red-100">
              Advanced volatility analysis and risk assessment tools
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {[
              { label: 'VIX', value: '18.45', change: '+2.3%', icon: Activity },
              { label: 'Put/Call Ratio', value: '1.12', change: '+0.08', icon: BarChart3 },
              { label: 'Implied Vol', value: '22.5%', change: '+1.2%', icon: TrendingUp },
              { label: 'Realized Vol', value: '19.8%', change: '-0.5%', icon: Target },
            ].map((metric) => (
              <div key={metric.label} className="bg-white rounded-xl shadow-lg border border-slate-200 p-6">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm text-slate-600">{metric.label}</span>
                  <metric.icon className="h-5 w-5 text-red-500" />
                </div>
                <div className="text-2xl font-bold text-slate-900">{metric.value}</div>
                <div className="text-sm text-green-600 font-semibold">{metric.change}</div>
              </div>
            ))}
          </div>

          <VolatilityAnalysis />
        </div>
      ),
      closeable: true,
      lazy: true,
    },
    {
      id: 'global',
      label: 'Global Markets',
      icon: <Globe className="h-4 w-4" />,
      content: (
        <div className="space-y-6">
          <div className="bg-gradient-to-r from-indigo-600 to-indigo-700 rounded-xl p-6 text-white">
            <h2 className="text-2xl font-bold mb-2">International Markets</h2>
            <p className="text-indigo-100">
              Track major indices and economic indicators from markets worldwide
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {[
              { region: 'Asia Pacific', markets: ['Nikkei 225', 'Hang Seng', 'Shanghai Composite'] },
              { region: 'Europe', markets: ['FTSE 100', 'DAX', 'CAC 40'] },
              { region: 'Americas', markets: ['S&P 500', 'TSX', 'Bovespa'] },
            ].map((region) => (
              <div key={region.region} className="bg-white rounded-xl shadow-lg border border-slate-200 p-6">
                <h3 className="text-lg font-bold text-slate-900 mb-4 flex items-center space-x-2">
                  <Globe className="h-5 w-5 text-indigo-600" />
                  <span>{region.region}</span>
                </h3>
                <div className="space-y-3">
                  {region.markets.map((market) => (
                    <div key={market} className="flex items-center justify-between p-3 bg-slate-50 rounded-lg">
                      <span className="font-semibold text-slate-900">{market}</span>
                      <div className="text-right">
                        <div className="font-bold text-green-600">+{(Math.random() * 3).toFixed(2)}%</div>
                        <div className="text-xs text-slate-500">{(Math.random() * 10000 + 30000).toFixed(2)}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      ),
      closeable: true,
      lazy: true,
    },
  ];

  const handleTabChange = (tabId: string) => {
    console.log('Tab changed to:', tabId);
  };

  const handleTabClose = (tabId: string) => {
    const confirmed = window.confirm(`Close ${tabId} tab?`);
    return confirmed;
  };

  const handleTabAdd = () => {
    console.log('Add new tab clicked');
    console.log('Custom tab creation coming soon!');
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-slate-50">
      <div className="max-w-[1600px] mx-auto p-6">
        {/* Page Header */}
        <div className="mb-6">
          <div className="flex items-center space-x-4 mb-2">
            <div className="p-3 bg-gradient-to-br from-blue-600 to-blue-700 rounded-xl shadow-lg">
              <BarChart3 className="h-8 w-8 text-white" />
            </div>
            <div>
              <h1 className="text-4xl font-bold text-slate-900">Market Analysis & News</h1>
              <p className="text-slate-600 mt-1">Comprehensive market data with advanced navigation</p>
            </div>
          </div>
        </div>

        {/* Advanced Tab System */}
        <div className="bg-white rounded-xl shadow-2xl border border-slate-200 overflow-hidden" style={{ minHeight: '700px' }}>
          <AdvancedTabSystem
            tabs={tabs}
            defaultActiveTab="overview"
            onTabChange={handleTabChange}
            onTabClose={handleTabClose}
            onTabAdd={handleTabAdd}
            persistState={true}
            storageKey="market-analysis-tabs"
            theme="light"
            maxVisibleTabs={6}
            enableDragDrop={true}
            enableSearch={true}
          />
        </div>

        {/* Quick Stats Footer */}
        <div className="mt-6 grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            { label: 'Active Alerts', value: '12', icon: AlertCircle, color: 'red' },
            { label: 'Watchlist Items', value: '24', icon: Award, color: 'yellow' },
            { label: 'Hot Sectors', value: '6', icon: Flame, color: 'orange' },
            { label: 'News Today', value: news.length, icon: Newspaper, color: 'blue' },
          ].map((stat) => (
            <div key={stat.label} className="bg-white rounded-xl shadow-lg border border-slate-200 p-4">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-2xl font-bold text-slate-900">{stat.value}</div>
                  <div className="text-sm text-slate-600">{stat.label}</div>
                </div>
                <stat.icon className={`h-8 w-8 text-${stat.color}-500`} />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
