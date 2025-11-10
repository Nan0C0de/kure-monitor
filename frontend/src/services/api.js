// Fixed API URL for security - users cannot modify this
const API_BASE = window.location.hostname === 'localhost' && window.location.port === '3000' 
  ? 'http://localhost:8000'  // Development mode
  : '';  // Production mode (same origin)

export const api = {
  getFailedPods: async () => {
    const response = await fetch(`${API_BASE}/api/pods/failed`);
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  dismissPod: async (podId) => {
    const response = await fetch(`${API_BASE}/api/pods/failed/${podId}`, {
      method: 'DELETE'
    });
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  getClusterInfo: async () => {
    const response = await fetch(`${API_BASE}/api/cluster/info`);
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  // Security findings API
  getSecurityFindings: async () => {
    const response = await fetch(`${API_BASE}/api/security/findings`);
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  dismissSecurityFinding: async (findingId) => {
    const response = await fetch(`${API_BASE}/api/security/findings/${findingId}`, {
      method: 'DELETE'
    });
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  }
};
