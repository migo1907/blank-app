import { useState, useEffect, useMemo, useCallback } from 'react';
import { Newspaper, Clock, TrendingUp, RefreshCw, ExternalLink, Activity, AlertCircle, Zap } from 'lucide-react';
import NewsCard from '../components/NewsCard';
import { supabase } from '../lib/supabase';

interface NewsArticle {
  id: string;
  title: string;
  description: string;
  url: string;
  source: string;
  publishedAt: string;
  category: string;
  imageUrl?: string;
  isBreaking?: boolean;
  breakingNewsTime?: string;
}

export default function NewsFeed() {
  const [news, setNews] = useState<NewsArticle[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [lastUpdate, setLastUpdate] = useState<Date>(new Date());
  const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(true);

  const AUTO_REFRESH_INTERVAL = 3 * 60 * 1000;

  const fetchNewsFromAPI = async () => {
    try {
      const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
      const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

      if (!supabaseUrl || !supabaseKey) {
        console.error('Supabase credentials not configured');
        return;
      }

      const apiUrl = `${supabaseUrl}/functions/v1/fetch-news?mode=all`;

      const response = await fetch(apiUrl, {
        headers: {
          'Authorization': `Bearer ${supabaseKey}`,
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }

      const result = await response.json();

      if (result.success && result.articles) {
        const formattedArticles = result.articles.map((article: any) => ({
          id: article.id || article.url,
          title: article.title,
          description: article.description || '',
          url: article.url,
          source: article.source,
          publishedAt: article.published_at || article.publishedAt,
          category: article.category,
          imageUrl: article.image_url || article.imageUrl,
          isBreaking: article.is_breaking || false,
          breakingNewsTime: article.breaking_news_time || null,
        }));
        setNews(formattedArticles);
      }
    } catch (error) {
      console.error('Error fetching news from API:', error);
      await fetchNewsFromDatabase();
    }
  };

  const fetchNewsFromDatabase = async () => {
    try {
      const { data, error } = await supabase
        .from('news_articles')
        .select('*')
        .order('published_at', { ascending: false })
        .limit(200);

      if (error) throw error;

      if (data) {
        // Filter for premium financial news sources only
        const premiumSources = [
          'cnbc', 'bloomberg', 'reuters', 'wall street journal', 'wsj',
          'financial times', 'marketwatch', 'seeking alpha', 'barrons',
          'investor\'s business daily', 'the economist', 'forbes'
        ];

        const qualityNews = data.filter((article: any) => {
          const source = (article.source || '').toLowerCase();
          return premiumSources.some(premium => source.includes(premium));
        });

        const formattedArticles = qualityNews.map((article: any) => ({
          id: article.id,
          title: article.title,
          description: article.description || '',
          url: article.url,
          source: article.source,
          publishedAt: article.published_at,
          category: article.category,
          imageUrl: article.image_url,
          isBreaking: article.is_breaking || false,
          breakingNewsTime: article.breaking_news_time || null,
        }));
        setNews(formattedArticles);
      }
    } catch (error) {
      console.error('Error fetching news from database:', error);
    }
  };

  const loadNews = useCallback(async () => {
    setLoading(true);
    await fetchNewsFromAPI();
    setLastUpdate(new Date());
    setLoading(false);
  }, []);

  useEffect(() => {
    loadNews();
  }, []);

  useEffect(() => {
    if (!autoRefreshEnabled) return;

    const interval = setInterval(() => {
      loadNews();
    }, AUTO_REFRESH_INTERVAL);

    return () => clearInterval(interval);
  }, [autoRefreshEnabled, loadNews, AUTO_REFRESH_INTERVAL]);

  const handleRefresh = () => {
    loadNews();
  };

  const categories = [
    'all',
    'Breaking',
    'Markets',
    'Technology',
    'Economy',
    'Finance',
    'Energy',
    'Healthcare',
    'Consumer',
    'Automotive',
    'Crypto',
    'Real Estate',
    'Industrials',
    'Materials',
    'Utilities'
  ];

  const filteredNews = useMemo(() => {
    if (selectedCategory === 'all') {
      return news;
    }
    if (selectedCategory === 'Breaking') {
      return news.filter(article => article.isBreaking);
    }
    return news.filter(article => article.category === selectedCategory);
  }, [news, selectedCategory]);

  // Breaking news from Financial Juice - only show red label news (within 30 minutes)
  const breakingNews = useMemo(() => {
    const now = Date.now();
    return news.filter(article => {
      if (!article.isBreaking || !article.breakingNewsTime) return false;

      // Check if source is Financial Juice
      const source = (article.source || '').toLowerCase();
      const isFinancialJuice = source.includes('financial') || source.includes('juice');

      // Check if within 30 minutes
      const breakingTime = new Date(article.breakingNewsTime).getTime();
      const diffMins = Math.floor((now - breakingTime) / 60000);
      const isRecent = diffMins <= 30;

      return isFinancialJuice && isRecent;
    }).slice(0, 5);
  }, [news]);

  const getTimeAgo = useCallback((dateString: string) => {
    const now = Date.now();
    const publishedDate = new Date(dateString).getTime();
    const diffMs = now - publishedDate;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);

    if (diffMins < 60) {
      return `${diffMins}m ago`;
    } else if (diffHours < 24) {
      return `${diffHours}h ago`;
    } else {
      return new Date(publishedDate).toLocaleDateString();
    }
  }, []);

  const nextUpdate = useMemo(() => {
    const nextTime = new Date(lastUpdate.getTime() + AUTO_REFRESH_INTERVAL);
    const minutesUntil = Math.floor((nextTime.getTime() - Date.now()) / 60000);
    return minutesUntil > 0 ? minutesUntil : 0;
  }, [lastUpdate, AUTO_REFRESH_INTERVAL]);

  return (
    <div className="min-h-screen bg-slate-50 py-8">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-6">
          <div className="mb-4 md:mb-0">
            <div className="flex items-center space-x-3 mb-2">
              <Newspaper className="h-8 w-8 text-daman-blue-600" />
              <h1 className="text-3xl font-bold text-slate-900">Financial News Feed</h1>
            </div>
            <p className="text-slate-600">
              Live updates from 15+ premium sources: Bloomberg, Reuters, WSJ, CNBC, Financial Times, TechCrunch & more
            </p>
            <div className="flex items-center space-x-4 mt-2 text-sm">
              <div className="flex items-center space-x-2 text-slate-500">
                <Clock className="h-4 w-4" />
                <span>Last updated: {lastUpdate.toLocaleTimeString()}</span>
              </div>
              {autoRefreshEnabled && (
                <div className="flex items-center space-x-2 text-green-600">
                  <Activity className="h-4 w-4 animate-pulse" />
                  <span>Auto-refresh in {nextUpdate} min</span>
                </div>
              )}
            </div>
          </div>
          <div className="flex items-center space-x-3">
            <button
              onClick={() => setAutoRefreshEnabled(!autoRefreshEnabled)}
              className={`px-4 py-2 rounded-lg font-medium text-sm transition-all border-2 ${
                autoRefreshEnabled
                  ? 'bg-green-50 border-green-300 text-green-700'
                  : 'bg-slate-100 border-slate-300 text-slate-600'
              }`}
            >
              {autoRefreshEnabled ? 'Auto-refresh: ON' : 'Auto-refresh: OFF'}
            </button>
            <button
              onClick={handleRefresh}
              disabled={loading}
              className="flex items-center space-x-2 px-4 py-2 bg-daman-blue-600 text-white rounded-lg hover:bg-daman-blue-700 transition-all disabled:opacity-50"
            >
              <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
              <span>Refresh</span>
            </button>
          </div>
        </div>

        {/* Breaking News Banner - Financial Juice Only */}
        {breakingNews.length > 0 && (
          <div className="mb-6 bg-gradient-to-r from-red-600 to-red-700 rounded-xl shadow-lg overflow-hidden border-2 border-red-800">
            <div className="p-4">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center space-x-2">
                  <Zap className="h-5 w-5 text-yellow-300 animate-pulse" />
                  <h2 className="text-xl font-bold text-white">Breaking News</h2>
                  <span className="px-2 py-1 bg-red-900 text-red-100 text-xs rounded-full font-semibold">LIVE</span>
                </div>
                <a
                  href="https://www.financialjuice.com/home"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-red-100 hover:text-white transition-colors"
                >
                  Source: Financial Juice
                </a>
              </div>
              <div className="space-y-3">
                {breakingNews.map((article) => (
                  <a
                    key={article.id}
                    href={article.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block bg-white bg-opacity-10 hover:bg-opacity-20 rounded-lg p-3 transition-all"
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-2">
                          <span className="px-2 py-0.5 bg-red-900 text-white text-xs font-bold rounded">RED LABEL</span>
                          <span className="text-red-100 text-xs">Expires in {Math.max(0, 30 - Math.floor((Date.now() - new Date(article.breakingNewsTime!).getTime()) / 60000))} min</span>
                        </div>
                        <h3 className="text-white font-semibold mb-1 line-clamp-2">{article.title}</h3>
                        <div className="flex items-center space-x-3 text-sm text-red-100">
                          <span className="font-semibold">{article.source}</span>
                          <span>•</span>
                          <span>{getTimeAgo(article.publishedAt)}</span>
                        </div>
                      </div>
                      <ExternalLink className="h-4 w-4 text-white ml-3 flex-shrink-0" />
                    </div>
                  </a>
                ))}
              </div>
              <div className="mt-3 text-xs text-red-100">
                Breaking news automatically expires after 30 minutes
              </div>
            </div>
          </div>
        )}

        {/* Category Filter */}
        <div className="mb-6 bg-white rounded-xl shadow-md border border-slate-200 p-4">
          <div className="flex items-center space-x-2 mb-3">
            <TrendingUp className="h-5 w-5 text-daman-blue-600" />
            <h3 className="text-lg font-bold text-slate-900">Filter by Sector</h3>
          </div>
          <div className="flex flex-wrap gap-2">
            {categories.map((category) => (
              <button
                key={category}
                onClick={() => setSelectedCategory(category)}
                className={`px-4 py-2 rounded-lg font-medium text-sm transition-all border-2 ${
                  selectedCategory === category
                    ? 'bg-daman-blue-600 border-daman-blue-600 text-white shadow-md'
                    : 'bg-white border-slate-200 text-slate-700 hover:border-daman-blue-300 hover:bg-daman-blue-50'
                } ${category === 'Breaking' ? 'border-red-500 text-red-600 hover:bg-red-50' : ''} ${
                  selectedCategory === category && category === 'Breaking' ? 'bg-red-600 border-red-600 text-white' : ''
                }`}
              >
                {category === 'Breaking' && <Zap className="inline h-3 w-3 mr-1" />}
                {category}
              </button>
            ))}
          </div>
        </div>

        {/* Stats Bar */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <div className="bg-white rounded-xl shadow-md border border-slate-200 p-4">
            <div className="text-sm text-slate-600 mb-1">Total Articles</div>
            <div className="text-2xl font-bold text-slate-900">{news.length}</div>
          </div>
          <div className="bg-white rounded-xl shadow-md border border-slate-200 p-4">
            <div className="text-sm text-slate-600 mb-1">Breaking News</div>
            <div className="text-2xl font-bold text-red-600">{news.filter(a => a.isBreaking).length}</div>
          </div>
          <div className="bg-white rounded-xl shadow-md border border-slate-200 p-4">
            <div className="text-sm text-slate-600 mb-1">Selected Category</div>
            <div className="text-2xl font-bold text-daman-blue-600">{filteredNews.length}</div>
          </div>
          <div className="bg-white rounded-xl shadow-md border border-slate-200 p-4">
            <div className="text-sm text-slate-600 mb-1">Premium Sources</div>
            <div className="text-2xl font-bold text-green-600">15+</div>
          </div>
        </div>

        {/* News Grid */}
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Activity className="h-12 w-12 animate-spin text-daman-blue-600" />
            <span className="ml-3 text-slate-600 text-lg">Loading latest news...</span>
          </div>
        ) : filteredNews.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {filteredNews.map((article) => (
              <NewsCard
                key={article.id}
                title={article.title}
                description={article.description}
                url={article.url}
                source={article.source}
                publishedAt={article.publishedAt}
                category={article.category}
                imageUrl={article.imageUrl}
                isBreaking={article.isBreaking}
                breakingNewsTime={article.breakingNewsTime}
              />
            ))}
          </div>
        ) : (
          <div className="text-center py-12 bg-white rounded-xl shadow-md border border-slate-200">
            <AlertCircle className="h-16 w-16 text-slate-300 mx-auto mb-4" />
            <p className="text-slate-600 text-lg">No articles found in this category</p>
            <button
              onClick={() => setSelectedCategory('all')}
              className="mt-4 px-6 py-2 bg-daman-blue-600 text-white rounded-lg hover:bg-daman-blue-700 transition-all"
            >
              View All News
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
