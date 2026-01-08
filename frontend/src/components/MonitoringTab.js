import React, { useState, useMemo } from 'react';
import { Server, Cpu, MemoryStick, HardDrive, Box, AlertTriangle, CheckCircle, ChevronDown, ChevronUp, Search, Loader2 } from 'lucide-react';

const MonitoringTab = ({ metrics }) => {
  const [showPodsList, setShowPodsList] = useState(false);
  const [namespaceFilter, setNamespaceFilter] = useState('');

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

  if (!metrics || !metrics.node_count) {
    return (
      <div className="p-6 space-y-6">
        {/* Loading Skeleton */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="bg-white rounded-lg border border-gray-200 p-4 animate-pulse">
              <div className="flex items-center">
                <div className="p-2 bg-gray-200 rounded-lg w-9 h-9"></div>
                <div className="ml-3 flex-1">
                  <div className="h-3 bg-gray-200 rounded w-16 mb-2"></div>
                  <div className="h-6 bg-gray-200 rounded w-12"></div>
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Loading Spinner */}
        <div className="bg-white rounded-lg border border-gray-200 p-8">
          <div className="flex flex-col items-center justify-center">
            <Loader2 className="w-10 h-10 text-blue-500 animate-spin mb-4" />
            <span className="text-gray-700 font-medium">Waiting for cluster metrics...</span>
            <p className="text-sm text-gray-500 mt-2">The agent will send metrics shortly</p>
          </div>
        </div>

        {/* Skeleton for Node Table */}
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-200 bg-gray-50">
            <div className="h-4 bg-gray-200 rounded w-24 animate-pulse"></div>
          </div>
          <div className="p-4 space-y-3">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="flex items-center space-x-4 animate-pulse">
                <div className="h-4 bg-gray-200 rounded w-32"></div>
                <div className="h-4 bg-gray-200 rounded w-16"></div>
                <div className="h-4 bg-gray-200 rounded w-20"></div>
                <div className="h-4 bg-gray-200 rounded w-20"></div>
                <div className="h-4 bg-gray-200 rounded w-12"></div>
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
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center">
              <div className="p-2 bg-blue-100 rounded-lg">
                <Server className="w-5 h-5 text-blue-600" />
              </div>
              <div className="ml-3">
                <p className="text-sm text-gray-500">Nodes</p>
                <p className="text-2xl font-semibold text-gray-900">{metrics.node_count}</p>
              </div>
            </div>
          </div>
        </div>

        {/* CPU */}
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <div className="flex items-center">
            <div className="p-2 bg-purple-100 rounded-lg">
              <Cpu className="w-5 h-5 text-purple-600" />
            </div>
            <div className="ml-3 flex-1">
              <p className="text-sm text-gray-500">CPU</p>
              {metrics.metrics_available && metrics.cpu_usage_percent !== null ? (
                <>
                  <p className="text-lg font-semibold text-gray-900">{metrics.cpu_usage_percent}%</p>
                  <div className="w-full bg-gray-200 rounded-full h-1.5 mt-1">
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
                <p className="text-lg font-semibold text-gray-900">{metrics.total_cpu_allocatable}</p>
              )}
            </div>
          </div>
        </div>

        {/* Memory */}
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <div className="flex items-center">
            <div className="p-2 bg-green-100 rounded-lg">
              <MemoryStick className="w-5 h-5 text-green-600" />
            </div>
            <div className="ml-3 flex-1">
              <p className="text-sm text-gray-500">Memory</p>
              {metrics.metrics_available && metrics.memory_usage_percent !== null ? (
                <>
                  <p className="text-lg font-semibold text-gray-900">{metrics.memory_usage_percent}%</p>
                  <div className="w-full bg-gray-200 rounded-full h-1.5 mt-1">
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
                <p className="text-lg font-semibold text-gray-900">{metrics.total_memory_allocatable}</p>
              )}
            </div>
          </div>
        </div>

        {/* Storage */}
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <div className="flex items-center">
            <div className="p-2 bg-cyan-100 rounded-lg">
              <HardDrive className="w-5 h-5 text-cyan-600" />
            </div>
            <div className="ml-3 flex-1">
              <p className="text-sm text-gray-500">Storage</p>
              {metrics.storage_usage_percent !== null ? (
                <>
                  <p className="text-lg font-semibold text-gray-900">{metrics.storage_usage_percent}%</p>
                  <div className="w-full bg-gray-200 rounded-full h-1.5 mt-1">
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
                <p className="text-lg font-semibold text-gray-900">{metrics.total_storage_capacity}</p>
              ) : (
                <p className="text-sm text-gray-400">N/A</p>
              )}
            </div>
          </div>
        </div>

        {/* Pods - Clickable */}
        <button
          onClick={() => setShowPodsList(!showPodsList)}
          className="bg-white rounded-lg border border-gray-200 p-4 hover:bg-gray-50 transition-colors text-left w-full"
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center">
              <div className="p-2 bg-orange-100 rounded-lg">
                <Box className="w-5 h-5 text-orange-600" />
              </div>
              <div className="ml-3">
                <p className="text-sm text-gray-500">Total Pods</p>
                <p className="text-2xl font-semibold text-gray-900">{metrics.total_pods || 0}</p>
              </div>
            </div>
            {showPodsList ? (
              <ChevronUp className="w-5 h-5 text-gray-400" />
            ) : (
              <ChevronDown className="w-5 h-5 text-gray-400" />
            )}
          </div>
          <p className="text-xs text-gray-400 mt-2">Click to {showPodsList ? 'hide' : 'view'} pod list</p>
        </button>
      </div>

      {/* Pods List */}
      {showPodsList && (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-200 bg-gray-50 flex items-center justify-between">
            <h3 className="text-sm font-medium text-gray-700">All Pods ({filteredPods.length})</h3>
            <div className="flex items-center space-x-2">
              <div className="relative">
                <Search className="w-4 h-4 absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400" />
                <input
                  type="text"
                  placeholder="Filter by namespace..."
                  value={namespaceFilter}
                  onChange={(e) => setNamespaceFilter(e.target.value)}
                  className="pl-9 pr-3 py-1.5 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 w-48"
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
                  className="text-xs text-gray-500 hover:text-gray-700"
                >
                  Clear
                </button>
              )}
            </div>
          </div>
          <div className="overflow-x-auto max-h-96 overflow-y-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50 sticky top-0">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Pod
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Namespace
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Status
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Node
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Restarts
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {filteredPods.map((pod, index) => (
                  <tr key={`${pod.namespace}-${pod.name}-${index}`} className="hover:bg-gray-50">
                    <td className="px-4 py-2 whitespace-nowrap">
                      <div className="flex items-center">
                        <Box className="w-4 h-4 text-gray-400 mr-2" />
                        <span className="text-sm font-medium text-gray-900">{pod.name}</span>
                      </div>
                    </td>
                    <td className="px-4 py-2 whitespace-nowrap">
                      <span className="text-sm text-gray-600 bg-gray-100 px-2 py-0.5 rounded">
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
                    <td className="px-4 py-2 whitespace-nowrap text-sm text-gray-600">
                      {pod.node}
                    </td>
                    <td className="px-4 py-2 whitespace-nowrap text-sm text-gray-600">
                      <span className={pod.restarts > 0 ? 'text-orange-600 font-medium' : ''}>
                        {pod.restarts}
                      </span>
                    </td>
                  </tr>
                ))}
                {filteredPods.length === 0 && (
                  <tr>
                    <td colSpan="5" className="px-4 py-8 text-center text-gray-500">
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
      <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-200 bg-gray-50">
          <h3 className="text-sm font-medium text-gray-700">Node Details</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Node
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Status
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  CPU
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Memory
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Storage
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Pods
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {metrics.nodes && metrics.nodes.map((node, index) => {
                const status = getNodeStatus(node);
                return (
                  <tr key={index} className="hover:bg-gray-50">
                    <td className="px-4 py-3 whitespace-nowrap">
                      <div className="flex items-center">
                        <Server className="w-4 h-4 text-gray-400 mr-2" />
                        <span className="text-sm font-medium text-gray-900">{node.name}</span>
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
                    <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-600">
                      {node.cpu_usage ? (
                        <span>{node.cpu_usage} / {node.cpu_allocatable}</span>
                      ) : (
                        <span>{node.cpu_allocatable}</span>
                      )}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-600">
                      {node.memory_usage ? (
                        <span>{node.memory_usage} / {node.memory_allocatable}</span>
                      ) : (
                        <span>{node.memory_allocatable}</span>
                      )}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-600">
                      {node.storage_used ? (
                        <span>{node.storage_used} / {node.storage_capacity}</span>
                      ) : node.storage_capacity ? (
                        <span>{node.storage_capacity}</span>
                      ) : (
                        <span className="text-gray-400">N/A</span>
                      )}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-600">
                      {node.pods_count || 0}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Last Updated */}
      {metrics.timestamp && (
        <div className="text-center text-xs text-gray-400">
          Last updated: {new Date(metrics.timestamp).toLocaleString()}
        </div>
      )}
    </div>
  );
};

export default MonitoringTab;
