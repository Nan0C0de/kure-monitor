import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';

const AuthContext = createContext(null);

const API_BASE = window.location.hostname === 'localhost' && window.location.port === '3000'
  ? 'http://localhost:8000'
  : '';

export function AuthProvider({ children }) {
  const [apiKey, setApiKey] = useState(() => sessionStorage.getItem('kure-auth-key'));
  const [userRole, setUserRole] = useState(() => sessionStorage.getItem('kure-auth-role') || null);
  const [authEnabled, setAuthEnabled] = useState(null); // null = loading
  const [authChecked, setAuthChecked] = useState(false);

  // Check if auth is enabled on mount (and resolve role for existing key)
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const headers = {};
        const storedKey = sessionStorage.getItem('kure-auth-key');
        if (storedKey) {
          headers['Authorization'] = `Bearer ${storedKey}`;
        }
        const res = await fetch(`${API_BASE}/api/auth/status`, { headers });
        if (res.ok) {
          const data = await res.json();
          if (!cancelled) {
            setAuthEnabled(data.enabled);
            setAuthChecked(true);
            if (data.role) {
              setUserRole(data.role);
              sessionStorage.setItem('kure-auth-role', data.role);
            } else if (!data.enabled) {
              // Auth disabled = full admin access
              setUserRole('admin');
              sessionStorage.setItem('kure-auth-role', 'admin');
            }
          }
        } else {
          // If endpoint doesn't exist (old backend), assume auth disabled
          if (!cancelled) {
            setAuthEnabled(false);
            setUserRole('admin');
            setAuthChecked(true);
          }
        }
      } catch {
        // Network error - assume auth disabled so dashboard still works
        if (!cancelled) {
          setAuthEnabled(false);
          setUserRole('admin');
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
    const data = await res.json();
    sessionStorage.setItem('kure-auth-key', key);
    setApiKey(key);

    const role = data.role || 'viewer';
    sessionStorage.setItem('kure-auth-role', role);
    setUserRole(role);
  }, []);

  const logout = useCallback(() => {
    sessionStorage.removeItem('kure-auth-key');
    sessionStorage.removeItem('kure-auth-role');
    setApiKey(null);
    setUserRole(null);
  }, []);

  return (
    <AuthContext.Provider value={{ apiKey, isAuthenticated, authEnabled, authChecked, userRole, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
