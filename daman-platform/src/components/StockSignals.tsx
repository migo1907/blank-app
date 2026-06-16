import { useState, useEffect } from 'react';
import { TrendingUp, TrendingDown, Activity, Clock, RefreshCw, AlertCircle, Target, Zap, Copy, CheckCircle, Trash2, FlaskConical } from 'lucide-react';
import { supabase } from '../lib/supabase';

interface StockSignal {
  id: string;
  timestamp: string;
  ticker: string;
  signal_type: string;
  price: number;
  timeframe: string;
  indicator: string | null;
  strategy: string | null;
  stop_loss: number | null;
  take_profit: number | null;
  message: string | null;
  is_active: boolean;
  created_at: string;
  notes: string | null;
}

export default function StockSignals() {
  const [signals, setSignals] = useState<StockSignal[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<'ALL' | 'BUY' | 'SELL' | 'LONG' | 'SHORT'>('ALL');
  const [showWebhookInfo, setShowWebhookInfo] = useState(false);
  const [webhookCopied, setWebhookCopied] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [testingWebhook, setTestingWebhook] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);

  const webhookUrl = `${import.meta.env.VITE_SUPABASE_URL}/functions/v1/stock-signals-webhook`;

  useEffect(() => {
    loadSignals();

    const subscription = supabase
      .channel('stock_signals_changes')
      .on('postgres_changes',
        { event: '*', schema: 'public', table: 'stock_signals' },
        (payload) => {
          console.log('Signal change detected:', payload);
          loadSignals();
        }
      )
      .subscribe();

    let interval: NodeJS.Timeout | null = null;
    if (autoRefresh) {
      interval = setInterval(() => {
        loadSignals();
      }, 30000);
    }

    return () => {
      subscription.unsubscribe();
      if (interval) clearInterval(interval);
    };
  }, [autoRefresh]);

  const loadSignals = async () => {
    try {
      setLoading(true);
      console.log('Loading signals from database...');

      const { data, error } = await supabase
        .from('stock_signals')
        .select('*')
        .order('timestamp', { ascending: false })
        .limit(100);

      if (error) {
        console.error('Supabase error:', error);
        throw error;
      }

      if (data) {
        console.log(`Loaded ${data.length} signals from database`);
        console.log('First signal sample:', data[0]);
        setSignals(data);
      } else {
        console.warn('No data returned from database');
        setSignals([]);
      }
    } catch (error) {
      console.error('Error loading signals:', error);
      setSignals([]);
    } finally {
      setLoading(false);
    }
  };

  const deleteSignal = async (id: string) => {
    if (!confirm('Delete this signal?')) return;

    try {
      const { error } = await supabase
        .from('stock_signals')
        .delete()
        .eq('id', id);

      if (error) throw error;
      loadSignals();
    } catch (error) {
      console.error('Error deleting signal:', error);
    }
  };

  const toggleSignalActive = async (id: string, currentState: boolean) => {
    try {
      const { error } = await supabase
        .from('stock_signals')
        .update({ is_active: !currentState })
        .eq('id', id);

      if (error) throw error;
      loadSignals();
    } catch (error) {
      console.error('Error updating signal:', error);
    }
  };

  const copyWebhookUrl = () => {
    navigator.clipboard.writeText(webhookUrl);
    setWebhookCopied(true);
    setTimeout(() => setWebhookCopied(false), 2000);
  };

  const testWebhook = async () => {
    setTestingWebhook(true);
    setTestResult(null);

    try {
      const testData = {
        ticker: 'AAPL',
        signal_type: 'BUY',
        price: 182.50,
        timeframe: '5m',
        indicator: 'Test Signal',
        strategy: 'Webhook Test',
        stop_loss: 180.00,
        take_profit: 185.00,
        message: 'This is a test signal from the Test Webhook button'
      };

      const response = await fetch(webhookUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(testData)
      });

      const result = await response.json();

      if (response.ok) {
        setTestResult({
          success: true,
          message: 'Test signal sent successfully! Check the signals list below.'
        });
        setTimeout(() => {
          loadSignals();
        }, 1000);
      } else {
        setTestResult({
          success: false,
          message: `Error: ${result.error || 'Failed to send test signal'}`
        });
      }
    } catch (error) {
      setTestResult({
        success: false,
        message: `Network error: ${error instanceof Error ? error.message : 'Unknown error'}`
      });
    } finally {
      setTestingWebhook(false);
      setTimeout(() => setTestResult(null), 5000);
    }
  };

  const filteredSignals = signals.filter(signal => {
    if (filter === 'ALL') return true;
    return signal.signal_type === filter;
  });

  const activeSignals = signals.filter(s => s.is_active).length;
  const buySignals = signals.filter(s => s.signal_type === 'BUY' || s.signal_type === 'LONG').length;
  const sellSignals = signals.filter(s => s.signal_type === 'SELL' || s.signal_type === 'SHORT').length;

  return (
    <div className="space-y-6">
      <div className="bg-gradient-to-r from-daman-blue-600 to-blue-700 rounded-xl p-6 text-white">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center space-x-3">
            <Activity className="h-8 w-8" />
            <div>
              <h2 className="text-2xl font-bold">Stock Signals from TradingView</h2>
              <p className="text-blue-100">Real-time trading signals via webhook integration</p>
            </div>
          </div>
          <button
            onClick={() => setShowWebhookInfo(!showWebhookInfo)}
            className="px-4 py-2 bg-white/20 hover:bg-white/30 rounded-lg font-semibold flex items-center space-x-2"
          >
            <Zap className="h-4 w-4" />
            <span>Webhook Info</span>
          </button>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-white/10 rounded-lg p-3">
            <div className="text-blue-100 text-sm mb-1">Total Signals</div>
            <div className="text-2xl font-bold">{signals.length}</div>
          </div>
          <div className="bg-white/10 rounded-lg p-3">
            <div className="text-blue-100 text-sm mb-1">Active Signals</div>
            <div className="text-2xl font-bold text-green-300">{activeSignals}</div>
          </div>
          <div className="bg-white/10 rounded-lg p-3">
            <div className="text-blue-100 text-sm mb-1">Buy/Long</div>
            <div className="text-2xl font-bold text-green-300">{buySignals}</div>
          </div>
          <div className="bg-white/10 rounded-lg p-3">
            <div className="text-blue-100 text-sm mb-1">Sell/Short</div>
            <div className="text-2xl font-bold text-red-300">{sellSignals}</div>
          </div>
        </div>
      </div>

      {showWebhookInfo && (
        <div className="bg-white rounded-xl p-6 shadow-lg border border-slate-200">
          <h3 className="text-xl font-bold text-slate-900 mb-4 flex items-center space-x-2">
            <Zap className="h-6 w-6 text-yellow-500" />
            <span>TradingView Webhook Setup</span>
          </h3>

          <div className="space-y-4">
            <div>
              <label className="block text-sm font-semibold text-slate-700 mb-2">Webhook URL:</label>
              <div className="flex items-center space-x-2">
                <input
                  type="text"
                  value={webhookUrl}
                  readOnly
                  className="flex-1 px-4 py-2 border border-slate-300 rounded-lg bg-slate-50 font-mono text-sm"
                />
                <button
                  onClick={copyWebhookUrl}
                  className="px-4 py-2 bg-daman-blue-600 hover:bg-daman-blue-700 text-white rounded-lg font-semibold flex items-center space-x-2"
                >
                  {webhookCopied ? <CheckCircle className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                  <span>{webhookCopied ? 'Copied!' : 'Copy'}</span>
                </button>
                <button
                  onClick={testWebhook}
                  disabled={testingWebhook}
                  className="px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg font-semibold flex items-center space-x-2 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <FlaskConical className={`h-4 w-4 ${testingWebhook ? 'animate-pulse' : ''}`} />
                  <span>{testingWebhook ? 'Testing...' : 'Test'}</span>
                </button>
              </div>
            </div>

            {testResult && (
              <div className={`rounded-lg p-4 ${testResult.success ? 'bg-green-50 border border-green-200' : 'bg-red-50 border border-red-200'}`}>
                <div className="flex items-start space-x-3">
                  {testResult.success ? (
                    <CheckCircle className="h-5 w-5 text-green-600 mt-0.5 flex-shrink-0" />
                  ) : (
                    <AlertCircle className="h-5 w-5 text-red-600 mt-0.5 flex-shrink-0" />
                  )}
                  <div>
                    <p className={`font-semibold ${testResult.success ? 'text-green-900' : 'text-red-900'}`}>
                      {testResult.success ? 'Success!' : 'Error'}
                    </p>
                    <p className={`text-sm ${testResult.success ? 'text-green-700' : 'text-red-700'}`}>
                      {testResult.message}
                    </p>
                  </div>
                </div>
              </div>
            )}

            <div className="bg-slate-50 rounded-lg p-4">
              <p className="text-sm font-semibold text-slate-700 mb-2">TradingView Alert Message Format (JSON):</p>
              <pre className="text-xs bg-slate-900 text-green-400 p-3 rounded overflow-x-auto">
{`{
  "ticker": "{{ticker}}",
  "signal_type": "BUY",
  "price": {{close}},
  "timeframe": "{{interval}}",
  "indicator": "RSI Cross",
  "strategy": "My Strategy",
  "stop_loss": {{low}},
  "take_profit": {{high}},
  "message": "[◆] NEW SIGNAL | إشارة جديدة ◆ {{ticker}} ◆ {{interval}} ◆ Price: {{close}}"
}`}
              </pre>
            </div>

            <div className="bg-blue-50 rounded-lg p-4">
              <p className="text-sm font-semibold text-blue-900 mb-2">Setup Instructions:</p>
              <ol className="text-sm text-blue-800 space-y-2 list-decimal list-inside">
                <li>Copy the webhook URL above</li>
                <li>In TradingView, create an alert on your chart</li>
                <li>IMPORTANT: Check ☑ "Webhook URL" checkbox in alert settings</li>
                <li>Paste the webhook URL in the "Webhook URL" field</li>
                <li>Set "Message" to the JSON format above</li>
                <li>Customize signal_type: BUY, SELL, LONG, SHORT</li>
                <li>Click "Create" and signals will appear here automatically!</li>
              </ol>
            </div>

            <div className="bg-amber-50 rounded-lg p-4 border border-amber-200">
              <p className="text-sm font-semibold text-amber-900 mb-2 flex items-center space-x-2">
                <AlertCircle className="h-4 w-4" />
                <span>Troubleshooting: Alerts Not Appearing?</span>
              </p>
              <ul className="text-sm text-amber-800 space-y-1 list-disc list-inside">
                <li><strong>TradingView Pro/Premium required</strong> - Free accounts cannot use webhooks</li>
                <li><strong>Test button works but TradingView alerts don't?</strong> - Check webhook checkbox is enabled</li>
                <li><strong>Getting errors?</strong> - Verify JSON format is correct (no typos)</li>
                <li><strong>Signal shows wrong data?</strong> - Check ticker variable has quotes, close does not</li>
                <li><strong>Still not working?</strong> - See TRADINGVIEW_ALERT_TROUBLESHOOTING_GUIDE.md</li>
              </ul>
            </div>

            <div className="bg-green-50 rounded-lg p-4 border border-green-200">
              <p className="text-sm font-semibold text-green-900 mb-2 flex items-center space-x-2">
                <CheckCircle className="h-4 w-4" />
                <span>Quick Diagnostic:</span>
              </p>
              <div className="space-y-2 text-sm text-green-800">
                <div className="flex items-center space-x-2">
                  <span className={signals.length > 0 ? 'text-green-600' : 'text-red-600'}>
                    {signals.length > 0 ? '✅' : '❌'}
                  </span>
                  <span>Database Connection: {signals.length > 0 ? 'Working' : 'Check connection'}</span>
                </div>
                <div className="flex items-center space-x-2">
                  <span>⚠️</span>
                  <span>TradingView Account: Verify you have Pro/Premium subscription</span>
                </div>
                <div className="flex items-center space-x-2">
                  <span>💡</span>
                  <span>Use the Test button above to verify webhook is working</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="bg-white rounded-xl p-6 shadow-lg border border-slate-200">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center space-x-4">
            <button
              onClick={loadSignals}
              disabled={loading}
              className="px-4 py-2 bg-daman-blue-600 hover:bg-daman-blue-700 text-white rounded-lg font-semibold flex items-center space-x-2 disabled:opacity-50"
            >
              <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
              <span>Refresh</span>
            </button>

            <label className="flex items-center space-x-2 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.target.checked)}
                className="rounded"
              />
              <span>Auto-refresh (30s)</span>
            </label>
          </div>

          <div className="flex items-center space-x-2">
            {['ALL', 'BUY', 'SELL', 'LONG', 'SHORT'].map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f as any)}
                className={`px-3 py-1 rounded-lg text-sm font-semibold ${
                  filter === f
                    ? 'bg-daman-blue-600 text-white'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                }`}
              >
                {f}
              </button>
            ))}
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="bg-slate-100 border-b border-slate-200">
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-700">Time</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-700">Ticker</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-700">Signal</th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-slate-700">Price</th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-slate-700">Stop Loss</th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-slate-700">Take Profit</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-700">Timeframe</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-700">Indicator</th>
                <th className="px-4 py-3 text-center text-xs font-semibold text-slate-700">Status</th>
                <th className="px-4 py-3 text-center text-xs font-semibold text-slate-700">Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr>
                  <td colSpan={10} className="px-4 py-8 text-center text-slate-500">
                    <RefreshCw className="h-6 w-6 animate-spin mx-auto mb-2" />
                    <p>Loading signals...</p>
                  </td>
                </tr>
              )}
              {!loading && filteredSignals.length === 0 && (
                <tr>
                  <td colSpan={10} className="px-4 py-8 text-center text-slate-500">
                    <AlertCircle className="h-8 w-8 mx-auto mb-2 text-slate-400" />
                    <p>No signals yet. Set up TradingView webhook to receive alerts.</p>
                  </td>
                </tr>
              )}
              {!loading && filteredSignals.map((signal) => (
                <tr key={signal.id} className={`border-b border-slate-100 hover:bg-slate-50 ${!signal.is_active ? 'opacity-50' : ''}`}>
                  <td className="px-4 py-3 text-xs text-slate-600">
                    <div className="flex items-center space-x-1">
                      <Clock className="h-3 w-3" />
                      <span>{new Date(signal.timestamp).toLocaleString()}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-sm font-bold text-slate-900">{signal.ticker}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-flex items-center space-x-1 px-2 py-1 rounded text-xs font-bold ${
                        signal.signal_type === 'BUY' || signal.signal_type === 'LONG'
                          ? 'bg-green-100 text-green-800'
                          : signal.signal_type === 'SELL' || signal.signal_type === 'SHORT'
                          ? 'bg-red-100 text-red-800'
                          : 'bg-amber-100 text-amber-800'
                      }`}
                    >
                      {(signal.signal_type === 'BUY' || signal.signal_type === 'LONG') ? (
                        <TrendingUp className="h-3 w-3" />
                      ) : signal.signal_type === 'SELL' || signal.signal_type === 'SHORT' ? (
                        <TrendingDown className="h-3 w-3" />
                      ) : (
                        <AlertCircle className="h-3 w-3" />
                      )}
                      <span className="text-xs">{signal.signal_type.includes('{{') ? 'Invalid Signal' : signal.signal_type}</span>
                    </span>
                  </td>
                  <td className="px-4 py-3 text-sm font-mono text-right text-slate-900">${signal.price.toFixed(2)}</td>
                  <td className="px-4 py-3 text-sm font-mono text-right text-red-600">
                    {signal.stop_loss ? `$${signal.stop_loss.toFixed(2)}` : '-'}
                  </td>
                  <td className="px-4 py-3 text-sm font-mono text-right text-green-600">
                    {signal.take_profit ? `$${signal.take_profit.toFixed(2)}` : '-'}
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-700">{signal.timeframe}</td>
                  <td className="px-4 py-3 text-xs text-slate-700">{signal.indicator || '-'}</td>
                  <td className="px-4 py-3 text-center">
                    <button
                      onClick={() => toggleSignalActive(signal.id, signal.is_active)}
                      className={`px-2 py-1 rounded text-xs font-semibold ${
                        signal.is_active
                          ? 'bg-green-100 text-green-800'
                          : 'bg-slate-100 text-slate-600'
                      }`}
                    >
                      {signal.is_active ? 'Active' : 'Inactive'}
                    </button>
                  </td>
                  <td className="px-4 py-3 text-center">
                    <button
                      onClick={() => deleteSignal(signal.id)}
                      className="px-2 py-1 text-red-600 hover:bg-red-50 rounded"
                      title="Delete signal"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
