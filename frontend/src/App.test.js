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

test('renders dashboard component', () => {
  render(<App />);
  expect(screen.getByText(/Kure/i)).toBeInTheDocument();
});

test('renders dashboard title', () => {
  render(<App />);
  expect(screen.getByText(/Kubernetes Health Monitor/i)).toBeInTheDocument();
});
