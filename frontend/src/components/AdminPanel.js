import React, { useState, useEffect } from 'react';
import { Plus, Trash2, AlertCircle, CheckCircle, ChevronDown } from 'lucide-react';
import { api } from '../services/api';

const AdminPanel = () => {
  const [excludedNamespaces, setExcludedNamespaces] = useState([]);
  const [availableNamespaces, setAvailableNamespaces] = useState([]);
  const [newNamespace, setNewNamespace] = useState('');
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [successMessage, setSuccessMessage] = useState(null);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      const [excluded, available] = await Promise.all([
        api.getExcludedNamespaces(),
        api.getAllNamespaces()
      ]);
      setExcludedNamespaces(excluded);
      setAvailableNamespaces(available);
      setError(null);
    } catch (err) {
      setError('Failed to load data');
      console.error('Error loading data:', err);
    } finally {
      setLoading(false);
    }
  };

  // Filter suggestions: available namespaces that are not already excluded
  const suggestions = availableNamespaces.filter(
    ns => !excludedNamespaces.some(excluded => excluded.namespace === ns)
  );

  // Filter suggestions based on input
  const filteredSuggestions = newNamespace.trim()
    ? suggestions.filter(ns => ns.toLowerCase().includes(newNamespace.toLowerCase()))
    : suggestions;

  const handleAddNamespace = async (namespaceToAdd) => {
    const namespace = (namespaceToAdd || newNamespace).trim();

    if (!namespace) {
      setError('Please enter a namespace name');
      return;
    }

    // Check if already excluded
    if (excludedNamespaces.some(ns => ns.namespace === namespace)) {
      setError('This namespace is already excluded');
      return;
    }

    try {
      const result = await api.addExcludedNamespace(namespace);
      setExcludedNamespaces(prev => [...prev, result]);
      setNewNamespace('');
      setShowSuggestions(false);
      setError(null);
      setSuccessMessage(`Namespace "${namespace}" excluded. All findings removed.`);
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (err) {
      setError('Failed to add namespace');
      console.error('Error adding namespace:', err);
    }
  };

  const handleRemoveNamespace = async (namespace) => {
    try {
      await api.removeExcludedNamespace(namespace);
      setExcludedNamespaces(prev => prev.filter(ns => ns.namespace !== namespace));
      setError(null);
      setSuccessMessage(`Namespace "${namespace}" will now be scanned again`);
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (err) {
      setError('Failed to remove namespace');
      console.error('Error removing namespace:', err);
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    handleAddNamespace();
  };

  if (loading) {
    return (
      <div className="p-6">
        <div className="flex items-center justify-center py-8">
          <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
          <span className="ml-2">Loading...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6">
      <div className="mb-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-2">Namespace Exclusions</h2>
        <p className="text-sm text-gray-600">
          Namespaces added here will be excluded from pod monitoring and security scanning.
          System namespaces (kube-system, kube-public, etc.) are always excluded by default.
        </p>
      </div>

      {error && (
        <div className="mb-4 bg-red-50 border border-red-200 rounded-md p-3">
          <div className="flex items-center">
            <AlertCircle className="w-4 h-4 text-red-500 mr-2" />
            <span className="text-sm text-red-800">{error}</span>
          </div>
        </div>
      )}

      {successMessage && (
        <div className="mb-4 bg-green-50 border border-green-200 rounded-md p-3">
          <div className="flex items-center">
            <CheckCircle className="w-4 h-4 text-green-500 mr-2" />
            <span className="text-sm text-green-800">{successMessage}</span>
          </div>
        </div>
      )}

      {/* Add namespace form with suggestions */}
      <form onSubmit={handleSubmit} className="mb-6">
        <div className="flex gap-2">
          <div className="relative flex-1">
            <input
              type="text"
              value={newNamespace}
              onChange={(e) => {
                setNewNamespace(e.target.value);
                setShowSuggestions(true);
              }}
              onFocus={() => setShowSuggestions(true)}
              onBlur={() => setTimeout(() => setShowSuggestions(false), 200)}
              placeholder="Enter or select namespace"
              className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
            {showSuggestions && filteredSuggestions.length > 0 && (
              <div className="absolute z-10 w-full mt-1 bg-white border border-gray-200 rounded-md shadow-lg max-h-48 overflow-y-auto">
                <div className="px-3 py-2 text-xs text-gray-500 border-b border-gray-100">
                  Available namespaces with findings
                </div>
                {filteredSuggestions.map(ns => (
                  <button
                    key={ns}
                    type="button"
                    onClick={() => handleAddNamespace(ns)}
                    className="w-full px-3 py-2 text-left text-sm hover:bg-blue-50 hover:text-blue-700 focus:outline-none focus:bg-blue-50"
                  >
                    {ns}
                  </button>
                ))}
              </div>
            )}
          </div>
          <button
            type="submit"
            className="inline-flex items-center px-4 py-2 text-sm font-medium text-white bg-blue-600 border border-transparent rounded-md shadow-sm hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
          >
            <Plus className="w-4 h-4 mr-1" />
            Exclude
          </button>
        </div>
        {suggestions.length > 0 && !showSuggestions && (
          <p className="mt-1 text-xs text-gray-500">
            Click the input to see {suggestions.length} available namespace{suggestions.length !== 1 ? 's' : ''}
          </p>
        )}
      </form>

      {/* Excluded namespaces list */}
      <div className="border border-gray-200 rounded-md">
        <div className="bg-gray-50 px-4 py-3 border-b border-gray-200">
          <h3 className="text-sm font-medium text-gray-700">
            Excluded Namespaces ({excludedNamespaces.length})
          </h3>
        </div>

        {excludedNamespaces.length === 0 ? (
          <div className="px-4 py-8 text-center text-gray-500">
            <p className="text-sm">No namespaces excluded yet.</p>
            <p className="text-xs mt-1">Add namespaces above to exclude them from scanning.</p>
          </div>
        ) : (
          <ul className="divide-y divide-gray-200">
            {excludedNamespaces.map((ns) => (
              <li key={ns.namespace} className="px-4 py-3 flex items-center justify-between hover:bg-gray-50">
                <div>
                  <span className="text-sm font-medium text-gray-900">{ns.namespace}</span>
                  {ns.created_at && (
                    <span className="ml-2 text-xs text-gray-500">
                      Added {new Date(ns.created_at).toLocaleDateString()}
                    </span>
                  )}
                </div>
                <button
                  onClick={() => handleRemoveNamespace(ns.namespace)}
                  className="inline-flex items-center px-2 py-1 text-xs font-medium text-red-700 bg-red-50 border border-red-200 rounded hover:bg-red-100 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500"
                >
                  <Trash2 className="w-3 h-3 mr-1" />
                  Include
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
};

export default AdminPanel;
