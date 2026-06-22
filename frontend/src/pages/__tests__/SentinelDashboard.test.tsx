import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// ---------------------------------------------------------------------------
// Mock all data hooks — tests should not make HTTP calls
// ---------------------------------------------------------------------------

vi.mock("../../hooks/useSentinelData", () => ({
  useGovernanceReviews:     vi.fn(),
  usePendingReviews:        vi.fn(),
  useLatestInterpretation:  vi.fn(),
  useInterpretationHistory: vi.fn(),
  useReuseMetrics:          vi.fn(),
  useStudentList:           vi.fn(),
  useGovernanceAction:      vi.fn(),
  useStudentResponses:      vi.fn(),
  useKpiSummary:            vi.fn(),
}));

import {
  useGovernanceReviews,
  useLatestInterpretation,
  useInterpretationHistory,
  useReuseMetrics,
  useStudentList,
  useGovernanceAction,
  useStudentResponses,
  useKpiSummary,
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
        total_interpretations:       0,
        active_interpretations:      0,
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
  vi.mocked(useStudentList).mockReturnValue({
    state:  { status: "success", data: { students: [], total: 0, source: "mock" } },
    reload: noopReload,
  });
  vi.mocked(useGovernanceAction).mockReturnValue({
    state:   { status: "idle" },
    execute: vi.fn().mockResolvedValue(true),
    reset:   vi.fn(),
  });
  vi.mocked(useStudentResponses).mockReturnValue({
    state:  { status: "success", data: { responses: [], total: 0, source: "mock" } },
    reload: noopReload,
  });
  vi.mocked(useKpiSummary).mockReturnValue({
    state: {
      status: "success",
      data: { pending_reviews: 3, approved_reviews: 2, student_responses: 4, suppressed_retriggers: 2, source: "mock" },
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
    expect(screen.getByText(/Governed shadow mode/)).toBeInTheDocument();
  });

  it("renders all six navigation tabs", () => {
    render(<SentinelDashboard />);
    // Use role-based queries for tabs (buttons) to avoid matching KPI tile labels
    const buttons = screen.getAllByRole("button");
    const tabLabels = buttons.map((b) => b.textContent ?? "");
    const hasTab = (label: string) => tabLabels.some((t) => t.includes(label));
    expect(hasTab("Governance Queue")).toBe(true);
    expect(hasTab("Interpretation Timeline")).toBe(true);
    expect(hasTab("Reuse & Metrics")).toBe(true);
    expect(hasTab("Student Detail")).toBe(true);
    expect(hasTab("Risk Evolution")).toBe(true);
    expect(hasTab("Student Responses")).toBe(true);
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

  it("renders the KPI strip", () => {
    render(<SentinelDashboard />);
    expect(screen.getByTestId("kpi-strip")).toBeInTheDocument();
  });

  it("shows Student Responses tab in navigation", () => {
    render(<SentinelDashboard />);
    const buttons = screen.getAllByRole("button");
    const tabBtn = buttons.find((b) => b.textContent?.includes("Student Responses"));
    expect(tabBtn).toBeDefined();
  });

  it("shows student picker when Student Responses tab is active", async () => {
    render(<SentinelDashboard />);
    const buttons = screen.getAllByRole("button");
    const tabBtn = buttons.find((b) => b.textContent?.includes("Student Responses") && b.textContent?.includes("💬"))!;
    await userEvent.click(tabBtn);
    expect(screen.getByLabelText(/Student/i)).toBeInTheDocument();
  });

  it("renders StudentResponsesPanel content when responses tab is active", async () => {
    vi.mocked(useStudentResponses).mockReturnValue({
      state: {
        status: "success",
        data: { responses: [], total: 0, source: "mock" },
      },
      reload: noopReload,
    });
    render(<SentinelDashboard />);
    const buttons = screen.getAllByRole("button");
    const tabBtn = buttons.find((b) => b.textContent?.includes("Student Responses") && b.textContent?.includes("💬"))!;
    await userEvent.click(tabBtn);
    expect(screen.getByTestId("empty-state")).toBeInTheDocument();
  });
});
