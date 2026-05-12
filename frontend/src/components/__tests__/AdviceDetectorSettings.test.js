import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import AdviceDetectorSettings from '../admin/AdviceDetectorSettings';
import { api } from '../../services/api';

jest.mock('../../services/api', () => ({
  api: {
    getAdviceDetectors: jest.fn(),
    setAdviceDetectorEnabled: jest.fn(),
  },
}));

jest.mock('../../contexts/AuthContext', () => ({
  useCanWrite: () => true,
}));

const sampleDetectors = [
  {
    id: 'deployment-hpa-burst-mismatch',
    category: 'scaling',
    default_severity: 'medium',
    requires_hubble: false,
    enabled: true,
    description: 'HPA burst mismatch detector',
  },
  {
    id: 'cross-namespace-east-west',
    category: 'networking',
    default_severity: 'low',
    requires_hubble: true,
    enabled: false,
    description: 'Detects east-west traffic across namespaces',
  },
  {
    id: 'workload-restart-loop',
    category: 'reliability',
    default_severity: 'high',
    requires_hubble: false,
    enabled: true,
    description: 'Detects restart loops',
  },
  {
    id: 'service-graph-orphan',
    category: 'networking',
    default_severity: 'info',
    requires_hubble: true,
    enabled: true,
    description: 'Orphan service in graph',
  },
  {
    id: 'startup-io-amplification',
    category: 'startup',
    default_severity: 'medium',
    requires_hubble: false,
    enabled: true,
    description: 'Startup IO amplification detector',
  },
  {
    id: 'deployment-pattern-mismatch',
    category: 'workload-pattern',
    default_severity: 'low',
    requires_hubble: false,
    enabled: false,
    description: 'Workload pattern mismatch',
  },
  {
    id: 'flow-spike-detector',
    category: 'networking',
    default_severity: 'medium',
    requires_hubble: true,
    enabled: true,
    description: 'Flow spike detection',
  },
];

const sampleResponse = {
  detectors: sampleDetectors,
  hubble_status: {
    available: false,
    reason: 'HubbleClient stub: configure CILIUM_HUBBLE_RELAY_ADDRESS to enable.',
    flow_count: 0,
  },
};

describe('AdviceDetectorSettings', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    api.getAdviceDetectors.mockResolvedValue(sampleResponse);
    api.setAdviceDetectorEnabled.mockImplementation((id, enabled) =>
      Promise.resolve({ id, enabled }),
    );
  });

  test('renders 7 detectors sorted by id', async () => {
    render(<AdviceDetectorSettings />);
    await waitFor(() => expect(api.getAdviceDetectors).toHaveBeenCalled());

    const list = await screen.findByTestId('advice-detector-list');
    const items = list.querySelectorAll('li');
    expect(items).toHaveLength(7);

    // First item should be the alphabetically-first detector id.
    const ids = Array.from(items).map((li) => {
      const idEl = li.querySelector('.font-mono');
      return idEl ? idEl.textContent : '';
    });
    const sorted = [...ids].sort();
    expect(ids).toEqual(sorted);
    expect(ids[0]).toBe('cross-namespace-east-west');
  });

  test('shows amber Hubble-not-configured status', async () => {
    render(<AdviceDetectorSettings />);
    expect(
      await screen.findByText(/Hubble: not configured/i),
    ).toBeInTheDocument();
  });

  test('shows green Hubble-connected status when available', async () => {
    api.getAdviceDetectors.mockResolvedValue({
      detectors: sampleDetectors,
      hubble_status: { available: true, reason: '', flow_count: 42 },
    });
    render(<AdviceDetectorSettings />);
    expect(
      await screen.findByText(/Hubble: connected — 42 recent flows/i),
    ).toBeInTheDocument();
  });

  test('annotates Layer-2 disabled detectors when Hubble unavailable', async () => {
    render(<AdviceDetectorSettings />);
    await screen.findByTestId('advice-detector-list');
    // At least one "skipped — needs Hubble" annotation for layer-2 detectors.
    const annotations = screen.getAllByText(/skipped — needs Hubble/i);
    // 3 requires_hubble=true detectors in the fixture.
    expect(annotations.length).toBe(3);
  });

  test('toggling a detector calls setAdviceDetectorEnabled with the new value', async () => {
    render(<AdviceDetectorSettings />);
    await screen.findByTestId('advice-detector-list');

    const toggle = screen.getByLabelText(
      'Toggle detector deployment-hpa-burst-mismatch',
    );
    expect(toggle).toBeChecked();

    fireEvent.click(toggle);

    await waitFor(() =>
      expect(api.setAdviceDetectorEnabled).toHaveBeenCalledWith(
        'deployment-hpa-burst-mismatch',
        false,
      ),
    );
  });

  test('rolls back optimistic toggle and shows row error on failure', async () => {
    api.setAdviceDetectorEnabled.mockRejectedValueOnce(
      new Error('boom: server rejected'),
    );
    render(<AdviceDetectorSettings />);
    await screen.findByTestId('advice-detector-list');

    const toggle = screen.getByLabelText(
      'Toggle detector deployment-hpa-burst-mismatch',
    );
    fireEvent.click(toggle);

    // Inline error appears on the row.
    expect(await screen.findByText(/boom: server rejected/)).toBeInTheDocument();
    // Toggle rolls back to its previous state (was enabled=true).
    expect(toggle).toBeChecked();
  });
});
