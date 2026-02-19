import { render, screen, fireEvent } from '@testing-library/react';
import KyvernoViolationsPanel from '../KyvernoViolationsPanel';

// Mock lucide-react
jest.mock('lucide-react', () => ({
  ShieldAlert: () => <span data-testid="shield-alert-icon">ShieldAlert</span>,
  ChevronDown: () => <span data-testid="chevron-down">ChevronDown</span>,
  ChevronUp: () => <span data-testid="chevron-up">ChevronUp</span>,
}));

const mockViolations = [
  {
    policy_name: 'require-labels',
    rule_name: 'check-for-labels',
    resource_kind: 'Pod',
    resource_name: 'test-pod-1',
    resource_namespace: 'default',
    message: 'label "app" is required',
    severity: 'high',
    category: 'Best Practices',
    timestamp: '2025-01-01T00:00:00Z'
  },
  {
    policy_name: 'require-labels',
    rule_name: 'check-for-labels',
    resource_kind: 'Deployment',
    resource_name: 'test-deploy-1',
    resource_namespace: 'staging',
    message: 'label "app" is required',
    severity: 'medium',
    category: 'Best Practices',
    timestamp: '2025-01-01T01:00:00Z'
  },
  {
    policy_name: 'disallow-privileged',
    rule_name: 'no-privileged-containers',
    resource_kind: 'Pod',
    resource_name: 'risky-pod',
    resource_namespace: 'production',
    message: 'Privileged mode is not allowed',
    severity: 'high',
    category: 'Security',
    timestamp: '2025-01-01T02:00:00Z'
  },
  {
    policy_name: 'restrict-image-registries',
    rule_name: 'validate-registries',
    resource_kind: 'Pod',
    resource_name: 'untrusted-pod',
    resource_namespace: 'default',
    message: 'Image registry is not trusted',
    severity: 'low',
    category: 'Security',
    timestamp: '2025-01-01T03:00:00Z'
  }
];

describe('KyvernoViolationsPanel', () => {
  test('renders empty state when no violations', () => {
    render(<KyvernoViolationsPanel violations={[]} />);

    expect(screen.getByText('Policy Violations')).toBeInTheDocument();
    expect(screen.getByText('0')).toBeInTheDocument();
    expect(screen.getByText('No policy violations detected')).toBeInTheDocument();
  });

  test('renders empty state with default props', () => {
    render(<KyvernoViolationsPanel />);

    expect(screen.getByText('No policy violations detected')).toBeInTheDocument();
  });

  test('renders violation count badge', () => {
    render(<KyvernoViolationsPanel violations={mockViolations} />);

    expect(screen.getByText('Policy Violations')).toBeInTheDocument();
    expect(screen.getByText('4')).toBeInTheDocument();
  });

  test('renders table headers when expanded', () => {
    render(<KyvernoViolationsPanel violations={mockViolations} />);

    expect(screen.getByText('Policy')).toBeInTheDocument();
    expect(screen.getByText('Rule')).toBeInTheDocument();
    expect(screen.getByText('Resource')).toBeInTheDocument();
    expect(screen.getByText('Namespace')).toBeInTheDocument();
    expect(screen.getByText('Message')).toBeInTheDocument();
    expect(screen.getByText('Severity')).toBeInTheDocument();
  });

  test('renders violation data correctly', () => {
    render(<KyvernoViolationsPanel violations={mockViolations} />);

    expect(screen.getAllByText('require-labels')).toHaveLength(2);
    expect(screen.getByText('disallow-privileged')).toBeInTheDocument();
    expect(screen.getByText('restrict-image-registries')).toBeInTheDocument();
    expect(screen.getByText('test-pod-1')).toBeInTheDocument();
    expect(screen.getByText('risky-pod')).toBeInTheDocument();
    expect(screen.getAllByText('label "app" is required')).toHaveLength(2);
    expect(screen.getByText('Privileged mode is not allowed')).toBeInTheDocument();
  });

  test('renders resource kind under resource name', () => {
    render(<KyvernoViolationsPanel violations={mockViolations} />);

    // Resource kinds shown as secondary text
    const pods = screen.getAllByText('Pod');
    expect(pods.length).toBeGreaterThan(0);
    expect(screen.getByText('Deployment')).toBeInTheDocument();
  });

  test('renders namespaces', () => {
    render(<KyvernoViolationsPanel violations={mockViolations} />);

    expect(screen.getAllByText('default')).toHaveLength(2);
    expect(screen.getByText('staging')).toBeInTheDocument();
    expect(screen.getByText('production')).toBeInTheDocument();
  });

  test('displays severity badges', () => {
    render(<KyvernoViolationsPanel violations={mockViolations} />);

    const highBadges = screen.getAllByText('HIGH');
    expect(highBadges).toHaveLength(2);
    expect(screen.getByText('MEDIUM')).toBeInTheDocument();
    expect(screen.getByText('LOW')).toBeInTheDocument();
  });

  test('collapses table when header is clicked', () => {
    render(<KyvernoViolationsPanel violations={mockViolations} />);

    // Initially expanded - table should be visible
    expect(screen.getByText('Policy')).toBeInTheDocument();
    expect(screen.getByTestId('chevron-up')).toBeInTheDocument();

    // Click the header to collapse
    fireEvent.click(screen.getByText('Policy Violations'));

    // Table should be hidden
    expect(screen.queryByText('Policy')).not.toBeInTheDocument();
    expect(screen.getByTestId('chevron-down')).toBeInTheDocument();
  });

  test('expands table when header is clicked again', () => {
    render(<KyvernoViolationsPanel violations={mockViolations} />);

    // Collapse
    fireEvent.click(screen.getByText('Policy Violations'));
    expect(screen.queryByText('Policy')).not.toBeInTheDocument();

    // Expand again
    fireEvent.click(screen.getByText('Policy Violations'));
    expect(screen.getByText('Policy')).toBeInTheDocument();
    expect(screen.getByTestId('chevron-up')).toBeInTheDocument();
  });

  test('renders in dark mode', () => {
    render(<KyvernoViolationsPanel isDark={true} violations={mockViolations} />);

    const table = screen.getByRole('table');
    expect(table.querySelector('thead')).toHaveClass('bg-gray-900');
  });

  test('renders in light mode by default', () => {
    render(<KyvernoViolationsPanel violations={mockViolations} />);

    const table = screen.getByRole('table');
    expect(table.querySelector('thead')).toHaveClass('bg-gray-50');
  });

  test('groups violations by policy name', () => {
    render(<KyvernoViolationsPanel violations={mockViolations} />);

    // Both 'require-labels' violations should render the policy name
    const requireLabels = screen.getAllByText('require-labels');
    expect(requireLabels).toHaveLength(2);

    const checkForLabels = screen.getAllByText('check-for-labels');
    expect(checkForLabels).toHaveLength(2);
  });

  test('handles unknown severity gracefully', () => {
    const violationWithUnknownSeverity = [{
      policy_name: 'test-policy',
      rule_name: 'test-rule',
      resource_kind: 'Pod',
      resource_name: 'test-pod',
      resource_namespace: 'default',
      message: 'Test message',
      severity: null,
      category: 'Test',
      timestamp: '2025-01-01T00:00:00Z'
    }];

    render(<KyvernoViolationsPanel violations={violationWithUnknownSeverity} />);

    expect(screen.getByText('UNKNOWN')).toBeInTheDocument();
  });

  test('shows ShieldAlert icon', () => {
    render(<KyvernoViolationsPanel violations={mockViolations} />);

    expect(screen.getByTestId('shield-alert-icon')).toBeInTheDocument();
  });
});
