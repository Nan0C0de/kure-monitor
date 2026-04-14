import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Setup from '../Setup';

const mockSetup = jest.fn();

jest.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({
    setup: mockSetup,
    setupRequired: true,
    isAuthenticated: false,
    authChecked: true,
  }),
}));

const setupMock = mockSetup;

const renderSetup = () =>
  render(
    <MemoryRouter>
      <Setup />
    </MemoryRouter>
  );

describe('Setup', () => {
  beforeEach(() => {
    setupMock.mockReset();
  });

  test('validates password length', async () => {
    renderSetup();

    fireEvent.change(screen.getByLabelText(/^username$/i), { target: { value: 'alice' } });
    fireEvent.change(screen.getByLabelText(/^password$/i), { target: { value: 'short' } });
    fireEvent.change(screen.getByLabelText(/repeat password/i), { target: { value: 'short' } });
    fireEvent.click(screen.getByRole('button', { name: /create admin account/i }));

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/at least 8 characters/i);
    });
    expect(setupMock).not.toHaveBeenCalled();
  });

  test('validates password match', async () => {
    renderSetup();

    fireEvent.change(screen.getByLabelText(/^username$/i), { target: { value: 'alice' } });
    fireEvent.change(screen.getByLabelText(/^password$/i), { target: { value: 'password123' } });
    fireEvent.change(screen.getByLabelText(/repeat password/i), { target: { value: 'different123' } });
    fireEvent.click(screen.getByRole('button', { name: /create admin account/i }));

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/do not match/i);
    });
    expect(setupMock).not.toHaveBeenCalled();
  });

  test('submits when valid', async () => {
    setupMock.mockResolvedValueOnce({});
    renderSetup();

    fireEvent.change(screen.getByLabelText(/^username$/i), { target: { value: 'alice' } });
    fireEvent.change(screen.getByLabelText(/^password$/i), { target: { value: 'password123' } });
    fireEvent.change(screen.getByLabelText(/repeat password/i), { target: { value: 'password123' } });
    fireEvent.click(screen.getByRole('button', { name: /create admin account/i }));

    await waitFor(() =>
      expect(setupMock).toHaveBeenCalledWith({
        username: 'alice',
        password: 'password123',
        email: undefined,
      })
    );
  });

  test('shows 409 message when setup already completed', async () => {
    const err = Object.assign(new Error('Setup already completed'), { status: 409 });
    setupMock.mockRejectedValueOnce(err);
    renderSetup();

    fireEvent.change(screen.getByLabelText(/^username$/i), { target: { value: 'alice' } });
    fireEvent.change(screen.getByLabelText(/^password$/i), { target: { value: 'password123' } });
    fireEvent.change(screen.getByLabelText(/repeat password/i), { target: { value: 'password123' } });
    fireEvent.click(screen.getByRole('button', { name: /create admin account/i }));

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/already completed/i);
    });
  });
});
