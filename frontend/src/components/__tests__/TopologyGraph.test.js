import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import TopologyGraph from '../Diagram/TopologyGraph';
import { api } from '../../services/api';

jest.mock('../../services/api', () => ({
  api: {
    getResourceManifest: jest.fn(),
  },
}));

const mockResponse = {
  scope: 'namespace',
  nodes: [
    { id: 'Deployment/ns/web', kind: 'Deployment', name: 'web', namespace: 'ns' },
    { id: 'ReplicaSet/ns/web-rs', kind: 'ReplicaSet', name: 'web-rs', namespace: 'ns' },
    { id: 'Pod/ns/web-pod', kind: 'Pod', name: 'web-pod', namespace: 'ns', status: 'Running' },
    { id: 'Service/ns/web-svc', kind: 'Service', name: 'web-svc', namespace: 'ns' },
    { id: 'Ingress/ns/web-ing', kind: 'Ingress', name: 'web-ing', namespace: 'ns' },
    { id: 'ConfigMap/ns/web-cm', kind: 'ConfigMap', name: 'web-cm', namespace: 'ns' },
    {
      id: 'Secret/ns/web-secret',
      kind: 'Secret',
      name: 'web-secret',
      namespace: 'ns',
      metadata: { derived: true },
    },
    { id: 'HorizontalPodAutoscaler/ns/web-hpa', kind: 'HorizontalPodAutoscaler', name: 'web-hpa', namespace: 'ns' },
    { id: 'NetworkPolicy/ns/web-np', kind: 'NetworkPolicy', name: 'web-np', namespace: 'ns' },
  ],
  edges: [
    { source: 'Deployment/ns/web', target: 'ReplicaSet/ns/web-rs', type: 'owns' },
    { source: 'Service/ns/web-svc', target: 'Pod/ns/web-pod', type: 'selects' },
    { source: 'Ingress/ns/web-ing', target: 'Service/ns/web-svc', type: 'routes' },
    { source: 'Pod/ns/web-pod', target: 'ConfigMap/ns/web-cm', type: 'mounts' },
    { source: 'HorizontalPodAutoscaler/ns/web-hpa', target: 'Deployment/ns/web', type: 'scales' },
    { source: 'NetworkPolicy/ns/web-np', target: 'Pod/ns/web-pod', type: 'policy' },
  ],
  groups: [],
};

