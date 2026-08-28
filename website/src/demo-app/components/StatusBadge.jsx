import React from 'react';

const StatusBadge = ({ reason }) => {
  const getStatusColor = (reason) => {
    switch (reason) {
      case 'ImagePullBackOff':
      case 'ErrImagePull':
      case 'InvalidImageName':
      case 'ErrImageNeverPull':
        return 'bg-blue-50 text-blue-700 border-blue-300';
      case 'CrashLoopBackOff':
      case 'CreateContainerError':
      case 'RunContainerError':
      case 'FailedMount':
      case 'Failed':
        return 'bg-red-50 text-red-700 border-red-300';
      case 'Pending':
        return 'bg-yellow-50 text-yellow-700 border-yellow-300';
      case 'FailedScheduling':
        return 'bg-red-50 text-red-700 border-red-300';
      case 'Evicted':
        return 'bg-gray-50 text-gray-700 border-gray-300';
      case 'NodeLost':
        return 'bg-stone-50 text-stone-700 border-stone-300';
      default:
        return 'bg-red-50 text-red-700 border-red-300';
    }
  };

  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded text-xs font-medium border ${getStatusColor(reason)}`}>
      {reason}
    </span>
  );
};

export default StatusBadge;
