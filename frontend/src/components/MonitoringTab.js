import React from 'react';
import { Server, Cpu, HardDrive, Box, AlertTriangle, CheckCircle, Clock } from 'lucide-react';

const MonitoringTab = ({ metrics }) => {
  if (!metrics || !metrics.node_count) {
    return (
      <div className="p-6">
        <div className="flex items-center justify-center py-12 text-gray-500">
          <Clock className="w-5 h-5 mr-2 animate-pulse" />
          <span>Waiting for cluster metrics...</span>
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
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
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
              <HardDrive className="w-5 h-5 text-green-600" />
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

        {/* Pods */}
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <div className="flex items-center">
            <div className="p-2 bg-orange-100 rounded-lg">
              <Box className="w-5 h-5 text-orange-600" />
            </div>
            <div className="ml-3">
              <p className="text-sm text-gray-500">Total Pods</p>
              <p className="text-2xl font-semibold text-gray-900">{metrics.total_pods || 0}</p>
            </div>
          </div>
        </div>
      </div>

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
