// Fixed API URL for security - users cannot modify this
const API_BASE = window.location.hostname === 'localhost' && window.location.port === '3000'
  ? 'http://localhost:8000'  // Development mode
  : '';  // Production mode (same origin)

/**
 * Wrapper around fetch that injects the auth header and handles 401 globally.
 */
const authFetch = async (url, options = {}) => {
  const apiKey = sessionStorage.getItem('kure-auth-key');
  if (apiKey) {
    options.headers = {
      ...options.headers,
      'Authorization': `Bearer ${apiKey}`,
    };
  }
  const response = await fetch(url, options);
  if (response.status === 401) {
    // Auth failed - clear session and redirect to login
    sessionStorage.removeItem('kure-auth-key');
    window.location.href = '/login';
    throw new Error('Authentication required');
  }
  return response;
};

export const api = {
  getConfig: async () => {
    const response = await authFetch(`${API_BASE}/api/config`);
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  getFailedPods: async () => {
    const response = await authFetch(`${API_BASE}/api/pods/failed`);
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  dismissPod: async (podId) => {
    const response = await authFetch(`${API_BASE}/api/pods/failed/${podId}`, {
      method: 'DELETE'
    });
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  updatePodStatus: async (podId, status, resolutionNote = null) => {
    const body = { status };
    if (resolutionNote) {
      body.resolution_note = resolutionNote;
    }
    const response = await authFetch(`${API_BASE}/api/pods/failed/${podId}/status`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  getPodHistory: async () => {
    const response = await authFetch(`${API_BASE}/api/pods/history`);
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  getIgnoredPods: async () => {
    const response = await authFetch(`${API_BASE}/api/pods/ignored`);
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  deletePodRecord: async (podId) => {
    const response = await authFetch(`${API_BASE}/api/pods/records/${podId}`, {
      method: 'DELETE'
    });
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  getHistoryRetention: async () => {
    const response = await authFetch(`${API_BASE}/api/admin/settings/history-retention`);
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  setHistoryRetention: async (minutes) => {
    const response = await authFetch(`${API_BASE}/api/admin/settings/history-retention`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ minutes })
    });
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  getIgnoredRetention: async () => {
    const response = await authFetch(`${API_BASE}/api/admin/settings/ignored-retention`);
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  setIgnoredRetention: async (minutes) => {
    const response = await authFetch(`${API_BASE}/api/admin/settings/ignored-retention`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ minutes })
    });
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  retrySolution: async (podId) => {
    const response = await authFetch(`${API_BASE}/api/pods/failed/${podId}/retry-solution`, {
      method: 'POST'
    });
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  // Security findings API
  getSecurityFindings: async () => {
    const response = await authFetch(`${API_BASE}/api/security/findings`);
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  dismissSecurityFinding: async (findingId) => {
    const response = await authFetch(`${API_BASE}/api/security/findings/${findingId}`, {
      method: 'DELETE'
    });
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  getSecurityFindingManifest: async (findingId) => {
    const response = await authFetch(`${API_BASE}/api/security/findings/${findingId}/manifest`);
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  generateSecurityFix: async (findingId) => {
    const response = await authFetch(`${API_BASE}/api/security/findings/${findingId}/fix`, {
      method: 'POST'
    });
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  triggerSecurityRescan: async () => {
    const response = await authFetch(`${API_BASE}/api/security/rescan`, {
      method: 'POST'
    });
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  // Admin API - Excluded Namespaces
  getExcludedNamespaces: async () => {
    const response = await authFetch(`${API_BASE}/api/admin/excluded-namespaces`);
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  getAllNamespaces: async () => {
    const response = await authFetch(`${API_BASE}/api/admin/namespaces`);
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  addExcludedNamespace: async (namespace) => {
    const response = await authFetch(`${API_BASE}/api/admin/excluded-namespaces`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ namespace })
    });
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  removeExcludedNamespace: async (namespace) => {
    const response = await authFetch(`${API_BASE}/api/admin/excluded-namespaces/${encodeURIComponent(namespace)}`, {
      method: 'DELETE'
    });
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  // Admin API - Excluded Pods (Pod Monitoring Exclusions - by pod name only)
  getExcludedPods: async () => {
    const response = await authFetch(`${API_BASE}/api/admin/excluded-pods`);
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  getMonitoredPods: async () => {
    const response = await authFetch(`${API_BASE}/api/admin/monitored-pods`);
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  addExcludedPod: async (podName) => {
    const response = await authFetch(`${API_BASE}/api/admin/excluded-pods`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ pod_name: podName })
    });
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  removeExcludedPod: async (podName) => {
    const response = await authFetch(`${API_BASE}/api/admin/excluded-pods/${encodeURIComponent(podName)}`, {
      method: 'DELETE'
    });
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  // Admin API - Excluded Security Rules
  getExcludedRules: async () => {
    const response = await authFetch(`${API_BASE}/api/admin/excluded-rules`);
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  getAllRuleTitles: async (namespace = null) => {
    let url = `${API_BASE}/api/admin/rule-titles`;
    if (namespace) {
      url += `?namespace=${encodeURIComponent(namespace)}`;
    }
    const response = await authFetch(url);
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  addExcludedRule: async (ruleTitle, namespace = null) => {
    const body = { rule_title: ruleTitle };
    if (namespace) {
      body.namespace = namespace;
    }
    const response = await authFetch(`${API_BASE}/api/admin/excluded-rules`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(body)
    });
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  removeExcludedRule: async (ruleTitle, namespace = null) => {
    let url = `${API_BASE}/api/admin/excluded-rules/${encodeURIComponent(ruleTitle)}`;
    if (namespace) {
      url += `?namespace=${encodeURIComponent(namespace)}`;
    }
    const response = await authFetch(url, {
      method: 'DELETE'
    });
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  // Admin API - Trusted Container Registries
  getTrustedRegistries: async () => {
    const response = await authFetch(`${API_BASE}/api/admin/trusted-registries`);
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  addTrustedRegistry: async (registry) => {
    const response = await authFetch(`${API_BASE}/api/admin/trusted-registries`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ registry })
    });
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  removeTrustedRegistry: async (registry) => {
    const response = await authFetch(`${API_BASE}/api/admin/trusted-registries/${encodeURIComponent(registry)}`, {
      method: 'DELETE'
    });
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return true;
  },

  // Notification Settings API
  getNotificationSettings: async () => {
    const response = await authFetch(`${API_BASE}/api/admin/notifications`);
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  saveNotificationSetting: async (setting) => {
    const response = await authFetch(`${API_BASE}/api/admin/notifications`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(setting)
    });
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  updateNotificationSetting: async (provider, setting) => {
    const response = await authFetch(`${API_BASE}/api/admin/notifications/${encodeURIComponent(provider)}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(setting)
    });
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  deleteNotificationSetting: async (provider) => {
    const response = await authFetch(`${API_BASE}/api/admin/notifications/${encodeURIComponent(provider)}`, {
      method: 'DELETE'
    });
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  testNotification: async (provider) => {
    const response = await authFetch(`${API_BASE}/api/admin/notifications/${encodeURIComponent(provider)}/test`, {
      method: 'POST'
    });
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  // Cluster Metrics API
  getClusterMetrics: async () => {
    const response = await authFetch(`${API_BASE}/api/metrics/cluster`);
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  // Pod Metrics History API
  getPodMetricsHistory: async (namespace, podName) => {
    const url = `${API_BASE}/api/metrics/pods/${encodeURIComponent(namespace)}/${encodeURIComponent(podName)}/history`;
    const response = await authFetch(url);
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  // Pod Logs API
  getPodLogs: async (namespace, podName, options = {}) => {
    const params = new URLSearchParams();
    if (options.container) params.append('container', options.container);
    if (options.tailLines) params.append('tail_lines', options.tailLines);
    if (options.previous) params.append('previous', 'true');

    const url = `${API_BASE}/api/pods/${encodeURIComponent(namespace)}/${encodeURIComponent(podName)}/logs?${params}`;
    const response = await authFetch(url);
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  // Streaming Pod Logs API (returns EventSource URL with auth token)
  getStreamingLogsUrl: (namespace, podName, options = {}) => {
    const params = new URLSearchParams();
    if (options.container) params.append('container', options.container);
    if (options.tailLines) params.append('tail_lines', options.tailLines);

    // Append auth token for SSE (EventSource cannot set headers)
    const apiKey = sessionStorage.getItem('kure-auth-key');
    if (apiKey) params.append('token', apiKey);

    return `${API_BASE}/api/pods/${encodeURIComponent(namespace)}/${encodeURIComponent(podName)}/logs/stream?${params}`;
  },

  // LLM Configuration API
  getLLMStatus: async () => {
    const response = await authFetch(`${API_BASE}/api/admin/llm/status`);
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  saveLLMConfig: async (config) => {
    const response = await authFetch(`${API_BASE}/api/admin/llm/config`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(config)
    });
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  deleteLLMConfig: async () => {
    const response = await authFetch(`${API_BASE}/api/admin/llm/config`, {
      method: 'DELETE'
    });
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  testLLMConfig: async (config) => {
    const response = await authFetch(`${API_BASE}/api/admin/llm/test`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(config)
    });
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  // API Key Management
  getApiKeys: async () => {
    const response = await authFetch(`${API_BASE}/api/admin/api-keys`);
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  createApiKey: async (name, role) => {
    const response = await authFetch(`${API_BASE}/api/admin/api-keys`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, role })
    });
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  revokeApiKey: async (keyId) => {
    const response = await authFetch(`${API_BASE}/api/admin/api-keys/${keyId}`, {
      method: 'DELETE'
    });
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

};
