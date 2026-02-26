import React, { useState, useCallback } from 'react';
import { AlertCircle, CheckCircle, Bot, Bell, EyeOff, Key, Settings, ShieldAlert, X } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import NotificationSettings from './NotificationSettings';
import LLMSettings from './LLMSettings';
import ExclusionNamespaces from './admin/ExclusionNamespaces';
import ExclusionPods from './admin/ExclusionPods';
import ExclusionRules from './admin/ExclusionRules';
import ExclusionRegistries from './admin/ExclusionRegistries';
import RetentionSettings from './admin/RetentionSettings';
import ApiKeyManager from './admin/ApiKeyManager';

const AdminPanel = ({ isDark = false, onConfigChange }) => {
  // Tab state
  const [activeTab, setActiveTab] = useState('ai');

  // Error/success messages displayed at the top level
  const [error, setError] = useState(null);
  const [successMessage, setSuccessMessage] = useState(null);

  // Auth warning banner
  const { authEnabled } = useAuth();
  const [authBannerDismissed, setAuthBannerDismissed] = useState(
    () => localStorage.getItem('kure-auth-warning-dismissed') === 'true'
  );

  const dismissAuthBanner = () => {
    localStorage.setItem('kure-auth-warning-dismissed', 'true');
    setAuthBannerDismissed(true);
  };

  const baseTabs = [
    { id: 'ai', label: 'AI Config', icon: Bot },
    { id: 'notifications', label: 'Notifications', icon: Bell },
    { id: 'exclusions', label: 'Exclusions', icon: EyeOff },
    { id: 'settings', label: 'Settings', icon: Settings },
  ];

  const tabs = authEnabled
    ? [...baseTabs, { id: 'api-keys', label: 'API Keys', icon: Key }]
    : baseTabs;

  const handleSuccess = useCallback((message) => {
    setError(null);
    setSuccessMessage(message);
    setTimeout(() => setSuccessMessage(null), 3000);
  }, []);

  const handleError = useCallback((message) => {
    setError(message);
  }, []);

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

      {/* Auth Disabled Warning */}
      {authEnabled === false && !authBannerDismissed && (
        <div className={`mb-4 rounded-lg border ${isDark ? 'bg-amber-900/20 border-amber-800' : 'bg-amber-50 border-amber-200'}`}>
          <div className="px-4 py-3 flex items-center justify-between">
            <div className="flex items-center">
              <div className={`p-2 rounded-lg mr-3 ${isDark ? 'bg-amber-800' : 'bg-amber-100'}`}>
                <ShieldAlert className={`w-5 h-5 ${isDark ? 'text-amber-300' : 'text-amber-600'}`} />
              </div>
              <div>
                <h3 className={`text-sm font-semibold ${isDark ? 'text-amber-200' : 'text-amber-900'}`}>
                  Authentication Disabled
                </h3>
                <p className={`text-sm ${isDark ? 'text-amber-300' : 'text-amber-700'}`}>
                  Authentication is not enabled. Anyone with network access can view and modify your dashboard. Enable it via Helm: <code className={`text-xs px-1 py-0.5 rounded ${isDark ? 'bg-amber-800/50' : 'bg-amber-100'}`}>--set auth.apiKey=your-secret-key</code>
                </p>
              </div>
            </div>
            <button
              onClick={dismissAuthBanner}
              className={`p-1.5 rounded-md ml-4 flex-shrink-0 ${isDark ? 'text-amber-400 hover:bg-amber-800' : 'text-amber-500 hover:bg-amber-100'}`}
              title="Dismiss"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

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
      {activeTab === 'ai' && <LLMSettings isDark={isDark} onConfigChange={onConfigChange} />}

      {activeTab === 'notifications' && <NotificationSettings isDark={isDark} />}

      {activeTab === 'settings' && (
        <RetentionSettings isDark={isDark} onError={handleError} onSuccess={handleSuccess} />
      )}

      {activeTab === 'exclusions' && (
        <div className="space-y-8">
          <ExclusionNamespaces isDark={isDark} onError={handleError} onSuccess={handleSuccess} />
          <ExclusionPods isDark={isDark} onError={handleError} onSuccess={handleSuccess} />
          <ExclusionRules isDark={isDark} onError={handleError} onSuccess={handleSuccess} />
          <ExclusionRegistries isDark={isDark} onError={handleError} onSuccess={handleSuccess} />
        </div>
      )}

      {activeTab === 'api-keys' && (
        <ApiKeyManager isDark={isDark} onError={handleError} onSuccess={handleSuccess} />
      )}
    </div>
  );
};

export default AdminPanel;
