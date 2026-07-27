import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import NotificationSettings from '../NotificationSettings';
import { api } from '../../services/api';

jest.mock('../../services/api', () => ({
  api: {
    getNotificationSettings: jest.fn(),
    saveNotificationSetting: jest.fn(),
    testNotification: jest.fn(),
    deleteNotificationSetting: jest.fn(),
  },
}));

describe('NotificationSettings', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test('renders notification providers and expands to show mode selection', async () => {
    api.getNotificationSettings.mockResolvedValue([
      {
        id: 1,
        provider: 'slack',
        enabled: true,
        config: { mode: 'app', bot_token: 'xoxb-test', channel_id: 'C0123' },
      },
    ]);

    render(<NotificationSettings />);

    await waitFor(() => {
      expect(screen.getByText('Notification Settings')).toBeInTheDocument();
      expect(screen.getByText('Slack')).toBeInTheDocument();
      expect(screen.getByText('Microsoft Teams')).toBeInTheDocument();
    });

    // Click on Slack provider header to expand
    fireEvent.click(screen.getByText('Slack'));

    await waitFor(() => {
      expect(screen.getByText('Integration Mode')).toBeInTheDocument();
      expect(screen.getByText('Slack App (interactive ChatOps)')).toBeInTheDocument();
      expect(screen.getByText('Webhook (alerts only)')).toBeInTheDocument();
    });
  });

  test('switching modes updates visible fields', async () => {
    api.getNotificationSettings.mockResolvedValue([]);

    render(<NotificationSettings />);

    await waitFor(() => {
      expect(screen.getByText('Slack')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Slack'));

    await waitFor(() => {
      expect(screen.getByText('Webhook URL')).toBeInTheDocument();
    });

    // Switch to Slack App mode
    fireEvent.click(screen.getByText('Slack App (interactive ChatOps)'));

    await waitFor(() => {
      expect(screen.getByText('Bot User OAuth Token')).toBeInTheDocument();
      expect(screen.getByText('Signing Secret')).toBeInTheDocument();
      expect(screen.getByText('Channel ID')).toBeInTheDocument();
    });
  });
});
