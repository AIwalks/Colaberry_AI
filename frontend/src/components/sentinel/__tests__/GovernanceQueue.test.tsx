import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import type { GovernanceReview } from "../../../types/sentinel";

// ---------------------------------------------------------------------------
// Mock the data-fetching hook so tests are hermetic (no HTTP calls)
// ---------------------------------------------------------------------------

const mockReload = vi.fn();

vi.mock("../../../hooks/useSentinelData", () => ({
  useGovernanceReviews: vi.fn(),
  usePendingReviews:    vi.fn(),
  useGovernanceAction:  vi.fn(),
}));

import { useGovernanceReviews, useGovernanceAction } from "../../../hooks/useSentinelData";
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
    mockReload.mockClear();
    vi.mocked(useGovernanceReviews).mockReset();
    vi.mocked(useGovernanceAction).mockReset();
    // Default action hook — succeeds immediately, used by all tests that don't override it
    vi.mocked(useGovernanceAction).mockReturnValue({
      state:   { status: "idle" },
      execute: vi.fn().mockResolvedValue(true),
      reset:   vi.fn(),
    });
  });

  // ---------------------------------------------------------------------------
  // Existing render / state tests (unchanged)
  // ---------------------------------------------------------------------------

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

  // ---------------------------------------------------------------------------
  // Action buttons — visibility
  // ---------------------------------------------------------------------------

  it("renders Approve, Reject, Defer buttons for pending reviews", () => {
    vi.mocked(useGovernanceReviews).mockReturnValue({
      state: {
        status: "success",
        data: { reviews: [mockReview({ id: 10, status: "pending" })], total: 1, source: "mock" },
      },
      reload: mockReload,
    });
    render(<GovernanceQueue />);
    expect(screen.getByTestId("action-btn-approve-10")).toBeInTheDocument();
    expect(screen.getByTestId("action-btn-reject-10")).toBeInTheDocument();
    expect(screen.getByTestId("action-btn-defer-10")).toBeInTheDocument();
  });

  it("does not render action buttons for approved reviews", () => {
    vi.mocked(useGovernanceReviews).mockReturnValue({
      state: {
        status: "success",
        data: { reviews: [mockReview({ id: 11, status: "approved" })], total: 1, source: "mock" },
      },
      reload: mockReload,
    });
    render(<GovernanceQueue />);
    expect(screen.queryByTestId("action-buttons-11")).not.toBeInTheDocument();
  });

  it("does not render action buttons for rejected reviews", () => {
    vi.mocked(useGovernanceReviews).mockReturnValue({
      state: {
        status: "success",
        data: { reviews: [mockReview({ id: 12, status: "rejected" })], total: 1, source: "mock" },
      },
      reload: mockReload,
    });
    render(<GovernanceQueue />);
    expect(screen.queryByTestId("action-buttons-12")).not.toBeInTheDocument();
  });

  it("does not render action buttons for deferred reviews", () => {
    vi.mocked(useGovernanceReviews).mockReturnValue({
      state: {
        status: "success",
        data: { reviews: [mockReview({ id: 13, status: "deferred" })], total: 1, source: "mock" },
      },
      reload: mockReload,
    });
    render(<GovernanceQueue />);
    expect(screen.queryByTestId("action-buttons-13")).not.toBeInTheDocument();
  });

  // ---------------------------------------------------------------------------
  // Action panel — open / close
  // ---------------------------------------------------------------------------

  it("opens action panel when Approve button is clicked", () => {
    vi.mocked(useGovernanceReviews).mockReturnValue({
      state: {
        status: "success",
        data: { reviews: [mockReview({ id: 20, status: "pending" })], total: 1, source: "mock" },
      },
      reload: mockReload,
    });
    render(<GovernanceQueue />);
    fireEvent.click(screen.getByTestId("action-btn-approve-20"));
    expect(screen.getByTestId("action-panel-20")).toBeInTheDocument();
    expect(screen.getByTestId("input-reviewed-by")).toBeInTheDocument();
  });

  it("hides action buttons when panel is open", () => {
    vi.mocked(useGovernanceReviews).mockReturnValue({
      state: {
        status: "success",
        data: { reviews: [mockReview({ id: 21, status: "pending" })], total: 1, source: "mock" },
      },
      reload: mockReload,
    });
    render(<GovernanceQueue />);
    fireEvent.click(screen.getByTestId("action-btn-approve-21"));
    expect(screen.queryByTestId("action-buttons-21")).not.toBeInTheDocument();
  });

  it("closes action panel when Cancel is clicked", () => {
    vi.mocked(useGovernanceReviews).mockReturnValue({
      state: {
        status: "success",
        data: { reviews: [mockReview({ id: 22, status: "pending" })], total: 1, source: "mock" },
      },
      reload: mockReload,
    });
    render(<GovernanceQueue />);
    fireEvent.click(screen.getByTestId("action-btn-reject-22"));
    expect(screen.getByTestId("action-panel-22")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("cancel-action"));
    expect(screen.queryByTestId("action-panel-22")).not.toBeInTheDocument();
    expect(screen.getByTestId("action-buttons-22")).toBeInTheDocument();
  });

  // ---------------------------------------------------------------------------
  // Submit — validation
  // ---------------------------------------------------------------------------

  it("submit button is disabled when reviewed_by is empty", () => {
    vi.mocked(useGovernanceReviews).mockReturnValue({
      state: {
        status: "success",
        data: { reviews: [mockReview({ id: 30, status: "pending" })], total: 1, source: "mock" },
      },
      reload: mockReload,
    });
    render(<GovernanceQueue />);
    fireEvent.click(screen.getByTestId("action-btn-approve-30"));
    expect(screen.getByTestId("submit-action")).toBeDisabled();
  });

  it("submit button is disabled for reject when review_notes is empty", () => {
    vi.mocked(useGovernanceReviews).mockReturnValue({
      state: {
        status: "success",
        data: { reviews: [mockReview({ id: 31, status: "pending" })], total: 1, source: "mock" },
      },
      reload: mockReload,
    });
    render(<GovernanceQueue />);
    fireEvent.click(screen.getByTestId("action-btn-reject-31"));
    fireEvent.change(screen.getByTestId("input-reviewed-by"), { target: { value: "admin@test.com" } });
    // review_notes is required for reject but still empty
    expect(screen.getByTestId("submit-action")).toBeDisabled();
  });

  it("submit button is enabled for approve with only reviewed_by filled", () => {
    vi.mocked(useGovernanceReviews).mockReturnValue({
      state: {
        status: "success",
        data: { reviews: [mockReview({ id: 32, status: "pending" })], total: 1, source: "mock" },
      },
      reload: mockReload,
    });
    render(<GovernanceQueue />);
    fireEvent.click(screen.getByTestId("action-btn-approve-32"));
    fireEvent.change(screen.getByTestId("input-reviewed-by"), { target: { value: "admin@test.com" } });
    expect(screen.getByTestId("submit-action")).not.toBeDisabled();
  });

  // ---------------------------------------------------------------------------
  // Submit — API calls
  // ---------------------------------------------------------------------------

  it("calls execute with correct approve payload", async () => {
    const mockExecute = vi.fn().mockResolvedValue(true);
    vi.mocked(useGovernanceAction).mockReturnValue({
      state:   { status: "idle" },
      execute: mockExecute,
      reset:   vi.fn(),
    });
    vi.mocked(useGovernanceReviews).mockReturnValue({
      state: {
        status: "success",
        data: { reviews: [mockReview({ id: 40, status: "pending" })], total: 1, source: "mock" },
      },
      reload: mockReload,
    });

    render(<GovernanceQueue />);
    fireEvent.click(screen.getByTestId("action-btn-approve-40"));
    fireEvent.change(screen.getByTestId("input-reviewed-by"), { target: { value: "admin@test.com" } });
    fireEvent.click(screen.getByTestId("submit-action"));

    await waitFor(() => {
      expect(mockExecute).toHaveBeenCalledWith(
        40,
        "approve",
        expect.objectContaining({ reviewed_by: "admin@test.com" }),
      );
    });
  });

  it("calls execute with correct reject payload including review_notes", async () => {
    const mockExecute = vi.fn().mockResolvedValue(true);
    vi.mocked(useGovernanceAction).mockReturnValue({
      state:   { status: "idle" },
      execute: mockExecute,
      reset:   vi.fn(),
    });
    vi.mocked(useGovernanceReviews).mockReturnValue({
      state: {
        status: "success",
        data: { reviews: [mockReview({ id: 41, status: "pending" })], total: 1, source: "mock" },
      },
      reload: mockReload,
    });

    render(<GovernanceQueue />);
    fireEvent.click(screen.getByTestId("action-btn-reject-41"));
    fireEvent.change(screen.getByTestId("input-reviewed-by"),  { target: { value: "admin@test.com" } });
    fireEvent.change(screen.getByTestId("input-extra-field"),  { target: { value: "Confidence too low" } });
    fireEvent.click(screen.getByTestId("submit-action"));

    await waitFor(() => {
      expect(mockExecute).toHaveBeenCalledWith(
        41,
        "reject",
        { reviewed_by: "admin@test.com", review_notes: "Confidence too low" },
      );
    });
  });

  it("calls execute with correct defer payload including governance_reason", async () => {
    const mockExecute = vi.fn().mockResolvedValue(true);
    vi.mocked(useGovernanceAction).mockReturnValue({
      state:   { status: "idle" },
      execute: mockExecute,
      reset:   vi.fn(),
    });
    vi.mocked(useGovernanceReviews).mockReturnValue({
      state: {
        status: "success",
        data: { reviews: [mockReview({ id: 42, status: "pending" })], total: 1, source: "mock" },
      },
      reload: mockReload,
    });

    render(<GovernanceQueue />);
    fireEvent.click(screen.getByTestId("action-btn-defer-42"));
    fireEvent.change(screen.getByTestId("input-reviewed-by"),  { target: { value: "admin@test.com" } });
    fireEvent.change(screen.getByTestId("input-extra-field"),  { target: { value: "Awaiting updated data" } });
    fireEvent.click(screen.getByTestId("submit-action"));

    await waitFor(() => {
      expect(mockExecute).toHaveBeenCalledWith(
        42,
        "defer",
        { reviewed_by: "admin@test.com", governance_reason: "Awaiting updated data" },
      );
    });
  });

  it("reloads queue after successful action", async () => {
    const mockExecute = vi.fn().mockResolvedValue(true);
    vi.mocked(useGovernanceAction).mockReturnValue({
      state:   { status: "idle" },
      execute: mockExecute,
      reset:   vi.fn(),
    });
    vi.mocked(useGovernanceReviews).mockReturnValue({
      state: {
        status: "success",
        data: { reviews: [mockReview({ id: 50, status: "pending" })], total: 1, source: "mock" },
      },
      reload: mockReload,
    });

    render(<GovernanceQueue />);
    fireEvent.click(screen.getByTestId("action-btn-approve-50"));
    fireEvent.change(screen.getByTestId("input-reviewed-by"), { target: { value: "admin@test.com" } });
    fireEvent.click(screen.getByTestId("submit-action"));

    await waitFor(() => {
      expect(mockReload).toHaveBeenCalled();
    });
  });

  it("shows error banner when action fails", async () => {
    const mockExecute = vi.fn().mockResolvedValue(false);
    vi.mocked(useGovernanceAction).mockReturnValue({
      state:   { status: "error", message: "HTTP 503: no_db" },
      execute: mockExecute,
      reset:   vi.fn(),
    });
    vi.mocked(useGovernanceReviews).mockReturnValue({
      state: {
        status: "success",
        data: { reviews: [mockReview({ id: 60, status: "pending" })], total: 1, source: "mock" },
      },
      reload: mockReload,
    });

    render(<GovernanceQueue />);
    fireEvent.click(screen.getByTestId("action-btn-approve-60"));

    // Error banner is visible because actionState is already "error"
    expect(screen.getByTestId("action-error")).toBeInTheDocument();
    expect(screen.getByText("HTTP 503: no_db")).toBeInTheDocument();
  });

  it("does not reload queue after failed action", async () => {
    const mockExecute = vi.fn().mockResolvedValue(false);
    vi.mocked(useGovernanceAction).mockReturnValue({
      state:   { status: "idle" },
      execute: mockExecute,
      reset:   vi.fn(),
    });
    vi.mocked(useGovernanceReviews).mockReturnValue({
      state: {
        status: "success",
        data: { reviews: [mockReview({ id: 61, status: "pending" })], total: 1, source: "mock" },
      },
      reload: mockReload,
    });

    render(<GovernanceQueue />);
    fireEvent.click(screen.getByTestId("action-btn-approve-61"));
    fireEvent.change(screen.getByTestId("input-reviewed-by"), { target: { value: "admin@test.com" } });
    fireEvent.click(screen.getByTestId("submit-action"));

    await waitFor(() => {
      expect(mockExecute).toHaveBeenCalled();
    });
    expect(mockReload).not.toHaveBeenCalled();
  });
});
