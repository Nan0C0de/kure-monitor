import React, { useState, useEffect, useRef, useCallback } from 'react';
import { X, Play, Pause, Loader2, AlertTriangle, Terminal, RotateCcw, Download, ArrowDown } from 'lucide-react';
import { api } from '../services/api';

const PodLogsModal = ({ isOpen, onClose, pod, isDark = false }) => {
  const [logs, setLogs] = useState([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState(null);
  const [selectedContainer, setSelectedContainer] = useState('');
  const [showPrevious, setShowPrevious] = useState(false);
  const [autoScroll, setAutoScroll] = useState(true);
  const [initialLoading, setInitialLoading] = useState(true);

  const logsContainerRef = useRef(null);
  const eventSourceRef = useRef(null);

  // Get container names from pod
  const containers = pod?.container_statuses?.map(c => c.name) || [];

  // Set default container when pod changes
  useEffect(() => {
    if (containers.length > 0 && !selectedContainer) {
      setSelectedContainer(containers[0]);
    }
  }, [containers, selectedContainer]);

  // Auto-scroll to bottom when new logs arrive
  useEffect(() => {
    if (autoScroll && logsContainerRef.current) {
      logsContainerRef.current.scrollTop = logsContainerRef.current.scrollHeight;
    }
  }, [logs, autoScroll]);

  // Cleanup EventSource on unmount or close
  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, []);

  // Stop streaming when modal closes
  useEffect(() => {
    if (!isOpen && eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
      setIsStreaming(false);
    }
  }, [isOpen]);

  // Fetch initial logs (non-streaming)
  const fetchInitialLogs = useCallback(async () => {
    if (!pod || !selectedContainer) return;

    setInitialLoading(true);
    setError(null);
    setLogs([]);

    try {
      const data = await api.getPodLogs(pod.namespace, pod.pod_name, {
        container: selectedContainer,
        tailLines: 100,
        previous: showPrevious
      });

      if (data.logs) {
        const logLines = data.logs.split('\n').filter(line => line.trim());
        setLogs(logLines.map((line, idx) => ({ id: idx, text: line, timestamp: Date.now() })));
      }
    } catch (err) {
      setError(err.message || 'Failed to fetch logs');
    } finally {
      setInitialLoading(false);
    }
  }, [pod, selectedContainer, showPrevious]);

  // Start streaming logs
  const startStreaming = useCallback(() => {
    if (!pod || !selectedContainer || eventSourceRef.current) return;

    setError(null);
    const url = api.getStreamingLogsUrl(pod.namespace, pod.pod_name, {
      container: selectedContainer,
      tailLines: 50
    });

    try {
      const eventSource = new EventSource(url);
      eventSourceRef.current = eventSource;

      eventSource.onopen = () => {
        setIsStreaming(true);
      };

      eventSource.onmessage = (event) => {
        const logLine = event.data;
        if (logLine && logLine.trim()) {
          setLogs(prev => [...prev, { id: Date.now() + Math.random(), text: logLine, timestamp: Date.now() }]);
        }
      };

      eventSource.onerror = (err) => {
        console.error('EventSource error:', err);
        if (eventSource.readyState === EventSource.CLOSED) {
          setIsStreaming(false);
          eventSourceRef.current = null;
        }
      };
    } catch (err) {
      setError('Failed to start log streaming');
      setIsStreaming(false);
    }
  }, [pod, selectedContainer]);

  // Stop streaming logs
  const stopStreaming = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
      setIsStreaming(false);
    }
  }, []);

  // Toggle streaming
  const toggleStreaming = () => {
    if (isStreaming) {
      stopStreaming();
    } else {
      startStreaming();
    }
  };

  // Load logs when modal opens or container changes
  useEffect(() => {
    if (isOpen && pod && selectedContainer) {
      fetchInitialLogs();
    }
  }, [isOpen, pod, selectedContainer, showPrevious, fetchInitialLogs]);

  // Download logs
  const downloadLogs = () => {
    const content = logs.map(l => l.text).join('\n');
    const blob = new Blob([content], { type: 'text/plain' });
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
      setAutoScroll(true);
    }
  };

  // Handle scroll to detect if user scrolled up
  const handleScroll = () => {
    if (logsContainerRef.current) {
      const { scrollTop, scrollHeight, clientHeight } = logsContainerRef.current;
      const isAtBottom = scrollHeight - scrollTop - clientHeight < 50;
      setAutoScroll(isAtBottom);
    }
  };

  if (!isOpen) return null;

  const bgColor = isDark ? 'bg-gray-800' : 'bg-white';
  const borderColor = isDark ? 'border-gray-700' : 'border-gray-200';
  const textColor = isDark ? 'text-gray-200' : 'text-gray-900';
  const textMuted = isDark ? 'text-gray-400' : 'text-gray-500';
  const logsBg = isDark ? 'bg-gray-900' : 'bg-gray-950';

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
              <h3 className={`text-lg font-medium ${textColor}`}>Live Logs</h3>
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
                onChange={(e) => {
                  stopStreaming();
                  setSelectedContainer(e.target.value);
                }}
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

            {/* Previous logs toggle */}
            <label className={`flex items-center space-x-2 text-sm ${textMuted}`}>
              <input
                type="checkbox"
                checked={showPrevious}
                onChange={(e) => {
                  stopStreaming();
                  setShowPrevious(e.target.checked);
                }}
                className="rounded"
              />
              <span>Previous container</span>
            </label>
          </div>

          <div className="flex items-center space-x-2">
            {/* Play/Pause button */}
            <button
              onClick={toggleStreaming}
              disabled={initialLoading || showPrevious}
              className={`inline-flex items-center px-3 py-1.5 rounded text-sm font-medium ${
                isStreaming
                  ? 'bg-yellow-100 text-yellow-800 hover:bg-yellow-200'
                  : 'bg-green-100 text-green-800 hover:bg-green-200'
              } disabled:opacity-50 disabled:cursor-not-allowed`}
              title={showPrevious ? 'Streaming not available for previous logs' : (isStreaming ? 'Pause' : 'Start streaming')}
            >
              {isStreaming ? (
                <>
                  <Pause className="w-4 h-4 mr-1.5" />
                  Pause
                </>
              ) : (
                <>
                  <Play className="w-4 h-4 mr-1.5" />
                  Stream
                </>
              )}
            </button>

            {/* Refresh button */}
            <button
              onClick={() => {
                stopStreaming();
                fetchInitialLogs();
              }}
              disabled={initialLoading}
              className={`p-1.5 rounded ${isDark ? 'hover:bg-gray-700' : 'hover:bg-gray-100'} disabled:opacity-50`}
              title="Refresh logs"
            >
              <RotateCcw className={`w-4 h-4 ${textMuted}`} />
            </button>

            {/* Download button */}
            <button
              onClick={downloadLogs}
              disabled={logs.length === 0}
              className={`p-1.5 rounded ${isDark ? 'hover:bg-gray-700' : 'hover:bg-gray-100'} disabled:opacity-50`}
              title="Download logs"
            >
              <Download className={`w-4 h-4 ${textMuted}`} />
            </button>

            {/* Scroll to bottom */}
            {!autoScroll && (
              <button
                onClick={scrollToBottom}
                className="inline-flex items-center px-2 py-1 rounded bg-blue-100 text-blue-800 text-xs hover:bg-blue-200"
                title="Scroll to bottom"
              >
                <ArrowDown className="w-3 h-3 mr-1" />
                Latest
              </button>
            )}
          </div>
        </div>

        {/* Streaming indicator */}
        {isStreaming && (
          <div className={`px-6 py-2 ${isDark ? 'bg-green-900/30' : 'bg-green-50'} border-b ${borderColor} flex items-center space-x-2`}>
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
            </span>
            <span className={`text-sm ${isDark ? 'text-green-400' : 'text-green-700'}`}>
              Streaming live logs...
            </span>
          </div>
        )}

        {/* Logs content */}
        <div
          ref={logsContainerRef}
          onScroll={handleScroll}
          className={`${logsBg} overflow-auto font-mono text-xs`}
          style={{ height: 'calc(90vh - 200px)', minHeight: '300px' }}
        >
          {initialLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-6 h-6 animate-spin mr-3 text-gray-500" />
              <span className="text-gray-500">Loading logs...</span>
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <AlertTriangle className="w-10 h-10 mb-4 text-red-500" />
              <p className="text-red-500 mb-4">{error}</p>
              <button
                onClick={fetchInitialLogs}
                className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
              >
                Retry
              </button>
            </div>
          ) : logs.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <Terminal className="w-10 h-10 mb-4 text-gray-500" />
              <p className="text-gray-500">No logs available</p>
              <p className="text-gray-600 text-xs mt-2">
                {showPrevious
                  ? 'No previous container logs found. The container may not have crashed yet.'
                  : 'The container may not have started or produced any output yet.'}
              </p>
            </div>
          ) : (
            <div className="p-4">
              {logs.map((log) => (
                <div
                  key={log.id}
                  className="text-gray-300 leading-relaxed hover:bg-gray-800/50 py-0.5 whitespace-pre-wrap break-all"
                >
                  {log.text}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer with log count */}
        <div className={`px-6 py-2 border-t ${borderColor} flex items-center justify-between text-xs ${textMuted}`}>
          <span>{logs.length} log lines</span>
          {showPrevious && (
            <span className="text-yellow-500">Showing logs from previous container instance</span>
          )}
        </div>
      </div>
    </div>
  );
};

export default PodLogsModal;
