import React, { useState, useEffect, useRef, useCallback } from 'react';
import { X, Loader2, AlertTriangle, Terminal, RotateCcw, Download, ArrowDown } from 'lucide-react';
import { api } from '../services/api';

const LINE_OPTIONS = [50, 100, 500, 1000, 2000];

const PodLogsModal = ({ isOpen, onClose, pod, isDark = false }) => {
  const [logs, setLogs] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [selectedContainer, setSelectedContainer] = useState('');
  const [showPrevious, setShowPrevious] = useState(false);
  const [tailLines, setTailLines] = useState(100);

  const logsContainerRef = useRef(null);

  // Get container names from pod
  const containers = pod?.container_statuses?.map(c => c.name) || [];

  // Set default container when pod changes
  useEffect(() => {
    if (containers.length > 0 && !selectedContainer) {
      setSelectedContainer(containers[0]);
    }
  }, [containers, selectedContainer]);

  // Fetch logs
  const fetchLogs = useCallback(async () => {
    if (!pod || !selectedContainer) return;

    setLoading(true);
    setError(null);

    try {
      const data = await api.getPodLogs(pod.namespace, pod.pod_name, {
        container: selectedContainer,
        tailLines: tailLines,
        previous: showPrevious
      });

      setLogs(data.logs || '');
    } catch (err) {
      setError(err.message || 'Failed to fetch logs');
      setLogs('');
    } finally {
      setLoading(false);
    }
  }, [pod, selectedContainer, tailLines, showPrevious]);

  // Load logs when modal opens or settings change
  useEffect(() => {
    if (isOpen && pod && selectedContainer) {
      fetchLogs();
    }
  }, [isOpen, pod, selectedContainer, tailLines, showPrevious, fetchLogs]);

  // Reset state when modal closes
  useEffect(() => {
    if (!isOpen) {
      setLogs('');
      setError(null);
    }
  }, [isOpen]);

  // Download logs
  const downloadLogs = () => {
    const blob = new Blob([logs], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${pod?.pod_name}-${selectedContainer}-logs.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  // Scroll to bottom
  const scrollToBottom = () => {
    if (logsContainerRef.current) {
      logsContainerRef.current.scrollTop = logsContainerRef.current.scrollHeight;
    }
  };

  if (!isOpen) return null;

  const bgColor = isDark ? 'bg-gray-800' : 'bg-white';
  const borderColor = isDark ? 'border-gray-700' : 'border-gray-200';
  const textColor = isDark ? 'text-gray-200' : 'text-gray-900';
  const textMuted = isDark ? 'text-gray-400' : 'text-gray-500';
  const logsBg = isDark ? 'bg-gray-900' : 'bg-gray-950';

  const logLines = logs.split('\n').filter(line => line.trim());

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black bg-opacity-50" onClick={onClose} />

      {/* Modal */}
      <div className={`relative w-full max-w-4xl max-h-[90vh] mx-4 rounded-lg shadow-xl overflow-hidden ${bgColor}`}>
        {/* Header */}
        <div className={`px-6 py-4 border-b ${borderColor} flex items-center justify-between`}>
          <div className="flex items-center space-x-3">
            <Terminal className={`w-5 h-5 ${isDark ? 'text-green-400' : 'text-green-600'}`} />
            <div>
              <h3 className={`text-lg font-medium ${textColor}`}>Pod Logs</h3>
              <p className={`text-sm ${textMuted}`}>{pod?.namespace}/{pod?.pod_name}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className={`p-2 rounded ${isDark ? 'hover:bg-gray-700' : 'hover:bg-gray-100'}`}
          >
            <X className={`w-5 h-5 ${textMuted}`} />
          </button>
        </div>

        {/* Controls */}
        <div className={`px-6 py-3 border-b ${borderColor} flex items-center justify-between flex-wrap gap-3`}>
          <div className="flex items-center space-x-3">
            {/* Container selector */}
            {containers.length > 1 && (
              <select
                value={selectedContainer}
                onChange={(e) => setSelectedContainer(e.target.value)}
                className={`px-3 py-1.5 rounded border text-sm ${
                  isDark
                    ? 'bg-gray-700 border-gray-600 text-gray-200'
                    : 'bg-white border-gray-300 text-gray-900'
                }`}
              >
                {containers.map(container => (
                  <option key={container} value={container}>{container}</option>
                ))}
              </select>
            )}

            {/* Lines selector */}
            <select
              value={tailLines}
              onChange={(e) => setTailLines(Number(e.target.value))}
              className={`px-3 py-1.5 rounded border text-sm ${
                isDark
                  ? 'bg-gray-700 border-gray-600 text-gray-200'
                  : 'bg-white border-gray-300 text-gray-900'
              }`}
            >
              {LINE_OPTIONS.map(num => (
                <option key={num} value={num}>Last {num} lines</option>
              ))}
            </select>

            {/* Previous logs toggle */}
            <label className={`flex items-center space-x-2 text-sm ${textMuted}`}>
              <input
                type="checkbox"
                checked={showPrevious}
                onChange={(e) => setShowPrevious(e.target.checked)}
                className="rounded"
              />
              <span>Previous container</span>
            </label>
          </div>

          <div className="flex items-center space-x-2">
            {/* Refresh button */}
            <button
              onClick={fetchLogs}
              disabled={loading}
              className={`inline-flex items-center px-3 py-1.5 rounded text-sm font-medium bg-blue-100 text-blue-800 hover:bg-blue-200 disabled:opacity-50`}
            >
              <RotateCcw className={`w-4 h-4 mr-1.5 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </button>

            {/* Download button */}
            <button
              onClick={downloadLogs}
              disabled={!logs}
              className={`p-1.5 rounded ${isDark ? 'hover:bg-gray-700' : 'hover:bg-gray-100'} disabled:opacity-50`}
              title="Download logs"
            >
              <Download className={`w-4 h-4 ${textMuted}`} />
            </button>

            {/* Scroll to bottom */}
            <button
              onClick={scrollToBottom}
              disabled={!logs}
              className={`p-1.5 rounded ${isDark ? 'hover:bg-gray-700' : 'hover:bg-gray-100'} disabled:opacity-50`}
              title="Scroll to bottom"
            >
              <ArrowDown className={`w-4 h-4 ${textMuted}`} />
            </button>
          </div>
        </div>

        {/* Logs content */}
        <div
          ref={logsContainerRef}
          className={`${logsBg} overflow-auto font-mono text-xs`}
          style={{ height: 'calc(90vh - 180px)', minHeight: '300px' }}
        >
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-6 h-6 animate-spin mr-3 text-gray-500" />
              <span className="text-gray-500">Loading logs...</span>
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <AlertTriangle className="w-10 h-10 mb-4 text-red-500" />
              <p className="text-red-500 mb-4">{error}</p>
              <button
                onClick={fetchLogs}
                className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
              >
                Retry
              </button>
            </div>
          ) : logLines.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <Terminal className="w-10 h-10 mb-4 text-gray-500" />
              <p className="text-gray-500">No logs available</p>
              <p className="text-gray-600 text-xs mt-2">
                {showPrevious
                  ? 'No previous container logs found.'
                  : 'The container may not have produced any output yet.'}
              </p>
            </div>
          ) : (
            <div className="p-4">
              {logLines.map((line, index) => (
                <div
                  key={index}
                  className="text-gray-300 leading-relaxed hover:bg-gray-800/50 py-0.5 whitespace-pre-wrap break-all"
                >
                  {line}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer with log count */}
        <div className={`px-6 py-2 border-t ${borderColor} flex items-center justify-between text-xs ${textMuted}`}>
          <span>{logLines.length} lines</span>
          {showPrevious && (
            <span className="text-yellow-500">Showing logs from previous container instance</span>
          )}
        </div>
      </div>
    </div>
  );
};

export default PodLogsModal;
