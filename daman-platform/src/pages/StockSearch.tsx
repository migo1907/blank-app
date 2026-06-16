import { useState } from 'react';
import { Search, Info } from 'lucide-react';
import AdvancedStockSearch from '../components/AdvancedStockSearch';
import StockDetail from './StockDetail';

export default function StockSearch() {
  const [selectedStock, setSelectedStock] = useState<string | null>(null);

  if (selectedStock) {
    return (
      <div className="min-h-screen bg-slate-50 dark:bg-slate-900">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <button
            onClick={() => setSelectedStock(null)}
            className="mb-6 flex items-center space-x-2 text-daman-blue-600 dark:text-daman-blue-400 hover:text-daman-blue-700 dark:hover:text-daman-blue-300 font-medium transition-colors"
          >
            <span>←</span>
            <span>Back to Search</span>
          </button>
          <StockDetail symbol={selectedStock} onBack={() => setSelectedStock(null)} />
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900 py-8 transition-colors duration-200">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="mb-8">
          <div className="flex items-center space-x-3 mb-4">
            <Search className="h-8 w-8 text-daman-blue-600 dark:text-daman-blue-400" />
            <h1 className="text-3xl font-bold text-slate-900 dark:text-white">Stock Search</h1>
          </div>
          <p className="text-slate-600 dark:text-slate-400 mb-4">
            Search and analyze stocks from our universe of 81 companies
          </p>

          <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4 flex items-start space-x-3">
            <Info className="h-5 w-5 text-blue-600 dark:text-blue-400 flex-shrink-0 mt-0.5" />
            <div className="text-sm">
              <p className="text-blue-900 dark:text-blue-100 font-medium mb-1">How to Use Stock Search:</p>
              <ul className="text-blue-800 dark:text-blue-200 space-y-1 list-disc list-inside">
                <li>Enter a company name or ticker symbol in the search box</li>
                <li>Use filters to narrow results by sector, exchange, price range, or market cap</li>
                <li>Click "View Details" on any stock to see comprehensive analysis</li>
                <li>Live prices are fetched when available, with fallback to cached data</li>
              </ul>
            </div>
          </div>
        </div>

        <AdvancedStockSearch onSelectStock={(symbol) => setSelectedStock(symbol)} />
      </div>
    </div>
  );
}
