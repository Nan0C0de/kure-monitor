import React, { useState, useEffect, useRef } from 'react';
import { FileText, RefreshCw, Terminal, Search, CheckCircle, EyeOff, RotateCcw, Clock, Trash2, FlaskConical } from 'lucide-react';
import SolutionMarkdown from './SolutionMarkdown';
import TroubleshootSection from './TroubleshootSection';
import { api } from '../services/api';

const MirrorPhaseIndicator = ({ phase }) => {
  if (!phase) return null;
  const lower = phase.toLowerCase();
  if (lower === 'running' || lower === 'succeeded') {
    return <span className="inline-block w-2.5 h-2.5 rounded-full bg-green-500" title="Running" />;
  }
  if (lower === 'pending') {
    return <span className="inline-block w-2.5 h-2.5 rounded-full bg-yellow-500 animate-pulse" title="Pending" />;
  }
  return <span className="inline-block w-2.5 h-2.5 rounded-full bg-red-500" title="Failed" />;
};

const formatCountdown = (expiresAt) => {
  if (!expiresAt) return '--:--';
  const remaining = Math.max(0, Math.floor((new Date(expiresAt) - Date.now()) / 1000));
  const minutes = Math.floor(remaining / 60);
  const seconds = remaining % 60;
  return `${minutes}:${String(seconds).padStart(2, '0')}`;
};

const MirrorPodStatus = ({ mirror, onDelete, onRefresh, isDark = false }) => {
  const [timeRemaining, setTimeRemaining] = useState(() => formatCountdown(mirror?.expires_at));
  const [isDeleting, setIsDeleting] = useState(false);
  const countdownRef = useRef(null);

  useEffect(() => {
    if (!mirror?.expires_at) return;

    setTimeRemaining(formatCountdown(mirror.expires_at));

    countdownRef.current = setInterval(() => {
      const remaining = Math.max(0, Math.floor((new Date(mirror.expires_at) - Date.now()) / 1000));
      setTimeRemaining(formatCountdown(mirror.expires_at));
      if (remaining <= 0) {
        clearInterval(countdownRef.current);
        // Mirror expired, refresh to check if it's gone
        if (onRefresh) onRefresh();
      }
    }, 1000);

    return () => {
      if (countdownRef.current) clearInterval(countdownRef.current);
    };
  }, [mirror?.expires_at, onRefresh]);

  const handleDelete = async () => {
    if (!mirror?.mirror_id) return;
    setIsDeleting(true);
    try {
      await onDelete(mirror.mirror_id);
    } catch {
      setIsDeleting(false);
    }
  };

  if (!mirror) return null;

  const phase = mirror.phase || 'Pending';

  return (
    <div className={`border-2 rounded-lg p-4 ${isDark ? 'border-purple-700 bg-purple-900/30' : 'border-purple-300 bg-purple-50'}`}>
      <div className="flex items-center mb-3">
        <FlaskConical className={`w-4 h-4 mr-2 ${isDark ? 'text-purple-400' : 'text-purple-600'}`} />
        <h4 className={`text-sm font-semibold ${isDark ? 'text-purple-200' : 'text-purple-900'}`}>Mirror Pod Active</h4>
      </div>
      <div className="space-y-2 text-sm">
        <div className="flex items-center justify-between">
          <span className={`font-medium ${isDark ? 'text-purple-300' : 'text-purple-800'}`}>Name:</span>
          <span className={`font-mono text-xs truncate ml-2 max-w-xs ${isDark ? 'text-purple-200' : 'text-purple-900'}`}>{mirror.mirror_pod_name}</span>
        </div>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className={`font-medium ${isDark ? 'text-purple-300' : 'text-purple-800'}`}>Phase:</span>
            <span className={isDark ? 'text-purple-200' : 'text-purple-900'}>{phase}</span>
            <MirrorPhaseIndicator phase={phase} />
          </div>
          <div className={`flex items-center gap-1 ${isDark ? 'text-purple-300' : 'text-purple-800'}`}>
            <Clock className={`w-3.5 h-3.5 ${isDark ? 'text-purple-500' : 'text-purple-400'}`} />
            <span className="font-medium">Expires:</span>
            <span className={`font-mono text-xs ${isDark ? 'text-purple-200' : 'text-purple-900'}`}>{timeRemaining}</span>
          </div>
        </div>
      </div>
      <div className="flex justify-end mt-3">
        <button
          onClick={handleDelete}
          disabled={isDeleting}
          className={`inline-flex items-center px-3 py-1.5 text-xs font-medium rounded-md disabled:opacity-50 ${isDark ? 'text-red-300 bg-red-900/40 border border-red-700 hover:bg-red-900/60' : 'text-red-700 bg-red-50 border border-red-300 hover:bg-red-100'}`}
        >
          <Trash2 className="w-3.5 h-3.5 mr-1" />
          {isDeleting ? 'Deleting...' : 'Delete Mirror'}
        </button>
      </div>
    </div>
  );
};

