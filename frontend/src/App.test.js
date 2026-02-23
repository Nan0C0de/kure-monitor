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

// Mock the Login component
jest.mock('./components/Login', () => {
  return function MockLogin() {
    return <div>Login Page</div>;
  };
});

// Mock the AuthContext to simulate auth-disabled (open access)
jest.mock('./contexts/AuthContext', () => {
  const React = require('react');
  return {
    AuthProvider: ({ children }) => children,
    useAuth: () => ({
      apiKey: null,
      isAuthenticated: true,
      authEnabled: false,
      authChecked: true,
      login: jest.fn(),
      logout: jest.fn(),
    }),
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
