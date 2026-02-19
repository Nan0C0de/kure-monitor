import React, { useState, useEffect } from 'react';
import { Plus, Trash2, Globe } from 'lucide-react';
import { api } from '../../services/api';

const DEFAULT_REGISTRIES = ['docker.io', 'gcr.io', 'ghcr.io', 'quay.io', 'registry.k8s.io', 'mcr.microsoft.com', 'public.ecr.aws'];

const ExclusionRegistries = ({ isDark, onError, onSuccess }) => {
  const [trustedRegistries, setTrustedRegistries] = useState([]);
  const [newRegistry, setNewRegistry] = useState('');
  const [registryLoading, setRegistryLoading] = useState(null);

  useEffect(() => {
    const loadData = async () => {
      try {
        const data = await api.getTrustedRegistries();
        setTrustedRegistries(data);
      } catch (err) {
        // Silently handle - matches original .catch(() => []) behavior
        console.error('Error loading trusted registries:', err);
      }
    };
    loadData();
  }, []);

  const handleAddRegistry = async () => {
    const registry = newRegistry.trim().toLowerCase();
    if (!registry) {
      onError('Please enter a registry name');
      return;
    }
    if (DEFAULT_REGISTRIES.includes(registry)) {
      onError('This registry is already trusted by default');
      return;
    }
    if (trustedRegistries.some(r => r.registry === registry)) {
      onError('This registry is already in the trusted list');
      return;
    }
    setRegistryLoading('add');
    try {
      const result = await api.addTrustedRegistry(registry);
      setTrustedRegistries(prev => [...prev, result]);
      setNewRegistry('');
      onSuccess(`Registry "${registry}" added to trusted list.`);
    } catch (err) {
      onError('Failed to add registry');
      console.error('Error adding trusted registry:', err);
    } finally {
      setRegistryLoading(null);
    }
  };

  const handleRemoveRegistry = async (registry) => {
    setRegistryLoading(registry);
    try {
      await api.removeTrustedRegistry(registry);
      setTrustedRegistries(prev => prev.filter(r => r.registry !== registry));
      onSuccess(`Registry "${registry}" removed from trusted list.`);
    } catch (err) {
      onError('Failed to remove registry');
      console.error('Error removing trusted registry:', err);
    } finally {
      setRegistryLoading(null);
    }
  };

  const handleRegistrySubmit = (e) => {
    e.preventDefault();
    handleAddRegistry();
  };

  return (
    <div>
      <div className="mb-4 flex items-center">
        <Globe className="w-5 h-5 text-blue-500 mr-2" />
        <h2 className={`text-lg font-semibold ${isDark ? 'text-gray-100' : 'text-gray-900'}`}>Trusted Container Registries</h2>
      </div>
      <p className={`text-sm mb-4 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
        Add custom trusted container registries. Default registries cannot be removed.
      </p>

      <form onSubmit={handleRegistrySubmit} className="mb-4">
        <div className="flex gap-2">
          <input
            type="text"
            value={newRegistry}
            onChange={(e) => setNewRegistry(e.target.value)}
            placeholder="e.g. my-registry.example.com"
            className={`flex-1 px-3 py-2 text-sm border rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 ${isDark ? 'bg-gray-700 border-gray-600 text-gray-200 placeholder-gray-400' : 'bg-white border-gray-300 text-gray-900'}`}
          />
          <button
            type="submit"
            disabled={registryLoading === 'add'}
            className={`inline-flex items-center px-4 py-2 text-sm font-medium text-white border border-transparent rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 ${registryLoading === 'add' ? 'bg-blue-400 cursor-not-allowed' : 'bg-blue-600 hover:bg-blue-700'}`}
          >
            {registryLoading === 'add' ? (
              <>
                <svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                Adding...
              </>
            ) : (
              <>
                <Plus className="w-4 h-4 mr-1" />
                Add
              </>
            )}
          </button>
        </div>
      </form>

      <div className={`border rounded-md ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
        <div className={`px-4 py-3 border-b ${isDark ? 'bg-gray-900 border-gray-700' : 'bg-gray-50 border-gray-200'}`}>
          <h3 className={`text-sm font-medium ${isDark ? 'text-gray-200' : 'text-gray-700'}`}>
            Trusted Registries ({DEFAULT_REGISTRIES.length + trustedRegistries.length})
          </h3>
        </div>

        <ul className={`divide-y ${isDark ? 'divide-gray-700' : 'divide-gray-200'}`}>
          {DEFAULT_REGISTRIES.map((reg) => (
            <li key={reg} className={`px-4 py-3 flex items-center justify-between ${isDark ? '' : ''}`}>
              <div>
                <span className={`text-sm font-medium ${isDark ? 'text-gray-200' : 'text-gray-900'}`}>{reg}</span>
                <span className={`ml-2 text-xs px-2 py-0.5 rounded-full ${isDark ? 'bg-gray-700 text-gray-400' : 'bg-gray-200 text-gray-600'}`}>
                  Default
                </span>
              </div>
            </li>
          ))}
          {trustedRegistries.map((reg) => (
            <li key={reg.registry} className={`px-4 py-3 flex items-center justify-between ${isDark ? 'hover:bg-gray-800' : 'hover:bg-gray-50'}`}>
              <div>
                <span className={`text-sm font-medium ${isDark ? 'text-gray-200' : 'text-gray-900'}`}>{reg.registry}</span>
                {reg.created_at && (
                  <span className={`ml-2 text-xs ${isDark ? 'text-gray-500' : 'text-gray-500'}`}>
                    Added {new Date(reg.created_at).toLocaleDateString()}
                  </span>
                )}
              </div>
              <button
                onClick={() => handleRemoveRegistry(reg.registry)}
                disabled={registryLoading === reg.registry}
                className={`inline-flex items-center px-2 py-1 text-xs font-medium border rounded focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500 ${registryLoading === reg.registry ? 'text-gray-400 bg-gray-100 border-gray-200 cursor-not-allowed' : 'text-red-700 bg-red-50 border-red-200 hover:bg-red-100'}`}
              >
                {registryLoading === reg.registry ? (
                  <>
                    <svg className="animate-spin -ml-0.5 mr-1 h-3 w-3 text-gray-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    Removing...
                  </>
                ) : (
                  <>
                    <Trash2 className="w-3 h-3 mr-1" />
                    Remove
                  </>
                )}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
};

export default ExclusionRegistries;
