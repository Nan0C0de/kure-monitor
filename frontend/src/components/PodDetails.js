import React from 'react';
import { FileText } from 'lucide-react';

const PodDetails = ({ pod, onViewManifest }) => {
  const formatTimestamp = (timestamp) => {
    return new Date(timestamp).toLocaleString();
  };

  return (
    <div className="space-y-4">
      {/* Pod Details */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <h4 className="font-medium text-gray-900 mb-2">Pod Details</h4>
          <dl className="space-y-1 text-sm">
            <div className="flex">
              <dt className="font-medium text-gray-600 w-24">Node:</dt>
              <dd className="text-gray-900">{pod.node_name || 'N/A'}</dd>
            </div>
            <div className="flex">
              <dt className="font-medium text-gray-600 w-24">Phase:</dt>
              <dd className="text-gray-900">{pod.phase}</dd>
            </div>
            <div className="flex">
              <dt className="font-medium text-gray-600 w-24">Created:</dt>
              <dd className="text-gray-900">{formatTimestamp(pod.creation_timestamp)}</dd>
            </div>
          </dl>
        </div>
        <div>
          <h4 className="font-medium text-gray-900 mb-2">Error Details</h4>
          <dl className="space-y-1 text-sm">
            <div className="flex">
              <dt className="font-medium text-gray-600 w-24">Reason:</dt>
              <dd className="text-gray-900">{pod.failure_reason}</dd>
            </div>
            {pod.failure_message && (
              <div>
                <dt className="font-medium text-gray-600">Message:</dt>
                <dd className="text-gray-900 text-xs bg-gray-100 p-2 rounded mt-1">
                  {pod.failure_message}
                </dd>
              </div>
            )}
          </dl>
        </div>
      </div>

      {/* Container Statuses */}
      {pod.container_statuses && pod.container_statuses.length > 0 && (
        <div>
          <h4 className="font-medium text-gray-900 mb-2">Container Status</h4>
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="bg-gray-100">
                  <th className="px-3 py-2 text-left">Name</th>
                  <th className="px-3 py-2 text-left">Image</th>
                  <th className="px-3 py-2 text-left">State</th>
                  <th className="px-3 py-2 text-left">Restarts</th>
                </tr>
              </thead>
              <tbody>
                {pod.container_statuses.map((container, index) => (
                  <tr key={index} className="border-t border-gray-200">
                    <td className="px-3 py-2">{container.name}</td>
                    <td className="px-3 py-2 font-mono text-xs">{container.image}</td>
                    <td className="px-3 py-2">
                      <span className={`px-2 py-1 rounded text-xs ${
                        container.state === 'running' ? 'bg-green-100 text-green-800' :
                        container.state === 'waiting' ? 'bg-yellow-100 text-yellow-800' :
                        'bg-red-100 text-red-800'
                      }`}>
                        {container.state}
                      </span>
                    </td>
                    <td className="px-3 py-2">{container.restart_count}</td>
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
          <h4 className="font-medium text-gray-900 mb-2">Recent Events</h4>
          <div className="space-y-2">
            {pod.events.slice(0, 3).map((event, index) => (
              <div key={index} className="flex items-start space-x-2">
                <span className={`px-2 py-1 rounded text-xs ${
                  event.type === 'Warning' ? 'bg-red-100 text-red-800' : 'bg-blue-100 text-blue-800'
                }`}>
                  {event.type}
                </span>
                <div className="flex-1">
                  <div className="text-sm font-medium">{event.reason}</div>
                  <div className="text-xs text-gray-600">{event.message}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Complete Solution */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <h4 className="font-medium text-gray-900">AI-Generated Solution</h4>
          <button
            onClick={onViewManifest}
            className="inline-flex items-center px-3 py-1 border border-gray-300 rounded-md text-sm text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
            title="View Pod Manifest"
          >
            <FileText className="w-4 h-4 mr-2" />
            View Manifest
          </button>
        </div>
        <div 
          className="bg-blue-50 border border-blue-200 rounded p-4 text-sm"
          style={{ whiteSpace: 'pre-wrap' }}
        >
          {pod.solution}
        </div>
      </div>
    </div>
  );
};

export default PodDetails;
