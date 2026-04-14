import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { api } from '../services/api';

const AuthContext = createContext(null);

/**
 * AuthProvider manages the currently-logged-in user.
 *
 * Auth is cookie-based: the backend sets an HttpOnly `kure_session` cookie.
 * JS cannot read the cookie — we learn about the user by calling
 * `GET /api/auth/me`. A 401 means "not logged in".
 *
 * Additionally, on first boot we check `GET /api/auth/setup-required` so the
 * app can route to the first-run setup flow.
 */
export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [setupRequired, setSetupRequired] = useState(false);
  const [authChecked, setAuthChecked] = useState(false);

  const refreshAuth = useCallback(async () => {
    try {
      const setup = await api.getAuthSetupRequired();
      if (setup?.setup_required) {
        setSetupRequired(true);
        setUser(null);
        return { setupRequired: true, user: null };
      }
      setSetupRequired(false);
    } catch (err) {
      // Setup endpoint failure: fall through; let /me decide.
      setSetupRequired(false);
    }

    try {
      const me = await api.getAuthMe();
      setUser(me);
      return { setupRequired: false, user: me };
    } catch (err) {
      setUser(null);
      return { setupRequired: false, user: null };
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      await refreshAuth();
      if (!cancelled) {
        setAuthChecked(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [refreshAuth]);

  const login = useCallback(async ({ username, password }) => {
    await api.login({ username, password });
    const me = await api.getAuthMe();
    setUser(me);
    return me;
  }, []);

  const setup = useCallback(async ({ username, password, email }) => {
    await api.setupAdmin({ username, password, email });
    const me = await api.getAuthMe();
    setUser(me);
    setSetupRequired(false);
    return me;
  }, []);

  const acceptInvitation = useCallback(async ({ token, username, password, email }) => {
    await api.acceptInvitation({ token, username, password, email });
    const me = await api.getAuthMe();
    setUser(me);
    return me;
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.logout();
    } catch {
      // ignore - we're logging out locally anyway
    }
    setUser(null);
  }, []);

  const isAuthenticated = !!user;
  const userRole = user?.role || null;

  const value = {
    user,
    userRole,
    isAuthenticated,
    authChecked,
    setupRequired,
    refreshAuth,
    login,
    setup,
    acceptInvitation,
    logout,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}

/**
 * Convenience hook for components that want to know if the current user
 * is allowed to perform mutations. `read`-role users should not see write UI.
 */
export function useCanWrite() {
  const { userRole } = useAuth();
  return userRole === 'admin' || userRole === 'write';
}

export function useIsAdmin() {
  const { userRole } = useAuth();
  return userRole === 'admin';
}
