import React, { useState, useEffect, useCallback } from 'react';
import { Shield, ShieldCheck, ShieldAlert, X, Check, AlertTriangle, RefreshCw, Download, Settings2 } from 'lucide-react';
import { api } from '../services/api';

const CATEGORY_COLORS = {
  'Pod Security': {
    bg: 'bg-red-100 text-red-700',
    bgDark: 'bg-red-900/40 text-red-300',
    border: 'border-red-200',
    borderDark: 'border-red-800'
  },
  'Best Practices': {
    bg: 'bg-blue-100 text-blue-700',
    bgDark: 'bg-blue-900/40 text-blue-300',
    border: 'border-blue-200',
    borderDark: 'border-blue-800'
  },
  'Image Security': {
    bg: 'bg-amber-100 text-amber-700',
    bgDark: 'bg-amber-900/40 text-amber-300',
    border: 'border-amber-200',
    borderDark: 'border-amber-800'
  },
  'Networking': {
    bg: 'bg-emerald-100 text-emerald-700',
    bgDark: 'bg-emerald-900/40 text-emerald-300',
    border: 'border-emerald-200',
    borderDark: 'border-emerald-800'
  }
};

const SEVERITY_COLORS = {
  critical: { bg: 'bg-red-100 text-red-800', bgDark: 'bg-red-900/40 text-red-300' },
  high: { bg: 'bg-orange-100 text-orange-800', bgDark: 'bg-orange-900/40 text-orange-300' },
  medium: { bg: 'bg-yellow-100 text-yellow-800', bgDark: 'bg-yellow-900/40 text-yellow-300' },
  low: { bg: 'bg-green-100 text-green-800', bgDark: 'bg-green-900/40 text-green-300' }
};

const DEFAULT_CATEGORY_COLORS = {
  bg: 'bg-gray-100 text-gray-700',
  bgDark: 'bg-gray-700 text-gray-300',
  border: 'border-gray-200',
  borderDark: 'border-gray-700'
};

