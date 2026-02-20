import React, { useState, useEffect } from 'react';
import { Bot, Save, Trash2, CheckCircle, AlertCircle, Loader2, Eye, EyeOff } from 'lucide-react';
import { api } from '../services/api';

const LLMSettings = ({ isDark = false, onConfigChange }) => {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [showApiKey, setShowApiKey] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  // Form state
  const [provider, setProvider] = useState('ollama');
  const [apiKey, setApiKey] = useState('');
  const [model, setModel] = useState('');
  const [baseUrl, setBaseUrl] = useState('');

  const providers = [
    {
      value: 'ollama',
      label: 'Ollama (Local)',
      trust: 'local',
      trustLabel: 'Local - no data leaves cluster',
      needsApiKey: false,
      needsBaseUrl: true,
      defaultBaseUrl: 'http://ollama:11434',
      defaultModel: 'llama3.2',
      models: [
        { value: 'llama3.2', label: 'Llama 3.2 (Recommended)' },
        { value: 'llama3.1', label: 'Llama 3.1' },
        { value: 'mistral', label: 'Mistral' },
        { value: 'gemma2', label: 'Gemma 2' }
      ]
    },
    {
      value: 'openai',
      label: 'OpenAI',
      trust: 'external',
      trustLabel: 'External - data sent to OpenAI',
      needsApiKey: true,
      needsBaseUrl: false,
      defaultModel: 'gpt-4.1-mini',
      models: [
        { value: 'gpt-4.1', label: 'GPT-4.1 (Latest)' },
        { value: 'gpt-4.1-mini', label: 'GPT-4.1 Mini (Recommended)' },
        { value: 'gpt-4o', label: 'GPT-4o' }
      ]
    },
    {
      value: 'anthropic',
      label: 'Anthropic (Claude)',
      trust: 'external',
      trustLabel: 'External - data sent to Anthropic',
      needsApiKey: true,
      needsBaseUrl: false,
      defaultModel: 'claude-sonnet-4-20250514',
      models: [
        { value: 'claude-opus-4-5-20251124', label: 'Claude Opus 4.5 (Latest)' },
        { value: 'claude-sonnet-4-20250514', label: 'Claude Sonnet 4 (Recommended)' },
        { value: 'claude-haiku-4-5-20251015', label: 'Claude Haiku 4.5 (Fast)' }
      ]
    },
    {
      value: 'groq',
      label: 'Groq',
      trust: 'external',
      trustLabel: 'External - data sent to Groq',
      needsApiKey: true,
      needsBaseUrl: false,
      defaultModel: 'meta-llama/llama-4-scout-17b-16e-instruct',
      models: [
        { value: 'meta-llama/llama-4-maverick-17b-128e-instruct', label: 'Llama 4 Maverick (Best)' },
        { value: 'meta-llama/llama-4-scout-17b-16e-instruct', label: 'Llama 4 Scout (Recommended)' },
        { value: 'llama-3.3-70b-versatile', label: 'Llama 3.3 70B' }
      ]
    },
    {
      value: 'gemini',
      label: 'Google Gemini',
      trust: 'external',
      trustLabel: 'External - data sent to Google',
      needsApiKey: true,
      needsBaseUrl: false,
      defaultModel: 'gemini-2.0-flash',
      models: [
        { value: 'gemini-2.5-pro-preview-05-06', label: 'Gemini 2.5 Pro (Latest)' },
        { value: 'gemini-2.0-flash', label: 'Gemini 2.0 Flash (Recommended)' },
        { value: 'gemini-2.0-flash-lite', label: 'Gemini 2.0 Flash Lite (Fast)' }
      ]
    }
  ];

  const currentProvider = providers.find(p => p.value === provider);

  useEffect(() => {
    loadStatus();
    // Set default model for initial provider (ollama)
    if (!model) {
      setModel('llama3.2');
      setBaseUrl('http://ollama:11434');
    }
  }, []);

  const loadStatus = async () => {
    try {
      setLoading(true);
      const data = await api.getLLMStatus();
      setStatus(data);
      if (data.configured) {
        setProvider(data.provider || 'ollama');
        setModel(data.model || '');
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
    }
  };

  // Get current provider's models
  const currentProviderModels = currentProvider?.models || [];

  const buildPayload = () => {
    const payload = {
      provider,
      api_key: currentProvider?.needsApiKey ? apiKey : 'unused',
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

    try {
      setTesting(true);
      setError(null);
      const result = await api.testLLMConfig(buildPayload());
      if (result.success) {
        setSuccess('Connection successful! LLM is working.');
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

    try {
      setSaving(true);
      setError(null);
      await api.saveLLMConfig(buildPayload());
      setSuccess('LLM configuration saved successfully!');
      setApiKey(''); // Clear API key from form after save
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

  const canSubmit = currentProvider?.needsApiKey ? !!apiKey : true;

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
            <button
              onClick={handleDelete}
              disabled={saving}
              className="inline-flex items-center px-3 py-1.5 text-sm font-medium text-red-700 bg-red-50 border border-red-200 rounded-md hover:bg-red-100 disabled:opacity-50"
            >
              <Trash2 className="w-4 h-4 mr-1" />
              Delete
            </button>
          )}
        </div>
      </div>

      {/* Configuration Form */}
      <div className={`border rounded-md p-4 ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
        <h3 className={`text-sm font-medium mb-4 ${isDark ? 'text-gray-200' : 'text-gray-700'}`}>
          {status?.configured ? 'Update Configuration' : 'Configure LLM Provider'}
        </h3>

        <div className="space-y-4">
          {/* Provider Select */}
          <div>
            <label className={`block text-sm font-medium mb-1 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
              Provider
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

          {/* Trust Level Badge */}
          {currentProvider && (
            <div className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium ${
              currentProvider.trust === 'local'
                ? (isDark ? 'bg-green-900/40 text-green-300 border border-green-700' : 'bg-green-50 text-green-700 border border-green-200')
                : (isDark ? 'bg-yellow-900/40 text-yellow-300 border border-yellow-700' : 'bg-yellow-50 text-yellow-700 border border-yellow-200')
            }`}>
              <span className={`w-1.5 h-1.5 rounded-full mr-1.5 ${
                currentProvider.trust === 'local' ? 'bg-green-500' : 'bg-yellow-500'
              }`}></span>
              {currentProvider.trustLabel}
            </div>
          )}

          {/* API Key Input - only shown when provider needs it */}
          {currentProvider?.needsApiKey && (
            <div>
              <label className={`block text-sm font-medium mb-1 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                API Key
              </label>
              <div className="relative">
                <input
                  type={showApiKey ? 'text' : 'password'}
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder={status?.configured ? 'Enter new API key to update' : 'Enter your API key'}
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
              <p className={`mt-1 text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
                The URL where your Ollama instance is running
              </p>
            </div>
          )}

          {/* Model Select */}
          <div>
            <label className={`block text-sm font-medium mb-1 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
              Model
            </label>
            <select
              value={model}
              onChange={(e) => setModel(e.target.value)}
              className={`w-full px-3 py-2 text-sm border rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500 ${isDark ? 'bg-gray-700 border-gray-600 text-gray-200' : 'bg-white border-gray-300 text-gray-900'}`}
            >
              {currentProviderModels.map(m => (
                <option key={m.value} value={m.value}>{m.label}</option>
              ))}
            </select>
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
          </div>
        </div>
      </div>
    </div>
  );
};

export default LLMSettings;
