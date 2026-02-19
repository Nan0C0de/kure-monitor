import React, { useState, useEffect } from 'react';
import { Plus, Trash2, Shield } from 'lucide-react';
import { api } from '../../services/api';

const ExclusionRules = ({ isDark, onError, onSuccess }) => {
  // Per-resource rule state
  const [excludedRules, setExcludedRules] = useState([]);
  const [availableRuleTitles, setAvailableRuleTitles] = useState([]);
  const [allRuleTitles, setAllRuleTitles] = useState([]);
  const [newRuleTitle, setNewRuleTitle] = useState('');
  const [showRuleSuggestions, setShowRuleSuggestions] = useState(false);
  const [ruleNamespaceScope, setRuleNamespaceScope] = useState('');
  const [selectedRuleTitles, setSelectedRuleTitles] = useState([]);

  // Global rule state
  const [newGlobalRuleTitle, setNewGlobalRuleTitle] = useState('');
  const [showGlobalRuleSuggestions, setShowGlobalRuleSuggestions] = useState(false);
  const [selectedGlobalRuleTitles, setSelectedGlobalRuleTitles] = useState([]);

  // Namespace list for scope dropdown
  const [availableNamespaces, setAvailableNamespaces] = useState([]);

  useEffect(() => {
    const loadData = async () => {
      try {
        const [excludedRulesData, ruleTitlesData, namespacesData] = await Promise.all([
          api.getExcludedRules(),
          api.getAllRuleTitles(),
          api.getAllNamespaces()
        ]);
        setExcludedRules(excludedRulesData);
        setAvailableRuleTitles(ruleTitlesData);
        setAllRuleTitles(ruleTitlesData);
        setAvailableNamespaces(namespacesData);
      } catch (err) {
        onError('Failed to load rule data');
        console.error('Error loading rule data:', err);
      }
    };
    loadData();
  }, [onError]);

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

  // Global rule suggestions: base names (without ': ') that have container-specific variants
  // Uses allRuleTitles (unfiltered by namespace) since global exclusions are cluster-wide
  const globalRuleSuggestions = allRuleTitles.filter(title => {
    if (title.includes(': ')) return false;
    if (!allRuleTitles.some(t => t.startsWith(title + ': '))) return false;
    if (excludedRules.some(r => r.rule_title === title && !r.namespace)) return false;
    return true;
  });

  const filteredGlobalRuleSuggestions = newGlobalRuleTitle.trim()
    ? globalRuleSuggestions.filter(t => t.toLowerCase().includes(newGlobalRuleTitle.toLowerCase()))
    : globalRuleSuggestions;

  // Per-resource rule suggestions: specific titles (with ': ') and standalone rules
  // Uses availableRuleTitles (filtered by ruleNamespaceScope)
  const perResourceRuleSuggestions = availableRuleTitles.filter(title => {
    if (!title.includes(': ') && availableRuleTitles.some(t => t.startsWith(title + ': '))) return false;
    const scope = ruleNamespaceScope || null;
    if (excludedRules.some(r => r.rule_title === title && (r.namespace || null) === scope)) return false;
    if (title.includes(': ')) {
      const baseName = title.split(': ')[0];
      if (excludedRules.some(r => r.rule_title === baseName && (r.namespace || null) === scope)) return false;
    }
    return true;
  });

  const filteredPerResourceRuleSuggestions = newRuleTitle.trim()
    ? perResourceRuleSuggestions.filter(t => t.toLowerCase().includes(newRuleTitle.toLowerCase()))
    : perResourceRuleSuggestions;

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
      onError('Please select or enter at least one rule');
      return;
    }

    // Filter out already excluded
    titlesToExclude = titlesToExclude.filter(
      title => !excludedRules.some(rule => rule.rule_title === title && (rule.namespace || null) === namespace)
    );

    if (titlesToExclude.length === 0) {
      onError('Selected rules are already excluded for this scope');
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
      const scope = namespace ? ` in namespace "${namespace}"` : ' globally';
      const count = titlesToExclude.length;
      onSuccess(`${count} rule${count > 1 ? 's' : ''} excluded${scope}.`);
    } catch (err) {
      onError('Failed to add rule(s)');
      console.error('Error adding rules:', err);
    }
  };

  const handleRemoveRule = async (ruleTitle, namespace = null) => {
    try {
      await api.removeExcludedRule(ruleTitle, namespace);
      setExcludedRules(prev => prev.filter(rule =>
        !(rule.rule_title === ruleTitle && (rule.namespace || null) === namespace)
      ));
      const scope = namespace ? ` in namespace "${namespace}"` : ' (global)';
      onSuccess(`Rule "${ruleTitle}"${scope} will now be reported again`);
    } catch (err) {
      onError('Failed to remove rule');
      console.error('Error removing rule:', err);
    }
  };

  const handleRuleSubmit = (e) => {
    e.preventDefault();
    handleAddRule();
  };

  const toggleGlobalRuleSelection = (title) => {
    setSelectedGlobalRuleTitles(prev =>
      prev.includes(title) ? prev.filter(t => t !== title) : [...prev, title]
    );
  };

  const handleAddGlobalRule = async () => {
    let titlesToExclude = [...selectedGlobalRuleTitles];
    if (titlesToExclude.length === 0 && newGlobalRuleTitle.trim()) {
      titlesToExclude = [newGlobalRuleTitle.trim()];
    }

    if (titlesToExclude.length === 0) {
      onError('Please select or enter at least one rule');
      return;
    }

    titlesToExclude = titlesToExclude.filter(
      title => !excludedRules.some(rule => rule.rule_title === title && !rule.namespace)
    );

    if (titlesToExclude.length === 0) {
      onError('Selected rules are already excluded globally');
      return;
    }

    try {
      const results = await Promise.all(
        titlesToExclude.map(title => api.addExcludedRule(title, null))
      );
      setExcludedRules(prev => [...prev, ...results]);
      setNewGlobalRuleTitle('');
      setSelectedGlobalRuleTitles([]);
      setShowGlobalRuleSuggestions(false);
      const count = titlesToExclude.length;
      onSuccess(`${count} rule${count > 1 ? 's' : ''} excluded globally (all resources).`);
    } catch (err) {
      onError('Failed to add rule(s)');
      console.error('Error adding global rules:', err);
    }
  };

  const handleGlobalRuleSubmit = (e) => {
    e.preventDefault();
    handleAddGlobalRule();
  };

  const selectedRuleCount = selectedRuleTitles.length;
  const selectedGlobalRuleCount = selectedGlobalRuleTitles.length;

  return (
    <div>
      <div className="mb-4 flex items-center">
        <Shield className="w-5 h-5 text-purple-500 mr-2" />
        <h2 className={`text-lg font-semibold ${isDark ? 'text-gray-100' : 'text-gray-900'}`}>Security Rules</h2>
      </div>
      <p className={`text-sm mb-4 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
        Exclude specific security rules from scanning. Findings for excluded rules will be removed.
      </p>

      {/* Global Rule Exclusions */}
      <div className={`mb-4 p-4 border rounded-md ${isDark ? 'border-gray-700 bg-gray-800/50' : 'border-gray-200 bg-gray-50/50'}`}>
        <h3 className={`text-sm font-semibold mb-1 ${isDark ? 'text-purple-400' : 'text-purple-700'}`}>
          Global (all resources)
        </h3>
        <p className={`text-xs mb-3 ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
          Exclude a rule across all containers and resources cluster-wide.
        </p>
        <form onSubmit={handleGlobalRuleSubmit}>
          <div className="flex gap-2">
            <div className="relative flex-1">
              <input
                type="text"
                value={newGlobalRuleTitle}
                onChange={(e) => {
                  setNewGlobalRuleTitle(e.target.value);
                  setShowGlobalRuleSuggestions(true);
                }}
                onFocus={() => setShowGlobalRuleSuggestions(true)}
                onBlur={() => setTimeout(() => setShowGlobalRuleSuggestions(false), 200)}
                placeholder="Enter or select rule to exclude globally"
                className={`w-full px-3 py-2 text-sm border rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-purple-500 ${isDark ? 'bg-gray-700 border-gray-600 text-gray-200 placeholder-gray-400' : 'bg-white border-gray-300 text-gray-900'}`}
              />
              {showGlobalRuleSuggestions && filteredGlobalRuleSuggestions.length > 0 && (
                <div
                  className={`absolute z-10 w-full mt-1 border rounded-md shadow-lg max-h-48 overflow-y-auto ${isDark ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'}`}
                  onMouseDown={(e) => e.preventDefault()}
                >
                  <div className={`px-3 py-2 text-xs border-b flex items-center justify-between ${isDark ? 'text-gray-400 border-gray-700' : 'text-gray-500 border-gray-100'}`}>
                    <span>Rules with multiple resources</span>
                    {selectedGlobalRuleCount > 0 && (
                      <span className={`text-xs font-medium ${isDark ? 'text-purple-400' : 'text-purple-600'}`}>
                        {selectedGlobalRuleCount} selected
                      </span>
                    )}
                  </div>
                  {filteredGlobalRuleSuggestions.map(title => (
                    <label
                      key={title}
                      className={`w-full px-3 py-2 text-left text-sm flex items-center gap-2 cursor-pointer ${
                        selectedGlobalRuleTitles.includes(title)
                          ? isDark ? 'bg-purple-900/30 text-purple-300' : 'bg-purple-50 text-purple-700'
                          : isDark ? 'hover:bg-gray-700 hover:text-purple-400' : 'hover:bg-purple-50 hover:text-purple-700'
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={selectedGlobalRuleTitles.includes(title)}
                        onChange={() => toggleGlobalRuleSelection(title)}
                        className="rounded border-gray-300 text-purple-600 focus:ring-purple-500"
                      />
                      <span className="truncate font-medium">{title}</span>
                    </label>
                  ))}
                </div>
              )}
            </div>
            <button
              type="submit"
              className="inline-flex items-center px-4 py-2 text-sm font-medium text-white bg-purple-600 border border-transparent rounded-md shadow-sm hover:bg-purple-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-purple-500"
            >
              <Plus className="w-4 h-4 mr-1" />
              Exclude{selectedGlobalRuleCount > 0 ? ` (${selectedGlobalRuleCount})` : ''}
            </button>
          </div>
        </form>
      </div>

      {/* Per Resource Rule Exclusions */}
      <div className={`mb-4 p-4 border rounded-md ${isDark ? 'border-gray-700 bg-gray-800/50' : 'border-gray-200 bg-gray-50/50'}`}>
        <h3 className={`text-sm font-semibold mb-1 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
          Per resource
        </h3>
        <p className={`text-xs mb-3 ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
          Exclude a specific rule for a single container or resource.
        </p>
        <form onSubmit={handleRuleSubmit}>
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
                placeholder="Enter or select specific rule"
                className={`w-full px-3 py-2 text-sm border rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-purple-500 ${isDark ? 'bg-gray-700 border-gray-600 text-gray-200 placeholder-gray-400' : 'bg-white border-gray-300 text-gray-900'}`}
              />
              {showRuleSuggestions && filteredPerResourceRuleSuggestions.length > 0 && (
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
                  {filteredPerResourceRuleSuggestions.map(title => (
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
      </div>

      {/* Combined Excluded Rules List */}
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
  );
};

export default ExclusionRules;
