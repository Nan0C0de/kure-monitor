import React from "react";
import {
  render,
  screen,
  waitFor,
  fireEvent,
  within,
  act,
} from "@testing-library/react";
import AdviceDetectorSettings from "../admin/AdviceDetectorSettings";
import { api } from "../../services/api";

jest.mock("../../services/api", () => ({
  api: {
    getAdviceDetectors: jest.fn(),
    setAdviceDetectorEnabled: jest.fn(),
  },
}));

jest.mock("../../contexts/AuthContext", () => ({
  useCanWrite: () => true,
}));

const sampleDetectors = [
  {
    id: "deployment-hpa-burst-mismatch",
    category: "scaling",
    default_severity: "medium",
    requires_hubble: false,
    enabled: true,
    description:
      "HPA burst mismatch — workload bursts exceed configured HPA range",
  },
  {
    id: "cross-namespace-east-west",
    category: "networking",
    default_severity: "low",
    requires_hubble: true,
    enabled: false,
    description:
      "East-west traffic across namespaces detected via Hubble flows",
  },
  {
    id: "workload-restart-loop",
    category: "reliability",
    default_severity: "high",
    requires_hubble: false,
    enabled: true,
    description: "Restart loops — pods crash and restart repeatedly",
  },
  {
    id: "service-graph-orphan",
    category: "networking",
    default_severity: "info",
    requires_hubble: true,
    enabled: true,
    description: "Orphan services in the graph with no callers",
  },
  {
    id: "startup-io-amplification",
    category: "startup",
    default_severity: "medium",
    requires_hubble: false,
    enabled: true,
    description: "Startup IO amplification — slow first reads after pod boot",
  },
  {
    id: "deployment-pattern-mismatch",
    category: "workload-pattern",
    default_severity: "low",
    requires_hubble: false,
    enabled: false,
    description:
      "Workload pattern mismatch — declared kind does not match shape",
  },
  {
    id: "flow-spike-detector",
    category: "networking",
    default_severity: "medium",
    requires_hubble: true,
    enabled: true,
    description: "Flow spike detection — sudden ramp in east-west traffic",
  },
];

const buildResponse = (overrides = {}) => ({
  detectors: sampleDetectors.map((d) => ({ ...d })),
  hubble_status: {
    available: false,
    reason:
      "HubbleClient stub: configure CILIUM_HUBBLE_RELAY_ADDRESS to enable.",
    flow_count: 0,
  },
  ...overrides,
});

const openModal = async () => {
  const button = await screen.findByRole("button", {
    name: /manage detectors/i,
  });
  await act(async () => {
    fireEvent.click(button);
  });
  await screen.findByTestId("advice-detector-modal");
};

