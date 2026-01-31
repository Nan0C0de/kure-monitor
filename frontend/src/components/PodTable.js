import React from 'react';
import PodTableRow from './PodTableRow';

const PodTable = ({ pods, onSolutionUpdated, onStatusChange, isDark = false, aiEnabled = false, viewMode = 'active' }) => {
  return (
    <div className="overflow-hidden w-full">
      <table className={`min-w-full divide-y table-fixed ${isDark ? 'divide-gray-700' : 'divide-gray-200'}`}>
        <thead className={isDark ? 'bg-gray-900' : 'bg-gray-50'}>
          <tr>
            <th className={`px-6 py-3 text-left text-xs font-medium uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
              Pod Name
            </th>
            <th className={`px-6 py-3 text-left text-xs font-medium uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
              Status
            </th>
            <th className={`px-6 py-3 text-left text-xs font-medium uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
              Solution
            </th>
            <th className={`px-6 py-3 text-left text-xs font-medium uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
              {viewMode === 'history' ? 'Resolved' : 'Detected'}
            </th>
          </tr>
        </thead>
        <tbody className={`divide-y ${isDark ? 'bg-gray-800 divide-gray-700' : 'bg-white divide-gray-200'}`}>
          {pods.map((pod) => (
            <PodTableRow
              key={pod.id}
              pod={pod}
              onSolutionUpdated={onSolutionUpdated}
              onStatusChange={onStatusChange}
              isDark={isDark}
              aiEnabled={aiEnabled}
              viewMode={viewMode}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default PodTable;
