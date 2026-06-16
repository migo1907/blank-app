import { useState } from 'react';
import { Target } from 'lucide-react';
import StockSignals from '../components/StockSignals';
import SPXOptionsFlow from '../components/SPXOptionsFlow';
import QuantFilter from '../components/QuantFilter';
import IBKROptionsChain from '../components/IBKROptionsChain';
import StockSearch from './StockSearch';
import PasswordProtection from '../components/PasswordProtection';

export default function ScannerHub() {
  const [scannerTab, setScannerTab] = useState<'signals' | 'search' | 'spx-flow' | 'stocks' | 'ibkr'>('signals');
  const [isScannerUnlocked, setIsScannerUnlocked] = useState(false);

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900 py-6 px-4">
      <div className="max-w-7xl mx-auto">
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
                <Target className="h-7 w-7 text-blue-600" />
                <span>Scanner Tools</span>
              </h2>

              {/* Scanner Tabs */}
              <div className="flex flex-wrap space-x-2 mb-6 border-b border-slate-200 dark:border-slate-700">
                <button
                  onClick={() => setScannerTab('signals')}
                  className={`px-6 py-3 font-semibold transition-all whitespace-nowrap ${
                    scannerTab === 'signals'
                      ? 'border-b-2 border-blue-600 text-blue-600'
                      : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
                  }`}
                >
                  Stock Signals
                </button>
                <button
                  onClick={() => setScannerTab('spx-flow')}
                  className={`px-6 py-3 font-semibold transition-all whitespace-nowrap ${
                    scannerTab === 'spx-flow'
                      ? 'border-b-2 border-blue-600 text-blue-600'
                      : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
                  }`}
                >
                  SPX Options Flow
                </button>
                <button
                  onClick={() => setScannerTab('stocks')}
                  className={`px-6 py-3 font-semibold transition-all whitespace-nowrap ${
                    scannerTab === 'stocks'
                      ? 'border-b-2 border-blue-600 text-blue-600'
                      : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
                  }`}
                >
                  QuantFlow Scanner
                </button>
                <button
                  onClick={() => setScannerTab('ibkr')}
                  className={`px-6 py-3 font-semibold transition-all whitespace-nowrap ${
                    scannerTab === 'ibkr'
                      ? 'border-b-2 border-blue-600 text-blue-600'
                      : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
                  }`}
                >
                  IBKR Options Chain
                </button>
                <button
                  onClick={() => setScannerTab('search')}
                  className={`px-6 py-3 font-semibold transition-all whitespace-nowrap ${
                    scannerTab === 'search'
                      ? 'border-b-2 border-blue-600 text-blue-600'
                      : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
                  }`}
                >
                  Stock Search
                </button>
              </div>

              {/* Scanner Content */}
              <div className="mt-6">
                {scannerTab === 'signals' && <StockSignals />}
                {scannerTab === 'search' && <StockSearch />}
                {scannerTab === 'spx-flow' && <SPXOptionsFlow />}
                {scannerTab === 'stocks' && <QuantFilter />}
                {scannerTab === 'ibkr' && <IBKROptionsChain />}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
