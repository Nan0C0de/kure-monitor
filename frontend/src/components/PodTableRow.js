import React, { useState } from 'react';
import { ChevronDown, ChevronRight, AlertTriangle } from 'lucide-react';
import StatusBadge from './StatusBadge';
import PodDetails from './PodDetails';
import ManifestModal from './ManifestModal';
import PodLogsModal from './PodLogsModal';
import { api } from '../services/api';

const getWorkflowStatusBadge = (status) => {
  switch (status) {
    case 'investigating':
      return { label: 'Investigating', className: 'bg-yellow-100 text-yellow-800 border-yellow-300' };
    case 'resolved':
      return { label: 'Resolved', className: 'bg-green-100 text-green-800 border-green-300' };
    case 'ignored':
      return { label: 'Ignored', className: 'bg-gray-100 text-gray-600 border-gray-300' };
    case 'new':
    default:
      return { label: 'New', className: 'bg-red-100 text-red-800 border-red-300' };
  }
};

const PodTableRow = ({ pod, onSolutionUpdated, onStatusChange, isDark = false, aiEnabled = false, viewMode = 'active' }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [showManifest, setShowManifest] = useState(false);
  const [showLogs, setShowLogs] = useState(false);
  const [isRetryingFromModal, setIsRetryingFromModal] = useState(false);

  const formatTimestamp = (timestamp) => {
    return new Date(timestamp).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  // Check if solution is a fallback (AI unavailable)
  const isFallbackSolution = pod.solution && (
    pod.solution.includes('AI solution temporarily unavailable') ||
    pod.solution.includes('Failed to generate AI solution') ||
    pod.solution.includes('Basic troubleshooting')
  );

  // Retry handler for ManifestModal
  const handleRetrySolutionFromModal = async () => {
    setIsRetryingFromModal(true);
    try {
      const updatedPod = await api.retrySolution(pod.id);
      if (onSolutionUpdated) {
        onSolutionUpdated(updatedPod);
      }
    } catch (error) {
      console.error('Failed to retry solution:', error);
    } finally {
      setIsRetryingFromModal(false);
    }
  };

  return (
    <>
      <tr className={`border-b ${isDark ? 'border-gray-700 hover:bg-gray-700' : 'border-gray-200 hover:bg-gray-50'}`}>
        <td className="px-6 py-3 align-top">
          <div className="flex items-start">
            <button
              onClick={() => setIsExpanded(!isExpanded)}
              className={`mr-2 mt-0.5 ${isDark ? 'text-gray-500 hover:text-gray-300' : 'text-gray-400 hover:text-gray-600'}`}
            >
              {isExpanded ? (
                <ChevronDown className="w-4 h-4" data-testid="chevron-down" />
              ) : (
                <ChevronRight className="w-4 h-4" data-testid="chevron-right" />
              )}
            </button>
            <div className="flex-1">
              <button
                onClick={() => setIsExpanded(!isExpanded)}
                className={`text-left rounded transition-colors w-full ${isDark ? 'hover:bg-gray-700' : 'hover:bg-gray-50'}`}
              >
                <div className={`text-sm font-bold ${isDark ? 'text-gray-200' : 'text-gray-900'}`}>{pod.pod_name}</div>
                <div className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>{pod.namespace}</div>
              </button>
            </div>
          </div>
        </td>
        <td className="px-6 py-3 align-top">
          <div className="flex flex-col items-start gap-1">
            <button
              onClick={() => setIsExpanded(!isExpanded)}
              className={`rounded transition-colors ${isDark ? 'hover:bg-gray-700' : 'hover:bg-gray-50'}`}
            >
              <StatusBadge reason={pod.failure_reason} />
            </button>
            {(() => {
              const badge = getWorkflowStatusBadge(pod.status);
              return (
                <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${badge.className}`}>
                  {badge.label}
                </span>
              );
            })()}
          </div>
        </td>
        <td className="px-6 py-3 align-top">
          <div className="w-full">
            <button
              onClick={() => setIsExpanded(!isExpanded)}
              className={`text-sm text-left rounded transition-colors w-full ${isDark ? 'hover:bg-gray-700' : 'hover:bg-gray-50'}`}
            >
              {isFallbackSolution ? (
                <>
                  <div className="font-medium text-yellow-500 mb-1 flex items-center">
                    <AlertTriangle className="w-4 h-4 mr-1" />
                    Basic Solution Available
                  </div>
                  <div className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Click to expand and retry AI</div>
                </>
              ) : (
                <>
                  <div className={`font-medium mb-1 ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>AI Solution Available</div>
                  <div className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Click to expand for detailed solution</div>
                </>
              )}
            </button>
          </div>
        </td>
        <td className={`px-6 py-3 text-sm align-top ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
          <div>
            {viewMode === 'history' && pod.resolved_at
              ? formatTimestamp(pod.resolved_at)
              : formatTimestamp(pod.timestamp)
            }
          </div>
          {viewMode === 'history' && pod.resolution_note && (
            <div className={`text-xs mt-1 ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
              {pod.resolution_note.length > 50
                ? pod.resolution_note.substring(0, 50) + '...'
                : pod.resolution_note}
            </div>
          )}
        </td>
      </tr>
      {isExpanded && (
        <tr className={isDark ? 'bg-gray-900' : 'bg-gray-50'}>
          <td colSpan="4" className="px-6 py-4 overflow-hidden max-w-0">
            <PodDetails
              pod={pod}
              onViewManifest={() => setShowManifest(true)}
              onViewLogs={() => setShowLogs(true)}
              onSolutionUpdated={onSolutionUpdated}
              onStatusChange={onStatusChange}
              isDark={isDark}
              aiEnabled={aiEnabled}
              viewMode={viewMode}
            />
          </td>
        </tr>
      )}
      <ManifestModal
        isOpen={showManifest}
        onClose={() => setShowManifest(false)}
        podName={pod.pod_name}
        namespace={pod.namespace}
        manifest={pod.manifest}
        solution={pod.solution}
        onRetrySolution={handleRetrySolutionFromModal}
        isRetrying={isRetryingFromModal}
        isDark={isDark}
        aiEnabled={aiEnabled}
      />
      <PodLogsModal
        isOpen={showLogs}
        onClose={() => setShowLogs(false)}
        pod={pod}
        isDark={isDark}
      />
    </>
  );
};

export default PodTableRow;
