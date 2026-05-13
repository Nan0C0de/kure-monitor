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

  test("loads and renders findings after a namespace is picked", async () => {
    render(<AdvicePanel canWrite={true} />);
    // No fetch on mount — panel waits for a namespace.
    await waitFor(() =>
      expect(
        screen.getByTestId("advice-select-namespace-empty"),
      ).toBeInTheDocument(),
    );
    expect(api.getAdviceFindings).not.toHaveBeenCalled();

    const nsSelect = await waitFor(() => {
      const el = document.getElementById("advice-scope-namespace");
      if (!el) throw new Error("namespace select not ready");
      // Wait until the namespace options have actually rendered — without
      // this, `fireEvent.change` to a value not yet present in the <option>
      // list is silently ignored by the DOM and the test wedges.
      if (!el.querySelector('option[value="data"]')) {
        throw new Error("namespace options not yet loaded");
      }
      return el;
    });
    fireEvent.change(nsSelect, { target: { value: "data" } });
    await waitFor(() =>
      expect(api.getAdviceFindings).toHaveBeenCalledWith({ namespace: "data" }),
    );
    expect(
      await screen.findByText("Startup IO amplification"),
    ).toBeInTheDocument();
  });

  test("toggling show-dismissed re-fetches with include_dismissed", async () => {
    render(<AdvicePanel canWrite={true} />);
    // Pick a namespace first so the panel actually fetches.
    const nsSelect = await waitFor(() => {
      const el = document.getElementById("advice-scope-namespace");
      if (!el) throw new Error("namespace select not ready");
      // Wait until the namespace options have actually rendered — without
      // this, `fireEvent.change` to a value not yet present in the <option>
      // list is silently ignored by the DOM and the test wedges.
      if (!el.querySelector('option[value="data"]')) {
        throw new Error("namespace options not yet loaded");
      }
      return el;
    });
    fireEvent.change(nsSelect, { target: { value: "data" } });
    await waitFor(() =>
      expect(api.getAdviceFindings).toHaveBeenCalledWith({ namespace: "data" }),
    );
    fireEvent.click(screen.getByLabelText(/Show dismissed/i));
    await waitFor(() =>
      expect(api.getAdviceFindings).toHaveBeenCalledWith({
        include_dismissed: true,
        namespace: "data",
      }),
    );
  });

  test("Run scan button posts to runAdviceScan", async () => {
    render(<AdvicePanel canWrite={true} />);
    // Picking a namespace alone now auto-scans; wait for that first call,
    // then narrow the scope to a workload kind (which suppresses auto-scan)
    // and assert the explicit button click triggers a second call with the
    // narrower scope.
    const nsSelect = await waitFor(() => {
      const el = document.getElementById("advice-scope-namespace");
      if (!el) throw new Error("namespace select not ready");
      // Wait until the namespace options have actually rendered — without
      // this, `fireEvent.change` to a value not yet present in the <option>
      // list is silently ignored by the DOM and the test wedges.
      if (!el.querySelector('option[value="data"]')) {
        throw new Error("namespace options not yet loaded");
      }
      return el;
    });
    fireEvent.change(nsSelect, { target: { value: "data" } });
    await waitFor(() =>
      expect(api.runAdviceScan).toHaveBeenCalledWith(
        expect.objectContaining({ namespace: "data" }),
      ),
    );
    expect(api.runAdviceScan).toHaveBeenCalledTimes(1);

    const kindSelect = document.getElementById("advice-scope-kind");
    fireEvent.change(kindSelect, { target: { value: "Deployment" } });
    // Picking a workload kind must NOT auto-scan.
    expect(api.runAdviceScan).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: /Run scan/i }));
    await waitFor(() =>
      expect(api.runAdviceScan).toHaveBeenCalledWith(
        expect.objectContaining({
          namespace: "data",
          workload_kind: "Deployment",
        }),
      ),
    );
    expect(api.runAdviceScan).toHaveBeenCalledTimes(2);
  });

  test("auto-scans when a namespace is picked with no workload", async () => {
    render(<AdvicePanel canWrite={true} />);
    await waitFor(() =>
      expect(
        screen.getByTestId("advice-select-namespace-empty"),
      ).toBeInTheDocument(),
    );
    expect(api.runAdviceScan).not.toHaveBeenCalled();

    const nsSelect = await waitFor(() => {
      const el = document.getElementById("advice-scope-namespace");
      if (!el) throw new Error("namespace select not ready");
      // Wait until the namespace options have actually rendered — without
      // this, `fireEvent.change` to a value not yet present in the <option>
      // list is silently ignored by the DOM and the test wedges.
      if (!el.querySelector('option[value="data"]')) {
        throw new Error("namespace options not yet loaded");
      }
      return el;
    });
    fireEvent.change(nsSelect, { target: { value: "data" } });

    await waitFor(() =>
      expect(api.runAdviceScan).toHaveBeenCalledWith(
        expect.objectContaining({ namespace: "data" }),
      ),
    );
  });

  test("does not auto-scan when a workload is picked", async () => {
    render(<AdvicePanel canWrite={true} />);

    // Pick a namespace — auto-scan fires once.
    const nsSelect = await waitFor(() => {
      const el = document.getElementById("advice-scope-namespace");
      if (!el) throw new Error("namespace select not ready");
      // Wait until the namespace options have actually rendered — without
      // this, `fireEvent.change` to a value not yet present in the <option>
      // list is silently ignored by the DOM and the test wedges.
      if (!el.querySelector('option[value="data"]')) {
        throw new Error("namespace options not yet loaded");
      }
      return el;
    });
    fireEvent.change(nsSelect, { target: { value: "data" } });
    await waitFor(() => expect(api.runAdviceScan).toHaveBeenCalledTimes(1));

    // Narrow to a workload kind — must NOT trigger a second auto-scan.
    const kindSelect = document.getElementById("advice-scope-kind");
    fireEvent.change(kindSelect, { target: { value: "Deployment" } });

    // Give any pending microtasks a chance to flush.
    await Promise.resolve();
    await Promise.resolve();
    expect(api.runAdviceScan).toHaveBeenCalledTimes(1);

    // Now an explicit button click must fire the scan.
    fireEvent.click(screen.getByRole("button", { name: /Run scan/i }));
    await waitFor(() => expect(api.runAdviceScan).toHaveBeenCalledTimes(2));
  });

  test("auto-scans again when namespace changes with no workload selected", async () => {
    render(<AdvicePanel canWrite={true} />);

    const nsSelect = await waitFor(() => {
      const el = document.getElementById("advice-scope-namespace");
      if (!el) throw new Error("namespace select not ready");
      // Wait until the namespace options have actually rendered — without
      // this, `fireEvent.change` to a value not yet present in the <option>
      // list is silently ignored by the DOM and the test wedges.
      if (!el.querySelector('option[value="data"]')) {
        throw new Error("namespace options not yet loaded");
      }
      return el;
    });
    fireEvent.change(nsSelect, { target: { value: "data" } });
    await waitFor(() =>
      expect(api.runAdviceScan).toHaveBeenCalledWith(
        expect.objectContaining({ namespace: "data" }),
      ),
    );

    fireEvent.change(nsSelect, { target: { value: "web" } });
    await waitFor(() =>
      expect(api.runAdviceScan).toHaveBeenCalledWith(
        expect.objectContaining({ namespace: "web" }),
      ),
    );
  });

  test("Run scan button is disabled until a namespace is picked", async () => {
    render(<AdvicePanel canWrite={true} />);
    const btn = await screen.findByRole("button", { name: /Run scan/i });
    expect(btn).toBeDisabled();
    expect(screen.getByTestId("advice-run-scan-hint")).toHaveTextContent(
      /Pick a namespace to run a scan/i,
    );
    // Clicking the disabled button must not call the API.
    fireEvent.click(btn);
    expect(api.runAdviceScan).not.toHaveBeenCalled();

    const nsSelect = await waitFor(() => {
      const el = document.getElementById("advice-scope-namespace");
      if (!el) throw new Error("namespace select not ready");
      // Wait until the namespace options have actually rendered — without
      // this, `fireEvent.change` to a value not yet present in the <option>
      // list is silently ignored by the DOM and the test wedges.
      if (!el.querySelector('option[value="data"]')) {
        throw new Error("namespace options not yet loaded");
      }
      return el;
    });
    fireEvent.change(nsSelect, { target: { value: "data" } });
    await waitFor(() => expect(btn).not.toBeDisabled());
  });

  test("Run scan button hidden when canWrite is false", async () => {
    render(<AdvicePanel canWrite={false} />);
    // The panel renders the select-a-namespace empty state; Run scan should
    // not appear at all (no canWrite).
    await waitFor(() =>
      expect(
        screen.getByTestId("advice-select-namespace-empty"),
      ).toBeInTheDocument(),
    );
    expect(
      screen.queryByRole("button", { name: /Run scan/i }),
    ).not.toBeInTheDocument();
  });

  test("WS advice_scan_status started shows banner", async () => {
    const { rerender } = render(<AdvicePanel canWrite={true} wsEvent={null} />);
    // Pick a namespace so findings load.
    const nsSelect = await waitFor(() => {
      const el = document.getElementById("advice-scope-namespace");
      if (!el) throw new Error("namespace select not ready");
      // Wait until the namespace options have actually rendered — without
      // this, `fireEvent.change` to a value not yet present in the <option>
      // list is silently ignored by the DOM and the test wedges.
      if (!el.querySelector('option[value="data"]')) {
        throw new Error("namespace options not yet loaded");
      }
      return el;
    });
    fireEvent.change(nsSelect, { target: { value: "data" } });
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
    // Pick a namespace so findings load.
    const nsSelect = await waitFor(() => {
      const el = document.getElementById("advice-scope-namespace");
      if (!el) throw new Error("namespace select not ready");
      // Wait until the namespace options have actually rendered — without
      // this, `fireEvent.change` to a value not yet present in the <option>
      // list is silently ignored by the DOM and the test wedges.
      if (!el.querySelector('option[value="data"]')) {
        throw new Error("namespace options not yet loaded");
      }
      return el;
    });
    fireEvent.change(nsSelect, { target: { value: "data" } });
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
    api.getAdviceFindings.mockResolvedValue({ findings: [] });
    // Make the auto-scan a no-op so the panel stays in the pre-scan empty
    // state long enough to assert the "No advice findings" copy. Without
    // this, the auto-scan resolves synchronously, flips hasCompletedScan,
    // and the heading swaps to "No improvements suggested".
    api.runAdviceScan.mockImplementation(() => new Promise(() => {}));
    render(<AdvicePanel canWrite={true} />);
    const nsSelect = await waitFor(() => {
      const el = document.getElementById("advice-scope-namespace");
      if (!el) throw new Error("namespace select not ready");
      if (!el.querySelector('option[value="data"]')) {
        throw new Error("namespace options not yet loaded");
      }
      return el;
    });
    fireEvent.change(nsSelect, { target: { value: "data" } });
    expect(await screen.findByText(/No advice findings/i)).toBeInTheDocument();
  });

  test("no findings or fetch when namespace is unselected", async () => {
    render(<AdvicePanel canWrite={true} />);
    // Wait a tick so any potential mount-effect fetches would have fired.
    await Promise.resolve();
    await Promise.resolve();
    await waitFor(() =>
      expect(
        screen.getByTestId("advice-select-namespace-empty"),
      ).toBeInTheDocument(),
    );
    expect(api.getAdviceFindings).not.toHaveBeenCalled();
    expect(
      screen.getByText(/Select a namespace to view AI Advice findings/i),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("Startup IO amplification"),
    ).not.toBeInTheDocument();
  });

  test("clearing the namespace clears findings", async () => {
    render(<AdvicePanel canWrite={true} />);
    const nsSelect = await waitFor(() => {
      const el = document.getElementById("advice-scope-namespace");
      if (!el) throw new Error("namespace select not ready");
      // Wait until the namespace options have actually rendered — without
      // this, `fireEvent.change` to a value not yet present in the <option>
      // list is silently ignored by the DOM and the test wedges.
      if (!el.querySelector('option[value="data"]')) {
        throw new Error("namespace options not yet loaded");
      }
      return el;
    });
    fireEvent.change(nsSelect, { target: { value: "data" } });
    // Finding A renders once the namespace-scoped fetch resolves.
    expect(
      await screen.findByText("Startup IO amplification"),
    ).toBeInTheDocument();

    // Clear the namespace — empty-state copy comes back, finding is gone.
    fireEvent.change(nsSelect, { target: { value: "" } });
    await waitFor(() =>
      expect(
        screen.getByTestId("advice-select-namespace-empty"),
      ).toBeInTheDocument(),
    );
    expect(
      screen.queryByText("Startup IO amplification"),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText(/Select a namespace to view AI Advice findings/i),
    ).toBeInTheDocument();
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
      hubble_status: {
        available: false,
        reason: "not configured",
        flow_count: 0,
      },
    });
    render(<AdvicePanel canWrite={true} />);
    const banner = await screen.findByTestId("advice-detector-coverage-banner");
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
    // Wait for the panel to settle (empty-namespace state is fine here).
    await waitFor(() =>
      expect(
        screen.getByTestId("advice-select-namespace-empty"),
      ).toBeInTheDocument(),
    );
    expect(
      screen.queryByTestId("advice-detector-coverage-banner"),
    ).not.toBeInTheDocument();
  });

  test("hasCompletedScan resets when scope changes", async () => {
    // Start with no findings so the empty state renders.
    api.getAdviceFindings.mockResolvedValue({ findings: [] });
    api.runAdviceScan.mockResolvedValue({ findings: [], scan_id: "s1" });

    render(<AdvicePanel canWrite={true} />);
    // Initial empty state — no namespace selected yet.
    expect(
      await screen.findByTestId("advice-select-namespace-empty"),
    ).toBeInTheDocument();

    // Pick a namespace — this auto-scans; once it resolves we should see
    // the "looks healthy" copy.
    const nsSelect = document.getElementById("advice-scope-namespace");
    expect(nsSelect).toBeTruthy();
    fireEvent.change(nsSelect, { target: { value: "data" } });
    await waitFor(() => expect(api.runAdviceScan).toHaveBeenCalled());
    expect(
      await screen.findByText(/No improvements suggested/i),
    ).toBeInTheDocument();

    // Narrow scope: pick a workload kind. This must reset the
    // completed-scan flag and bring back the "Run a scan to surface…" prompt.
    // Picking a workload kind does NOT auto-scan (per the auto-scan rules),
    // so the reset is observable.
    const kindSelect = document.getElementById("advice-scope-kind");
    fireEvent.change(kindSelect, { target: { value: "Deployment" } });

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

  test("switching namespace refetches with the new scope and clears stale findings", async () => {
    const findingA = {
      ...sampleFinding,
      id: 10,
      namespace: "data",
      title: "Finding A",
    };
    const findingB = {
      ...sampleFinding,
      id: 20,
      namespace: "web",
      title: "Finding B",
    };
    // First scoped fetch (namespace=data) returns A.
    api.getAdviceFindings.mockResolvedValueOnce({ findings: [findingA] });
    // Second scoped fetch (namespace=web) returns B, NOT A.
    api.getAdviceFindings.mockResolvedValueOnce({ findings: [findingB] });

    render(<AdvicePanel canWrite={true} />);

    const nsSelect = await waitFor(() => {
      const el = document.getElementById("advice-scope-namespace");
      if (!el) throw new Error("namespace select not ready");
      // Wait until the namespace options have actually rendered — without
      // this, `fireEvent.change` to a value not yet present in the <option>
      // list is silently ignored by the DOM and the test wedges.
      if (!el.querySelector('option[value="data"]')) {
        throw new Error("namespace options not yet loaded");
      }
      return el;
    });
    fireEvent.change(nsSelect, { target: { value: "data" } });
    await waitFor(() =>
      expect(api.getAdviceFindings).toHaveBeenCalledWith({ namespace: "data" }),
    );
    expect(await screen.findByText("Finding A")).toBeInTheDocument();

    fireEvent.change(nsSelect, { target: { value: "web" } });
    await waitFor(() =>
      expect(api.getAdviceFindings).toHaveBeenCalledWith({ namespace: "web" }),
    );

    // The previous namespace's finding must be gone after the scope switch.
    await waitFor(() =>
      expect(screen.queryByText("Finding A")).not.toBeInTheDocument(),
    );
    expect(screen.getByText("Finding B")).toBeInTheDocument();
  });

  describe("infinite scroll / pagination", () => {
    const makeFindings = (count, namespace = "data") =>
      Array.from({ length: count }, (_, i) => ({
        ...sampleFinding,
        id: 1000 + i,
        namespace,
        title: `Finding ${namespace} ${i + 1}`,
      }));

    test("renders only the first 5 findings initially with a Showing X of Y footer", async () => {
      api.getAdviceFindings.mockResolvedValue({ findings: makeFindings(12) });
      render(<AdvicePanel canWrite={true} />);

      const nsSelect = await waitFor(() => {
        const el = document.getElementById("advice-scope-namespace");
        if (!el) throw new Error("namespace select not ready");
        if (!el.querySelector('option[value="data"]')) {
          throw new Error("namespace options not yet loaded");
        }
        return el;
      });
      fireEvent.change(nsSelect, { target: { value: "data" } });

      // Findings sort by severity then by id desc within same severity, so
      // "Finding data 12" (highest id) renders first and "Finding data 8" is
      // the 5th. "Finding data 7" and below are paginated out.
      expect(await screen.findByText("Finding data 12")).toBeInTheDocument();
      expect(screen.getByText("Finding data 8")).toBeInTheDocument();
      expect(screen.queryByText("Finding data 7")).not.toBeInTheDocument();
      expect(screen.queryByText("Finding data 1")).not.toBeInTheDocument();
      // Footer shows progress.
      expect(
        screen.getByTestId("advice-findings-pagination-footer"),
      ).toHaveTextContent(/Showing 5 of 12 findings/i);
    });

    test("clicking Load more reveals the next page until all findings are shown", async () => {
      api.getAdviceFindings.mockResolvedValue({ findings: makeFindings(12) });
      render(<AdvicePanel canWrite={true} />);

      const nsSelect = await waitFor(() => {
        const el = document.getElementById("advice-scope-namespace");
        if (!el) throw new Error("namespace select not ready");
        if (!el.querySelector('option[value="data"]')) {
          throw new Error("namespace options not yet loaded");
        }
        return el;
      });
      fireEvent.change(nsSelect, { target: { value: "data" } });

      // Initial state: 5 of 12 (highest ids 12..8 render first).
      await screen.findByText("Finding data 12");
      const footer = screen.getByTestId("advice-findings-pagination-footer");
      expect(footer).toHaveTextContent(/Showing 5 of 12 findings/i);

      // Click "Load more" — 10 of 12.
      // IntersectionObserver itself is annoying to test in jsdom (no real
      // scroll/layout) so we exercise the click fallback path here. The
      // observer code uses the same setVisibleCount updater, so this covers
      // the state transition.
      fireEvent.click(screen.getByRole("button", { name: /Load more/i }));
      await waitFor(() =>
        expect(
          screen.getByTestId("advice-findings-pagination-footer"),
        ).toHaveTextContent(/Showing 10 of 12 findings/i),
      );
      // After page 2 we see ids 12..3, so "Finding data 3" is visible but
      // "Finding data 2" is not yet.
      expect(screen.getByText("Finding data 3")).toBeInTheDocument();
      expect(screen.queryByText("Finding data 2")).not.toBeInTheDocument();

      // Click again — all 12.
      fireEvent.click(screen.getByRole("button", { name: /Load more/i }));
      await waitFor(() =>
        expect(
          screen.getByTestId("advice-findings-pagination-footer"),
        ).toHaveTextContent(/All 12 findings shown/i),
      );
      expect(screen.getByText("Finding data 1")).toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: /Load more/i }),
      ).not.toBeInTheDocument();
    });

    test("switching namespace resets visible count (no Showing 5 of 3)", async () => {
      // First scoped fetch: data with 12 findings.
      api.getAdviceFindings.mockResolvedValueOnce({
        findings: makeFindings(12, "data"),
      });
      // Second scoped fetch: web with 3 findings.
      api.getAdviceFindings.mockResolvedValueOnce({
        findings: makeFindings(3, "web"),
      });

      render(<AdvicePanel canWrite={true} />);

      const nsSelect = await waitFor(() => {
        const el = document.getElementById("advice-scope-namespace");
        if (!el) throw new Error("namespace select not ready");
        if (!el.querySelector('option[value="data"]')) {
          throw new Error("namespace options not yet loaded");
        }
        return el;
      });
      fireEvent.change(nsSelect, { target: { value: "data" } });
      await screen.findByText("Finding data 12");
      expect(
        screen.getByTestId("advice-findings-pagination-footer"),
      ).toHaveTextContent(/Showing 5 of 12 findings/i);

      // Switch to "web" — only 3 findings, so the footer should disappear
      // entirely (no "Showing 5 of 3" weirdness) and all three should render.
      fireEvent.change(nsSelect, { target: { value: "web" } });
      await screen.findByText("Finding web 3");
      expect(screen.getByText("Finding web 2")).toBeInTheDocument();
      expect(screen.getByText("Finding web 1")).toBeInTheDocument();
      expect(
        screen.queryByTestId("advice-findings-pagination-footer"),
      ).not.toBeInTheDocument();
      // The previous namespace's findings should be gone.
      expect(screen.queryByText("Finding data 12")).not.toBeInTheDocument();
    });
  });

  test("does not render coverage banner when no detectors are gated", async () => {
    // All enabled detectors are non-Hubble; gatedCount === 0 even though
    // Hubble is unavailable.
    api.getAdviceDetectors.mockResolvedValueOnce({
      detectors: [
        { id: "a", enabled: true, requires_hubble: false },
        { id: "b", enabled: true, requires_hubble: false },
      ],
      hubble_status: {
        available: false,
        reason: "not configured",
        flow_count: 0,
      },
    });
    render(<AdvicePanel canWrite={true} />);
    await waitFor(() =>
      expect(
        screen.getByTestId("advice-select-namespace-empty"),
      ).toBeInTheDocument(),
    );
    expect(
      screen.queryByTestId("advice-detector-coverage-banner"),
    ).not.toBeInTheDocument();
  });
});
