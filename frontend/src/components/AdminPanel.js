import React, { useState, useCallback } from 'react';
import { AlertCircle, CheckCircle, ShieldCheck, Bot, Bell, EyeOff, Settings } from 'lucide-react';
import NotificationSettings from './NotificationSettings';
import LLMSettings from './LLMSettings';
import KyvernoPolicies from './KyvernoPolicies';
import ExclusionNamespaces from './admin/ExclusionNamespaces';
import ExclusionPods from './admin/ExclusionPods';
import ExclusionRules from './admin/ExclusionRules';
import ExclusionRegistries from './admin/ExclusionRegistries';
import RetentionSettings from './admin/RetentionSettings';

const AdminPanel = ({ isDark = false, onConfigChange }) => {
  // Tab state
  const [activeTab, setActiveTab] = useState('ai');

  // Error/success messages displayed at the top level
  const [error, setError] = useState(null);
  const [successMessage, setSuccessMessage] = useState(null);

  const tabs = [
    { id: 'ai', label: 'AI Config', icon: Bot },
    { id: 'notifications', label: 'Notifications', icon: Bell },
    { id: 'policies', label: 'Policies', icon: ShieldCheck },
    { id: 'exclusions', label: 'Exclusions', icon: EyeOff },
    { id: 'settings', label: 'Settings', icon: Settings },
  ];

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

      {activeTab === 'policies' && <KyvernoPolicies isDark={isDark} />}

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
    </div>
  );
};

export default AdminPanel;
