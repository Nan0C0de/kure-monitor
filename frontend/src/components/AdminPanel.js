import React, { useState, useEffect } from 'react';
import { Plus, Trash2, AlertCircle, CheckCircle, Shield, Activity, Bot, Bell, EyeOff, Clock, Settings } from 'lucide-react';
import { api } from '../services/api';
import NotificationSettings from './NotificationSettings';
import LLMSettings from './LLMSettings';

const AdminPanel = ({ isDark = false }) => {
  // Tab state
  const [activeTab, setActiveTab] = useState('ai');

  // Security Scan Namespace Exclusions state
  const [excludedNamespaces, setExcludedNamespaces] = useState([]);
  const [availableNamespaces, setAvailableNamespaces] = useState([]);
  const [newNamespace, setNewNamespace] = useState('');
  const [showNamespaceSuggestions, setShowNamespaceSuggestions] = useState(false);

  // Pod Monitoring Exclusions state
  const [excludedPods, setExcludedPods] = useState([]);
  const [monitoredPods, setMonitoredPods] = useState([]);
  const [newPodName, setNewPodName] = useState('');
  const [showPodSuggestions, setShowPodSuggestions] = useState(false);

  // Security Rule Exclusions state
  const [excludedRules, setExcludedRules] = useState([]);
  const [availableRuleTitles, setAvailableRuleTitles] = useState([]);
  const [newRuleTitle, setNewRuleTitle] = useState('');
  const [showRuleSuggestions, setShowRuleSuggestions] = useState(false);
  const [ruleNamespaceScope, setRuleNamespaceScope] = useState('');
  const [selectedRuleTitles, setSelectedRuleTitles] = useState([]);

  // History retention state (stored as minutes in backend)
  const [retentionEnabled, setRetentionEnabled] = useState(false);
  const [retentionValue, setRetentionValue] = useState(7);
  const [retentionUnit, setRetentionUnit] = useState('days');

  // General state
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [successMessage, setSuccessMessage] = useState(null);

  const tabs = [
    { id: 'ai', label: 'AI Config', icon: Bot },
    { id: 'notifications', label: 'Notifications', icon: Bell },
    { id: 'exclusions', label: 'Exclusions', icon: EyeOff },
    { id: 'settings', label: 'Settings', icon: Settings },
  ];

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      const [excluded, available, excludedPodsData, monitoredPodsData, excludedRulesData, ruleTitlesData, retentionData] = await Promise.all([
        api.getExcludedNamespaces(),
        api.getAllNamespaces(),
        api.getExcludedPods(),
        api.getMonitoredPods(),
        api.getExcludedRules(),
        api.getAllRuleTitles(),
        api.getHistoryRetention().catch(() => ({ hours: 0 }))
      ]);
      setExcludedNamespaces(excluded);
      setAvailableNamespaces(available);
      setExcludedPods(excludedPodsData);
      setMonitoredPods(monitoredPodsData);
      setExcludedRules(excludedRulesData);
      setAvailableRuleTitles(ruleTitlesData);
      const mins = retentionData.minutes || 0;
      if (mins > 0) {
        setRetentionEnabled(true);
        if (mins % 1440 === 0) {
          setRetentionValue(mins / 1440);
          setRetentionUnit('days');
        } else if (mins % 60 === 0) {
          setRetentionValue(mins / 60);
          setRetentionUnit('hours');
        } else {
          setRetentionValue(mins);
          setRetentionUnit('minutes');
        }
      } else {
        setRetentionEnabled(false);
        setRetentionValue(7);
        setRetentionUnit('days');
      }
      setError(null);
    } catch (err) {
      setError('Failed to load data');
      console.error('Error loading data:', err);
    } finally {
      setLoading(false);
    }
  };

  // Namespace suggestions: available namespaces that are not already excluded
  const namespaceSuggestions = availableNamespaces.filter(
    ns => !excludedNamespaces.some(excluded => excluded.namespace === ns)
  );

  const filteredNamespaceSuggestions = newNamespace.trim()
    ? namespaceSuggestions.filter(ns => ns.toLowerCase().includes(newNamespace.toLowerCase()))
    : namespaceSuggestions;

  // Pod suggestions: monitored pods that are not already excluded (by pod name only)
  const podSuggestions = monitoredPods.filter(
    pod => !excludedPods.some(excluded => excluded.pod_name === pod.pod_name)
  );

  const filteredPodSuggestions = newPodName.trim()
    ? podSuggestions.filter(pod =>
        pod.pod_name.toLowerCase().includes(newPodName.toLowerCase())
      )
    : podSuggestions;

  // Re-fetch rule titles when namespace scope changes
  useEffect(() => {
    const fetchRuleTitles = async () => {
      try {
        const titles = await api.getAllRuleTitles(ruleNamespaceScope || null);
        setAvailableRuleTitles(titles);
        setSelectedRuleTitles([]);
      } catch (err) {
        console.error('Error fetching rule titles:', err);
      }
    };
    fetchRuleTitles();
  }, [ruleNamespaceScope]);

  // Rule suggestions: available rule titles that are not already excluded (for current scope)
  const ruleSuggestions = availableRuleTitles.filter(
    title => !excludedRules.some(excluded => excluded.rule_title === title && (excluded.namespace || null) === (ruleNamespaceScope || null))
  );

  const filteredRuleSuggestions = newRuleTitle.trim()
    ? ruleSuggestions.filter(title => title.toLowerCase().includes(newRuleTitle.toLowerCase()))
    : ruleSuggestions;

  const handleAddNamespace = async (namespaceToAdd) => {
    const namespace = (namespaceToAdd || newNamespace).trim();

    if (!namespace) {
      setError('Please enter a namespace name');
      return;
    }

    if (excludedNamespaces.some(ns => ns.namespace === namespace)) {
      setError('This namespace is already excluded');
      return;
    }

    try {
      const result = await api.addExcludedNamespace(namespace);
      setExcludedNamespaces(prev => [...prev, result]);
      setNewNamespace('');
      setShowNamespaceSuggestions(false);
      setError(null);
      setSuccessMessage(`Namespace "${namespace}" excluded from security scan.`);
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (err) {
      setError('Failed to add namespace');
      console.error('Error adding namespace:', err);
    }
  };

  const handleRemoveNamespace = async (namespace) => {
    try {
      await api.removeExcludedNamespace(namespace);
      setExcludedNamespaces(prev => prev.filter(ns => ns.namespace !== namespace));
      setError(null);
      setSuccessMessage(`Namespace "${namespace}" will now be scanned again`);
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (err) {
      setError('Failed to remove namespace');
      console.error('Error removing namespace:', err);
    }
  };

  const handleAddPod = async (podToAdd) => {
    const podName = (podToAdd?.pod_name || newPodName).trim();

    if (!podName) {
      setError('Please enter a pod name');
      return;
    }

    if (excludedPods.some(pod => pod.pod_name === podName)) {
      setError('This pod is already excluded');
      return;
    }

    try {
      const result = await api.addExcludedPod(podName);
      setExcludedPods(prev => [...prev, result]);
      setNewPodName('');
      setShowPodSuggestions(false);
      setError(null);
      setSuccessMessage(`Pod "${podName}" excluded from monitoring.`);
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (err) {
      setError('Failed to add pod');
      console.error('Error adding pod:', err);
    }
  };

  const handleRemovePod = async (podName) => {
    try {
      await api.removeExcludedPod(podName);
      setExcludedPods(prev => prev.filter(pod => pod.pod_name !== podName));
      setError(null);
      setSuccessMessage(`Pod "${podName}" will now be monitored again`);
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (err) {
      setError('Failed to remove pod');
      console.error('Error removing pod:', err);
    }
  };

  const handleNamespaceSubmit = (e) => {
    e.preventDefault();
    handleAddNamespace();
  };

  const handlePodSubmit = (e) => {
    e.preventDefault();
    handleAddPod();
  };

  const toggleRuleSelection = (title) => {
    setSelectedRuleTitles(prev =>
      prev.includes(title) ? prev.filter(t => t !== title) : [...prev, title]
    );
  };

  const handleAddRule = async () => {
    const namespace = ruleNamespaceScope || null;

    // Collect titles: from checkboxes, or fall back to text input
    let titlesToExclude = [...selectedRuleTitles];
    if (titlesToExclude.length === 0 && newRuleTitle.trim()) {
      titlesToExclude = [newRuleTitle.trim()];
    }

    if (titlesToExclude.length === 0) {
      setError('Please select or enter at least one rule');
      return;
    }

    // Filter out already excluded
    titlesToExclude = titlesToExclude.filter(
      title => !excludedRules.some(rule => rule.rule_title === title && (rule.namespace || null) === namespace)
    );

    if (titlesToExclude.length === 0) {
      setError('Selected rules are already excluded for this scope');
      return;
    }

    try {
      const results = await Promise.all(
        titlesToExclude.map(title => api.addExcludedRule(title, namespace))
      );
      setExcludedRules(prev => [...prev, ...results]);
      setNewRuleTitle('');
      setSelectedRuleTitles([]);
      setShowRuleSuggestions(false);
      setError(null);
      const scope = namespace ? ` in namespace "${namespace}"` : ' globally';
      const count = titlesToExclude.length;
      setSuccessMessage(`${count} rule${count > 1 ? 's' : ''} excluded${scope}.`);
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (err) {
      setError('Failed to add rule(s)');
      console.error('Error adding rules:', err);
    }
  };

  const handleRemoveRule = async (ruleTitle, namespace = null) => {
    try {
      await api.removeExcludedRule(ruleTitle, namespace);
      setExcludedRules(prev => prev.filter(rule =>
        !(rule.rule_title === ruleTitle && (rule.namespace || null) === namespace)
      ));
      setError(null);
      const scope = namespace ? ` in namespace "${namespace}"` : ' (global)';
      setSuccessMessage(`Rule "${ruleTitle}"${scope} will now be reported again`);
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (err) {
      setError('Failed to remove rule');
      console.error('Error removing rule:', err);
    }
  };

  const handleRuleSubmit = (e) => {
    e.preventDefault();
    handleAddRule();
  };

  const toMinutes = (value, unit) => {
    switch (unit) {
      case 'minutes': return value;
      case 'hours': return value * 60;
      case 'days': return value * 1440;
      default: return value;
    }
  };

  const getMaxValue = (unit) => {
    switch (unit) {
      case 'minutes': return 43200;
      case 'hours': return 720;
      case 'days': return 30;
      default: return 43200;
    }
  };

  const handleRetentionSave = async (enabled, value, unit) => {
    try {
      const minutes = enabled ? toMinutes(value, unit) : 0;
      if (enabled && (minutes < 1 || minutes > 43200)) {
        setError('Retention must be between 1 minute and 30 days');
        return;
      }
      await api.setHistoryRetention(minutes);
      setError(null);
      if (!enabled) {
        setSuccessMessage('History auto-delete disabled.');
      } else {
        setSuccessMessage(`Resolved pods will be auto-deleted after ${value} ${unit}.`);
      }
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (err) {
      setError('Failed to update retention setting');
      console.error('Error updating retention:', err);
    }
  };

  const selectedRuleCount = selectedRuleTitles.length;

  if (loading) {
    return (
      <div className="p-6">
        <div className="flex items-center justify-center py-8">
          <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
          <span className={`ml-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Loading...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6">
      {/* Tab Navigation */}
      <div className={`flex border-b mb-6 ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                isActive
                  ? isDark
                    ? 'border-purple-500 text-purple-400'
                    : 'border-purple-600 text-purple-600'
                  : isDark
                    ? 'border-transparent text-gray-400 hover:text-gray-300 hover:border-gray-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              <Icon className="w-4 h-4 mr-2" />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Error/Success Messages */}
      {error && (
        <div className={`border rounded-md p-3 mb-4 ${isDark ? 'bg-red-900/30 border-red-800' : 'bg-red-50 border-red-200'}`}>
          <div className="flex items-center">
            <AlertCircle className="w-4 h-4 text-red-500 mr-2" />
            <span className={`text-sm ${isDark ? 'text-red-300' : 'text-red-800'}`}>{error}</span>
          </div>
        </div>
      )}

      {successMessage && (
        <div className={`border rounded-md p-3 mb-4 ${isDark ? 'bg-green-900/30 border-green-800' : 'bg-green-50 border-green-200'}`}>
          <div className="flex items-center">
            <CheckCircle className="w-4 h-4 text-green-500 mr-2" />
            <span className={`text-sm ${isDark ? 'text-green-300' : 'text-green-800'}`}>{successMessage}</span>
          </div>
        </div>
      )}

      {/* Tab Content */}
      {activeTab === 'ai' && <LLMSettings isDark={isDark} />}

      {activeTab === 'notifications' && <NotificationSettings isDark={isDark} />}

      {activeTab === 'settings' && (
        <div className="space-y-8">
          {/* History Retention */}
          <div>
            <div className="mb-4 flex items-center">
              <Clock className="w-5 h-5 text-green-500 mr-2" />
              <h2 className={`text-lg font-semibold ${isDark ? 'text-gray-100' : 'text-gray-900'}`}>History Retention</h2>
            </div>
            <p className={`text-sm mb-4 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
              Automatically delete resolved pods from history after a set period. Ignored pods are not affected by this setting.
            </p>

            <div className="flex items-center gap-4">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={retentionEnabled}
                  onChange={(e) => {
                    const enabled = e.target.checked;
                    setRetentionEnabled(enabled);
                    handleRetentionSave(enabled, retentionValue, retentionUnit);
                  }}
                  className="h-4 w-4 text-green-600 rounded border-gray-300 focus:ring-green-500"
                />
                <span className={`text-sm font-medium ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                  Auto-delete resolved pods after
                </span>
              </label>

              <input
                type="number"
                min={1}
                max={getMaxValue(retentionUnit)}
                value={retentionValue}
                disabled={!retentionEnabled}
                onChange={(e) => {
                  const val = parseInt(e.target.value) || 1;
                  setRetentionValue(val);
                }}
                onBlur={() => {
                  const clamped = Math.max(1, Math.min(retentionValue, getMaxValue(retentionUnit)));
                  setRetentionValue(clamped);
                  if (retentionEnabled) handleRetentionSave(true, clamped, retentionUnit);
                }}
                className={`w-20 px-3 py-2 text-sm border rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-green-500 disabled:opacity-50 ${
                  isDark ? 'bg-gray-700 border-gray-600 text-gray-200' : 'bg-white border-gray-300 text-gray-900'
                }`}
              />

              <select
                value={retentionUnit}
                disabled={!retentionEnabled}
                onChange={(e) => {
                  const newUnit = e.target.value;
                  const maxVal = newUnit === 'minutes' ? 43200 : newUnit === 'hours' ? 720 : 30;
                  const clamped = Math.min(retentionValue, maxVal);
                  setRetentionUnit(newUnit);
                  setRetentionValue(clamped);
                  if (retentionEnabled) handleRetentionSave(true, clamped, newUnit);
                }}
                className={`px-3 py-2 text-sm border rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-green-500 disabled:opacity-50 ${
                  isDark ? 'bg-gray-700 border-gray-600 text-gray-200' : 'bg-white border-gray-300 text-gray-900'
                }`}
              >
                <option value="minutes">minutes</option>
                <option value="hours">hours</option>
                <option value="days">days</option>
              </select>
            </div>

            {retentionEnabled && (
              <div className={`mt-3 text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
                The cleanup runs every minute. Resolved pods older than the configured period will be permanently deleted.
              </div>
            )}
          </div>
        </div>
      )}

      {activeTab === 'exclusions' && (
        <div className="space-y-8">
          {/* Security Scan Namespace Exclusions */}
          <div>
            <div className="mb-4 flex items-center">
              <Shield className="w-5 h-5 text-orange-500 mr-2" />
              <h2 className={`text-lg font-semibold ${isDark ? 'text-gray-100' : 'text-gray-900'}`}>Namespaces (Security Scan)</h2>
            </div>
            <p className={`text-sm mb-4 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
              Exclude namespaces from security scanning. System namespaces are always excluded by default.
            </p>

            <form onSubmit={handleNamespaceSubmit} className="mb-4">
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <input
                    type="text"
                    value={newNamespace}
                    onChange={(e) => {
                      setNewNamespace(e.target.value);
                      setShowNamespaceSuggestions(true);
                    }}
                    onFocus={() => setShowNamespaceSuggestions(true)}
                    onBlur={() => setTimeout(() => setShowNamespaceSuggestions(false), 200)}
                    placeholder="Enter or select namespace"
                    className={`w-full px-3 py-2 text-sm border rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 ${isDark ? 'bg-gray-700 border-gray-600 text-gray-200 placeholder-gray-400' : 'bg-white border-gray-300 text-gray-900'}`}
                  />
                  {showNamespaceSuggestions && filteredNamespaceSuggestions.length > 0 && (
                    <div className={`absolute z-10 w-full mt-1 border rounded-md shadow-lg max-h-48 overflow-y-auto ${isDark ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'}`}>
                      <div className={`px-3 py-2 text-xs border-b ${isDark ? 'text-gray-400 border-gray-700' : 'text-gray-500 border-gray-100'}`}>
                        Available namespaces
                      </div>
                      {filteredNamespaceSuggestions.map(ns => (
                        <button
                          key={ns}
                          type="button"
                          onClick={() => handleAddNamespace(ns)}
                          className={`w-full px-3 py-2 text-left text-sm focus:outline-none ${isDark ? 'hover:bg-gray-700 hover:text-blue-400 focus:bg-gray-700' : 'hover:bg-blue-50 hover:text-blue-700 focus:bg-blue-50'}`}
                        >
                          {ns}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
                <button
                  type="submit"
                  className="inline-flex items-center px-4 py-2 text-sm font-medium text-white bg-orange-600 border border-transparent rounded-md shadow-sm hover:bg-orange-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-orange-500"
                >
                  <Plus className="w-4 h-4 mr-1" />
                  Exclude
                </button>
              </div>
            </form>

            <div className={`border rounded-md ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
              <div className={`px-4 py-3 border-b ${isDark ? 'bg-gray-900 border-gray-700' : 'bg-gray-50 border-gray-200'}`}>
                <h3 className={`text-sm font-medium ${isDark ? 'text-gray-200' : 'text-gray-700'}`}>
                  Excluded Namespaces ({excludedNamespaces.length})
                </h3>
              </div>

              {excludedNamespaces.length === 0 ? (
                <div className={`px-4 py-6 text-center ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                  <p className="text-sm">No namespaces excluded.</p>
                </div>
              ) : (
                <ul className={`divide-y ${isDark ? 'divide-gray-700' : 'divide-gray-200'}`}>
                  {excludedNamespaces.map((ns) => (
                    <li key={ns.namespace} className={`px-4 py-3 flex items-center justify-between ${isDark ? 'hover:bg-gray-800' : 'hover:bg-gray-50'}`}>
                      <div>
                        <span className={`text-sm font-medium ${isDark ? 'text-gray-200' : 'text-gray-900'}`}>{ns.namespace}</span>
                        {ns.created_at && (
                          <span className={`ml-2 text-xs ${isDark ? 'text-gray-500' : 'text-gray-500'}`}>
                            Added {new Date(ns.created_at).toLocaleDateString()}
                          </span>
                        )}
                      </div>
                      <button
                        onClick={() => handleRemoveNamespace(ns.namespace)}
                        className="inline-flex items-center px-2 py-1 text-xs font-medium text-red-700 bg-red-50 border border-red-200 rounded hover:bg-red-100 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500"
                      >
                        <Trash2 className="w-3 h-3 mr-1" />
                        Remove
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>

          {/* Pod Monitoring Exclusions */}
          <div>
            <div className="mb-4 flex items-center">
              <Activity className="w-5 h-5 text-blue-500 mr-2" />
              <h2 className={`text-lg font-semibold ${isDark ? 'text-gray-100' : 'text-gray-900'}`}>Pods (Failure Monitoring)</h2>
            </div>
            <p className={`text-sm mb-4 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
              Exclude pods from failure monitoring across all namespaces.
            </p>

            <form onSubmit={handlePodSubmit} className="mb-4">
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <input
                    type="text"
                    value={newPodName}
                    onChange={(e) => {
                      setNewPodName(e.target.value);
                      setShowPodSuggestions(true);
                    }}
                    onFocus={() => setShowPodSuggestions(true)}
                    onBlur={() => setTimeout(() => setShowPodSuggestions(false), 200)}
                    placeholder="Enter or select pod name"
                    className={`w-full px-3 py-2 text-sm border rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 ${isDark ? 'bg-gray-700 border-gray-600 text-gray-200 placeholder-gray-400' : 'bg-white border-gray-300 text-gray-900'}`}
                  />
                  {showPodSuggestions && filteredPodSuggestions.length > 0 && (
                    <div className={`absolute z-10 w-full mt-1 border rounded-md shadow-lg max-h-48 overflow-y-auto ${isDark ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'}`}>
                      <div className={`px-3 py-2 text-xs border-b ${isDark ? 'text-gray-400 border-gray-700' : 'text-gray-500 border-gray-100'}`}>
                        Monitored pods with issues
                      </div>
                      {filteredPodSuggestions.map(pod => (
                        <button
                          key={pod.pod_name}
                          type="button"
                          onClick={() => handleAddPod(pod)}
                          className={`w-full px-3 py-2 text-left text-sm focus:outline-none ${isDark ? 'hover:bg-gray-700 hover:text-blue-400 focus:bg-gray-700' : 'hover:bg-blue-50 hover:text-blue-700 focus:bg-blue-50'}`}
                        >
                          <span className="font-medium">{pod.pod_name}</span>
                          <span className={`text-xs ml-2 ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>({pod.namespace})</span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
                <button
                  type="submit"
                  className="inline-flex items-center px-4 py-2 text-sm font-medium text-white bg-blue-600 border border-transparent rounded-md shadow-sm hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
                >
                  <Plus className="w-4 h-4 mr-1" />
                  Exclude
                </button>
              </div>
            </form>

            <div className={`border rounded-md ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
              <div className={`px-4 py-3 border-b ${isDark ? 'bg-gray-900 border-gray-700' : 'bg-gray-50 border-gray-200'}`}>
                <h3 className={`text-sm font-medium ${isDark ? 'text-gray-200' : 'text-gray-700'}`}>
                  Excluded Pods ({excludedPods.length})
                </h3>
              </div>

              {excludedPods.length === 0 ? (
                <div className={`px-4 py-6 text-center ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                  <p className="text-sm">No pods excluded.</p>
                </div>
              ) : (
                <ul className={`divide-y ${isDark ? 'divide-gray-700' : 'divide-gray-200'}`}>
                  {excludedPods.map((pod) => (
                    <li key={pod.pod_name} className={`px-4 py-3 flex items-center justify-between ${isDark ? 'hover:bg-gray-800' : 'hover:bg-gray-50'}`}>
                      <div>
                        <span className={`text-sm font-medium ${isDark ? 'text-gray-200' : 'text-gray-900'}`}>{pod.pod_name}</span>
                        {pod.created_at && (
                          <span className={`ml-2 text-xs ${isDark ? 'text-gray-500' : 'text-gray-500'}`}>
                            Added {new Date(pod.created_at).toLocaleDateString()}
                          </span>
                        )}
                      </div>
                      <button
                        onClick={() => handleRemovePod(pod.pod_name)}
                        className="inline-flex items-center px-2 py-1 text-xs font-medium text-red-700 bg-red-50 border border-red-200 rounded hover:bg-red-100 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500"
                      >
                        <Trash2 className="w-3 h-3 mr-1" />
                        Remove
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>

          {/* Security Rule Exclusions */}
          <div>
            <div className="mb-4 flex items-center">
              <Shield className="w-5 h-5 text-purple-500 mr-2" />
              <h2 className={`text-lg font-semibold ${isDark ? 'text-gray-100' : 'text-gray-900'}`}>Security Rules</h2>
            </div>
            <p className={`text-sm mb-4 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
              Exclude specific security rules from scanning. Findings for excluded rules will be removed.
            </p>

            <form onSubmit={handleRuleSubmit} className="mb-4">
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <input
                    type="text"
                    value={newRuleTitle}
                    onChange={(e) => {
                      setNewRuleTitle(e.target.value);
                      setShowRuleSuggestions(true);
                    }}
                    onFocus={() => setShowRuleSuggestions(true)}
                    onBlur={() => setTimeout(() => setShowRuleSuggestions(false), 200)}
                    placeholder="Enter or select security rule"
                    className={`w-full px-3 py-2 text-sm border rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-purple-500 ${isDark ? 'bg-gray-700 border-gray-600 text-gray-200 placeholder-gray-400' : 'bg-white border-gray-300 text-gray-900'}`}
                  />
                  {showRuleSuggestions && filteredRuleSuggestions.length > 0 && (
                    <div
                      className={`absolute z-10 w-full mt-1 border rounded-md shadow-lg max-h-48 overflow-y-auto ${isDark ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'}`}
                      onMouseDown={(e) => e.preventDefault()}
                    >
                      <div className={`px-3 py-2 text-xs border-b flex items-center justify-between ${isDark ? 'text-gray-400 border-gray-700' : 'text-gray-500 border-gray-100'}`}>
                        <span>Active security rules</span>
                        {selectedRuleCount > 0 && (
                          <span className={`text-xs font-medium ${isDark ? 'text-purple-400' : 'text-purple-600'}`}>
                            {selectedRuleCount} selected
                          </span>
                        )}
                      </div>
                      {filteredRuleSuggestions.map(title => (
                        <label
                          key={title}
                          className={`w-full px-3 py-2 text-left text-sm flex items-center gap-2 cursor-pointer ${
                            selectedRuleTitles.includes(title)
                              ? isDark ? 'bg-purple-900/30 text-purple-300' : 'bg-purple-50 text-purple-700'
                              : isDark ? 'hover:bg-gray-700 hover:text-purple-400' : 'hover:bg-purple-50 hover:text-purple-700'
                          }`}
                        >
                          <input
                            type="checkbox"
                            checked={selectedRuleTitles.includes(title)}
                            onChange={() => toggleRuleSelection(title)}
                            className="rounded border-gray-300 text-purple-600 focus:ring-purple-500"
                          />
                          <span className="truncate">{title}</span>
                        </label>
                      ))}
                    </div>
                  )}
                </div>
                <select
                  value={ruleNamespaceScope}
                  onChange={(e) => setRuleNamespaceScope(e.target.value)}
                  className={`px-3 py-2 text-sm border rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-purple-500 ${isDark ? 'bg-gray-700 border-gray-600 text-gray-200' : 'bg-white border-gray-300 text-gray-900'}`}
                >
                  <option value="">All namespaces</option>
                  {availableNamespaces.map(ns => (
                    <option key={ns} value={ns}>{ns}</option>
                  ))}
                </select>
                <button
                  type="submit"
                  className="inline-flex items-center px-4 py-2 text-sm font-medium text-white bg-purple-600 border border-transparent rounded-md shadow-sm hover:bg-purple-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-purple-500"
                >
                  <Plus className="w-4 h-4 mr-1" />
                  Exclude{selectedRuleCount > 0 ? ` (${selectedRuleCount})` : ''}
                </button>
              </div>
            </form>

            <div className={`border rounded-md ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
              <div className={`px-4 py-3 border-b ${isDark ? 'bg-gray-900 border-gray-700' : 'bg-gray-50 border-gray-200'}`}>
                <h3 className={`text-sm font-medium ${isDark ? 'text-gray-200' : 'text-gray-700'}`}>
                  Excluded Rules ({excludedRules.length})
                </h3>
              </div>

              {excludedRules.length === 0 ? (
                <div className={`px-4 py-6 text-center ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                  <p className="text-sm">No rules excluded.</p>
                </div>
              ) : (
                <ul className={`divide-y ${isDark ? 'divide-gray-700' : 'divide-gray-200'}`}>
                  {excludedRules.map((rule) => (
                    <li key={`${rule.rule_title}-${rule.namespace || 'global'}`} className={`px-4 py-3 flex items-center justify-between ${isDark ? 'hover:bg-gray-800' : 'hover:bg-gray-50'}`}>
                      <div>
                        <span className={`text-sm font-medium ${isDark ? 'text-gray-200' : 'text-gray-900'}`}>{rule.rule_title}</span>
                        <span className={`ml-2 text-xs px-2 py-0.5 rounded-full ${
                          rule.namespace
                            ? isDark ? 'bg-blue-900/40 text-blue-300' : 'bg-blue-100 text-blue-700'
                            : isDark ? 'bg-gray-700 text-gray-400' : 'bg-gray-200 text-gray-600'
                        }`}>
                          {rule.namespace || 'Global'}
                        </span>
                        {rule.created_at && (
                          <span className={`ml-2 text-xs ${isDark ? 'text-gray-500' : 'text-gray-500'}`}>
                            Added {new Date(rule.created_at).toLocaleDateString()}
                          </span>
                        )}
                      </div>
                      <button
                        onClick={() => handleRemoveRule(rule.rule_title, rule.namespace || null)}
                        className="inline-flex items-center px-2 py-1 text-xs font-medium text-red-700 bg-red-50 border border-red-200 rounded hover:bg-red-100 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500"
                      >
                        <Trash2 className="w-3 h-3 mr-1" />
                        Remove
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AdminPanel;
