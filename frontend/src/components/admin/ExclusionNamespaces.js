import React, { useState, useEffect } from 'react';
import { Plus, Trash2, Shield } from 'lucide-react';
import { api } from '../../services/api';

const ExclusionNamespaces = ({ isDark, onError, onSuccess }) => {
  const [excludedNamespaces, setExcludedNamespaces] = useState([]);
  const [availableNamespaces, setAvailableNamespaces] = useState([]);
  const [newNamespace, setNewNamespace] = useState('');
  const [showNamespaceSuggestions, setShowNamespaceSuggestions] = useState(false);

  useEffect(() => {
    const loadData = async () => {
      try {
        const [excluded, available] = await Promise.all([
          api.getExcludedNamespaces(),
          api.getAllNamespaces()
        ]);
        setExcludedNamespaces(excluded);
        setAvailableNamespaces(available);
      } catch (err) {
        onError('Failed to load namespace data');
        console.error('Error loading namespace data:', err);
      }
    };
    loadData();
  }, [onError]);

  // Namespace suggestions: available namespaces that are not already excluded
  const namespaceSuggestions = availableNamespaces.filter(
    ns => !excludedNamespaces.some(excluded => excluded.namespace === ns)
  );

  const filteredNamespaceSuggestions = newNamespace.trim()
    ? namespaceSuggestions.filter(ns => ns.toLowerCase().includes(newNamespace.toLowerCase()))
    : namespaceSuggestions;

  const handleAddNamespace = async (namespaceToAdd) => {
    const namespace = (namespaceToAdd || newNamespace).trim();

    if (!namespace) {
      onError('Please enter a namespace name');
      return;
    }

    if (excludedNamespaces.some(ns => ns.namespace === namespace)) {
      onError('This namespace is already excluded');
      return;
    }

    try {
      const result = await api.addExcludedNamespace(namespace);
      setExcludedNamespaces(prev => [...prev, result]);
      setNewNamespace('');
      setShowNamespaceSuggestions(false);
      onSuccess(`Namespace "${namespace}" excluded from security scan.`);
    } catch (err) {
      onError('Failed to add namespace');
      console.error('Error adding namespace:', err);
    }
  };

  const handleRemoveNamespace = async (namespace) => {
    try {
      await api.removeExcludedNamespace(namespace);
      setExcludedNamespaces(prev => prev.filter(ns => ns.namespace !== namespace));
      onSuccess(`Namespace "${namespace}" will now be scanned again`);
    } catch (err) {
      onError('Failed to remove namespace');
      console.error('Error removing namespace:', err);
    }
  };

  const handleNamespaceSubmit = (e) => {
    e.preventDefault();
    handleAddNamespace();
  };

  return (
    <div>
      <div className="mb-4 flex items-center">
        <Shield className="w-5 h-5 text-orange-500 mr-2" />
        <h2 className={`text-lg font-semibold ${isDark ? 'text-gray-100' : 'text-gray-900'}`}>Namespaces (Security Scan)</h2>
      </div>
      <p className={`text-sm mb-4 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
        Exclude namespaces from security scanning. System namespaces are always excluded by default.
      </p>

      <form onSubmit={handleNamespaceSubmit} className="mb-4">
        <div className="flex gap-2">
          <div className="relative flex-1">
            <input
              type="text"
              value={newNamespace}
              onChange={(e) => {
                setNewNamespace(e.target.value);
                setShowNamespaceSuggestions(true);
              }}
              onFocus={() => setShowNamespaceSuggestions(true)}
              onBlur={() => setTimeout(() => setShowNamespaceSuggestions(false), 200)}
              placeholder="Enter or select namespace"
              className={`w-full px-3 py-2 text-sm border rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 ${isDark ? 'bg-gray-700 border-gray-600 text-gray-200 placeholder-gray-400' : 'bg-white border-gray-300 text-gray-900'}`}
            />
            {showNamespaceSuggestions && filteredNamespaceSuggestions.length > 0 && (
              <div className={`absolute z-10 w-full mt-1 border rounded-md shadow-lg max-h-48 overflow-y-auto ${isDark ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'}`}>
                <div className={`px-3 py-2 text-xs border-b ${isDark ? 'text-gray-400 border-gray-700' : 'text-gray-500 border-gray-100'}`}>
                  Available namespaces
                </div>
                {filteredNamespaceSuggestions.map(ns => (
                  <button
                    key={ns}
                    type="button"
                    onClick={() => handleAddNamespace(ns)}
                    className={`w-full px-3 py-2 text-left text-sm focus:outline-none ${isDark ? 'hover:bg-gray-700 hover:text-blue-400 focus:bg-gray-700' : 'hover:bg-blue-50 hover:text-blue-700 focus:bg-blue-50'}`}
                  >
                    {ns}
                  </button>
                ))}
              </div>
            )}
          </div>
          <button
            type="submit"
            className="inline-flex items-center px-4 py-2 text-sm font-medium text-white bg-orange-600 border border-transparent rounded-md shadow-sm hover:bg-orange-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-orange-500"
          >
            <Plus className="w-4 h-4 mr-1" />
            Exclude
          </button>
        </div>
      </form>

      <div className={`border rounded-md ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
        <div className={`px-4 py-3 border-b ${isDark ? 'bg-gray-900 border-gray-700' : 'bg-gray-50 border-gray-200'}`}>
          <h3 className={`text-sm font-medium ${isDark ? 'text-gray-200' : 'text-gray-700'}`}>
            Excluded Namespaces ({excludedNamespaces.length})
          </h3>
        </div>

        {excludedNamespaces.length === 0 ? (
          <div className={`px-4 py-6 text-center ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
            <p className="text-sm">No namespaces excluded.</p>
          </div>
        ) : (
          <ul className={`divide-y ${isDark ? 'divide-gray-700' : 'divide-gray-200'}`}>
            {excludedNamespaces.map((ns) => (
              <li key={ns.namespace} className={`px-4 py-3 flex items-center justify-between ${isDark ? 'hover:bg-gray-800' : 'hover:bg-gray-50'}`}>
                <div>
                  <span className={`text-sm font-medium ${isDark ? 'text-gray-200' : 'text-gray-900'}`}>{ns.namespace}</span>
                  {ns.created_at && (
                    <span className={`ml-2 text-xs ${isDark ? 'text-gray-500' : 'text-gray-500'}`}>
                      Added {new Date(ns.created_at).toLocaleDateString()}
                    </span>
                  )}
                </div>
                <button
                  onClick={() => handleRemoveNamespace(ns.namespace)}
                  className="inline-flex items-center px-2 py-1 text-xs font-medium text-red-700 bg-red-50 border border-red-200 rounded hover:bg-red-100 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500"
                >
                  <Trash2 className="w-3 h-3 mr-1" />
                  Remove
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
};

export default ExclusionNamespaces;
