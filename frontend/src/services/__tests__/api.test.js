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

});