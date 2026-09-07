import React, { useState, useEffect, useRef } from 'react';
import { Bot, Save, Trash2, CheckCircle, AlertCircle, Loader2, Eye, EyeOff, Search, Edit, FileText, Star, Plus, Download, Upload } from 'lucide-react';
import { api } from '../services/api';

const LLMSettings = ({ isDark = false, onConfigChange }) => {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [showApiKey, setShowApiKey] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [discoveryLoading, setDiscoveryLoading] = useState(false);
  const [discoveredEndpoints, setDiscoveredEndpoints] = useState([]);
  const [pendingEndpoint, setPendingEndpoint] = useState(null);
  const [pendingApiKey, setPendingApiKey] = useState('');
  const [testingPhase, setTestingPhase] = useState('');

  // Multi-LLM configs state
  const [configsList, setConfigsList] = useState([]);
  const [defaultConfigId, setDefaultConfigId] = useState(null);
  const [showAddForm, setShowAddForm] = useState(false);
  const [editingConfigId, setEditingConfigId] = useState(null);
  const [testingConfigId, setTestingConfigId] = useState(null);
  const [configName, setConfigName] = useState('');
  const [isDefaultCheckbox, setIsDefaultCheckbox] = useState(false);

  // Form state
  const [provider, setProvider] = useState('anthropic');
  const [apiKey, setApiKey] = useState('');
  const [model, setModel] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [isCustomModelInput, setIsCustomModelInput] = useState(false);
  const [isEditing, setIsEditing] = useState(false);

  // Custom Instructions state
  const [customInstructions, setCustomInstructions] = useState('');
  const [savingInstructions, setSavingInstructions] = useState(false);
  const [instructionsSuccess, setInstructionsSuccess] = useState(null);
  const [instructionsError, setInstructionsError] = useState(null);
  const fileInputRef = useRef(null);

  const providers = [
    {
      value: 'anthropic',
      label: 'Anthropic',
      trust: 'external',
      trustLabel: 'External - data sent to Anthropic',
      needsApiKey: false,
      optionalApiKey: true,
      needsBaseUrl: true,
      defaultBaseUrl: 'https://api.anthropic.com',
      defaultModel: 'claude-sonnet-5',
      models: [
        { value: 'claude-fable-5', label: 'Claude Fable 5 (Best)' },
        { value: 'claude-sonnet-5', label: 'Claude Sonnet 5 (Recommended)' },
        { value: 'claude-opus-5', label: 'Claude Opus 5 (Enterprise)' }
      ]
    },
    {
      value: 'openai',
      label: 'OpenAI',
      trust: 'external',
      trustLabel: 'External - data sent to OpenAI',
      needsApiKey: false,
      optionalApiKey: true,
      needsBaseUrl: true,
      defaultBaseUrl: 'https://api.openai.com/v1',
      defaultModel: 'gpt-5.6-terra',
      apiKeyHelper: 'OpenAI API Key',
      models: [
        { value: 'gpt-5.6-luna', label: 'GPT-5.6 Luna' },
        { value: 'gpt-5.6-sol', label: 'GPT-5.6 Sol' },
        { value: 'gpt-5.6-terra', label: 'GPT-5.6 Terra (Recommended)' },
        { value: 'o3-pro', label: 'o3 Pro' }
      ]
    },
    {
      value: 'gemini',
      label: 'Gemini',
      trust: 'external',
      trustLabel: 'External - data sent to Google',
      needsApiKey: false,
      optionalApiKey: true,
      needsBaseUrl: true,
      defaultBaseUrl: 'https://generativelanguage.googleapis.com/v1beta',
      defaultModel: 'gemini-3.7-flash',
      models: [
        { value: 'gemini-3.7-flash', label: 'Gemini 3.7 Flash' },
        { value: 'gemini-3.5-flash-lite', label: 'Gemini 3.5 Flash-Lite' },
        { value: 'gemini-3.1-pro', label: 'Gemini 3.1 Pro' }
      ]
    },
    {
      value: 'copilot',
      label: 'GitHub Copilot / Models',
      trust: 'external',
      trustLabel: 'External - data sent to GitHub Models',
      needsApiKey: true,
      optionalApiKey: false,
      needsBaseUrl: true,
      defaultBaseUrl: 'https://models.github.ai/inference',
      defaultModel: 'openai/gpt-5.5-mini',
      apiKeyHelper: 'GitHub Personal Access Token (PAT) with access to GitHub Models',
      baseUrlHelper: 'Base URL (default: https://models.github.ai/inference)',
      models: [
        { value: 'openai/gpt-5.5-mini', label: 'GPT-5.5 Mini (Default)' },
        { value: 'openai/gpt-5', label: 'GPT-5' },
        { value: 'anthropic/claude-sonnet-4', label: 'Claude Sonnet 4' },
        { value: 'meta/llama-3.3-70b-instruct', label: 'Llama 3.3 70B Instruct' },
        { value: 'deepseek/deepseek-r1', label: 'DeepSeek R1' }
      ]
    },
    {
      value: 'custom_local',
      label: 'Custom Endpoint',
      trust: 'local',
      trustLabel: 'Local / Custom Endpoint',
      needsApiKey: false,
      optionalApiKey: true,
      needsBaseUrl: true,
      requireBaseUrl: true,
      defaultBaseUrl: 'http://localhost:8000/v1',
      defaultModel: 'llama-3',
      isCustomModel: true,
      baseUrlHelper: 'Base URL of your custom endpoint',
      apiKeyHelper: 'Optional. Leave blank if your endpoint does not require authentication.',
      models: []
    }
  ];

  const currentProvider = providers.find(p => p.value === provider);

  useEffect(() => {
    loadStatus();
    loadConfigs();
    loadInstructions();
    // Set default model for initial provider (anthropic)
    if (!model) {
      setModel('claude-sonnet-5');
    }
  }, []);

  const loadConfigs = async () => {
    try {
      const data = await api.getLLMConfigs();
      setConfigsList(data.configs || []);
      setDefaultConfigId(data.default_config_id);
    } catch (err) {
      console.error('Failed to load LLM configs list:', err);
    }
  };

  const loadInstructions = async () => {
    try {
      const res = await api.getCustomInstructions();
      if (res && res.instructions !== undefined) {
        setCustomInstructions(res.instructions);
      }
    } catch (err) {
      console.error('Failed to load custom instructions:', err);
    }
  };

  const handleSaveInstructions = async () => {
    try {
      setSavingInstructions(true);
      setInstructionsError(null);
      await api.saveCustomInstructions(customInstructions);
      setInstructionsSuccess('Custom instructions saved successfully!');
      setTimeout(() => setInstructionsSuccess(null), 3000);
    } catch (err) {
      setInstructionsError(err.message || 'Failed to save custom instructions');
    } finally {
      setSavingInstructions(false);
    }
  };

  const handleDeleteInstructions = async () => {
    if (!window.confirm('Are you sure you want to clear custom instructions?')) {
      return;
    }
    try {
      setSavingInstructions(true);
      setInstructionsError(null);
      await api.deleteCustomInstructions();
      setCustomInstructions('');
      setInstructionsSuccess('Custom instructions cleared successfully!');
      setTimeout(() => setInstructionsSuccess(null), 3000);
    } catch (err) {
      setInstructionsError(err.message || 'Failed to clear custom instructions');
    } finally {
      setSavingInstructions(false);
    }
  };

  const handleExportInstructions = () => {
    try {
      setInstructionsError(null);
      const content = customInstructions || '';
      if (!content.trim()) {
        setInstructionsError('There are no instructions to export.');
        setTimeout(() => setInstructionsError(null), 3000);
        return;
      }
      const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = 'kure-instructions.md';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      setInstructionsSuccess('Instructions exported as kure-instructions.md');
      setTimeout(() => setInstructionsSuccess(null), 3000);
    } catch (err) {
      setInstructionsError(err.message || 'Failed to export instructions');
    }
  };

  const handleImportClick = () => {
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
      fileInputRef.current.click();
    }
  };

  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // Validate that the file has .md extension
    if (!file.name.toLowerCase().endsWith('.md')) {
      setInstructionsError('Please select a valid markdown (.md) file.');
      setTimeout(() => setInstructionsError(null), 4000);
      return;
    }

    const reader = new FileReader();
    reader.onload = (event) => {
      try {
        const text = event.target?.result;
        if (typeof text === 'string') {
          if (text.length > 10000) {
            setInstructionsError('Imported file exceeds the 10,000 character limit. It was truncated.');
            setCustomInstructions(text.slice(0, 10000));
          } else {
            setCustomInstructions(text);
            setInstructionsSuccess(`Imported "${file.name}" successfully! Click "Save Instructions" to persist.`);
          }
          setTimeout(() => {
            setInstructionsSuccess(null);
            setInstructionsError(null);
          }, 4000);
        }
      } catch (err) {
        setInstructionsError('Failed to read markdown file: ' + err.message);
      }
    };
    reader.onerror = () => {
      setInstructionsError('Failed to read the selected file.');
    };
    reader.readAsText(file);
  };

  const loadStatus = async () => {
    try {
      setLoading(true);
      const data = await api.getLLMStatus();
      setStatus(data);
      if (data.configured) {
        setProvider(data.provider || 'anthropic');
        const loadedModel = data.model || '';
        
        // Find if the loaded model is in the provider's predefined models
        const prov = providers.find(p => p.value === (data.provider || 'anthropic'));
        if (prov && !prov.isCustomModel) {
            const isPredefined = prov.models.some(m => m.value === loadedModel);
            if (!isPredefined && loadedModel !== '') {
                setIsCustomModelInput(true);
            } else {
                setIsCustomModelInput(false);
            }
        }
        setModel(loadedModel);
        if (data.base_url) {
          setBaseUrl(data.base_url);
        } else {
          // If no base_url in data, try to use provider default
          const prov = providers.find(p => p.value === (data.provider || 'anthropic'));
          if (prov && prov.defaultBaseUrl) {
            setBaseUrl(prov.defaultBaseUrl);
          } else {
            setBaseUrl('');
          }
        }
      }
    } catch (err) {
      console.error('Failed to load LLM status:', err);
      setError('Failed to load LLM configuration');
    } finally {
      setLoading(false);
    }
  };

  const handleSetDefault = async (configId) => {
    try {
      setError(null);
      await api.setDefaultLLMConfig(configId);
      setSuccess('Default LLM updated successfully!');
      await loadConfigs();
      await loadStatus();
      if (onConfigChange) onConfigChange();
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      setError(err.message || 'Failed to set default LLM');
    }
  };

  const handleDeleteConfigItem = async (configId) => {
    if (!window.confirm('Are you sure you want to remove this LLM?')) return;
    try {
      setError(null);
      await api.deleteLLMConfigItem(configId);
      setSuccess('LLM removed successfully!');
      await loadConfigs();
      await loadStatus();
      if (onConfigChange) onConfigChange();
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      setError(err.message || 'Failed to delete LLM');
    }
  };

  const handleTestRegistered = async (configId) => {
    try {
      setTestingConfigId(configId);
      setError(null);
      const res = await api.testRegisteredLLMConfig(configId);
      if (res.success) {
        setSuccess('LLM test connection successful!');
        setTimeout(() => setSuccess(null), 3000);
      } else {
        setError(res.message || 'LLM test failed');
      }
    } catch (err) {
      setError(err.message || 'Test failed');
    } finally {
      setTestingConfigId(null);
    }
  };

  const handleProviderChange = (e) => {
    const newProvider = e.target.value;
    setProvider(newProvider);
    const providerConfig = providers.find(p => p.value === newProvider);
    if (providerConfig) {
      setModel(providerConfig.defaultModel);
      setBaseUrl(providerConfig.defaultBaseUrl || '');
      setApiKey('');
      setIsCustomModelInput(false);
    }
  };

  const handleDiscover = async () => {
    try {
      setDiscoveryLoading(true);
      setError(null);
      const res = await api.discoverLLMs();
      if (res.endpoints && res.endpoints.length > 0) {
        setDiscoveredEndpoints(res.endpoints);
        setSuccess(`Found ${res.endpoints.length} local AI service(s)!`);
        setTimeout(() => setSuccess(null), 3000);
      } else {
        setError('No local AI services discovered in the cluster.');
      }
    } catch (err) {
      setError('Failed to discover LLMs: ' + err.message);
    } finally {
      setDiscoveryLoading(false);
    }
  };

  const applyDiscovered = (ep) => {
    setPendingEndpoint(ep);
    setPendingApiKey('');
  };

  const handlePendingEndpointConfirm = async (useApiKey) => {
    const ep = pendingEndpoint;
    const finalApiKey = useApiKey && pendingApiKey.trim() ? pendingApiKey.trim() : 'unused';
    const finalModel = ep.models && ep.models.length > 0 ? ep.models[0] : null;
    
    const payload = {
      provider: ep.provider,
      api_key: finalApiKey,
      model: finalModel,
      base_url: ep.base_url
    };

    try {
      setTesting(true);
      setTestingPhase('Testing connection...');
      setError(null);
      const testResult = await api.testLLMConfig(payload);
      
      if (testResult.success) {
        setTestingPhase('Connection successful!');
        await new Promise(r => setTimeout(r, 600)); // Smooth UX delay
        
        setTestingPhase('Applying configuration...');
        await api.saveLLMConfig(payload);
        await new Promise(r => setTimeout(r, 600)); // Smooth UX delay
        
        setSuccess('LLM configuration saved successfully!');
        
        setProvider(ep.provider);
        setBaseUrl(ep.base_url);
        setModel(finalModel || '');
        setApiKey(''); 
        setDiscoveredEndpoints([]);
        setPendingEndpoint(null);
        
        await loadStatus();
        if (onConfigChange) onConfigChange();
        
        setTimeout(() => setSuccess(null), 3000);
      } else {
        setError(testResult.message || 'Test failed. Please check your API key and try again.');
      }
    } catch (err) {
      setError(err.message || 'Test failed. Please check your API key and try again.');
    } finally {
      setTesting(false);
      setTestingPhase('');
    }
  };

  // Get current provider's models
  const currentProviderModels = currentProvider?.models || [];

  const buildPayload = () => {
    const payload = {
      name: configName.trim() || `${provider.charAt(0).toUpperCase() + provider.slice(1)} (${model || 'default'})`,
      provider,
      api_key: (currentProvider?.needsApiKey || (currentProvider?.optionalApiKey && apiKey)) ? (apiKey || 'unused') : 'unused',
      model: model || null,
      is_default: isDefaultCheckbox,
    };
    if (currentProvider?.needsBaseUrl && baseUrl) {
      payload.base_url = baseUrl;
    }
    return payload;
  };

  const handleTest = async () => {
    if (currentProvider?.needsApiKey && !apiKey) {
      setError('Please enter an API key');
      return;
    }
    if (currentProvider?.requireBaseUrl && !baseUrl) {
      setError('Please enter a Base URL');
      return;
    }

    try {
      setTesting(true);
      setError(null);
      const payload = buildPayload();
      const result = await api.testLLMConfig(payload);
      if (result.success) {
        setSuccess('Connection test successful! Registering LLM...');
        // Auto-register LLM on successful connection test
        try {
          await persistConfig(payload);
          setSuccess('Connection test successful and LLM registered!');
        } catch (saveErr) {
          console.warn('Auto-registration after test failed:', saveErr);
          setSuccess('Connection test successful! (Click Save & Register to retry saving)');
        }
        setTimeout(() => setSuccess(null), 3500);
      } else {
        setError(result.message || 'Test failed');
      }
    } catch (err) {
      setError(err.message || 'Test failed');
    } finally {
      setTesting(false);
    }
  };

  const persistConfig = async (payload) => {
    if (editingConfigId) {
      await api.updateLLMConfig(editingConfigId, {
        name: payload.name,
        provider: payload.provider,
        api_key: apiKey ? apiKey : null,
        model: payload.model,
        base_url: payload.base_url,
        is_default: payload.is_default,
      });
    } else {
      try {
        await api.createLLMConfig(payload);
      } catch (err) {
        // Fallback to legacy single-config endpoint if backend doesn't support multi-LLM route yet
        if (err.message && (err.message.includes('404') || err.message.includes('Not Found'))) {
          await api.saveLLMConfig(payload);
        } else {
          throw err;
        }
      }
    }

    setApiKey(''); // Clear API key from form after save
    setConfigName('');
    setIsDefaultCheckbox(false);
    setIsEditing(false);
    setEditingConfigId(null);
    setShowAddForm(false);
    await loadConfigs();
    await loadStatus();
    if (onConfigChange) {
      onConfigChange();
    }
  };

  const handleSave = async () => {
    if (currentProvider?.needsApiKey && !apiKey) {
      setError('Please enter an API key');
      return;
    }
    if (currentProvider?.requireBaseUrl && !baseUrl) {
      setError('Please enter a Base URL');
      return;
    }

    try {
      setSaving(true);
      setError(null);
      const payload = buildPayload();
      await persistConfig(payload);
      setSuccess(editingConfigId ? 'LLM configuration updated successfully!' : 'LLM registered successfully!');
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      setError(err.message || 'Failed to save configuration');
    } finally {
      setSaving(false);
    }
  };

  const startEditConfig = (cfg) => {
    setEditingConfigId(cfg.id);
    setConfigName(cfg.name || '');
    setProvider(cfg.provider);
    setModel(cfg.model || '');
    setBaseUrl(cfg.base_url || '');
    setApiKey('');
    setIsDefaultCheckbox(cfg.is_default);
    setShowAddForm(true);
  };

  const handleDelete = async () => {
    if (!window.confirm('Are you sure you want to delete the LLM configuration? AI-powered solutions will be disabled.')) {
      return;
    }

    try {
      setSaving(true);
      setError(null);
      await api.deleteLLMConfig();
      setSuccess('LLM configuration deleted. Using rule-based solutions.');
      setApiKey('');
      await loadStatus();
      // Notify parent that config has changed so aiEnabled state updates
      if (onConfigChange) {
        onConfigChange();
      }
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      setError(err.message || 'Failed to delete configuration');
    } finally {
      setSaving(false);
    }
  };

  const canSubmit = (currentProvider?.needsApiKey ? !!apiKey : true) && (currentProvider?.requireBaseUrl ? !!baseUrl : true);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="w-6 h-6 animate-spin text-blue-500" />
        <span className={`ml-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Loading...</span>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center mb-4">
        <Bot className="w-5 h-5 text-blue-500 mr-2" />
        <h2 className={`text-lg font-semibold ${isDark ? 'text-gray-100' : 'text-gray-900'}`}>
          AI Configuration
        </h2>
      </div>

      <p className={`text-sm mb-4 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
        Configure an LLM provider to enable AI-powered troubleshooting solutions.
        Without configuration, the system uses rule-based solutions.
      </p>

      {error && (
        <div className={`border rounded-sm p-3 ${isDark ? 'bg-red-900/30 border-red-800' : 'bg-red-50 border-red-200'}`}>
          <div className="flex items-center">
            <AlertCircle className="w-4 h-4 text-red-500 mr-2" />
            <span className={`text-sm ${isDark ? 'text-red-300' : 'text-red-800'}`}>{error}</span>
          </div>
        </div>
      )}

      {success && (
        <div className={`border rounded-sm p-3 ${isDark ? 'bg-green-900/30 border-green-800' : 'bg-green-50 border-green-200'}`}>
          <div className="flex items-center">
            <CheckCircle className="w-4 h-4 text-green-500 mr-2" />
            <span className={`text-sm ${isDark ? 'text-green-300' : 'text-green-800'}`}>{success}</span>
          </div>
        </div>
      )}

      {/* Registered LLMs Registry Card */}
      <div className={`border rounded-sm p-4 ${isDark ? 'border-gray-700 bg-gray-800/50' : 'border-gray-200 bg-gray-50'}`}>
        <div className="flex items-center justify-between mb-3">
          <div>
            <h3 className={`text-sm font-semibold ${isDark ? 'text-gray-200' : 'text-gray-800'}`}>
              Registered LLM Providers
            </h3>
            <p className={`text-xs mt-0.5 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
              Multiple LLMs will automatically fail over if the primary/default provider becomes unavailable.
            </p>
          </div>
          <button
            onClick={() => {
              setEditingConfigId(null);
              setConfigName('');
              setProvider('anthropic');
              const prov = providers.find(p => p.value === 'anthropic');
              setModel(prov?.defaultModel || '');
              setBaseUrl(prov?.defaultBaseUrl || '');
              setApiKey('');
              setIsDefaultCheckbox(configsList.length === 0);
              setShowAddForm(true);
            }}
            className="inline-flex items-center px-3 py-1.5 text-xs font-medium rounded-sm text-white bg-blue-600 hover:bg-blue-700 shadow-sm"
          >
            <Plus className="w-3.5 h-3.5 mr-1" />
            Register LLM
          </button>
        </div>

        {configsList.length === 0 ? (
          <div className={`text-center py-6 border border-dashed rounded-sm ${isDark ? 'border-gray-700 text-gray-400' : 'border-gray-300 text-gray-500'}`}>
            <Bot className="w-8 h-8 mx-auto mb-2 opacity-50" />
            <p className="text-sm">No LLM providers registered yet.</p>
            <p className="text-xs mt-1">Register at least one LLM to enable AI-powered troubleshooting.</p>
          </div>
        ) : (
          <div className="space-y-2">
            {configsList.map((cfg) => {
              const isDefault = cfg.id === defaultConfigId || cfg.is_default;
              const isTestingThis = testingConfigId === cfg.id;

              return (
                <div
                  key={cfg.id}
                  className={`flex items-center justify-between p-3 rounded border transition-all ${
                    isDefault
                      ? isDark
                        ? 'border-blue-700 bg-blue-950/20'
                        : 'border-blue-300 bg-blue-50/60'
                      : isDark
                        ? 'border-gray-700 bg-gray-800/40'
                        : 'border-gray-200 bg-white'
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <div className="flex flex-col">
                      <div className="flex items-center gap-2">
                        <span className={`text-sm font-medium ${isDark ? 'text-gray-100' : 'text-gray-900'}`}>
                          {cfg.name || cfg.provider}
                        </span>
                        {isDefault && (
                          <span className="inline-flex items-center px-2 py-0.5 text-xs font-semibold rounded bg-blue-600 text-white">
                            <Star className="w-3 h-3 mr-1 fill-white" />
                            Default
                          </span>
                        )}
                        <span className={`text-xs px-2 py-0.5 rounded capitalize ${
                          isDark ? 'bg-gray-700 text-gray-300' : 'bg-gray-100 text-gray-700'
                        }`}>
                          {cfg.provider}
                        </span>
                      </div>
                      <div className={`text-xs mt-1 flex items-center gap-3 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                        {cfg.model && <span>Model: <span className="font-mono">{cfg.model}</span></span>}
                        {cfg.base_url && <span>URL: <span className="font-mono">{cfg.base_url}</span></span>}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-1.5">
                    <button
                      onClick={() => handleTestRegistered(cfg.id)}
                      disabled={isTestingThis}
                      className={`inline-flex items-center px-2.5 py-1 text-xs font-medium rounded border ${
                        isDark
                          ? 'border-gray-700 text-gray-300 hover:bg-gray-700'
                          : 'border-gray-300 text-gray-700 hover:bg-gray-100'
                      }`}
                      title="Test connection"
                    >
                      {isTestingThis ? (
                        <Loader2 className="w-3 h-3 mr-1 animate-spin" />
                      ) : (
                        <CheckCircle className="w-3 h-3 mr-1 text-green-500" />
                      )}
                      Test
                    </button>

                    {!isDefault && (
                      <button
                        onClick={() => handleSetDefault(cfg.id)}
                        className={`inline-flex items-center px-2.5 py-1 text-xs font-medium rounded border ${
                          isDark
                            ? 'border-blue-800 text-blue-300 hover:bg-blue-900/40'
                            : 'border-blue-200 text-blue-700 hover:bg-blue-50'
                        }`}
                        title="Set as primary default"
                      >
                        <Star className="w-3 h-3 mr-1" />
                        Set Default
                      </button>
                    )}

                    <button
                      onClick={() => startEditConfig(cfg)}
                      className={`p-1.5 rounded text-xs ${
                        isDark ? 'text-gray-400 hover:text-gray-200 hover:bg-gray-700' : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
                      }`}
                      title="Edit configuration"
                    >
                      <Edit className="w-3.5 h-3.5" />
                    </button>

                    <button
                      onClick={() => handleDeleteConfigItem(cfg.id)}
                      className={`p-1.5 rounded text-xs ${
                        isDark ? 'text-red-400 hover:text-red-300 hover:bg-red-900/30' : 'text-red-600 hover:text-red-700 hover:bg-red-50'
                      }`}
                      title="Delete LLM"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Configuration / Registration Form */}
      {showAddForm && (
        <div className={`border rounded-sm p-4 ${isDark ? 'border-gray-700 bg-gray-800/30' : 'border-gray-200 bg-white'}`}>
        <div className="flex justify-between items-center mb-4">
          <h3 className={`text-sm font-semibold ${isDark ? 'text-gray-200' : 'text-gray-800'}`}>
            {editingConfigId ? 'Edit LLM Provider' : 'Register New LLM Provider'}
          </h3>
          <button
            onClick={handleDiscover}
            disabled={discoveryLoading}
            className={`inline-flex items-center px-3 py-1 text-xs font-medium border rounded-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50 ${isDark ? 'bg-blue-900/30 text-blue-300 border-blue-800 hover:bg-blue-900/50' : 'bg-blue-50 text-blue-700 border-blue-200 hover:bg-blue-100'}`}
          >
            {discoveryLoading ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : <Search className="w-3 h-3 mr-1" />}
            Auto-Discover Local Services
          </button>
        </div>

        {discoveredEndpoints.length > 0 && (
          <div className={`mb-6 p-3 border rounded-sm ${isDark ? 'bg-gray-800 border-blue-900/50' : 'bg-blue-50/50 border-blue-100'}`}>
            <h4 className={`text-xs font-medium mb-2 ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>Discovered Services:</h4>
            <div className="space-y-2">
              {discoveredEndpoints.map((ep, i) => (
                <div key={i} className={`flex items-center justify-between p-2 rounded border ${isDark ? 'bg-gray-900/50 border-gray-700' : 'bg-white border-gray-200'}`}>
                  <div>
                    <div className={`text-sm font-medium ${isDark ? 'text-gray-200' : 'text-gray-800'}`}>{ep.description}</div>
                    <div className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>{ep.base_url} ({ep.models?.length || 0} models)</div>
                  </div>
                  <button onClick={() => applyDiscovered(ep)} className="text-xs px-2 py-1 bg-blue-600 text-white rounded hover:bg-blue-700">
                    Use This
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="space-y-4">
          {/* Display Name Input */}
          <div>
            <label className={`block text-sm font-medium mb-1 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
              Provider Name / Label
            </label>
            <input
              type="text"
              value={configName}
              onChange={(e) => setConfigName(e.target.value)}
              placeholder="e.g., Primary Claude, Local Ollama, Production OpenAI"
              className={`w-full px-3 py-2 text-sm border rounded-sm focus:outline-none focus:ring-2 focus:ring-blue-500 ${isDark ? 'bg-gray-700 border-gray-600 text-gray-200 placeholder-gray-400' : 'bg-white border-gray-300 text-gray-900'}`}
            />
          </div>

          {/* Provider Select */}
          <div>
            <label className={`block text-sm font-medium mb-1 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
              API Endpoint / Provider
            </label>
            <select
              value={provider}
              onChange={handleProviderChange}
              className={`w-full px-3 py-2 text-sm border rounded-sm focus:outline-none focus:ring-2 focus:ring-blue-500 ${isDark ? 'bg-gray-700 border-gray-600 text-gray-200' : 'bg-white border-gray-300 text-gray-900'}`}
            >
              {providers.map(p => (
                <option key={p.value} value={p.value}>{p.label}</option>
              ))}
            </select>
          </div>

          {/* API Key Input - only shown when provider needs it */}
          {(currentProvider?.needsApiKey || currentProvider?.optionalApiKey) && (
            <div>
              <label className={`block text-sm font-medium mb-1 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                API Key
              </label>
              <div className="relative">
                <input
                  type={showApiKey ? 'text' : 'password'}
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder={currentProvider?.optionalApiKey ? 'Optional: Enter your API key if required' : (status?.configured ? 'Enter new API key to update' : 'Enter your API key')}
                  className={`w-full px-3 py-2 pr-10 text-sm border rounded-sm focus:outline-none focus:ring-2 focus:ring-blue-500 ${isDark ? 'bg-gray-700 border-gray-600 text-gray-200 placeholder-gray-400' : 'bg-white border-gray-300 text-gray-900'}`}
                />
                <button
                  type="button"
                  onClick={() => setShowApiKey(!showApiKey)}
                  className={`absolute right-2 top-1/2 -translate-y-1/2 p-1 ${isDark ? 'text-gray-400 hover:text-gray-300' : 'text-gray-500 hover:text-gray-700'}`}
                >
                  {showApiKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
              {currentProvider.apiKeyHelper && (
                <p className={`mt-1 text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
                  {currentProvider.apiKeyHelper}
                </p>
              )}
            </div>
          )}

          {/* Base URL Input - only shown when provider needs it */}
          {currentProvider?.needsBaseUrl && (
            <div>
              <label className={`block text-sm font-medium mb-1 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                Base URL
              </label>
              <input
                type="text"
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                placeholder={currentProvider.defaultBaseUrl}
                className={`w-full px-3 py-2 text-sm border rounded-sm focus:outline-none focus:ring-2 focus:ring-blue-500 ${isDark ? 'bg-gray-700 border-gray-600 text-gray-200 placeholder-gray-400' : 'bg-white border-gray-300 text-gray-900'}`}
              />
              {currentProvider.baseUrlHelper && (
                <p className={`mt-1 text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
                  {currentProvider.baseUrlHelper}
                </p>
              )}
            </div>
          )}

          {/* Model Select */}
          <div>
            <label className={`block text-sm font-medium mb-1 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
              Model
            </label>
            {currentProvider?.isCustomModel ? (
              <>
                <input
                  type="text"
                  list="provider-models"
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  placeholder="Enter or select a model name..."
                  className={`w-full px-3 py-2 text-sm border rounded-sm focus:outline-none focus:ring-2 focus:ring-blue-500 ${isDark ? 'bg-gray-700 border-gray-600 text-gray-200 placeholder-gray-400' : 'bg-white border-gray-300 text-gray-900'}`}
                />
                <datalist id="provider-models">
                  {currentProviderModels.map(m => (
                    <option key={m.value} value={m.value}>{m.label}</option>
                  ))}
                </datalist>
              </>
            ) : (
              <div className="space-y-2">
                <select
                  value={isCustomModelInput ? 'custom_entry' : model}
                  onChange={(e) => {
                    if (e.target.value === 'custom_entry') {
                      setIsCustomModelInput(true);
                      setModel('');
                    } else {
                      setIsCustomModelInput(false);
                      setModel(e.target.value);
                    }
                  }}
                  className={`w-full px-3 py-2 text-sm border rounded-sm focus:outline-none focus:ring-2 focus:ring-blue-500 ${isDark ? 'bg-gray-700 border-gray-600 text-gray-200' : 'bg-white border-gray-300 text-gray-900'}`}
                >
                  {currentProviderModels.map(m => (
                    <option key={m.value} value={m.value}>{m.label}</option>
                  ))}
                  <option value="custom_entry">Custom... (Type your own)</option>
                </select>

                {isCustomModelInput && (
                  <input
                    type="text"
                    value={model}
                    onChange={(e) => setModel(e.target.value)}
                    placeholder="Enter model name (e.g., claude-3-haiku-20240307)"
                    className={`w-full px-3 py-2 text-sm border rounded-sm focus:outline-none focus:ring-2 focus:ring-blue-500 ${isDark ? 'bg-gray-700 border-gray-600 text-gray-200 placeholder-gray-400' : 'bg-white border-gray-300 text-gray-900'}`}
                    autoFocus
                  />
                )}
              </div>
            )}
          </div>

          {/* Set as Default Checkbox */}
          <div className="flex items-center gap-2 pt-1">
            <input
              type="checkbox"
              id="is_default_checkbox"
              checked={isDefaultCheckbox}
              onChange={(e) => setIsDefaultCheckbox(e.target.checked)}
              className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
            />
            <label htmlFor="is_default_checkbox" className={`text-sm select-none ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
              Designate as default LLM (used first for real-time triage and pod analysis)
            </label>
          </div>

          {/* Action Buttons */}
          <div className="flex gap-2 pt-2">
            <button
              onClick={handleTest}
              disabled={testing || !canSubmit}
              className={`inline-flex items-center px-4 py-2 text-sm font-medium border rounded-sm focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50 ${isDark ? 'bg-gray-700 border-gray-600 text-gray-200 hover:bg-gray-600' : 'bg-white border-gray-300 text-gray-700 hover:bg-gray-50'}`}
            >
              {testing ? (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                <CheckCircle className="w-4 h-4 mr-2" />
              )}
              Test Connection
            </button>
            <button
              onClick={handleSave}
              disabled={saving || !canSubmit}
              className="inline-flex items-center px-4 py-2 text-sm font-medium text-white bg-blue-600 border border-transparent rounded-sm shadow-sm hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50"
            >
              {saving ? (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                <Save className="w-4 h-4 mr-2" />
              )}
              {editingConfigId ? 'Update Provider' : 'Save & Register'}
            </button>
            <button
              onClick={() => {
                setShowAddForm(false);
                setEditingConfigId(null);
                setConfigName('');
                setApiKey('');
                setError(null);
              }}
              disabled={saving || testing}
              className={`inline-flex items-center px-4 py-2 text-sm font-medium border rounded-sm focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-500 disabled:opacity-50 ${isDark ? 'bg-gray-700 border-gray-600 text-gray-200 hover:bg-gray-600' : 'bg-white border-gray-300 text-gray-700 hover:bg-gray-50'}`}
            >
              Cancel
            </button>
          </div>
        </div>
      </div>
      )}

      {/* Custom LLM Instructions Section */}
      <div className={`border rounded-sm p-4 ${isDark ? 'border-gray-700 bg-gray-800/30' : 'border-gray-200 bg-white'}`}>
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center">
            <FileText className="w-4 h-4 text-blue-500 mr-2" />
            <h3 className={`text-sm font-medium ${isDark ? 'text-gray-200' : 'text-gray-800'}`}>
              Custom AI Instructions
            </h3>
          </div>
          <span className={`text-xs ${customInstructions.length > 9000 ? 'text-amber-500 font-semibold' : isDark ? 'text-gray-400' : 'text-gray-500'}`}>
            {customInstructions.length} / 10,000 characters
          </span>
        </div>

        <p className={`text-xs mb-3 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
          Provide domain knowledge, architecture details (e.g. Istio sidecars, Vault injectors), or output style guidelines. These instructions are injected into all troubleshooting and fix-generation prompts.
        </p>

        {instructionsError && (
          <div className={`border rounded-sm p-2.5 mb-3 ${isDark ? 'bg-red-900/30 border-red-800' : 'bg-red-50 border-red-200'}`}>
            <div className="flex items-center">
              <AlertCircle className="w-4 h-4 text-red-500 mr-2 flex-shrink-0" />
              <span className={`text-xs ${isDark ? 'text-red-300' : 'text-red-800'}`}>{instructionsError}</span>
            </div>
          </div>
        )}

        {instructionsSuccess && (
          <div className={`border rounded-sm p-2.5 mb-3 ${isDark ? 'bg-green-900/30 border-green-800' : 'bg-green-50 border-green-200'}`}>
            <div className="flex items-center">
              <CheckCircle className="w-4 h-4 text-green-500 mr-2 flex-shrink-0" />
              <span className={`text-xs ${isDark ? 'text-green-300' : 'text-green-800'}`}>{instructionsSuccess}</span>
            </div>
          </div>
        )}

        <textarea
          rows={6}
          value={customInstructions}
          onChange={(e) => setCustomInstructions(e.target.value)}
          maxLength={10000}
          placeholder="Example:
- Our cluster uses Istio sidecars. If you see connection issues or CrashLoopBackOff, check istio-proxy container logs before assuming application errors.
- Always provide Helm values.yaml snippets for fixes when modifying deployments.
- For payment-service, required environment variables are injected by Vault Agent."
          className={`w-full px-3 py-2 text-xs font-mono border rounded-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-y leading-relaxed ${
            isDark
              ? 'bg-gray-900 border-gray-700 text-gray-200 placeholder-gray-500'
              : 'bg-gray-50 border-gray-300 text-gray-900 placeholder-gray-400'
          }`}
        />

        <div className="flex items-center justify-between mt-3 flex-wrap gap-2">
          <div className="flex items-center gap-2 flex-wrap">
            <button
              onClick={handleSaveInstructions}
              disabled={savingInstructions}
              className="inline-flex items-center px-3 py-1.5 text-xs font-medium text-white bg-blue-600 border border-transparent rounded-sm shadow-sm hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50"
            >
              {savingInstructions ? (
                <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
              ) : (
                <Save className="w-3.5 h-3.5 mr-1.5" />
              )}
              Save Instructions
            </button>

            {/* Hidden file input restricted to .md files */}
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileChange}
              accept=".md,text/markdown"
              style={{ display: 'none' }}
            />

            <button
              type="button"
              onClick={handleImportClick}
              disabled={savingInstructions}
              title="Import instructions from a .md file"
              className={`inline-flex items-center px-3 py-1.5 text-xs font-medium border rounded-sm focus:outline-none disabled:opacity-50 ${
                isDark
                  ? 'border-gray-700 text-gray-300 bg-gray-800 hover:bg-gray-700'
                  : 'border-gray-300 text-gray-700 bg-white hover:bg-gray-50'
              }`}
            >
              <Upload className="w-3.5 h-3.5 mr-1.5 text-blue-500" />
              Import (.md)
            </button>

            <button
              type="button"
              onClick={handleExportInstructions}
              disabled={savingInstructions || !customInstructions.trim()}
              title="Export instructions as kure-instructions.md"
              className={`inline-flex items-center px-3 py-1.5 text-xs font-medium border rounded-sm focus:outline-none disabled:opacity-50 ${
                isDark
                  ? 'border-gray-700 text-gray-300 bg-gray-800 hover:bg-gray-700'
                  : 'border-gray-300 text-gray-700 bg-white hover:bg-gray-50'
              }`}
            >
              <Download className="w-3.5 h-3.5 mr-1.5 text-emerald-500" />
              Export (.md)
            </button>

            {customInstructions && (
              <button
                onClick={handleDeleteInstructions}
                disabled={savingInstructions}
                className={`inline-flex items-center px-3 py-1.5 text-xs font-medium border rounded-sm focus:outline-none disabled:opacity-50 ${
                  isDark
                    ? 'text-red-300 bg-red-900/30 border-red-800 hover:bg-red-900/50'
                    : 'text-red-700 bg-red-50 border-red-200 hover:bg-red-100'
                }`}
              >
                <Trash2 className="w-3.5 h-3.5 mr-1.5" />
                Clear
              </button>
            )}
          </div>
          <span className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
            Saved globally in cluster configuration
          </span>
        </div>
      </div>

      {/* API Key Modal for Discovered Endpoint */}
      {pendingEndpoint && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className={`p-6 rounded-sm shadow-xl max-w-md w-full mx-4 ${isDark ? 'bg-gray-800 border border-gray-700' : 'bg-white border border-gray-200'}`}>
            {!testing && (
              <>
                <h3 className={`text-lg font-medium mb-2 ${isDark ? 'text-white' : 'text-gray-900'}`}>
                  Authentication Required?
                </h3>
                <p className={`text-sm mb-4 ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>
                  If your LLM requires api_key please insert, otherwise ignore this.
                </p>
                {error && (
                  <div className="p-3 mb-4 text-sm text-red-700 bg-red-100 rounded-sm flex items-start">
                    <AlertCircle className="w-4 h-4 mr-2 flex-shrink-0 mt-0.5" />
                    {error}
                  </div>
                )}
                <input
                  type="password"
                  value={pendingApiKey}
                  onChange={(e) => setPendingApiKey(e.target.value)}
                  placeholder="Enter API Key (if required)"
                  className={`w-full px-3 py-2 text-sm border rounded-sm focus:outline-none focus:ring-2 focus:ring-blue-500 mb-6 ${isDark ? 'bg-gray-700 border-gray-600 text-gray-200 placeholder-gray-400' : 'bg-white border-gray-300 text-gray-900'}`}
                />
              </>
            )}
            <div className="mt-6">
              {testing ? (
                <div className="flex flex-col items-center justify-center py-4">
                  <p className={`text-sm font-medium mb-4 ${isDark ? 'text-gray-200' : 'text-gray-700'}`}>
                    {testingPhase}
                  </p>
                  <div className={`w-full h-2 rounded overflow-hidden ${isDark ? 'bg-gray-700' : 'bg-gray-200'}`}>
                    <div 
                      className="h-full bg-blue-600 transition-all duration-500 ease-out"
                      style={{ 
                        width: testingPhase === 'Testing connection...' ? '33%' : 
                               testingPhase === 'Connection successful!' ? '66%' : 
                               testingPhase === 'Applying configuration...' ? '100%' : '100%'
                      }}
                    />
                  </div>
                </div>
              ) : (
                <div className="flex flex-col gap-2">
                  <button
                    onClick={() => handlePendingEndpointConfirm(true)}
                    className="w-full px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-sm shadow-sm hover:bg-blue-700 focus:outline-none flex justify-center items-center"
                  >
                    Insert api_key & Test Connection
                  </button>
                  <button
                    onClick={() => handlePendingEndpointConfirm(false)}
                    className={`w-full px-4 py-2 text-sm font-medium border rounded-sm focus:outline-none flex justify-center items-center ${isDark ? 'bg-gray-700 border-gray-600 text-gray-200 hover:bg-gray-600' : 'bg-white border-gray-300 text-gray-700 hover:bg-gray-50'}`}
                  >
                    Ignore (No API Key needed) & Test Connection
                  </button>
                  <button
                    onClick={() => {
                      setPendingEndpoint(null);
                      setError(null);
                    }}
                    className={`w-full px-4 py-2 text-sm font-medium rounded-sm focus:outline-none mt-2 ${isDark ? 'text-red-400 hover:text-red-300 hover:bg-red-900/30' : 'text-red-600 hover:text-red-700 hover:bg-red-50'}`}
                  >
                    Cancel
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default LLMSettings;
