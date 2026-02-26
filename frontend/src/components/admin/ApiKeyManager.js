import React, { useState, useEffect, useCallback } from 'react';
import { Key, Plus, Trash2, Copy, CheckCircle, AlertCircle } from 'lucide-react';
import { api } from '../../services/api';

const ApiKeyManager = ({ isDark, onError, onSuccess }) => {
  const [keys, setKeys] = useState([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [newKeyName, setNewKeyName] = useState('');
  const [newKeyRole, setNewKeyRole] = useState('viewer');
  const [createdKey, setCreatedKey] = useState(null);
  const [copied, setCopied] = useState(false);

  const fetchKeys = useCallback(async () => {
    try {
      const data = await api.getApiKeys();
      setKeys(data);
    } catch (err) {
      onError?.('Failed to load API keys');
    } finally {
      setLoading(false);
    }
  }, [onError]);

  useEffect(() => {
    fetchKeys();
  }, [fetchKeys]);

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!newKeyName.trim()) return;

    setCreating(true);
    try {
      const result = await api.createApiKey(newKeyName.trim(), newKeyRole);
      setCreatedKey(result.key);
      setNewKeyName('');
      setNewKeyRole('viewer');
      onSuccess?.(`API key "${result.name}" created`);
      await fetchKeys();
    } catch (err) {
      onError?.('Failed to create API key');
    } finally {
      setCreating(false);
    }
  };

  const handleRevoke = async (keyId, keyName) => {
    if (!window.confirm(`Revoke API key "${keyName}"? This cannot be undone.`)) return;

    try {
      await api.revokeApiKey(keyId);
      onSuccess?.(`API key "${keyName}" revoked`);
      await fetchKeys();
    } catch (err) {
      onError?.('Failed to revoke API key');
    }
  };

  const handleCopy = async () => {
    if (!createdKey) return;
    try {
      await navigator.clipboard.writeText(createdKey);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback for non-HTTPS
      const textarea = document.createElement('textarea');
      textarea.value = createdKey;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div>
      <div className="flex items-center mb-4">
        <div className={`p-2 rounded-lg mr-3 ${isDark ? 'bg-purple-900/50' : 'bg-purple-100'}`}>
          <Key className={`w-5 h-5 ${isDark ? 'text-purple-400' : 'text-purple-600'}`} />
        </div>
        <div>
          <h3 className={`text-lg font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>API Keys</h3>
          <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
            Create and manage API keys for team members
          </p>
        </div>
      </div>

      {/* Created key banner */}
      {createdKey && (
        <div className={`mb-4 rounded-lg border p-4 ${isDark ? 'bg-green-900/20 border-green-800' : 'bg-green-50 border-green-200'}`}>
          <div className="flex items-start">
            <AlertCircle className={`w-5 h-5 mt-0.5 mr-2 flex-shrink-0 ${isDark ? 'text-green-400' : 'text-green-600'}`} />
            <div className="flex-1 min-w-0">
              <p className={`text-sm font-medium mb-1 ${isDark ? 'text-green-300' : 'text-green-800'}`}>
                Copy this key now — it won't be shown again
              </p>
              <div className="flex items-center gap-2">
                <code className={`text-xs px-2 py-1 rounded break-all ${isDark ? 'bg-green-900/50 text-green-200' : 'bg-green-100 text-green-900'}`}>
                  {createdKey}
                </code>
                <button
                  onClick={handleCopy}
                  className={`p-1.5 rounded flex-shrink-0 ${isDark ? 'hover:bg-green-800 text-green-400' : 'hover:bg-green-200 text-green-700'}`}
                  title="Copy to clipboard"
                >
                  {copied ? <CheckCircle className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                </button>
              </div>
            </div>
            <button
              onClick={() => setCreatedKey(null)}
              className={`ml-2 text-xs px-2 py-1 rounded flex-shrink-0 ${isDark ? 'text-green-400 hover:bg-green-800' : 'text-green-700 hover:bg-green-200'}`}
            >
              Dismiss
            </button>
          </div>
        </div>
      )}

      {/* Create form */}
      <form onSubmit={handleCreate} className="flex items-end gap-3 mb-6">
        <div className="flex-1">
          <label className={`block text-xs font-medium mb-1 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
            Name
          </label>
          <input
            type="text"
            value={newKeyName}
            onChange={(e) => setNewKeyName(e.target.value)}
            placeholder="e.g. alice-readonly"
            className={`w-full px-3 py-2 text-sm rounded-md border focus:outline-none focus:ring-2 focus:ring-purple-500 ${
              isDark
                ? 'bg-gray-800 border-gray-600 text-white placeholder-gray-500'
                : 'bg-white border-gray-300 text-gray-900 placeholder-gray-400'
            }`}
          />
        </div>
        <div>
          <label className={`block text-xs font-medium mb-1 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
            Role
          </label>
          <select
            value={newKeyRole}
            onChange={(e) => setNewKeyRole(e.target.value)}
            className={`px-3 py-2 text-sm rounded-md border focus:outline-none focus:ring-2 focus:ring-purple-500 ${
              isDark
                ? 'bg-gray-800 border-gray-600 text-white'
                : 'bg-white border-gray-300 text-gray-900'
            }`}
          >
            <option value="viewer">Viewer</option>
            <option value="admin">Admin</option>
          </select>
        </div>
        <button
          type="submit"
          disabled={creating || !newKeyName.trim()}
          className={`flex items-center px-4 py-2 text-sm font-medium rounded-md transition-colors ${
            isDark
              ? 'bg-purple-600 hover:bg-purple-500 text-white disabled:bg-gray-700 disabled:text-gray-500'
              : 'bg-purple-600 hover:bg-purple-700 text-white disabled:bg-gray-300 disabled:text-gray-500'
          }`}
        >
          <Plus className="w-4 h-4 mr-1" />
          {creating ? 'Creating...' : 'Create'}
        </button>
      </form>

      {/* Keys table */}
      {loading ? (
        <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Loading...</p>
      ) : keys.length === 0 ? (
        <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
          No API keys created yet. The bootstrap key (AUTH_API_KEY) is always available.
        </p>
      ) : (
        <div className={`rounded-lg border overflow-hidden ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
          <table className="w-full text-sm">
            <thead>
              <tr className={isDark ? 'bg-gray-800' : 'bg-gray-50'}>
                <th className={`text-left px-4 py-2 font-medium ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>Name</th>
                <th className={`text-left px-4 py-2 font-medium ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>Role</th>
                <th className={`text-left px-4 py-2 font-medium ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>Created</th>
                <th className={`text-right px-4 py-2 font-medium ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {keys.map((k) => (
                <tr
                  key={k.id}
                  className={`border-t ${isDark ? 'border-gray-700 hover:bg-gray-800/50' : 'border-gray-200 hover:bg-gray-50'}`}
                >
                  <td className={`px-4 py-2 ${isDark ? 'text-white' : 'text-gray-900'}`}>{k.name}</td>
                  <td className="px-4 py-2">
                    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                      k.role === 'admin'
                        ? isDark ? 'bg-amber-900/50 text-amber-300' : 'bg-amber-100 text-amber-800'
                        : isDark ? 'bg-blue-900/50 text-blue-300' : 'bg-blue-100 text-blue-800'
                    }`}>
                      {k.role}
                    </span>
                  </td>
                  <td className={`px-4 py-2 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                    {new Date(k.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-2 text-right">
                    <button
                      onClick={() => handleRevoke(k.id, k.name)}
                      className={`p-1.5 rounded transition-colors ${
                        isDark
                          ? 'text-red-400 hover:bg-red-900/30'
                          : 'text-red-600 hover:bg-red-50'
                      }`}
                      title="Revoke key"
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
    </div>
  );
};

export default ApiKeyManager;
