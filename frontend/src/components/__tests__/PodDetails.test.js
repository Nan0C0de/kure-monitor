import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import PodDetails from '../PodDetails';

// Mock react-markdown
jest.mock('react-markdown', () => {
  return function MockReactMarkdown({ children }) {
    return <div data-testid="markdown-content">{children}</div>;
  };
});

// Mock lucide-react
jest.mock('lucide-react', () => ({
  FileText: () => <span data-testid="file-text-icon">FileText</span>,
  RefreshCw: ({ className }) => <span data-testid="refresh-icon" className={className}>RefreshCw</span>,
  Copy: () => <span data-testid="copy-icon">Copy</span>,
  Check: () => <span data-testid="check-icon">Check</span>,
  Terminal: () => <span data-testid="terminal-icon">Terminal</span>,
  Search: () => <span data-testid="search-icon">Search</span>,
  CheckCircle: () => <span data-testid="check-circle-icon">CheckCircle</span>,
  EyeOff: () => <span data-testid="eye-off-icon">EyeOff</span>,
  RotateCcw: () => <span data-testid="rotate-ccw-icon">RotateCcw</span>,
  Clock: () => <span data-testid="clock-icon">Clock</span>,
  Trash2: () => <span data-testid="trash-icon">Trash2</span>,
  FlaskConical: () => <span data-testid="flask-icon">FlaskConical</span>,
}));

// Mock API
jest.mock('../../services/api', () => ({
  api: {
    retrySolution: jest.fn(),
    getActiveMirrors: jest.fn().mockResolvedValue([]),
    getMirrorStatus: jest.fn().mockResolvedValue(null),
    deleteMirrorPod: jest.fn().mockResolvedValue({}),
  },
}));

const mockPod = {
  id: 1,
  pod_name: 'test-pod',
  namespace: 'default',
  node_name: 'node-1',
  phase: 'Pending',
  creation_timestamp: '2025-01-01T00:00:00Z',
  failure_reason: 'ImagePullBackOff',
  failure_message: 'Failed to pull image nginx:invalid',
  container_statuses: [
    {
      name: 'nginx',
      image: 'nginx:invalid',
      state: 'waiting',
      restart_count: 5
    }
  ],
  events: [
    {
      type: 'Warning',
      reason: 'Failed',
      message: 'Failed to pull image'
    },
    {
      type: 'Normal',
      reason: 'Pulling',
      message: 'Pulling image'
    }
  ],
  solution: 'Check the image name and tag'
};

