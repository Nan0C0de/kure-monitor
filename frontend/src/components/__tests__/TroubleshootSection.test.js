import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import TroubleshootSection from '../TroubleshootSection';

// Mock react-markdown (used by SolutionMarkdown)
jest.mock('react-markdown', () => {
  return function MockReactMarkdown({ children }) {
    return <div data-testid="markdown-content">{children}</div>;
  };
});

// Mock lucide-react
jest.mock('lucide-react', () => ({
  Wand2: ({ className }) => <span data-testid="wand-icon" className={className}>Wand2</span>,
  RefreshCw: ({ className }) => <span data-testid="refresh-icon" className={className}>RefreshCw</span>,
  Copy: () => <span data-testid="copy-icon">Copy</span>,
  Check: () => <span data-testid="check-icon">Check</span>,
}));

// Mock API
jest.mock('../../services/api', () => ({
  api: {
    generateLogAwareSolution: jest.fn(),
    regenerateLogAwareSolution: jest.fn(),
  },
}));

const eligiblePod = {
  id: 42,
  pod_name: 'crasher',
  namespace: 'default',
  failure_reason: 'CrashLoopBackOff',
  logs_captured: true,
  log_aware_solution: null,
  log_aware_solution_generated_at: null,
};

describe('TroubleshootSection', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test('renders nothing when logs_captured is false', () => {
    const pod = { ...eligiblePod, logs_captured: false };
    render(<TroubleshootSection pod={pod} aiEnabled={true} />);
    expect(screen.queryByText('Troubleshoot')).not.toBeInTheDocument();
    expect(screen.queryByText('Log-aware analysis')).not.toBeInTheDocument();
  });

  test('renders nothing when logs_captured is missing (old backend)', () => {
    const pod = { ...eligiblePod };
    delete pod.logs_captured;
    render(<TroubleshootSection pod={pod} aiEnabled={true} />);
    expect(screen.queryByText('Troubleshoot')).not.toBeInTheDocument();
    expect(screen.queryByText('Log-aware analysis')).not.toBeInTheDocument();
  });

  test('renders nothing when failure_reason is ImagePullBackOff', () => {
    const pod = { ...eligiblePod, failure_reason: 'ImagePullBackOff' };
    render(<TroubleshootSection pod={pod} aiEnabled={true} />);
    expect(screen.queryByText('Troubleshoot')).not.toBeInTheDocument();
    expect(screen.queryByText('Log-aware analysis')).not.toBeInTheDocument();
  });

  test('renders for OOMKilled', () => {
    const pod = { ...eligiblePod, failure_reason: 'OOMKilled' };
    render(<TroubleshootSection pod={pod} aiEnabled={true} />);
    expect(screen.getByText('Troubleshoot')).toBeInTheDocument();
  });

  test('renders nothing when aiEnabled is false', () => {
    render(<TroubleshootSection pod={eligiblePod} aiEnabled={false} />);
    expect(screen.queryByText('Troubleshoot')).not.toBeInTheDocument();
    expect(screen.queryByText('Log-aware analysis')).not.toBeInTheDocument();
  });

  test('shows Troubleshoot button and empty state message when eligible and no prior solution', () => {
    render(<TroubleshootSection pod={eligiblePod} aiEnabled={true} />);
    expect(screen.getByText('Troubleshoot')).toBeInTheDocument();
    expect(screen.getByText(/Get a deeper diagnosis/)).toBeInTheDocument();
    expect(screen.getByText('Log-aware analysis')).toBeInTheDocument();
  });

  test('click Troubleshoot calls api.generateLogAwareSolution, shows skeleton, then renders markdown', async () => {
    const { api } = require('../../services/api');
    let resolveCall;
    api.generateLogAwareSolution.mockImplementation(
      () => new Promise(resolve => { resolveCall = resolve; })
    );

    const onUpdated = jest.fn();
    render(
      <TroubleshootSection
        pod={eligiblePod}
        aiEnabled={true}
        onLogAwareSolutionUpdated={onUpdated}
      />
    );

    fireEvent.click(screen.getByText('Troubleshoot'));

    // Skeleton should appear while loading
    await waitFor(() => {
      expect(screen.getByTestId('troubleshoot-skeleton')).toBeInTheDocument();
    });
    expect(api.generateLogAwareSolution).toHaveBeenCalledWith(42);

    // Resolve the API promise
    resolveCall({
      solution: 'Log-aware diagnosis: OOM at startup',
      generated_at: '2026-04-13T12:00:00Z',
      cached: false,
      log_aware: true,
    });

    await waitFor(() => {
      expect(screen.getByTestId('markdown-content')).toHaveTextContent('Log-aware diagnosis: OOM at startup');
    });
    expect(onUpdated).toHaveBeenCalledWith(42, 'Log-aware diagnosis: OOM at startup', '2026-04-13T12:00:00Z');
    expect(screen.getByText('Regenerate')).toBeInTheDocument();
  });

  test('hydrates from pod.log_aware_solution without calling API', () => {
    const { api } = require('../../services/api');
    const pod = {
      ...eligiblePod,
      log_aware_solution: 'Previously generated diagnosis',
      log_aware_solution_generated_at: new Date().toISOString(),
    };

    render(<TroubleshootSection pod={pod} aiEnabled={true} />);

    expect(screen.getByTestId('markdown-content')).toHaveTextContent('Previously generated diagnosis');
    expect(screen.getByText('Regenerate')).toBeInTheDocument();
    expect(api.generateLogAwareSolution).not.toHaveBeenCalled();
    expect(screen.queryByText('Troubleshoot')).not.toBeInTheDocument();
  });

  test('click Regenerate calls api.regenerateLogAwareSolution', async () => {
    const { api } = require('../../services/api');
    api.regenerateLogAwareSolution.mockResolvedValue({
      solution: 'Fresh diagnosis',
      generated_at: '2026-04-13T13:00:00Z',
      cached: false,
      log_aware: true,
    });

    const pod = {
      ...eligiblePod,
      log_aware_solution: 'Old diagnosis',
      log_aware_solution_generated_at: '2026-04-13T10:00:00Z',
    };

    render(<TroubleshootSection pod={pod} aiEnabled={true} />);

    fireEvent.click(screen.getByText('Regenerate'));

    await waitFor(() => {
      expect(api.regenerateLogAwareSolution).toHaveBeenCalledWith(42);
    });

    await waitFor(() => {
      expect(screen.getByTestId('markdown-content')).toHaveTextContent('Fresh diagnosis');
    });
  });

  test('API failure renders muted retry text, no crash', async () => {
    const { api } = require('../../services/api');
    api.generateLogAwareSolution.mockRejectedValue(new Error('network down'));
    // Silence expected console.error
    const consoleErrSpy = jest.spyOn(console, 'error').mockImplementation(() => {});

    render(<TroubleshootSection pod={eligiblePod} aiEnabled={true} />);

    fireEvent.click(screen.getByText('Troubleshoot'));

    await waitFor(() => {
      expect(screen.getByText("Couldn't generate. Click to retry.")).toBeInTheDocument();
    });
    // The troubleshoot button is still visible for retry
    expect(screen.getByText('Troubleshoot')).toBeInTheDocument();

    consoleErrSpy.mockRestore();
  });

  test('renders dark-themed classes when isDark is true', () => {
    render(<TroubleshootSection pod={eligiblePod} aiEnabled={true} isDark={true} />);
    // The empty-state text lives inside the card, so walk up to find the card element.
    // eslint-disable-next-line testing-library/no-node-access
    const card = screen.getByText(/Get a deeper diagnosis/).closest('.rounded');
    expect(card).toHaveClass('bg-indigo-900/30');
    expect(card).toHaveClass('border-indigo-700');
  });

  test('renders light-themed classes when isDark is false', () => {
    render(<TroubleshootSection pod={eligiblePod} aiEnabled={true} isDark={false} />);
    // eslint-disable-next-line testing-library/no-node-access
    const card = screen.getByText(/Get a deeper diagnosis/).closest('.rounded');
    expect(card).toHaveClass('bg-indigo-50');
    expect(card).toHaveClass('border-indigo-200');
  });
});
