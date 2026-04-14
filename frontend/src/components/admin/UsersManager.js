import React, { useState, useEffect, useCallback } from 'react';
import { Users as UsersIcon, Trash2 } from 'lucide-react';
import { api } from '../../services/api';
import { useAuth } from '../../contexts/AuthContext';

const ROLES = ['admin', 'write', 'read'];

const UsersManager = ({ isDark, onError, onSuccess }) => {
  const { user: currentUser } = useAuth();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [pendingId, setPendingId] = useState(null);

  const fetchUsers = useCallback(async () => {
    try {
      const data = await api.getUsers();
      setUsers(data);
    } catch (err) {
      onError?.('Failed to load users');
    } finally {
      setLoading(false);
    }
  }, [onError]);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  const handleRoleChange = async (u, newRole) => {
    if (newRole === u.role) return;
    setPendingId(u.id);
    try {
      await api.updateUserRole(u.id, newRole);
      onSuccess?.(`Updated role for "${u.username}" to ${newRole}`);
      await fetchUsers();
    } catch (err) {
      onError?.(err?.message || 'Failed to update user role');
    } finally {
      setPendingId(null);
    }
  };

  const handleDelete = async (u) => {
    if (!window.confirm(`Delete user "${u.username}"? This cannot be undone.`)) return;
    setPendingId(u.id);
    try {
      await api.deleteUser(u.id);
      onSuccess?.(`User "${u.username}" deleted`);
      await fetchUsers();
    } catch (err) {
      onError?.(err?.message || 'Failed to delete user');
    } finally {
      setPendingId(null);
    }
  };

  const formatDate = (iso) => {
    if (!iso) return '—';
    try {
      return new Date(iso).toLocaleDateString();
    } catch {
      return iso;
    }
  };

  return (
    <div>
      <div className="flex items-center mb-4">
        <div className={`p-2 rounded-lg mr-3 ${isDark ? 'bg-purple-900/50' : 'bg-purple-100'}`}>
          <UsersIcon className={`w-5 h-5 ${isDark ? 'text-purple-400' : 'text-purple-600'}`} />
        </div>
        <div>
          <h3 className={`text-lg font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>Users</h3>
          <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
            Manage user accounts and their roles.
          </p>
        </div>
      </div>

      {loading ? (
        <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Loading...</p>
      ) : users.length === 0 ? (
        <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>No users found.</p>
      ) : (
        <div className={`rounded-lg border overflow-hidden ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
          <table className="w-full text-sm">
            <thead>
              <tr className={isDark ? 'bg-gray-800' : 'bg-gray-50'}>
                <th className={`text-left px-4 py-2 font-medium ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>Username</th>
                <th className={`text-left px-4 py-2 font-medium ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>Email</th>
                <th className={`text-left px-4 py-2 font-medium ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>Role</th>
                <th className={`text-left px-4 py-2 font-medium ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>Created</th>
                <th className={`text-right px-4 py-2 font-medium ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => {
                const isSelf = currentUser && u.id === currentUser.id;
                const busy = pendingId === u.id;
                return (
                  <tr
                    key={u.id}
                    className={`border-t ${isDark ? 'border-gray-700 hover:bg-gray-800/50' : 'border-gray-200 hover:bg-gray-50'}`}
                  >
                    <td className={`px-4 py-2 ${isDark ? 'text-white' : 'text-gray-900'}`}>
                      {u.username}
                      {isSelf && (
                        <span className={`ml-2 text-xs px-1.5 py-0.5 rounded ${
                          isDark ? 'bg-blue-900/50 text-blue-300' : 'bg-blue-100 text-blue-800'
                        }`}>
                          you
                        </span>
                      )}
                    </td>
                    <td className={`px-4 py-2 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                      {u.email || '—'}
                    </td>
                    <td className="px-4 py-2">
                      {isSelf ? (
                        <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                          u.role === 'admin'
                            ? isDark ? 'bg-amber-900/50 text-amber-300' : 'bg-amber-100 text-amber-800'
                            : isDark ? 'bg-blue-900/50 text-blue-300' : 'bg-blue-100 text-blue-800'
                        }`}>
                          {u.role}
                        </span>
                      ) : (
                        <select
                          value={u.role}
                          disabled={busy}
                          onChange={(e) => handleRoleChange(u, e.target.value)}
                          aria-label={`Role for ${u.username}`}
                          className={`px-2 py-1 text-sm rounded-md border focus:outline-none focus:ring-2 focus:ring-purple-500 ${
                            isDark
                              ? 'bg-gray-800 border-gray-600 text-white'
                              : 'bg-white border-gray-300 text-gray-900'
                          }`}
                        >
                          {ROLES.map((r) => (
                            <option key={r} value={r}>{r}</option>
                          ))}
                        </select>
                      )}
                    </td>
                    <td className={`px-4 py-2 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                      {formatDate(u.created_at)}
                    </td>
                    <td className="px-4 py-2 text-right">
                      {isSelf ? (
                        <span className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>—</span>
                      ) : (
                        <button
                          onClick={() => handleDelete(u)}
                          disabled={busy}
                          aria-label={`Delete ${u.username}`}
                          className={`p-1.5 rounded transition-colors ${
                            isDark
                              ? 'text-red-400 hover:bg-red-900/30 disabled:text-gray-600'
                              : 'text-red-600 hover:bg-red-50 disabled:text-gray-300'
                          }`}
                          title="Delete user"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default UsersManager;
