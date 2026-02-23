import { render, screen, fireEvent } from '@testing-library/react';
import ManifestModal from '../ManifestModal';

// Mock lucide-react
jest.mock('lucide-react', () => ({
  X: () => <span data-testid="close-icon">X</span>,
  Copy: () => <span data-testid="copy-icon">Copy</span>,
  Download: () => <span data-testid="download-icon">Download</span>,
  RefreshCw: ({ className }) => <span data-testid="refresh-icon" className={className}>RefreshCw</span>,
  Sparkles: () => <span data-testid="sparkles-icon">Sparkles</span>,
}));

// Mock clipboard API
Object.assign(navigator, {
  clipboard: {
    writeText: jest.fn().mockResolvedValue(),
  },
});

// Mock URL API
global.URL.createObjectURL = jest.fn(() => 'blob:test-url');
global.URL.revokeObjectURL = jest.fn();

const defaultProps = {
  isOpen: true,
  onClose: jest.fn(),
  podName: 'test-pod',
  namespace: 'default',
  manifest: `apiVersion: v1
kind: Pod
metadata:
  name: test-pod
  namespace: default
spec:
  containers:
  - name: nginx
    image: nginx:latest
    resources:
      limits:
        memory: "128Mi"
        cpu: "500m"`,
  solution: 'Add resources limits to the container',
  onRetrySolution: jest.fn(),
  isRetrying: false,
};

describe('ManifestModal', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test('renders nothing when isOpen is false', () => {
    render(<ManifestModal {...defaultProps} isOpen={false} />);

    expect(screen.queryByText('Pod Manifest')).not.toBeInTheDocument();
  });

  test('renders modal when isOpen is true', () => {
    render(<ManifestModal {...defaultProps} />);

    expect(screen.getByText('Pod Manifest')).toBeInTheDocument();
    expect(screen.getByText('default/test-pod')).toBeInTheDocument();
  });

  test('displays manifest content', () => {
    render(<ManifestModal {...defaultProps} />);

    // Use getAllByText since content appears in both visible display and hidden textarea
    expect(screen.getAllByText(/apiVersion: v1/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/kind: Pod/).length).toBeGreaterThan(0);
  });

  test('shows Copy button', () => {
    render(<ManifestModal {...defaultProps} />);

    expect(screen.getByRole('button', { name: /copy/i })).toBeInTheDocument();
  });

  test('shows Download button', () => {
    render(<ManifestModal {...defaultProps} />);

    expect(screen.getByRole('button', { name: /download/i })).toBeInTheDocument();
  });

  test('calls onClose when Close button is clicked', () => {
    const onClose = jest.fn();
    render(<ManifestModal {...defaultProps} onClose={onClose} />);

    fireEvent.click(screen.getByText('Close'));
    expect(onClose).toHaveBeenCalled();
  });

  test('calls onClose when overlay is clicked', () => {
    const onClose = jest.fn();
    render(<ManifestModal {...defaultProps} onClose={onClose} />);

    // Click the overlay (the background)
    const overlay = document.querySelector('.fixed.inset-0.bg-gray-500');
    fireEvent.click(overlay);
    expect(onClose).toHaveBeenCalled();
  });

  test('copies manifest to clipboard', async () => {
    render(<ManifestModal {...defaultProps} />);

    // Use button role to find the Copy button
    const copyButton = screen.getByRole('button', { name: /copy/i });
    fireEvent.click(copyButton);

    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(defaultProps.manifest);
  });

  test('highlights relevant lines based on AI solution', () => {
    render(<ManifestModal {...defaultProps} />);

    // The solution mentions "resources" which should highlight the resources section
    expect(screen.getByTestId('sparkles-icon')).toBeInTheDocument();
  });

  test('shows Retry AI button when solution is a fallback', () => {
    const propsWithFallback = {
      ...defaultProps,
      solution: 'AI solution temporarily unavailable. Basic troubleshooting steps...',
    };

    render(<ManifestModal {...propsWithFallback} />);

    expect(screen.getByText('Retry AI')).toBeInTheDocument();
  });

  test('does not show Retry AI button for regular solutions', () => {
    render(<ManifestModal {...defaultProps} />);

    // Should not show Retry AI button for non-fallback solutions
    expect(screen.queryByText('Retry AI')).not.toBeInTheDocument();
  });

  test('shows "No manifest available" when manifest is empty', () => {
    render(<ManifestModal {...defaultProps} manifest="" />);

    expect(screen.getByText('# No manifest available')).toBeInTheDocument();
  });

  test('displays line numbers', () => {
    render(<ManifestModal {...defaultProps} />);

    // Check that line numbers are displayed
    expect(screen.getByText('1')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
  });

  test('handles Retry AI button click', async () => {
    const onRetrySolution = jest.fn().mockResolvedValue();
    const propsWithFallback = {
      ...defaultProps,
      solution: 'AI solution temporarily unavailable. Basic troubleshooting steps...',
      onRetrySolution,
      aiEnabled: true,
    };

    render(<ManifestModal {...propsWithFallback} />);

    fireEvent.click(screen.getByText('Retry AI'));

    expect(onRetrySolution).toHaveBeenCalled();
  });

  test('shows retrying state', () => {
    const propsWithFallback = {
      ...defaultProps,
      solution: 'AI solution temporarily unavailable. Basic troubleshooting steps...',
      isRetrying: true,
    };

    render(<ManifestModal {...propsWithFallback} />);

    expect(screen.getByText('Retrying AI...')).toBeInTheDocument();
  });
});