const PodDetails = ({ pod, onViewManifest, onViewLogs, onTestFix, onSolutionUpdated, onLogAwareSolutionUpdated, onStatusChange, onDeleteRecord, isDark = false, aiEnabled = false, viewMode = 'active', activeMirror, onDeleteMirror, onRefreshMirror }) => {
  const [isRetrying, setIsRetrying] = useState(false);
  const [isUpdatingStatus, setIsUpdatingStatus] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const hasAutoTriggered = useRef(false);

  // Check if solution is a fallback (AI unavailable)
  const isFallbackSolution = pod.solution && (
    pod.solution.includes('AI solution temporarily unavailable') ||
    pod.solution.includes('Failed to generate AI solution') ||
    pod.solution.includes('Basic troubleshooting')
  );

  const handleRetrySolution = async () => {
    setIsRetrying(true);
    try {
      const updatedPod = await api.retrySolution(pod.id);
      if (onSolutionUpdated) {
        onSolutionUpdated(updatedPod);
      }
    } catch (error) {
      console.error('Failed to retry solution:', error);
    } finally {
      setIsRetrying(false);
    }
  };

  // Auto-trigger AI generation when expanded with a fallback solution
  useEffect(() => {
    if (isFallbackSolution && aiEnabled && !hasAutoTriggered.current) {
      hasAutoTriggered.current = true;
      handleRetrySolution();
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleStatusAction = async (newStatus) => {
    if (!onStatusChange) return;
    setIsUpdatingStatus(true);
    try {
      await onStatusChange(pod.id, newStatus);
    } finally {
      setIsUpdatingStatus(false);
    }
  };

  const handleDelete = async () => {
    if (!onDeleteRecord) return;
    setIsDeleting(true);
    try {
      await onDeleteRecord(pod.id);
    } finally {
      setIsDeleting(false);
    }
  };

  const formatTimestamp = (timestamp) => {
    return new Date(timestamp).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  // Get error message from various sources
  const getErrorMessage = () => {
    // Primary: pod failure message
    if (pod.failure_message && pod.failure_message.trim()) {
      return pod.failure_message;
    }
    
    // Fallback: container status message
    if (pod.container_statuses) {
      for (const container of pod.container_statuses) {
        if (container.message && container.message.trim()) {
          return container.message;
        }
      }
    }
    
    // Fallback: recent warning events
    if (pod.events) {
      const warningEvents = pod.events.filter(e => e.type === 'Warning' && e.message);
      if (warningEvents.length > 0) {
        return warningEvents[0].message;
      }
    }
    
    // Last resort: generic message
    return `Pod is in ${pod.failure_reason} state. Check events and container statuses for more details.`;
  };

  return (
    <div className="space-y-4 overflow-hidden w-full">
      {/* Pod Details */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <h4 className={`font-medium mb-2 ${isDark ? 'text-gray-100' : 'text-gray-900'}`}>Pod Details</h4>
          <dl className="space-y-1 text-sm">
            <div className="flex">
              <dt className={`font-medium w-24 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Node:</dt>
              <dd className={isDark ? 'text-gray-200' : 'text-gray-900'}>{pod.node_name || 'N/A'}</dd>
            </div>
            <div className="flex">
              <dt className={`font-medium w-24 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Phase:</dt>
              <dd className={isDark ? 'text-gray-200' : 'text-gray-900'}>{pod.phase}</dd>
            </div>
            <div className="flex">
              <dt className={`font-medium w-24 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Created:</dt>
              <dd className={isDark ? 'text-gray-200' : 'text-gray-900'}>{formatTimestamp(pod.creation_timestamp)}</dd>
            </div>
          </dl>
        </div>
        <div>
          <h4 className={`font-medium mb-2 ${isDark ? 'text-gray-100' : 'text-gray-900'}`}>Error Details</h4>
          <dl className="space-y-1 text-sm">
            <div className="flex">
              <dt className={`font-medium w-24 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Reason:</dt>
              <dd className={isDark ? 'text-gray-200' : 'text-gray-900'}>{pod.failure_reason}</dd>
            </div>
            <div>
              <dt className={`font-medium ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Message:</dt>
              <dd className={`text-xs p-2 rounded mt-1 break-words ${isDark ? 'text-gray-200 bg-gray-800' : 'text-gray-900 bg-gray-100'}`}>
                {getErrorMessage()}
              </dd>
            </div>
          </dl>
        </div>
      </div>

      {/* Container Statuses */}
      {pod.container_statuses && pod.container_statuses.length > 0 && (
        <div>
          <h4 className={`font-medium mb-2 ${isDark ? 'text-gray-100' : 'text-gray-900'}`}>Container Status</h4>
          <div className="overflow-x-auto">
            <table className={`min-w-full text-sm ${isDark ? 'text-gray-300' : ''}`}>
              <thead>
                <tr className={isDark ? 'bg-gray-800' : 'bg-gray-100'}>
                  <th className={`px-3 py-2 text-left ${isDark ? 'text-gray-300' : ''}`}>Name</th>
                  <th className={`px-3 py-2 text-left ${isDark ? 'text-gray-300' : ''}`}>Image</th>
                  <th className={`px-3 py-2 text-left ${isDark ? 'text-gray-300' : ''}`}>State</th>
                  <th className={`px-3 py-2 text-left ${isDark ? 'text-gray-300' : ''}`}>Restarts</th>
                </tr>
              </thead>
              <tbody>
                {pod.container_statuses.map((container, index) => (
                  <tr key={index} className={`border-t ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
                    <td className={`px-3 py-2 ${isDark ? 'text-gray-200' : ''}`}>{container.name}</td>
                    <td className={`px-3 py-2 font-mono text-xs ${isDark ? 'text-gray-300' : ''}`}>{container.image}</td>
                    <td className="px-3 py-2">
                      <span className={`px-2 py-1 rounded text-xs ${
                        container.state === 'running'
                          ? isDark ? 'bg-green-900/50 text-green-300' : 'bg-green-100 text-green-800'
                          : container.state === 'waiting'
                            ? isDark ? 'bg-yellow-900/50 text-yellow-300' : 'bg-yellow-100 text-yellow-800'
                            : isDark ? 'bg-red-900/50 text-red-300' : 'bg-red-100 text-red-800'
                      }`}>
                        {container.state}
                      </span>
                    </td>
                    <td className={`px-3 py-2 ${isDark ? 'text-gray-200' : ''}`}>{container.restart_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Events */}
      {pod.events && pod.events.length > 0 && (
        <div>
          <h4 className={`font-medium mb-2 ${isDark ? 'text-gray-100' : 'text-gray-900'}`}>Recent Events</h4>
          <div className="space-y-2">
            {pod.events.slice(0, 3).map((event, index) => (
              <div key={index} className="flex items-start space-x-2">
                <span className={`px-2 py-1 rounded text-xs ${
                  event.type === 'Warning'
                    ? isDark ? 'bg-red-900/50 text-red-300' : 'bg-red-100 text-red-800'
                    : isDark ? 'bg-blue-900/50 text-blue-300' : 'bg-blue-100 text-blue-800'
                }`}>
                  {event.type}
                </span>
                <div className="flex-1">
                  <div className={`text-sm font-medium ${isDark ? 'text-gray-200' : ''}`}>{event.reason}</div>
                  <div className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>{event.message}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Workflow Actions */}
      {onStatusChange && (
        <div className="flex items-center flex-wrap gap-2">
          {/* New status: Acknowledge + Ignore */}
          {(pod.status === 'new' || !pod.status) && (
            <>
              <button
                onClick={() => handleStatusAction('investigating')}
                disabled={isUpdatingStatus}
                className={`inline-flex items-center px-3 py-1.5 text-xs font-medium rounded-md disabled:opacity-50 ${isDark ? 'text-purple-300 bg-purple-900/40 border border-purple-700 hover:bg-purple-900/60' : 'text-purple-700 bg-purple-100 border border-purple-300 hover:bg-purple-200'}`}
              >
                <Search className="w-3.5 h-3.5 mr-1" />
                Acknowledge
              </button>
              <button
                onClick={() => handleStatusAction('ignored')}
                disabled={isUpdatingStatus}
                className={`inline-flex items-center px-3 py-1.5 text-xs font-medium rounded-md disabled:opacity-50 ${isDark ? 'text-gray-300 bg-gray-700 border border-gray-600 hover:bg-gray-600' : 'text-gray-600 bg-gray-100 border border-gray-300 hover:bg-gray-200'}`}
              >
                <EyeOff className="w-3.5 h-3.5 mr-1" />
                Ignore
              </button>
            </>
          )}

          {/* Investigating status: Ignore only (resolve is automatic) */}
          {pod.status === 'investigating' && (
            <>
              <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${isDark ? 'bg-yellow-900/50 text-yellow-300 border-yellow-700' : 'bg-yellow-100 text-yellow-800 border-yellow-300'}`}>
                <Clock className="w-3 h-3 mr-1" />
                Investigating — will auto-resolve when pod recovers
              </span>
              <button
                onClick={() => handleStatusAction('ignored')}
                disabled={isUpdatingStatus}
                className={`inline-flex items-center px-3 py-1.5 text-xs font-medium rounded-md disabled:opacity-50 ${isDark ? 'text-gray-300 bg-gray-700 border border-gray-600 hover:bg-gray-600' : 'text-gray-600 bg-gray-100 border border-gray-300 hover:bg-gray-200'}`}
              >
                <EyeOff className="w-3.5 h-3.5 mr-1" />
                Ignore
              </button>
            </>
          )}

          {/* Resolved status: show resolution info + delete */}
          {pod.status === 'resolved' && (
            <div className={`flex items-center text-xs ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
              <span className={`inline-flex items-center px-2 py-0.5 rounded-full font-medium mr-2 border ${isDark ? 'bg-green-900/50 text-green-300 border-green-700' : 'bg-green-100 text-green-800 border-green-300'}`}>
                <CheckCircle className="w-3 h-3 mr-1" />
                Resolved
              </span>
              {pod.resolved_at && <span className={isDark ? 'text-gray-400' : 'text-gray-500'}>on {new Date(pod.resolved_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>}
              {pod.resolution_note && <span className={`ml-2 italic ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>— {pod.resolution_note}</span>}
              {onDeleteRecord && (
                <button
                  onClick={handleDelete}
                  disabled={isDeleting}
                  className={`ml-auto shrink-0 inline-flex items-center px-3 py-1.5 text-xs font-medium rounded-md disabled:opacity-50 ${isDark ? 'text-red-300 bg-red-900/40 border border-red-700 hover:bg-red-900/60' : 'text-red-700 bg-red-50 border border-red-300 hover:bg-red-100'}`}
                >
                  <Trash2 className="w-3.5 h-3.5 mr-1" />
                  {isDeleting ? 'Deleting...' : 'Delete'}
                </button>
              )}
            </div>
          )}

          {/* Ignored status: Restore + Delete buttons */}
          {pod.status === 'ignored' && (
            <>
              <button
                onClick={() => handleStatusAction('new')}
                disabled={isUpdatingStatus}
                className={`inline-flex items-center px-3 py-1.5 text-xs font-medium rounded-md disabled:opacity-50 ${isDark ? 'text-blue-300 bg-blue-900/40 border border-blue-700 hover:bg-blue-900/60' : 'text-blue-700 bg-blue-100 border border-blue-300 hover:bg-blue-200'}`}
              >
                <RotateCcw className="w-3.5 h-3.5 mr-1" />
                Restore
              </button>
              {onDeleteRecord && (
                <button
                  onClick={handleDelete}
                  disabled={isDeleting}
                  className={`inline-flex items-center px-3 py-1.5 text-xs font-medium rounded-md disabled:opacity-50 ${isDark ? 'text-red-300 bg-red-900/40 border border-red-700 hover:bg-red-900/60' : 'text-red-700 bg-red-50 border border-red-300 hover:bg-red-100'}`}
                >
                  <Trash2 className="w-3.5 h-3.5 mr-1" />
                  {isDeleting ? 'Deleting...' : 'Delete'}
                </button>
              )}
            </>
          )}
        </div>
      )}

      {/* Mirror Pod Status */}
      {activeMirror && (
        <MirrorPodStatus
          mirror={activeMirror}
          onDelete={onDeleteMirror}
          onRefresh={onRefreshMirror}
          isDark={isDark}
        />
      )}

      {/* Complete Solution */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center space-x-2">
            <h4 className={`font-medium ${isDark ? 'text-gray-100' : 'text-gray-900'}`}>AI-Generated Solution</h4>
            <button
              onClick={handleRetrySolution}
              disabled={isRetrying || !aiEnabled}
              className={`inline-flex items-center px-2 py-1 text-xs font-medium rounded focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed ${isDark ? 'text-blue-300 bg-blue-900/40 border border-blue-700 hover:bg-blue-900/60' : 'text-blue-700 bg-blue-100 border border-blue-300 hover:bg-blue-200'}`}
              title={!aiEnabled ? 'AI provider not configured' : 'Retry AI Solution'}
            >
              <RefreshCw className={`w-3 h-3 mr-1 ${isRetrying ? 'animate-spin' : ''}`} />
              {isRetrying ? 'Retrying...' : 'Retry AI'}
            </button>
          </div>
          <div className="flex items-center space-x-2">
            {aiEnabled && onTestFix && (
              <button
                onClick={onTestFix}
                className={`inline-flex items-center px-3 py-1 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 ${isDark ? 'border border-purple-700 text-purple-300 bg-purple-900/40 hover:bg-purple-900/60' : 'border border-purple-300 text-purple-700 bg-purple-50 hover:bg-purple-100'}`}
                title="Deploy a temporary mirror pod with the AI fix applied"
              >
                <FlaskConical className="w-4 h-4 mr-2" />
                Test Fix
              </button>
            )}
            <button
              onClick={onViewLogs}
              className={`inline-flex items-center px-3 py-1 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-green-500 ${isDark ? 'border border-green-700 text-green-300 bg-green-900/40 hover:bg-green-900/60' : 'border border-green-300 text-green-700 bg-green-50 hover:bg-green-100'}`}
              title="View Pod Logs"
            >
              <Terminal className="w-4 h-4 mr-2" />
              Logs
            </button>
            <button
              onClick={onViewManifest}
              className={`inline-flex items-center px-3 py-1 border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                isDark
                  ? 'border-gray-600 text-gray-300 bg-gray-700 hover:bg-gray-600'
                  : 'border-gray-300 text-gray-700 bg-white hover:bg-gray-50'
              }`}
              title="View Pod Manifest"
            >
              <FileText className="w-4 h-4 mr-2" />
              View Manifest
            </button>
          </div>
        </div>
        <div className={`rounded p-4 text-sm overflow-hidden ${
          isFallbackSolution
            ? isDark ? 'bg-yellow-900/30 border border-yellow-700' : 'bg-yellow-50 border border-yellow-200'
            : isDark ? 'bg-blue-900/30 border border-blue-700' : 'bg-blue-50 border border-blue-200'
        }`}>
          <div className="solution-content">
            <SolutionMarkdown content={pod.solution} isDark={isDark} />
          </div>
        </div>
      </div>

      {/* Log-Aware Troubleshoot Section */}
      <TroubleshootSection
        pod={pod}
        isDark={isDark}
        aiEnabled={aiEnabled}
        onLogAwareSolutionUpdated={onLogAwareSolutionUpdated}
      />
    </div>
  );
};

export default PodDetails;
