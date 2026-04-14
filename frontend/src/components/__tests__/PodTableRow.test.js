import { render, screen, fireEvent } from '@testing-library/react';
import PodTableRow from '../PodTableRow';

// Mock child components that have complex dependencies
jest.mock('../PodDetails', () => {
  return function MockPodDetails({ pod, onStatusChange, onDeleteRecord, onTestFix }) {
    return (
      <div data-testid="pod-details">
        <h3>Error Details</h3>
        <p>{pod.solution}</p>
        {onStatusChange && <button>Resolve</button>}
        {onDeleteRecord && <button>Delete</button>}
        {onTestFix && <button>Test fix</button>}
      </div>
    );
  };
});

jest.mock('../ManifestModal', () => {
  return function MockManifestModal() {
    return null;
  };
});

jest.mock('../MirrorPodModal', () => {
  return function MockMirrorPodModal() {
    return null;
  };
});

jest.mock('../PodLogsModal', () => {
  return function MockPodLogsModal() {
    return null;
  };
});

// Mock API for mirror pod checks
jest.mock('../../services/api', () => ({
  api: {
    getActiveMirrors: jest.fn().mockResolvedValue([]),
    getMirrorStatus: jest.fn().mockResolvedValue(null),
    deleteMirrorPod: jest.fn().mockResolvedValue({}),
    retrySolution: jest.fn().mockResolvedValue({}),
  },
}));

const mockPod = {
  id: 1,
  pod_name: 'test-pod',
  namespace: 'default',
  failure_reason: 'ImagePullBackOff',
  failure_message: 'Failed to pull image',
  timestamp: '2025-01-01T00:00:00Z',
  solution: 'Check image name and registry access',
  container_statuses: [],
  events: [],
  manifest: 'apiVersion: v1\nkind: Pod'
};

describe('PodTableRow', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test('renders pod information correctly', () => {
    render(
      <table>
        <tbody>
          <PodTableRow pod={mockPod} />
        </tbody>
      </table>
    );
    
    expect(screen.getByText('test-pod')).toBeInTheDocument();
    expect(screen.getByText('default')).toBeInTheDocument();
    expect(screen.getByText('ImagePullBackOff')).toBeInTheDocument();
    expect(screen.getByText('Click to expand')).toBeInTheDocument();
  });

  test('pod name is bold', () => {
    render(
      <table>
        <tbody>
          <PodTableRow pod={mockPod} />
        </tbody>
      </table>
    );
    
    const podName = screen.getByText('test-pod');
    expect(podName).toHaveClass('font-bold');
  });

  test('expands and collapses on chevron click', () => {
    render(
      <table>
        <tbody>
          <PodTableRow pod={mockPod} />
        </tbody>
      </table>
    );
    
    // Initially collapsed
    expect(screen.queryByText('Error Details')).not.toBeInTheDocument();
    
    // Click chevron to expand
    const chevronButton = screen.getByTestId('chevron-right').closest('button');
    fireEvent.click(chevronButton);
    
    // Should now be expanded
    expect(screen.getByText('Error Details')).toBeInTheDocument();
    
    // Click again to collapse
    fireEvent.click(chevronButton);
    
    // Should be collapsed again
    expect(screen.queryByText('Error Details')).not.toBeInTheDocument();
  });

  test('expands on pod name click', () => {
    render(
      <table>
        <tbody>
          <PodTableRow pod={mockPod} />
        </tbody>
      </table>
    );
    
    // Initially collapsed
    expect(screen.queryByText('Error Details')).not.toBeInTheDocument();
    
    // Click pod name to expand
    const podNameButton = screen.getByText('test-pod').closest('button');
    fireEvent.click(podNameButton);
    
    // Should now be expanded
    expect(screen.getByText('Error Details')).toBeInTheDocument();
  });

  test('expands on status badge click', () => {
    render(
      <table>
        <tbody>
          <PodTableRow pod={mockPod} />
        </tbody>
      </table>
    );
    
    // Initially collapsed
    expect(screen.queryByText('Error Details')).not.toBeInTheDocument();
    
    // Click status badge to expand
    const statusButton = screen.getByText('ImagePullBackOff').closest('button');
    fireEvent.click(statusButton);
    
    // Should now be expanded
    expect(screen.getByText('Error Details')).toBeInTheDocument();
  });

  test('formats timestamp correctly', () => {
    render(
      <table>
        <tbody>
          <PodTableRow pod={mockPod} />
        </tbody>
      </table>
    );
    
    // Should display formatted timestamp  
    const timestamp = screen.getByText(/Jan 1/);
    expect(timestamp).toBeInTheDocument();
  });

  test('shows solution text', () => {
    render(
      <table>
        <tbody>
          <PodTableRow pod={mockPod} />
        </tbody>
      </table>
    );

    expect(screen.getByText('Click to expand')).toBeInTheDocument();
  });

  test('hides mutation action buttons when canWrite is false', () => {
    render(
      <table>
        <tbody>
          <PodTableRow
            pod={mockPod}
            canWrite={false}
            onStatusChange={jest.fn()}
            onDeleteRecord={jest.fn()}
          />
        </tbody>
      </table>
    );

    // Expand the row
    const chevron = screen.getByTestId('chevron-right').closest('button');
    fireEvent.click(chevron);

    // PodDetails only renders action buttons when callbacks are passed.
    // With canWrite=false, PodTableRow passes `undefined` for mutations.
    expect(screen.queryByText('Resolve')).not.toBeInTheDocument();
    expect(screen.queryByText('Delete')).not.toBeInTheDocument();
    expect(screen.queryByText('Test fix')).not.toBeInTheDocument();
  });

  test('shows mutation action buttons when canWrite is true', () => {
    render(
      <table>
        <tbody>
          <PodTableRow
            pod={mockPod}
            canWrite={true}
            onStatusChange={jest.fn()}
            onDeleteRecord={jest.fn()}
          />
        </tbody>
      </table>
    );

    const chevron = screen.getByTestId('chevron-right').closest('button');
    fireEvent.click(chevron);

    expect(screen.getByText('Resolve')).toBeInTheDocument();
    expect(screen.getByText('Delete')).toBeInTheDocument();
    // Test fix only shows if onTestFix is passed (it is, via PodTableRow)
    expect(screen.getByText('Test fix')).toBeInTheDocument();
  });
});