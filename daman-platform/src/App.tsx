import { useState, lazy, Suspense } from 'react';
import { Globe, Shield, Menu, X, Moon, Sun } from 'lucide-react';
import DamanLogo from './components/DamanLogo';
import MobileBottomNav from './components/MobileBottomNav';
import BackToTop from './components/BackToTop';
import FloatingHermes from './components/FloatingHermes';
import InstallPrompt from './components/InstallPrompt';
import { ToastProvider } from './components/ToastContainer';
import { useTheme } from './contexts/ThemeContext';

// Lazy-load pages so the initial bundle only ships what first paint needs.
// Each page becomes its own chunk, fetched on demand when navigated to.
const HomePage = lazy(() => import('./pages/HomePage'));
const MarketOverviewWithTabs = lazy(() => import('./pages/MarketOverviewWithTabs'));
const AIStrategist = lazy(() => import('./pages/AIStrategist'));
const Portfolio = lazy(() => import('./pages/Portfolio'));
const WatchlistPage = lazy(() => import('./pages/WatchlistPage'));
const SettingsPage = lazy(() => import('./pages/SettingsPage'));

// Lightweight fallback shown while a page chunk loads.
function PageLoader() {
  return (
    <div className="flex items-center justify-center min-h-[60vh]" role="status" aria-label="Loading">
      <div className="h-10 w-10 rounded-full border-4 border-slate-200 dark:border-slate-700 border-t-blue-600 animate-spin" />
    </div>
  );
}

