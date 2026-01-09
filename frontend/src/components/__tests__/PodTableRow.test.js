import { render, screen, fireEvent } from '@testing-library/react';
import PodTableRow from '../PodTableRow';

// Mock child components that have complex dependencies
jest.mock('../PodDetails', () => {
  return function MockPodDetails({ pod }) {
    return (
      <div data-testid="pod-details">
        <h3>Error Details</h3>
        <p>{pod.solution}</p>
      </div>
    );
  };
});

jest.mock('../ManifestModal', () => {
  return function MockManifestModal() {
    return null;
  };
});

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
    expect(screen.getByText('AI Solution Available')).toBeInTheDocument();
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
    
    expect(screen.getByText('AI Solution Available')).toBeInTheDocument();
    expect(screen.getByText('Click to expand for detailed solution')).toBeInTheDocument();
  });
});