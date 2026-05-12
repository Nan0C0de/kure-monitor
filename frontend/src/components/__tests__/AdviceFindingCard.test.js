import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import AdviceFindingCard from "../AdviceFindingCard";

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
  test("renders core finding fields", () => {
    render(<AdviceFindingCard finding={baseFinding} />);
    expect(screen.getByText("HPA burst mismatch")).toBeInTheDocument();
    expect(
      screen.getByText("deployment-hpa-burst-mismatch"),
    ).toBeInTheDocument();
    expect(screen.getByText("MEDIUM")).toBeInTheDocument();
    expect(screen.getByText(/Deployment\/api/)).toBeInTheDocument();
    expect(screen.getByText(/ns-foo/)).toBeInTheDocument();
    expect(screen.getByText(/confidence: 90%/i)).toBeInTheDocument();
    expect(
      screen.getByText("Increase HPA maxReplicas to at least 8."),
    ).toBeInTheDocument();
  });

  test("evidence is hidden by default and revealed on click", () => {
    render(<AdviceFindingCard finding={baseFinding} />);
    expect(screen.queryByTestId("advice-evidence")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText(/Show evidence/i));
    const ev = screen.getByTestId("advice-evidence");
    expect(ev).toBeInTheDocument();
    expect(ev.textContent).toContain("current_replicas");
  });

  test("shows fallback when explanation is null", () => {
    render(
      <AdviceFindingCard finding={{ ...baseFinding, explanation: null }} />,
    );
    expect(screen.getByText(/No LLM explanation/i)).toBeInTheDocument();
  });

  test("dismiss button calls onDismiss when canWrite", () => {
    const onDismiss = jest.fn().mockResolvedValue();
    render(
      <AdviceFindingCard
        finding={baseFinding}
        canWrite={true}
        onDismiss={onDismiss}
      />,
    );
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
    expect(
      screen.queryByRole("button", { name: /Dismiss/i }),
    ).not.toBeInTheDocument();
  });

  test("shows restore button when finding is dismissed", () => {
    const onRestore = jest.fn().mockResolvedValue();
    render(
      <AdviceFindingCard
        finding={{ ...baseFinding, dismissed: true }}
        canWrite={true}
        onRestore={onRestore}
      />,
    );
    expect(screen.getByText(/Dismissed/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Restore/i }));
    expect(onRestore).toHaveBeenCalled();
  });
});
