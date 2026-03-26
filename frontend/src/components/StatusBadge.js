import React from 'react';

const StatusBadge = ({ reason, isDark = false }) => {
  const getStatusColor = (reason) => {
    switch (reason) {
      case 'ImagePullBackOff':
      case 'ErrImagePull':
      case 'InvalidImageName':
      case 'ErrImageNeverPull':
      case 'CrashLoopBackOff':
      case 'CreateContainerError':
      case 'RunContainerError':
      case 'FailedMount':
      case 'Failed':
        return isDark ? 'bg-red-900/50 text-red-300 border-red-700' : 'bg-red-50 text-red-700 border-red-300';
      case 'Pending':
        return isDark ? 'bg-yellow-900/50 text-yellow-300 border-yellow-700' : 'bg-yellow-50 text-yellow-700 border-yellow-300';
      case 'FailedScheduling':
        return isDark ? 'bg-orange-900/50 text-orange-300 border-orange-700' : 'bg-orange-50 text-orange-700 border-orange-300';
      default:
        return isDark ? 'bg-red-900/50 text-red-300 border-red-700' : 'bg-red-50 text-red-700 border-red-300';
    }
  };

  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${getStatusColor(reason)}`}>
      {reason}
    </span>
  );
};

export default StatusBadge;
