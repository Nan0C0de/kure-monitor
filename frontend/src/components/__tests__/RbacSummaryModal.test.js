import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import RbacSummaryModal from '../Diagram/RbacSummaryModal';

describe('RbacSummaryModal', () => {
  test('returns null when not open', () => {
    const { container } = render(
      <RbacSummaryModal
        isOpen={false}
        onClose={() => {}}
        kind="Permission"
        name="permission/configmaps"
        namespace=""
        metadata={{}}
      />
    );
    expect(container.firstChild).toBeNull();
  });

  test('renders Permission summary with verbs as badges', () => {
    render(
      <RbacSummaryModal
        isOpen={true}
        onClose={() => {}}
        kind="Permission"
        name="permission/configmaps"
        namespace=""
        metadata={{
          apiGroup: '',
          resource: 'configmaps',
          verbs: ['get', 'list', 'watch'],
          resourceNames: ['my-config'],
        }}
      />
    );

    expect(screen.getByText('Permission')).toBeInTheDocument();
    expect(screen.getByText('configmaps')).toBeInTheDocument();
    expect(screen.getByTestId('verb-get')).toBeInTheDocument();
    expect(screen.getByTestId('verb-list')).toBeInTheDocument();
    expect(screen.getByTestId('verb-watch')).toBeInTheDocument();
    expect(screen.getByText('my-config')).toBeInTheDocument();
  });

  test('renders Subject:User summary with the synthesized note', () => {
    render(
      <RbacSummaryModal
        isOpen={true}
        onClose={() => {}}
        kind="Subject:User"
        name="alice@example.com"
        namespace=""
        metadata={{}}
      />
    );

    expect(screen.getByText('Subject:User')).toBeInTheDocument();
    expect(screen.getAllByText('alice@example.com').length).toBeGreaterThan(0);
    expect(screen.getByText(/synthesized RBAC subject/i)).toBeInTheDocument();
  });

  test('close button fires onClose', () => {
    const onClose = jest.fn();
    render(
      <RbacSummaryModal
        isOpen={true}
        onClose={onClose}
        kind="Subject:Group"
        name="system:masters"
        namespace=""
        metadata={{}}
      />
    );

    const closeButtons = screen.getAllByRole('button', { name: 'Close' });
    fireEvent.click(closeButtons[closeButtons.length - 1]);
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
