import React from 'react';
import { MemoryRouter } from 'react-router-dom';
import Dashboard from './components/Dashboard';

// A mock AuthContext provider if Dashboard uses useAuth()
import { AuthContext } from './contexts/AuthContext';

export default function DemoAppWrapper() {
  const mockAuth = {
    isAuthenticated: true,
    setupRequired: false,
    authChecked: true,
    user: { username: 'demo_user', role: 'admin' },
    checkAuth: async () => {},
    login: async () => {},
    logout: async () => {},
    setupAdmin: async () => {},
    acceptInvitation: async () => {}
  };

  return (
    <AuthContext.Provider value={mockAuth}>
      <MemoryRouter>
        <div className="App">
          <Dashboard />
        </div>
      </MemoryRouter>
    </AuthContext.Provider>
  );
}
