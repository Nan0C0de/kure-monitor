import React from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import Dashboard from './components/Dashboard';
import Login from './components/Login';
import Setup from './components/Setup';
import InviteAccept from './components/InviteAccept';

const LoadingScreen = ({ message }) => (
  <div className="min-h-screen flex items-center justify-center bg-gray-100 dark:bg-gray-900">
    <div className="flex items-center space-x-2">
      <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
      <span className="text-gray-700 dark:text-gray-300">{message || 'Loading...'}</span>
    </div>
  </div>
);

/**
 * AuthGate handles top-level routing decisions:
 *  - If first-run setup is required, route all traffic to /setup.
 *  - If not authenticated, route all traffic (other than public pages) to /login.
 *  - Otherwise render children.
 */
function AuthGate({ children }) {
  const { authChecked, setupRequired, isAuthenticated } = useAuth();
  const location = useLocation();

  if (!authChecked) {
    return <LoadingScreen message="Checking authentication..." />;
  }

  const path = location.pathname;
  const isLogin = path === '/login';
  const isSetup = path === '/setup';
  const isInvite = path.startsWith('/invite/');

  if (setupRequired && !isSetup && !isInvite) {
    return <Navigate to="/setup" replace />;
  }

  if (!setupRequired && isSetup) {
    return <Navigate to={isAuthenticated ? '/' : '/login'} replace />;
  }

  if (!isAuthenticated && !isLogin && !isSetup && !isInvite) {
    return <Navigate to="/login" replace />;
  }

  return children;
}

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <div className="App">
          <AuthGate>
            <Routes>
              <Route path="/login" element={<Login />} />
              <Route path="/setup" element={<Setup />} />
              <Route path="/invite/:token" element={<InviteAccept />} />
              <Route path="/*" element={<Dashboard />} />
            </Routes>
          </AuthGate>
        </div>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
