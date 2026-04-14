import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

// We mock the AuthContext to control AuthGate's routing decisions.
let mockAuthState = {
  authChecked: false,
  setupRequired: false,
  isAuthenticated: false,
};

jest.mock('../../contexts/AuthContext', () => ({
  AuthProvider: ({ children }) => children,
  useAuth: () => mockAuthState,
}));

// Replace the real page components with trivial markers so we can assert routing.
jest.mock('../../components/Dashboard', () => () => <div>DashboardPage</div>);
jest.mock('../../components/Login', () => () => <div>LoginPage</div>);
jest.mock('../../components/Setup', () => () => <div>SetupPage</div>);
jest.mock('../../components/InviteAccept', () => () => <div>InvitePage</div>);

// Re-import App *after* mocks are set up.
// Using require here because jest's module hoisting already processed the mocks.
const App = require('../../App').default;

const renderAt = (path) => {
  // Intercept BrowserRouter in App by wrapping with MemoryRouter through manipulating window.history
  window.history.pushState({}, '', path);
  return render(<App />);
};

describe('AuthGate', () => {
  afterEach(() => {
    jest.clearAllMocks();
  });

  test('shows loading screen while authChecked is false', () => {
    mockAuthState = { authChecked: false, setupRequired: false, isAuthenticated: false };
    renderAt('/');
    expect(screen.getByText(/Checking authentication/i)).toBeInTheDocument();
  });

  test('redirects to /setup when setup is required', async () => {
    mockAuthState = { authChecked: true, setupRequired: true, isAuthenticated: false };
    renderAt('/');

    await waitFor(() => {
      expect(screen.getByText('SetupPage')).toBeInTheDocument();
    });
  });

  test('redirects to /login when unauthenticated', async () => {
    mockAuthState = { authChecked: true, setupRequired: false, isAuthenticated: false };
    renderAt('/');

    await waitFor(() => {
      expect(screen.getByText('LoginPage')).toBeInTheDocument();
    });
  });

  test('renders Dashboard when authenticated', async () => {
    mockAuthState = { authChecked: true, setupRequired: false, isAuthenticated: true };
    renderAt('/');

    await waitFor(() => {
      expect(screen.getByText('DashboardPage')).toBeInTheDocument();
    });
  });

  test('allows /invite/:token even when unauthenticated and setup required', async () => {
    mockAuthState = { authChecked: true, setupRequired: true, isAuthenticated: false };
    renderAt('/invite/abc');

    await waitFor(() => {
      expect(screen.getByText('InvitePage')).toBeInTheDocument();
    });
  });
});
