import { useState } from 'react';
import { X, Mail, Lock, User } from 'lucide-react';

interface AuthModalProps {
  onClose: () => void;
  onAuthSuccess: () => void;
}

export default function AuthModal({ onClose, onAuthSuccess }: AuthModalProps) {
  const [isLogin, setIsLogin] = useState(true);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    setTimeout(() => {
      setLoading(false);
      onAuthSuccess();
    }, 1000);
  };

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="flex min-h-screen items-center justify-center p-4">
        <div className="fixed inset-0 bg-slate-900 bg-opacity-75 transition-opacity" onClick={onClose}></div>

        <div className="relative bg-white rounded-2xl shadow-2xl max-w-md w-full p-8 transform transition-all">
          <button
            onClick={onClose}
            className="absolute top-4 right-4 text-slate-400 hover:text-slate-600 transition-colors"
          >
            <X className="h-6 w-6" />
          </button>

          <div className="mb-8">
            <h2 className="text-3xl font-bold text-slate-900 mb-2">
              {isLogin ? 'Welcome Back' : 'Create Account'}
            </h2>
            <p className="text-slate-600">
              {isLogin
                ? 'Sign in to access your trading dashboard'
                : 'Join thousands of traders worldwide'}
            </p>
          </div>

          {error && (
            <div className="mb-6 bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-6">
            {!isLogin && (
              <div>
                <label htmlFor="fullName" className="block text-sm font-medium text-slate-700 mb-2">
                  Full Name
                </label>
                <div className="relative">
                  <User className="absolute left-3 top-1/2 transform -translate-y-1/2 h-5 w-5 text-slate-400" />
                  <input
                    id="fullName"
                    type="text"
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    className="w-full pl-10 pr-4 py-3 border border-slate-300 rounded-lg focus:ring-2 focus:ring-daman-blue-500 focus:border-daman-blue-500 transition-colors"
                    placeholder="John Doe"
                    required
                  />
                </div>
              </div>
            )}

            <div>
              <label htmlFor="email" className="block text-sm font-medium text-slate-700 mb-2">
                Email Address
              </label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 transform -translate-y-1/2 h-5 w-5 text-slate-400" />
                <input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full pl-10 pr-4 py-3 border border-slate-300 rounded-lg focus:ring-2 focus:ring-daman-blue-500 focus:border-daman-blue-500 transition-colors"
                  placeholder="you@example.com"
                  required
                />
              </div>
            </div>

            <div>
              <label htmlFor="password" className="block text-sm font-medium text-slate-700 mb-2">
                Password
              </label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 transform -translate-y-1/2 h-5 w-5 text-slate-400" />
                <input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full pl-10 pr-4 py-3 border border-slate-300 rounded-lg focus:ring-2 focus:ring-daman-blue-500 focus:border-daman-blue-500 transition-colors"
                  placeholder="••••••••"
                  required
                  minLength={6}
                />
              </div>
            </div>

            {isLogin && (
              <div className="flex items-center justify-between text-sm">
                <label className="flex items-center">
                  <input
                    type="checkbox"
                    className="rounded border-slate-300 text-daman-blue-600 focus:ring-daman-blue-500"
                  />
                  <span className="ml-2 text-slate-600">Remember me</span>
                </label>
                <button type="button" className="text-daman-blue-600 hover:text-daman-blue-700 font-medium">
                  Forgot password?
                </button>
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-daman-blue-600 text-white py-3 rounded-lg font-semibold hover:bg-daman-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? 'Processing...' : isLogin ? 'Sign In' : 'Create Account'}
            </button>
          </form>

          <div className="mt-6 text-center">
            <p className="text-slate-600">
              {isLogin ? "Don't have an account? " : 'Already have an account? '}
              <button
                onClick={() => {
                  setIsLogin(!isLogin);
                  setError('');
                }}
                className="text-daman-blue-600 hover:text-daman-blue-700 font-semibold"
              >
                {isLogin ? 'Sign up' : 'Sign in'}
              </button>
            </p>
          </div>

          <div className="mt-8 pt-6 border-t border-slate-200">
            <p className="text-xs text-slate-500 text-center leading-relaxed">
              By continuing, you agree to our Terms of Service and Privacy Policy. Your account is protected by industry-standard encryption and security measures.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
