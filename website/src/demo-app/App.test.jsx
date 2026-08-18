import { render, screen } from '@testing-library/react';
import App from './App';

// Mock the Dashboard component to avoid complex dependency issues
jest.mock('./components/Dashboard', () => {
  return function MockDashboard() {
    return (
      <div>
        <h1>Kure</h1>
        <p>Kubernetes Health Monitor</p>
      </div>
    );
  };
});

jest.mock('./components/Login', () => {
  return function MockLogin() {
    return <div>Login Page</div>;
  };
});

jest.mock('./components/Setup', () => {
  return function MockSetup() {
    return <div>Setup Page</div>;
  };
});

jest.mock('./components/InviteAccept', () => {
  return function MockInvite() {
    return <div>Invite Page</div>;
  };
});

// Mock the AuthContext to simulate an authenticated admin user
jest.mock('./contexts/AuthContext', () => {
  return {
    AuthProvider: ({ children }) => children,
    useAuth: () => ({
      user: { id: 1, username: 'admin', role: 'admin' },
      userRole: 'admin',
      isAuthenticated: true,
      authChecked: true,
      setupRequired: false,
      login: jest.fn(),
      logout: jest.fn(),
      setup: jest.fn(),
      acceptInvitation: jest.fn(),
      refreshAuth: jest.fn(),
    }),
    useCanWrite: () => true,
    useIsAdmin: () => true,
  };
});

test('renders dashboard component', () => {
  render(<App />);
  expect(screen.getByText(/Kure/i)).toBeInTheDocument();
});

test('renders dashboard title', () => {
  render(<App />);
  expect(screen.getByText(/Kubernetes Health Monitor/i)).toBeInTheDocument();
});
