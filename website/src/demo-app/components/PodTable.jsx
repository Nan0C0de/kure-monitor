import React from 'react';
import PodTableRow from './PodTableRow';

const PodTable = ({ pods, onSolutionUpdated, onLogAwareSolutionUpdated, onStatusChange, onDeleteRecord, aiEnabled = false, viewMode = 'active', canWrite = true }) => {
  return (
    <div className="overflow-hidden w-full">
      <table className={`min-w-full divide-y table-fixed divide-gray-200`}>
        <thead className={'bg-gray-50'}>
          <tr>
            <th className={`px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500`}>
              Pod Name
            </th>
            <th className={`px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500`}>
              Status
            </th>
            <th className={`px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500`}>
              Solution
            </th>
            <th className={`px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500`}>
              {viewMode === 'history' ? 'Resolved' : 'Detected'}
            </th>
          </tr>
        </thead>
        <tbody className={`divide-y bg-white divide-gray-200`}>
          {pods.map((pod) => (
            <PodTableRow
              key={pod.id}
              pod={pod}
              onSolutionUpdated={canWrite ? onSolutionUpdated : undefined}
              onLogAwareSolutionUpdated={canWrite ? onLogAwareSolutionUpdated : undefined}
              onStatusChange={canWrite ? onStatusChange : undefined}
              onDeleteRecord={canWrite ? onDeleteRecord : undefined}
              aiEnabled={aiEnabled}
              viewMode={viewMode}
              canWrite={canWrite}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default PodTable;
