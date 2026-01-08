import React from 'react';
import PodTableRow from './PodTableRow';

const PodTable = ({ pods, onSolutionUpdated }) => {
  return (
    <div className="overflow-hidden w-full">
      <table className="min-w-full divide-y divide-gray-200 table-fixed">
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
          </tr>
        </thead>
        <tbody className="bg-white divide-y divide-gray-200">
          {pods.map((pod) => (
            <PodTableRow
              key={pod.id}
              pod={pod}
              onSolutionUpdated={onSolutionUpdated}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default PodTable;
