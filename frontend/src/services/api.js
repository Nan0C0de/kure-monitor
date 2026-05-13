// Fixed API URL for security - users cannot modify this
const API_BASE = window.location.hostname === 'localhost' && window.location.port === '3000'
  ? 'http://localhost:8000'  // Development mode
  : '';  // Production mode (same origin)

export { API_BASE };

/**
 * Wrapper around fetch that always sends cookies and handles 401 globally.
 * Auth is done via an HttpOnly `kure_session` cookie set by the backend.
 */
const authFetch = async (url, options = {}) => {
  const response = await fetch(url, {
    ...options,
    credentials: 'include',
  });
  if (response.status === 401) {
    // Don't hard-redirect away from public routes (login/setup/invite).
    const path = window.location.pathname;
    const isPublicRoute =
      path === '/login' ||
      path === '/setup' ||
      path.startsWith('/invite/');
    if (!isPublicRoute) {
      window.location.href = '/login';
    }
    throw new Error('Authentication required');
  }
  return response;
};

// Helper to extract error messages from backend responses.
const extractError = async (response, fallback) => {
  try {
    const data = await response.json();
    if (data?.detail) return data.detail;
    if (typeof data === 'string') return data;
  } catch {
    // ignore JSON parse errors
  }
  return fallback;
};

