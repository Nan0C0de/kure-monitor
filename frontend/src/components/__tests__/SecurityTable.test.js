import { render, screen, fireEvent } from '@testing-library/react';
import SecurityTable from '../SecurityTable';

// Mock lucide-react
jest.mock('lucide-react', () => ({
  Shield: () => <span data-testid="shield-icon">Shield</span>,
  ChevronDown: () => <span data-testid="chevron-down">ChevronDown</span>,
  ChevronRight: () => <span data-testid="chevron-right">ChevronRight</span>,
  AlertTriangle: () => <span data-testid="alert-triangle">AlertTriangle</span>,
  AlertCircle: () => <span data-testid="alert-circle">AlertCircle</span>,
  Info: () => <span data-testid="info-icon">Info</span>,
}));

const mockFindings = [
  {
    id: 1,
    resource_name: 'test-pod',
    resource_type: 'Pod',
    namespace: 'default',
    severity: 'critical',
    category: 'Security Context',
    title: 'Privileged container detected',
    description: 'Container is running in privileged mode',
    remediation: 'Remove privileged: true from the container spec',
    timestamp: '2025-01-01T00:00:00Z'
  },
  {
    id: 2,
    resource_name: 'risky-deployment',
    resource_type: 'Deployment',
    namespace: 'kube-system',
    severity: 'high',
    category: 'RBAC',
    title: 'Excessive permissions detected',
    description: 'Deployment has wildcard permissions',
    remediation: 'Limit RBAC permissions to specific resources',
    timestamp: '2025-01-01T01:00:00Z'
  },
  {
    id: 3,
    resource_name: 'warning-pod',
    resource_type: 'Pod',
    namespace: 'test',
    severity: 'medium',
    category: 'Resources',
    title: 'Missing resource limits',
    description: 'Container does not have resource limits set',
    remediation: 'Add resources.limits to the container spec',
    timestamp: '2025-01-01T02:00:00Z'
  },
  {
    id: 4,
    resource_name: 'info-pod',
    resource_type: 'Pod',
    namespace: 'dev',
    severity: 'low',
    category: 'Best Practices',
    title: 'Missing readiness probe',
    description: 'Container does not have a readiness probe',
    remediation: 'Add readinessProbe to the container spec',
    timestamp: '2025-01-01T03:00:00Z'
  }
];