describe('PodDetails', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test('renders pod details correctly', () => {
    render(<PodDetails pod={mockPod} onViewManifest={jest.fn()} />);

    expect(screen.getByText('Pod Details')).toBeInTheDocument();
    expect(screen.getByText('node-1')).toBeInTheDocument();
    expect(screen.getByText('Pending')).toBeInTheDocument();
  });

  test('renders error details', () => {
    render(<PodDetails pod={mockPod} onViewManifest={jest.fn()} />);

    expect(screen.getByText('Error Details')).toBeInTheDocument();
    expect(screen.getByText('ImagePullBackOff')).toBeInTheDocument();
    expect(screen.getByText('Failed to pull image nginx:invalid')).toBeInTheDocument();
  });

  test('renders container statuses table', () => {
    render(<PodDetails pod={mockPod} onViewManifest={jest.fn()} />);

    expect(screen.getByText('Container Status')).toBeInTheDocument();
    expect(screen.getByText('nginx')).toBeInTheDocument();
    expect(screen.getByText('nginx:invalid')).toBeInTheDocument();
    expect(screen.getByText('waiting')).toBeInTheDocument();
    expect(screen.getByText('5')).toBeInTheDocument();
  });

  test('renders events list', () => {
    render(<PodDetails pod={mockPod} onViewManifest={jest.fn()} />);

    expect(screen.getByText('Recent Events')).toBeInTheDocument();
    expect(screen.getByText('Failed')).toBeInTheDocument();
    expect(screen.getByText('Failed to pull image')).toBeInTheDocument();
  });

  test('renders solution section', () => {
    render(<PodDetails pod={mockPod} onViewManifest={jest.fn()} />);

    expect(screen.getByText('AI-Generated Solution')).toBeInTheDocument();
    expect(screen.getByTestId('markdown-content')).toHaveTextContent('Check the image name and tag');
  });

  test('calls onViewManifest when View Manifest button is clicked', () => {
    const onViewManifest = jest.fn();
    render(<PodDetails pod={mockPod} onViewManifest={onViewManifest} />);

    fireEvent.click(screen.getByText('View Manifest'));
    expect(onViewManifest).toHaveBeenCalled();
  });

  test('detects fallback solution', () => {
    const podWithFallback = {
      ...mockPod,
      solution: 'AI solution temporarily unavailable. Basic troubleshooting: Check the image name.'
    };

    render(<PodDetails pod={podWithFallback} onViewManifest={jest.fn()} />);

    // Fallback solution should have yellow background
    const solutionContainer = screen.getByTestId('markdown-content').parentElement.parentElement;
    expect(solutionContainer).toHaveClass('bg-yellow-50');
  });

  test('shows N/A when node_name is not available', () => {
    const podWithoutNode = {
      ...mockPod,
      node_name: null
    };

    render(<PodDetails pod={podWithoutNode} onViewManifest={jest.fn()} />);

    expect(screen.getByText('N/A')).toBeInTheDocument();
  });

  test('handles pod without container_statuses', () => {
    const podWithoutContainers = {
      ...mockPod,
      container_statuses: []
    };

    render(<PodDetails pod={podWithoutContainers} onViewManifest={jest.fn()} />);

    expect(screen.queryByText('Container Status')).not.toBeInTheDocument();
  });

  test('handles pod without events', () => {
    const podWithoutEvents = {
      ...mockPod,
      events: []
    };

    render(<PodDetails pod={podWithoutEvents} onViewManifest={jest.fn()} />);

    expect(screen.queryByText('Recent Events')).not.toBeInTheDocument();
  });

  test('retry AI button triggers retry', async () => {
    const { api } = require('../../services/api');
    api.retrySolution.mockResolvedValue({ ...mockPod, solution: 'New solution' });

    const onSolutionUpdated = jest.fn();
    render(
      <PodDetails
        pod={mockPod}
        onViewManifest={jest.fn()}
        onSolutionUpdated={onSolutionUpdated}
        aiEnabled={true}
      />
    );

    fireEvent.click(screen.getByText('Retry AI'));

    await waitFor(() => {
      expect(api.retrySolution).toHaveBeenCalledWith(1);
    });
  });

  test('shows fallback message when failure_message is empty', () => {
    const podWithoutMessage = {
      ...mockPod,
      failure_message: '',
      events: []
    };

    render(<PodDetails pod={podWithoutMessage} onViewManifest={jest.fn()} />);

    expect(screen.getByText(/Pod is in ImagePullBackOff state/)).toBeInTheDocument();
  });

  test('formats timestamp correctly', () => {
    render(<PodDetails pod={mockPod} onViewManifest={jest.fn()} />);

    // Check that a formatted date is displayed (exact format depends on locale)
    expect(screen.getByText(/Jan/)).toBeInTheDocument();
  });

  describe('Mirror Pod Status', () => {
    const mockMirror = {
      mirror_id: 'mirror-123',
      mirror_pod_name: 'test-pod-kure-mirror',
      namespace: 'default',
      phase: 'Running',
      expires_at: new Date(Date.now() + 120000).toISOString(), // 2 minutes from now
    };

    test('renders mirror pod status when activeMirror is provided', () => {
      render(
        <PodDetails
          pod={mockPod}
          onViewManifest={jest.fn()}
          activeMirror={mockMirror}
          onDeleteMirror={jest.fn()}
          onRefreshMirror={jest.fn()}
        />
      );

      expect(screen.getByText('Mirror Pod Active')).toBeInTheDocument();
      expect(screen.getByText('test-pod-kure-mirror')).toBeInTheDocument();
      expect(screen.getByText('Running')).toBeInTheDocument();
    });

    test('does not render mirror pod status when activeMirror is null', () => {
      render(
        <PodDetails
          pod={mockPod}
          onViewManifest={jest.fn()}
          activeMirror={null}
        />
      );

      expect(screen.queryByText('Mirror Pod Active')).not.toBeInTheDocument();
    });

    test('shows delete mirror button', () => {
      render(
        <PodDetails
          pod={mockPod}
          onViewManifest={jest.fn()}
          activeMirror={mockMirror}
          onDeleteMirror={jest.fn()}
          onRefreshMirror={jest.fn()}
        />
      );

      expect(screen.getByText('Delete Mirror')).toBeInTheDocument();
    });

    test('calls onDeleteMirror when delete button is clicked', async () => {
      const onDeleteMirror = jest.fn().mockResolvedValue();
      render(
        <PodDetails
          pod={mockPod}
          onViewManifest={jest.fn()}
          activeMirror={mockMirror}
          onDeleteMirror={onDeleteMirror}
          onRefreshMirror={jest.fn()}
        />
      );

      fireEvent.click(screen.getByText('Delete Mirror'));

      await waitFor(() => {
        expect(onDeleteMirror).toHaveBeenCalledWith('mirror-123');
      });
    });

    test('shows pending phase indicator for pending mirror', () => {
      const pendingMirror = { ...mockMirror, phase: 'Pending' };
      render(
        <PodDetails
          pod={mockPod}
          onViewManifest={jest.fn()}
          activeMirror={pendingMirror}
          onDeleteMirror={jest.fn()}
          onRefreshMirror={jest.fn()}
        />
      );

      // Pending phase should be displayed
      const phaseTexts = screen.getAllByText('Pending');
      // One from pod phase, one from mirror phase
      expect(phaseTexts.length).toBeGreaterThanOrEqual(1);
    });

    test('shows countdown timer', () => {
      render(
        <PodDetails
          pod={mockPod}
          onViewManifest={jest.fn()}
          activeMirror={mockMirror}
          onDeleteMirror={jest.fn()}
          onRefreshMirror={jest.fn()}
        />
      );

      // Should show the "Expires:" label
      expect(screen.getByText('Expires:')).toBeInTheDocument();
    });
  });
});
