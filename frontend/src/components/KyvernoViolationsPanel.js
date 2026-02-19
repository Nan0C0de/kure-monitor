import React, { useState, useMemo } from 'react';
import { ShieldAlert, ChevronDown, ChevronUp } from 'lucide-react';

const KyvernoViolationsPanel = ({ isDark = false, violations = [] }) => {
  const [isExpanded, setIsExpanded] = useState(true);

  const getSeverityBadge = (severity) => {
    switch (severity?.toLowerCase()) {
      case 'high':
        return isDark
          ? 'bg-red-900 text-red-200 border-red-700'
          : 'bg-red-100 text-red-800 border-red-300';
      case 'medium':
        return isDark
          ? 'bg-yellow-900 text-yellow-200 border-yellow-700'
          : 'bg-yellow-100 text-yellow-800 border-yellow-300';
      case 'low':
        return isDark
          ? 'bg-blue-900 text-blue-200 border-blue-700'
          : 'bg-blue-100 text-blue-800 border-blue-300';
      default:
        return isDark
          ? 'bg-gray-700 text-gray-200 border-gray-600'
          : 'bg-gray-100 text-gray-800 border-gray-300';
    }
  };

  // Group violations by policy_name, preserving order of first appearance
  const groupedViolations = useMemo(() => {
    const groups = [];
    const seen = new Map();
    violations.forEach((v) => {
      const key = v.policy_name;
      if (!seen.has(key)) {
        seen.set(key, groups.length);
        groups.push({ policyName: key, items: [v] });
      } else {
        groups[seen.get(key)].items.push(v);
      }
    });
    return groups;
  }, [violations]);

  if (violations.length === 0) {
    return (
      <div className={`mb-6 rounded-lg border ${isDark ? 'border-gray-700 bg-gray-800' : 'border-gray-200 bg-white'}`}>
        <div className="flex items-center justify-between px-4 py-3">
          <div className="flex items-center space-x-2">
            <ShieldAlert className={`w-5 h-5 ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
            <span className={`text-sm font-medium ${isDark ? 'text-gray-200' : 'text-gray-700'}`}>Policy Violations</span>
            <span className={`py-0.5 px-2 rounded-full text-xs font-medium ${isDark ? 'bg-gray-700 text-gray-300' : 'bg-gray-100 text-gray-600'}`}>0</span>
          </div>
        </div>
        <div className={`px-4 py-6 text-center border-t ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
          <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>No policy violations detected</p>
        </div>
      </div>
    );
  }

  return (
    <div className={`mb-6 rounded-lg border ${isDark ? 'border-gray-700 bg-gray-800' : 'border-gray-200 bg-white'}`}>
      {/* Header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className={`w-full flex items-center justify-between px-4 py-3 rounded-t-lg transition-colors ${
          isDark ? 'hover:bg-gray-700' : 'hover:bg-gray-50'
        }`}
      >
        <div className="flex items-center space-x-2">
          <ShieldAlert className={`w-5 h-5 ${isDark ? 'text-orange-400' : 'text-orange-500'}`} />
          <span className={`text-sm font-medium ${isDark ? 'text-gray-200' : 'text-gray-700'}`}>Policy Violations</span>
          <span className={`py-0.5 px-2 rounded-full text-xs font-medium ${isDark ? 'bg-orange-900 text-orange-200' : 'bg-orange-100 text-orange-800'}`}>
            {violations.length}
          </span>
        </div>
        {isExpanded ? (
          <ChevronUp className={`w-5 h-5 ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
        ) : (
          <ChevronDown className={`w-5 h-5 ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
        )}
      </button>

      {/* Table */}
      {isExpanded && (
        <div className={`overflow-x-auto border-t ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
          <table className={`min-w-full divide-y ${isDark ? 'divide-gray-700' : 'divide-gray-200'}`}>
            <thead className={isDark ? 'bg-gray-900' : 'bg-gray-50'}>
              <tr>
                <th className={`px-6 py-3 text-left text-xs font-medium uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                  Policy
                </th>
                <th className={`px-6 py-3 text-left text-xs font-medium uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                  Rule
                </th>
                <th className={`px-6 py-3 text-left text-xs font-medium uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                  Resource
                </th>
                <th className={`px-6 py-3 text-left text-xs font-medium uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                  Namespace
                </th>
                <th className={`px-6 py-3 text-left text-xs font-medium uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                  Message
                </th>
                <th className={`px-6 py-3 text-left text-xs font-medium uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                  Severity
                </th>
              </tr>
            </thead>
            <tbody className={`divide-y ${isDark ? 'bg-gray-800 divide-gray-700' : 'bg-white divide-gray-200'}`}>
              {groupedViolations.map((group, groupIdx) => (
                <React.Fragment key={group.policyName}>
                  {groupIdx > 0 && (
                    <tr>
                      <td colSpan="6" className={`h-px ${isDark ? 'bg-gray-600' : 'bg-gray-300'}`} />
                    </tr>
                  )}
                  {group.items.map((violation, idx) => (
                    <tr
                      key={`${violation.policy_name}-${violation.rule_name}-${violation.resource_namespace}-${violation.resource_name}-${idx}`}
                      className={isDark ? 'hover:bg-gray-700' : 'hover:bg-gray-50'}
                    >
                      <td className={`px-6 py-4 whitespace-nowrap text-sm font-medium ${isDark ? 'text-gray-200' : 'text-gray-900'}`}>
                        {violation.policy_name}
                      </td>
                      <td className={`px-6 py-4 whitespace-nowrap text-sm ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                        {violation.rule_name}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div>
                          <div className={`text-sm font-medium ${isDark ? 'text-gray-200' : 'text-gray-900'}`}>
                            {violation.resource_name}
                          </div>
                          <div className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                            {violation.resource_kind}
                          </div>
                        </div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <span className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${isDark ? 'bg-indigo-900 text-indigo-300' : 'bg-indigo-100 text-indigo-800'}`}>
                          {violation.resource_namespace}
                        </span>
                      </td>
                      <td className={`px-6 py-4 text-sm ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>
                        {violation.message}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <span className={`inline-flex px-2.5 py-0.5 rounded-full text-xs font-medium border ${getSeverityBadge(violation.severity)}`}>
                          {(violation.severity || 'unknown').toUpperCase()}
                        </span>
                      </td>
                    </tr>
                  ))}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default KyvernoViolationsPanel;