describe('SecurityTable', () => {
  test('renders nothing when findings array is empty', () => {
    const { container } = render(<SecurityTable findings={[]} />);
    expect(container.firstChild).toBeNull();
  });

  test('renders table headers', () => {
    render(<SecurityTable findings={mockFindings} />);

    expect(screen.getByText('Severity')).toBeInTheDocument();
    expect(screen.getByText('Resource')).toBeInTheDocument();
    expect(screen.getByText('Namespace')).toBeInTheDocument();
    expect(screen.getByText('Category')).toBeInTheDocument();
    expect(screen.getByText('Issue')).toBeInTheDocument();
  });

  test('renders findings correctly', () => {
    render(<SecurityTable findings={mockFindings} />);

    expect(screen.getByText('test-pod')).toBeInTheDocument();
    expect(screen.getByText('risky-deployment')).toBeInTheDocument();
    expect(screen.getByText('Privileged container detected')).toBeInTheDocument();
    expect(screen.getByText('Excessive permissions detected')).toBeInTheDocument();
  });

  test('displays severity badges with correct colors', () => {
    render(<SecurityTable findings={mockFindings} />);

    expect(screen.getByText('CRITICAL')).toBeInTheDocument();
    expect(screen.getByText('HIGH')).toBeInTheDocument();
    expect(screen.getByText('MEDIUM')).toBeInTheDocument();
    expect(screen.getByText('LOW')).toBeInTheDocument();
  });

  test('displays namespaces', () => {
    render(<SecurityTable findings={mockFindings} />);

    expect(screen.getByText('default')).toBeInTheDocument();
    expect(screen.getByText('kube-system')).toBeInTheDocument();
    expect(screen.getByText('test')).toBeInTheDocument();
    expect(screen.getByText('dev')).toBeInTheDocument();
  });

  test('displays categories', () => {
    render(<SecurityTable findings={mockFindings} />);

    expect(screen.getByText('Security Context')).toBeInTheDocument();
    expect(screen.getByText('RBAC')).toBeInTheDocument();
    expect(screen.getByText('Resources')).toBeInTheDocument();
    expect(screen.getByText('Best Practices')).toBeInTheDocument();
  });

  test('expands row on click to show details', () => {
    render(<SecurityTable findings={mockFindings} />);

    // Initially, description should not be visible
    expect(screen.queryByText('Container is running in privileged mode')).not.toBeInTheDocument();

    // Click on the first row
    fireEvent.click(screen.getByText('Privileged container detected'));

    // Now description should be visible
    expect(screen.getByText('Description')).toBeInTheDocument();
    expect(screen.getByText('Container is running in privileged mode')).toBeInTheDocument();
    expect(screen.getByText('Remediation')).toBeInTheDocument();
    expect(screen.getByText('Remove privileged: true from the container spec')).toBeInTheDocument();
  });

  test('collapses row on second click', () => {
    render(<SecurityTable findings={mockFindings} />);

    // Click to expand
    fireEvent.click(screen.getByText('Privileged container detected'));
    expect(screen.getByText('Container is running in privileged mode')).toBeInTheDocument();

    // Click again to collapse
    fireEvent.click(screen.getByText('Privileged container detected'));
    expect(screen.queryByText('Container is running in privileged mode')).not.toBeInTheDocument();
  });

  test('shows correct icon for severity levels', () => {
    render(<SecurityTable findings={mockFindings} />);

    // Critical and High should show AlertTriangle
    expect(screen.getAllByTestId('alert-triangle')).toHaveLength(2);
    // Medium should show AlertCircle
    expect(screen.getAllByTestId('alert-circle')).toHaveLength(1);
    // Low should show Info
    expect(screen.getAllByTestId('info-icon')).toHaveLength(1);
  });

  test('shows chevron icons for expand/collapse', () => {
    render(<SecurityTable findings={mockFindings} />);

    // Initially all should show ChevronRight
    expect(screen.getAllByTestId('chevron-right')).toHaveLength(4);

    // Click to expand first row
    fireEvent.click(screen.getByText('Privileged container detected'));

    // Now one should show ChevronDown
    expect(screen.getAllByTestId('chevron-down')).toHaveLength(1);
    expect(screen.getAllByTestId('chevron-right')).toHaveLength(3);
  });

  test('renders in dark mode', () => {
    render(<SecurityTable findings={mockFindings} isDark={true} />);

    // Check that dark mode classes are applied
    const table = screen.getByRole('table');
    expect(table.querySelector('thead')).toHaveClass('bg-gray-900');
  });

  test('renders in light mode by default', () => {
    render(<SecurityTable findings={mockFindings} />);

    // Check that light mode classes are applied
    const table = screen.getByRole('table');
    expect(table.querySelector('thead')).toHaveClass('bg-gray-50');
  });

  test('displays resource type', () => {
    render(<SecurityTable findings={mockFindings} />);

    // Multiple Pods exist, so check that at least one is present
    expect(screen.getAllByText('Pod').length).toBeGreaterThan(0);
    expect(screen.getByText('Deployment')).toBeInTheDocument();
  });

  test('formats timestamp in expanded details', () => {
    render(<SecurityTable findings={mockFindings} />);

    // Expand first row
    fireEvent.click(screen.getByText('Privileged container detected'));

    // Check that timestamp section exists
    expect(screen.getByText('Detected At')).toBeInTheDocument();
  });

  test('only one row can be expanded at a time', () => {
    render(<SecurityTable findings={mockFindings} />);

    // Expand first row
    fireEvent.click(screen.getByText('Privileged container detected'));
    expect(screen.getByText('Container is running in privileged mode')).toBeInTheDocument();

    // Expand second row
    fireEvent.click(screen.getByText('Excessive permissions detected'));

    // First row should now be collapsed
    expect(screen.queryByText('Container is running in privileged mode')).not.toBeInTheDocument();
    // Second row should be expanded
    expect(screen.getByText('Deployment has wildcard permissions')).toBeInTheDocument();
  });
});