describe('TopologyGraph', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test('renders all six edge types from a mock response without crashing', () => {
    render(<TopologyGraph data={mockResponse} />);

    expect(screen.getByTestId('edge-owns')).toBeInTheDocument();
    expect(screen.getByTestId('edge-selects')).toBeInTheDocument();
    expect(screen.getByTestId('edge-routes')).toBeInTheDocument();
    expect(screen.getByTestId('edge-mounts')).toBeInTheDocument();
    expect(screen.getByTestId('edge-scales')).toBeInTheDocument();
    expect(screen.getByTestId('edge-policy')).toBeInTheDocument();
  });

  test('clicking a node opens the manifest modal and calls getResourceManifest with (ns, kind, name)', async () => {
    api.getResourceManifest.mockResolvedValue({
      manifest: 'apiVersion: v1\nkind: Pod\nmetadata:\n  name: web-pod\n',
      kind: 'Pod',
      name: 'web-pod',
      namespace: 'ns',
    });

    render(<TopologyGraph data={mockResponse} />);

    fireEvent.click(screen.getByTestId('node-Pod/ns/web-pod'));

    await waitFor(() => {
      expect(api.getResourceManifest).toHaveBeenCalledWith('ns', 'Pod', 'web-pod');
    });

    expect(await screen.findByText('Pod Manifest')).toBeInTheDocument();
    expect(screen.getByText('ns/web-pod')).toBeInTheDocument();
  });

  test('clicking a derived Secret node shows the no-read-access info instead of fetching', async () => {
    render(<TopologyGraph data={mockResponse} />);

    fireEvent.click(screen.getByTestId('node-Secret/ns/web-secret'));

    expect(await screen.findByText(/Secret manifest not available/i)).toBeInTheDocument();
    expect(api.getResourceManifest).not.toHaveBeenCalled();
  });

  describe('edge focus', () => {
    const focusData = {
      scope: 'namespace',
      nodes: [
        { id: 'A', kind: 'Deployment', name: 'A', namespace: 'ns' },
        { id: 'B', kind: 'ReplicaSet', name: 'B', namespace: 'ns' },
        { id: 'C', kind: 'Pod', name: 'C', namespace: 'ns' },
        { id: 'D', kind: 'ConfigMap', name: 'D', namespace: 'ns' },
      ],
      edges: [
        { source: 'A', target: 'B', type: 'owns' },
        { source: 'B', target: 'C', type: 'owns' },
      ],
      groups: [],
    };

    test('clicking an edge focuses its path and dims disconnected nodes', () => {
      render(<TopologyGraph data={focusData} />);

      // Before clicking, everything is at full opacity.
      expect(screen.getByTestId('node-A').getAttribute('data-opacity')).toBe('1');
      expect(screen.getByTestId('node-D').getAttribute('data-opacity')).toBe('1');

      // Click the A->B edge. There are two `edge-owns` elements; pick the A->B one.
      const ownsEdges = screen.getAllByTestId('edge-owns');
      const aToB = ownsEdges.find(
        (el) => el.getAttribute('data-source') === 'A' && el.getAttribute('data-target') === 'B'
      );
      expect(aToB).toBeTruthy();
      fireEvent.click(aToB);

      // A, B, C are all in the path (forward from B reaches C; backward from A reaches none).
      expect(screen.getByTestId('node-A').getAttribute('data-opacity')).toBe('1');
      expect(screen.getByTestId('node-B').getAttribute('data-opacity')).toBe('1');
      expect(screen.getByTestId('node-C').getAttribute('data-opacity')).toBe('1');
      // Disconnected D is dimmed.
      expect(screen.getByTestId('node-D').getAttribute('data-opacity')).toBe('0.15');

      // Both edges remain in the path.
      const focusedOwns = screen
        .getAllByTestId('edge-owns')
        .filter((el) => el.getAttribute('data-opacity') === '1');
      expect(focusedOwns).toHaveLength(2);
    });

    test('clicking the same edge again clears focus (toggle)', () => {
      render(<TopologyGraph data={focusData} />);

      const ownsEdges = screen.getAllByTestId('edge-owns');
      const aToB = ownsEdges.find(
        (el) => el.getAttribute('data-source') === 'A' && el.getAttribute('data-target') === 'B'
      );

      fireEvent.click(aToB);
      expect(screen.getByTestId('node-D').getAttribute('data-opacity')).toBe('0.15');

      // Re-resolve since a re-render replaced the DOM elements.
      const aToB2 = screen
        .getAllByTestId('edge-owns')
        .find(
          (el) => el.getAttribute('data-source') === 'A' && el.getAttribute('data-target') === 'B'
        );
      fireEvent.click(aToB2);

      expect(screen.getByTestId('node-D').getAttribute('data-opacity')).toBe('1');
      expect(screen.getByTestId('node-A').getAttribute('data-opacity')).toBe('1');
    });
  });

  test('shows the no-read-access info when the backend returns 403 for a non-derived resource', async () => {
    const err = new Error('Forbidden');
    err.status = 403;
    api.getResourceManifest.mockRejectedValue(err);

    const data = {
      ...mockResponse,
      nodes: [
        { id: 'Secret/ns/other', kind: 'Secret', name: 'other', namespace: 'ns' },
      ],
      edges: [],
    };

    render(<TopologyGraph data={data} />);

    fireEvent.click(screen.getByTestId('node-Secret/ns/other'));

    await waitFor(() => {
      expect(api.getResourceManifest).toHaveBeenCalledWith('ns', 'Secret', 'other');
    });

    expect(await screen.findByText(/Secret manifest not available/i)).toBeInTheDocument();
  });
});
