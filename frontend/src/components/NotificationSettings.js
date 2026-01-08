import React, { useState, useEffect } from 'react';
import { Bell, Mail, MessageSquare, Hash, Users, ChevronDown, ChevronRight, Save, TestTube, Trash2, Eye, EyeOff, AlertCircle, CheckCircle } from 'lucide-react';
import { api } from '../services/api';

const NotificationSettings = ({ isDark = false }) => {
  const [settings, setSettings] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState({});
  const [testing, setTesting] = useState({});
  const [error, setError] = useState(null);
  const [successMessage, setSuccessMessage] = useState(null);
  const [expandedProviders, setExpandedProviders] = useState({});
  const [showPasswords, setShowPasswords] = useState({});

  const providers = [
    {
      id: 'email',
      name: 'Email (SMTP)',
      icon: Mail,
      color: 'blue',
      fields: [
        { key: 'smtp_host', label: 'SMTP Host', type: 'text', placeholder: 'smtp.gmail.com' },
        { key: 'smtp_port', label: 'SMTP Port', type: 'number', placeholder: '587' },
        { key: 'smtp_user', label: 'SMTP Username', type: 'text', placeholder: 'your-email@gmail.com' },
        { key: 'smtp_password', label: 'SMTP Password', type: 'password', placeholder: 'App password' },
        { key: 'from_email', label: 'From Email', type: 'text', placeholder: 'alerts@yourcompany.com' },
        { key: 'to_emails', label: 'To Emails (comma-separated)', type: 'text', placeholder: 'admin@company.com, team@company.com' },
        { key: 'use_tls', label: 'Use TLS', type: 'checkbox' }
      ]
    },
    {
      id: 'slack',
      name: 'Slack',
      icon: Hash,
      color: 'purple',
      fields: [
        { key: 'webhook_url', label: 'Webhook URL', type: 'text', placeholder: 'https://hooks.slack.com/services/...' },
        { key: 'channel', label: 'Channel (optional)', type: 'text', placeholder: '#alerts' }
      ]
    },
    {
      id: 'discord',
      name: 'Discord',
      icon: MessageSquare,
      color: 'indigo',
      fields: [
        { key: 'webhook_url', label: 'Webhook URL', type: 'text', placeholder: 'https://discord.com/api/webhooks/...' }
      ]
    },
    {
      id: 'teams',
      name: 'Microsoft Teams',
      icon: Users,
      color: 'violet',
      fields: [
        { key: 'webhook_url', label: 'Webhook URL', type: 'text', placeholder: 'https://outlook.office.com/webhook/...' }
      ]
    }
  ];

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    try {
      setLoading(true);
      const data = await api.getNotificationSettings();
      const settingsMap = {};
      data.forEach(s => {
        settingsMap[s.provider] = {
          ...s,
          config: s.config || {}
        };
      });
      setSettings(settingsMap);
      setError(null);
    } catch (err) {
      setError('Failed to load notification settings');
      console.error('Error loading settings:', err);
    } finally {
      setLoading(false);
    }
  };

  const toggleExpand = (providerId) => {
    setExpandedProviders(prev => ({
      ...prev,
      [providerId]: !prev[providerId]
    }));
  };

  const togglePassword = (providerId, fieldKey) => {
    const key = `${providerId}-${fieldKey}`;
    setShowPasswords(prev => ({
      ...prev,
      [key]: !prev[key]
    }));
  };

  const handleConfigChange = (providerId, key, value) => {
    setSettings(prev => ({
      ...prev,
      [providerId]: {
        ...prev[providerId],
        provider: providerId,
        enabled: prev[providerId]?.enabled || false,
        config: {
          ...prev[providerId]?.config,
          [key]: value
        }
      }
    }));
  };

  const handleToggleEnabled = async (providerId) => {
    const currentSetting = settings[providerId];
    const newEnabled = !currentSetting?.enabled;

    setSettings(prev => ({
      ...prev,
      [providerId]: {
        ...prev[providerId],
        provider: providerId,
        enabled: newEnabled,
        config: prev[providerId]?.config || {}
      }
    }));

    // Auto-save when toggling
    try {
      const setting = {
        provider: providerId,
        enabled: newEnabled,
        config: currentSetting?.config || {}
      };
      await api.saveNotificationSetting(setting);
      setSuccessMessage(`${providerId} notifications ${newEnabled ? 'enabled' : 'disabled'}`);
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (err) {
      setError(`Failed to update ${providerId} settings`);
      // Revert on error
      setSettings(prev => ({
        ...prev,
        [providerId]: currentSetting
      }));
    }
  };

  const handleSave = async (providerId) => {
    setSaving(prev => ({ ...prev, [providerId]: true }));
    try {
      const setting = settings[providerId];

      // Process to_emails if it's a string
      const config = { ...setting.config };
      if (providerId === 'email' && typeof config.to_emails === 'string') {
        config.to_emails = config.to_emails.split(',').map(e => e.trim()).filter(e => e);
      }

      await api.saveNotificationSetting({
        provider: providerId,
        enabled: setting.enabled || false,
        config
      });

      setSuccessMessage(`${providerId} settings saved successfully`);
      setTimeout(() => setSuccessMessage(null), 3000);
      setError(null);
    } catch (err) {
      setError(`Failed to save ${providerId} settings`);
      console.error('Error saving settings:', err);
    } finally {
      setSaving(prev => ({ ...prev, [providerId]: false }));
    }
  };

  const handleTest = async (providerId) => {
    setTesting(prev => ({ ...prev, [providerId]: true }));
    try {
      await api.testNotification(providerId);
      setSuccessMessage(`Test notification sent via ${providerId}`);
      setTimeout(() => setSuccessMessage(null), 3000);
      setError(null);
    } catch (err) {
      setError(`Failed to send test notification via ${providerId}`);
      console.error('Error testing notification:', err);
    } finally {
      setTesting(prev => ({ ...prev, [providerId]: false }));
    }
  };

  const handleDelete = async (providerId) => {
    if (!window.confirm(`Are you sure you want to delete ${providerId} notification settings?`)) {
      return;
    }

    try {
      await api.deleteNotificationSetting(providerId);
      setSettings(prev => {
        const updated = { ...prev };
        delete updated[providerId];
        return updated;
      });
      setSuccessMessage(`${providerId} settings deleted`);
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (err) {
      setError(`Failed to delete ${providerId} settings`);
    }
  };

  const getFieldValue = (providerId, fieldKey) => {
    const config = settings[providerId]?.config || {};
    const value = config[fieldKey];

    // Handle to_emails array display
    if (fieldKey === 'to_emails' && Array.isArray(value)) {
      return value.join(', ');
    }

    return value !== undefined ? value : (fieldKey === 'use_tls' ? true : '');
  };

  const colorClasses = {
    blue: 'bg-blue-100 text-blue-700 border-blue-200',
    purple: 'bg-purple-100 text-purple-700 border-purple-200',
    indigo: 'bg-indigo-100 text-indigo-700 border-indigo-200',
    violet: 'bg-violet-100 text-violet-700 border-violet-200'
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
        <span className={`ml-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Loading notification settings...</span>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-4 flex items-center">
        <Bell className="w-5 h-5 text-green-500 mr-2" />
        <h2 className={`text-lg font-semibold ${isDark ? 'text-gray-100' : 'text-gray-900'}`}>Notification Settings</h2>
      </div>
      <p className={`text-sm mb-4 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
        Configure how you want to be notified when pod failures are detected.
        Enable one or more providers and configure their settings below.
      </p>

      {error && (
        <div className={`mb-4 border rounded-md p-3 ${isDark ? 'bg-red-900/30 border-red-800' : 'bg-red-50 border-red-200'}`}>
          <div className="flex items-center">
            <AlertCircle className="w-4 h-4 text-red-500 mr-2" />
            <span className={`text-sm ${isDark ? 'text-red-300' : 'text-red-800'}`}>{error}</span>
          </div>
        </div>
      )}

      {successMessage && (
        <div className={`mb-4 border rounded-md p-3 ${isDark ? 'bg-green-900/30 border-green-800' : 'bg-green-50 border-green-200'}`}>
          <div className="flex items-center">
            <CheckCircle className="w-4 h-4 text-green-500 mr-2" />
            <span className={`text-sm ${isDark ? 'text-green-300' : 'text-green-800'}`}>{successMessage}</span>
          </div>
        </div>
      )}

      <div className="space-y-3">
        {providers.map(provider => {
          const Icon = provider.icon;
          const isExpanded = expandedProviders[provider.id];
          const isEnabled = settings[provider.id]?.enabled || false;
          const hasSaved = settings[provider.id]?.id;

          return (
            <div key={provider.id} className={`border rounded-lg overflow-hidden ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
              <div
                className={`flex items-center justify-between px-4 py-3 cursor-pointer ${isDark ? 'bg-gray-900 hover:bg-gray-800' : 'bg-gray-50 hover:bg-gray-100'}`}
                onClick={() => toggleExpand(provider.id)}
              >
                <div className="flex items-center">
                  {isExpanded ? (
                    <ChevronDown className={`w-4 h-4 mr-2 ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
                  ) : (
                    <ChevronRight className={`w-4 h-4 mr-2 ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
                  )}
                  <div className={`p-1.5 rounded ${colorClasses[provider.color]}`}>
                    <Icon className="w-4 h-4" />
                  </div>
                  <span className={`ml-2 font-medium ${isDark ? 'text-gray-200' : 'text-gray-900'}`}>{provider.name}</span>
                  {hasSaved && (
                    <span className={`ml-2 px-2 py-0.5 text-xs rounded-full ${isEnabled ? 'bg-green-100 text-green-700' : (isDark ? 'bg-gray-700 text-gray-400' : 'bg-gray-100 text-gray-600')}`}>
                      {isEnabled ? 'Enabled' : 'Disabled'}
                    </span>
                  )}
                </div>
                <div className="flex items-center" onClick={e => e.stopPropagation()}>
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      checked={isEnabled}
                      onChange={() => handleToggleEnabled(provider.id)}
                      className="sr-only peer"
                    />
                    <div className="w-9 h-5 bg-gray-200 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-blue-600"></div>
                  </label>
                </div>
              </div>

              {isExpanded && (
                <div className={`px-4 py-4 border-t ${isDark ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'}`}>
                  <div className="space-y-4">
                    {provider.fields.map(field => (
                      <div key={field.key}>
                        <label className={`block text-sm font-medium mb-1 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                          {field.label}
                        </label>
                        {field.type === 'checkbox' ? (
                          <label className="relative inline-flex items-center cursor-pointer">
                            <input
                              type="checkbox"
                              checked={getFieldValue(provider.id, field.key)}
                              onChange={(e) => handleConfigChange(provider.id, field.key, e.target.checked)}
                              className="sr-only peer"
                            />
                            <div className="w-9 h-5 bg-gray-200 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-blue-600"></div>
                            <span className={`ml-2 text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Enable TLS encryption</span>
                          </label>
                        ) : field.type === 'password' ? (
                          <div className="relative">
                            <input
                              type={showPasswords[`${provider.id}-${field.key}`] ? 'text' : 'password'}
                              value={getFieldValue(provider.id, field.key)}
                              onChange={(e) => handleConfigChange(provider.id, field.key, e.target.value)}
                              placeholder={field.placeholder}
                              className={`w-full px-3 py-2 text-sm border rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 pr-10 ${isDark ? 'bg-gray-700 border-gray-600 text-gray-200 placeholder-gray-400' : 'bg-white border-gray-300 text-gray-900'}`}
                            />
                            <button
                              type="button"
                              onClick={() => togglePassword(provider.id, field.key)}
                              className={`absolute right-2 top-1/2 -translate-y-1/2 ${isDark ? 'text-gray-400 hover:text-gray-200' : 'text-gray-400 hover:text-gray-600'}`}
                            >
                              {showPasswords[`${provider.id}-${field.key}`] ? (
                                <EyeOff className="w-4 h-4" />
                              ) : (
                                <Eye className="w-4 h-4" />
                              )}
                            </button>
                          </div>
                        ) : (
                          <input
                            type={field.type}
                            value={getFieldValue(provider.id, field.key)}
                            onChange={(e) => handleConfigChange(provider.id, field.key, field.type === 'number' ? parseInt(e.target.value) || '' : e.target.value)}
                            placeholder={field.placeholder}
                            className={`w-full px-3 py-2 text-sm border rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 ${isDark ? 'bg-gray-700 border-gray-600 text-gray-200 placeholder-gray-400' : 'bg-white border-gray-300 text-gray-900'}`}
                          />
                        )}
                      </div>
                    ))}
                  </div>

                  <div className={`mt-4 pt-4 border-t flex items-center gap-2 ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
                    <button
                      onClick={() => handleSave(provider.id)}
                      disabled={saving[provider.id]}
                      className="inline-flex items-center px-3 py-1.5 text-sm font-medium text-white bg-blue-600 border border-transparent rounded-md shadow-sm hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50"
                    >
                      {saving[provider.id] ? (
                        <>
                          <div className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin mr-1.5"></div>
                          Saving...
                        </>
                      ) : (
                        <>
                          <Save className="w-3 h-3 mr-1.5" />
                          Save
                        </>
                      )}
                    </button>

                    {hasSaved && (
                      <>
                        <button
                          onClick={() => handleTest(provider.id)}
                          disabled={testing[provider.id] || !isEnabled}
                          className={`inline-flex items-center px-3 py-1.5 text-sm font-medium border rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50 ${isDark ? 'text-gray-300 bg-gray-700 border-gray-600 hover:bg-gray-600' : 'text-gray-700 bg-white border-gray-300 hover:bg-gray-50'}`}
                        >
                          {testing[provider.id] ? (
                            <>
                              <div className="w-3 h-3 border-2 border-gray-400 border-t-transparent rounded-full animate-spin mr-1.5"></div>
                              Sending...
                            </>
                          ) : (
                            <>
                              <TestTube className="w-3 h-3 mr-1.5" />
                              Test
                            </>
                          )}
                        </button>

                        <button
                          onClick={() => handleDelete(provider.id)}
                          className="inline-flex items-center px-3 py-1.5 text-sm font-medium text-red-700 bg-white border border-red-200 rounded-md shadow-sm hover:bg-red-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500"
                        >
                          <Trash2 className="w-3 h-3 mr-1.5" />
                          Delete
                        </button>
                      </>
                    )}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default NotificationSettings;
