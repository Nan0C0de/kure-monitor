import React, { useState } from 'react';
import { Bug, ChevronDown, ChevronRight, AlertTriangle, AlertCircle, Info, ExternalLink, Check, X } from 'lucide-react';
import { api } from '../services/api';

const CVETable = ({ cves, onDismiss, onAcknowledge }) => {
  const [expandedCVE, setExpandedCVE] = useState(null);
  const [actionLoading, setActionLoading] = useState(null);

  const getSeverityColor = (severity) => {
    switch (severity?.toLowerCase()) {
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
    switch (severity?.toLowerCase()) {
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

  const handleDismiss = async (e, cveId) => {
    e.stopPropagation();
    setActionLoading(cveId);
    try {
      await api.dismissCVEFinding(cveId);
      if (onDismiss) onDismiss(cveId);
    } catch (error) {
      console.error('Failed to dismiss CVE:', error);
    } finally {
      setActionLoading(null);
    }
  };

  const handleAcknowledge = async (e, cveId) => {
    e.stopPropagation();
    setActionLoading(cveId);
    try {
      await api.acknowledgeCVEFinding(cveId);
      if (onAcknowledge) onAcknowledge(cveId);
    } catch (error) {
      console.error('Failed to acknowledge CVE:', error);
    } finally {
      setActionLoading(null);
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return 'Unknown';
    try {
      return new Date(dateString).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
      });
    } catch {
      return dateString;
    }
  };

  if (!cves || cves.length === 0) {
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
              CVE ID
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Severity
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              CVSS
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Components
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Title
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Actions
            </th>
          </tr>
        </thead>
        <tbody className="bg-white divide-y divide-gray-200">
          {cves.map((cve) => {
            const isExpanded = expandedCVE === cve.cve_id;
            const isLoading = actionLoading === cve.id;

            return (
              <React.Fragment key={cve.cve_id}>
                <tr
                  className={`hover:bg-gray-50 cursor-pointer ${cve.acknowledged ? 'opacity-60' : ''}`}
                  onClick={() => setExpandedCVE(isExpanded ? null : cve.cve_id)}
                >
                  <td className="px-6 py-4 whitespace-nowrap">
                    {isExpanded ? (
                      <ChevronDown className="w-5 h-5 text-gray-400" />
                    ) : (
                      <ChevronRight className="w-5 h-5 text-gray-400" />
                    )}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="flex items-center">
                      <Bug className="w-4 h-4 text-red-500 mr-2" />
                      <a
                        href={cve.external_url || `https://cve.mitre.org/cgi-bin/cvename.cgi?name=${cve.cve_id}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        onClick={(e) => e.stopPropagation()}
                        className="text-sm font-medium text-blue-600 hover:text-blue-800 hover:underline flex items-center"
                      >
                        {cve.cve_id}
                        <ExternalLink className="w-3 h-3 ml-1" />
                      </a>
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className={`inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-xs font-medium border ${getSeverityColor(cve.severity)}`}>
                      {getSeverityIcon(cve.severity)}
                      <span className="ml-1">{cve.severity?.toUpperCase() || 'UNKNOWN'}</span>
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    {cve.cvss_score ? (
                      <span className={`inline-flex items-center px-2.5 py-0.5 rounded text-xs font-medium ${
                        cve.cvss_score >= 9.0 ? 'bg-red-100 text-red-800' :
                        cve.cvss_score >= 7.0 ? 'bg-orange-100 text-orange-800' :
                        cve.cvss_score >= 4.0 ? 'bg-yellow-100 text-yellow-800' :
                        'bg-blue-100 text-blue-800'
                      }`}>
                        {cve.cvss_score.toFixed(1)}
                      </span>
                    ) : (
                      <span className="text-xs text-gray-400">N/A</span>
                    )}
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex flex-wrap gap-1">
                      {cve.components && cve.components.length > 0 ? (
                        cve.components.slice(0, 3).map((component, idx) => (
                          <span
                            key={idx}
                            className="px-2 py-0.5 text-xs font-medium rounded-full bg-purple-100 text-purple-800"
                          >
                            {component}
                          </span>
                        ))
                      ) : (
                        <span className="text-xs text-gray-400">Unknown</span>
                      )}
                      {cve.components && cve.components.length > 3 && (
                        <span className="text-xs text-gray-500">+{cve.components.length - 3}</span>
                      )}
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <div className="text-sm text-gray-900 max-w-md truncate" title={cve.title}>
                      {cve.title}
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="flex items-center space-x-2">
                      {!cve.acknowledged && (
                        <button
                          onClick={(e) => handleAcknowledge(e, cve.id)}
                          disabled={isLoading}
                          className="inline-flex items-center px-2 py-1 text-xs font-medium text-green-700 bg-green-100 rounded hover:bg-green-200 disabled:opacity-50"
                          title="Mark as acknowledged"
                        >
                          <Check className="w-3 h-3 mr-1" />
                          Ack
                        </button>
                      )}
                      <button
                        onClick={(e) => handleDismiss(e, cve.id)}
                        disabled={isLoading}
                        className="inline-flex items-center px-2 py-1 text-xs font-medium text-gray-700 bg-gray-100 rounded hover:bg-gray-200 disabled:opacity-50"
                        title="Dismiss this CVE"
                      >
                        <X className="w-3 h-3 mr-1" />
                        Dismiss
                      </button>
                    </div>
                  </td>
                </tr>
                {isExpanded && (
                  <tr>
                    <td colSpan="7" className="px-6 py-4 bg-gray-50">
                      <div className="space-y-4">
                        <div>
                          <h4 className="text-sm font-semibold text-gray-700 mb-2">Description</h4>
                          <p className="text-sm text-gray-600">{cve.description || 'No description available.'}</p>
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                          <div>
                            <h4 className="text-sm font-semibold text-gray-700 mb-2">Affected Versions</h4>
                            {cve.affected_versions && cve.affected_versions.length > 0 ? (
                              <div className="flex flex-wrap gap-1">
                                {cve.affected_versions.map((version, idx) => (
                                  <span key={idx} className="px-2 py-0.5 text-xs font-medium rounded bg-red-50 text-red-700">
                                    {version}
                                  </span>
                                ))}
                              </div>
                            ) : (
                              <p className="text-sm text-gray-500">Not specified</p>
                            )}
                          </div>

                          <div>
                            <h4 className="text-sm font-semibold text-gray-700 mb-2">Fixed In Versions</h4>
                            {cve.fixed_versions && cve.fixed_versions.length > 0 ? (
                              <div className="flex flex-wrap gap-1">
                                {cve.fixed_versions.map((version, idx) => (
                                  <span key={idx} className="px-2 py-0.5 text-xs font-medium rounded bg-green-50 text-green-700">
                                    {version}
                                  </span>
                                ))}
                              </div>
                            ) : (
                              <p className="text-sm text-gray-500">Not specified</p>
                            )}
                          </div>
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                          <div>
                            <h4 className="text-sm font-semibold text-gray-700 mb-2">Published Date</h4>
                            <p className="text-sm text-gray-600">{formatDate(cve.published_date)}</p>
                          </div>

                          <div>
                            <h4 className="text-sm font-semibold text-gray-700 mb-2">Your Cluster Version</h4>
                            <span className="px-2 py-0.5 text-xs font-medium rounded bg-indigo-100 text-indigo-800">
                              {cve.cluster_version || 'Unknown'}
                            </span>
                          </div>

                          <div>
                            <h4 className="text-sm font-semibold text-gray-700 mb-2">Detected At</h4>
                            <p className="text-sm text-gray-600">{formatDate(cve.timestamp)}</p>
                          </div>
                        </div>

                        <div>
                          <h4 className="text-sm font-semibold text-gray-700 mb-2">References</h4>
                          <div className="flex flex-wrap gap-3">
                            {cve.external_url && (
                              <a
                                href={cve.external_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="inline-flex items-center text-sm text-blue-600 hover:text-blue-800 hover:underline"
                              >
                                <ExternalLink className="w-4 h-4 mr-1" />
                                CVE Record
                              </a>
                            )}
                            {cve.url && (
                              <a
                                href={cve.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="inline-flex items-center text-sm text-blue-600 hover:text-blue-800 hover:underline"
                              >
                                <ExternalLink className="w-4 h-4 mr-1" />
                                GitHub Issue
                              </a>
                            )}
                          </div>
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
    </div>
  );
};

export default CVETable;
