import React, { useState } from 'react';
import { Shield, ChevronDown, ChevronRight, AlertTriangle, AlertCircle, Info, FileText } from 'lucide-react';
import SecurityFixModal from './SecurityFixModal';

const SecurityTable = ({ findings, isDark = false, aiEnabled = false }) => {
  const [expandedFinding, setExpandedFinding] = useState(null);
  const [selectedFinding, setSelectedFinding] = useState(null);
  const [showFixModal, setShowFixModal] = useState(false);

  // Create a stable key for each finding
  const getFindingKey = (finding) => {
    return `${finding.namespace}-${finding.resource_name}-${finding.title}`;
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
      <table className={`min-w-full divide-y ${isDark ? 'divide-gray-700' : 'divide-gray-200'}`}>
        <thead className={isDark ? 'bg-gray-900' : 'bg-gray-50'}>
          <tr>
            <th className={`w-10 px-6 py-3 text-left text-xs font-medium uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>

            </th>
            <th className={`px-6 py-3 text-left text-xs font-medium uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
              Severity
            </th>
            <th className={`px-6 py-3 text-left text-xs font-medium uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
              Resource
            </th>
            <th className={`px-6 py-3 text-left text-xs font-medium uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
              Namespace
            </th>
            <th className={`px-6 py-3 text-left text-xs font-medium uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
              Category
            </th>
            <th className={`px-6 py-3 text-left text-xs font-medium uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
              Issue
            </th>
          </tr>
        </thead>
        <tbody className={`divide-y ${isDark ? 'bg-gray-800 divide-gray-700' : 'bg-white divide-gray-200'}`}>
          {findings.map((finding) => {
            const findingKey = getFindingKey(finding);
            const isExpanded = expandedFinding === findingKey;

            return (
              <React.Fragment key={findingKey}>
                <tr className={`cursor-pointer ${isDark ? 'hover:bg-gray-700' : 'hover:bg-gray-50'}`} onClick={() => setExpandedFinding(isExpanded ? null : findingKey)}>
                  <td className="px-6 py-4 whitespace-nowrap">
                    {isExpanded ? (
                      <ChevronDown className={`w-5 h-5 ${isDark ? 'text-gray-500' : 'text-gray-400'}`} />
                    ) : (
                      <ChevronRight className={`w-5 h-5 ${isDark ? 'text-gray-500' : 'text-gray-400'}`} />
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
                      <Shield className={`w-4 h-4 mr-2 ${isDark ? 'text-gray-500' : 'text-gray-400'}`} />
                      <div>
                        <div className={`text-sm font-medium ${isDark ? 'text-gray-200' : 'text-gray-900'}`}>{finding.resource_name}</div>
                        <div className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>{finding.resource_type}</div>
                      </div>
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${isDark ? 'bg-indigo-900 text-indigo-300' : 'bg-indigo-100 text-indigo-800'}`}>
                      {finding.namespace}
                    </span>
                  </td>
                  <td className={`px-6 py-4 whitespace-nowrap text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                    {finding.category}
                  </td>
                  <td className="px-6 py-4">
                    <div className={`text-sm ${isDark ? 'text-gray-200' : 'text-gray-900'}`}>{finding.title}</div>
                  </td>
                </tr>
                {isExpanded && (
                  <tr>
                    <td colSpan="6" className={`px-6 py-4 ${isDark ? 'bg-gray-900' : 'bg-gray-50'}`}>
                      <div className="space-y-4">
                        <div>
                          <h4 className={`text-sm font-semibold mb-2 ${isDark ? 'text-gray-200' : 'text-gray-700'}`}>Description</h4>
                          <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>{finding.description}</p>
                        </div>
                        <div>
                          <h4 className={`text-sm font-semibold mb-2 ${isDark ? 'text-gray-200' : 'text-gray-700'}`}>Remediation</h4>
                          <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>{finding.remediation}</p>
                        </div>
                        <div>
                          <h4 className={`text-sm font-semibold mb-2 ${isDark ? 'text-gray-200' : 'text-gray-700'}`}>Detected At</h4>
                          <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>{new Date(finding.timestamp).toLocaleString()}</p>
                        </div>
                        <div className="pt-2">
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              setSelectedFinding(finding);
                              setShowFixModal(true);
                            }}
                            className={`inline-flex items-center px-3 py-2 border shadow-sm text-sm leading-4 font-medium rounded-md focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 ${
                              isDark
                                ? 'border-gray-600 text-gray-300 bg-gray-700 hover:bg-gray-600'
                                : 'border-gray-300 text-gray-700 bg-white hover:bg-gray-50'
                            }`}
                          >
                            <FileText className="w-4 h-4 mr-1" />
                            Manifest
                          </button>
                        </div>
                      </div>
                    </td>
                  </tr>
                )}
              </React.Fragment>
            );
          })}
        </tbody>
      </table>

      <SecurityFixModal
        isOpen={showFixModal}
        onClose={() => {
          setShowFixModal(false);
          setSelectedFinding(null);
        }}
        finding={selectedFinding}
        isDark={isDark}
        aiEnabled={aiEnabled}
      />
    </div>
  );
};

export default SecurityTable;
