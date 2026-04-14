import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import InviteAccept from '../InviteAccept';

const mockAcceptInvitation = jest.fn();
const mockGetInvitation = jest.fn();

jest.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({
    acceptInvitation: mockAcceptInvitation,
  }),
}));

jest.mock('../../services/api', () => ({
  api: {
    getInvitation: (...args) => mockGetInvitation(...args),
  },
}));

const acceptInvitationMock = mockAcceptInvitation;
const getInvitationMock = mockGetInvitation;

const renderInvite = (token = 'abc123') =>
  render(
    <MemoryRouter initialEntries={[`/invite/${token}`]}>
      <Routes>
        <Route path="/invite/:token" element={<InviteAccept />} />
      </Routes>
    </MemoryRouter>
  );

describe('InviteAccept', () => {
  beforeEach(() => {
    acceptInvitationMock.mockReset();
    getInvitationMock.mockReset();
  });

  test('shows registration form on 200', async () => {
    getInvitationMock.mockResolvedValueOnce({ role: 'write', expires_at: '2099-01-01T00:00:00Z' });
    renderInvite();

    await waitFor(() => {
      expect(screen.getByText(/You have been invited as a/i)).toBeInTheDocument();
    });
    expect(screen.getByLabelText(/^role$/i)).toHaveValue('write');
    expect(screen.getByLabelText(/^username$/i)).toBeInTheDocument();
  });

  test('shows "not found" on 404', async () => {
    const err = Object.assign(new Error('nf'), { status: 404 });
    getInvitationMock.mockRejectedValueOnce(err);
    renderInvite();

    await waitFor(() => {
      expect(screen.getByText(/invitation not found/i)).toBeInTheDocument();
    });
  });

  test('shows "unavailable" on 410', async () => {
    const err = Object.assign(new Error('gone'), { status: 410 });
    getInvitationMock.mockRejectedValueOnce(err);
    renderInvite();

    await waitFor(() => {
      expect(screen.getByText(/invitation unavailable/i)).toBeInTheDocument();
    });
  });
});
