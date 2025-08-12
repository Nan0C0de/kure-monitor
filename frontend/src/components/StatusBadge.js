import React from 'react';

const StatusBadge = ({ reason }) => {
  const getStatusColor = (reason) => {
    switch (reason) {
      case 'ImagePullBackOff':
      case 'ErrImagePull':
      case 'InvalidImageName':
      case 'ErrImageNeverPull':
        return 'bg-red-50 text-red-700 border-red-300';
      case 'CrashLoopBackOff':
        return 'bg-red-50 text-red-700 border-red-300';
      case 'CreateContainerError':
      case 'RunContainerError':
        return 'bg-red-50 text-red-700 border-red-300';
      case 'Pending':
        return 'bg-yellow-50 text-yellow-700 border-yellow-300';
      case 'FailedMount':
        return 'bg-red-50 text-red-700 border-red-300';
      case 'FailedScheduling':
        return 'bg-orange-50 text-orange-700 border-orange-300';
      case 'Failed':
        return 'bg-red-50 text-red-700 border-red-300';
      default:
        return 'bg-red-50 text-red-700 border-red-300';
    }
  };

  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${getStatusColor(reason)}`}>
      {reason}
    </span>
  );
};

export default StatusBadge;
