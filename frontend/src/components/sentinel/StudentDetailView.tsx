import React from "react";
import type { AIInterpretation, GovernanceReview } from "../../types/sentinel";
import { RiskLevelBadge, ConfidenceBar, GovernanceStatusBadge, SourceBadge } from "./StatusBadge";
import { LoadingState, ErrorState, EmptyState } from "./EmptyState";
import type { LoadState } from "../../types/sentinel";

const LABEL: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  textTransform: "uppercase",
  letterSpacing: "0.07em",
  color: "#9ca3af",
  marginBottom: 4,
};

function formatDate(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-US", {
    month: "short", day: "numeric", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

// ---------------------------------------------------------------------------
// Latest interpretation card
// ---------------------------------------------------------------------------

function LatestInterpCard({ interp, source }: { interp: AIInterpretation; source: "db" | "mock" }) {
  const isStale = interp.stale_after && new Date(interp.stale_after) < new Date();

  return (
    <div style={{
      background: "#fff", border: "1px solid #e5e7eb",
      borderLeft: "4px solid #2563eb", borderRadius: 10, padding: "20px 24px",
    }}>
      {/* Header row */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 }}>
        <div>
          <div style={{ fontWeight: 700, fontSize: 16, color: "#111827" }}>
            Latest AI Interpretation
          </div>
          <div style={{ fontSize: 12, color: "#6b7280", marginTop: 3 }}>
            #{interp.id} · v{interp.interpretation_version} · {interp.dimension}
            {interp.model_name && <> · {interp.model_name}</>}
          </div>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <SourceBadge source={source} />
          {isStale && (
            <span style={{
              fontSize: 11, fontWeight: 700, padding: "3px 10px",
              borderRadius: 20, background: "#fffbeb", color: "#92400e",
            }}>
              STALE
            </span>
          )}
        </div>
      </div>

      {/* Risk + confidence */}
      <div style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: 16, alignItems: "center", marginBottom: 16 }}>
        <RiskLevelBadge level={interp.risk_level} />
        <ConfidenceBar value={interp.confidence} />
      </div>

      {/* Summary */}
      <div style={{ marginBottom: 16 }}>
        <div style={LABEL}>Summary</div>
        <div style={{ fontSize: 14, color: "#111827", lineHeight: 1.6 }}>{interp.summary}</div>
      </div>

      {/* Explainability trace */}
      {interp.explainability.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <div style={LABEL}>Explainability Trace</div>
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {interp.explainability.map((item, i) => (
              <li key={i} style={{ fontSize: 13, color: "#374151", lineHeight: 1.6, marginBottom: 4 }}>
                {item}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Recommended action */}
      {interp.recommended_action && (
        <div style={{
          borderLeft: "3px solid #2563eb", paddingLeft: 12, marginBottom: 16,
        }}>
          <div style={LABEL}>Recommended Action</div>
          <div style={{ fontSize: 14, color: "#111827", lineHeight: 1.6 }}>
            {interp.recommended_action}
          </div>
        </div>
      )}

      {/* Lifecycle metadata */}
      <div style={{
        borderTop: "1px solid #f3f4f6", paddingTop: 12, marginTop: 4,
        display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10,
      }}>
        <div>
          <div style={LABEL}>Generated At</div>
          <div style={{ fontSize: 12, color: "#374151" }}>{formatDate(interp.created_at)}</div>
        </div>
        <div>
          <div style={LABEL}>Fresh Until</div>
          <div style={{ fontSize: 12, color: isStale ? "#b45309" : "#374151" }}>
            {formatDate(interp.stale_after)}
          </div>
        </div>
        <div>
          <div style={LABEL}>Source Hash</div>
          <div style={{
            fontSize: 11, color: "#9ca3af", fontFamily: "monospace",
            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
          }}>
            {interp.source_metrics_hash ? interp.source_metrics_hash.slice(0, 16) + "…" : "—"}
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Governance history table
// ---------------------------------------------------------------------------

function GovernanceHistoryTable({ reviews }: { reviews: GovernanceReview[] }) {
  if (reviews.length === 0) {
    return (
      <EmptyState
        title="No governance history"
        body="Governance reviews for this student will appear here once interpretations are generated."
        icon="📋"
      />
    );
  }

  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
        <thead>
          <tr style={{ background: "#f9fafb" }}>
            {["Review #", "Interp #", "Status", "Risk", "Confidence", "Reviewed By", "Created"].map((h) => (
              <th key={h} style={{
                padding: "8px 12px", textAlign: "left", fontSize: 11, fontWeight: 700,
                textTransform: "uppercase", letterSpacing: "0.06em", color: "#6b7280",
                borderBottom: "1px solid #e5e7eb", whiteSpace: "nowrap",
              }}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {reviews.map((r) => (
            <tr key={r.id} style={{ borderBottom: "1px solid #f3f4f6" }}>
              <td style={{ padding: "10px 12px", color: "#374151" }}>#{r.id}</td>
              <td style={{ padding: "10px 12px", color: "#374151" }}>#{r.interpretation_id}</td>
              <td style={{ padding: "10px 12px" }}><GovernanceStatusBadge status={r.status} /></td>
              <td style={{ padding: "10px 12px" }}><RiskLevelBadge level={r.risk_level} /></td>
              <td style={{ padding: "10px 12px", color: "#374151" }}>
                {Math.round(r.confidence * 100)}%
              </td>
              <td style={{ padding: "10px 12px", color: "#6b7280" }}>
                {r.reviewed_by ?? <span style={{ color: "#d1d5db" }}>—</span>}
              </td>
              <td style={{ padding: "10px 12px", color: "#6b7280", whiteSpace: "nowrap" }}>
                {formatDate(r.created_at)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Public component
// ---------------------------------------------------------------------------

interface StudentDetailViewProps {
  entityId: string;
  latestState: LoadState<{ entity_id: string; latest: AIInterpretation | null; source: "db" | "mock" }>;
  reviewsState: LoadState<{ reviews: GovernanceReview[]; total: number; source: "db" | "mock" }>;
}

export function StudentDetailView({ entityId, latestState, reviewsState }: StudentDetailViewProps) {
  return (
    <div>
      {/* Latest interpretation */}
      <div style={{ marginBottom: 24 }}>
        <h3 style={{ margin: "0 0 12px", fontSize: 15, fontWeight: 700, color: "#374151" }}>
          Current Interpretation — {entityId}
        </h3>
        {(latestState.status === "idle" || latestState.status === "loading") && (
          <LoadingState label={`Loading interpretation for ${entityId}...`} />
        )}
        {latestState.status === "error" && <ErrorState message={latestState.message} />}
        {latestState.status === "success" && !latestState.data.latest && (
          <EmptyState
            title="No active interpretation"
            body="Run an orchestration evaluation to generate the first interpretation for this student."
            icon="🔍"
          />
        )}
        {latestState.status === "success" && latestState.data.latest && (
          <LatestInterpCard interp={latestState.data.latest} source={latestState.data.source} />
        )}
      </div>

      {/* Governance history */}
      <div>
        <h3 style={{ margin: "0 0 12px", fontSize: 15, fontWeight: 700, color: "#374151" }}>
          Governance History
        </h3>
        <div style={{
          background: "#fff", border: "1px solid #e5e7eb",
          borderRadius: 10, overflow: "hidden",
        }}>
          {(reviewsState.status === "idle" || reviewsState.status === "loading") && (
            <LoadingState label="Loading governance history..." />
          )}
          {reviewsState.status === "error" && <ErrorState message={reviewsState.message} />}
          {reviewsState.status === "success" && (
            <GovernanceHistoryTable reviews={reviewsState.data.reviews} />
          )}
        </div>
      </div>
    </div>
  );
}
