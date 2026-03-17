import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import MirrorPodModal from '../MirrorPodModal';
import { api } from '../../services/api';

// Mock lucide-react icons
jest.mock('lucide-react', () => ({
  X: ({ className }) => <span data-testid="x-icon" className={className}>X</span>,
  RefreshCw: ({ className }) => <span data-testid="refresh-icon" className={className}>RefreshCw</span>,
  CheckCircle: ({ className }) => <span data-testid="check-circle-icon" className={className}>CheckCircle</span>,
  XCircle: ({ className }) => <span data-testid="x-circle-icon" className={className}>XCircle</span>,
  Clock: ({ className }) => <span data-testid="clock-icon" className={className}>Clock</span>,
  Trash2: ({ className }) => <span data-testid="trash-icon" className={className}>Trash2</span>,
  AlertCircle: ({ className }) => <span data-testid="alert-circle-icon" className={className}>AlertCircle</span>,
  FlaskConical: ({ className }) => <span data-testid="flask-icon" className={className}>FlaskConical</span>,
}));

jest.mock('../../services/api', () => ({
  api: {
    deployMirrorPod: jest.fn(),
    getMirrorStatus: jest.fn(),
    deleteMirrorPod: jest.fn(),
  }
}));

const mockPod = {
  id: 1,
  pod_name: 'test-pod',
  namespace: 'default',
  failure_reason: 'ImagePullBackOff',
  failure_message: 'Failed to pull image',
  solution: 'Fix the container configuration',
  timestamp: '2025-01-01T00:00:00Z',
};

