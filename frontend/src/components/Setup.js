import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Server, UserPlus } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';

const MIN_PASSWORD_LENGTH = 8;
const USERNAME_MIN = 3;
const USERNAME_MAX = 64;

const Setup = () => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [repeatPassword, setRepeatPassword] = useState('');
  const [email, setEmail] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const { setup, setupRequired, isAuthenticated, authChecked } = useAuth();
  const navigate = useNavigate();

  const [isDark] = useState(() => {
    if (typeof window !== 'undefined') {
      return localStorage.getItem('kure-theme') === 'dark';
    }
    return false;
  });

  useEffect(() => {
    if (isDark) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, [isDark]);

  // If setup is not required, kick the user to login or dashboard.
  useEffect(() => {
    if (!authChecked) return;
    if (!setupRequired) {
      navigate(isAuthenticated ? '/' : '/login', { replace: true });
    }
  }, [setupRequired, isAuthenticated, authChecked, navigate]);

  const validate = () => {
    if (username.trim().length < USERNAME_MIN || username.trim().length > USERNAME_MAX) {
      return `Username must be between ${USERNAME_MIN} and ${USERNAME_MAX} characters`;
    }
    if (password.length < MIN_PASSWORD_LENGTH) {
      return `Password must be at least ${MIN_PASSWORD_LENGTH} characters`;
    }
    if (password !== repeatPassword) {
      return 'Passwords do not match';
    }
    return null;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const validationError = validate();
    if (validationError) {
      setError(validationError);
      return;
    }

    setLoading(true);
    setError('');
    try {
      await setup({
        username: username.trim(),
        password,
        email: email.trim() || undefined,
      });
      navigate('/', { replace: true });
    } catch (err) {
      if (err?.status === 409) {
        setError(err?.message || 'Setup has already been completed.');
      } else {
        setError(err?.message || 'Setup failed');
      }
    } finally {
      setLoading(false);
    }
  };

  const inputCls = `w-full px-4 py-3 rounded-md border text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 ${
    isDark
      ? 'bg-gray-700 border-gray-600 text-gray-200 placeholder-gray-500'
      : 'bg-white border-gray-300 text-gray-900 placeholder-gray-400'
  }`;
  const labelCls = `block text-sm font-medium mb-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`;

  return (
    <div className={`min-h-screen flex items-center justify-center ${isDark ? 'bg-gray-900' : 'bg-gray-100'}`}>
      <div className={`w-full max-w-md p-8 rounded-lg shadow-lg ${isDark ? 'bg-gray-800' : 'bg-white'}`}>
        <div className="flex flex-col items-center mb-6">
          <Server className={`w-12 h-12 mb-3 ${isDark ? 'text-blue-400' : 'text-blue-500'}`} />
          <h1 className={`text-2xl font-bold ${isDark ? 'text-gray-100' : 'text-gray-900'}`}>
            Welcome to Kure Monitor
          </h1>
          <p className={`mt-2 text-sm text-center ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
            Create the first admin account to get started.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <label htmlFor="setup-username" className={labelCls}>Username</label>
            <input
              id="setup-username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="3–64 characters"
              autoComplete="username"
              autoFocus
              className={inputCls}
            />
          </div>

          <div>
            <label htmlFor="setup-password" className={labelCls}>Password</label>
            <input
              id="setup-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="At least 8 characters"
              autoComplete="new-password"
              className={inputCls}
            />
          </div>

          <div>
            <label htmlFor="setup-repeat-password" className={labelCls}>Repeat password</label>
            <input
              id="setup-repeat-password"
              type="password"
              value={repeatPassword}
              onChange={(e) => setRepeatPassword(e.target.value)}
              placeholder="Repeat password"
              autoComplete="new-password"
              className={inputCls}
            />
          </div>

          <div>
            <label htmlFor="setup-email" className={labelCls}>Email (optional)</label>
            <input
              id="setup-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              autoComplete="email"
              className={inputCls}
            />
          </div>

          {error && (
            <div
              role="alert"
              className={`text-sm p-3 rounded-md ${isDark ? 'bg-red-900/50 text-red-300' : 'bg-red-50 text-red-700'}`}
            >
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className={`w-full flex items-center justify-center space-x-2 px-4 py-3 rounded-md text-sm font-medium text-white transition-colors ${
              loading ? 'bg-blue-400 cursor-not-allowed' : 'bg-blue-600 hover:bg-blue-700'
            }`}
          >
            {loading ? (
              <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
            ) : (
              <>
                <UserPlus className="w-4 h-4" />
                <span>Create admin account</span>
              </>
            )}
          </button>
        </form>
      </div>
    </div>
  );
};

export default Setup;
