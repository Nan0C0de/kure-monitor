import React, { useState, useEffect } from 'react';
import { AlertTriangle, CheckCircle, Server } from 'lucide-react';
import PodTable from './PodTable';
import { api } from '../services/api';
import { useWebSocket } from '../hooks/useWebSocket';

const Dashboard = () => {
  const [pods, setPods] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [clusterName, setClusterName] = useState('k8s-cluster');

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
      const [activePods, clusterInfo] = await Promise.all([
        api.getFailedPods(),
        api.getClusterInfo().catch(() => ({ cluster_name: 'k8s-cluster' }))
      ]);
      setPods(activePods);
      setClusterName(clusterInfo.cluster_name || 'k8s-cluster');
      setError(null);
    } catch (err) {
      setError('Failed to load pod failures');
      console.error('Error loading pods:', err);
    } finally {
      setLoading(false);
    }
  };



  if (loading) {
    return (
      <div className="min-h-screen bg-gray-100 flex items-center justify-center">
        <div className="flex items-center space-x-2">
          <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
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
              <div className="flex items-center space-x-3">
                <span className="text-sm text-gray-600 font-medium">{clusterName}</span>
                <div className="flex items-center space-x-2">
                  <div className={`w-2 h-2 rounded-full ${connected ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`} />
                  <span className="text-sm text-gray-600 font-bold">
                    {connected ? 'Connected' : 'Disconnected'}
                  </span>
                </div>
              </div>
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
          {pods.length === 0 ? (
            <div className="text-center py-12">
              <CheckCircle className="w-12 h-12 text-green-500 mx-auto mb-4" />
              <h3 className="text-lg font-medium text-gray-900 mb-2">All Good!</h3>
              <p className="text-gray-600">No pod failures detected in your cluster.</p>
            </div>
          ) : (
            <PodTable pods={pods} />
          )}
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
