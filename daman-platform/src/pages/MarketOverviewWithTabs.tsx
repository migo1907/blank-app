import { useState, lazy, Suspense } from 'react';
import { TrendingUp, Search, Newspaper } from 'lucide-react';

// Lazy-load each tab so the Market Overview page only ships the active tab's
// code. The default "overview" tab loads first; Search/News load on click.
const UltimateMarketHub = lazy(() => import('./UltimateMarketHub'));
const StockSearch = lazy(() => import('./StockSearch'));
const NewsFeed = lazy(() => import('./NewsFeed'));

function TabLoader() {
  return (
    <div className="flex items-center justify-center py-24" role="status" aria-label="Loading">
      <div className="h-10 w-10 rounded-full border-4 border-slate-200 dark:border-slate-700 border-t-blue-600 animate-spin" />
    </div>
  );
}

export default function MarketOverviewWithTabs() {
  const [activeTab, setActiveTab] = useState<'overview' | 'search' | 'news'>('overview');

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900">
      <div className="bg-white dark:bg-slate-800 shadow-md sticky top-16 z-40">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex space-x-8 border-b border-slate-200 dark:border-slate-700">
            <button
              onClick={() => setActiveTab('overview')}
              className={`flex items-center space-x-2 px-4 py-4 border-b-2 transition-colors font-medium ${
                activeTab === 'overview'
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-slate-600 dark:text-slate-400 hover:text-blue-600'
              }`}
            >
              <TrendingUp className="h-5 w-5" />
              <span>Market Overview</span>
            </button>
            <button
              onClick={() => setActiveTab('search')}
              className={`flex items-center space-x-2 px-4 py-4 border-b-2 transition-colors font-medium ${
                activeTab === 'search'
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-slate-600 dark:text-slate-400 hover:text-blue-600'
              }`}
            >
              <Search className="h-5 w-5" />
              <span>Stock Search</span>
            </button>
            <button
              onClick={() => setActiveTab('news')}
              className={`flex items-center space-x-2 px-4 py-4 border-b-2 transition-colors font-medium ${
                activeTab === 'news'
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-slate-600 dark:text-slate-400 hover:text-blue-600'
              }`}
            >
              <Newspaper className="h-5 w-5" />
              <span>News</span>
            </button>
          </div>
        </div>
      </div>

      <Suspense fallback={<TabLoader />}>
        {/* key replays the fade transition when switching tabs */}
        <div key={activeTab} className="animate-fadeIn">
          {activeTab === 'overview' && <UltimateMarketHub />}
          {activeTab === 'search' && <StockSearch />}
          {activeTab === 'news' && <NewsFeed />}
        </div>
      </Suspense>
    </div>
  );
}
