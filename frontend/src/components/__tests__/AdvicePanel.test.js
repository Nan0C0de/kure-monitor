import React from "react";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import AdvicePanel from "../AdvicePanel";
import { api } from "../../services/api";

jest.mock("../../services/api", () => ({
  api: {
    getAdviceFindings: jest.fn(),
    getDiagramNamespaces: jest.fn(),
    getDiagramWorkloads: jest.fn(),
    runAdviceScan: jest.fn(),
    dismissAdviceFinding: jest.fn(),
    restoreAdviceFinding: jest.fn(),
    getAdviceDetectors: jest.fn(),
  },
}));

const sampleFinding = {
  id: 1,
  detector_id: "startup-io-amplification",
  severity: "high",
  category: "startup",
  title: "Startup IO amplification",
  summary: "Init container reads many large files.",
  resource_kind: "StatefulSet",
  resource_name: "cache",
  namespace: "data",
  evidence: { files: 1024 },
  recommended_change: "Bake assets into the image.",
  confidence: 0.75,
  explanation: "Long startup IO causes slow rollouts.",
  dismissed: false,
};

describe("AdvicePanel", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    api.getAdviceFindings.mockResolvedValue({ findings: [sampleFinding] });
    api.getDiagramNamespaces.mockResolvedValue({ namespaces: ["data", "web"] });
    api.getDiagramWorkloads.mockResolvedValue({ workloads: [] });
    api.runAdviceScan.mockResolvedValue({ findings: [], scan_id: "scan-1" });
    api.dismissAdviceFinding.mockResolvedValue({ dismissed: true, id: 1 });
    api.restoreAdviceFinding.mockResolvedValue({ restored: true, id: 1 });
    // Default: full coverage, no banner.
    api.getAdviceDetectors.mockResolvedValue({
      detectors: [
        { id: "d1", enabled: true, requires_hubble: false },
        { id: "d2", enabled: true, requires_hubble: false },
      ],
      hubble_status: { available: true, reason: "ok", flow_count: 10 },
    });
  });

  test("loads and renders findings on mount", async () => {
    render(<AdvicePanel canWrite={true} />);
    await waitFor(() => expect(api.getAdviceFindings).toHaveBeenCalledWith({}));
    expect(
      await screen.findByText("Startup IO amplification"),
    ).toBeInTheDocument();
  });

  test("toggling show-dismissed re-fetches with include_dismissed", async () => {
    render(<AdvicePanel canWrite={true} />);
    await waitFor(() => expect(api.getAdviceFindings).toHaveBeenCalledWith({}));
    fireEvent.click(screen.getByLabelText(/Show dismissed/i));
    await waitFor(() =>
      expect(api.getAdviceFindings).toHaveBeenCalledWith({
        include_dismissed: true,
      }),
    );
  });

  test("Run scan button posts to runAdviceScan", async () => {
    render(<AdvicePanel canWrite={true} />);
    await screen.findByText("Startup IO amplification");
    fireEvent.click(screen.getByRole("button", { name: /Run scan/i }));
    await waitFor(() => expect(api.runAdviceScan).toHaveBeenCalled());
  });

  test("Run scan button hidden when canWrite is false", async () => {
    render(<AdvicePanel canWrite={false} />);
    await screen.findByText("Startup IO amplification");
    expect(
      screen.queryByRole("button", { name: /Run scan/i }),
    ).not.toBeInTheDocument();
  });

  test("WS advice_scan_status started shows banner", async () => {
    const { rerender } = render(<AdvicePanel canWrite={true} wsEvent={null} />);
    await screen.findByText("Startup IO amplification");
    rerender(
      <AdvicePanel
        canWrite={true}
        wsEvent={{
          seq: 1,
          type: "advice_scan_status",
          data: {
            status: "started",
            scan_id: "s1",
            scope: { namespace: "data" },
          },
        }}
      />,
    );
    expect(
      await screen.findByText(/Advice scan in progress/i),
    ).toBeInTheDocument();
  });

  test("WS advice_finding_deleted removes the finding", async () => {
    const { rerender } = render(<AdvicePanel canWrite={true} wsEvent={null} />);
    await screen.findByText("Startup IO amplification");
    rerender(
      <AdvicePanel
        canWrite={true}
        wsEvent={{
          seq: 1,
          type: "advice_finding_deleted",
          data: {
            id: 1,
            namespace: "data",
            resource_kind: "StatefulSet",
            resource_name: "cache",
            detector_id: "startup-io-amplification",
          },
        }}
      />,
    );
    await waitFor(() =>
      expect(
        screen.queryByText("Startup IO amplification"),
      ).not.toBeInTheDocument(),
    );
  });

  test("empty state when no findings", async () => {
    api.getAdviceFindings.mockResolvedValueOnce({ findings: [] });
    render(<AdvicePanel canWrite={true} />);
    expect(await screen.findByText(/No advice findings/i)).toBeInTheDocument();
  });

  test("renders detector coverage banner when Hubble is unavailable and gates detectors", async () => {
    // 7 detectors total: 4 non-Hubble + 3 Hubble-required, all enabled.
    // Hubble unavailable -> activeEnabled=4, gatedCount=3.
    api.getAdviceDetectors.mockResolvedValueOnce({
      detectors: [
        { id: "a", enabled: true, requires_hubble: false },
        { id: "b", enabled: true, requires_hubble: false },
        { id: "c", enabled: true, requires_hubble: false },
        { id: "d", enabled: true, requires_hubble: false },
        { id: "e", enabled: true, requires_hubble: true },
        { id: "f", enabled: true, requires_hubble: true },
        { id: "g", enabled: true, requires_hubble: true },
      ],
      hubble_status: { available: false, reason: "not configured", flow_count: 0 },
    });
    render(<AdvicePanel canWrite={true} />);
    const banner = await screen.findByTestId(
      "advice-detector-coverage-banner",
    );
    expect(banner).toHaveTextContent(/4 of 7 detectors active/);
    expect(banner).toHaveTextContent(/3 network-flow detectors/);
  });

  test("does not render coverage banner when Hubble is available", async () => {
    api.getAdviceDetectors.mockResolvedValueOnce({
      detectors: [
        { id: "a", enabled: true, requires_hubble: false },
        { id: "b", enabled: true, requires_hubble: true },
      ],
      hubble_status: { available: true, reason: "ok", flow_count: 5 },
    });
    render(<AdvicePanel canWrite={true} />);
    // Wait for the findings to load so we know the panel has settled.
    await screen.findByText("Startup IO amplification");
    expect(
      screen.queryByTestId("advice-detector-coverage-banner"),
    ).not.toBeInTheDocument();
  });

  test("hasCompletedScan resets when scope changes", async () => {
    // Start with no findings so the empty state renders.
    api.getAdviceFindings.mockResolvedValue({ findings: [] });
    // The run-scan response sets hasCompletedScan=true synchronously.
    api.runAdviceScan.mockResolvedValueOnce({ findings: [], scan_id: "s1" });

    render(<AdvicePanel canWrite={true} />);
    // Initial empty state — never scanned.
    expect(
      await screen.findByText(
        /Run a scan to surface scaling, startup, and capacity advice/i,
      ),
    ).toBeInTheDocument();

    // Run a scan; after it resolves we should see the "looks healthy" copy.
    fireEvent.click(screen.getByRole("button", { name: /Run scan/i }));
    await waitFor(() => expect(api.runAdviceScan).toHaveBeenCalled());
    expect(
      await screen.findByText(/No improvements suggested/i),
    ).toBeInTheDocument();

    // Change scope: pick a namespace. This must reset the completed-scan
    // flag and bring back the "Run a scan to surface…" prompt.
    const nsSelect = document.getElementById("advice-scope-namespace");
    expect(nsSelect).toBeTruthy();
    fireEvent.change(nsSelect, { target: { value: "data" } });

    await waitFor(() =>
      expect(
        screen.getByText(
          /Run a scan to surface scaling, startup, and capacity advice/i,
        ),
      ).toBeInTheDocument(),
    );
    expect(
      screen.queryByText(/No improvements suggested/i),
    ).not.toBeInTheDocument();
  });

  test("does not render coverage banner when no detectors are gated", async () => {
    // All enabled detectors are non-Hubble; gatedCount === 0 even though
    // Hubble is unavailable.
    api.getAdviceDetectors.mockResolvedValueOnce({
      detectors: [
        { id: "a", enabled: true, requires_hubble: false },
        { id: "b", enabled: true, requires_hubble: false },
      ],
      hubble_status: { available: false, reason: "not configured", flow_count: 0 },
    });
    render(<AdvicePanel canWrite={true} />);
    await screen.findByText("Startup IO amplification");
    expect(
      screen.queryByTestId("advice-detector-coverage-banner"),
    ).not.toBeInTheDocument();
  });
});
