import React from "react";
import {
  render,
  screen,
  fireEvent,
  waitFor,
} from "@testing-library/react";
import AdviceFindingCard from "../AdviceFindingCard";
import { api } from "../../services/api";

jest.mock("../../services/api", () => ({
  api: {
    explainAdviceFinding: jest.fn(),
  },
}));

const baseFinding = {
  id: 42,
  detector_id: "deployment-hpa-burst-mismatch",
  severity: "medium",
  category: "scaling",
  title: "HPA burst mismatch",
  summary: "Replica burst exceeds HPA maxReplicas.",
  resource_kind: "Deployment",
  resource_name: "api",
  namespace: "ns-foo",
  evidence: { current_replicas: 3, max_replicas: 4 },
  recommended_change: "Increase HPA maxReplicas to at least 8.",
  confidence: 0.9,
  explanation: "## Why this matters\nBurst load exceeds capacity.",
  dismissed: false,
};

describe("AdviceFindingCard", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test("renders core header fields when collapsed", () => {
    render(<AdviceFindingCard finding={baseFinding} />);
    expect(screen.getByText("HPA burst mismatch")).toBeInTheDocument();
    expect(
      screen.getByText("deployment-hpa-burst-mismatch"),
    ).toBeInTheDocument();
    expect(screen.getByText("MEDIUM")).toBeInTheDocument();
    expect(screen.getByText(/Deployment\/api/)).toBeInTheDocument();
    expect(screen.getByText(/ns-foo/)).toBeInTheDocument();
    expect(screen.getByText(/confidence: 90%/i)).toBeInTheDocument();
  });

  test("is collapsed by default — summary, recommended_change, and explanation are hidden", () => {
    render(<AdviceFindingCard finding={baseFinding} />);
    expect(
      screen.queryByText("Replica burst exceeds HPA maxReplicas."),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText("Increase HPA maxReplicas to at least 8."),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/Explanation/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Show evidence/i)).not.toBeInTheDocument();
  });

  test("expand button toggles aria-expanded and reveals details", () => {
    render(<AdviceFindingCard finding={baseFinding} />);
    const header = screen.getByRole("button", { expanded: false });
    fireEvent.click(header);
    expect(header).toHaveAttribute("aria-expanded", "true");
    expect(
      screen.getByText("Replica burst exceeds HPA maxReplicas."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Increase HPA maxReplicas to at least 8."),
    ).toBeInTheDocument();
  });

  test("evidence stays hidden until its own toggle is clicked after expanding", () => {
    render(<AdviceFindingCard finding={baseFinding} />);
    fireEvent.click(screen.getByRole("button", { expanded: false }));
    expect(screen.queryByTestId("advice-evidence")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText(/Show evidence/i));
    const ev = screen.getByTestId("advice-evidence");
    expect(ev).toBeInTheDocument();
    expect(ev.textContent).toContain("current_replicas");
  });

  test("shows fallback when explanation is null AFTER expanding (collapsed cards never show the slot)", async () => {
    api.explainAdviceFinding.mockResolvedValue({
      ...baseFinding,
      explanation: null,
    });
    render(
      <AdviceFindingCard finding={{ ...baseFinding, explanation: null }} />,
    );
    expect(
      screen.queryByText(/No explanation generated for this finding/i),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { expanded: false }));
    await waitFor(() =>
      expect(
        screen.getByText(/No explanation generated for this finding/i),
      ).toBeInTheDocument(),
    );
  });

  test("first expand with null explanation triggers explainAdviceFinding and renders the result", async () => {
    api.explainAdviceFinding.mockResolvedValue({
      ...baseFinding,
      explanation: "## Why this matters\nLazy fetched content.",
    });
    render(
      <AdviceFindingCard finding={{ ...baseFinding, explanation: null }} />,
    );
    fireEvent.click(screen.getByRole("button", { expanded: false }));
    // Loading spinner is visible immediately.
    expect(
      screen.getByTestId("advice-explanation-loading"),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(api.explainAdviceFinding).toHaveBeenCalledWith(42),
    );
    await waitFor(() =>
      expect(screen.getByText(/Lazy fetched content/)).toBeInTheDocument(),
    );
  });

  test("first expand with an existing explanation does NOT call explainAdviceFinding", () => {
    render(<AdviceFindingCard finding={baseFinding} />);
    fireEvent.click(screen.getByRole("button", { expanded: false }));
    expect(api.explainAdviceFinding).not.toHaveBeenCalled();
    expect(screen.getByText(/Burst load exceeds capacity/i)).toBeInTheDocument();
  });

  test("collapse then re-expand does NOT re-call the API", async () => {
    api.explainAdviceFinding.mockResolvedValue({
      ...baseFinding,
      explanation: "## fetched\nonce",
    });
    render(
      <AdviceFindingCard finding={{ ...baseFinding, explanation: null }} />,
    );
    const header = screen.getByRole("button", { expanded: false });
    fireEvent.click(header);
    await waitFor(() =>
      expect(api.explainAdviceFinding).toHaveBeenCalledTimes(1),
    );
    fireEvent.click(header); // collapse
    fireEvent.click(header); // re-expand
    expect(api.explainAdviceFinding).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/fetched/i)).toBeInTheDocument();
  });

  test("explain API failure falls back to the no-explanation copy without crashing", async () => {
    // Silence the expected console.error in the test output.
    const errSpy = jest.spyOn(console, "error").mockImplementation(() => {});
    api.explainAdviceFinding.mockRejectedValue(new Error("boom"));
    render(
      <AdviceFindingCard finding={{ ...baseFinding, explanation: null }} />,
    );
    fireEvent.click(screen.getByRole("button", { expanded: false }));
    await waitFor(() =>
      expect(api.explainAdviceFinding).toHaveBeenCalled(),
    );
    await waitFor(() =>
      expect(
        screen.getByText(/No explanation generated for this finding/i),
      ).toBeInTheDocument(),
    );
    errSpy.mockRestore();
  });

  test("onExplained is called with the updated finding after lazy fetch", async () => {
    const updated = { ...baseFinding, explanation: "## new" };
    api.explainAdviceFinding.mockResolvedValue(updated);
    const onExplained = jest.fn();
    render(
      <AdviceFindingCard
        finding={{ ...baseFinding, explanation: null }}
        onExplained={onExplained}
      />,
    );
    fireEvent.click(screen.getByRole("button", { expanded: false }));
    await waitFor(() => expect(onExplained).toHaveBeenCalledWith(updated));
  });

  test("dismiss button calls onDismiss when canWrite (after expanding)", () => {
    const onDismiss = jest.fn().mockResolvedValue();
    render(
      <AdviceFindingCard
        finding={baseFinding}
        canWrite={true}
        onDismiss={onDismiss}
      />,
    );
    fireEvent.click(screen.getByRole("button", { expanded: false }));
    fireEvent.click(screen.getByRole("button", { name: /Dismiss/i }));
    expect(onDismiss).toHaveBeenCalledWith(baseFinding);
  });

  test("hides dismiss button when canWrite is false", () => {
    render(
      <AdviceFindingCard
        finding={baseFinding}
        canWrite={false}
        onDismiss={() => {}}
      />,
    );
    fireEvent.click(screen.getByRole("button", { expanded: false }));
    expect(
      screen.queryByRole("button", { name: /Dismiss/i }),
    ).not.toBeInTheDocument();
  });

  test("shows restore button when finding is dismissed (after expanding)", () => {
    const onRestore = jest.fn().mockResolvedValue();
    render(
      <AdviceFindingCard
        finding={{ ...baseFinding, dismissed: true }}
        canWrite={true}
        onRestore={onRestore}
      />,
    );
    // "Dismissed" pill is visible in the collapsed header.
    expect(screen.getByText(/Dismissed/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { expanded: false }));
    fireEvent.click(screen.getByRole("button", { name: /Restore/i }));
    expect(onRestore).toHaveBeenCalled();
  });
});
