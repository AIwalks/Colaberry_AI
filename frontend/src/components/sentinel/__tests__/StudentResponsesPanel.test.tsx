import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// ---------------------------------------------------------------------------
// Mock the hook — tests must not make HTTP calls
// ---------------------------------------------------------------------------

vi.mock("../../../hooks/useSentinelData", () => ({
  useStudentResponses: vi.fn(),
}));

import { useStudentResponses } from "../../../hooks/useSentinelData";
import { StudentResponsesPanel } from "../StudentResponsesPanel";
import type { StudentResponsesResponse } from "../../../types/sentinel";

const noopReload = vi.fn();

function mockSuccess(responses: StudentResponsesResponse["responses"]) {
  vi.mocked(useStudentResponses).mockReturnValue({
    state: {
      status: "success",
      data: { responses, total: responses.length, source: "mock" },
    },
    reload: noopReload,
  });
}

const DET_ROW = {
  id: 1,
  cbm_id: 42,
  engagement_event_id: 1001,
  user_id: 101,
  response_channel: "whatsapp",
  match_method: "thread_id",
  confidence: 1.0,
  matched_at: "2026-06-20T14:30:00",
};

const HEU_ROW = {
  id: 2,
  cbm_id: 43,
  engagement_event_id: 1002,
  user_id: 202,
  response_channel: "email",
  match_method: "time_proximity",
  confidence: 0.65,
  matched_at: "2026-06-19T09:15:00",
};

