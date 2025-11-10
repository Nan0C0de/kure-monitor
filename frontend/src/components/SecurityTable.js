import React, { useState } from 'react';
import { Shield, X, ChevronDown, ChevronRight, AlertTriangle, AlertCircle, Info } from 'lucide-react';
import { api } from '../services/api';

const SecurityTable = ({ findings }) => {
  const [expandedFinding, setExpandedFinding] = useState(null);
  const [dismissing, setDismissing] = useState(null);

  const handleDismiss = async (findingId) => {
    setDismissing(findingId);
    try {
      await api.dismissSecurityFinding(findingId);
      // The parent component will handle removing the finding from the list via WebSocket
    } catch (error) {
      console.error('Error dismissing finding:', error);
      alert('Failed to dismiss security finding');
    } finally {
      setDismissing(null);
    }
  };

  const getSeverityColor = (severity) => {
    switch (severity.toLowerCase()) {
      case 'critical':
        return 'bg-red-100 text-red-800 border-red-300';
      case 'high':
        return 'bg-orange-100 text-orange-800 border-orange-300';
      case 'medium':
        return 'bg-yellow-100 text-yellow-800 border-yellow-300';
      case 'low':
        return 'bg-blue-100 text-blue-800 border-blue-300';
      default:
        return 'bg-gray-100 text-gray-800 border-gray-300';
    }
  };

  const getSeverityIcon = (severity) => {
    switch (severity.toLowerCase()) {
      case 'critical':
      case 'high':
        return <AlertTriangle className="w-4 h-4" />;
      case 'medium':
        return <AlertCircle className="w-4 h-4" />;
      case 'low':
      default:
        return <Info className="w-4 h-4" />;
    }
  };

  if (findings.length === 0) {
    return null;
  }

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-gray-200">
        <thead className="bg-gray-50">
          <tr>
            <th className="w-10 px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">

            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Severity
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Resource
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Namespace
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Category
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Issue
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Actions
            </th>
          </tr>
        </thead>
        <tbody className="bg-white divide-y divide-gray-200">
          {findings.map((finding) => (
            <React.Fragment key={finding.id}>
              <tr className="hover:bg-gray-50 cursor-pointer" onClick={() => setExpandedFinding(expandedFinding === finding.id ? null : finding.id)}>
                <td className="px-6 py-4 whitespace-nowrap">
                  {expandedFinding === finding.id ? (
                    <ChevronDown className="w-5 h-5 text-gray-400" />
                  ) : (
                    <ChevronRight className="w-5 h-5 text-gray-400" />
                  )}
                </td>
                <td className="px-6 py-4 whitespace-nowrap">
                  <span className={`inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-xs font-medium border ${getSeverityColor(finding.severity)}`}>
                    {getSeverityIcon(finding.severity)}
                    <span className="ml-1">{finding.severity.toUpperCase()}</span>
                  </span>
                </td>
                <td className="px-6 py-4 whitespace-nowrap">
                  <div className="flex items-center">
                    <Shield className="w-4 h-4 text-gray-400 mr-2" />
                    <div>
                      <div className="text-sm font-medium text-gray-900">{finding.resource_name}</div>
                      <div className="text-xs text-gray-500">{finding.resource_type}</div>
                    </div>
                  </div>
                </td>
                <td className="px-6 py-4 whitespace-nowrap">
                  <span className="px-2 inline-flex text-xs leading-5 font-semibold rounded-full bg-indigo-100 text-indigo-800">
                    {finding.namespace}
                  </span>
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                  {finding.category}
                </td>
                <td className="px-6 py-4">
                  <div className="text-sm text-gray-900">{finding.title}</div>
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDismiss(finding.id);
                    }}
                    disabled={dismissing === finding.id}
                    className="text-red-600 hover:text-red-900 disabled:opacity-50"
                  >
                    <X className="w-5 h-5" />
                  </button>
                </td>
              </tr>
              {expandedFinding === finding.id && (
                <tr>
                  <td colSpan="7" className="px-6 py-4 bg-gray-50">
                    <div className="space-y-4">
                      <div>
                        <h4 className="text-sm font-semibold text-gray-700 mb-2">Description</h4>
                        <p className="text-sm text-gray-600">{finding.description}</p>
                      </div>
                      <div>
                        <h4 className="text-sm font-semibold text-gray-700 mb-2">Remediation</h4>
                        <p className="text-sm text-gray-600">{finding.remediation}</p>
                      </div>
                      <div>
                        <h4 className="text-sm font-semibold text-gray-700 mb-2">Detected At</h4>
                        <p className="text-sm text-gray-600">{new Date(finding.timestamp).toLocaleString()}</p>
                      </div>
                    </div>
                  </td>
                </tr>
              )}
            </React.Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default SecurityTable;