export const api = {
  // ============================================================
  // Auth endpoints
  // ============================================================
  getAuthSetupRequired: async () => {
    const response = await fetch(`${API_BASE}/api/auth/setup-required`, {
      credentials: 'include',
    });
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  getAuthMe: async () => {
    const response = await fetch(`${API_BASE}/api/auth/me`, {
      credentials: 'include',
    });
    if (response.status === 401) {
      const err = new Error('Not authenticated');
      err.status = 401;
      throw err;
    }
    if (!response.ok) {
      const err = new Error(`HTTP error! status: ${response.status}`);
      err.status = response.status;
      throw err;
    }
    return response.json();
  },

  setupAdmin: async ({ username, password, email }) => {
    const body = { username, password };
    if (email) body.email = email;
    const response = await fetch(`${API_BASE}/api/auth/setup`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      const msg = await extractError(response, 'Setup failed');
      const err = new Error(msg);
      err.status = response.status;
      throw err;
    }
    return response.json();
  },

  login: async ({ username, password }) => {
    const response = await fetch(`${API_BASE}/api/auth/login`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    if (!response.ok) {
      const msg = await extractError(response, 'Login failed');
      const err = new Error(msg);
      err.status = response.status;
      throw err;
    }
    return response.json();
  },

  logout: async () => {
    const response = await fetch(`${API_BASE}/api/auth/logout`, {
      method: 'POST',
      credentials: 'include',
    });
    // Even if server returns an error, we consider the user logged out client-side.
    return response.ok ? response.json().catch(() => ({})) : {};
  },

  getInvitation: async (token) => {
    const response = await fetch(
      `${API_BASE}/api/auth/invitation/${encodeURIComponent(token)}`,
      { credentials: 'include' }
    );
    if (!response.ok) {
      const err = new Error(`HTTP error! status: ${response.status}`);
      err.status = response.status;
      throw err;
    }
    return response.json();
  },

  acceptInvitation: async ({ token, username, password, email }) => {
    const body = { token, username, password };
    if (email) body.email = email;
    const response = await fetch(`${API_BASE}/api/auth/accept-invitation`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      const msg = await extractError(response, 'Failed to accept invitation');
      const err = new Error(msg);
      err.status = response.status;
      throw err;
    }
    return response.json();
  },

  // ============================================================
  // Admin: Users
  // ============================================================
  getUsers: async () => {
    const response = await authFetch(`${API_BASE}/api/admin/users`);
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  updateUserRole: async (userId, role) => {
    const response = await authFetch(`${API_BASE}/api/admin/users/${userId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ role }),
    });
    if (!response.ok) {
      const msg = await extractError(response, `HTTP error! status: ${response.status}`);
      const err = new Error(msg);
      err.status = response.status;
      throw err;
    }
    return response.json();
  },

  deleteUser: async (userId) => {
    const response = await authFetch(`${API_BASE}/api/admin/users/${userId}`, {
      method: 'DELETE',
    });
    if (!response.ok) {
      const msg = await extractError(response, `HTTP error! status: ${response.status}`);
      const err = new Error(msg);
      err.status = response.status;
      throw err;
    }
    return response.json().catch(() => ({}));
  },

  // ============================================================
  // Admin: Invitations
  // ============================================================
  getInvitations: async () => {
    const response = await authFetch(`${API_BASE}/api/admin/invitations`);
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  createInvitation: async ({ role, expiresInHours }) => {
    const body = { role };
    if (expiresInHours != null) body.expires_in_hours = expiresInHours;
    const response = await authFetch(`${API_BASE}/api/admin/invitations`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      const msg = await extractError(response, 'Failed to create invitation');
      const err = new Error(msg);
      err.status = response.status;
      throw err;
    }
    return response.json();
  },

  revokeInvitation: async (invitationId) => {
    const response = await authFetch(`${API_BASE}/api/admin/invitations/${invitationId}`, {
      method: 'DELETE',
    });
    if (!response.ok) {
      const msg = await extractError(response, `HTTP error! status: ${response.status}`);
      const err = new Error(msg);
      err.status = response.status;
      throw err;
    }
    return response.json().catch(() => ({}));
  },

  // ============================================================
  // App endpoints (all use cookie auth)
  // ============================================================
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

  generateLogAwareSolution: async (podId) => {
    const response = await authFetch(`${API_BASE}/api/pods/failed/${podId}/troubleshoot`, {
      method: 'POST'
    });
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  regenerateLogAwareSolution: async (podId) => {
    const response = await authFetch(`${API_BASE}/api/pods/failed/${podId}/troubleshoot?regenerate=true`, {
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

  // Admin API - Excluded Pods
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

  // Streaming Pod Logs API (EventSource with cookie auth)
  getStreamingLogsUrl: (namespace, podName, options = {}) => {
    const params = new URLSearchParams();
    if (options.container) params.append('container', options.container);
    if (options.tailLines) params.append('tail_lines', options.tailLines);

    const query = params.toString();
    const base = `${API_BASE}/api/pods/${encodeURIComponent(namespace)}/${encodeURIComponent(podName)}/logs/stream`;
    return query ? `${base}?${query}` : `${base}?`;
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

  // Mirror Pod API
  previewMirrorPod: async (podId) => {
    const response = await authFetch(`${API_BASE}/api/mirror/preview/${podId}`, {
      method: 'POST'
    });
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  deployMirrorPod: async (podId, ttlSeconds, manifest = null) => {
    const body = { ttl_seconds: ttlSeconds };
    if (manifest) {
      body.manifest = manifest;
    }
    const response = await authFetch(`${API_BASE}/api/mirror/deploy/${podId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  getMirrorStatus: async (mirrorId) => {
    const response = await authFetch(`${API_BASE}/api/mirror/status/${mirrorId}`);
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  deleteMirrorPod: async (mirrorId) => {
    const response = await authFetch(`${API_BASE}/api/mirror/${mirrorId}`, {
      method: 'DELETE'
    });
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  getActiveMirrors: async () => {
    const response = await authFetch(`${API_BASE}/api/mirror/active`);
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  getMirrorTTL: async () => {
    const response = await authFetch(`${API_BASE}/api/admin/settings/mirror-ttl`);
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  setMirrorTTL: async (seconds) => {
    const response = await authFetch(`${API_BASE}/api/admin/settings/mirror-ttl`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ seconds })
    });
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  // Diagram API
  getDiagramNamespaces: async (kind) => {
    const url = kind
      ? `${API_BASE}/api/diagram/namespaces?kind=${encodeURIComponent(kind)}`
      : `${API_BASE}/api/diagram/namespaces`;
    const response = await authFetch(url);
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  getDiagramNamespace: async (namespace) => {
    const response = await authFetch(
      `${API_BASE}/api/diagram/namespace/${encodeURIComponent(namespace)}`
    );
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  getDiagramWorkloads: async (namespace, kind) => {
    const url = `${API_BASE}/api/diagram/workloads/${encodeURIComponent(namespace)}/${encodeURIComponent(kind)}`;
    const response = await authFetch(url);
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  getDiagramWorkload: async (namespace, kind, name) => {
    const url = `${API_BASE}/api/diagram/workload/${encodeURIComponent(namespace)}/${encodeURIComponent(kind)}/${encodeURIComponent(name)}`;
    const response = await authFetch(url);
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  getDiagramRoles: async () => {
    const response = await authFetch(`${API_BASE}/api/diagram/roles`);
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  getDiagramRole: async (namespace, name) => {
    const url = `${API_BASE}/api/diagram/role/${encodeURIComponent(namespace)}/${encodeURIComponent(name)}`;
    const response = await authFetch(url);
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  getDiagramClusterRole: async (name) => {
    const url = `${API_BASE}/api/diagram/clusterrole/${encodeURIComponent(name)}`;
    const response = await authFetch(url);
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  // ============================================================
  // AI Advice API
  // ============================================================
  getAdviceFindings: async (params = {}) => {
    const search = new URLSearchParams();
    if (params.include_dismissed) search.append('include_dismissed', 'true');
    if (params.dismissed_only) search.append('dismissed_only', 'true');
    if (params.namespace) search.append('namespace', params.namespace);
    if (params.resource_kind) search.append('resource_kind', params.resource_kind);
    if (params.resource_name) search.append('resource_name', params.resource_name);
    const query = search.toString();
    const url = query
      ? `${API_BASE}/api/advice/findings?${query}`
      : `${API_BASE}/api/advice/findings`;
    const response = await authFetch(url);
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  getAdviceFinding: async (findingId) => {
    const response = await authFetch(`${API_BASE}/api/advice/findings/${findingId}`);
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  runAdviceScan: async (scope = {}) => {
    const body = {};
    if (scope.namespace) body.namespace = scope.namespace;
    if (scope.workload_kind) body.workload_kind = scope.workload_kind;
    if (scope.workload_name) body.workload_name = scope.workload_name;
    if (scope.pod_name) body.pod_name = scope.pod_name;
    const response = await authFetch(`${API_BASE}/api/advice/scan`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      const msg = await extractError(response, `HTTP error! status: ${response.status}`);
      const err = new Error(msg);
      err.status = response.status;
      throw err;
    }
    return response.json();
  },

  dismissAdviceFinding: async (findingId) => {
    const response = await authFetch(`${API_BASE}/api/advice/findings/${findingId}`, {
      method: 'DELETE',
    });
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  restoreAdviceFinding: async (findingId) => {
    const response = await authFetch(`${API_BASE}/api/advice/findings/${findingId}/restore`, {
      method: 'PUT',
    });
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  // Lazily generate (or fetch a cached) LLM explanation for a finding.
  // Idempotent on the backend — calling again on a finding whose explanation
  // is already populated is cheap.
  explainAdviceFinding: async (findingId) => {
    const response = await authFetch(
      `${API_BASE}/api/advice/findings/${findingId}/explain`,
      { method: 'POST' },
    );
    if (!response.ok) {
      const msg = await extractError(response, `HTTP error! status: ${response.status}`);
      const err = new Error(msg);
      err.status = response.status;
      throw err;
    }
    return response.json();
  },

  // Advice detector configuration
  getAdviceDetectors: async () => {
    const response = await authFetch(`${API_BASE}/api/advice/detectors`);
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  setAdviceDetectorEnabled: async (detectorId, enabled) => {
    const response = await authFetch(
      `${API_BASE}/api/advice/detectors/${encodeURIComponent(detectorId)}`,
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled }),
      },
    );
    if (!response.ok) {
      const msg = await extractError(response, `HTTP error! status: ${response.status}`);
      const err = new Error(msg);
      err.status = response.status;
      throw err;
    }
    return response.json();
  },

  // Build the URL for the findings export endpoint. The browser will
  // follow Content-Disposition to save the file with the backend-supplied name.
  getAdviceFindingsExportUrl: (format, params = {}) => {
    const search = new URLSearchParams();
    search.append('format', format);
    if (params.include_dismissed) search.append('include_dismissed', 'true');
    if (params.dismissed_only) search.append('dismissed_only', 'true');
    if (params.namespace) search.append('namespace', params.namespace);
    if (params.resource_kind) search.append('resource_kind', params.resource_kind);
    if (params.resource_name) search.append('resource_name', params.resource_name);
    return `${API_BASE}/api/advice/findings/export?${search.toString()}`;
  },

  // Cookie auth needs `credentials: include`, which a plain anchor click on a
  // cross-origin dev URL would not send. Fetch the blob ourselves and trigger
  // a download from an object URL.
  downloadAdviceFindings: async (format, params = {}) => {
    const url = api.getAdviceFindingsExportUrl(format, params);
    const response = await authFetch(url);
    if (!response.ok) {
      const msg = await extractError(response, `HTTP error! status: ${response.status}`);
      const err = new Error(msg);
      err.status = response.status;
      throw err;
    }
    const blob = await response.blob();
    // Try to honor the backend's Content-Disposition filename.
    let filename = `advice-findings.${format}`;
    const disposition = response.headers.get('Content-Disposition') || '';
    const match = disposition.match(/filename="?([^";]+)"?/i);
    if (match && match[1]) {
      filename = match[1];
    }
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = objectUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    // Free memory soon after the click is fired.
    setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
    return { ok: true, filename };
  },

  getResourceManifest: async (namespace, kind, name) => {
    const url = `${API_BASE}/api/diagram/manifest/${encodeURIComponent(namespace)}/${encodeURIComponent(kind)}/${encodeURIComponent(name)}`;
    const response = await authFetch(url);
    if (response.status === 403) {
      const err = new Error('Forbidden');
      err.status = 403;
      try {
        const data = await response.json();
        if (data?.detail) err.message = data.detail;
      } catch {
        // ignore
      }
      throw err;
    }
    if (!response.ok) {
      const err = new Error(`HTTP error! status: ${response.status}`);
      err.status = response.status;
      throw err;
    }
    return response.json();
  },
};
