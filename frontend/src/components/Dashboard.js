import React, { useState, useEffect, useCallback } from 'react';
import { AlertTriangle, CheckCircle, Server, Shield, Activity, ChevronDown, Filter, Settings, BarChart3, Sun, Moon, Download, Clock, EyeOff } from 'lucide-react';
import PodTable from './PodTable';
import SecurityTable from './SecurityTable';
import AdminPanel from './AdminPanel';
import MonitoringTab from './MonitoringTab';
import SetupBanner from './SetupBanner';
import { api } from '../services/api';
import { useWebSocket } from '../hooks/useWebSocket';
import { exportAsCSV, exportAsJSON, exportAsPDF } from '../utils/exportFindings';

const Dashboard = () => {
  const [activeTab, setActiveTab] = useState('monitoring');
  const [pods, setPods] = useState([]);
  const [securityFindings, setSecurityFindings] = useState([]);
  const [clusterMetrics, setClusterMetrics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [aiEnabled, setAiEnabled] = useState(false);
  // Separate namespace filters for each tab
  const [podNamespaceFilter, setPodNamespaceFilter] = useState('');
  const [securityNamespaceFilter, setSecurityNamespaceFilter] = useState('');
  const [selectedSeverities, setSelectedSeverities] = useState(['critical', 'high', 'medium', 'low']);
  const [showSeverityDropdown, setShowSeverityDropdown] = useState(false);
  const [showExportDropdown, setShowExportDropdown] = useState(false);
  // Pod sub-tab state
  const [podSubTab, setPodSubTab] = useState('active');
  const [podHistory, setPodHistory] = useState([]);
  const [ignoredPods, setIgnoredPods] = useState([]);

  // Theme state - load from localStorage or default to 'light'
  const [theme, setTheme] = useState(() => {
    if (typeof window !== 'undefined') {
      return localStorage.getItem('kure-theme') || 'light';
    }
    return 'light';
  });

  // Apply theme to document and save to localStorage
  useEffect(() => {
    localStorage.setItem('kure-theme', theme);
    if (theme === 'dark') {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, [theme]);

  const toggleTheme = () => {
    setTheme(prev => prev === 'light' ? 'dark' : 'light');
  };

  const isDark = theme === 'dark';

  // Handle WebSocket messages - wrapped in useCallback for stability
  const handleWebSocketMessage = useCallback((message) => {
    if (message.type === 'pod_failure') {
      // Update or add pod failure (deduplicate by id OR by pod_name+namespace)
      setPods(prevPods => {
        // Check by ID first (most reliable), then by name+namespace
        const existingByIdIndex = message.data.id
          ? prevPods.findIndex(pod => pod.id === message.data.id)
          : -1;
        const existingByNameIndex = prevPods.findIndex(
          pod => pod.pod_name === message.data.pod_name &&
                 pod.namespace === message.data.namespace
        );

        const existingIndex = existingByIdIndex >= 0 ? existingByIdIndex : existingByNameIndex;

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
      // Update or add security finding (deduplicate by id OR by resource_name+namespace+title)
      setSecurityFindings(prevFindings => {
        const existingByIdIndex = message.data.id
          ? prevFindings.findIndex(finding => finding.id === message.data.id)
          : -1;
        const existingByNameIndex = prevFindings.findIndex(
          finding => finding.resource_name === message.data.resource_name &&
                     finding.namespace === message.data.namespace &&
                     finding.title === message.data.title
        );

        const existingIndex = existingByIdIndex >= 0 ? existingByIdIndex : existingByNameIndex;

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
    } else if (message.type === 'pod_solution_updated') {
      // Update pod with new solution
      setPods(prevPods => {
        return prevPods.map(pod =>
          pod.id === message.data.id ? message.data : pod
        );
      });
    } else if (message.type === 'pod_status_change') {
      // Move pod between lists based on new status
      const pod = message.data;
      const newStatus = pod.status;
      // Remove from all lists first
      setPods(prev => prev.filter(p => p.id !== pod.id));
      setPodHistory(prev => prev.filter(p => p.id !== pod.id));
      setIgnoredPods(prev => prev.filter(p => p.id !== pod.id));
      // Add to appropriate list
      if (newStatus === 'new' || newStatus === 'investigating') {
        setPods(prev => [pod, ...prev.filter(p => p.id !== pod.id)]);
      } else if (newStatus === 'resolved') {
        setPodHistory(prev => [pod, ...prev.filter(p => p.id !== pod.id)]);
      } else if (newStatus === 'ignored') {
        setIgnoredPods(prev => [pod, ...prev.filter(p => p.id !== pod.id)]);
      }
    } else if (message.type === 'pod_record_deleted') {
      // Remove permanently deleted pod record from all lists
      const deletedId = message.data.id;
      setPodHistory(prev => prev.filter(p => p.id !== deletedId));
      setIgnoredPods(prev => prev.filter(p => p.id !== deletedId));
    } else if (message.type === 'cluster_metrics') {
      // Update cluster metrics
      setClusterMetrics(message.data);
    }
  }, []);

  // Handle solution update from retry button
  const handleSolutionUpdated = (updatedPod) => {
    setPods(prevPods => {
      return prevPods.map(pod =>
        pod.id === updatedPod.id ? updatedPod : pod
      );
    });
  };

  // Handle permanent deletion of a pod record (history/ignored)
  const handleDeletePodRecord = async (podId) => {
    try {
      await api.deletePodRecord(podId);
      setPodHistory(prev => prev.filter(p => p.id !== podId));
      setIgnoredPods(prev => prev.filter(p => p.id !== podId));
    } catch (err) {
      console.error('Failed to delete pod record:', err);
    }
  };

  // Handle pod status change (acknowledge, resolve, ignore, restore)
  const handleStatusChange = async (podId, newStatus) => {
    try {
      const updatedPod = await api.updatePodStatus(podId, newStatus);
      // Remove from current list
      setPods(prev => prev.filter(p => p.id !== podId));
      setPodHistory(prev => prev.filter(p => p.id !== podId));
      setIgnoredPods(prev => prev.filter(p => p.id !== podId));
      // Add to appropriate list
      if (newStatus === 'new' || newStatus === 'investigating') {
        setPods(prev => [updatedPod, ...prev.filter(p => p.id !== updatedPod.id)]);
      } else if (newStatus === 'resolved') {
        setPodHistory(prev => [updatedPod, ...prev.filter(p => p.id !== updatedPod.id)]);
      } else if (newStatus === 'ignored') {
        setIgnoredPods(prev => [updatedPod, ...prev.filter(p => p.id !== updatedPod.id)]);
      }
    } catch (err) {
      console.error('Failed to update pod status:', err);
    }
  };

  // Load history/ignored pods on sub-tab change
  const loadPodHistory = useCallback(async () => {
    try {
      const history = await api.getPodHistory();
      setPodHistory(history);
    } catch (err) {
      console.error('Failed to load pod history:', err);
    }
  }, []);

  const loadIgnoredPods = useCallback(async () => {
    try {
      const ignored = await api.getIgnoredPods();
      setIgnoredPods(ignored);
    } catch (err) {
      console.error('Failed to load ignored pods:', err);
    }
  }, []);

  useEffect(() => {
    if (podSubTab === 'history') loadPodHistory();
    else if (podSubTab === 'ignored') loadIgnoredPods();
  }, [podSubTab, loadPodHistory, loadIgnoredPods]);

  const { connected } = useWebSocket(handleWebSocketMessage);

  // Filter pods based on pod-specific namespace filter
  const filteredPods = podNamespaceFilter.trim() === ''
    ? pods
    : pods.filter(pod => pod.namespace.toLowerCase().includes(podNamespaceFilter.toLowerCase().trim()));

  const filteredHistory = podNamespaceFilter.trim() === ''
    ? podHistory
    : podHistory.filter(pod => pod.namespace.toLowerCase().includes(podNamespaceFilter.toLowerCase().trim()));

  const filteredIgnored = podNamespaceFilter.trim() === ''
    ? ignoredPods
    : ignoredPods.filter(pod => pod.namespace.toLowerCase().includes(podNamespaceFilter.toLowerCase().trim()));

  // Severity order for sorting (Critical > High > Medium > Low)
  const severityOrder = { 'critical': 1, 'high': 2, 'medium': 3, 'low': 4 };
  const allSeverities = ['critical', 'high', 'medium', 'low'];

  // Filter security findings based on security-specific namespace filter and severity
  const filteredSecurityFindings = securityFindings.filter(finding => {
    const matchesNamespace = securityNamespaceFilter.trim() === '' ||
      finding.namespace.toLowerCase().includes(securityNamespaceFilter.toLowerCase().trim());
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
      case 'critical': return isDark ? 'bg-red-900 text-red-200 border-red-700' : 'bg-red-100 text-red-800 border-red-300';
      case 'high': return isDark ? 'bg-orange-900 text-orange-200 border-orange-700' : 'bg-orange-100 text-orange-800 border-orange-300';
      case 'medium': return isDark ? 'bg-yellow-900 text-yellow-200 border-yellow-700' : 'bg-yellow-100 text-yellow-800 border-yellow-300';
      case 'low': return isDark ? 'bg-blue-900 text-blue-200 border-blue-700' : 'bg-blue-100 text-blue-800 border-blue-300';
      default: return isDark ? 'bg-gray-700 text-gray-200 border-gray-600' : 'bg-gray-100 text-gray-800 border-gray-300';
    }
  };

  // Load initial data
  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      const [activePods, findings, config, metrics] = await Promise.all([
        api.getFailedPods(),
        api.getSecurityFindings(),
        api.getConfig(),
        api.getClusterMetrics().catch(() => null)
      ]);
      setPods(activePods);
      setSecurityFindings(findings);
      setAiEnabled(config.ai_enabled || false);
      if (metrics && metrics.node_count) {
        setClusterMetrics(metrics);
      }
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
      <div className={`min-h-screen flex items-center justify-center ${isDark ? 'bg-gray-900 text-gray-100' : 'bg-gray-100 text-gray-900'}`}>
        <div className="flex items-center space-x-2">
          <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
          <span>Loading pod failures...</span>
        </div>
      </div>
    );
  }

  return (
    <div className={`min-h-screen ${isDark ? 'bg-gray-900' : 'bg-gray-100'}`}>
      <div className={`${isDark ? 'bg-gray-800' : 'bg-white'} shadow`}>
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center space-x-3">
              <Server className={`w-8 h-8 ${isDark ? 'text-blue-400' : 'text-blue-500'}`} />
              <h1 className={`text-2xl font-bold ${isDark ? 'text-gray-100' : 'text-gray-900'}`}>Kure Dashboard</h1>
            </div>

            <div className="flex items-center space-x-4">
              {/* Theme Toggle */}
              <button
                onClick={toggleTheme}
                className={`p-2 rounded-lg transition-colors ${
                  isDark
                    ? 'hover:bg-gray-700 text-gray-300 hover:text-gray-100'
                    : 'hover:bg-gray-100 text-gray-600 hover:text-gray-900'
                }`}
                title={`Switch to ${isDark ? 'light' : 'dark'} mode`}
              >
                {isDark ? (
                  <Sun className="w-5 h-5" />
                ) : (
                  <Moon className="w-5 h-5" />
                )}
              </button>

              {/* Connection Status */}
              <div className="flex items-center space-x-2">
                <div className={`w-2 h-2 rounded-full ${connected ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`} />
                <span className={`text-sm font-bold ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>
                  {connected ? 'Connected' : 'Disconnected'}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {error && (
          <div className={`mb-6 ${isDark ? 'bg-red-900/50 border-red-700' : 'bg-red-50 border-red-200'} border rounded-md p-4`}>
            <div className="flex">
              <AlertTriangle className={`w-5 h-5 ${isDark ? 'text-red-400' : 'text-red-400'}`} />
              <div className="ml-3">
                <p className={`text-sm ${isDark ? 'text-red-200' : 'text-red-800'}`}>{error}</p>
              </div>
            </div>
          </div>
        )}

        {/* Setup Banner - shows when LLM is not configured */}
        <SetupBanner isDark={isDark} onNavigateToAdmin={() => setActiveTab('admin')} />

        {/* Tabs */}
        <div className="mb-6">
          <div className={`border-b ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
            <nav className="-mb-px flex justify-between">
              <div className="flex">
                <button
                  onClick={() => setActiveTab('monitoring')}
                  className={`${
                    activeTab === 'monitoring'
                      ? isDark ? 'border-blue-400 text-blue-400' : 'border-blue-500 text-blue-600'
                      : isDark ? 'border-transparent text-gray-400 hover:text-gray-200 hover:border-gray-500' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                  } mr-8 whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm flex items-center space-x-2`}
                >
                  <Activity className="w-5 h-5" />
                  <span>Pod Monitoring</span>
                  {pods.filter(p => p.status === 'new' || p.status === 'investigating' || !p.status).length > 0 && (
                    <span className={`ml-2 py-0.5 px-2.5 rounded-full text-xs font-medium ${isDark ? 'bg-red-900 text-red-200' : 'bg-red-100 text-red-800'}`}>
                      {pods.filter(p => p.status === 'new' || p.status === 'investigating' || !p.status).length}
                    </span>
                  )}
                </button>
                <button
                  onClick={() => setActiveTab('security')}
                  className={`${
                    activeTab === 'security'
                      ? isDark ? 'border-blue-400 text-blue-400' : 'border-blue-500 text-blue-600'
                      : isDark ? 'border-transparent text-gray-400 hover:text-gray-200 hover:border-gray-500' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                  } whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm flex items-center space-x-2`}
                >
                  <Shield className="w-5 h-5" />
                  <span>Security Scan</span>
                  {securityFindings.length > 0 && (
                    <span className={`ml-2 py-0.5 px-2.5 rounded-full text-xs font-medium ${isDark ? 'bg-orange-900 text-orange-200' : 'bg-orange-100 text-orange-800'}`}>
                      {securityFindings.length}
                    </span>
                  )}
                </button>
                <button
                  onClick={() => setActiveTab('cluster')}
                  className={`${
                    activeTab === 'cluster'
                      ? isDark ? 'border-blue-400 text-blue-400' : 'border-blue-500 text-blue-600'
                      : isDark ? 'border-transparent text-gray-400 hover:text-gray-200 hover:border-gray-500' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                  } ml-8 whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm flex items-center space-x-2`}
                >
                  <BarChart3 className="w-5 h-5" />
                  <span>Cluster Metrics</span>
                </button>
              </div>
              <button
                onClick={() => setActiveTab('admin')}
                className={`${
                  activeTab === 'admin'
                    ? isDark ? 'border-blue-400 text-blue-400' : 'border-blue-500 text-blue-600'
                    : isDark ? 'border-transparent text-gray-400 hover:text-gray-200 hover:border-gray-500' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                } whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm flex items-center space-x-2`}
              >
                <Settings className="w-5 h-5" />
                <span>Admin</span>
              </button>
            </nav>
          </div>
        </div>

        {/* Filters - hide on admin and cluster tabs */}
        {activeTab !== 'admin' && activeTab !== 'cluster' && (
        <div className="flex justify-end mb-4 gap-4">
          {/* Severity Filter - only show on security tab */}
          {activeTab === 'security' && (
            <div className="relative">
              <button
                onClick={() => setShowSeverityDropdown(!showSeverityDropdown)}
                className={`flex items-center space-x-2 px-3 py-2 text-sm border rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                  isDark
                    ? 'border-gray-600 bg-gray-800 hover:bg-gray-700 text-gray-200'
                    : 'border-gray-300 bg-white hover:bg-gray-50 text-gray-700'
                }`}
              >
                <Filter className={`w-4 h-4 ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
                <span>Severity</span>
                <span className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>({selectedSeverities.length}/{allSeverities.length})</span>
                <ChevronDown className={`w-4 h-4 transition-transform ${isDark ? 'text-gray-400' : 'text-gray-500'} ${showSeverityDropdown ? 'rotate-180' : ''}`} />
              </button>

              {showSeverityDropdown && (
                <div className={`absolute right-0 mt-2 w-48 rounded-md shadow-lg border z-10 ${
                  isDark ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'
                }`}>
                  <div className="py-1">
                    {allSeverities.map(severity => (
                      <label
                        key={severity}
                        className={`flex items-center px-4 py-2 cursor-pointer ${isDark ? 'hover:bg-gray-700' : 'hover:bg-gray-50'}`}
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
                  <div className={`border-t px-4 py-2 ${isDark ? 'border-gray-700' : 'border-gray-100'}`}>
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

          {/* Export - only show on security tab */}
          {activeTab === 'security' && sortedSecurityFindings.length > 0 && (
            <div className="relative">
              <button
                onClick={() => setShowExportDropdown(!showExportDropdown)}
                onBlur={() => setTimeout(() => setShowExportDropdown(false), 200)}
                className={`flex items-center space-x-2 px-3 py-2 text-sm border rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-purple-500 ${
                  isDark
                    ? 'border-gray-600 bg-gray-800 hover:bg-gray-700 text-gray-200'
                    : 'border-gray-300 bg-white hover:bg-gray-50 text-gray-700'
                }`}
              >
                <Download className={`w-4 h-4 ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
                <span>Export</span>
                <ChevronDown className={`w-4 h-4 transition-transform ${isDark ? 'text-gray-400' : 'text-gray-500'} ${showExportDropdown ? 'rotate-180' : ''}`} />
              </button>

              {showExportDropdown && (
                <div className={`absolute right-0 mt-2 w-40 rounded-md shadow-lg border z-10 ${
                  isDark ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'
                }`}>
                  <div className="py-1">
                    <button
                      onClick={() => { exportAsCSV(sortedSecurityFindings); setShowExportDropdown(false); }}
                      className={`w-full text-left px-4 py-2 text-sm ${isDark ? 'hover:bg-gray-700 text-gray-200' : 'hover:bg-gray-50 text-gray-700'}`}
                    >
                      CSV
                    </button>
                    <button
                      onClick={() => { exportAsJSON(sortedSecurityFindings); setShowExportDropdown(false); }}
                      className={`w-full text-left px-4 py-2 text-sm ${isDark ? 'hover:bg-gray-700 text-gray-200' : 'hover:bg-gray-50 text-gray-700'}`}
                    >
                      JSON
                    </button>
                    <button
                      onClick={() => { exportAsPDF(sortedSecurityFindings); setShowExportDropdown(false); }}
                      className={`w-full text-left px-4 py-2 text-sm ${isDark ? 'hover:bg-gray-700 text-gray-200' : 'hover:bg-gray-50 text-gray-700'}`}
                    >
                      PDF
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Namespace Filter - uses separate state per tab */}
          <div className="flex items-center space-x-2">
            <label htmlFor="namespace-filter" className={`text-sm font-medium ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
              Filter by namespace:
            </label>
            <input
              id="namespace-filter"
              type="text"
              value={activeTab === 'monitoring' ? podNamespaceFilter : securityNamespaceFilter}
              onChange={(e) => activeTab === 'monitoring'
                ? setPodNamespaceFilter(e.target.value)
                : setSecurityNamespaceFilter(e.target.value)
              }
              placeholder="Enter namespace"
              className={`block w-40 px-3 py-2 text-sm border rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 ${
                isDark
                  ? 'bg-gray-800 border-gray-600 text-gray-200 placeholder-gray-500'
                  : 'bg-white border-gray-300 text-gray-900 placeholder-gray-400'
              }`}
            />
          </div>
        </div>
        )}

        {/* Tab Content */}
        <div className={`${isDark ? 'bg-gray-800' : 'bg-white'} shadow rounded-lg`}>
          {activeTab === 'monitoring' && (
            <>
              {/* Pod sub-tabs */}
              <div className={`flex border-b ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
                <button
                  onClick={() => setPodSubTab('active')}
                  className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors flex items-center space-x-2 ${
                    podSubTab === 'active'
                      ? isDark ? 'border-blue-400 text-blue-400' : 'border-blue-500 text-blue-600'
                      : isDark ? 'border-transparent text-gray-400 hover:text-gray-200' : 'border-transparent text-gray-500 hover:text-gray-700'
                  }`}
                >
                  <Activity className="w-4 h-4" />
                  <span>Active</span>
                  {pods.length > 0 && (
                    <span className={`py-0.5 px-2 rounded-full text-xs font-medium ${isDark ? 'bg-red-900 text-red-200' : 'bg-red-100 text-red-800'}`}>
                      {pods.length}
                    </span>
                  )}
                </button>
                <button
                  onClick={() => setPodSubTab('history')}
                  className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors flex items-center space-x-2 ${
                    podSubTab === 'history'
                      ? isDark ? 'border-blue-400 text-blue-400' : 'border-blue-500 text-blue-600'
                      : isDark ? 'border-transparent text-gray-400 hover:text-gray-200' : 'border-transparent text-gray-500 hover:text-gray-700'
                  }`}
                >
                  <Clock className="w-4 h-4" />
                  <span>History</span>
                  {podHistory.length > 0 && (
                    <span className={`py-0.5 px-2 rounded-full text-xs font-medium ${isDark ? 'bg-green-900 text-green-200' : 'bg-green-100 text-green-800'}`}>
                      {podHistory.length}
                    </span>
                  )}
                </button>
                <button
                  onClick={() => setPodSubTab('ignored')}
                  className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors flex items-center space-x-2 ${
                    podSubTab === 'ignored'
                      ? isDark ? 'border-blue-400 text-blue-400' : 'border-blue-500 text-blue-600'
                      : isDark ? 'border-transparent text-gray-400 hover:text-gray-200' : 'border-transparent text-gray-500 hover:text-gray-700'
                  }`}
                >
                  <EyeOff className="w-4 h-4" />
                  <span>Ignored</span>
                  {ignoredPods.length > 0 && (
                    <span className={`py-0.5 px-2 rounded-full text-xs font-medium ${isDark ? 'bg-gray-600 text-gray-200' : 'bg-gray-200 text-gray-700'}`}>
                      {ignoredPods.length}
                    </span>
                  )}
                </button>
              </div>

              {/* Active sub-tab */}
              {podSubTab === 'active' && (
                <>
                  {filteredPods.length === 0 ? (
                    <div className="text-center py-12">
                      <CheckCircle className={`w-12 h-12 mx-auto mb-4 ${isDark ? 'text-green-400' : 'text-green-500'}`} />
                      <h3 className={`text-lg font-medium mb-2 ${isDark ? 'text-gray-100' : 'text-gray-900'}`}>
                        {pods.length === 0 ? 'All Good!' : 'No Failures Found'}
                      </h3>
                      <p className={isDark ? 'text-gray-400' : 'text-gray-600'}>
                        {pods.length === 0
                          ? 'No pod failures detected in your cluster.'
                          : podNamespaceFilter.trim() === ''
                            ? 'No pod failures found in your cluster.'
                            : `No pod failures found matching namespace '${podNamespaceFilter}'.`
                        }
                      </p>
                    </div>
                  ) : (
                    <PodTable pods={filteredPods} onSolutionUpdated={handleSolutionUpdated} onStatusChange={handleStatusChange} isDark={isDark} aiEnabled={aiEnabled} viewMode="active" />
                  )}
                </>
              )}

              {/* History sub-tab */}
              {podSubTab === 'history' && (
                <>
                  {filteredHistory.length === 0 ? (
                    <div className="text-center py-12">
                      <Clock className={`w-12 h-12 mx-auto mb-4 ${isDark ? 'text-gray-500' : 'text-gray-400'}`} />
                      <h3 className={`text-lg font-medium mb-2 ${isDark ? 'text-gray-100' : 'text-gray-900'}`}>
                        No Resolved Pods
                      </h3>
                      <p className={isDark ? 'text-gray-400' : 'text-gray-600'}>
                        Resolved pod failures will appear here.
                      </p>
                    </div>
                  ) : (
                    <PodTable pods={filteredHistory} onSolutionUpdated={handleSolutionUpdated} onStatusChange={handleStatusChange} onDeleteRecord={handleDeletePodRecord} isDark={isDark} aiEnabled={aiEnabled} viewMode="history" />
                  )}
                </>
              )}

              {/* Ignored sub-tab */}
              {podSubTab === 'ignored' && (
                <>
                  {filteredIgnored.length === 0 ? (
                    <div className="text-center py-12">
                      <EyeOff className={`w-12 h-12 mx-auto mb-4 ${isDark ? 'text-gray-500' : 'text-gray-400'}`} />
                      <h3 className={`text-lg font-medium mb-2 ${isDark ? 'text-gray-100' : 'text-gray-900'}`}>
                        No Ignored Pods
                      </h3>
                      <p className={isDark ? 'text-gray-400' : 'text-gray-600'}>
                        Ignored pod failures will appear here.
                      </p>
                    </div>
                  ) : (
                    <PodTable pods={filteredIgnored} onSolutionUpdated={handleSolutionUpdated} onStatusChange={handleStatusChange} onDeleteRecord={handleDeletePodRecord} isDark={isDark} aiEnabled={aiEnabled} viewMode="ignored" />
                  )}
                </>
              )}
            </>
          )}

          {activeTab === 'security' && (
            <>
              {sortedSecurityFindings.length === 0 ? (
                <div className="text-center py-12">
                  <Shield className={`w-12 h-12 mx-auto mb-4 ${isDark ? 'text-green-400' : 'text-green-500'}`} />
                  <h3 className={`text-lg font-medium mb-2 ${isDark ? 'text-gray-100' : 'text-gray-900'}`}>
                    {securityFindings.length === 0 ? 'No Security Issues!' : 'No Issues Found'}
                  </h3>
                  <p className={isDark ? 'text-gray-400' : 'text-gray-600'}>
                    {securityFindings.length === 0
                      ? 'No security issues detected in your cluster.'
                      : securityNamespaceFilter.trim() === ''
                        ? 'No security issues found in your cluster.'
                        : `No security issues found matching namespace '${securityNamespaceFilter}'.`
                    }
                  </p>
                </div>
              ) : (
                <SecurityTable findings={sortedSecurityFindings} isDark={isDark} />
              )}
            </>
          )}

          {activeTab === 'cluster' && (
            <MonitoringTab metrics={clusterMetrics} isDark={isDark} />
          )}

          {activeTab === 'admin' && (
            <AdminPanel isDark={isDark} />
          )}

        </div>
      </div>
    </div>
  );
};

export default Dashboard;