const KyvernoPolicies = ({ isDark = false }) => {
  const [kyvernoStatus, setKyvernoStatus] = useState(null);
  const [policies, setPolicies] = useState([]);
  const [violations, setViolations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [installing, setInstalling] = useState(false);
  const [reconciling, setReconciling] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  // Modal state
  const [selectedPolicy, setSelectedPolicy] = useState(null);
  const [modalConfig, setModalConfig] = useState(null);
  const [savingPolicy, setSavingPolicy] = useState(false);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const [statusData, policiesData] = await Promise.all([
        api.getKyvernoStatus(),
        api.getKyvernoPolicies().catch(() => [])
      ]);
      setKyvernoStatus(statusData);
      setPolicies(policiesData);

      if (statusData.installed) {
        const violationsData = await api.getKyvernoViolations().catch(() => []);
        setViolations(violationsData);
      }
    } catch (err) {
      setError('Failed to load Kyverno data');
      console.error('Error loading Kyverno data:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleInstall = async () => {
    try {
      setInstalling(true);
      setError(null);
      const result = await api.installKyverno();
      setSuccess(result.message || 'Kyverno installed successfully. It may take a minute to become fully ready.');
      setTimeout(() => setSuccess(null), 10000);
      await loadData();
    } catch (err) {
      setError(err.message || 'Failed to install Kyverno');
      console.error('Error installing Kyverno:', err);
    } finally {
      setInstalling(false);
    }
  };

  const handleReconcile = async () => {
    try {
      setReconciling(true);
      setError(null);
      await api.reconcileKyvernoPolicies();
      setSuccess('Policies reconciled successfully.');
      setTimeout(() => setSuccess(null), 3000);
      await loadData();
    } catch (err) {
      setError('Failed to reconcile policies');
      console.error('Error reconciling policies:', err);
    } finally {
      setReconciling(false);
    }
  };

  const handleToggleEnabled = async (policy, e) => {
    e.stopPropagation();
    const newEnabled = !policy.enabled;
    const config = {
      enabled: newEnabled,
      mode: policy.mode || 'audit',
      excluded_namespaces: policy.excluded_namespaces || [],
      excluded_deployments: policy.excluded_deployments || []
    };

    // Optimistic update
    setPolicies(prev => prev.map(p =>
      p.id === policy.id ? { ...p, enabled: newEnabled } : p
    ));

    try {
      await api.updateKyvernoPolicy(policy.id, config);
    } catch (err) {
      // Revert on error
      setPolicies(prev => prev.map(p =>
        p.id === policy.id ? { ...p, enabled: !newEnabled } : p
      ));
      setError(`Failed to update policy "${policy.display_name}"`);
      console.error('Error toggling policy:', err);
    }
  };

  const openModal = (policy) => {
    setSelectedPolicy(policy);
    setModalConfig({
      enabled: policy.enabled,
      mode: policy.mode || 'audit',
      excluded_namespaces: (policy.excluded_namespaces || []).join(', '),
      excluded_deployments: (policy.excluded_deployments || []).join(', ')
    });
  };

  const closeModal = () => {
    setSelectedPolicy(null);
    setModalConfig(null);
  };

  const handleModalSave = async () => {
    if (!selectedPolicy || !modalConfig) return;

    const config = {
      enabled: modalConfig.enabled,
      mode: modalConfig.mode,
      excluded_namespaces: modalConfig.excluded_namespaces
        .split(',')
        .map(s => s.trim())
        .filter(Boolean),
      excluded_deployments: modalConfig.excluded_deployments
        .split(',')
        .map(s => s.trim())
        .filter(Boolean)
    };

    try {
      setSavingPolicy(true);
      setError(null);
      const updated = await api.updateKyvernoPolicy(selectedPolicy.id, config);
      setPolicies(prev => prev.map(p =>
        p.id === selectedPolicy.id ? { ...p, ...updated } : p
      ));
      setSuccess(`Policy "${selectedPolicy.display_name}" updated successfully.`);
      setTimeout(() => setSuccess(null), 3000);
      closeModal();
    } catch (err) {
      setError(`Failed to update policy "${selectedPolicy.display_name}"`);
      console.error('Error saving policy:', err);
    } finally {
      setSavingPolicy(false);
    }
  };

  const groupedPolicies = policies.reduce((acc, policy) => {
    const category = policy.category || 'Other';
    if (!acc[category]) acc[category] = [];
    acc[category].push(policy);
    return acc;
  }, {});

  const activePoliciesCount = policies.filter(p => p.enabled).length;
  const totalViolationsCount = Array.isArray(violations) ? violations.length : 0;

  const getCategoryColor = (category) => {
    return CATEGORY_COLORS[category] || DEFAULT_CATEGORY_COLORS;
  };

  const getSeverityColor = (severity) => {
    return SEVERITY_COLORS[severity] || SEVERITY_COLORS.medium;
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
        <span className={`ml-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Loading Kyverno policies...</span>
      </div>
    );
  }

  // Kyverno not installed state
  if (kyvernoStatus && !kyvernoStatus.installed) {
    return (
      <div>
        <div className="mb-4 flex items-center">
          <Shield className="w-5 h-5 text-purple-500 mr-2" />
          <h2 className={`text-lg font-semibold ${isDark ? 'text-gray-100' : 'text-gray-900'}`}>Kyverno Policy Management</h2>
        </div>

        {error && (
          <div className={`border rounded-md p-3 mb-4 ${isDark ? 'bg-red-900/30 border-red-800' : 'bg-red-50 border-red-200'}`}>
            <div className="flex items-center">
              <ShieldAlert className="w-4 h-4 text-red-500 mr-2" />
              <span className={`text-sm ${isDark ? 'text-red-300' : 'text-red-800'}`}>{error}</span>
            </div>
          </div>
        )}

        {success && (
          <div className={`border rounded-md p-3 mb-4 ${isDark ? 'bg-green-900/30 border-green-800' : 'bg-green-50 border-green-200'}`}>
            <div className="flex items-center">
              <ShieldCheck className="w-4 h-4 text-green-500 mr-2" />
              <span className={`text-sm ${isDark ? 'text-green-300' : 'text-green-800'}`}>{success}</span>
            </div>
          </div>
        )}

        <div className={`border rounded-lg p-6 text-center ${isDark ? 'border-gray-700 bg-gray-800/50' : 'border-gray-200 bg-gray-50'}`}>
          <ShieldAlert className={`w-12 h-12 mx-auto mb-4 ${isDark ? 'text-gray-500' : 'text-gray-400'}`} />
          <h3 className={`text-lg font-medium mb-2 ${isDark ? 'text-gray-200' : 'text-gray-700'}`}>
            Kyverno is not installed
          </h3>
          <p className={`text-sm mb-6 max-w-md mx-auto ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
            Kyverno is a policy engine for Kubernetes that validates, mutates, and generates configurations.
            Install it to enforce security policies across your cluster.
          </p>
          <button
            onClick={handleInstall}
            disabled={installing}
            className="inline-flex items-center px-4 py-2 text-sm font-medium text-white bg-purple-600 border border-transparent rounded-md shadow-sm hover:bg-purple-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-purple-500 disabled:opacity-50"
          >
            {installing ? (
              <>
                <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin mr-2"></div>
                Installing...
              </>
            ) : (
              <>
                <Download className="w-4 h-4 mr-2" />
                Install Kyverno
              </>
            )}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center">
          <Shield className="w-5 h-5 text-purple-500 mr-2" />
          <h2 className={`text-lg font-semibold ${isDark ? 'text-gray-100' : 'text-gray-900'}`}>Kyverno Policy Management</h2>
        </div>
        <button
          onClick={handleReconcile}
          disabled={reconciling}
          className={`inline-flex items-center px-3 py-1.5 text-sm font-medium border rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-purple-500 disabled:opacity-50 ${isDark ? 'text-gray-300 bg-gray-700 border-gray-600 hover:bg-gray-600' : 'text-gray-700 bg-white border-gray-300 hover:bg-gray-50'}`}
        >
          <RefreshCw className={`w-4 h-4 mr-1.5 ${reconciling ? 'animate-spin' : ''}`} />
          Reconcile
        </button>
      </div>

      {/* Error / Success messages */}
      {error && (
        <div className={`border rounded-md p-3 mb-4 ${isDark ? 'bg-red-900/30 border-red-800' : 'bg-red-50 border-red-200'}`}>
          <div className="flex items-center">
            <ShieldAlert className="w-4 h-4 text-red-500 mr-2" />
            <span className={`text-sm ${isDark ? 'text-red-300' : 'text-red-800'}`}>{error}</span>
          </div>
        </div>
      )}

      {success && (
        <div className={`border rounded-md p-3 mb-4 ${isDark ? 'bg-green-900/30 border-green-800' : 'bg-green-50 border-green-200'}`}>
          <div className="flex items-center">
            <ShieldCheck className="w-4 h-4 text-green-500 mr-2" />
            <span className={`text-sm ${isDark ? 'text-green-300' : 'text-green-800'}`}>{success}</span>
          </div>
        </div>
      )}

      {/* Status Bar */}
      <div className={`border rounded-md p-4 mb-6 ${isDark ? 'border-gray-700 bg-gray-800/50' : 'border-gray-200 bg-gray-50'}`}>
        <div className="flex items-center gap-6 flex-wrap">
          {kyvernoStatus?.version && (
            <div className="flex items-center">
              <ShieldCheck className={`w-4 h-4 mr-2 ${isDark ? 'text-green-400' : 'text-green-600'}`} />
              <span className={`text-sm ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>
                Kyverno <span className="font-medium">{kyvernoStatus.version}</span>
              </span>
            </div>
          )}
          <div className="flex items-center">
            <Shield className={`w-4 h-4 mr-2 ${isDark ? 'text-blue-400' : 'text-blue-600'}`} />
            <span className={`text-sm ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>
              <span className="font-medium">{activePoliciesCount}</span> active {activePoliciesCount === 1 ? 'policy' : 'policies'}
            </span>
          </div>
          <div className="flex items-center">
            <AlertTriangle className={`w-4 h-4 mr-2 ${totalViolationsCount > 0 ? (isDark ? 'text-amber-400' : 'text-amber-600') : (isDark ? 'text-gray-500' : 'text-gray-400')}`} />
            <span className={`text-sm ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>
              <span className="font-medium">{totalViolationsCount}</span> {totalViolationsCount === 1 ? 'violation' : 'violations'}
            </span>
          </div>
        </div>
      </div>

      {/* Policy Grid grouped by category */}
      {Object.keys(groupedPolicies).length === 0 ? (
        <div className={`border rounded-md p-6 text-center ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
          <Shield className={`w-8 h-8 mx-auto mb-2 ${isDark ? 'text-gray-500' : 'text-gray-400'}`} />
          <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>No policies found. Click Reconcile to sync policies.</p>
        </div>
      ) : (
        <div className="space-y-6">
          {Object.entries(groupedPolicies).map(([category, categoryPolicies]) => {
            const catColor = getCategoryColor(category);
            return (
              <div key={category}>
                <h3 className={`text-sm font-semibold mb-3 ${isDark ? 'text-gray-200' : 'text-gray-700'}`}>
                  {category}
                  <span className={`ml-2 text-xs font-normal ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
                    ({categoryPolicies.length})
                  </span>
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                  {categoryPolicies.map(policy => {
                    const sevColor = getSeverityColor(policy.severity);
                    return (
                      <div
                        key={policy.id}
                        onClick={() => openModal(policy)}
                        className={`border rounded-lg p-4 cursor-pointer transition-all hover:shadow-md ${
                          isDark
                            ? 'border-gray-700 bg-gray-800 hover:border-gray-600'
                            : 'border-gray-200 bg-white hover:border-gray-300'
                        } ${!policy.enabled ? (isDark ? 'opacity-60' : 'opacity-70') : ''}`}
                      >
                        {/* Card header */}
                        <div className="flex items-start justify-between mb-2">
                          <h4 className={`text-sm font-medium leading-tight flex-1 mr-2 ${isDark ? 'text-gray-200' : 'text-gray-900'}`}>
                            {policy.display_name}
                          </h4>
                          <div onClick={(e) => e.stopPropagation()}>
                            <label className="relative inline-flex items-center cursor-pointer">
                              <input
                                type="checkbox"
                                checked={policy.enabled}
                                onChange={(e) => handleToggleEnabled(policy, e)}
                                className="sr-only peer"
                              />
                              <div className="w-9 h-5 bg-gray-200 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-purple-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-purple-600"></div>
                            </label>
                          </div>
                        </div>

                        {/* Badges */}
                        <div className="flex items-center gap-2 mb-2 flex-wrap">
                          <span className={`inline-flex items-center px-2 py-0.5 text-xs font-medium rounded-full ${isDark ? catColor.bgDark : catColor.bg}`}>
                            {category}
                          </span>
                          <span className={`inline-flex items-center px-2 py-0.5 text-xs font-medium rounded-full ${isDark ? sevColor.bgDark : sevColor.bg}`}>
                            {policy.severity}
                          </span>
                          <span className={`inline-flex items-center px-2 py-0.5 text-xs font-medium rounded-full ${
                            policy.mode === 'enforce'
                              ? isDark ? 'bg-orange-900/40 text-orange-300' : 'bg-orange-100 text-orange-700'
                              : isDark ? 'bg-blue-900/40 text-blue-300' : 'bg-blue-100 text-blue-700'
                          }`}>
                            {policy.mode || 'audit'}
                          </span>
                        </div>

                        {/* Description */}
                        <p className={`text-xs leading-relaxed line-clamp-2 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                          {policy.description}
                        </p>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Config Modal */}
      {selectedPolicy && modalConfig && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={closeModal}>
          <div
            className={`w-full max-w-lg mx-4 rounded-lg shadow-xl ${isDark ? 'bg-gray-800' : 'bg-white'}`}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal header */}
            <div className={`flex items-center justify-between px-6 py-4 border-b ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
              <div className="flex items-center">
                <Settings2 className={`w-5 h-5 mr-2 ${isDark ? 'text-purple-400' : 'text-purple-600'}`} />
                <h3 className={`text-lg font-semibold ${isDark ? 'text-gray-100' : 'text-gray-900'}`}>
                  {selectedPolicy.display_name}
                </h3>
              </div>
              <button
                onClick={closeModal}
                className={`p-1 rounded-md ${isDark ? 'text-gray-400 hover:text-gray-300 hover:bg-gray-700' : 'text-gray-500 hover:text-gray-700 hover:bg-gray-100'}`}
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal body */}
            <div className="px-6 py-4 space-y-5">
              {/* Description */}
              <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                {selectedPolicy.description}
              </p>

              {/* Enable/Disable toggle */}
              <div className="flex items-center justify-between">
                <label className={`text-sm font-medium ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                  Enabled
                </label>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input
                    type="checkbox"
                    checked={modalConfig.enabled}
                    onChange={(e) => setModalConfig(prev => ({ ...prev, enabled: e.target.checked }))}
                    className="sr-only peer"
                  />
                  <div className="w-9 h-5 bg-gray-200 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-purple-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-purple-600"></div>
                </label>
              </div>

              {/* Mode selector */}
              <div>
                <label className={`block text-sm font-medium mb-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                  Mode
                </label>
                <div className="flex items-center gap-4">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="radio"
                      name="policyMode"
                      value="audit"
                      checked={modalConfig.mode === 'audit'}
                      onChange={() => setModalConfig(prev => ({ ...prev, mode: 'audit' }))}
                      className="text-purple-600 focus:ring-purple-500"
                    />
                    <span className={`text-sm ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Audit</span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="radio"
                      name="policyMode"
                      value="enforce"
                      checked={modalConfig.mode === 'enforce'}
                      onChange={() => setModalConfig(prev => ({ ...prev, mode: 'enforce' }))}
                      className="text-purple-600 focus:ring-purple-500"
                    />
                    <span className={`text-sm ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Enforce</span>
                  </label>
                </div>
                {modalConfig.mode === 'enforce' && (
                  <div className={`mt-2 flex items-start gap-2 p-2 rounded-md text-xs ${isDark ? 'bg-orange-900/30 text-orange-300' : 'bg-orange-50 text-orange-700'}`}>
                    <AlertTriangle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
                    <span>Will block non-compliant deployments</span>
                  </div>
                )}
              </div>

              {/* Excluded namespaces */}
              <div>
                <label className={`block text-sm font-medium mb-1 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                  Excluded Namespaces
                </label>
                <input
                  type="text"
                  value={modalConfig.excluded_namespaces}
                  onChange={(e) => setModalConfig(prev => ({ ...prev, excluded_namespaces: e.target.value }))}
                  placeholder="e.g. kube-system, monitoring"
                  className={`w-full px-3 py-2 text-sm border rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-purple-500 ${isDark ? 'bg-gray-700 border-gray-600 text-gray-200 placeholder-gray-400' : 'bg-white border-gray-300 text-gray-900'}`}
                />
                <p className={`mt-1 text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
                  Comma-separated list of namespaces to exclude from this policy
                </p>
              </div>

              {/* Excluded deployments */}
              <div>
                <label className={`block text-sm font-medium mb-1 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                  Excluded Deployments
                </label>
                <input
                  type="text"
                  value={modalConfig.excluded_deployments}
                  onChange={(e) => setModalConfig(prev => ({ ...prev, excluded_deployments: e.target.value }))}
                  placeholder="e.g. legacy-app, debug-pod"
                  className={`w-full px-3 py-2 text-sm border rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-purple-500 ${isDark ? 'bg-gray-700 border-gray-600 text-gray-200 placeholder-gray-400' : 'bg-white border-gray-300 text-gray-900'}`}
                />
                <p className={`mt-1 text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
                  Comma-separated list of deployments to exclude from this policy
                </p>
              </div>
            </div>

            {/* Modal footer */}
            <div className={`flex items-center justify-end gap-2 px-6 py-4 border-t ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
              <button
                onClick={closeModal}
                className={`inline-flex items-center px-4 py-2 text-sm font-medium border rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-500 ${isDark ? 'text-gray-300 bg-gray-700 border-gray-600 hover:bg-gray-600' : 'text-gray-700 bg-white border-gray-300 hover:bg-gray-50'}`}
              >
                Cancel
              </button>
              <button
                onClick={handleModalSave}
                disabled={savingPolicy}
                className="inline-flex items-center px-4 py-2 text-sm font-medium text-white bg-purple-600 border border-transparent rounded-md shadow-sm hover:bg-purple-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-purple-500 disabled:opacity-50"
              >
                {savingPolicy ? (
                  <>
                    <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin mr-2"></div>
                    Saving...
                  </>
                ) : (
                  <>
                    <Check className="w-4 h-4 mr-2" />
                    Save
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default KyvernoPolicies;
