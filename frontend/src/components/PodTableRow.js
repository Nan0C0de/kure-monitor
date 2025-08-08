import React, { useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import StatusBadge from './StatusBadge';
import PodDetails from './PodDetails';
import ManifestModal from './ManifestModal';

const PodTableRow = ({ pod }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [showManifest, setShowManifest] = useState(false);

  const formatTimestamp = (timestamp) => {
    return new Date(timestamp).toLocaleString();
  };

  return (
    <>
      <tr className="hover:bg-gray-50 border-b border-gray-200">
        <td className="px-6 py-4 align-top">
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
            <div>
              <div className="text-sm font-medium text-gray-900">{pod.pod_name}</div>
              <div className="text-sm text-gray-500">{pod.namespace}</div>
            </div>
          </div>
        </td>
        <td className="px-6 py-4 whitespace-nowrap align-top">
          <div className="mt-0.5">
            <StatusBadge reason={pod.failure_reason} />
          </div>
        </td>
        <td className="px-6 py-4 align-top">
          <div className="mt-0.5">
            <button
              onClick={() => setIsExpanded(!isExpanded)}
              className="text-sm text-left hover:bg-gray-50 rounded transition-colors w-full"
            >
              <div className="font-medium text-gray-600 mb-1">AI Solution Available</div>
              <div className="text-xs text-gray-500">Click to expand for detailed solution</div>
            </button>
          </div>
        </td>
        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 align-top">
          <div className="mt-0.5">
            {formatTimestamp(pod.timestamp)}
          </div>
        </td>
      </tr>
      {isExpanded && (
        <tr className="bg-gray-50">
          <td colSpan="4" className="px-6 py-4">
            <PodDetails 
              pod={pod} 
              onViewManifest={() => setShowManifest(true)}
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
      />
    </>
  );
};

export default PodTableRow;
