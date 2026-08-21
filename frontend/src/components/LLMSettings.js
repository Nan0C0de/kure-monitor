import React, { useState, useEffect } from 'react';
import { Bot, Save, Trash2, CheckCircle, AlertCircle, Loader2, Eye, EyeOff, Search, Edit } from 'lucide-react';
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

  // Form state
  const [provider, setProvider] = useState('anthropic');
  const [apiKey, setApiKey] = useState('');
  const [model, setModel] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [isCustomModelInput, setIsCustomModelInput] = useState(false);
  const [isEditing, setIsEditing] = useState(false);

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
    // Set default model for initial provider (anthropic)
    if (!model) {
      setModel('claude-sonnet-5');
    }
  }, []);

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
      provider,
      api_key: (currentProvider?.needsApiKey || (currentProvider?.optionalApiKey && apiKey)) ? (apiKey || 'unused') : 'unused',
      model: model || null,
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
      const result = await api.testLLMConfig(buildPayload());
      if (result.success) {
        await api.saveLLMConfig(buildPayload());
        setSuccess('Connection successful! Configuration automatically saved.');
        setApiKey(''); // Clear API key from form after save
        setIsEditing(false);
        await loadStatus();
        if (onConfigChange) {
          onConfigChange();
        }
        setTimeout(() => setSuccess(null), 3000);
      } else {
        setError(result.message || 'Test failed');
      }
    } catch (err) {
      setError(err.message || 'Test failed');
    } finally {
      setTesting(false);
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
      await api.saveLLMConfig(buildPayload());
      setSuccess('LLM configuration saved successfully!');
      setApiKey(''); // Clear API key from form after save
      setIsEditing(false);
      await loadStatus();
      // Notify parent that config has changed so aiEnabled state updates
      if (onConfigChange) {
        onConfigChange();
      }
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      setError(err.message || 'Failed to save configuration');
    } finally {
      setSaving(false);
    }
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
        <Bot className="w-5 h-5 text-purple-500 mr-2" />
        <h2 className={`text-lg font-semibold ${isDark ? 'text-gray-100' : 'text-gray-900'}`}>
          AI Configuration
        </h2>
      </div>

      <p className={`text-sm mb-4 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
        Configure an LLM provider to enable AI-powered troubleshooting solutions.
        Without configuration, the system uses rule-based solutions.
      </p>

      {error && (
        <div className={`border rounded-md p-3 ${isDark ? 'bg-red-900/30 border-red-800' : 'bg-red-50 border-red-200'}`}>
          <div className="flex items-center">
            <AlertCircle className="w-4 h-4 text-red-500 mr-2" />
            <span className={`text-sm ${isDark ? 'text-red-300' : 'text-red-800'}`}>{error}</span>
          </div>
        </div>
      )}

      {success && (
        <div className={`border rounded-md p-3 ${isDark ? 'bg-green-900/30 border-green-800' : 'bg-green-50 border-green-200'}`}>
          <div className="flex items-center">
            <CheckCircle className="w-4 h-4 text-green-500 mr-2" />
            <span className={`text-sm ${isDark ? 'text-green-300' : 'text-green-800'}`}>{success}</span>
          </div>
        </div>
      )}

      {/* Current Status */}
      <div className={`border rounded-md p-4 ${isDark ? 'border-gray-700 bg-gray-800/50' : 'border-gray-200 bg-gray-50'}`}>
        <div className="flex items-center justify-between">
          <div>
            <h3 className={`text-sm font-medium ${isDark ? 'text-gray-200' : 'text-gray-700'}`}>Current Status</h3>
            <div className="mt-1 flex items-center">
              {status?.configured ? (
                <>
                  <span className="w-2 h-2 bg-green-500 rounded-full mr-2"></span>
                  <span className={`text-sm ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>
                    Configured: {status.provider} {status.model && `(${status.model})`}
                  </span>
                  <span className={`ml-2 text-xs px-2 py-0.5 rounded ${isDark ? 'bg-gray-700 text-gray-400' : 'bg-gray-200 text-gray-500'}`}>
                    via {status.source}
                  </span>
                </>
              ) : (
                <>
                  <span className="w-2 h-2 bg-yellow-500 rounded-full mr-2"></span>
                  <span className={`text-sm ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>
                    Not configured - using rule-based solutions
                  </span>
                </>
              )}
            </div>
          </div>
          {status?.configured && status?.source === 'database' && (
            <div className="flex gap-2">
              <button
                onClick={() => setIsEditing(true)}
                disabled={saving || isEditing}
                className={`inline-flex items-center px-3 py-1.5 text-sm font-medium rounded-md disabled:opacity-50 ${isDark ? 'text-blue-300 bg-blue-900/40 border border-blue-700 hover:bg-blue-900/60' : 'text-blue-700 bg-blue-50 border border-blue-200 hover:bg-blue-100'}`}
              >
                <Edit className="w-4 h-4 mr-1" />
                Edit
              </button>
              <button
                onClick={handleDelete}
                disabled={saving}
                className={`inline-flex items-center px-3 py-1.5 text-sm font-medium rounded-md disabled:opacity-50 ${isDark ? 'text-red-300 bg-red-900/40 border border-red-700 hover:bg-red-900/60' : 'text-red-700 bg-red-50 border border-red-200 hover:bg-red-100'}`}
              >
                <Trash2 className="w-4 h-4 mr-1" />
                Delete
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Configuration Form */}
      {(!status?.configured || isEditing) && (
        <div className={`border rounded-md p-4 ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
        <div className="flex justify-between items-center mb-4">
          <h3 className={`text-sm font-medium ${isDark ? 'text-gray-200' : 'text-gray-700'}`}>
            {status?.configured ? 'Update Configuration' : 'Configure API Endpoint'}
          </h3>
          <button
            onClick={handleDiscover}
            disabled={discoveryLoading}
            className={`inline-flex items-center px-3 py-1 text-xs font-medium border rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-purple-500 disabled:opacity-50 ${isDark ? 'bg-purple-900/30 text-purple-300 border-purple-800 hover:bg-purple-900/50' : 'bg-purple-50 text-purple-700 border-purple-200 hover:bg-purple-100'}`}
          >
            {discoveryLoading ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : <Search className="w-3 h-3 mr-1" />}
            Auto-Discover Local Services
          </button>
        </div>

        {discoveredEndpoints.length > 0 && (
          <div className={`mb-6 p-3 border rounded-md ${isDark ? 'bg-gray-800 border-purple-900/50' : 'bg-purple-50/50 border-purple-100'}`}>
            <h4 className={`text-xs font-medium mb-2 ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>Discovered Services:</h4>
            <div className="space-y-2">
              {discoveredEndpoints.map((ep, i) => (
                <div key={i} className={`flex items-center justify-between p-2 rounded border ${isDark ? 'bg-gray-900/50 border-gray-700' : 'bg-white border-gray-200'}`}>
                  <div>
                    <div className={`text-sm font-medium ${isDark ? 'text-gray-200' : 'text-gray-800'}`}>{ep.description}</div>
                    <div className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>{ep.base_url} ({ep.models?.length || 0} models)</div>
                  </div>
                  <button onClick={() => applyDiscovered(ep)} className="text-xs px-2 py-1 bg-purple-600 text-white rounded hover:bg-purple-700">
                    Use This
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="space-y-4">
          {/* Provider Select */}
          <div>
            <label className={`block text-sm font-medium mb-1 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
              API Endpoint
            </label>
            <select
              value={provider}
              onChange={handleProviderChange}
              className={`w-full px-3 py-2 text-sm border rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500 ${isDark ? 'bg-gray-700 border-gray-600 text-gray-200' : 'bg-white border-gray-300 text-gray-900'}`}
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
                  className={`w-full px-3 py-2 pr-10 text-sm border rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500 ${isDark ? 'bg-gray-700 border-gray-600 text-gray-200 placeholder-gray-400' : 'bg-white border-gray-300 text-gray-900'}`}
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
                className={`w-full px-3 py-2 text-sm border rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500 ${isDark ? 'bg-gray-700 border-gray-600 text-gray-200 placeholder-gray-400' : 'bg-white border-gray-300 text-gray-900'}`}
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
                  className={`w-full px-3 py-2 text-sm border rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500 ${isDark ? 'bg-gray-700 border-gray-600 text-gray-200 placeholder-gray-400' : 'bg-white border-gray-300 text-gray-900'}`}
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
                  className={`w-full px-3 py-2 text-sm border rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500 ${isDark ? 'bg-gray-700 border-gray-600 text-gray-200' : 'bg-white border-gray-300 text-gray-900'}`}
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
                    className={`w-full px-3 py-2 text-sm border rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500 ${isDark ? 'bg-gray-700 border-gray-600 text-gray-200 placeholder-gray-400' : 'bg-white border-gray-300 text-gray-900'}`}
                    autoFocus
                  />
                )}
              </div>
            )}
          </div>

          {/* Action Buttons */}
          <div className="flex gap-2 pt-2">
            <button
              onClick={handleTest}
              disabled={testing || !canSubmit}
              className={`inline-flex items-center px-4 py-2 text-sm font-medium border rounded-md focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-purple-500 disabled:opacity-50 ${isDark ? 'bg-gray-700 border-gray-600 text-gray-200 hover:bg-gray-600' : 'bg-white border-gray-300 text-gray-700 hover:bg-gray-50'}`}
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
              className="inline-flex items-center px-4 py-2 text-sm font-medium text-white bg-purple-600 border border-transparent rounded-md shadow-sm hover:bg-purple-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-purple-500 disabled:opacity-50"
            >
              {saving ? (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                <Save className="w-4 h-4 mr-2" />
              )}
              Save Configuration
            </button>
            {isEditing && (
              <button
                onClick={() => {
                  setIsEditing(false);
                  loadStatus(); // Reset to saved state
                }}
                disabled={saving || testing}
                className={`inline-flex items-center px-4 py-2 text-sm font-medium border rounded-md focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-500 disabled:opacity-50 ${isDark ? 'bg-gray-700 border-gray-600 text-gray-200 hover:bg-gray-600' : 'bg-white border-gray-300 text-gray-700 hover:bg-gray-50'}`}
              >
                Cancel
              </button>
            )}
          </div>
        </div>
      </div>
      )}

      {/* API Key Modal for Discovered Endpoint */}
      {pendingEndpoint && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className={`p-6 rounded-lg shadow-xl max-w-md w-full mx-4 ${isDark ? 'bg-gray-800 border border-gray-700' : 'bg-white border border-gray-200'}`}>
            {!testing && (
              <>
                <h3 className={`text-lg font-medium mb-2 ${isDark ? 'text-white' : 'text-gray-900'}`}>
                  Authentication Required?
                </h3>
                <p className={`text-sm mb-4 ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>
                  If your LLM requires api_key please insert, otherwise ignore this.
                </p>
                {error && (
                  <div className="p-3 mb-4 text-sm text-red-700 bg-red-100 rounded-md flex items-start">
                    <AlertCircle className="w-4 h-4 mr-2 flex-shrink-0 mt-0.5" />
                    {error}
                  </div>
                )}
                <input
                  type="password"
                  value={pendingApiKey}
                  onChange={(e) => setPendingApiKey(e.target.value)}
                  placeholder="Enter API Key (if required)"
                  className={`w-full px-3 py-2 text-sm border rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500 mb-6 ${isDark ? 'bg-gray-700 border-gray-600 text-gray-200 placeholder-gray-400' : 'bg-white border-gray-300 text-gray-900'}`}
                />
              </>
            )}
            <div className="mt-6">
              {testing ? (
                <div className="flex flex-col items-center justify-center py-4">
                  <p className={`text-sm font-medium mb-4 ${isDark ? 'text-gray-200' : 'text-gray-700'}`}>
                    {testingPhase}
                  </p>
                  <div className={`w-full h-2 rounded-full overflow-hidden ${isDark ? 'bg-gray-700' : 'bg-gray-200'}`}>
                    <div 
                      className="h-full bg-purple-600 transition-all duration-500 ease-out"
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
                    className="w-full px-4 py-2 text-sm font-medium text-white bg-purple-600 rounded-md shadow-sm hover:bg-purple-700 focus:outline-none flex justify-center items-center"
                  >
                    Insert api_key & Test Connection
                  </button>
                  <button
                    onClick={() => handlePendingEndpointConfirm(false)}
                    className={`w-full px-4 py-2 text-sm font-medium border rounded-md focus:outline-none flex justify-center items-center ${isDark ? 'bg-gray-700 border-gray-600 text-gray-200 hover:bg-gray-600' : 'bg-white border-gray-300 text-gray-700 hover:bg-gray-50'}`}
                  >
                    Ignore (No API Key needed) & Test Connection
                  </button>
                  <button
                    onClick={() => {
                      setPendingEndpoint(null);
                      setError(null);
                    }}
                    className={`w-full px-4 py-2 text-sm font-medium rounded-md focus:outline-none mt-2 ${isDark ? 'text-red-400 hover:text-red-300 hover:bg-red-900/30' : 'text-red-600 hover:text-red-700 hover:bg-red-50'}`}
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
