import React, { useState, useEffect } from 'react';
import { AlertTriangle, CheckCircle, Server, Shield, Activity, ChevronDown, Filter, Settings } from 'lucide-react';
import PodTable from './PodTable';
import SecurityTable from './SecurityTable';
import AdminPanel from './AdminPanel';
import { api } from '../services/api';
import { useWebSocket } from '../hooks/useWebSocket';

const Dashboard = () => {
  const [activeTab, setActiveTab] = useState('monitoring');
  const [pods, setPods] = useState([]);
  const [securityFindings, setSecurityFindings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [clusterName, setClusterName] = useState('k8s-cluster');
  const [namespaceFilter, setNamespaceFilter] = useState('');
  const [selectedSeverities, setSelectedSeverities] = useState(['critical', 'high', 'medium', 'low']);
  const [showSeverityDropdown, setShowSeverityDropdown] = useState(false);

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
    } else if (message.type === 'security_finding') {
      // Update or add security finding (deduplicate by resource_name, namespace, and title)
      setSecurityFindings(prevFindings => {
        const existingIndex = prevFindings.findIndex(
          finding => finding.resource_name === message.data.resource_name &&
                     finding.namespace === message.data.namespace &&
                     finding.title === message.data.title
        );

        if (existingIndex >= 0) {
          // Update existing finding
          const newFindings = [...prevFindings];
          newFindings[existingIndex] = message.data;
          return newFindings;
        } else {
          // Add new finding
          return [message.data, ...prevFindings];
        }
      });
    } else if (message.type === 'security_finding_deleted') {
      // Remove deleted security finding from list
      setSecurityFindings(prevFindings =>
        prevFindings.filter(finding =>
          !(finding.resource_name === message.data.resource_name &&
            finding.namespace === message.data.namespace &&
            finding.title === message.data.title)
        )
      );
    }
  };

  const { connected } = useWebSocket(handleWebSocketMessage);

  // Filter pods based on namespace input
  const filteredPods = namespaceFilter.trim() === '' 
    ? pods 
    : pods.filter(pod => pod.namespace.toLowerCase().includes(namespaceFilter.toLowerCase().trim()));

  // Severity order for sorting (Critical > High > Medium > Low)
  const severityOrder = { 'critical': 1, 'high': 2, 'medium': 3, 'low': 4 };
  const allSeverities = ['critical', 'high', 'medium', 'low'];

  // Filter security findings based on namespace and severity
  const filteredSecurityFindings = securityFindings.filter(finding => {
    const matchesNamespace = namespaceFilter.trim() === '' ||
      finding.namespace.toLowerCase().includes(namespaceFilter.toLowerCase().trim());
    const matchesSeverity = selectedSeverities.includes(finding.severity.toLowerCase());
    return matchesNamespace && matchesSeverity;
  });

  // Sort security findings by severity (CRITICAL > HIGH > MEDIUM > LOW), then by timestamp (newest first)
  const sortedSecurityFindings = [...filteredSecurityFindings].sort((a, b) => {
    const severityA = severityOrder[a.severity.toLowerCase()] || 999;
    const severityB = severityOrder[b.severity.toLowerCase()] || 999;
    if (severityA !== severityB) {
      return severityA - severityB;
    }
    // Within same severity, sort by timestamp (newest first)
    return new Date(b.timestamp) - new Date(a.timestamp);
  });

  // Toggle severity selection
  const toggleSeverity = (severity) => {
    setSelectedSeverities(prev => {
      if (prev.includes(severity)) {
        // Don't allow deselecting all severities
        if (prev.length === 1) return prev;
        return prev.filter(s => s !== severity);
      } else {
        return [...prev, severity];
      }
    });
  };

  // Get severity badge color
  const getSeverityBadgeColor = (severity) => {
    switch (severity) {
      case 'critical': return 'bg-red-100 text-red-800 border-red-300';
      case 'high': return 'bg-orange-100 text-orange-800 border-orange-300';
      case 'medium': return 'bg-yellow-100 text-yellow-800 border-yellow-300';
      case 'low': return 'bg-blue-100 text-blue-800 border-blue-300';
      default: return 'bg-gray-100 text-gray-800 border-gray-300';
    }
  };

  // Load initial data
  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      const [activePods, findings, clusterInfo] = await Promise.all([
        api.getFailedPods(),
        api.getSecurityFindings(),
        api.getClusterInfo().catch(() => ({ cluster_name: 'k8s-cluster' }))
      ]);
      setPods(activePods);
      setSecurityFindings(findings);
      setClusterName(clusterInfo.cluster_name || 'k8s-cluster');
      setError(null);
    } catch (err) {
      setError('Failed to load data');
      console.error('Error loading data:', err);
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

        {/* Tabs */}
        <div className="mb-6">
          <div className="border-b border-gray-200">
            <nav className="-mb-px flex">
              <button
                onClick={() => setActiveTab('monitoring')}
                className={`${
                  activeTab === 'monitoring'
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                } mr-8 whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm flex items-center space-x-2`}
              >
                <Activity className="w-5 h-5" />
                <span>Pod Monitoring</span>
                {pods.length > 0 && (
                  <span className="ml-2 bg-red-100 text-red-800 py-0.5 px-2.5 rounded-full text-xs font-medium">
                    {pods.length}
                  </span>
                )}
              </button>
              <button
                onClick={() => setActiveTab('security')}
                className={`${
                  activeTab === 'security'
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                } mr-8 whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm flex items-center space-x-2`}
              >
                <Shield className="w-5 h-5" />
                <span>Security Scan</span>
                {securityFindings.length > 0 && (
                  <span className="ml-2 bg-orange-100 text-orange-800 py-0.5 px-2.5 rounded-full text-xs font-medium">
                    {securityFindings.length}
                  </span>
                )}
              </button>
              <button
                onClick={() => setActiveTab('admin')}
                className={`${
                  activeTab === 'admin'
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                } ml-auto whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm flex items-center space-x-2`}
              >
                <Settings className="w-5 h-5" />
                <span>Admin</span>
              </button>
            </nav>
          </div>
        </div>

        {/* Filters - hide on admin tab */}
        {activeTab !== 'admin' && (
        <div className="flex justify-end mb-4 gap-4">
          {/* Severity Filter - only show on security tab */}
          {activeTab === 'security' && (
            <div className="relative">
              <button
                onClick={() => setShowSeverityDropdown(!showSeverityDropdown)}
                className="flex items-center space-x-2 px-3 py-2 text-sm border border-gray-300 rounded-md shadow-sm bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <Filter className="w-4 h-4 text-gray-500" />
                <span className="text-gray-700">Severity</span>
                <span className="text-xs text-gray-500">({selectedSeverities.length}/{allSeverities.length})</span>
                <ChevronDown className={`w-4 h-4 text-gray-500 transition-transform ${showSeverityDropdown ? 'rotate-180' : ''}`} />
              </button>

              {showSeverityDropdown && (
                <div className="absolute right-0 mt-2 w-48 bg-white rounded-md shadow-lg border border-gray-200 z-10">
                  <div className="py-1">
                    {allSeverities.map(severity => (
                      <label
                        key={severity}
                        className="flex items-center px-4 py-2 hover:bg-gray-50 cursor-pointer"
                      >
                        <input
                          type="checkbox"
                          checked={selectedSeverities.includes(severity)}
                          onChange={() => toggleSeverity(severity)}
                          className="h-4 w-4 text-blue-600 rounded border-gray-300 focus:ring-blue-500"
                        />
                        <span className={`ml-3 px-2 py-0.5 rounded-full text-xs font-medium border ${getSeverityBadgeColor(severity)}`}>
                          {severity.charAt(0).toUpperCase() + severity.slice(1)}
                        </span>
                      </label>
                    ))}
                  </div>
                  <div className="border-t border-gray-100 px-4 py-2">
                    <button
                      onClick={() => setSelectedSeverities([...allSeverities])}
                      className="text-xs text-blue-600 hover:text-blue-800"
                    >
                      Select All
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Namespace Filter */}
          <div className="flex items-center space-x-2">
            <label htmlFor="namespace-filter" className="text-sm font-medium text-gray-700">
              Filter by namespace:
            </label>
            <input
              id="namespace-filter"
              type="text"
              value={namespaceFilter}
              onChange={(e) => setNamespaceFilter(e.target.value)}
              placeholder="Enter namespace"
              className="block w-40 px-3 py-2 text-sm border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
            />
          </div>
        </div>
        )}

        {/* Tab Content */}
        <div className="bg-white shadow rounded-lg">
          {activeTab === 'monitoring' && (
            <>
              {filteredPods.length === 0 ? (
                <div className="text-center py-12">
                  <CheckCircle className="w-12 h-12 text-green-500 mx-auto mb-4" />
                  <h3 className="text-lg font-medium text-gray-900 mb-2">
                    {pods.length === 0 ? 'All Good!' : 'No Failures Found'}
                  </h3>
                  <p className="text-gray-600">
                    {pods.length === 0
                      ? 'No pod failures detected in your cluster.'
                      : namespaceFilter.trim() === ''
                        ? 'No pod failures found in your cluster.'
                        : `No pod failures found matching namespace '${namespaceFilter}'.`
                    }
                  </p>
                </div>
              ) : (
                <PodTable pods={filteredPods} />
              )}
            </>
          )}

          {activeTab === 'security' && (
            <>
              {sortedSecurityFindings.length === 0 ? (
                <div className="text-center py-12">
                  <Shield className="w-12 h-12 text-green-500 mx-auto mb-4" />
                  <h3 className="text-lg font-medium text-gray-900 mb-2">
                    {securityFindings.length === 0 ? 'No Security Issues!' : 'No Issues Found'}
                  </h3>
                  <p className="text-gray-600">
                    {securityFindings.length === 0
                      ? 'No security issues detected in your cluster.'
                      : namespaceFilter.trim() === ''
                        ? 'No security issues found in your cluster.'
                        : `No security issues found matching namespace '${namespaceFilter}'.`
                    }
                  </p>
                </div>
              ) : (
                <SecurityTable findings={sortedSecurityFindings} />
              )}
            </>
          )}

          {activeTab === 'admin' && (
            <AdminPanel />
          )}

        </div>
      </div>
    </div>
  );
};

export default Dashboard;
