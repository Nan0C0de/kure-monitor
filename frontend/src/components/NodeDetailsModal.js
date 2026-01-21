import React from 'react';
import { X, Server, Cpu, MemoryStick, HardDrive, CheckCircle, AlertTriangle, AlertCircle, Box } from 'lucide-react';

const NodeDetailsModal = ({ isOpen, onClose, node, isDark = false }) => {
  if (!isOpen || !node) return null;

  const bgColor = isDark ? 'bg-gray-800' : 'bg-white';
  const borderColor = isDark ? 'border-gray-700' : 'border-gray-200';
  const textColor = isDark ? 'text-gray-200' : 'text-gray-900';
  const textMuted = isDark ? 'text-gray-400' : 'text-gray-500';
  const cardBg = isDark ? 'bg-gray-900' : 'bg-gray-50';

  // Parse numeric value from formatted string (e.g., "1.5 cores" -> 1.5, "256Mi" -> 256)
  const parseValue = (str) => {
    if (!str) return 0;
    const num = parseFloat(str);
    return isNaN(num) ? 0 : num;
  };

  // Get progress bar color based on percentage
  const getProgressColor = (percent) => {
    if (percent >= 90) return 'bg-red-500';
    if (percent >= 75) return 'bg-yellow-500';
    return 'bg-green-500';
  };

  // Get condition icon based on type and status
  const getConditionIcon = (condition) => {
    const isHealthy = (condition.type === 'Ready' && condition.status === 'True') ||
                      (condition.type !== 'Ready' && condition.status === 'False');

    if (isHealthy) {
      return <CheckCircle className="w-4 h-4 text-green-500" />;
    } else if (condition.type === 'Ready') {
      return <AlertTriangle className="w-4 h-4 text-red-500" />;
    } else {
      return <AlertCircle className="w-4 h-4 text-yellow-500" />;
    }
  };

  // Get condition status text
  const getConditionStatus = (condition) => {
    const isHealthy = (condition.type === 'Ready' && condition.status === 'True') ||
                      (condition.type !== 'Ready' && condition.status === 'False');
    return isHealthy ? 'Healthy' : 'Issue';
  };

  // Progress bar component
  const ProgressBar = ({ label, icon: Icon, iconColor, usage, capacity, percent }) => (
    <div className={`p-4 rounded-lg ${cardBg}`}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center space-x-2">
          <Icon className={`w-5 h-5 ${iconColor}`} />
          <span className={`font-medium ${textColor}`}>{label}</span>
        </div>
        <span className={`text-lg font-bold ${textColor}`}>
          {percent !== null ? `${percent}%` : 'N/A'}
        </span>
      </div>
      {percent !== null && (
        <div className={`w-full h-3 rounded-full ${isDark ? 'bg-gray-700' : 'bg-gray-200'}`}>
          <div
            className={`h-3 rounded-full ${getProgressColor(percent)} transition-all`}
            style={{ width: `${Math.min(percent, 100)}%` }}
          />
        </div>
      )}
      <p className={`text-sm mt-2 ${textMuted}`}>
        {usage || 'N/A'} / {capacity || 'N/A'}
      </p>
    </div>
  );

  // Calculate CPU percentage
  // The values come as formatted strings like "150m", "1.5 cores", etc.
  const cpuUsageStr = node.cpu_usage;
  const cpuAllocStr = node.cpu_allocatable;

  // Convert to millicores for comparison
  const cpuUsageMilli = cpuUsageStr?.includes('cores')
    ? parseValue(cpuUsageStr) * 1000
    : parseValue(cpuUsageStr);
  const cpuAllocMilli = cpuAllocStr?.includes('cores')
    ? parseValue(cpuAllocStr) * 1000
    : parseValue(cpuAllocStr);

  const cpuPercent = cpuAllocMilli > 0 && cpuUsageMilli > 0
    ? Math.round((cpuUsageMilli / cpuAllocMilli) * 100)
    : null;

  // Calculate Memory percentage
  // Memory values come as formatted strings like "1.5 Gi", "256 Mi", etc.
  const memUsageStr = node.memory_usage;
  const memAllocStr = node.memory_allocatable;

  // Convert to bytes for comparison
  const getMemoryBytes = (str) => {
    if (!str) return 0;
    const num = parseValue(str);
    if (str.includes('Gi')) return num * 1024 * 1024 * 1024;
    if (str.includes('Mi')) return num * 1024 * 1024;
    if (str.includes('Ki')) return num * 1024;
    return num;
  };

  const memUsageBytes = getMemoryBytes(memUsageStr);
  const memAllocBytes = getMemoryBytes(memAllocStr);

  const memPercent = memAllocBytes > 0 && memUsageBytes > 0
    ? Math.round((memUsageBytes / memAllocBytes) * 100)
    : null;

  // Calculate Storage percentage
  const storUsageStr = node.storage_used;
  const storCapStr = node.storage_capacity;

  const storUsageBytes = getMemoryBytes(storUsageStr);
  const storCapBytes = getMemoryBytes(storCapStr);

  const storPercent = storCapBytes > 0 && storUsageBytes > 0
    ? Math.round((storUsageBytes / storCapBytes) * 100)
    : null;

  // Get node ready status
  const readyCondition = node.conditions?.find(c => c.type === 'Ready');
  const isReady = readyCondition?.status === 'True';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black bg-opacity-50" onClick={onClose} />

      {/* Modal */}
      <div className={`relative w-full max-w-2xl max-h-[85vh] mx-4 rounded-lg shadow-xl overflow-hidden ${bgColor}`}>
        {/* Header */}
        <div className={`px-6 py-4 border-b ${borderColor} flex items-center justify-between`}>
          <div className="flex items-center space-x-3">
            <Server className={`w-5 h-5 ${isDark ? 'text-blue-400' : 'text-blue-600'}`} />
            <div>
              <h3 className={`text-lg font-medium ${textColor}`}>Node Details</h3>
              <div className="flex items-center space-x-2">
                <p className={`text-sm ${textMuted}`}>{node.name}</p>
                <span className={`px-2 py-0.5 text-xs rounded-full ${isReady ? 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200' : 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200'}`}>
                  {isReady ? 'Ready' : 'Not Ready'}
                </span>
              </div>
            </div>
          </div>
          <button
            onClick={onClose}
            className={`p-2 rounded ${isDark ? 'hover:bg-gray-700' : 'hover:bg-gray-100'}`}
          >
            <X className={`w-5 h-5 ${textMuted}`} />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 overflow-auto" style={{ maxHeight: 'calc(85vh - 80px)' }}>
          {/* Resource Usage */}
          <h4 className={`font-medium mb-4 ${textColor}`}>Resource Usage</h4>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            <ProgressBar
              label="CPU"
              icon={Cpu}
              iconColor={isDark ? 'text-purple-400' : 'text-purple-600'}
              usage={node.cpu_usage}
              capacity={node.cpu_allocatable}
              percent={cpuPercent}
            />
            <ProgressBar
              label="Memory"
              icon={MemoryStick}
              iconColor={isDark ? 'text-green-400' : 'text-green-600'}
              usage={node.memory_usage}
              capacity={node.memory_allocatable}
              percent={memPercent}
            />
            <ProgressBar
              label="Storage"
              icon={HardDrive}
              iconColor={isDark ? 'text-cyan-400' : 'text-cyan-600'}
              usage={node.storage_used}
              capacity={node.storage_capacity}
              percent={storPercent}
            />
          </div>

          {/* Node Conditions */}
          <h4 className={`font-medium mb-4 ${textColor}`}>Node Conditions</h4>
          <div className={`rounded-lg border ${borderColor} overflow-hidden mb-6`}>
            <table className="min-w-full">
              <thead className={cardBg}>
                <tr>
                  <th className={`px-4 py-3 text-left text-xs font-medium uppercase ${textMuted}`}>Condition</th>
                  <th className={`px-4 py-3 text-left text-xs font-medium uppercase ${textMuted}`}>Status</th>
                  <th className={`px-4 py-3 text-left text-xs font-medium uppercase ${textMuted}`}>Reason</th>
                </tr>
              </thead>
              <tbody className={`divide-y ${isDark ? 'divide-gray-700' : 'divide-gray-200'}`}>
                {node.conditions?.map((condition, idx) => (
                  <tr key={idx}>
                    <td className={`px-4 py-3 ${textColor}`}>
                      <div className="flex items-center space-x-2">
                        {getConditionIcon(condition)}
                        <span>{condition.type}</span>
                      </div>
                    </td>
                    <td className={`px-4 py-3 ${textMuted}`}>{getConditionStatus(condition)}</td>
                    <td className={`px-4 py-3 text-sm ${textMuted}`}>{condition.reason || '-'}</td>
                  </tr>
                ))}
                {(!node.conditions || node.conditions.length === 0) && (
                  <tr>
                    <td colSpan="3" className={`px-4 py-6 text-center ${textMuted}`}>
                      No condition information available
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {/* Pods Count */}
          <div className={`p-4 rounded-lg ${cardBg} flex items-center justify-between`}>
            <div className="flex items-center space-x-2">
              <Box className={`w-5 h-5 ${isDark ? 'text-blue-400' : 'text-blue-600'}`} />
              <span className={textColor}>Running Pods</span>
            </div>
            <span className={`text-xl font-bold ${textColor}`}>{node.pods_count || 0}</span>
          </div>
        </div>

        {/* Footer */}
        <div className={`px-6 py-4 border-t ${borderColor} flex justify-end`}>
          <button
            onClick={onClose}
            className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};

export default NodeDetailsModal;
