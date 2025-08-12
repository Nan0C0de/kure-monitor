import { render, screen } from '@testing-library/react';
import PodTable from '../PodTable';

const mockPods = [
  {
    id: 1,
    pod_name: 'test-pod-1',
    namespace: 'default',
    failure_reason: 'ImagePullBackOff',
    failure_message: 'Failed to pull image',
    timestamp: '2025-01-01T00:00:00Z'
  },
  {
    id: 2,
    pod_name: 'test-pod-2',
    namespace: 'kube-system',
    failure_reason: 'CrashLoopBackOff',
    failure_message: 'Container crashed',
    timestamp: '2025-01-01T01:00:00Z'
  }
];

describe('PodTable', () => {
  test('renders table headers', () => {
    render(<PodTable pods={[]} />);
    
    expect(screen.getByText('Pod Name')).toBeInTheDocument();
    expect(screen.getByText('Status')).toBeInTheDocument();
    expect(screen.getByText('Solution')).toBeInTheDocument();
    expect(screen.getByText('Detected')).toBeInTheDocument();
  });

  test('renders empty table when no pods provided', () => {
    render(<PodTable pods={[]} />);
    
    // Should only have headers, no data rows
    const rows = screen.getAllByRole('row');
    expect(rows).toHaveLength(1); // Only header row
  });

  test('renders pod data correctly', () => {
    render(<PodTable pods={mockPods} />);
    
    // Should have header row plus data rows
    const rows = screen.getAllByRole('row');
    expect(rows).toHaveLength(3); // Header + 2 data rows
    
    // Check pod names are displayed
    expect(screen.getByText('test-pod-1')).toBeInTheDocument();
    expect(screen.getByText('test-pod-2')).toBeInTheDocument();
    
    // Check namespaces are displayed
    expect(screen.getByText('default')).toBeInTheDocument();
    expect(screen.getByText('kube-system')).toBeInTheDocument();
  });

  test('renders status badges for pods', () => {
    render(<PodTable pods={mockPods} />);
    
    expect(screen.getByText('ImagePullBackOff')).toBeInTheDocument();
    expect(screen.getByText('CrashLoopBackOff')).toBeInTheDocument();
  });
});