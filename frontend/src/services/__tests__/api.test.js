import { api } from '../api';

// Mock fetch globally
global.fetch = jest.fn();

describe('API Service', () => {
  beforeEach(() => {
    fetch.mockClear();
  });

  describe('getFailedPods', () => {
    test('fetches failed pods successfully', async () => {
      const mockPods = [
        { id: 1, pod_name: 'test-pod', failure_reason: 'ImagePullBackOff' }
      ];

      fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockPods,
      });

      const result = await api.getFailedPods();

      expect(fetch).toHaveBeenCalledWith('/api/pods/failed');
      expect(result).toEqual(mockPods);
    });

    test('throws error when fetch fails', async () => {
      fetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
      });

      await expect(api.getFailedPods()).rejects.toThrow('HTTP error! status: 500');
    });

    test('throws error when network fails', async () => {
      fetch.mockRejectedValueOnce(new Error('Network error'));

      await expect(api.getFailedPods()).rejects.toThrow('Network error');
    });
  });

  describe('dismissPod', () => {
    test('dismisses pod successfully', async () => {
      fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true }),
      });

      const result = await api.dismissPod(1);

      expect(fetch).toHaveBeenCalledWith('/api/pods/failed/1', {
        method: 'DELETE',
      });
      expect(result).toEqual({ success: true });
    });

    test('throws error when dismiss fails', async () => {
      fetch.mockResolvedValueOnce({
        ok: false,
        status: 404,
      });

      await expect(api.dismissPod(999)).rejects.toThrow('HTTP error! status: 404');
    });
  });

  describe('retrySolution', () => {
    test('retries solution successfully', async () => {
      const mockPod = { id: 1, solution: 'New AI solution' };
      fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockPod,
      });

      const result = await api.retrySolution(1);

      expect(fetch).toHaveBeenCalledWith('/api/pods/failed/1/retry-solution', {
        method: 'POST',
      });
      expect(result).toEqual(mockPod);
    });

    test('throws error when retry fails', async () => {
      fetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
      });

      await expect(api.retrySolution(1)).rejects.toThrow('HTTP error! status: 500');
    });
  });

  describe('getSecurityFindings', () => {
    test('fetches security findings successfully', async () => {
      const mockFindings = [{ id: 1, title: 'Privileged container' }];
      fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockFindings,
      });

      const result = await api.getSecurityFindings();

      expect(fetch).toHaveBeenCalledWith('/api/security/findings');
      expect(result).toEqual(mockFindings);
    });
  });

  describe('dismissSecurityFinding', () => {
    test('dismisses security finding successfully', async () => {
      fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true }),
      });

      const result = await api.dismissSecurityFinding(1);

      expect(fetch).toHaveBeenCalledWith('/api/security/findings/1', {
        method: 'DELETE',
      });
      expect(result).toEqual({ success: true });
    });
  });

  describe('getExcludedNamespaces', () => {
    test('fetches excluded namespaces successfully', async () => {
      const mockNamespaces = ['kube-system', 'kube-public'];
      fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockNamespaces,
      });

      const result = await api.getExcludedNamespaces();

      expect(fetch).toHaveBeenCalledWith('/api/admin/excluded-namespaces');
      expect(result).toEqual(mockNamespaces);
    });
  });

  describe('getAllNamespaces', () => {
    test('fetches all namespaces successfully', async () => {
      const mockNamespaces = ['default', 'kube-system', 'production'];
      fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockNamespaces,
      });

      const result = await api.getAllNamespaces();

      expect(fetch).toHaveBeenCalledWith('/api/admin/namespaces');
      expect(result).toEqual(mockNamespaces);
    });
  });

  describe('addExcludedNamespace', () => {
    test('adds excluded namespace successfully', async () => {
      fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true }),
      });

      const result = await api.addExcludedNamespace('test-ns');

      expect(fetch).toHaveBeenCalledWith('/api/admin/excluded-namespaces', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ namespace: 'test-ns' }),
      });
      expect(result).toEqual({ success: true });
    });
  });

  describe('removeExcludedNamespace', () => {
    test('removes excluded namespace successfully', async () => {
      fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true }),
      });

      const result = await api.removeExcludedNamespace('test-ns');

      expect(fetch).toHaveBeenCalledWith('/api/admin/excluded-namespaces/test-ns', {
        method: 'DELETE',
      });
      expect(result).toEqual({ success: true });
    });
  });

  describe('getExcludedPods', () => {
    test('fetches excluded pods successfully', async () => {
      const mockPods = ['test-pod-1', 'test-pod-2'];
      fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockPods,
      });

      const result = await api.getExcludedPods();

      expect(fetch).toHaveBeenCalledWith('/api/admin/excluded-pods');
      expect(result).toEqual(mockPods);
    });
  });

  describe('getMonitoredPods', () => {
    test('fetches monitored pods successfully', async () => {
      const mockPods = [{ name: 'pod-1', namespace: 'default' }];
      fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockPods,
      });

      const result = await api.getMonitoredPods();

      expect(fetch).toHaveBeenCalledWith('/api/admin/monitored-pods');
      expect(result).toEqual(mockPods);
    });
  });

  describe('addExcludedPod', () => {
    test('adds excluded pod successfully', async () => {
      fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true }),
      });

      const result = await api.addExcludedPod('test-pod');

      expect(fetch).toHaveBeenCalledWith('/api/admin/excluded-pods', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pod_name: 'test-pod' }),
      });
      expect(result).toEqual({ success: true });
    });
  });

  describe('removeExcludedPod', () => {
    test('removes excluded pod successfully', async () => {
      fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true }),
      });

      const result = await api.removeExcludedPod('test-pod');

      expect(fetch).toHaveBeenCalledWith('/api/admin/excluded-pods/test-pod', {
        method: 'DELETE',
      });
      expect(result).toEqual({ success: true });
    });
  });

  describe('Notification Settings', () => {
    test('getNotificationSettings fetches settings', async () => {
      const mockSettings = [{ provider: 'slack', enabled: true }];
      fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockSettings,
      });

      const result = await api.getNotificationSettings();

      expect(fetch).toHaveBeenCalledWith('/api/admin/notifications');
      expect(result).toEqual(mockSettings);
    });

    test('saveNotificationSetting saves new setting', async () => {
      const setting = { provider: 'slack', config: { webhook_url: 'https://hooks.slack.com/test' } };
      fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true }),
      });

      const result = await api.saveNotificationSetting(setting);

      expect(fetch).toHaveBeenCalledWith('/api/admin/notifications', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(setting),
      });
      expect(result).toEqual({ success: true });
    });

    test('updateNotificationSetting updates existing setting', async () => {
      const setting = { enabled: false };
      fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true }),
      });

      const result = await api.updateNotificationSetting('slack', setting);

      expect(fetch).toHaveBeenCalledWith('/api/admin/notifications/slack', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(setting),
      });
      expect(result).toEqual({ success: true });
    });

    test('deleteNotificationSetting deletes setting', async () => {
      fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true }),
      });

      const result = await api.deleteNotificationSetting('slack');

      expect(fetch).toHaveBeenCalledWith('/api/admin/notifications/slack', {
        method: 'DELETE',
      });
      expect(result).toEqual({ success: true });
    });

    test('testNotification sends test notification', async () => {
      fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true }),
      });

      const result = await api.testNotification('slack');

      expect(fetch).toHaveBeenCalledWith('/api/admin/notifications/slack/test', {
        method: 'POST',
      });
      expect(result).toEqual({ success: true });
    });
  });

  describe('getClusterMetrics', () => {
    test('fetches cluster metrics successfully', async () => {
      const mockMetrics = { nodes: 3, pods: 10, cpu_usage: 50 };
      fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockMetrics,
      });

      const result = await api.getClusterMetrics();

      expect(fetch).toHaveBeenCalledWith('/api/metrics/cluster');
      expect(result).toEqual(mockMetrics);
    });
  });

  describe('getPodLogs', () => {
    test('fetches pod logs without options', async () => {
      const mockLogs = { logs: 'Log line 1\nLog line 2' };
      fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockLogs,
      });

      const result = await api.getPodLogs('default', 'test-pod');

      expect(fetch).toHaveBeenCalledWith('/api/pods/default/test-pod/logs?');
      expect(result).toEqual(mockLogs);
    });

    test('fetches pod logs with all options', async () => {
      const mockLogs = { logs: 'Log line 1' };
      fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockLogs,
      });

      const result = await api.getPodLogs('default', 'test-pod', {
        container: 'nginx',
        tailLines: 100,
        previous: true,
      });

      expect(fetch).toHaveBeenCalledWith(
        '/api/pods/default/test-pod/logs?container=nginx&tail_lines=100&previous=true'
      );
      expect(result).toEqual(mockLogs);
    });
  });

  describe('getStreamingLogsUrl', () => {
    test('returns streaming URL without options', () => {
      const url = api.getStreamingLogsUrl('default', 'test-pod');
      expect(url).toBe('/api/pods/default/test-pod/logs/stream?');
    });

    test('returns streaming URL with options', () => {
      const url = api.getStreamingLogsUrl('default', 'test-pod', {
        container: 'nginx',
        tailLines: 50,
      });
      expect(url).toBe('/api/pods/default/test-pod/logs/stream?container=nginx&tail_lines=50');
    });
  });
});
