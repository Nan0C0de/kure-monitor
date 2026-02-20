import React, { useState, useEffect } from 'react';
import { Bot, X, Settings, Sparkles } from 'lucide-react';
import { api } from '../services/api';

const SetupBanner = ({ isDark = false, onNavigateToAdmin }) => {
  const [visible, setVisible] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    // Check if user has dismissed the banner in this session
    const sessionDismissed = sessionStorage.getItem('kure-setup-banner-dismissed');
    if (sessionDismissed) {
      return;
    }

    // Check LLM configuration status
    const checkStatus = async () => {
      try {
        const status = await api.getLLMStatus();
        if (!status.configured) {
          setVisible(true);
        }
      } catch (err) {
        console.error('Failed to check LLM status:', err);
      }
    };

    checkStatus();
  }, []);

  const handleDismiss = () => {
    setDismissed(true);
    setVisible(false);
    sessionStorage.setItem('kure-setup-banner-dismissed', 'true');
  };

  const handleConfigure = () => {
    handleDismiss();
    if (onNavigateToAdmin) {
      onNavigateToAdmin();
    }
  };

  if (!visible || dismissed) {
    return null;
  }

  return (
    <div className={`mb-4 rounded-lg border ${isDark ? 'bg-purple-900/20 border-purple-800' : 'bg-purple-50 border-purple-200'}`}>
      <div className="px-4 py-3 flex items-center justify-between">
        <div className="flex items-center">
          <div className={`p-2 rounded-lg mr-3 ${isDark ? 'bg-purple-800' : 'bg-purple-100'}`}>
            <Sparkles className={`w-5 h-5 ${isDark ? 'text-purple-300' : 'text-purple-600'}`} />
          </div>
          <div>
            <h3 className={`text-sm font-semibold ${isDark ? 'text-purple-200' : 'text-purple-900'}`}>
              Enable AI-Powered Solutions
            </h3>
            <p className={`text-sm ${isDark ? 'text-purple-300' : 'text-purple-700'}`}>
              Configure an LLM provider (Ollama for local/air-gapped, or OpenAI, Anthropic, Groq, Gemini) to get intelligent troubleshooting suggestions for pod failures.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 ml-4">
          <button
            onClick={handleConfigure}
            className={`inline-flex items-center px-3 py-1.5 text-sm font-medium rounded-md ${isDark ? 'bg-purple-600 text-white hover:bg-purple-500' : 'bg-purple-600 text-white hover:bg-purple-700'}`}
          >
            <Settings className="w-4 h-4 mr-1.5" />
            Configure
          </button>
          <button
            onClick={handleDismiss}
            className={`p-1.5 rounded-md ${isDark ? 'text-purple-400 hover:bg-purple-800' : 'text-purple-500 hover:bg-purple-100'}`}
            title="Dismiss"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
};

export default SetupBanner;
