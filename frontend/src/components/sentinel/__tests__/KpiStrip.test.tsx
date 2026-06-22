import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// ---------------------------------------------------------------------------
// Mock the hook — tests must not make HTTP calls
// ---------------------------------------------------------------------------

vi.mock("../../../hooks/useSentinelData", () => ({
  useKpiSummary: vi.fn(),
}));

import { useKpiSummary } from "../../../hooks/useSentinelData";
import { KpiStrip } from "../KpiStrip";

const noopReload = vi.fn();

function mockSuccess(overrides: Partial<{
  pending_reviews: number;
  approved_reviews: number;
  student_responses: number;
  suppressed_retriggers: number;
}> = {}) {
  vi.mocked(useKpiSummary).mockReturnValue({
    state: {
      status: "success",
      data: {
        pending_reviews:       3,
        approved_reviews:      2,
        student_responses:     4,
        suppressed_retriggers: 2,
        source: "mock",
        ...overrides,
      },
    },
    reload: noopReload,
  });
}

describe("KpiStrip", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    noopReload.mockReset();
  });

  // -------------------------------------------------------------------------
  // Structure
  // -------------------------------------------------------------------------

  it("renders the kpi-strip container", () => {
    mockSuccess();
    render(<KpiStrip />);
    expect(screen.getByTestId("kpi-strip")).toBeInTheDocument();
  });

  it("renders all four KPI tiles", () => {
    mockSuccess();
    render(<KpiStrip />);
    expect(screen.getByTestId("kpi-pending-reviews")).toBeInTheDocument();
    expect(screen.getByTestId("kpi-approved-reviews")).toBeInTheDocument();
    expect(screen.getByTestId("kpi-student-responses")).toBeInTheDocument();
    expect(screen.getByTestId("kpi-suppressed-retriggers")).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Values
  // -------------------------------------------------------------------------

  it("displays pending reviews count", () => {
    mockSuccess({ pending_reviews: 3 });
    render(<KpiStrip />);
    expect(screen.getByTestId("kpi-pending-reviews-value")).toHaveTextContent("3");
  });

  it("displays approved reviews count", () => {
    mockSuccess({ approved_reviews: 2 });
    render(<KpiStrip />);
    expect(screen.getByTestId("kpi-approved-reviews-value")).toHaveTextContent("2");
  });

  it("displays student responses count", () => {
    mockSuccess({ student_responses: 4 });
    render(<KpiStrip />);
    expect(screen.getByTestId("kpi-student-responses-value")).toHaveTextContent("4");
  });

  it("displays suppressed retriggers count", () => {
    mockSuccess({ suppressed_retriggers: 2 });
    render(<KpiStrip />);
    expect(screen.getByTestId("kpi-suppressed-retriggers-value")).toHaveTextContent("2");
  });

  it("displays zero counts correctly", () => {
    mockSuccess({ pending_reviews: 0, approved_reviews: 0, student_responses: 0, suppressed_retriggers: 0 });
    render(<KpiStrip />);
    const values = screen.getAllByTestId(/^kpi-.*-value$/);
    values.forEach((el) => expect(el).toHaveTextContent("0"));
  });

  // -------------------------------------------------------------------------
  // Loading state
  // -------------------------------------------------------------------------

  it("shows Loading button text when idle", () => {
    vi.mocked(useKpiSummary).mockReturnValue({ state: { status: "idle" }, reload: noopReload });
    render(<KpiStrip />);
    expect(screen.getByTestId("kpi-refresh")).toHaveTextContent("Loading…");
  });

  it("shows Loading button text when loading", () => {
    vi.mocked(useKpiSummary).mockReturnValue({ state: { status: "loading" }, reload: noopReload });
    render(<KpiStrip />);
    expect(screen.getByTestId("kpi-refresh")).toHaveTextContent("Loading…");
  });

  it("shows Refresh button text when loaded", () => {
    mockSuccess();
    render(<KpiStrip />);
    expect(screen.getByTestId("kpi-refresh")).toHaveTextContent("Refresh");
  });

  // -------------------------------------------------------------------------
  // Error state
  // -------------------------------------------------------------------------

  it("shows error banner when status is error", () => {
    vi.mocked(useKpiSummary).mockReturnValue({
      state: { status: "error", message: "Network error" },
      reload: noopReload,
    });
    render(<KpiStrip />);
    expect(screen.getByTestId("kpi-error")).toBeInTheDocument();
    expect(screen.getByText(/Network error/)).toBeInTheDocument();
  });

  it("does not show error banner when status is success", () => {
    mockSuccess();
    render(<KpiStrip />);
    expect(screen.queryByTestId("kpi-error")).toBeNull();
  });

  // -------------------------------------------------------------------------
  // Source badge
  // -------------------------------------------------------------------------

  it("shows mock data source badge", () => {
    mockSuccess();
    render(<KpiStrip />);
    expect(screen.getByText(/mock data/i)).toBeInTheDocument();
  });

  it("shows live db source badge", () => {
    vi.mocked(useKpiSummary).mockReturnValue({
      state: {
        status: "success",
        data: { pending_reviews: 1, approved_reviews: 1, student_responses: 1, suppressed_retriggers: 0, source: "db" },
      },
      reload: noopReload,
    });
    render(<KpiStrip />);
    expect(screen.getByText(/live db/i)).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Refresh button
  // -------------------------------------------------------------------------

  it("calls reload when Refresh is clicked", async () => {
    mockSuccess();
    const user = userEvent.setup();
    render(<KpiStrip />);
    await user.click(screen.getByTestId("kpi-refresh"));
    expect(noopReload).toHaveBeenCalledOnce();
  });
});
