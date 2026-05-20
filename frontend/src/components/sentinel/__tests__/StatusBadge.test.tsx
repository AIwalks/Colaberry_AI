import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { GovernanceStatusBadge, RiskLevelBadge, ConfidenceBar } from "../StatusBadge";

describe("GovernanceStatusBadge", () => {
  it("renders pending status", () => {
    render(<GovernanceStatusBadge status="pending" />);
    expect(screen.getByTestId("status-badge-pending")).toBeInTheDocument();
    expect(screen.getByTestId("status-badge-pending")).toHaveTextContent("pending");
  });

  it("renders approved status", () => {
    render(<GovernanceStatusBadge status="approved" />);
    expect(screen.getByTestId("status-badge-approved")).toBeInTheDocument();
    expect(screen.getByTestId("status-badge-approved")).toHaveTextContent("approved");
  });

  it("renders rejected status", () => {
    render(<GovernanceStatusBadge status="rejected" />);
    expect(screen.getByTestId("status-badge-rejected")).toHaveTextContent("rejected");
  });

  it("renders deferred status", () => {
    render(<GovernanceStatusBadge status="deferred" />);
    expect(screen.getByTestId("status-badge-deferred")).toHaveTextContent("deferred");
  });
});

describe("RiskLevelBadge", () => {
  it.each(["low", "medium", "high", "critical", "unknown"] as const)(
    "renders %s risk level",
    (level) => {
      render(<RiskLevelBadge level={level} />);
      expect(screen.getByTestId(`risk-badge-${level}`)).toHaveTextContent(level);
    }
  );
});

describe("ConfidenceBar", () => {
  it("renders without error", () => {
    const { container } = render(<ConfidenceBar value={0.85} />);
    expect(container.firstChild).not.toBeNull();
  });

  it("shows 85% for value 0.85", () => {
    render(<ConfidenceBar value={0.85} />);
    expect(screen.getByText("85%")).toBeInTheDocument();
  });

  it("shows 0% for value 0", () => {
    render(<ConfidenceBar value={0} />);
    expect(screen.getByText("0%")).toBeInTheDocument();
  });

  it("shows 100% for value 1", () => {
    render(<ConfidenceBar value={1} />);
    expect(screen.getByText("100%")).toBeInTheDocument();
  });
});