describe('MirrorPodModal', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test('does not render when isOpen is false', () => {
    render(<MirrorPodModal isOpen={false} onClose={jest.fn()} pod={mockPod} />);
    expect(screen.queryByText('Test Fix')).not.toBeInTheDocument();
  });

  test('renders confirm stage when opened', () => {
    render(<MirrorPodModal isOpen={true} onClose={jest.fn()} pod={mockPod} />);

    expect(screen.getByText('Test Fix')).toBeInTheDocument();
    expect(screen.getByText(/Deploy a temporary mirror pod/)).toBeInTheDocument();
    expect(screen.getByText('test-pod')).toBeInTheDocument();
    expect(screen.getByText('Deploy')).toBeInTheDocument();
    expect(screen.getByText('Cancel')).toBeInTheDocument();
  });

  test('shows default TTL in confirm message', () => {
    render(<MirrorPodModal isOpen={true} onClose={jest.fn()} pod={mockPod} defaultTTL={180} />);

    expect(screen.getByText(/180 seconds/)).toBeInTheDocument();
  });

  test('shows custom TTL in confirm message', () => {
    render(<MirrorPodModal isOpen={true} onClose={jest.fn()} pod={mockPod} defaultTTL={300} />);

    expect(screen.getByText(/300 seconds/)).toBeInTheDocument();
  });

  test('calls onClose when Cancel is clicked', () => {
    const onClose = jest.fn();
    render(<MirrorPodModal isOpen={true} onClose={onClose} pod={mockPod} />);

    fireEvent.click(screen.getByText('Cancel'));
    expect(onClose).toHaveBeenCalled();
  });

  test('calls onClose when overlay is clicked', () => {
    const onClose = jest.fn();
    render(<MirrorPodModal isOpen={true} onClose={onClose} pod={mockPod} />);

    const overlay = document.querySelector('.fixed.inset-0.bg-gray-500');
    fireEvent.click(overlay);
    expect(onClose).toHaveBeenCalled();
  });

  test('calls onClose when X button is clicked', () => {
    const onClose = jest.fn();
    render(<MirrorPodModal isOpen={true} onClose={onClose} pod={mockPod} />);

    const xButton = screen.getByTestId('x-icon').closest('button');
    fireEvent.click(xButton);
    expect(onClose).toHaveBeenCalled();
  });

  test('transitions to deploying state on Deploy click', async () => {
    api.deployMirrorPod.mockImplementation(() => new Promise(() => {})); // never resolves

    render(<MirrorPodModal isOpen={true} onClose={jest.fn()} pod={mockPod} />);

    await act(async () => {
      fireEvent.click(screen.getByText('Deploy'));
    });

    expect(screen.getByText('Creating mirror pod...')).toBeInTheDocument();
    expect(api.deployMirrorPod).toHaveBeenCalledWith(1, 180);
  });

  test('transitions to running state after successful deploy', async () => {
    api.deployMirrorPod.mockResolvedValue({
      mirror_id: 'mirror-123',
      mirror_pod_name: 'mirror-test-pod',
      namespace: 'default',
      status: 'created',
      ttl_seconds: 180,
      created_at: new Date().toISOString(),
    });
    api.getMirrorStatus.mockResolvedValue({
      mirror_id: 'mirror-123',
      mirror_pod_name: 'mirror-test-pod',
      namespace: 'default',
      phase: 'Pending',
      conditions: [],
      events: [],
      created_at: new Date().toISOString(),
      expires_at: new Date(Date.now() + 180000).toISOString(),
    });

    render(<MirrorPodModal isOpen={true} onClose={jest.fn()} pod={mockPod} />);

    await act(async () => {
      fireEvent.click(screen.getByText('Deploy'));
    });

    await waitFor(() => {
      expect(screen.getByText('mirror-test-pod')).toBeInTheDocument();
    });

    expect(screen.getByText('Delete Now')).toBeInTheDocument();
  });

  test('shows success result when mirror pod reaches Running phase', async () => {
    api.deployMirrorPod.mockResolvedValue({
      mirror_id: 'mirror-123',
      mirror_pod_name: 'mirror-test-pod',
      namespace: 'default',
      status: 'created',
      ttl_seconds: 180,
      created_at: new Date().toISOString(),
    });
    api.getMirrorStatus.mockResolvedValue({
      mirror_id: 'mirror-123',
      mirror_pod_name: 'mirror-test-pod',
      namespace: 'default',
      phase: 'Running',
      conditions: [],
      events: [],
      created_at: new Date().toISOString(),
      expires_at: new Date(Date.now() + 180000).toISOString(),
    });

    render(<MirrorPodModal isOpen={true} onClose={jest.fn()} pod={mockPod} />);

    await act(async () => {
      fireEvent.click(screen.getByText('Deploy'));
    });

    await waitFor(() => {
      expect(screen.getByText('Fix appears to be working!')).toBeInTheDocument();
    });
  });

  test('shows failure result when mirror pod fails', async () => {
    api.deployMirrorPod.mockResolvedValue({
      mirror_id: 'mirror-123',
      mirror_pod_name: 'mirror-test-pod',
      namespace: 'default',
      status: 'created',
      ttl_seconds: 180,
      created_at: new Date().toISOString(),
    });
    api.getMirrorStatus.mockResolvedValue({
      mirror_id: 'mirror-123',
      mirror_pod_name: 'mirror-test-pod',
      namespace: 'default',
      phase: 'Failed',
      conditions: [],
      events: [],
      created_at: new Date().toISOString(),
      expires_at: new Date(Date.now() + 180000).toISOString(),
    });

    render(<MirrorPodModal isOpen={true} onClose={jest.fn()} pod={mockPod} />);

    await act(async () => {
      fireEvent.click(screen.getByText('Deploy'));
    });

    await waitFor(() => {
      expect(screen.getByText("The fix didn't resolve the issue")).toBeInTheDocument();
    });
  });

  test('shows error state when deploy API fails', async () => {
    api.deployMirrorPod.mockRejectedValue(new Error('Server error'));

    render(<MirrorPodModal isOpen={true} onClose={jest.fn()} pod={mockPod} />);

    await act(async () => {
      fireEvent.click(screen.getByText('Deploy'));
    });

    await waitFor(() => {
      expect(screen.getByText('Server error')).toBeInTheDocument();
    });
  });

  test('handles Delete Now action', async () => {
    api.deployMirrorPod.mockResolvedValue({
      mirror_id: 'mirror-123',
      mirror_pod_name: 'mirror-test-pod',
      namespace: 'default',
      status: 'created',
      ttl_seconds: 180,
      created_at: new Date().toISOString(),
    });
    api.getMirrorStatus.mockResolvedValue({
      mirror_id: 'mirror-123',
      mirror_pod_name: 'mirror-test-pod',
      namespace: 'default',
      phase: 'Running',
      conditions: [],
      events: [],
      created_at: new Date().toISOString(),
      expires_at: new Date(Date.now() + 180000).toISOString(),
    });
    api.deleteMirrorPod.mockResolvedValue({ message: 'Mirror pod deleted' });

    render(<MirrorPodModal isOpen={true} onClose={jest.fn()} pod={mockPod} />);

    await act(async () => {
      fireEvent.click(screen.getByText('Deploy'));
    });

    await waitFor(() => {
      expect(screen.getByText('Delete Now')).toBeInTheDocument();
    });

    await act(async () => {
      fireEvent.click(screen.getByText('Delete Now'));
    });

    await waitFor(() => {
      expect(screen.getByText('Mirror pod was cleaned up.')).toBeInTheDocument();
    });

    expect(api.deleteMirrorPod).toHaveBeenCalledWith('mirror-123');
  });

  test('displays events in running state', async () => {
    api.deployMirrorPod.mockResolvedValue({
      mirror_id: 'mirror-123',
      mirror_pod_name: 'mirror-test-pod',
      namespace: 'default',
      status: 'created',
      ttl_seconds: 180,
      created_at: new Date().toISOString(),
    });
    api.getMirrorStatus.mockResolvedValue({
      mirror_id: 'mirror-123',
      mirror_pod_name: 'mirror-test-pod',
      namespace: 'default',
      phase: 'Pending',
      conditions: [],
      events: [
        { type: 'Normal', reason: 'Scheduled', message: 'Successfully assigned default/mirror-test-pod' },
        { type: 'Warning', reason: 'FailedMount', message: 'MountVolume.SetUp failed' },
      ],
      created_at: new Date().toISOString(),
      expires_at: new Date(Date.now() + 180000).toISOString(),
    });

    render(<MirrorPodModal isOpen={true} onClose={jest.fn()} pod={mockPod} />);

    await act(async () => {
      fireEvent.click(screen.getByText('Deploy'));
    });

    await waitFor(() => {
      expect(screen.getByText('Events')).toBeInTheDocument();
      expect(screen.getByText('Successfully assigned default/mirror-test-pod')).toBeInTheDocument();
      expect(screen.getByText('MountVolume.SetUp failed')).toBeInTheDocument();
    });
  });

  test('resets state when modal reopens', () => {
    const { rerender } = render(<MirrorPodModal isOpen={false} onClose={jest.fn()} pod={mockPod} />);

    // Open modal
    rerender(<MirrorPodModal isOpen={true} onClose={jest.fn()} pod={mockPod} />);
    expect(screen.getByText('Deploy')).toBeInTheDocument();

    // Close and reopen
    rerender(<MirrorPodModal isOpen={false} onClose={jest.fn()} pod={mockPod} />);
    rerender(<MirrorPodModal isOpen={true} onClose={jest.fn()} pod={mockPod} />);
    expect(screen.getByText('Deploy')).toBeInTheDocument();
  });

  test('shows namespace in confirm message', () => {
    render(<MirrorPodModal isOpen={true} onClose={jest.fn()} pod={mockPod} />);

    expect(screen.getByText('default')).toBeInTheDocument();
  });
});
