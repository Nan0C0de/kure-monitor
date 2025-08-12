import { render, screen, waitFor } from '@testing-library/react';
import App from './App';

// Mock the API
jest.mock('./services/api', () => ({
  api: {
    getFailedPods: jest.fn(() => Promise.resolve([])),
  }
}));

// Mock WebSocket hook  
jest.mock('./hooks/useWebSocket', () => ({
  useWebSocket: jest.fn(() => ({
    connected: true,
    error: null
  })),
}));

test('renders dashboard component', async () => {
  render(<App />);
  
  await waitFor(() => {
    expect(screen.getByText(/Kure/i)).toBeInTheDocument();
  });
});

test('renders dashboard title', async () => {
  render(<App />);
  
  await waitFor(() => {
    expect(screen.getByText(/Kubernetes Health Monitor/i)).toBeInTheDocument();
  });
});
