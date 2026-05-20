import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import type { GovernanceReview } from "../../../types/sentinel";

// ---------------------------------------------------------------------------
// Mock the data-fetching hook so tests are hermetic (no HTTP calls)
// ---------------------------------------------------------------------------

const mockReload = vi.fn();

vi.mock("../../../hooks/useSentinelData", () => ({
  useGovernanceReviews: vi.fn(),
  usePendingReviews:    vi.fn(),
}));

import { useGovernanceReviews } from "../../../hooks/useSentinelData";
import { GovernanceQueue } from "../GovernanceQueue";

const mockReview = (overrides: Partial<GovernanceReview> = {}): GovernanceReview => ({
  id: 1,
  created_at:        "2026-05-18T10:00:00",
  updated_at:        "2026-05-18T10:00:00",
  interpretation_id: 101,
  entity_id:         "student_101",
  entity_type:       "student",
  status:            "pending",
  reviewed_by:       null,
  reviewed_at:       null,
  review_notes:      null,
  governance_reason: "High engagement risk detected",
  risk_level:        "high",
  confidence:        0.87,
  is_active:         true,
  ...overrides,
});

describe("GovernanceQueue", () => {
  beforeEach(() => {
    vi.mocked(useGovernanceReviews).mockReset();
  });

  it("shows loading state", () => {
    vi.mocked(useGovernanceReviews).mockReturnValue({
      state:  { status: "loading" },
      reload: mockReload,
    });
    render(<GovernanceQueue />);
    expect(screen.getByTestId("loading-state")).toBeInTheDocument();
  });

  it("shows error state", () => {
    vi.mocked(useGovernanceReviews).mockReturnValue({
      state:  { status: "error", message: "HTTP 500" },
      reload: mockReload,
    });
    render(<GovernanceQueue />);
    expect(screen.getByTestId("error-state")).toBeInTheDocument();
    expect(screen.getByText("HTTP 500")).toBeInTheDocument();
  });

  it("shows empty state when review list is empty", () => {
    vi.mocked(useGovernanceReviews).mockReturnValue({
      state:  { status: "success", data: { reviews: [], total: 0, source: "mock" } },
      reload: mockReload,
    });
    render(<GovernanceQueue />);
    expect(screen.getByTestId("empty-state")).toBeInTheDocument();
  });

  it("renders review rows when data is present", () => {
    vi.mocked(useGovernanceReviews).mockReturnValue({
      state: {
        status: "success",
        data: {
          reviews: [mockReview(), mockReview({ id: 2, entity_id: "student_202", risk_level: "critical" })],
          total:   2,
          source:  "mock",
        },
      },
      reload: mockReload,
    });
    render(<GovernanceQueue />);
    const rows = screen.getAllByTestId("governance-review-row");
    expect(rows).toHaveLength(2);
  });

  it("renders entity_id for each review", () => {
    vi.mocked(useGovernanceReviews).mockReturnValue({
      state: {
        status: "success",
        data: {
          reviews: [mockReview({ entity_id: "student_999" })],
          total:   1,
          source:  "mock",
        },
      },
      reload: mockReload,
    });
    render(<GovernanceQueue />);
    expect(screen.getByText("student_999")).toBeInTheDocument();
  });

  it("renders governance status badge for pending review", () => {
    vi.mocked(useGovernanceReviews).mockReturnValue({
      state: {
        status: "success",
        data: { reviews: [mockReview({ status: "pending" })], total: 1, source: "mock" },
      },
      reload: mockReload,
    });
    render(<GovernanceQueue />);
    expect(screen.getByTestId("status-badge-pending")).toBeInTheDocument();
  });

  it("renders governance status badge for approved review", () => {
    vi.mocked(useGovernanceReviews).mockReturnValue({
      state: {
        status: "success",
        data: {
          reviews: [mockReview({ status: "approved", reviewed_by: "admin@test.com" })],
          total:   1,
          source:  "mock",
        },
      },
      reload: mockReload,
    });
    render(<GovernanceQueue />);
    expect(screen.getByTestId("status-badge-approved")).toBeInTheDocument();
  });

  it("renders risk level badge", () => {
    vi.mocked(useGovernanceReviews).mockReturnValue({
      state: {
        status: "success",
        data: { reviews: [mockReview({ risk_level: "critical" })], total: 1, source: "mock" },
      },
      reload: mockReload,
    });
    render(<GovernanceQueue />);
    expect(screen.getByTestId("risk-badge-critical")).toBeInTheDocument();
  });

  it("renders section heading", () => {
    vi.mocked(useGovernanceReviews).mockReturnValue({
      state:  { status: "idle" },
      reload: mockReload,
    });
    render(<GovernanceQueue />);
    expect(screen.getByText("Governance Review Queue")).toBeInTheDocument();
  });

  it("renders mock data source badge", () => {
    vi.mocked(useGovernanceReviews).mockReturnValue({
      state: {
        status: "success",
        data: { reviews: [], total: 0, source: "mock" },
      },
      reload: mockReload,
    });
    render(<GovernanceQueue />);
    expect(screen.getByText("mock data")).toBeInTheDocument();
  });

  it("renders db source badge", () => {
    vi.mocked(useGovernanceReviews).mockReturnValue({
      state: {
        status: "success",
        data: { reviews: [], total: 0, source: "db" },
      },
      reload: mockReload,
    });
    render(<GovernanceQueue />);
    expect(screen.getByText("live db")).toBeInTheDocument();
  });
});
