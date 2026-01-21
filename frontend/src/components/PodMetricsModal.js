import React, { useState, useEffect, useCallback } from 'react';
import { X, Cpu, MemoryStick, Loader2, AlertTriangle, Activity } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { api } from '../services/api';

const PodMetricsModal = ({ isOpen, onClose, pod, isDark = false }) => {
  const [metricsData, setMetricsData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchMetrics = useCallback(async () => {
    if (!pod) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api.getPodMetricsHistory(pod.namespace, pod.name);
      setMetricsData(data);
    } catch (err) {
      setError(err.message || 'Failed to fetch metrics');
    } finally {
      setLoading(false);
    }
  }, [pod]);

  useEffect(() => {
    if (isOpen && pod) {
      fetchMetrics();
    }
  }, [isOpen, pod, fetchMetrics]);

  if (!isOpen) return null;

  // Transform data for chart
  const chartData = metricsData?.history?.map((point, index) => ({
    index,
    time: new Date(point.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    cpu: point.cpu_millicores || 0,
    memory: point.memory_bytes ? Math.round(point.memory_bytes / (1024 * 1024)) : 0, // Convert to Mi
  })) || [];

  // Get current values
  const currentCpu = metricsData?.current_cpu || 'N/A';
  const currentMemory = metricsData?.current_memory || 'N/A';

  const bgColor = isDark ? 'bg-gray-800' : 'bg-white';
  const borderColor = isDark ? 'border-gray-700' : 'border-gray-200';
  const textColor = isDark ? 'text-gray-200' : 'text-gray-900';
  const textMuted = isDark ? 'text-gray-400' : 'text-gray-500';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black bg-opacity-50" onClick={onClose} />

      {/* Modal */}
      <div className={`relative w-full max-w-3xl max-h-[85vh] mx-4 rounded-lg shadow-xl overflow-hidden ${bgColor}`}>
        {/* Header */}
        <div className={`px-6 py-4 border-b ${borderColor} flex items-center justify-between`}>
          <div className="flex items-center space-x-3">
            <Activity className={`w-5 h-5 ${isDark ? 'text-blue-400' : 'text-blue-600'}`} />
            <div>
              <h3 className={`text-lg font-medium ${textColor}`}>Pod Metrics</h3>
              <p className={`text-sm ${textMuted}`}>{pod?.namespace}/{pod?.name}</p>
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
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className={`w-8 h-8 animate-spin mr-3 ${textMuted}`} />
              <span className={textMuted}>Loading metrics...</span>
            </div>
          ) : error ? (
            <div className="text-center py-12">
              <AlertTriangle className="w-12 h-12 mx-auto mb-4 text-red-500" />
              <p className="text-red-500">{error}</p>
              <button
                onClick={fetchMetrics}
                className="mt-4 px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
              >
                Retry
              </button>
            </div>
          ) : (
            <>
              {/* Current Usage Cards */}
              <div className="grid grid-cols-2 gap-4 mb-6">
                <div className={`p-4 rounded-lg border ${borderColor}`}>
                  <div className="flex items-center space-x-2 mb-2">
                    <Cpu className={`w-5 h-5 ${isDark ? 'text-purple-400' : 'text-purple-600'}`} />
                    <span className={`font-medium ${textColor}`}>CPU Usage</span>
                  </div>
                  <p className={`text-2xl font-bold ${textColor}`}>{currentCpu}</p>
                </div>
                <div className={`p-4 rounded-lg border ${borderColor}`}>
                  <div className="flex items-center space-x-2 mb-2">
                    <MemoryStick className={`w-5 h-5 ${isDark ? 'text-green-400' : 'text-green-600'}`} />
                    <span className={`font-medium ${textColor}`}>Memory Usage</span>
                  </div>
                  <p className={`text-2xl font-bold ${textColor}`}>{currentMemory}</p>
                </div>
              </div>

              {/* Chart */}
              {chartData.length > 0 ? (
                <div className={`p-4 rounded-lg border ${borderColor}`}>
                  <h4 className={`font-medium mb-4 ${textColor}`}>Usage History (Last {chartData.length} readings)</h4>
                  <ResponsiveContainer width="100%" height={300}>
                    <LineChart data={chartData}>
                      <CartesianGrid strokeDasharray="3 3" stroke={isDark ? '#374151' : '#e5e7eb'} />
                      <XAxis
                        dataKey="time"
                        stroke={isDark ? '#9ca3af' : '#6b7280'}
                        tick={{ fontSize: 12 }}
                      />
                      <YAxis
                        yAxisId="cpu"
                        orientation="left"
                        stroke={isDark ? '#a78bfa' : '#7c3aed'}
                        tick={{ fontSize: 12 }}
                        label={{ value: 'CPU (m)', angle: -90, position: 'insideLeft', style: { textAnchor: 'middle', fill: isDark ? '#a78bfa' : '#7c3aed' } }}
                      />
                      <YAxis
                        yAxisId="memory"
                        orientation="right"
                        stroke={isDark ? '#34d399' : '#059669'}
                        tick={{ fontSize: 12 }}
                        label={{ value: 'Memory (Mi)', angle: 90, position: 'insideRight', style: { textAnchor: 'middle', fill: isDark ? '#34d399' : '#059669' } }}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: isDark ? '#1f2937' : '#ffffff',
                          border: `1px solid ${isDark ? '#374151' : '#e5e7eb'}`,
                          borderRadius: '0.5rem'
                        }}
                        labelStyle={{ color: isDark ? '#f3f4f6' : '#111827' }}
                        formatter={(value, name) => {
                          if (name === 'CPU (millicores)') return [`${value}m`, 'CPU'];
                          if (name === 'Memory (Mi)') return [`${value} Mi`, 'Memory'];
                          return [value, name];
                        }}
                      />
                      <Legend />
                      <Line
                        yAxisId="cpu"
                        type="monotone"
                        dataKey="cpu"
                        stroke={isDark ? '#a78bfa' : '#7c3aed'}
                        name="CPU (millicores)"
                        dot={false}
                        strokeWidth={2}
                      />
                      <Line
                        yAxisId="memory"
                        type="monotone"
                        dataKey="memory"
                        stroke={isDark ? '#34d399' : '#059669'}
                        name="Memory (Mi)"
                        dot={false}
                        strokeWidth={2}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <div className={`p-8 text-center rounded-lg border ${borderColor}`}>
                  <Activity className={`w-12 h-12 mx-auto mb-4 ${textMuted}`} />
                  <p className={textMuted}>No historical data available yet.</p>
                  <p className={`text-sm mt-2 ${textMuted}`}>Metrics will appear after a few collection cycles.</p>
                </div>
              )}

              {/* Refresh button */}
              <div className="mt-4 flex justify-end">
                <button
                  onClick={fetchMetrics}
                  disabled={loading}
                  className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 flex items-center space-x-2"
                >
                  <Activity className="w-4 h-4" />
                  <span>Refresh</span>
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default PodMetricsModal;
