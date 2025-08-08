import React from 'react';
import PodTableRow from './PodTableRow';

const PodTable = ({ pods, onIgnore, isIgnoredView = false }) => {
  return (
    <div className="overflow-hidden">
      <table className="min-w-full divide-y divide-gray-200">
        <thead className="bg-gray-50">
          <tr>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Pod Name
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Status
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Solution
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Detected
            </th>
            <th className="relative px-6 py-3">
              <span className="sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody className="bg-white divide-y divide-gray-200">
          {pods.map((pod) => (
            <PodTableRow
              key={pod.id}
              pod={pod}
              onIgnore={onIgnore}
              isIgnoredView={isIgnoredView}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default PodTable;
