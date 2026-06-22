import React, { useState } from "react";
import { useStudentResponses } from "../../hooks/useSentinelData";
import type { StudentResponseRow } from "../../types/sentinel";
import { SourceBadge } from "./StatusBadge";
import { EmptyState, LoadingState, ErrorState } from "./EmptyState";

const LABEL: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  textTransform: "uppercase",
  letterSpacing: "0.07em",
  color: "#9ca3af",
  marginBottom: 3,
};

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-US", {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function MatchMethodBadge({ method }: { method: string }) {
  const isThread = method === "thread_id";
  return (
    <span
      data-testid={`method-badge-${method}`}
      style={{
        fontSize: 11,
        fontWeight: 700,
        textTransform: "uppercase",
        letterSpacing: "0.05em",
        padding: "3px 9px",
        borderRadius: 4,
        background: isThread ? "#eff6ff" : "#fffbeb",
        color:      isThread ? "#1d4ed8" : "#92400e",
        border:    `1px solid ${isThread ? "#bfdbfe" : "#fcd34d"}`,
        whiteSpace: "nowrap",
      }}
    >
      {method.replace(/_/g, " ")}
    </span>
  );
}

function ConfidenceChip({ value }: { value: number }) {
  const pct   = Math.round(value * 100);
  const isDet = value === 1.0;
  return (
    <span
      data-testid={isDet ? "confidence-deterministic" : "confidence-heuristic"}
      style={{
        fontSize: 12,
        fontWeight: 700,
        padding: "3px 10px",
        borderRadius: 20,
        background: isDet ? "#f0fdf4" : "#fffbeb",
        color:      isDet ? "#15803d" : "#92400e",
        border:     `1px solid ${isDet ? "#86efac" : "#fcd34d"}`,
        whiteSpace: "nowrap",
      }}
    >
      {isDet ? "Deterministic" : `Heuristic · ${pct}%`}
    </span>
  );
}

function SuppressionBadge() {
  return (
    <span
      data-testid="suppression-badge"
      style={{
        fontSize: 10,
        fontWeight: 700,
        textTransform: "uppercase",
        letterSpacing: "0.05em",
        padding: "3px 9px",
        borderRadius: 10,
        background: "#ecfdf5",
        color:      "#047857",
        border:     "1px solid #6ee7b7",
        whiteSpace: "nowrap",
      }}
    >
      suppression eligible
    </span>
  );
}

