import React, { useState } from 'react';
import { ChevronDown, ChevronRight, AlertTriangle } from 'lucide-react';
import StatusBadge from './StatusBadge';
import PodDetails from './PodDetails';
import ManifestModal from './ManifestModal';
import { api } from '../services/api';

const PodTableRow = ({ pod, onSolutionUpdated }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [showManifest, setShowManifest] = useState(false);
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
      <tr className="hover:bg-gray-50 border-b border-gray-200">
        <td className="px-6 py-3 align-top">
          <div className="flex items-start">
            <button
              onClick={() => setIsExpanded(!isExpanded)}
              className="mr-2 text-gray-400 hover:text-gray-600 mt-0.5"
            >
              {isExpanded ? (
                <ChevronDown className="w-4 h-4" />
              ) : (
                <ChevronRight className="w-4 h-4" />
              )}
            </button>
            <div className="flex-1">
              <button
                onClick={() => setIsExpanded(!isExpanded)}
                className="text-left hover:bg-gray-50 rounded transition-colors w-full"
              >
                <div className="text-sm font-bold text-gray-900">{pod.pod_name}</div>
                <div className="text-sm text-gray-500">{pod.namespace}</div>
              </button>
            </div>
          </div>
        </td>
        <td className="px-6 py-3 align-top">
          <div className="flex justify-start">
            <button
              onClick={() => setIsExpanded(!isExpanded)}
              className="hover:bg-gray-50 rounded transition-colors"
            >
              <StatusBadge reason={pod.failure_reason} />
            </button>
          </div>
        </td>
        <td className="px-6 py-3 align-top">
          <div className="w-full">
            <button
              onClick={() => setIsExpanded(!isExpanded)}
              className="text-sm text-left hover:bg-gray-50 rounded transition-colors w-full"
            >
              {isFallbackSolution ? (
                <>
                  <div className="font-medium text-yellow-600 mb-1 flex items-center">
                    <AlertTriangle className="w-4 h-4 mr-1" />
                    Basic Solution Available
                  </div>
                  <div className="text-xs text-gray-500">Click to expand and retry AI</div>
                </>
              ) : (
                <>
                  <div className="font-medium text-gray-600 mb-1">AI Solution Available</div>
                  <div className="text-xs text-gray-500">Click to expand for detailed solution</div>
                </>
              )}
            </button>
          </div>
        </td>
        <td className="px-6 py-3 text-sm text-gray-500 align-top">
          <div>
            {formatTimestamp(pod.timestamp)}
          </div>
        </td>
      </tr>
      {isExpanded && (
        <tr className="bg-gray-50">
          <td colSpan="4" className="px-6 py-4 overflow-hidden max-w-0">
            <PodDetails
              pod={pod}
              onViewManifest={() => setShowManifest(true)}
              onSolutionUpdated={onSolutionUpdated}
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
      />
    </>
  );
};

export default PodTableRow;