function App() {
  const { theme, toggleTheme } = useTheme();
  const [currentPage, setCurrentPage] = useState<'home' | 'market-overview' | 'ai-strategist' | 'portfolio' | 'watchlist' | 'settings'>('home');
  const [isMenuOpen, setIsMenuOpen] = useState(false);

  const navigation = [
    { name: 'Home', id: 'home' as const },
    { name: 'Market Overview', id: 'market-overview' as const },
    { name: 'AI Strategist', id: 'ai-strategist' as const },
    { name: 'Portfolio', id: 'portfolio' as const },
    { name: 'Watchlist', id: 'watchlist' as const },
    { name: 'Settings', id: 'settings' as const },
  ];

  const handleNavigation = (page: string) => {
    const validPages = ['home', 'market-overview', 'ai-strategist', 'portfolio', 'watchlist', 'settings'];
    if (validPages.includes(page)) {
      setCurrentPage(page as typeof currentPage);
      setIsMenuOpen(false);
    }
  };

  return (
    <ToastProvider>
      <div className="min-h-screen bg-slate-50 dark:bg-slate-900 pb-16 md:pb-0 transition-colors duration-200">
        <nav className="bg-white dark:bg-slate-800 shadow-md sticky top-0 z-50 transition-colors duration-200">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="flex justify-between h-16">
              <div className="flex items-center">
                <DamanLogo size="md" />
              </div>

              <div className="hidden md:flex items-center space-x-8">
                <button
                  onClick={toggleTheme}
                  className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
                  aria-label="Toggle theme"
                >
                  {theme === 'dark' ? (
                    <Sun className="h-5 w-5 text-slate-700 dark:text-slate-300" />
                  ) : (
                    <Moon className="h-5 w-5 text-slate-700" />
                  )}
                </button>
                {navigation.map((item) => (
                  <button
                    key={item.id}
                    onClick={() => handleNavigation(item.id)}
                    className={`group relative text-sm font-medium transition-colors pb-1 ${
                      currentPage === item.id
                        ? 'text-blue-600'
                        : 'text-slate-700 dark:text-slate-300 hover:text-blue-600'
                    }`}
                  >
                    {item.name}
                    {/* Animated underline: full width when active, grows on hover otherwise */}
                    <span
                      className={`pointer-events-none absolute left-0 -bottom-0 h-0.5 bg-blue-600 transition-all duration-300 ${
                        currentPage === item.id ? 'w-full' : 'w-0 group-hover:w-full'
                      }`}
                    />
                  </button>
                ))}
                <a
                  href="https://www.clientam.com/sso/Login?partnerID=ds2020"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="bg-blue-600 text-white px-6 py-2 rounded-lg font-medium hover:bg-blue-700 transition-colors inline-block"
                >
                  Login
                </a>
              </div>

              <div className="md:hidden flex items-center">
                <button
                  onClick={() => setIsMenuOpen(!isMenuOpen)}
                  className="text-slate-700 dark:text-slate-300 hover:text-blue-600"
                >
                  {isMenuOpen ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
                </button>
              </div>
            </div>
          </div>

          {isMenuOpen && (
            <div className="md:hidden bg-white dark:bg-slate-800 border-t border-slate-200 dark:border-slate-700 animate-slideUp">
              <div className="px-4 pt-2 pb-4 space-y-2">
                <button
                  onClick={toggleTheme}
                  className="flex items-center justify-between w-full px-4 py-2 rounded-lg text-sm font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700 transition-colors"
                >
                  <span>{theme === 'dark' ? 'Light Mode' : 'Dark Mode'}</span>
                  {theme === 'dark' ? (
                    <Sun className="h-5 w-5 text-slate-300" />
                  ) : (
                    <Moon className="h-5 w-5 text-slate-700" />
                  )}
                </button>
                {navigation.map((item) => (
                  <button
                    key={item.id}
                    onClick={() => handleNavigation(item.id)}
                    className={`block w-full text-left px-4 py-2 rounded-lg text-sm font-medium ${
                      currentPage === item.id
                        ? 'bg-blue-50 dark:bg-blue-900/20 text-blue-600'
                        : 'text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700'
                    }`}
                  >
                    {item.name}
                  </button>
                ))}
                <a
                  href="https://www.clientam.com/sso/Login?partnerID=ds2020"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block w-full text-center bg-blue-600 text-white px-4 py-2 rounded-lg font-medium hover:bg-blue-700 transition-colors mt-2"
                >
                  Login
                </a>
              </div>
            </div>
          )}
        </nav>

        <main>
          {/* key forces a remount per page so the fade-in transition replays on navigation */}
          <Suspense fallback={<PageLoader />}>
            <div key={currentPage} className="animate-fadeIn">
              {currentPage === 'home' && <HomePage onNavigate={handleNavigation} />}
              {currentPage === 'market-overview' && <MarketOverviewWithTabs />}
              {currentPage === 'ai-strategist' && <AIStrategist />}
              {currentPage === 'portfolio' && <Portfolio />}
              {currentPage === 'watchlist' && <WatchlistPage />}
              {currentPage === 'settings' && <SettingsPage />}
            </div>
          </Suspense>
        </main>

        <MobileBottomNav
          currentPage={currentPage}
          onNavigate={handleNavigation}
          onMenuClick={() => setIsMenuOpen(!isMenuOpen)}
        />

        <BackToTop />
        <FloatingHermes />
        <InstallPrompt />

        <footer className="bg-slate-900 text-white mt-20">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-8">
              <div>
                <DamanLogo size="sm" className="mb-4" />
                <p className="text-slate-300 text-sm">
                  Real-time financial market dashboard with live data integration
                </p>
              </div>

              <div>
                <h3 className="font-semibold mb-4">Features</h3>
                <ul className="space-y-2 text-sm text-slate-300">
                  <li>Live Market Data</li>
                  <li>Portfolio Tracking</li>
                  <li>Price Alerts</li>
                  <li>Real-Time News</li>
                </ul>
              </div>

              <div>
                <h3 className="font-semibold mb-4">Data Sources</h3>
                <ul className="space-y-2 text-sm text-slate-300">
                  <li>Alpaca Markets</li>
                  <li>Yahoo Finance</li>
                  <li>Real-Time APIs</li>
                  <li>Supabase Database</li>
                </ul>
              </div>

              <div>
                <h3 className="font-semibold mb-4">Compliance</h3>
                <div className="flex items-center space-x-2 mb-2">
                  <Globe className="h-4 w-4 text-blue-300" />
                  <span className="text-sm text-slate-300">Global Access</span>
                </div>
                <div className="flex items-center space-x-2">
                  <Shield className="h-4 w-4 text-blue-300" />
                  <span className="text-sm text-slate-300">Secure Platform</span>
                </div>
              </div>
            </div>

            <div className="border-t border-slate-800 mt-8 pt-8 text-center text-sm text-slate-300 space-y-4">
              <p className="text-yellow-400 font-semibold">
                DISCLAIMER: This is a demonstration platform using real market data. Not for actual trading.
              </p>
              <p>&copy; 2025 Market Dashboard. All rights reserved.</p>
            </div>
          </div>
        </footer>
      </div>
    </ToastProvider>
  );
}

export default App;
