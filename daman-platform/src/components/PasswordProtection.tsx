import { useState } from 'react';
import { Lock, Eye, EyeOff, AlertCircle } from 'lucide-react';

interface PasswordProtectionProps {
  onUnlock: () => void;
  title?: string;
  description?: string;
}

export default function PasswordProtection({
  onUnlock,
  title = "Protected Access",
  description = "Enter password to access this feature"
}: PasswordProtectionProps) {
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [isShaking, setIsShaking] = useState(false);

  const CORRECT_PASSWORD = 'migo';

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    if (password === CORRECT_PASSWORD) {
      setError('');
      onUnlock();
    } else {
      setError('Incorrect password');
      setIsShaking(true);
      setTimeout(() => setIsShaking(false), 500);
      setPassword('');
    }
  };

  return (
    <div className="min-h-[400px] flex items-center justify-center p-4">
      <div className={`w-full max-w-md ${isShaking ? 'animate-shake' : ''}`}>
        <div className="bg-white rounded-xl shadow-lg border border-slate-200 p-8">
          <div className="flex justify-center mb-6">
            <div className="w-16 h-16 bg-daman-blue-100 rounded-full flex items-center justify-center">
              <Lock className="w-8 h-8 text-daman-blue-600" />
            </div>
          </div>

          <h2 className="text-2xl font-bold text-center text-slate-900 mb-2">
            {title}
          </h2>
          <p className="text-center text-slate-600 mb-6">
            {description}
          </p>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-2">
                Password
              </label>
              <div className="relative">
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => {
                    setPassword(e.target.value);
                    setError('');
                  }}
                  placeholder="Enter password"
                  className={`w-full px-4 py-3 pr-12 rounded-lg border ${
                    error
                      ? 'border-red-300 focus:border-red-500 focus:ring-red-500'
                      : 'border-slate-300 focus:border-daman-blue-500 focus:ring-daman-blue-500'
                  } focus:outline-none focus:ring-2 transition-colors`}
                  autoFocus
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 transition-colors"
                >
                  {showPassword ? (
                    <EyeOff className="w-5 h-5" />
                  ) : (
                    <Eye className="w-5 h-5" />
                  )}
                </button>
              </div>

              {error && (
                <div className="mt-2 flex items-center gap-2 text-red-600 text-sm">
                  <AlertCircle className="w-4 h-4" />
                  <span>{error}</span>
                </div>
              )}
            </div>

            <button
              type="submit"
              className="w-full bg-daman-blue-600 text-white py-3 rounded-lg font-medium hover:bg-daman-blue-700 transition-colors focus:outline-none focus:ring-2 focus:ring-daman-blue-500 focus:ring-offset-2"
            >
              Unlock
            </button>
          </form>

          <div className="mt-6 text-center text-sm text-slate-500">
            <p>This feature requires authentication</p>
          </div>
        </div>
      </div>

      <style>{`
        @keyframes shake {
          0%, 100% { transform: translateX(0); }
          10%, 30%, 50%, 70%, 90% { transform: translateX(-10px); }
          20%, 40%, 60%, 80% { transform: translateX(10px); }
        }
        .animate-shake {
          animation: shake 0.5s ease-in-out;
        }
      `}</style>
    </div>
  );
}
