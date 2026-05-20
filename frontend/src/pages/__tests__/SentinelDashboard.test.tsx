import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// ---------------------------------------------------------------------------
// Mock all data hooks — tests should not make HTTP calls
// ---------------------------------------------------------------------------

vi.mock("../../hooks/useSentinelData", () => ({
  useGovernanceReviews:      vi.fn(),
  usePendingReviews:         vi.fn(),
  useLatestInterpretation:   vi.fn(),
  useInterpretationHistory:  vi.fn(),
  useReuseMetrics:           vi.fn(),
}));

import {
  useGovernanceReviews,
  useLatestInterpretation,
  useInterpretationHistory,
  useReuseMetrics,
} from "../../hooks/useSentinelData";
import { SentinelDashboard } from "../SentinelDashboard";

const noopReload = vi.fn();

function setupAllMocks() {
  vi.mocked(useGovernanceReviews).mockReturnValue({
    state:  { status: "success", data: { reviews: [], total: 0, source: "mock" } },
    reload: noopReload,
  });
  vi.mocked(useLatestInterpretation).mockReturnValue({
    state:  { status: "success", data: { entity_id: "student_101", latest: null, source: "mock" } },
    reload: noopReload,
  });
  vi.mocked(useInterpretationHistory).mockReturnValue({
    state:  { status: "success", data: { entity_id: "student_101", history: [], total: 0, source: "mock" } },
    reload: noopReload,
  });
  vi.mocked(useReuseMetrics).mockReturnValue({
    state: {
      status: "success",
      data: {
        total_interpretations: 0,
        active_interpretations: 0,
        invalidated_interpretations: 0,
        by_risk_level:   { low: 0, medium: 0, high: 0, critical: 0, unknown: 0 },
        by_generated_by: { claude: 0, fallback: 0, deterministic_engine: 0 },
        governance_summary: { pending: 0, approved: 0, rejected: 0, deferred: 0, total: 0 },
        note:   "Test",
        source: "mock",
      },
    },
    reload: noopReload,
  });
}

describe("SentinelDashboard", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    setupAllMocks();
  });

  it("renders the page heading", () => {
    render(<SentinelDashboard />);
    expect(screen.getByText("Sentinel Dashboard")).toBeInTheDocument();
  });

  it("renders SHADOW MODE badge", () => {
    render(<SentinelDashboard />);
    expect(screen.getByText("SHADOW MODE")).toBeInTheDocument();
  });

  it("renders the observability banner", () => {
    render(<SentinelDashboard />);
    expect(screen.getByText(/Shadow-mode observation only/)).toBeInTheDocument();
  });

  it("renders all five navigation tabs", () => {
    render(<SentinelDashboard />);
    expect(screen.getByText(/Governance Queue/)).toBeInTheDocument();
    expect(screen.getByText(/Interpretation Timeline/)).toBeInTheDocument();
    expect(screen.getByText(/Reuse & Metrics/)).toBeInTheDocument();
    expect(screen.getByText(/Student Detail/)).toBeInTheDocument();
    expect(screen.getByText(/Risk Evolution/)).toBeInTheDocument();
  });

  it("shows Governance Queue section by default", () => {
    render(<SentinelDashboard />);
    expect(screen.getByText("Governance Review Queue")).toBeInTheDocument();
  });

  it("switches to Metrics tab on click", async () => {
    render(<SentinelDashboard />);
    await userEvent.click(screen.getByText(/Reuse & Metrics/));
    expect(screen.getByText("Reuse & Regeneration Metrics")).toBeInTheDocument();
  });

  it("shows student picker when Timeline tab is active", async () => {
    render(<SentinelDashboard />);
    await userEvent.click(screen.getByText(/Interpretation Timeline/));
    expect(screen.getByLabelText(/Student/i)).toBeInTheDocument();
  });

  it("shows student picker when Student Detail tab is active", async () => {
    render(<SentinelDashboard />);
    await userEvent.click(screen.getByText(/Student Detail/));
    expect(screen.getByLabelText(/Student/i)).toBeInTheDocument();
  });

  it("shows student picker when Risk Evolution tab is active", async () => {
    render(<SentinelDashboard />);
    await userEvent.click(screen.getByText(/Risk Evolution/));
    expect(screen.getByLabelText(/Student/i)).toBeInTheDocument();
  });

  it("does not show student picker on Governance tab", () => {
    render(<SentinelDashboard />);
    expect(screen.queryByLabelText(/Student/i)).toBeNull();
  });

  it("renders empty state for governance queue when reviews list is empty", () => {
    render(<SentinelDashboard />);
    expect(screen.getByTestId("empty-state")).toBeInTheDocument();
  });

  it("renders loading state when governance is loading", () => {
    vi.mocked(useGovernanceReviews).mockReturnValue({
      state:  { status: "loading" },
      reload: noopReload,
    });
    render(<SentinelDashboard />);
    expect(screen.getByTestId("loading-state")).toBeInTheDocument();
  });
});
