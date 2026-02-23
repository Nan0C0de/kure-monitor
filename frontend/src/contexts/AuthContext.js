import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';

const AuthContext = createContext(null);

const API_BASE = window.location.hostname === 'localhost' && window.location.port === '3000'
  ? 'http://localhost:8000'
  : '';

export function AuthProvider({ children }) {
  const [apiKey, setApiKey] = useState(() => sessionStorage.getItem('kure-auth-key'));
  const [authEnabled, setAuthEnabled] = useState(null); // null = loading
  const [authChecked, setAuthChecked] = useState(false);

  // Check if auth is enabled on mount
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/api/auth/status`);
        if (res.ok) {
          const data = await res.json();
          if (!cancelled) {
            setAuthEnabled(data.enabled);
            setAuthChecked(true);
          }
        } else {
          // If endpoint doesn't exist (old backend), assume auth disabled
          if (!cancelled) {
            setAuthEnabled(false);
            setAuthChecked(true);
          }
        }
      } catch {
        // Network error - assume auth disabled so dashboard still works
        if (!cancelled) {
          setAuthEnabled(false);
          setAuthChecked(true);
        }
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const isAuthenticated = authEnabled === false || !!apiKey;

  const login = useCallback(async (key) => {
    const res = await fetch(`${API_BASE}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_key: key }),
    });
    if (!res.ok) {
      throw new Error('Invalid API key');
    }
    sessionStorage.setItem('kure-auth-key', key);
    setApiKey(key);
  }, []);

  const logout = useCallback(() => {
    sessionStorage.removeItem('kure-auth-key');
    setApiKey(null);
  }, []);

  return (
    <AuthContext.Provider value={{ apiKey, isAuthenticated, authEnabled, authChecked, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
