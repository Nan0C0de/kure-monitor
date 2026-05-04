import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import DiagramTab from '../Diagram/DiagramTab';
import { api } from '../../services/api';

jest.mock('../../services/api', () => ({
  api: {
    getDiagramNamespaces: jest.fn(),
    getDiagramNamespace: jest.fn(),
    getDiagramWorkload: jest.fn(),
    getDiagramRoles: jest.fn(),
    getDiagramRole: jest.fn(),
    getDiagramClusterRole: jest.fn(),
    getResourceManifest: jest.fn(),
  },
}));

const emptyDiagram = { scope: 'namespace', root_id: null, nodes: [], edges: [], groups: [] };
const roleDiagram = {
  scope: 'role',
  root_id: 'Role/default/configmap-reader',
  nodes: [
    {
      id: 'Role/default/configmap-reader',
      kind: 'Role',
      name: 'configmap-reader',
      namespace: 'default',
    },
  ],
  edges: [],
  groups: [],
};
const clusterRoleDiagram = {
  scope: 'clusterrole',
  root_id: 'ClusterRole/--/cluster-admin',
  nodes: [
    {
      id: 'ClusterRole/--/cluster-admin',
      kind: 'ClusterRole',
      name: 'cluster-admin',
      namespace: '--',
    },
  ],
  edges: [],
  groups: [],
};

describe('DiagramTab — Roles mode', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    api.getDiagramNamespaces.mockResolvedValue({ namespaces: ['default'] });
    api.getDiagramNamespace.mockResolvedValue(emptyDiagram);
    api.getDiagramRoles.mockResolvedValue({
      cluster_roles: [{ name: 'cluster-admin' }],
      roles: [{ namespace: 'default', name: 'configmap-reader' }],
    });
    api.getDiagramRole.mockResolvedValue(roleDiagram);
    api.getDiagramClusterRole.mockResolvedValue(clusterRoleDiagram);
  });

  test('renders three tabs and switches into Roles mode', async () => {
    await act(async () => {
      render(<DiagramTab />);
    });

    expect(screen.getByRole('tab', { name: 'Namespace' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Workload' })).toBeInTheDocument();
    const rolesTab = screen.getByRole('tab', { name: 'Roles' });
    expect(rolesTab).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(rolesTab);
    });

    await waitFor(() => {
      expect(api.getDiagramRoles).toHaveBeenCalledTimes(1);
    });

    expect(
      screen.getByRole('tab', { name: 'Namespace Roles' })
    ).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: 'ClusterRoles' })).toBeInTheDocument();
  });

  test('selecting a namespaced role calls getDiagramRole(namespace, name)', async () => {
    await act(async () => {
      render(<DiagramTab />);
    });

    await act(async () => {
      fireEvent.click(screen.getByRole('tab', { name: 'Roles' }));
    });

    await waitFor(() => {
      expect(api.getDiagramRoles).toHaveBeenCalledTimes(1);
    });

    // Default selection should auto-trigger a fetch.
    await waitFor(() => {
      expect(api.getDiagramRole).toHaveBeenCalledWith('default', 'configmap-reader');
    });
  });

  test('switching to ClusterRoles scope calls getDiagramClusterRole(name)', async () => {
    await act(async () => {
      render(<DiagramTab />);
    });

    await act(async () => {
      fireEvent.click(screen.getByRole('tab', { name: 'Roles' }));
    });

    await waitFor(() => {
      expect(api.getDiagramRoles).toHaveBeenCalledTimes(1);
    });

    await act(async () => {
      fireEvent.click(screen.getByRole('tab', { name: 'ClusterRoles' }));
    });

    await waitFor(() => {
      expect(api.getDiagramClusterRole).toHaveBeenCalledWith('cluster-admin');
    });

    // The ClusterRole dropdown should now be visible.
    expect(screen.getByLabelText('ClusterRole')).toBeInTheDocument();
  });
});
