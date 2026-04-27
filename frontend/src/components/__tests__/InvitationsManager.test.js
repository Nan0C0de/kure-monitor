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

    // Modal is open. Default is permanent (checkbox checked) → submit sends null.
    fireEvent.click(screen.getByRole('button', { name: /^create$/i }));

    await waitFor(() => {
      expect(createInvitationMock).toHaveBeenCalledWith({ role: 'read', expiresInHours: null });
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

  test('permanent invite checkbox is checked by default and the hours input is disabled', async () => {
    getInvitationsMock.mockResolvedValueOnce([]);
    render(<InvitationsManager isDark={false} onError={jest.fn()} onSuccess={jest.fn()} />);
    await screen.findByText(/no active invitations/i);

    fireEvent.click(screen.getByRole('button', { name: /create invitation/i }));

    const permanentCheckbox = screen.getByRole('checkbox', { name: /permanent invite/i });
    expect(permanentCheckbox).toBeChecked();

    // The number input (hours) should be disabled while permanent is checked.
    const hoursInput = screen.getByRole('spinbutton');
    expect(hoursInput).toBeDisabled();
  });

  test('unchecking permanent enables the hours input and submit sends the parsed hours', async () => {
    getInvitationsMock.mockResolvedValueOnce([]);
    createInvitationMock.mockResolvedValueOnce({
      id: 2,
      role: 'write',
      invite_url_path: '/invite/some-token',
    });
    getInvitationsMock.mockResolvedValueOnce([]);

    render(<InvitationsManager isDark={false} onError={jest.fn()} onSuccess={jest.fn()} />);
    await screen.findByText(/no active invitations/i);

    fireEvent.click(screen.getByRole('button', { name: /create invitation/i }));

    fireEvent.click(screen.getByRole('checkbox', { name: /permanent invite/i }));

    const hoursInput = screen.getByRole('spinbutton');
    expect(hoursInput).not.toBeDisabled();
    fireEvent.change(hoursInput, { target: { value: '168' } });

    // Role select is the only combobox in the modal.
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'write' } });

    fireEvent.click(screen.getByRole('button', { name: /^create$/i }));

    await waitFor(() => {
      expect(createInvitationMock).toHaveBeenCalledWith({ role: 'write', expiresInHours: 168 });
    });
  });

  test('renders "Never" in the expires column for invitations with no expiry', async () => {
    getInvitationsMock.mockResolvedValueOnce([
      {
        id: 99,
        role: 'read',
        created_at: '2026-01-01T00:00:00Z',
        expires_at: null,
        created_by: 'admin',
      },
    ]);
    render(<InvitationsManager isDark={false} onError={jest.fn()} onSuccess={jest.fn()} />);
    await screen.findByText('read');
    expect(screen.getByText('Never')).toBeInTheDocument();
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
