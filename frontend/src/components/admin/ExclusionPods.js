import React, { useState, useEffect } from 'react';
import { Plus, Trash2, Activity } from 'lucide-react';
import { api } from '../../services/api';

const ExclusionPods = ({ isDark, onError, onSuccess }) => {
  const [excludedPods, setExcludedPods] = useState([]);
  const [monitoredPods, setMonitoredPods] = useState([]);
  const [newPodName, setNewPodName] = useState('');
  const [showPodSuggestions, setShowPodSuggestions] = useState(false);

  useEffect(() => {
    const loadData = async () => {
      try {
        const [excludedPodsData, monitoredPodsData] = await Promise.all([
          api.getExcludedPods(),
          api.getMonitoredPods()
        ]);
        setExcludedPods(excludedPodsData);
        setMonitoredPods(monitoredPodsData);
      } catch (err) {
        onError('Failed to load pod data');
        console.error('Error loading pod data:', err);
      }
    };
    loadData();
  }, [onError]);

  // Pod suggestions: monitored pods that are not already excluded (by pod name only)
  const podSuggestions = monitoredPods.filter(
    pod => !excludedPods.some(excluded => excluded.pod_name === pod.pod_name)
  );

  const filteredPodSuggestions = newPodName.trim()
    ? podSuggestions.filter(pod =>
        pod.pod_name.toLowerCase().includes(newPodName.toLowerCase())
      )
    : podSuggestions;

  const handleAddPod = async (podToAdd) => {
    const podName = (podToAdd?.pod_name || newPodName).trim();

    if (!podName) {
      onError('Please enter a pod name');
      return;
    }

    if (excludedPods.some(pod => pod.pod_name === podName)) {
      onError('This pod is already excluded');
      return;
    }

    try {
      const result = await api.addExcludedPod(podName);
      setExcludedPods(prev => [...prev, result]);
      setNewPodName('');
      setShowPodSuggestions(false);
      onSuccess(`Pod "${podName}" excluded from monitoring.`);
    } catch (err) {
      onError('Failed to add pod');
      console.error('Error adding pod:', err);
    }
  };

  const handleRemovePod = async (podName) => {
    try {
      await api.removeExcludedPod(podName);
      setExcludedPods(prev => prev.filter(pod => pod.pod_name !== podName));
      onSuccess(`Pod "${podName}" will now be monitored again`);
    } catch (err) {
      onError('Failed to remove pod');
      console.error('Error removing pod:', err);
    }
  };

  const handlePodSubmit = (e) => {
    e.preventDefault();
    handleAddPod();
  };

  return (
    <div>
      <div className="mb-4 flex items-center">
        <Activity className="w-5 h-5 text-blue-500 mr-2" />
        <h2 className={`text-lg font-semibold ${isDark ? 'text-gray-100' : 'text-gray-900'}`}>Pods (Failure Monitoring)</h2>
      </div>
      <p className={`text-sm mb-4 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
        Exclude pods from failure monitoring across all namespaces.
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
            <p className="text-sm">No pods excluded.</p>
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

export default ExclusionPods;
