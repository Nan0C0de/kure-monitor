import React from 'react';

const StatusBadge = ({ reason }) => {
  const getStatusColor = (reason) => {
    switch (reason) {
      case 'ImagePullBackOff':
      case 'ErrImagePull':
        return 'bg-red-100 text-red-800 border-red-200';
      case 'CrashLoopBackOff':
        return 'bg-orange-100 text-orange-800 border-orange-200';
      case 'Pending':
        return 'bg-yellow-100 text-yellow-800 border-yellow-200';
      default:
        return 'bg-gray-100 text-gray-800 border-gray-200';
    }
  };

  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${getStatusColor(reason)}`}>
      {reason}
    </span>
  );
};

export default StatusBadge;
