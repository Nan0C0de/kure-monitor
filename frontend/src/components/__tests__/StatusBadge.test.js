import { render, screen } from '@testing-library/react';
import StatusBadge from '../StatusBadge';

describe('StatusBadge', () => {
  test('renders ImagePullBackOff status', () => {
    render(<StatusBadge reason="ImagePullBackOff" />);
    expect(screen.getByText('ImagePullBackOff')).toBeInTheDocument();
  });

  test('renders FailedMount status', () => {
    render(<StatusBadge reason="FailedMount" />);
    expect(screen.getByText('FailedMount')).toBeInTheDocument();
  });

  test('renders CrashLoopBackOff status', () => {
    render(<StatusBadge reason="CrashLoopBackOff" />);
    expect(screen.getByText('CrashLoopBackOff')).toBeInTheDocument();
  });

  test('renders Pending status', () => {
    render(<StatusBadge reason="Pending" />);
    expect(screen.getByText('Pending')).toBeInTheDocument();
  });

  test('applies correct CSS classes for all status types', () => {
    const { rerender } = render(<StatusBadge reason="ImagePullBackOff" />);
    let badge = screen.getByText('ImagePullBackOff');
    expect(badge).toHaveClass('bg-red-50', 'text-red-700', 'border-red-300');

    rerender(<StatusBadge reason="FailedMount" />);
    badge = screen.getByText('FailedMount');
    expect(badge).toHaveClass('bg-red-50', 'text-red-700', 'border-red-300');

    rerender(<StatusBadge reason="Unknown" />);
    badge = screen.getByText('Unknown');
    expect(badge).toHaveClass('bg-red-50', 'text-red-700', 'border-red-300');
  });
});