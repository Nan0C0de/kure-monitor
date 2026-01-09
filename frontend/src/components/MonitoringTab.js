import React, { useState, useMemo, useCallback, useRef, useEffect } from 'react';
import { Server, Cpu, MemoryStick, HardDrive, Box, AlertTriangle, CheckCircle, ChevronDown, ChevronUp, Search, Loader2, FileText, RefreshCw, X, Play, Pause } from 'lucide-react';
import { api } from '../services/api';

const MonitoringTab = ({ metrics, isDark = false }) => {
  const [showPodsList, setShowPodsList] = useState(false);
  const [namespaceFilter, setNamespaceFilter] = useState('');
  const [expandedPod, setExpandedPod] = useState(null); // { namespace, name }
  const [podLogs, setPodLogs] = useState(null);
  const [logsLoading, setLogsLoading] = useState(false);
  const [logsError, setLogsError] = useState(null);
  const [selectedContainer, setSelectedContainer] = useState(null);
  const [tailLines, setTailLines] = useState(100);
  const [isLiveMode, setIsLiveMode] = useState(false);
  const [liveLogsBuffer, setLiveLogsBuffer] = useState([]);
  const eventSourceRef = useRef(null);
  const logsEndRef = useRef(null);

  // Cleanup EventSource on unmount or when pod changes
  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
    };
  }, []);

  // Auto-scroll to top when new live logs arrive (latest logs are at top)
  useEffect(() => {
    if (isLiveMode && logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [liveLogsBuffer, isLiveMode]);

  // Stop live logs when pod expansion changes
  useEffect(() => {
    if (!expandedPod && eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
      setIsLiveMode(false);
      setLiveLogsBuffer([]);
    }
  }, [expandedPod]);

  // Get unique namespaces for filter suggestions
  const namespaces = useMemo(() => {
    if (!metrics?.pods) return [];
    const ns = [...new Set(metrics.pods.map(p => p.namespace))];
    return ns.sort();
  }, [metrics?.pods]);

  // Filter pods by namespace
  const filteredPods = useMemo(() => {
    if (!metrics?.pods) return [];
    if (!namespaceFilter.trim()) return metrics.pods;
    return metrics.pods.filter(pod =>
      pod.namespace.toLowerCase().includes(namespaceFilter.toLowerCase())
    );
  }, [metrics?.pods, namespaceFilter]);

  // Fetch pod logs - must be defined before the useEffect that uses it
  const fetchPodLogs = useCallback(async (namespace, podName, container = null) => {
    setLogsLoading(true);
    setLogsError(null);
    try {
      const data = await api.getPodLogs(namespace, podName, {
        container: container,
        tailLines: tailLines
      });
      setPodLogs(data);
      if (!selectedContainer && data.containers?.length > 0) {
        setSelectedContainer(data.container);
      }
    } catch (err) {
      setLogsError(err.message || 'Failed to fetch logs');
      setPodLogs(null);
    } finally {
      setLogsLoading(false);
    }
  }, [tailLines, selectedContainer]);

  // Auto-refresh logs when tailLines changes (only if pod is expanded and not in live mode)
  const prevTailLinesRef = useRef(tailLines);
  useEffect(() => {
    if (expandedPod && !isLiveMode && prevTailLinesRef.current !== tailLines) {
      fetchPodLogs(expandedPod.namespace, expandedPod.name, selectedContainer);
    }
    prevTailLinesRef.current = tailLines;
  }, [tailLines, expandedPod, isLiveMode, selectedContainer, fetchPodLogs]);

  // Toggle pod expansion
  const togglePodExpansion = useCallback((pod) => {
    const podKey = `${pod.namespace}/${pod.name}`;
    const expandedKey = expandedPod ? `${expandedPod.namespace}/${expandedPod.name}` : null;

    if (expandedKey === podKey) {
      // Collapse
      setExpandedPod(null);
      setPodLogs(null);
      setLogsError(null);
      setSelectedContainer(null);
    } else {
      // Expand and fetch logs
      setExpandedPod({ namespace: pod.namespace, name: pod.name });
      setSelectedContainer(null);
      fetchPodLogs(pod.namespace, pod.name);
    }
  }, [expandedPod, fetchPodLogs]);

  // Refresh logs
  const refreshLogs = useCallback(() => {
    if (expandedPod) {
      fetchPodLogs(expandedPod.namespace, expandedPod.name, selectedContainer);
    }
  }, [expandedPod, selectedContainer, fetchPodLogs]);

  // Start live logs streaming
  const startLiveLogs = useCallback(() => {
    if (!expandedPod) return;

    // Stop any existing stream
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    const container = selectedContainer || (podLogs?.containers?.[0]);
    const streamUrl = api.getStreamingLogsUrl(expandedPod.namespace, expandedPod.name, {
      container: container,
      tailLines: tailLines
    });

    const eventSource = new EventSource(streamUrl);
    eventSourceRef.current = eventSource;

    // Clear buffer and start fresh
    setLiveLogsBuffer([]);
    setIsLiveMode(true);
    setLogsError(null);

    eventSource.onmessage = (event) => {
      setLiveLogsBuffer(prev => {
        // Keep last 2000 lines to prevent memory issues
        const newLogs = [...prev, event.data];
        if (newLogs.length > 2000) {
          return newLogs.slice(-2000);
        }
        return newLogs;
      });
    };

    eventSource.onerror = (error) => {
      console.error('EventSource error:', error);
      eventSource.close();
      eventSourceRef.current = null;
      setIsLiveMode(false);
      setLogsError('Live log stream disconnected');
    };
  }, [expandedPod, selectedContainer, podLogs, tailLines]);

  // Stop live logs streaming
  const stopLiveLogs = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    setIsLiveMode(false);
  }, []);

  // Handle container change
  const handleContainerChange = useCallback((container) => {
    setSelectedContainer(container);
    if (expandedPod) {
      fetchPodLogs(expandedPod.namespace, expandedPod.name, container);
    }
  }, [expandedPod, fetchPodLogs]);

  if (!metrics || !metrics.node_count) {
    return (
      <div className="p-6 space-y-6">
        {/* Loading Skeleton */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
          {[...Array(5)].map((_, i) => (
            <div key={i} className={`rounded-lg border p-4 animate-pulse ${isDark ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'}`}>
              <div className="flex items-center">
                <div className={`p-2 rounded-lg w-9 h-9 ${isDark ? 'bg-gray-700' : 'bg-gray-200'}`}></div>
                <div className="ml-3 flex-1">
                  <div className={`h-3 rounded w-16 mb-2 ${isDark ? 'bg-gray-700' : 'bg-gray-200'}`}></div>
                  <div className={`h-6 rounded w-12 ${isDark ? 'bg-gray-700' : 'bg-gray-200'}`}></div>
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Loading Spinner */}
        <div className={`rounded-lg border p-8 ${isDark ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'}`}>
          <div className="flex flex-col items-center justify-center">
            <Loader2 className="w-10 h-10 text-blue-500 animate-spin mb-4" />
            <span className={`font-medium ${isDark ? 'text-gray-200' : 'text-gray-700'}`}>Waiting for cluster metrics...</span>
            <p className={`text-sm mt-2 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>The agent will send metrics shortly</p>
          </div>
        </div>

        {/* Skeleton for Node Table */}
        <div className={`rounded-lg border overflow-hidden ${isDark ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'}`}>
          <div className={`px-4 py-3 border-b ${isDark ? 'border-gray-700 bg-gray-900' : 'border-gray-200 bg-gray-50'}`}>
            <div className={`h-4 rounded w-24 animate-pulse ${isDark ? 'bg-gray-700' : 'bg-gray-200'}`}></div>
          </div>
          <div className="p-4 space-y-3">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="flex items-center space-x-4 animate-pulse">
                <div className={`h-4 rounded w-32 ${isDark ? 'bg-gray-700' : 'bg-gray-200'}`}></div>
                <div className={`h-4 rounded w-16 ${isDark ? 'bg-gray-700' : 'bg-gray-200'}`}></div>
                <div className={`h-4 rounded w-20 ${isDark ? 'bg-gray-700' : 'bg-gray-200'}`}></div>
                <div className={`h-4 rounded w-20 ${isDark ? 'bg-gray-700' : 'bg-gray-200'}`}></div>
                <div className={`h-4 rounded w-12 ${isDark ? 'bg-gray-700' : 'bg-gray-200'}`}></div>
              </div>
            ))}
          </div>
        </div>

      </div>
    );
  }

  const getNodeStatus = (node) => {
    if (!node.conditions) return 'Unknown';
    const readyCondition = node.conditions.find(c => c.type === 'Ready');
    return readyCondition && readyCondition.status === 'True' ? 'Ready' : 'NotReady';
  };

  const getProgressColor = (percent) => {
    if (percent >= 90) return 'bg-red-500';
    if (percent >= 75) return 'bg-yellow-500';
    return 'bg-green-500';
  };

  const getPodStatusColor = (status, ready) => {
    if (status === 'Running' && ready) return 'bg-green-100 text-green-800';
    if (status === 'Running' && !ready) return 'bg-yellow-100 text-yellow-800';
    if (status === 'Pending') return 'bg-yellow-100 text-yellow-800';
    if (status === 'Succeeded') return 'bg-blue-100 text-blue-800';
    if (status === 'Failed') return 'bg-red-100 text-red-800';
    return 'bg-gray-100 text-gray-800';
  };

  const isPodExpanded = (pod) => {
    return expandedPod?.namespace === pod.namespace && expandedPod?.name === pod.name;
  };

  // Log viewer theme styles - use global isDark theme
  const logThemeStyles = isDark
    ? 'bg-gray-900 text-gray-100 border-gray-700'
    : 'bg-gray-50 text-gray-900 border-gray-300';

  const logHeaderStyles = isDark
    ? 'bg-gray-800 border-gray-700 text-gray-200'
    : 'bg-gray-100 border-gray-300 text-gray-700';

  return (
    <div className="p-6 space-y-6">
      {/* Metrics Server Warning */}
      {!metrics.metrics_available && (
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
          <div className="flex items-start">
            <AlertTriangle className="w-5 h-5 text-yellow-500 mr-3 mt-0.5" />
            <div>
              <h3 className="text-sm font-medium text-yellow-800">Metrics Server Not Installed</h3>
              <p className="text-sm text-yellow-700 mt-1">
                CPU and memory usage data is unavailable. Install metrics-server to see real-time resource usage.
              </p>
              <code className="block mt-2 text-xs bg-yellow-100 text-yellow-900 p-2 rounded">
                kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
              </code>
            </div>
          </div>
        </div>
      )}

      {/* Overview Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
        {/* Nodes */}
        <div className={`rounded-lg border p-4 ${isDark ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'}`}>
          <div className="flex items-center justify-between">
            <div className="flex items-center">
              <div className={`p-2 rounded-lg ${isDark ? 'bg-blue-900' : 'bg-blue-100'}`}>
                <Server className={`w-5 h-5 ${isDark ? 'text-blue-400' : 'text-blue-600'}`} />
              </div>
              <div className="ml-3">
                <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Nodes</p>
                <p className={`text-2xl font-semibold ${isDark ? 'text-gray-100' : 'text-gray-900'}`}>{metrics.node_count}</p>
              </div>
            </div>
          </div>
        </div>

        {/* CPU */}
        <div className={`rounded-lg border p-4 ${isDark ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'}`}>
          <div className="flex items-center">
            <div className={`p-2 rounded-lg ${isDark ? 'bg-purple-900' : 'bg-purple-100'}`}>
              <Cpu className={`w-5 h-5 ${isDark ? 'text-purple-400' : 'text-purple-600'}`} />
            </div>
            <div className="ml-3 flex-1">
              <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>CPU</p>
              {metrics.metrics_available && metrics.cpu_usage_percent !== null ? (
                <>
                  <p className={`text-lg font-semibold ${isDark ? 'text-gray-100' : 'text-gray-900'}`}>{metrics.cpu_usage_percent}%</p>
                  <div className={`w-full rounded-full h-1.5 mt-1 ${isDark ? 'bg-gray-700' : 'bg-gray-200'}`}>
                    <div
                      className={`h-1.5 rounded-full ${getProgressColor(metrics.cpu_usage_percent)}`}
                      style={{ width: `${Math.min(metrics.cpu_usage_percent, 100)}%` }}
                    ></div>
                  </div>
                  <p className="text-xs text-gray-400 mt-1">
                    {metrics.total_cpu_usage} / {metrics.total_cpu_allocatable}
                  </p>
                </>
              ) : (
                <p className={`text-lg font-semibold ${isDark ? 'text-gray-100' : 'text-gray-900'}`}>{metrics.total_cpu_allocatable}</p>
              )}
            </div>
          </div>
        </div>

        {/* Memory */}
        <div className={`rounded-lg border p-4 ${isDark ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'}`}>
          <div className="flex items-center">
            <div className={`p-2 rounded-lg ${isDark ? 'bg-green-900' : 'bg-green-100'}`}>
              <MemoryStick className={`w-5 h-5 ${isDark ? 'text-green-400' : 'text-green-600'}`} />
            </div>
            <div className="ml-3 flex-1">
              <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Memory</p>
              {metrics.metrics_available && metrics.memory_usage_percent !== null ? (
                <>
                  <p className={`text-lg font-semibold ${isDark ? 'text-gray-100' : 'text-gray-900'}`}>{metrics.memory_usage_percent}%</p>
                  <div className={`w-full rounded-full h-1.5 mt-1 ${isDark ? 'bg-gray-700' : 'bg-gray-200'}`}>
                    <div
                      className={`h-1.5 rounded-full ${getProgressColor(metrics.memory_usage_percent)}`}
                      style={{ width: `${Math.min(metrics.memory_usage_percent, 100)}%` }}
                    ></div>
                  </div>
                  <p className="text-xs text-gray-400 mt-1">
                    {metrics.total_memory_usage} / {metrics.total_memory_allocatable}
                  </p>
                </>
              ) : (
                <p className={`text-lg font-semibold ${isDark ? 'text-gray-100' : 'text-gray-900'}`}>{metrics.total_memory_allocatable}</p>
              )}
            </div>
          </div>
        </div>

        {/* Storage */}
        <div className={`rounded-lg border p-4 ${isDark ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'}`}>
          <div className="flex items-center">
            <div className={`p-2 rounded-lg ${isDark ? 'bg-cyan-900' : 'bg-cyan-100'}`}>
              <HardDrive className={`w-5 h-5 ${isDark ? 'text-cyan-400' : 'text-cyan-600'}`} />
            </div>
            <div className="ml-3 flex-1">
              <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Storage</p>
              {metrics.storage_usage_percent !== null ? (
                <>
                  <p className={`text-lg font-semibold ${isDark ? 'text-gray-100' : 'text-gray-900'}`}>{metrics.storage_usage_percent}%</p>
                  <div className={`w-full rounded-full h-1.5 mt-1 ${isDark ? 'bg-gray-700' : 'bg-gray-200'}`}>
                    <div
                      className={`h-1.5 rounded-full ${getProgressColor(metrics.storage_usage_percent)}`}
                      style={{ width: `${Math.min(metrics.storage_usage_percent, 100)}%` }}
                    ></div>
                  </div>
                  <p className="text-xs text-gray-400 mt-1">
                    {metrics.total_storage_used} / {metrics.total_storage_capacity}
                  </p>
                </>
              ) : metrics.total_storage_capacity ? (
                <p className={`text-lg font-semibold ${isDark ? 'text-gray-100' : 'text-gray-900'}`}>{metrics.total_storage_capacity}</p>
              ) : (
                <p className="text-sm text-gray-400">N/A</p>
              )}
            </div>
          </div>
        </div>

        {/* Pods - Clickable */}
        <button
          onClick={() => setShowPodsList(!showPodsList)}
          className={`rounded-lg border p-4 transition-colors text-left w-full ${isDark ? 'bg-gray-800 border-gray-700 hover:bg-gray-700' : 'bg-white border-gray-200 hover:bg-gray-50'}`}
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center">
              <div className={`p-2 rounded-lg ${isDark ? 'bg-orange-900' : 'bg-orange-100'}`}>
                <Box className={`w-5 h-5 ${isDark ? 'text-orange-400' : 'text-orange-600'}`} />
              </div>
              <div className="ml-3">
                <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Total Pods</p>
                <p className={`text-2xl font-semibold ${isDark ? 'text-gray-100' : 'text-gray-900'}`}>{metrics.total_pods || 0}</p>
              </div>
            </div>
            {showPodsList ? (
              <ChevronUp className={`w-5 h-5 ${isDark ? 'text-gray-500' : 'text-gray-400'}`} />
            ) : (
              <ChevronDown className={`w-5 h-5 ${isDark ? 'text-gray-500' : 'text-gray-400'}`} />
            )}
          </div>
          <p className="text-xs text-gray-400 mt-2">Click to {showPodsList ? 'hide' : 'view'} pod list</p>
        </button>
      </div>

      {/* Pods List */}
      {showPodsList && (
        <div className={`rounded-lg border overflow-hidden ${isDark ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'}`}>
          <div className={`px-4 py-3 border-b flex items-center justify-between ${isDark ? 'border-gray-700 bg-gray-900' : 'border-gray-200 bg-gray-50'}`}>
            <h3 className={`text-sm font-medium ${isDark ? 'text-gray-200' : 'text-gray-700'}`}>All Pods ({filteredPods.length})</h3>
            <div className="flex items-center space-x-2">
              <div className="relative">
                <Search className={`w-4 h-4 absolute left-3 top-1/2 transform -translate-y-1/2 ${isDark ? 'text-gray-500' : 'text-gray-400'}`} />
                <input
                  type="text"
                  placeholder="Filter by namespace..."
                  value={namespaceFilter}
                  onChange={(e) => setNamespaceFilter(e.target.value)}
                  className={`pl-9 pr-3 py-1.5 text-sm border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 w-48 ${isDark ? 'bg-gray-700 border-gray-600 text-gray-200 placeholder-gray-400' : 'bg-white border-gray-300 text-gray-900'}`}
                  list="namespace-suggestions"
                />
                <datalist id="namespace-suggestions">
                  {namespaces.map(ns => (
                    <option key={ns} value={ns} />
                  ))}
                </datalist>
              </div>
              {namespaceFilter && (
                <button
                  onClick={() => setNamespaceFilter('')}
                  className={`text-xs ${isDark ? 'text-gray-400 hover:text-gray-200' : 'text-gray-500 hover:text-gray-700'}`}
                >
                  Clear
                </button>
              )}
            </div>
          </div>
          <div className="overflow-x-auto max-h-[600px] overflow-y-auto">
            <table className={`min-w-full divide-y ${isDark ? 'divide-gray-700' : 'divide-gray-200'}`}>
              <thead className={`sticky top-0 z-10 ${isDark ? 'bg-gray-900' : 'bg-gray-50'}`}>
                <tr>
                  <th className={`px-4 py-3 text-left text-xs font-medium uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                    Pod
                  </th>
                  <th className={`px-4 py-3 text-left text-xs font-medium uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                    Namespace
                  </th>
                  <th className={`px-4 py-3 text-left text-xs font-medium uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                    Status
                  </th>
                  <th className={`px-4 py-3 text-left text-xs font-medium uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                    Node
                  </th>
                  <th className={`px-4 py-3 text-left text-xs font-medium uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                    Restarts
                  </th>
                  <th className={`px-4 py-3 text-left text-xs font-medium uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                    Logs
                  </th>
                </tr>
              </thead>
              <tbody className={`divide-y ${isDark ? 'bg-gray-800 divide-gray-700' : 'bg-white divide-gray-200'}`}>
                {filteredPods.map((pod, index) => (
                  <React.Fragment key={`${pod.namespace}-${pod.name}-${index}`}>
                    <tr
                      className={`cursor-pointer ${isPodExpanded(pod) ? (isDark ? 'bg-blue-900/30' : 'bg-blue-50') : ''} ${isDark ? 'hover:bg-gray-700' : 'hover:bg-gray-50'}`}
                      onClick={() => togglePodExpansion(pod)}
                    >
                      <td className="px-4 py-2 whitespace-nowrap">
                        <div className="flex items-center">
                          <Box className={`w-4 h-4 mr-2 ${isDark ? 'text-gray-500' : 'text-gray-400'}`} />
                          <span className={`text-sm font-medium ${isDark ? 'text-gray-200' : 'text-gray-900'}`}>{pod.name}</span>
                        </div>
                      </td>
                      <td className="px-4 py-2 whitespace-nowrap">
                        <span className={`text-sm px-2 py-0.5 rounded ${isDark ? 'text-gray-300 bg-gray-700' : 'text-gray-600 bg-gray-100'}`}>
                          {pod.namespace}
                        </span>
                      </td>
                      <td className="px-4 py-2 whitespace-nowrap">
                        <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${getPodStatusColor(pod.status, pod.ready)}`}>
                          {pod.ready && pod.status === 'Running' ? (
                            <CheckCircle className="w-3 h-3 mr-1" />
                          ) : null}
                          {pod.status}
                        </span>
                      </td>
                      <td className={`px-4 py-2 whitespace-nowrap text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                        {pod.node}
                      </td>
                      <td className={`px-4 py-2 whitespace-nowrap text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                        <span className={pod.restarts > 0 ? 'text-orange-500 font-medium' : ''}>
                          {pod.restarts}
                        </span>
                      </td>
                      <td className="px-4 py-2 whitespace-nowrap">
                        <div className={`flex items-center text-sm ${isDark ? 'text-blue-400' : 'text-blue-600'}`}>
                          <FileText className="w-4 h-4 mr-1" />
                          {isPodExpanded(pod) ? (
                            <ChevronUp className="w-4 h-4" />
                          ) : (
                            <ChevronDown className="w-4 h-4" />
                          )}
                        </div>
                      </td>
                    </tr>
                    {/* Expanded Log View */}
                    {isPodExpanded(pod) && (
                      <tr>
                        <td colSpan="6" className="px-0 py-0">
                          <div className={`m-2 rounded-lg border ${logThemeStyles}`}>
                            {/* Log Header */}
                            <div className={`px-4 py-2 border-b flex items-center justify-between ${logHeaderStyles}`}>
                              <div className="flex items-center space-x-4">
                                <span className="text-sm font-medium">
                                  <FileText className="w-4 h-4 inline mr-1" />
                                  Logs: {pod.name}
                                </span>
                                {/* Container Selector */}
                                {podLogs?.containers && podLogs.containers.length > 1 && (
                                  <select
                                    value={selectedContainer || ''}
                                    onChange={(e) => handleContainerChange(e.target.value)}
                                    disabled={isLiveMode}
                                    className={`text-xs px-2 py-1 rounded border ${
                                      isDark
                                        ? 'bg-gray-700 border-gray-600 text-gray-200'
                                        : 'bg-white border-gray-300 text-gray-700'
                                    } ${isLiveMode ? 'opacity-50 cursor-not-allowed' : ''}`}
                                  >
                                    {podLogs.containers.map(c => (
                                      <option key={c} value={c}>{c}</option>
                                    ))}
                                  </select>
                                )}
                                {/* Tail Lines Selector */}
                                <select
                                  value={tailLines}
                                  onChange={(e) => {
                                    setTailLines(Number(e.target.value));
                                  }}
                                  disabled={isLiveMode}
                                  className={`text-xs px-2 py-1 rounded border ${
                                    isDark
                                      ? 'bg-gray-700 border-gray-600 text-gray-200'
                                      : 'bg-white border-gray-300 text-gray-700'
                                  } ${isLiveMode ? 'opacity-50 cursor-not-allowed' : ''}`}
                                >
                                  <option value={50}>50 lines</option>
                                  <option value={100}>100 lines</option>
                                  <option value={500}>500 lines</option>
                                  <option value={1000}>1000 lines</option>
                                </select>
                                {/* Live mode indicator */}
                                {isLiveMode && (
                                  <span className="flex items-center text-xs text-green-500">
                                    <span className="w-2 h-2 bg-green-500 rounded-full mr-1 animate-pulse"></span>
                                    Live
                                  </span>
                                )}
                              </div>
                              <div className="flex items-center space-x-2">
                                {/* Live Logs Toggle Button */}
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    if (isLiveMode) {
                                      stopLiveLogs();
                                    } else {
                                      startLiveLogs();
                                    }
                                  }}
                                  className={`p-1 rounded flex items-center ${
                                    isLiveMode
                                      ? 'bg-red-500 text-white hover:bg-red-600'
                                      : 'bg-green-500 text-white hover:bg-green-600'
                                  }`}
                                  title={isLiveMode ? 'Stop live logs' : 'Start live logs'}
                                >
                                  {isLiveMode ? (
                                    <Pause className="w-4 h-4" />
                                  ) : (
                                    <Play className="w-4 h-4" />
                                  )}
                                </button>
                                {/* Refresh Button - disabled in live mode */}
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    refreshLogs();
                                  }}
                                  disabled={isLiveMode}
                                  className={`p-1 rounded hover:bg-opacity-20 hover:bg-gray-500 ${
                                    logsLoading ? 'animate-spin' : ''
                                  } ${isLiveMode ? 'opacity-50 cursor-not-allowed' : ''}`}
                                  title="Refresh logs"
                                >
                                  <RefreshCw className="w-4 h-4" />
                                </button>
                                {/* Close Button */}
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    stopLiveLogs();
                                    togglePodExpansion(pod);
                                  }}
                                  className="p-1 rounded hover:bg-opacity-20 hover:bg-gray-500"
                                  title="Close"
                                >
                                  <X className="w-4 h-4" />
                                </button>
                              </div>
                            </div>
                            {/* Log Content */}
                            <div className="p-4 max-h-80 overflow-auto">
                              {logsLoading && !isLiveMode ? (
                                <div className="flex items-center justify-center py-8">
                                  <Loader2 className="w-6 h-6 animate-spin mr-2" />
                                  <span>Loading logs...</span>
                                </div>
                              ) : logsError ? (
                                <div className="text-red-500 py-4 text-center">
                                  <AlertTriangle className="w-6 h-6 mx-auto mb-2" />
                                  <p>{logsError}</p>
                                </div>
                              ) : isLiveMode ? (
                                <pre className="text-xs font-mono whitespace-pre-wrap break-all">
                                  <div ref={logsEndRef} />
                                  {liveLogsBuffer.length > 0
                                    ? [...liveLogsBuffer].reverse().join('\n')
                                    : '[Waiting for logs...]'}
                                </pre>
                              ) : podLogs?.logs ? (
                                <pre className="text-xs font-mono whitespace-pre-wrap break-all">
                                  {podLogs.logs.split('\n').reverse().join('\n') || '[No logs available]'}
                                </pre>
                              ) : (
                                <p className="text-center py-4 text-gray-500">No logs available</p>
                              )}
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                ))}
                {filteredPods.length === 0 && (
                  <tr>
                    <td colSpan="6" className={`px-4 py-8 text-center ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                      {namespaceFilter ? `No pods found in namespace matching "${namespaceFilter}"` : 'No pods found'}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Node Details Table */}
      <div className={`rounded-lg border overflow-hidden ${isDark ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'}`}>
        <div className={`px-4 py-3 border-b ${isDark ? 'border-gray-700 bg-gray-900' : 'border-gray-200 bg-gray-50'}`}>
          <h3 className={`text-sm font-medium ${isDark ? 'text-gray-200' : 'text-gray-700'}`}>Node Details</h3>
        </div>
        <div className="overflow-x-auto">
          <table className={`min-w-full divide-y ${isDark ? 'divide-gray-700' : 'divide-gray-200'}`}>
            <thead className={isDark ? 'bg-gray-900' : 'bg-gray-50'}>
              <tr>
                <th className={`px-4 py-3 text-left text-xs font-medium uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                  Node
                </th>
                <th className={`px-4 py-3 text-left text-xs font-medium uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                  Status
                </th>
                <th className={`px-4 py-3 text-left text-xs font-medium uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                  CPU
                </th>
                <th className={`px-4 py-3 text-left text-xs font-medium uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                  Memory
                </th>
                <th className={`px-4 py-3 text-left text-xs font-medium uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                  Storage
                </th>
                <th className={`px-4 py-3 text-left text-xs font-medium uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                  Pods
                </th>
              </tr>
            </thead>
            <tbody className={`divide-y ${isDark ? 'bg-gray-800 divide-gray-700' : 'bg-white divide-gray-200'}`}>
              {metrics.nodes && metrics.nodes.map((node, index) => {
                const status = getNodeStatus(node);
                return (
                  <tr key={index} className={isDark ? 'hover:bg-gray-700' : 'hover:bg-gray-50'}>
                    <td className="px-4 py-3 whitespace-nowrap">
                      <div className="flex items-center">
                        <Server className={`w-4 h-4 mr-2 ${isDark ? 'text-gray-500' : 'text-gray-400'}`} />
                        <span className={`text-sm font-medium ${isDark ? 'text-gray-200' : 'text-gray-900'}`}>{node.name}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                        status === 'Ready'
                          ? 'bg-green-100 text-green-800'
                          : 'bg-red-100 text-red-800'
                      }`}>
                        {status === 'Ready' ? (
                          <CheckCircle className="w-3 h-3 mr-1" />
                        ) : (
                          <AlertTriangle className="w-3 h-3 mr-1" />
                        )}
                        {status}
                      </span>
                    </td>
                    <td className={`px-4 py-3 whitespace-nowrap text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                      {node.cpu_usage ? (
                        <span>{node.cpu_usage} / {node.cpu_allocatable}</span>
                      ) : (
                        <span>{node.cpu_allocatable}</span>
                      )}
                    </td>
                    <td className={`px-4 py-3 whitespace-nowrap text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                      {node.memory_usage ? (
                        <span>{node.memory_usage} / {node.memory_allocatable}</span>
                      ) : (
                        <span>{node.memory_allocatable}</span>
                      )}
                    </td>
                    <td className={`px-4 py-3 whitespace-nowrap text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                      {node.storage_used ? (
                        <span>{node.storage_used} / {node.storage_capacity}</span>
                      ) : node.storage_capacity ? (
                        <span>{node.storage_capacity}</span>
                      ) : (
                        <span className="text-gray-400">N/A</span>
                      )}
                    </td>
                    <td className={`px-4 py-3 whitespace-nowrap text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                      {node.pods_count || 0}
                    </td>
                  </tr>
                );
              })}
              {/* Show unassigned/pending pods if any */}
              {metrics.unassigned_pods > 0 && (
                <tr className={isDark ? 'bg-gray-900' : 'bg-gray-50'}>
                  <td className="px-4 py-3 whitespace-nowrap">
                    <div className="flex items-center">
                      <Box className={`w-4 h-4 mr-2 ${isDark ? 'text-yellow-500' : 'text-yellow-600'}`} />
                      <span className={`text-sm font-medium italic ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Unassigned (Pending)</span>
                    </div>
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-yellow-100 text-yellow-800">
                      <AlertTriangle className="w-3 h-3 mr-1" />
                      Pending
                    </span>
                  </td>
                  <td className={`px-4 py-3 whitespace-nowrap text-sm ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>-</td>
                  <td className={`px-4 py-3 whitespace-nowrap text-sm ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>-</td>
                  <td className={`px-4 py-3 whitespace-nowrap text-sm ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>-</td>
                  <td className={`px-4 py-3 whitespace-nowrap text-sm ${isDark ? 'text-yellow-400' : 'text-yellow-600'}`}>
                    {metrics.unassigned_pods}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Last Updated */}
      {metrics.timestamp && (
        <div className={`text-center text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
          Last updated: {new Date(metrics.timestamp).toLocaleString()}
        </div>
      )}
    </div>
  );
};

export default MonitoringTab;
