import React, { useState, useEffect, useCallback } from 'react';
import { Mail, Plus, Trash2, Copy, CheckCircle, X, AlertCircle } from 'lucide-react';
import { api } from '../../services/api';

const ROLES = ['write', 'read'];
const DEFAULT_EXPIRES_HOURS = 72;

const buildInviteUrl = (inviteUrlPath) => {
  if (!inviteUrlPath) return '';
  if (inviteUrlPath.startsWith('http')) return inviteUrlPath;
  return `${window.location.origin}${inviteUrlPath.startsWith('/') ? '' : '/'}${inviteUrlPath}`;
};

const InvitationsManager = ({ isDark, onError, onSuccess }) => {
  const [invitations, setInvitations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newRole, setNewRole] = useState('read');
  const [newExpires, setNewExpires] = useState(DEFAULT_EXPIRES_HOURS);
  const [permanent, setPermanent] = useState(true);
  const [createdInvite, setCreatedInvite] = useState(null);
  const [copied, setCopied] = useState(false);

  const fetchInvitations = useCallback(async () => {
    try {
      const data = await api.getInvitations();
      setInvitations(data);
    } catch (err) {
      onError?.('Failed to load invitations');
    } finally {
      setLoading(false);
    }
  }, [onError]);

  useEffect(() => {
    fetchInvitations();
  }, [fetchInvitations]);

  const openModal = () => {
    setNewRole('read');
    setNewExpires(DEFAULT_EXPIRES_HOURS);
    setPermanent(true);
    setCreatedInvite(null);
    setCopied(false);
    setShowModal(true);
  };

  const closeModal = () => {
    setShowModal(false);
    setCreatedInvite(null);
    setCopied(false);
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    setCreating(true);
    try {
      const expiresInHours = permanent
        ? null
        : Math.max(parseInt(newExpires, 10) || DEFAULT_EXPIRES_HOURS, 1);
      const result = await api.createInvitation({ role: newRole, expiresInHours });
      setCreatedInvite(result);
      onSuccess?.('Invitation created');
      await fetchInvitations();
    } catch (err) {
      onError?.(err?.message || 'Failed to create invitation');
    } finally {
      setCreating(false);
    }
  };

  const handleRevoke = async (invite) => {
    if (!window.confirm('Revoke this invitation? The link will no longer be usable.')) return;
    try {
      await api.revokeInvitation(invite.id);
      onSuccess?.('Invitation revoked');
      await fetchInvitations();
    } catch (err) {
      onError?.(err?.message || 'Failed to revoke invitation');
    }
  };

  const handleCopy = async () => {
    const url = buildInviteUrl(createdInvite?.invite_url_path);
    if (!url) return;
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      const textarea = document.createElement('textarea');
      textarea.value = url;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const formatDate = (iso) => {
    if (!iso) return '—';
    try {
      return new Date(iso).toLocaleString();
    } catch {
      return iso;
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center">
          <div className={`p-2 rounded-lg mr-3 ${isDark ? 'bg-purple-900/50' : 'bg-purple-100'}`}>
            <Mail className={`w-5 h-5 ${isDark ? 'text-purple-400' : 'text-purple-600'}`} />
          </div>
          <div>
            <h3 className={`text-lg font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>Invitations</h3>
            <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
              Create invitation links and share them with new team members.
            </p>
          </div>
        </div>
        <button
          onClick={openModal}
          className={`flex items-center px-3 py-2 text-sm font-medium rounded-md ${
            isDark
              ? 'bg-purple-600 hover:bg-purple-500 text-white'
              : 'bg-purple-600 hover:bg-purple-700 text-white'
          }`}
        >
          <Plus className="w-4 h-4 mr-1" />
          Create invitation
        </button>
      </div>

      {loading ? (
        <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Loading...</p>
      ) : invitations.length === 0 ? (
        <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
          No active invitations.
        </p>
      ) : (
        <div className={`rounded-lg border overflow-hidden ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
          <table className="w-full text-sm">
            <thead>
              <tr className={isDark ? 'bg-gray-800' : 'bg-gray-50'}>
                <th className={`text-left px-4 py-2 font-medium ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>Role</th>
                <th className={`text-left px-4 py-2 font-medium ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>Created</th>
                <th className={`text-left px-4 py-2 font-medium ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>Expires</th>
                <th className={`text-left px-4 py-2 font-medium ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>Created by</th>
                <th className={`text-right px-4 py-2 font-medium ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {invitations.map((inv) => (
                <tr
                  key={inv.id}
                  className={`border-t ${isDark ? 'border-gray-700 hover:bg-gray-800/50' : 'border-gray-200 hover:bg-gray-50'}`}
                >
                  <td className="px-4 py-2">
                    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                      isDark ? 'bg-blue-900/50 text-blue-300' : 'bg-blue-100 text-blue-800'
                    }`}>
                      {inv.role}
                    </span>
                  </td>
                  <td className={`px-4 py-2 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                    {formatDate(inv.created_at)}
                  </td>
                  <td className={`px-4 py-2 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                    {inv.expires_at ? formatDate(inv.expires_at) : 'Never'}
                  </td>
                  <td className={`px-4 py-2 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                    {inv.created_by || inv.created_by_username || '—'}
                  </td>
                  <td className="px-4 py-2 text-right">
                    <button
                      onClick={() => handleRevoke(inv)}
                      aria-label="Revoke invitation"
                      className={`p-1.5 rounded transition-colors ${
                        isDark
                          ? 'text-red-400 hover:bg-red-900/30'
                          : 'text-red-600 hover:bg-red-50'
                      }`}
                      title="Revoke invitation"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" role="dialog" aria-modal="true">
          <div className={`w-full max-w-md rounded-lg shadow-xl ${isDark ? 'bg-gray-800' : 'bg-white'}`}>
            <div className={`flex items-center justify-between px-5 py-3 border-b ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
              <h3 className={`text-base font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>
                {createdInvite ? 'Share this invitation link' : 'Create invitation'}
              </h3>
              <button
                onClick={closeModal}
                aria-label="Close"
                className={`p-1 rounded ${isDark ? 'hover:bg-gray-700 text-gray-300' : 'hover:bg-gray-100 text-gray-500'}`}
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-5">
              {!createdInvite ? (
                <form onSubmit={handleCreate} className="space-y-4">
                  <div>
                    <label className={`block text-xs font-medium mb-1 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                      Role
                    </label>
                    <select
                      value={newRole}
                      onChange={(e) => setNewRole(e.target.value)}
                      className={`w-full px-3 py-2 text-sm rounded-md border focus:outline-none focus:ring-2 focus:ring-purple-500 ${
                        isDark
                          ? 'bg-gray-900 border-gray-600 text-white'
                          : 'bg-white border-gray-300 text-gray-900'
                      }`}
                    >
                      {ROLES.map((r) => (
                        <option key={r} value={r}>{r}</option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className={`flex items-center gap-2 text-xs font-medium ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                      <input
                        type="checkbox"
                        checked={permanent}
                        onChange={(e) => setPermanent(e.target.checked)}
                        className="rounded border-gray-300 text-purple-600 focus:ring-purple-500"
                      />
                      Permanent invite (never expires)
                    </label>
                    <p className={`mt-1 text-xs ${isDark ? 'text-gray-500' : 'text-gray-500'}`}>
                      Permanent invitations remain revocable from this list.
                    </p>
                  </div>

                  <div>
                    <label className={`block text-xs font-medium mb-1 ${isDark ? 'text-gray-400' : 'text-gray-600'} ${permanent ? 'opacity-50' : ''}`}>
                      Expires in (hours)
                    </label>
                    <input
                      type="number"
                      min={1}
                      value={newExpires}
                      onChange={(e) => setNewExpires(e.target.value)}
                      disabled={permanent}
                      className={`w-full px-3 py-2 text-sm rounded-md border focus:outline-none focus:ring-2 focus:ring-purple-500 disabled:opacity-50 disabled:cursor-not-allowed ${
                        isDark
                          ? 'bg-gray-900 border-gray-600 text-white'
                          : 'bg-white border-gray-300 text-gray-900'
                      }`}
                    />
                    <p className={`mt-1 text-xs ${isDark ? 'text-gray-500' : 'text-gray-500'} ${permanent ? 'opacity-50' : ''}`}>
                      Default {DEFAULT_EXPIRES_HOURS} hours. Used only when "Permanent invite" is unchecked.
                    </p>
                  </div>

                  <div className={`text-xs rounded-md px-3 py-2 flex items-start gap-2 ${
                    isDark ? 'bg-amber-900/20 text-amber-200' : 'bg-amber-50 text-amber-800'
                  }`}>
                    <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                    <span>
                      No email will be sent. After creating the invitation, copy the link and share it with the invitee.
                    </span>
                  </div>

                  <div className="flex justify-end gap-2 pt-2">
                    <button
                      type="button"
                      onClick={closeModal}
                      className={`px-4 py-2 text-sm rounded-md border ${
                        isDark
                          ? 'border-gray-600 text-gray-300 hover:bg-gray-700'
                          : 'border-gray-300 text-gray-700 hover:bg-gray-50'
                      }`}
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={creating}
                      className={`px-4 py-2 text-sm font-medium rounded-md ${
                        creating
                          ? 'bg-purple-400 text-white cursor-not-allowed'
                          : isDark
                            ? 'bg-purple-600 hover:bg-purple-500 text-white'
                            : 'bg-purple-600 hover:bg-purple-700 text-white'
                      }`}
                    >
                      {creating ? 'Creating...' : 'Create'}
                    </button>
                  </div>
                </form>
              ) : (
                <div className="space-y-4">
                  <p className={`text-sm ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                    Copy this invitation link and share it with the invitee. No email has been sent.
                  </p>
                  <div className={`flex items-center gap-2 rounded-md border px-3 py-2 ${
                    isDark ? 'bg-gray-900 border-gray-700' : 'bg-gray-50 border-gray-200'
                  }`}>
                    <code className={`flex-1 text-xs break-all ${isDark ? 'text-gray-200' : 'text-gray-800'}`}>
                      {buildInviteUrl(createdInvite.invite_url_path)}
                    </code>
                    <button
                      onClick={handleCopy}
                      className={`p-1.5 rounded flex-shrink-0 ${
                        isDark ? 'hover:bg-gray-700 text-gray-300' : 'hover:bg-gray-200 text-gray-700'
                      }`}
                      aria-label="Copy invitation link"
                      title="Copy to clipboard"
                    >
                      {copied ? <CheckCircle className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                    </button>
                  </div>
                  {copied && (
                    <p className={`text-xs ${isDark ? 'text-green-400' : 'text-green-600'}`}>Copied!</p>
                  )}
                  <div className="flex justify-end pt-2">
                    <button
                      onClick={closeModal}
                      className={`px-4 py-2 text-sm font-medium rounded-md ${
                        isDark
                          ? 'bg-purple-600 hover:bg-purple-500 text-white'
                          : 'bg-purple-600 hover:bg-purple-700 text-white'
                      }`}
                    >
                      Done
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default InvitationsManager;
