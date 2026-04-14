import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import InvitationsManager from '../admin/InvitationsManager';

const mockGetInvitations = jest.fn();
const mockCreateInvitation = jest.fn();
const mockRevokeInvitation = jest.fn();

jest.mock('../../services/api', () => ({
  api: {
    getInvitations: (...a) => mockGetInvitations(...a),
    createInvitation: (...a) => mockCreateInvitation(...a),
    revokeInvitation: (...a) => mockRevokeInvitation(...a),
  },
}));

const getInvitationsMock = mockGetInvitations;
const createInvitationMock = mockCreateInvitation;
const revokeInvitationMock = mockRevokeInvitation;

describe('InvitationsManager', () => {
  beforeEach(() => {
    getInvitationsMock.mockReset();
    createInvitationMock.mockReset();
    revokeInvitationMock.mockReset();
  });

  test('renders empty state when there are no invitations', async () => {
    getInvitationsMock.mockResolvedValueOnce([]);
    render(<InvitationsManager isDark={false} onError={jest.fn()} onSuccess={jest.fn()} />);
    await waitFor(() => {
      expect(screen.getByText(/no active invitations/i)).toBeInTheDocument();
    });
  });

  test('opens create modal, creates invitation, and shows the invite URL with copy button', async () => {
    getInvitationsMock.mockResolvedValueOnce([]);
    createInvitationMock.mockResolvedValueOnce({
      id: 1,
      role: 'read',
      invite_url_path: '/invite/some-token-xyz',
    });
    // After create, refresh list
    getInvitationsMock.mockResolvedValueOnce([
      {
        id: 1,
        role: 'read',
        created_at: '2025-01-01T00:00:00Z',
        expires_at: '2025-01-04T00:00:00Z',
        created_by: 'admin',
      },
    ]);

    render(<InvitationsManager isDark={false} onError={jest.fn()} onSuccess={jest.fn()} />);
    await screen.findByText(/no active invitations/i);

    fireEvent.click(screen.getByRole('button', { name: /create invitation/i }));

    // Modal is open — submit the form with defaults.
    fireEvent.click(screen.getByRole('button', { name: /^create$/i }));

    await waitFor(() => {
      expect(createInvitationMock).toHaveBeenCalledWith({ role: 'read', expiresInHours: 72 });
    });

    // Success view with the URL.
    await waitFor(() => {
      expect(screen.getByText(/share this invitation link/i)).toBeInTheDocument();
    });
    const code = screen.getByText(/\/invite\/some-token-xyz/);
    expect(code).toBeInTheDocument();
    // URL should include the origin
    expect(code.textContent).toContain(window.location.origin);

    expect(screen.getByLabelText(/copy invitation link/i)).toBeInTheDocument();
  });

  test('revoke button calls revokeInvitation after confirm', async () => {
    getInvitationsMock.mockResolvedValueOnce([
      {
        id: 42,
        role: 'write',
        created_at: '2025-01-01T00:00:00Z',
        expires_at: '2025-01-04T00:00:00Z',
        created_by: 'admin',
      },
    ]);
    revokeInvitationMock.mockResolvedValueOnce({});
    getInvitationsMock.mockResolvedValueOnce([]);

    const confirmSpy = jest.spyOn(window, 'confirm').mockReturnValue(true);
    render(<InvitationsManager isDark={false} onError={jest.fn()} onSuccess={jest.fn()} />);

    await screen.findByText('write');

    fireEvent.click(screen.getByLabelText(/revoke invitation/i));

    await waitFor(() => {
      expect(revokeInvitationMock).toHaveBeenCalledWith(42);
    });

    confirmSpy.mockRestore();
  });
});
