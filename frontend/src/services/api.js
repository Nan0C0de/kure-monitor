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
  },

  // CVE findings API
  getCVEFindings: async () => {
    const response = await fetch(`${API_BASE}/api/security/cves`);
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  getDismissedCVEFindings: async () => {
    const response = await fetch(`${API_BASE}/api/security/cves/dismissed`);
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  dismissCVEFinding: async (findingId) => {
    const response = await fetch(`${API_BASE}/api/security/cves/${findingId}`, {
      method: 'DELETE'
    });
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  restoreCVEFinding: async (findingId) => {
    const response = await fetch(`${API_BASE}/api/security/cves/${findingId}/restore`, {
      method: 'PUT'
    });
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  acknowledgeCVEFinding: async (findingId) => {
    const response = await fetch(`${API_BASE}/api/security/cves/${findingId}/acknowledge`, {
      method: 'PUT'
    });
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  }
};
