import React, { useState, useEffect } from 'react';
import { RefreshCw, AlertTriangle, CheckCircle, Server, EyeOff, Eye } from 'lucide-react';
import PodTable from './PodTable';
import { api } from '../services/api';
import { useWebSocket } from '../hooks/useWebSocket';

const Dashboard = () => {
  const [pods, setPods] = useState([]);
  const [ignoredPods, setIgnoredPods] = useState([]);
  const [activeTab, setActiveTab] = useState('active'); // 'active' or 'ignored'
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Handle WebSocket messages
  const handleWebSocketMessage = (message) => {
    if (message.type === 'pod_failure') {
      // Update or add pod failure
      setPods(prevPods => {
        const existingIndex = prevPods.findIndex(
          pod => pod.pod_name === message.data.pod_name && 
                 pod.namespace === message.data.namespace
        );
        
        if (existingIndex >= 0) {
          // Update existing pod
          const newPods = [...prevPods];
          newPods[existingIndex] = message.data;
          return newPods;
        } else {
          // Add new pod
          return [message.data, ...prevPods];
        }
      });
    } else if (message.type === 'pod_deleted') {
      // Remove deleted pod from list
      setPods(prevPods => 
        prevPods.filter(pod => 
          !(pod.pod_name === message.data.pod_name && 
            pod.namespace === message.data.namespace)
        )
      );
    }
  };

  const { connected } = useWebSocket(handleWebSocketMessage);

  // Load initial data
  useEffect(() => {
    loadPods();
  }, []);

  const loadPods = async () => {
    try {
      setLoading(true);
      const [activePods, ignored] = await Promise.all([
        api.getFailedPods(),
        api.getIgnoredPods()
      ]);
      setPods(activePods);
      setIgnoredPods(ignored);
      setError(null);
    } catch (err) {
      setError('Failed to load pod failures');
      console.error('Error loading pods:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleIgnore = async (podId) => {
    try {
      await api.dismissPod(podId);
      const ignoredPod = pods.find(pod => pod.id === podId);
      if (ignoredPod) {
        setPods(pods.filter(pod => pod.id !== podId));
        setIgnoredPods(prev => [{ ...ignoredPod, dismissed: true }, ...prev]);
      }
    } catch (err) {
      setError('Failed to ignore pod');
      console.error('Error ignoring pod:', err);
    }
  };

  const handleRestore = async (podId) => {
    try {
      await api.restorePod(podId);
      const restoredPod = ignoredPods.find(pod => pod.id === podId);
      if (restoredPod) {
        setIgnoredPods(ignoredPods.filter(pod => pod.id !== podId));
        setPods(prev => [{ ...restoredPod, dismissed: false }, ...prev]);
      }
    } catch (err) {
      setError('Failed to restore pod');
      console.error('Error restoring pod:', err);
    }
  };

  const handleRefresh = () => {
    loadPods();
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-100 flex items-center justify-center">
        <div className="flex items-center space-x-2">
          <RefreshCw className="w-6 h-6 animate-spin text-blue-500" />
          <span>Loading pod failures...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-100">
      <div className="bg-white shadow">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center space-x-3">
              <Server className="w-8 h-8 text-blue-500" />
              <h1 className="text-2xl font-bold text-gray-900">Kure Dashboard</h1>
            </div>

            <div className="flex items-center space-x-4">
              <div className="flex items-center space-x-2">
                <div className={`w-2 h-2 rounded-full ${connected ? 'bg-green-500' : 'bg-red-500'}`} />
                <span className="text-sm text-gray-600">
                  {connected ? 'Connected' : 'Disconnected'}
                </span>
              </div>

              <button
                onClick={handleRefresh}
                className="flex items-center space-x-2 px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
              >
                <RefreshCw className="w-4 h-4" />
                <span>Refresh</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {error && (
          <div className="mb-6 bg-red-50 border border-red-200 rounded-md p-4">
            <div className="flex">
              <AlertTriangle className="w-5 h-5 text-red-400" />
              <div className="ml-3">
                <p className="text-sm text-red-800">{error}</p>
              </div>
            </div>
          </div>
        )}

        <div className="bg-white shadow rounded-lg">
          {/* Tab Navigation */}
          <div className="border-b border-gray-200">
            <nav className="-mb-px flex">
              <button
                onClick={() => setActiveTab('active')}
                className={`py-4 px-6 text-sm font-medium border-b-2 ${
                  activeTab === 'active'
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                <div className="flex items-center space-x-2">
                  <AlertTriangle className="w-4 h-4" />
                  <span>Active Failures ({pods.length})</span>
                </div>
              </button>
              <button
                onClick={() => setActiveTab('ignored')}
                className={`py-4 px-6 text-sm font-medium border-b-2 ${
                  activeTab === 'ignored'
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                <div className="flex items-center space-x-2">
                  <EyeOff className="w-4 h-4" />
                  <span>Ignored ({ignoredPods.length})</span>
                </div>
              </button>
            </nav>
          </div>

          {/* Tab Content */}
          {activeTab === 'active' && (
            <>
              {pods.length === 0 ? (
                <div className="text-center py-12">
                  <CheckCircle className="w-12 h-12 text-green-500 mx-auto mb-4" />
                  <h3 className="text-lg font-medium text-gray-900 mb-2">All Good!</h3>
                  <p className="text-gray-600">No pod failures detected in your cluster.</p>
                </div>
              ) : (
                <PodTable pods={pods} onIgnore={handleIgnore} />
              )}
            </>
          )}

          {activeTab === 'ignored' && (
            <>
              {ignoredPods.length === 0 ? (
                <div className="text-center py-12">
                  <Eye className="w-12 h-12 text-gray-400 mx-auto mb-4" />
                  <h3 className="text-lg font-medium text-gray-900 mb-2">No Ignored Pods</h3>
                  <p className="text-gray-600">You haven't ignored any pod failures yet.</p>
                </div>
              ) : (
                <PodTable pods={ignoredPods} onIgnore={handleRestore} isIgnoredView={true} />
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