describe("AdviceDetectorSettings", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    api.getAdviceDetectors.mockResolvedValue(buildResponse());
    api.setAdviceDetectorEnabled.mockImplementation((id, enabled) =>
      Promise.resolve({ id, enabled }),
    );
  });

  test("renders inline summary and does not render modal when closed", async () => {
    render(<AdviceDetectorSettings />);
    await screen.findByRole("button", { name: /manage detectors/i });

    // Wait for the initial load to finish.
    await waitFor(() =>
      expect(screen.queryByText(/Loading detectors/i)).not.toBeInTheDocument(),
    );

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("advice-detector-modal"),
    ).not.toBeInTheDocument();
    // Summary text is split across multiple inline nodes; collapse and match.
    const collapsed = document.body.textContent.replace(/\s+/g, " ");
    expect(collapsed).toMatch(/5 of 7 detectors? enabled/i);
  });

  test("opens modal on Manage button click and closes on Close button", async () => {
    render(<AdviceDetectorSettings />);
    await openModal();

    expect(screen.getByRole("dialog")).toHaveAttribute("aria-modal", "true");
    expect(screen.getByText(/Manage AI Advice detectors/i)).toBeInTheDocument();

    // Footer "Close" button (the X icon also has aria-label="Close").
    const closeButtons = screen.getAllByRole("button", { name: /^Close$/ });
    fireEvent.click(closeButtons[closeButtons.length - 1]);
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
  });

  test("Escape key closes the modal", async () => {
    render(<AdviceDetectorSettings />);
    await openModal();

    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
  });

  test("clicking the backdrop closes the modal", async () => {
    render(<AdviceDetectorSettings />);
    await openModal();

    fireEvent.click(screen.getByTestId("advice-detector-modal-backdrop"));
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
  });

  test("groups detectors by category with enabled counts", async () => {
    render(<AdviceDetectorSettings />);
    await openModal();

    // Categories present.
    expect(screen.getByTestId("category-group-networking")).toBeInTheDocument();
    expect(screen.getByTestId("category-group-scaling")).toBeInTheDocument();
    expect(
      screen.getByTestId("category-group-reliability"),
    ).toBeInTheDocument();

    // Networking has 3 detectors, 2 enabled.
    const networking = screen.getByTestId("category-group-networking");
    expect(
      within(networking).getByText(/\(2 of 3 enabled\)/i),
    ).toBeInTheDocument();

    // Scaling has 1 detector, 1 enabled.
    const scaling = screen.getByTestId("category-group-scaling");
    expect(
      within(scaling).getByText(/\(1 of 1 enabled\)/i),
    ).toBeInTheDocument();
  });

  test("toggling a detector calls setAdviceDetectorEnabled with new value", async () => {
    render(<AdviceDetectorSettings />);
    await openModal();

    const toggle = screen.getByLabelText(
      "Toggle detector deployment-hpa-burst-mismatch",
    );
    expect(toggle).toBeChecked();

    fireEvent.click(toggle);

    await waitFor(() =>
      expect(api.setAdviceDetectorEnabled).toHaveBeenCalledWith(
        "deployment-hpa-burst-mismatch",
        false,
      ),
    );

    // Reflects new state.
    expect(toggle).not.toBeChecked();
  });

  test("Disable all disables only currently-enabled detectors", async () => {
    render(<AdviceDetectorSettings />);
    await openModal();

    fireEvent.click(screen.getByRole("button", { name: /disable all/i }));

    // 5 of 7 enabled in fixture; bulk should disable those 5 (not the 2 already off).
    await waitFor(() => {
      expect(api.setAdviceDetectorEnabled).toHaveBeenCalledTimes(5);
    });
    api.setAdviceDetectorEnabled.mock.calls.forEach((call) => {
      expect(call[1]).toBe(false);
    });
  });

  test("Enable all enables only currently-disabled detectors", async () => {
    render(<AdviceDetectorSettings />);
    await openModal();

    fireEvent.click(screen.getByRole("button", { name: /enable all/i }));

    // 2 disabled in fixture; bulk enables those 2.
    await waitFor(() => {
      expect(api.setAdviceDetectorEnabled).toHaveBeenCalledTimes(2);
    });
    api.setAdviceDetectorEnabled.mock.calls.forEach((call) => {
      expect(call[1]).toBe(true);
    });
  });

  test("Reset to defaults enables all (defaults = enabled)", async () => {
    render(<AdviceDetectorSettings />);
    await openModal();

    fireEvent.click(screen.getByRole("button", { name: /reset to defaults/i }));

    await waitFor(() => {
      expect(api.setAdviceDetectorEnabled).toHaveBeenCalledTimes(2);
    });
    api.setAdviceDetectorEnabled.mock.calls.forEach((call) => {
      expect(call[1]).toBe(true);
    });
  });

  test("search filters detectors by title, description, and category", async () => {
    render(<AdviceDetectorSettings />);
    await openModal();

    const searchBox = screen.getByLabelText("Search detectors");

    // Filter by title fragment.
    fireEvent.change(searchBox, { target: { value: "restart" } });
    expect(
      screen.getByTestId("category-group-reliability"),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId("category-group-networking"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("category-group-scaling"),
    ).not.toBeInTheDocument();

    // Filter by category name.
    fireEvent.change(searchBox, { target: { value: "networking" } });
    expect(screen.getByTestId("category-group-networking")).toBeInTheDocument();
    expect(
      screen.queryByTestId("category-group-reliability"),
    ).not.toBeInTheDocument();

    // Filter by description fragment.
    fireEvent.change(searchBox, { target: { value: "amplification" } });
    expect(screen.getByTestId("category-group-startup")).toBeInTheDocument();
    expect(
      screen.queryByTestId("category-group-networking"),
    ).not.toBeInTheDocument();

    // No matches.
    fireEvent.change(searchBox, { target: { value: "zzznevermatch" } });
    expect(
      screen.getByText(/No detectors match your search/i),
    ).toBeInTheDocument();
  });

  test("renders Needs Hubble badge and disables toggle when Hubble unavailable", async () => {
    render(<AdviceDetectorSettings />);
    await openModal();

    // Three detectors in the fixture require Hubble — match the badge text exactly.
    const badges = screen.getAllByText("Needs Hubble");
    expect(badges.length).toBe(3);

    // Their toggles should be disabled since hubble_status.available === false.
    [
      "cross-namespace-east-west",
      "service-graph-orphan",
      "flow-spike-detector",
    ].forEach((id) => {
      const toggle = screen.getByLabelText(`Toggle detector ${id}`);
      expect(toggle).toBeDisabled();
    });

    // A non-hubble detector toggle stays enabled.
    expect(
      screen.getByLabelText("Toggle detector deployment-hpa-burst-mismatch"),
    ).not.toBeDisabled();
  });

  test("rolls back optimistic toggle and shows row error on failure", async () => {
    api.setAdviceDetectorEnabled.mockRejectedValueOnce(
      new Error("boom: server rejected"),
    );
    render(<AdviceDetectorSettings />);
    await openModal();

    const toggle = screen.getByLabelText(
      "Toggle detector deployment-hpa-burst-mismatch",
    );
    expect(toggle).toBeChecked();
    fireEvent.click(toggle);

    expect(
      await screen.findByText(/boom: server rejected/),
    ).toBeInTheDocument();
    expect(toggle).toBeChecked();
  });

  test("shows a Saved indicator after a successful toggle that fades out", async () => {
    jest.useFakeTimers();
    try {
      render(<AdviceDetectorSettings />);
      await openModal();

      const toggle = screen.getByLabelText(
        "Toggle detector deployment-hpa-burst-mismatch",
      );
      fireEvent.click(toggle);

      await waitFor(() =>
        expect(api.setAdviceDetectorEnabled).toHaveBeenCalled(),
      );
      expect(
        await screen.findByTestId(
          "saved-indicator-deployment-hpa-burst-mismatch",
        ),
      ).toBeInTheDocument();

      act(() => {
        jest.advanceTimersByTime(2100);
      });

      await waitFor(() =>
        expect(
          screen.queryByTestId("saved-indicator-deployment-hpa-burst-mismatch"),
        ).not.toBeInTheDocument(),
      );
    } finally {
      jest.useRealTimers();
    }
  });

  test("shows Hubble-connected status when available", async () => {
    api.getAdviceDetectors.mockResolvedValue(
      buildResponse({
        hubble_status: { available: true, reason: "", flow_count: 42 },
      }),
    );
    render(<AdviceDetectorSettings />);
    // Summary card shows connected status without opening the modal.
    expect(
      await screen.findByText(/Hubble: connected — 42 recent flows/i),
    ).toBeInTheDocument();
  });
});
