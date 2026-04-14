import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import UsersManager from '../admin/UsersManager';

const mockGetUsers = jest.fn();
const mockUpdateUserRole = jest.fn();
const mockDeleteUser = jest.fn();

jest.mock('../../services/api', () => ({
  api: {
    getUsers: (...a) => mockGetUsers(...a),
    updateUserRole: (...a) => mockUpdateUserRole(...a),
    deleteUser: (...a) => mockDeleteUser(...a),
  },
}));

const getUsersMock = mockGetUsers;
const updateUserRoleMock = mockUpdateUserRole;
const deleteUserMock = mockDeleteUser;

jest.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 1, username: 'admin', role: 'admin' },
  }),
}));

const sampleUsers = [
  { id: 1, username: 'admin', role: 'admin', email: 'admin@example.com', created_at: '2025-01-01' },
  { id: 2, username: 'bob', role: 'read', email: null, created_at: '2025-02-01' },
];

describe('UsersManager', () => {
  beforeEach(() => {
    getUsersMock.mockReset();
    updateUserRoleMock.mockReset();
    deleteUserMock.mockReset();
  });

  test('shows "you" badge on self row and no role dropdown / delete for self', async () => {
    getUsersMock.mockResolvedValueOnce(sampleUsers);
    render(<UsersManager isDark={false} onError={jest.fn()} onSuccess={jest.fn()} />);

    await waitFor(() => {
      expect(screen.getByText(/^you$/i)).toBeInTheDocument();
    });

    // Other user has a role select
    expect(screen.getByLabelText('Role for bob')).toBeInTheDocument();

    // There should be exactly one role select (for bob, not admin)
    expect(screen.getAllByRole('combobox')).toHaveLength(1);
  });

  test('calls updateUserRole when selecting a new role', async () => {
    getUsersMock.mockResolvedValueOnce(sampleUsers);
    updateUserRoleMock.mockResolvedValueOnce({});
    // After update, refresh returns the same data
    getUsersMock.mockResolvedValueOnce(sampleUsers);

    const onSuccess = jest.fn();
    render(<UsersManager isDark={false} onError={jest.fn()} onSuccess={onSuccess} />);

    await screen.findByText('bob');

    const select = screen.getByLabelText('Role for bob');
    fireEvent.change(select, { target: { value: 'write' } });

    await waitFor(() => {
      expect(updateUserRoleMock).toHaveBeenCalledWith(2, 'write');
    });
  });

  test('displays server error when role change fails (e.g. last admin)', async () => {
    getUsersMock.mockResolvedValueOnce(sampleUsers);
    const err = Object.assign(new Error('Cannot demote the last admin'), { status: 400 });
    updateUserRoleMock.mockRejectedValueOnce(err);

    const onError = jest.fn();
    render(<UsersManager isDark={false} onError={onError} onSuccess={jest.fn()} />);

    await screen.findByText('bob');

    const select = screen.getByLabelText('Role for bob');
    fireEvent.change(select, { target: { value: 'write' } });

    await waitFor(() => {
      expect(onError).toHaveBeenCalledWith('Cannot demote the last admin');
    });
  });

  test('delete button asks for confirmation then calls deleteUser', async () => {
    getUsersMock.mockResolvedValueOnce(sampleUsers);
    deleteUserMock.mockResolvedValueOnce({});
    getUsersMock.mockResolvedValueOnce([sampleUsers[0]]);

    const confirmSpy = jest.spyOn(window, 'confirm').mockReturnValue(true);
    render(<UsersManager isDark={false} onError={jest.fn()} onSuccess={jest.fn()} />);

    await screen.findByText('bob');

    const deleteBtn = screen.getByLabelText('Delete bob');
    fireEvent.click(deleteBtn);

    expect(confirmSpy).toHaveBeenCalled();
    await waitFor(() => {
      expect(deleteUserMock).toHaveBeenCalledWith(2);
    });

    confirmSpy.mockRestore();
  });
});
