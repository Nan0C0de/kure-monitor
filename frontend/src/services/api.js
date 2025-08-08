const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';

export const api = {
  getFailedPods: async () => {
    const response = await fetch(`${API_BASE}/api/pods/failed`);
    if (!response.ok) throw new Error('Failed to fetch');
    return response.json();
  },

  getIgnoredPods: async () => {
    const response = await fetch(`${API_BASE}/api/pods/ignored`);
    if (!response.ok) throw new Error('Failed to fetch ignored pods');
    return response.json();
  },

  dismissPod: async (id) => {
    const response = await fetch(`${API_BASE}/api/pods/failed/${id}`, {
      method: 'DELETE'
    });
    if (!response.ok) throw new Error('Failed to dismiss');
    return response.json();
  },

  restorePod: async (id) => {
    const response = await fetch(`${API_BASE}/api/pods/ignored/${id}/restore`, {
      method: 'PUT'
    });
    if (!response.ok) throw new Error('Failed to restore pod');
    return response.json();
  }
};
