const API_BASE = process.env.REACT_APP_API_URL || 
  (window.location.hostname === 'localhost' && window.location.port === '3000' ? 
    'http://localhost:8000' : '');

export const api = {
  getFailedPods: async () => {
    const response = await fetch(`${API_BASE}/api/pods/failed`);
    if (!response.ok) throw new Error('Failed to fetch');
    return response.json();
  },

  getClusterInfo: async () => {
    const response = await fetch(`${API_BASE}/api/cluster/info`);
    if (!response.ok) throw new Error('Failed to fetch cluster info');
    return response.json();
  }
};