function ResponseCard({ row }: { row: StudentResponseRow }) {
  const [expanded, setExpanded] = useState(false);
  const isDeterministic = row.confidence === 1.0;

  return (
    <div
      data-testid="response-row"
      style={{
        background:   "#fff",
        border:       "1px solid #e5e7eb",
        borderLeft:   `4px solid ${isDeterministic ? "#16a34a" : "#d97706"}`,
        borderRadius: 10,
        overflow:     "hidden",
      }}
    >
      {/* Summary row — always visible, clickable to expand */}
      <div
        role="button"
        tabIndex={0}
        aria-expanded={expanded}
        data-testid="expand-toggle"
        onClick={() => setExpanded((v) => !v)}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && setExpanded((v) => !v)}
        style={{
          display:        "flex",
          justifyContent: "space-between",
          alignItems:     "center",
          padding:        "12px 18px",
          cursor:         "pointer",
          gap:            12,
          userSelect:     "none",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <span style={{ fontWeight: 700, fontSize: 14, color: "#111827" }}>
            CBM #{row.cbm_id}
          </span>
          <span style={{ fontWeight: 400, fontSize: 12, color: "#6b7280" }}>
            User #{row.user_id}
          </span>
          <MatchMethodBadge method={row.match_method} />
          <ConfidenceChip value={row.confidence} />
          {isDeterministic && <SuppressionBadge />}
        </div>
        <span
          aria-hidden
          style={{
            fontSize:   11,
            color:      "#9ca3af",
            flexShrink: 0,
            display:    "inline-block",
            transform:  expanded ? "rotate(180deg)" : "none",
            transition: "transform 0.15s",
          }}
        >
          ▾
        </span>
      </div>

      {/* Detail panel — only when expanded */}
      {expanded && (
        <div
          data-testid="detail-panel"
          style={{
            padding:   "0 18px 14px",
            borderTop: "1px solid #f3f4f6",
            display:   "flex",
            gap:       28,
            flexWrap:  "wrap",
          }}
        >
          <div style={{ marginTop: 12 }}>
            <div style={LABEL}>Response #</div>
            <div style={{ fontSize: 13, color: "#374151" }}>{row.id}</div>
          </div>
          <div style={{ marginTop: 12 }}>
            <div style={LABEL}>Channel</div>
            <div style={{ fontSize: 13, fontWeight: 600, color: "#374151" }}>
              {row.response_channel}
            </div>
          </div>
          <div style={{ marginTop: 12 }}>
            <div style={LABEL}>Engagement event</div>
            <div style={{ fontSize: 13, color: "#374151" }}>#{row.engagement_event_id}</div>
          </div>
          <div style={{ marginTop: 12 }}>
            <div style={LABEL}>Raw confidence</div>
            <div style={{ fontSize: 13, color: "#374151" }}>{row.confidence.toFixed(2)}</div>
          </div>
          <div style={{ marginTop: 12 }}>
            <div style={LABEL}>Matched at</div>
            <div style={{ fontSize: 12, color: "#6b7280" }}>{formatDate(row.matched_at)}</div>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Filter bar
// ---------------------------------------------------------------------------

interface FilterState {
  method:      string;
  confidence:  "all" | "deterministic" | "heuristic";
  suppression: "all" | "eligible";
}

const FILTER_DEFAULTS: FilterState = {
  method:      "all",
  confidence:  "all",
  suppression: "all",
};

function applyFilters(rows: StudentResponseRow[], f: FilterState): StudentResponseRow[] {
  return rows.filter((r) => {
    if (f.method !== "all"             && r.match_method !== f.method) return false;
    if (f.confidence === "deterministic" && r.confidence !== 1.0)       return false;
    if (f.confidence === "heuristic"     && r.confidence === 1.0)       return false;
    if (f.suppression === "eligible"     && r.confidence !== 1.0)       return false;
    return true;
  });
}

const SELECT_STYLE: React.CSSProperties = {
  padding:      "4px 8px",
  fontSize:     12,
  borderRadius: 6,
  border:       "1px solid #d1d5db",
  background:   "#fff",
  color:        "#374151",
  cursor:       "pointer",
};

function FilterBar({
  filters,
  methods,
  total,
  visible,
  onChange,
  onReset,
}: {
  filters:  FilterState;
  methods:  string[];
  total:    number;
  visible:  number;
  onChange: (f: FilterState) => void;
  onReset:  () => void;
}) {
  const isActive =
    filters.method !== "all" || filters.confidence !== "all" || filters.suppression !== "all";

  return (
    <div
      data-testid="filter-bar"
      style={{
        display:      "flex",
        gap:          10,
        flexWrap:     "wrap",
        alignItems:   "center",
        marginBottom: 14,
        padding:      "10px 14px",
        background:   "#f9fafb",
        border:       "1px solid #e5e7eb",
        borderRadius: 8,
      }}
    >
      <span style={{ fontSize: 11, fontWeight: 700, color: "#9ca3af", textTransform: "uppercase", marginRight: 4 }}>
        Filter:
      </span>

      <select
        data-testid="filter-method"
        aria-label="Filter by match method"
        style={SELECT_STYLE}
        value={filters.method}
        onChange={(e) => onChange({ ...filters, method: e.target.value })}
      >
        <option value="all">Method: All</option>
        {methods.map((m) => (
          <option key={m} value={m}>{m.replace(/_/g, " ")}</option>
        ))}
      </select>

      <select
        data-testid="filter-confidence"
        aria-label="Filter by confidence type"
        style={SELECT_STYLE}
        value={filters.confidence}
        onChange={(e) => onChange({ ...filters, confidence: e.target.value as FilterState["confidence"] })}
      >
        <option value="all">Confidence: All</option>
        <option value="deterministic">Deterministic</option>
        <option value="heuristic">Heuristic</option>
      </select>

      <select
        data-testid="filter-suppression"
        aria-label="Filter by suppression"
        style={SELECT_STYLE}
        value={filters.suppression}
        onChange={(e) => onChange({ ...filters, suppression: e.target.value as FilterState["suppression"] })}
      >
        <option value="all">Suppression: All</option>
        <option value="eligible">Eligible only</option>
      </select>

      {isActive && (
        <>
          <span data-testid="filter-active-count" style={{ fontSize: 12, color: "#374151" }}>
            Showing {visible} of {total}
          </span>
          <button
            data-testid="filter-reset"
            onClick={onReset}
            style={{
              padding: "3px 10px", fontSize: 11, fontWeight: 600,
              background: "#fff", border: "1px solid #d1d5db",
              borderRadius: 6, cursor: "pointer", color: "#374151",
            }}
          >
            Reset
          </button>
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Panel
// ---------------------------------------------------------------------------

interface StudentResponsesPanelProps {
  userId?: number;
}

export function StudentResponsesPanel({ userId }: StudentResponsesPanelProps) {
  const { state, reload }    = useStudentResponses(userId);
  const [filters, setFilters] = useState<FilterState>(FILTER_DEFAULTS);

  const allResponses       = state.status === "success" ? state.data.responses : [];
  const source             = state.status === "success" ? state.data.source    : null;
  const deterministicCount = allResponses.filter((r) => r.confidence === 1.0).length;
  const heuristicCount     = allResponses.filter((r) => r.confidence < 1.0).length;

  const uniqueMethods = [...new Set(allResponses.map((r) => r.match_method))].sort();
  const visibleRows   = applyFilters(allResponses, filters);

  return (
    <section>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: "#111827" }}>
            Student Responses
          </h2>
          <p style={{ margin: "4px 0 0", fontSize: 13, color: "#6b7280" }}>
            Inbound responses matched to outbound triggers — confidence=1.0 suppresses redelivery
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          {source && <SourceBadge source={source} />}
          <button
            onClick={reload}
            style={{
              padding: "6px 14px", fontSize: 12, fontWeight: 600,
              background: "#f9fafb", border: "1px solid #e5e7eb",
              borderRadius: 6, cursor: "pointer", color: "#374151",
            }}
          >
            Refresh
          </button>
        </div>
      </div>

      {/* Legend — only when rows are present */}
      {allResponses.length > 0 && (
        <div
          data-testid="response-legend"
          style={{ display: "flex", gap: 20, marginBottom: 16, fontSize: 12, color: "#6b7280", flexWrap: "wrap" }}
        >
          <span>
            <span style={{ color: "#16a34a", fontWeight: 700 }}>▌</span>{" "}
            <strong>{deterministicCount}</strong> deterministic — thread_id match, suppression eligible
          </span>
          <span>
            <span style={{ color: "#d97706", fontWeight: 700 }}>▌</span>{" "}
            <strong>{heuristicCount}</strong> heuristic — time_proximity, delivery not suppressed
          </span>
        </div>
      )}

      {state.status === "idle"    && <LoadingState label="Loading student responses..." />}
      {state.status === "loading" && <LoadingState label="Loading student responses..." />}
      {state.status === "error"   && <ErrorState message={state.message} />}
      {state.status === "success" && allResponses.length === 0 && (
        <EmptyState
          title="No student responses found"
          body={
            userId
              ? `No responses recorded for user #${userId}.`
              : "No response records in the system yet. Responses are created when the matching worker runs."
          }
          icon="💬"
        />
      )}
      {state.status === "success" && allResponses.length > 0 && (
        <>
          <FilterBar
            filters={filters}
            methods={uniqueMethods}
            total={allResponses.length}
            visible={visibleRows.length}
            onChange={setFilters}
            onReset={() => setFilters(FILTER_DEFAULTS)}
          />
          {visibleRows.length === 0 ? (
            <EmptyState
              title="No responses match current filters"
              body="Adjust or reset the filters above."
              icon="🔍"
            />
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {visibleRows.map((row) => (
                <ResponseCard key={row.id} row={row} />
              ))}
            </div>
          )}
        </>
      )}
    </section>
  );
}
