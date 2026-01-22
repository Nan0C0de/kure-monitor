import React, { useState, useEffect } from 'react';
import { Plus, Trash2, AlertCircle, CheckCircle, Shield, Activity } from 'lucide-react';
import { api } from '../services/api';
import NotificationSettings from './NotificationSettings';
import LLMSettings from './LLMSettings';

const AdminPanel = ({ isDark = false }) => {
  // Security Scan Namespace Exclusions state
  const [excludedNamespaces, setExcludedNamespaces] = useState([]);
  const [availableNamespaces, setAvailableNamespaces] = useState([]);
  const [newNamespace, setNewNamespace] = useState('');
  const [showNamespaceSuggestions, setShowNamespaceSuggestions] = useState(false);

  // Pod Monitoring Exclusions state
  const [excludedPods, setExcludedPods] = useState([]);
  const [monitoredPods, setMonitoredPods] = useState([]);
  const [newPodName, setNewPodName] = useState('');
  const [showPodSuggestions, setShowPodSuggestions] = useState(false);

  // General state
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [successMessage, setSuccessMessage] = useState(null);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      const [excluded, available, excludedPodsData, monitoredPodsData] = await Promise.all([
        api.getExcludedNamespaces(),
        api.getAllNamespaces(),
        api.getExcludedPods(),
        api.getMonitoredPods()
      ]);
      setExcludedNamespaces(excluded);
      setAvailableNamespaces(available);
      setExcludedPods(excludedPodsData);
      setMonitoredPods(monitoredPodsData);
      setError(null);
    } catch (err) {
      setError('Failed to load data');
      console.error('Error loading data:', err);
    } finally {
      setLoading(false);
    }
  };

  // Namespace suggestions: available namespaces that are not already excluded
  const namespaceSuggestions = availableNamespaces.filter(
    ns => !excludedNamespaces.some(excluded => excluded.namespace === ns)
  );

  const filteredNamespaceSuggestions = newNamespace.trim()
    ? namespaceSuggestions.filter(ns => ns.toLowerCase().includes(newNamespace.toLowerCase()))
    : namespaceSuggestions;

  // Pod suggestions: monitored pods that are not already excluded (by pod name only)
  const podSuggestions = monitoredPods.filter(
    pod => !excludedPods.some(excluded => excluded.pod_name === pod.pod_name)
  );

  const filteredPodSuggestions = newPodName.trim()
    ? podSuggestions.filter(pod =>
        pod.pod_name.toLowerCase().includes(newPodName.toLowerCase())
      )
    : podSuggestions;

  const handleAddNamespace = async (namespaceToAdd) => {
    const namespace = (namespaceToAdd || newNamespace).trim();

    if (!namespace) {
      setError('Please enter a namespace name');
      return;
    }

    if (excludedNamespaces.some(ns => ns.namespace === namespace)) {
      setError('This namespace is already excluded');
      return;
    }

    try {
      const result = await api.addExcludedNamespace(namespace);
      setExcludedNamespaces(prev => [...prev, result]);
      setNewNamespace('');
      setShowNamespaceSuggestions(false);
      setError(null);
      setSuccessMessage(`Namespace "${namespace}" excluded from security scan.`);
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

  const handleAddPod = async (podToAdd) => {
    const podName = (podToAdd?.pod_name || newPodName).trim();

    if (!podName) {
      setError('Please enter a pod name');
      return;
    }

    if (excludedPods.some(pod => pod.pod_name === podName)) {
      setError('This pod is already excluded');
      return;
    }

    try {
      const result = await api.addExcludedPod(podName);
      setExcludedPods(prev => [...prev, result]);
      setNewPodName('');
      setShowPodSuggestions(false);
      setError(null);
      setSuccessMessage(`Pod "${podName}" excluded from monitoring.`);
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (err) {
      setError('Failed to add pod');
      console.error('Error adding pod:', err);
    }
  };

  const handleRemovePod = async (podName) => {
    try {
      await api.removeExcludedPod(podName);
      setExcludedPods(prev => prev.filter(pod => pod.pod_name !== podName));
      setError(null);
      setSuccessMessage(`Pod "${podName}" will now be monitored again`);
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (err) {
      setError('Failed to remove pod');
      console.error('Error removing pod:', err);
    }
  };

  const handleNamespaceSubmit = (e) => {
    e.preventDefault();
    handleAddNamespace();
  };

  const handlePodSubmit = (e) => {
    e.preventDefault();
    handleAddPod();
  };

  if (loading) {
    return (
      <div className="p-6">
        <div className="flex items-center justify-center py-8">
          <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
          <span className={`ml-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Loading...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-8">
      {error && (
        <div className={`border rounded-md p-3 ${isDark ? 'bg-red-900/30 border-red-800' : 'bg-red-50 border-red-200'}`}>
          <div className="flex items-center">
            <AlertCircle className="w-4 h-4 text-red-500 mr-2" />
            <span className={`text-sm ${isDark ? 'text-red-300' : 'text-red-800'}`}>{error}</span>
          </div>
        </div>
      )}

      {successMessage && (
        <div className={`border rounded-md p-3 ${isDark ? 'bg-green-900/30 border-green-800' : 'bg-green-50 border-green-200'}`}>
          <div className="flex items-center">
            <CheckCircle className="w-4 h-4 text-green-500 mr-2" />
            <span className={`text-sm ${isDark ? 'text-green-300' : 'text-green-800'}`}>{successMessage}</span>
          </div>
        </div>
      )}

      {/* LLM Configuration */}
      <LLMSettings isDark={isDark} />

      {/* Notification Settings */}
      <NotificationSettings isDark={isDark} />

      {/* Security Scan Namespace Exclusions */}
      <div>
        <div className="mb-4 flex items-center">
          <Shield className="w-5 h-5 text-orange-500 mr-2" />
          <h2 className={`text-lg font-semibold ${isDark ? 'text-gray-100' : 'text-gray-900'}`}>Security Scan Namespace Exclusions</h2>
        </div>
        <p className={`text-sm mb-4 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
          Namespaces added here will be excluded from security scanning only.
          System namespaces (kube-system, kube-public, etc.) are always excluded by default.
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
              <p className="text-sm">No namespaces excluded from security scan.</p>
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
                    Include
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* Pod Monitoring Exclusions */}
      <div>
        <div className="mb-4 flex items-center">
          <Activity className="w-5 h-5 text-blue-500 mr-2" />
          <h2 className={`text-lg font-semibold ${isDark ? 'text-gray-100' : 'text-gray-900'}`}>Pod Monitoring Exclusions</h2>
        </div>
        <p className={`text-sm mb-4 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
          Pods added here (by name) will be excluded from pod failure monitoring across all namespaces.
          Use this to ignore known pods that you don't want to receive alerts for.
        </p>

        <form onSubmit={handlePodSubmit} className="mb-4">
          <div className="flex gap-2">
            <div className="relative flex-1">
              <input
                type="text"
                value={newPodName}
                onChange={(e) => {
                  setNewPodName(e.target.value);
                  setShowPodSuggestions(true);
                }}
                onFocus={() => setShowPodSuggestions(true)}
                onBlur={() => setTimeout(() => setShowPodSuggestions(false), 200)}
                placeholder="Enter or select pod name"
                className={`w-full px-3 py-2 text-sm border rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 ${isDark ? 'bg-gray-700 border-gray-600 text-gray-200 placeholder-gray-400' : 'bg-white border-gray-300 text-gray-900'}`}
              />
              {showPodSuggestions && filteredPodSuggestions.length > 0 && (
                <div className={`absolute z-10 w-full mt-1 border rounded-md shadow-lg max-h-48 overflow-y-auto ${isDark ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'}`}>
                  <div className={`px-3 py-2 text-xs border-b ${isDark ? 'text-gray-400 border-gray-700' : 'text-gray-500 border-gray-100'}`}>
                    Monitored pods with issues
                  </div>
                  {filteredPodSuggestions.map(pod => (
                    <button
                      key={pod.pod_name}
                      type="button"
                      onClick={() => handleAddPod(pod)}
                      className={`w-full px-3 py-2 text-left text-sm focus:outline-none ${isDark ? 'hover:bg-gray-700 hover:text-blue-400 focus:bg-gray-700' : 'hover:bg-blue-50 hover:text-blue-700 focus:bg-blue-50'}`}
                    >
                      <span className="font-medium">{pod.pod_name}</span>
                      <span className={`text-xs ml-2 ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>({pod.namespace})</span>
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
        </form>

        <div className={`border rounded-md ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
          <div className={`px-4 py-3 border-b ${isDark ? 'bg-gray-900 border-gray-700' : 'bg-gray-50 border-gray-200'}`}>
            <h3 className={`text-sm font-medium ${isDark ? 'text-gray-200' : 'text-gray-700'}`}>
              Excluded Pods ({excludedPods.length})
            </h3>
          </div>

          {excludedPods.length === 0 ? (
            <div className={`px-4 py-6 text-center ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
              <p className="text-sm">No pods excluded from monitoring.</p>
            </div>
          ) : (
            <ul className={`divide-y ${isDark ? 'divide-gray-700' : 'divide-gray-200'}`}>
              {excludedPods.map((pod) => (
                <li key={pod.pod_name} className={`px-4 py-3 flex items-center justify-between ${isDark ? 'hover:bg-gray-800' : 'hover:bg-gray-50'}`}>
                  <div>
                    <span className={`text-sm font-medium ${isDark ? 'text-gray-200' : 'text-gray-900'}`}>{pod.pod_name}</span>
                    {pod.created_at && (
                      <span className={`ml-2 text-xs ${isDark ? 'text-gray-500' : 'text-gray-500'}`}>
                        Added {new Date(pod.created_at).toLocaleDateString()}
                      </span>
                    )}
                  </div>
                  <button
                    onClick={() => handleRemovePod(pod.pod_name)}
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
    </div>
  );
};

export default AdminPanel;