describe("StudentResponsesPanel", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    noopReload.mockReset();
  });

  // -------------------------------------------------------------------------
  // Loading / error / empty states
  // -------------------------------------------------------------------------

  it("shows loading state when status is idle", () => {
    vi.mocked(useStudentResponses).mockReturnValue({
      state: { status: "idle" },
      reload: noopReload,
    });
    render(<StudentResponsesPanel />);
    expect(screen.getByTestId("loading-state")).toBeInTheDocument();
  });

  it("shows loading state when status is loading", () => {
    vi.mocked(useStudentResponses).mockReturnValue({
      state: { status: "loading" },
      reload: noopReload,
    });
    render(<StudentResponsesPanel />);
    expect(screen.getByTestId("loading-state")).toBeInTheDocument();
  });

  it("shows error state when status is error", () => {
    vi.mocked(useStudentResponses).mockReturnValue({
      state: { status: "error", message: "Network failure" },
      reload: noopReload,
    });
    render(<StudentResponsesPanel />);
    expect(screen.getByTestId("error-state")).toBeInTheDocument();
  });

  it("shows empty state when no responses", () => {
    mockSuccess([]);
    render(<StudentResponsesPanel />);
    expect(screen.getByTestId("empty-state")).toBeInTheDocument();
    expect(screen.getByText(/No student responses found/)).toBeInTheDocument();
  });

  it("empty state body mentions user when userId provided", () => {
    vi.mocked(useStudentResponses).mockReturnValue({
      state: {
        status: "success",
        data: { responses: [], total: 0, source: "mock" },
      },
      reload: noopReload,
    });
    render(<StudentResponsesPanel userId={101} />);
    expect(screen.getByText(/No responses recorded for user #101/)).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Response rows
  // -------------------------------------------------------------------------

  it("renders response rows when data is present", () => {
    mockSuccess([DET_ROW, HEU_ROW]);
    render(<StudentResponsesPanel />);
    const rows = screen.getAllByTestId("response-row");
    expect(rows).toHaveLength(2);
  });

  it("shows suppression badge for confidence=1.0 row", () => {
    mockSuccess([DET_ROW]);
    render(<StudentResponsesPanel />);
    expect(screen.getByTestId("suppression-badge")).toBeInTheDocument();
  });

  it("does not show suppression badge for confidence<1.0 row", () => {
    mockSuccess([HEU_ROW]);
    render(<StudentResponsesPanel />);
    expect(screen.queryByTestId("suppression-badge")).toBeNull();
  });

  it("shows green confidence chip for deterministic row", () => {
    mockSuccess([DET_ROW]);
    render(<StudentResponsesPanel />);
    expect(screen.getByTestId("confidence-deterministic")).toBeInTheDocument();
  });

  it("shows amber confidence chip for heuristic row", () => {
    mockSuccess([HEU_ROW]);
    render(<StudentResponsesPanel />);
    expect(screen.getByTestId("confidence-heuristic")).toBeInTheDocument();
  });

  it("shows thread_id method badge", () => {
    mockSuccess([DET_ROW]);
    render(<StudentResponsesPanel />);
    expect(screen.getByTestId("method-badge-thread_id")).toBeInTheDocument();
  });

  it("shows time_proximity method badge", () => {
    mockSuccess([HEU_ROW]);
    render(<StudentResponsesPanel />);
    expect(screen.getByTestId("method-badge-time_proximity")).toBeInTheDocument();
  });

  it("renders cbm_id and user_id for each row", () => {
    mockSuccess([DET_ROW]);
    render(<StudentResponsesPanel />);
    expect(screen.getByText(/CBM #42/)).toBeInTheDocument();
    expect(screen.getByText(/User #101/)).toBeInTheDocument();
  });

  it("shows legend when responses are present", () => {
    mockSuccess([DET_ROW, HEU_ROW]);
    render(<StudentResponsesPanel />);
    expect(screen.getByTestId("response-legend")).toBeInTheDocument();
  });

  it("does not show legend when responses are empty", () => {
    mockSuccess([]);
    render(<StudentResponsesPanel />);
    expect(screen.queryByTestId("response-legend")).toBeNull();
  });

  it("legend counts deterministic and heuristic rows correctly", () => {
    mockSuccess([DET_ROW, HEU_ROW]);
    render(<StudentResponsesPanel />);
    const legend = screen.getByTestId("response-legend");
    expect(legend).toHaveTextContent("1");
    expect(legend).toHaveTextContent("deterministic");
    expect(legend).toHaveTextContent("heuristic");
  });

  // -------------------------------------------------------------------------
  // Refresh button
  // -------------------------------------------------------------------------

  it("calls reload when Refresh button is clicked", async () => {
    mockSuccess([DET_ROW]);
    const user = userEvent.setup();
    render(<StudentResponsesPanel />);
    await user.click(screen.getByRole("button", { name: /Refresh/i }));
    expect(noopReload).toHaveBeenCalledOnce();
  });

  // -------------------------------------------------------------------------
  // Source badge
  // -------------------------------------------------------------------------

  it("shows source badge when data is loaded", () => {
    mockSuccess([DET_ROW]);
    render(<StudentResponsesPanel />);
    expect(screen.getByText(/mock data/i)).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Filter bar — presence
  // -------------------------------------------------------------------------

  it("renders filter bar when responses are present", () => {
    mockSuccess([DET_ROW]);
    render(<StudentResponsesPanel />);
    expect(screen.getByTestId("filter-bar")).toBeInTheDocument();
  });

  it("does not render filter bar when responses are empty", () => {
    mockSuccess([]);
    render(<StudentResponsesPanel />);
    expect(screen.queryByTestId("filter-bar")).toBeNull();
  });

  // -------------------------------------------------------------------------
  // Filter bar — method filter
  // -------------------------------------------------------------------------

  it("filtering by method=thread_id shows only thread_id rows", async () => {
    mockSuccess([DET_ROW, HEU_ROW]);
    const user = userEvent.setup();
    render(<StudentResponsesPanel />);
    await user.selectOptions(screen.getByTestId("filter-method"), "thread_id");
    expect(screen.getAllByTestId("response-row")).toHaveLength(1);
    expect(screen.getByTestId("method-badge-thread_id")).toBeInTheDocument();
    expect(screen.queryByTestId("method-badge-time_proximity")).toBeNull();
  });

  it("filtering by method=time_proximity shows only time_proximity rows", async () => {
    mockSuccess([DET_ROW, HEU_ROW]);
    const user = userEvent.setup();
    render(<StudentResponsesPanel />);
    await user.selectOptions(screen.getByTestId("filter-method"), "time_proximity");
    expect(screen.getAllByTestId("response-row")).toHaveLength(1);
    expect(screen.getByTestId("method-badge-time_proximity")).toBeInTheDocument();
    expect(screen.queryByTestId("method-badge-thread_id")).toBeNull();
  });

  // -------------------------------------------------------------------------
  // Filter bar — confidence filter
  // -------------------------------------------------------------------------

  it("filtering by confidence=deterministic shows only deterministic rows", async () => {
    mockSuccess([DET_ROW, HEU_ROW]);
    const user = userEvent.setup();
    render(<StudentResponsesPanel />);
    await user.selectOptions(screen.getByTestId("filter-confidence"), "deterministic");
    expect(screen.getAllByTestId("response-row")).toHaveLength(1);
    expect(screen.getByTestId("confidence-deterministic")).toBeInTheDocument();
    expect(screen.queryByTestId("confidence-heuristic")).toBeNull();
  });

  it("filtering by confidence=heuristic shows only heuristic rows", async () => {
    mockSuccess([DET_ROW, HEU_ROW]);
    const user = userEvent.setup();
    render(<StudentResponsesPanel />);
    await user.selectOptions(screen.getByTestId("filter-confidence"), "heuristic");
    expect(screen.getAllByTestId("response-row")).toHaveLength(1);
    expect(screen.getByTestId("confidence-heuristic")).toBeInTheDocument();
    expect(screen.queryByTestId("confidence-deterministic")).toBeNull();
  });

  // -------------------------------------------------------------------------
  // Filter bar — suppression filter
  // -------------------------------------------------------------------------

  it("filtering by suppression=eligible shows only confidence=1.0 rows", async () => {
    mockSuccess([DET_ROW, HEU_ROW]);
    const user = userEvent.setup();
    render(<StudentResponsesPanel />);
    await user.selectOptions(screen.getByTestId("filter-suppression"), "eligible");
    expect(screen.getAllByTestId("response-row")).toHaveLength(1);
    expect(screen.getByTestId("suppression-badge")).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Filter bar — active count and reset
  // -------------------------------------------------------------------------

  it("shows active count when a filter is applied", async () => {
    mockSuccess([DET_ROW, HEU_ROW]);
    const user = userEvent.setup();
    render(<StudentResponsesPanel />);
    await user.selectOptions(screen.getByTestId("filter-method"), "thread_id");
    expect(screen.getByTestId("filter-active-count")).toHaveTextContent("Showing 1 of 2");
  });

  it("reset button restores all rows", async () => {
    mockSuccess([DET_ROW, HEU_ROW]);
    const user = userEvent.setup();
    render(<StudentResponsesPanel />);
    await user.selectOptions(screen.getByTestId("filter-method"), "thread_id");
    expect(screen.getAllByTestId("response-row")).toHaveLength(1);
    await user.click(screen.getByTestId("filter-reset"));
    expect(screen.getAllByTestId("response-row")).toHaveLength(2);
    expect(screen.queryByTestId("filter-active-count")).toBeNull();
  });

  it("shows empty state when no rows match active filter", async () => {
    mockSuccess([DET_ROW]);
    const user = userEvent.setup();
    render(<StudentResponsesPanel />);
    await user.selectOptions(screen.getByTestId("filter-confidence"), "heuristic");
    expect(screen.getByTestId("empty-state")).toBeInTheDocument();
    expect(screen.getByText(/No responses match current filters/)).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Expandable detail
  // -------------------------------------------------------------------------

  it("each row has an expand toggle", () => {
    mockSuccess([DET_ROW, HEU_ROW]);
    render(<StudentResponsesPanel />);
    expect(screen.getAllByTestId("expand-toggle")).toHaveLength(2);
  });

  it("detail panel is hidden by default", () => {
    mockSuccess([DET_ROW]);
    render(<StudentResponsesPanel />);
    expect(screen.queryByTestId("detail-panel")).toBeNull();
  });

  it("clicking expand toggle reveals detail panel", async () => {
    mockSuccess([DET_ROW]);
    const user = userEvent.setup();
    render(<StudentResponsesPanel />);
    await user.click(screen.getByTestId("expand-toggle"));
    expect(screen.getByTestId("detail-panel")).toBeInTheDocument();
  });

  it("clicking expand toggle again hides detail panel", async () => {
    mockSuccess([DET_ROW]);
    const user = userEvent.setup();
    render(<StudentResponsesPanel />);
    await user.click(screen.getByTestId("expand-toggle"));
    expect(screen.getByTestId("detail-panel")).toBeInTheDocument();
    await user.click(screen.getByTestId("expand-toggle"));
    expect(screen.queryByTestId("detail-panel")).toBeNull();
  });

  it("detail panel shows channel and engagement event id", async () => {
    mockSuccess([DET_ROW]);
    const user = userEvent.setup();
    render(<StudentResponsesPanel />);
    await user.click(screen.getByTestId("expand-toggle"));
    const panel = screen.getByTestId("detail-panel");
    expect(panel).toHaveTextContent("whatsapp");
    expect(panel).toHaveTextContent("#1001");
  });
});
