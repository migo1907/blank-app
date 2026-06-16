import { useState, useEffect } from 'react';
import { Settings as SettingsIcon, Bell, Moon, Sun, Database, Download, Upload, Check, Palette } from 'lucide-react';
import { useTheme } from '../contexts/ThemeContext';

interface UserSettings {
  notifications: boolean;
  soundAlerts: boolean;
  priceAlerts: boolean;
  refreshInterval: number;
  dataRetention: number;
}

export default function SettingsPage() {
  const { theme, toggleTheme } = useTheme();
  const [settings, setSettings] = useState<UserSettings>({
    notifications: true,
    soundAlerts: true,
    priceAlerts: true,
    refreshInterval: 30,
    dataRetention: 90
  });

  const [saved, setSaved] = useState(false);

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = () => {
    const saved = localStorage.getItem('appSettings');
    if (saved) {
      setSettings(JSON.parse(saved));
    }
  };

  const saveSettings = () => {
    localStorage.setItem('appSettings', JSON.stringify(settings));
    setSaved(true);
    setTimeout(() => setSaved(false), 3000);

    if ('Notification' in window && settings.notifications && Notification.permission === 'default') {
      Notification.requestPermission();
    }
  };

  const setTheme = (newTheme: 'light' | 'dark') => {
    if (newTheme !== theme) {
      toggleTheme();
    }
  };

  const exportData = () => {
    const data = {
      settings,
      portfolio: localStorage.getItem('portfolio'),
      watchlist: localStorage.getItem('watchlist_v2'),
      exportDate: new Date().toISOString()
    };

    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `market-dashboard-export-${new Date().toISOString().split('T')[0]}.json`;
    a.click();
  };

  const importData = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const data = JSON.parse(e.target?.result as string);
        if (data.settings) {
          setSettings(data.settings);
          localStorage.setItem('appSettings', JSON.stringify(data.settings));
        }
        if (data.portfolio) localStorage.setItem('portfolio', data.portfolio);
        if (data.watchlist) localStorage.setItem('watchlist_v2', data.watchlist);
        alert('Data imported successfully!');
        window.location.reload();
      } catch (error) {
        alert('Error importing data. Please check the file format.');
      }
    };
    reader.readAsText(file);
  };

  const clearAllData = () => {
    if (confirm('Are you sure you want to clear all data? This cannot be undone.')) {
      localStorage.clear();
      alert('All data cleared successfully');
      window.location.reload();
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-purple-50 to-slate-50 dark:bg-gradient-to-br dark:from-slate-900 dark:via-slate-800 dark:to-slate-900 p-4 md:p-8">
      <div className="max-w-4xl mx-auto">
        <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-2xl border border-slate-200 dark:border-slate-700 p-6 md:p-8 mb-6">
          <div className="flex items-center space-x-3 mb-8">
            <div className="bg-gradient-to-br from-purple-600 to-purple-700 p-3 rounded-xl">
              <SettingsIcon className="h-7 w-7 text-white" />
            </div>
            <div>
              <h1 className="text-2xl md:text-3xl font-bold text-slate-900 dark:text-white">Settings</h1>
              <p className="text-slate-600 dark:text-slate-400 text-sm">Customize your market dashboard experience</p>
            </div>
          </div>

          <div className="space-y-6">
            <div className="bg-slate-50 dark:bg-slate-900 rounded-xl p-6 border border-slate-200 dark:border-slate-700">
              <div className="flex items-center space-x-2 mb-4">
                <Bell className="h-5 w-5 text-purple-600 dark:text-purple-400" />
                <h3 className="font-bold text-lg text-slate-900 dark:text-white">Notifications</h3>
              </div>

              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="font-medium text-slate-900 dark:text-white">Enable Notifications</div>
                    <div className="text-sm text-slate-600 dark:text-slate-400">Receive alerts for important events</div>
                  </div>
                  <button
                    onClick={() => setSettings({ ...settings, notifications: !settings.notifications })}
                    className={`relative w-12 h-6 rounded-full transition-colors ${
                      settings.notifications ? 'bg-green-500' : 'bg-slate-300 dark:bg-slate-600'
                    }`}
                  >
                    <div className={`absolute top-1 left-1 w-4 h-4 bg-white rounded-full transition-transform ${
                      settings.notifications ? 'translate-x-6' : ''
                    }`} />
                  </button>
                </div>

                <div className="flex items-center justify-between">
                  <div>
                    <div className="font-medium text-slate-900 dark:text-white">Sound Alerts</div>
                    <div className="text-sm text-slate-600 dark:text-slate-400">Play sound for notifications</div>
                  </div>
                  <button
                    onClick={() => setSettings({ ...settings, soundAlerts: !settings.soundAlerts })}
                    className={`relative w-12 h-6 rounded-full transition-colors ${
                      settings.soundAlerts ? 'bg-green-500' : 'bg-slate-300 dark:bg-slate-600'
                    }`}
                  >
                    <div className={`absolute top-1 left-1 w-4 h-4 bg-white rounded-full transition-transform ${
                      settings.soundAlerts ? 'translate-x-6' : ''
                    }`} />
                  </button>
                </div>

                <div className="flex items-center justify-between">
                  <div>
                    <div className="font-medium text-slate-900 dark:text-white">Price Alerts</div>
                    <div className="text-sm text-slate-600 dark:text-slate-400">Notify when prices hit targets</div>
                  </div>
                  <button
                    onClick={() => setSettings({ ...settings, priceAlerts: !settings.priceAlerts })}
                    className={`relative w-12 h-6 rounded-full transition-colors ${
                      settings.priceAlerts ? 'bg-green-500' : 'bg-slate-300 dark:bg-slate-600'
                    }`}
                  >
                    <div className={`absolute top-1 left-1 w-4 h-4 bg-white rounded-full transition-transform ${
                      settings.priceAlerts ? 'translate-x-6' : ''
                    }`} />
                  </button>
                </div>
              </div>
            </div>

            <div className="bg-slate-50 dark:bg-slate-900 rounded-xl p-6 border border-slate-200 dark:border-slate-700">
              <div className="flex items-center space-x-2 mb-4">
                <Palette className="h-5 w-5 text-purple-600 dark:text-purple-400" />
                <h3 className="font-bold text-lg text-slate-900 dark:text-white">Appearance</h3>
              </div>

              <div className="space-y-4">
                <div>
                  <label className="block font-medium text-slate-900 dark:text-white mb-2">Theme</label>
                  <div className="grid grid-cols-2 gap-3">
                    <button
                      onClick={() => setTheme('light')}
                      className={`flex items-center justify-center space-x-2 py-3 rounded-lg border-2 transition-all ${
                        theme === 'light'
                          ? 'border-blue-600 bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-400'
                          : 'border-slate-200 dark:border-slate-700 hover:border-slate-300 text-slate-700 dark:text-slate-300'
                      }`}
                    >
                      <Sun className="h-5 w-5" />
                      <span className="font-medium">Light</span>
                    </button>
                    <button
                      onClick={() => setTheme('dark')}
                      className={`flex items-center justify-center space-x-2 py-3 rounded-lg border-2 transition-all ${
                        theme === 'dark'
                          ? 'border-blue-600 bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-400'
                          : 'border-slate-200 dark:border-slate-700 hover:border-slate-300 text-slate-700 dark:text-slate-300'
                      }`}
                    >
                      <Moon className="h-5 w-5" />
                      <span className="font-medium">Dark</span>
                    </button>
                  </div>
                  <p className="text-sm text-slate-600 dark:text-slate-400 mt-2">
                    Current theme: <span className="font-semibold capitalize">{theme}</span>
                  </p>
                </div>
              </div>
            </div>

            <div className="bg-slate-50 dark:bg-slate-900 rounded-xl p-6 border border-slate-200 dark:border-slate-700">
              <div className="flex items-center space-x-2 mb-4">
                <Database className="h-5 w-5 text-purple-600 dark:text-purple-400" />
                <h3 className="font-bold text-lg text-slate-900 dark:text-white">Data & Performance</h3>
              </div>

              <div className="space-y-4">
                <div>
                  <label className="block font-medium text-slate-900 dark:text-white mb-2">
                    Refresh Interval
                  </label>
                  <select
                    value={settings.refreshInterval}
                    onChange={(e) => setSettings({ ...settings, refreshInterval: parseInt(e.target.value) })}
                    className="w-full px-4 py-3 border-2 border-slate-300 dark:border-slate-600 dark:bg-slate-800 dark:text-white rounded-xl focus:border-purple-500 focus:outline-none"
                  >
                    <option value="15">15 seconds</option>
                    <option value="30">30 seconds</option>
                    <option value="60">1 minute</option>
                    <option value="300">5 minutes</option>
                  </select>
                </div>

                <div>
                  <label className="block font-medium text-slate-900 dark:text-white mb-2">
                    Data Retention (days)
                  </label>
                  <input
                    type="number"
                    value={settings.dataRetention}
                    onChange={(e) => setSettings({ ...settings, dataRetention: parseInt(e.target.value) })}
                    min="7"
                    max="365"
                    className="w-full px-4 py-3 border-2 border-slate-300 dark:border-slate-600 dark:bg-slate-800 dark:text-white rounded-xl focus:border-purple-500 focus:outline-none"
                  />
                  <div className="text-sm text-slate-600 dark:text-slate-400 mt-1">
                    How long to keep historical data (7-365 days)
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <button
                    onClick={exportData}
                    className="flex items-center justify-center space-x-2 px-4 py-3 bg-blue-600 text-white rounded-xl hover:bg-blue-700 transition-all font-medium"
                  >
                    <Download className="h-5 w-5" />
                    <span>Export Data</span>
                  </button>

                  <label className="flex items-center justify-center space-x-2 px-4 py-3 bg-green-600 text-white rounded-xl hover:bg-green-700 transition-all font-medium cursor-pointer">
                    <Upload className="h-5 w-5" />
                    <span>Import Data</span>
                    <input
                      type="file"
                      accept=".json"
                      onChange={importData}
                      className="hidden"
                    />
                  </label>
                </div>

                <button
                  onClick={clearAllData}
                  className="w-full px-4 py-3 bg-red-100 dark:bg-red-900/20 text-red-700 dark:text-red-400 rounded-xl hover:bg-red-200 dark:hover:bg-red-900/30 transition-all font-medium border-2 border-red-200 dark:border-red-800"
                >
                  Clear All Data
                </button>
              </div>
            </div>
          </div>

          <div className="mt-8 flex space-x-4">
            <button
              onClick={saveSettings}
              className="flex-1 flex items-center justify-center space-x-2 py-4 bg-gradient-to-r from-purple-600 to-purple-700 text-white rounded-xl hover:from-purple-700 hover:to-purple-800 transition-all font-semibold shadow-lg"
            >
              {saved ? (
                <>
                  <Check className="h-5 w-5" />
                  <span>Saved!</span>
                </>
              ) : (
                <>
                  <SettingsIcon className="h-5 w-5" />
                  <span>Save Settings</span>
                </>
              )}
            </button>
          </div>
        </div>

        <div className="bg-purple-50 dark:bg-purple-900/20 border border-purple-200 dark:border-purple-800 rounded-xl p-4">
          <p className="text-sm text-purple-800 dark:text-purple-300">
            <strong>Settings:</strong> All preferences are saved locally in your browser.
            Export your data regularly to keep backups of your portfolio and watchlist.
          </p>
        </div>
      </div>
    </div>
  );
}
