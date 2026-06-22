import React from "react";
import { useKpiSummary } from "../../hooks/useSentinelData";
import { SourceBadge } from "./StatusBadge";

interface KpiTileProps {
  label:     string;
  value:     number | null;
  accent:    string;
  testId:    string;
  icon:      string;
}

function KpiTile({ label, value, accent, testId, icon }: KpiTileProps) {
  return (
    <div
      data-testid={testId}
      style={{
        flex:         "1 1 160px",
        background:   "#fff",
        border:       "1px solid #e5e7eb",
        borderTop:    `3px solid ${accent}`,
        borderRadius: 10,
        padding:      "14px 18px",
        minWidth:     0,
      }}
    >
      <div style={{ fontSize: 20, marginBottom: 6 }}>{icon}</div>
      <div
        data-testid={`${testId}-value`}
        style={{ fontSize: 28, fontWeight: 800, color: "#111827", lineHeight: 1 }}
      >
        {value ?? "—"}
      </div>
      <div style={{ fontSize: 12, fontWeight: 600, color: "#6b7280", marginTop: 4 }}>
        {label}
      </div>
    </div>
  );
}

export function KpiStrip() {
  const { state, reload } = useKpiSummary();

  const kpis =
    state.status === "success"
      ? state.data
      : { pending_reviews: null, approved_reviews: null, student_responses: null, suppressed_retriggers: null };

  const source = state.status === "success" ? state.data.source : null;
  const isLoading = state.status === "idle" || state.status === "loading";

  return (
    <div
      data-testid="kpi-strip"
      style={{ marginBottom: 20 }}
    >
      <div style={{ display: "flex", justifyContent: "flex-end", alignItems: "center", marginBottom: 8, gap: 10 }}>
        {source && <SourceBadge source={source} />}
        <button
          data-testid="kpi-refresh"
          onClick={reload}
          style={{
            padding:    "4px 10px",
            fontSize:   11,
            fontWeight: 600,
            background: "#f9fafb",
            border:     "1px solid #e5e7eb",
            borderRadius: 6,
            cursor:     "pointer",
            color:      "#6b7280",
          }}
        >
          {isLoading ? "Loading…" : "Refresh"}
        </button>
      </div>

      {state.status === "error" && (
        <div
          data-testid="kpi-error"
          style={{
            background: "#fef2f2",
            border:     "1px solid #fca5a5",
            borderRadius: 8,
            padding:    "8px 14px",
            fontSize:   12,
            color:      "#b91c1c",
          }}
        >
          Could not load KPI data: {state.message}
        </div>
      )}

      <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        <KpiTile
          testId="kpi-pending-reviews"
          label="Pending Reviews"
          value={kpis.pending_reviews}
          accent="#2563eb"
          icon="⏳"
        />
        <KpiTile
          testId="kpi-approved-reviews"
          label="Approved Reviews"
          value={kpis.approved_reviews}
          accent="#16a34a"
          icon="✅"
        />
        <KpiTile
          testId="kpi-student-responses"
          label="Student Responses"
          value={kpis.student_responses}
          accent="#7c3aed"
          icon="💬"
        />
        <KpiTile
          testId="kpi-suppressed-retriggers"
          label="Suppressed Retriggers"
          value={kpis.suppressed_retriggers}
          accent="#d97706"
          icon="🔒"
        />
      </div>
    </div>
  );
}
