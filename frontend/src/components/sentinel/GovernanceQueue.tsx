import React, { useState } from "react";
import { useGovernanceReviews } from "../../hooks/useSentinelData";
import type { GovernanceStatus } from "../../types/sentinel";
import { GovernanceStatusBadge, RiskLevelBadge, ConfidenceBar, SourceBadge } from "./StatusBadge";
import { EmptyState, LoadingState, ErrorState } from "./EmptyState";

const LABEL: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  textTransform: "uppercase",
  letterSpacing: "0.07em",
  color: "#9ca3af",
  marginBottom: 2,
};

const STATUS_TABS: Array<{ key: GovernanceStatus | "all"; label: string }> = [
  { key: "all",      label: "All" },
  { key: "pending",  label: "Pending" },
  { key: "approved", label: "Approved" },
  { key: "rejected", label: "Rejected" },
  { key: "deferred", label: "Deferred" },
];

function formatDate(iso: string) {
  return new Date(iso).toLocaleString("en-US", {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

export function GovernanceQueue() {
  const [activeTab, setActiveTab] = useState<GovernanceStatus | "all">("all");
  const { state, reload } = useGovernanceReviews(activeTab === "all" ? undefined : activeTab);

  const reviews = state.status === "success" ? state.data.reviews : [];
  const source  = state.status === "success" ? state.data.source  : null;

  return (
    <section>
      {/* Section header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: "#111827" }}>
            Governance Review Queue
          </h2>
          <p style={{ margin: "4px 0 0", fontSize: 13, color: "#6b7280" }}>
            AI interpretations awaiting human review — read-only
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

      {/* Status tabs */}
      <div style={{ display: "flex", gap: 6, marginBottom: 16, flexWrap: "wrap" }}>
        {STATUS_TABS.map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setActiveTab(key)}
            style={{
              padding: "5px 14px", fontSize: 12, fontWeight: 600,
              borderRadius: 20, border: "1px solid",
              cursor: "pointer",
              borderColor: activeTab === key ? "#2563eb" : "#e5e7eb",
              background: activeTab === key ? "#2563eb" : "#fff",
              color: activeTab === key ? "#fff" : "#374151",
            }}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Content */}
      {state.status === "idle"    && <EmptyState title="Select a filter to load reviews" />}
      {state.status === "loading" && <LoadingState label="Loading governance queue..." />}
      {state.status === "error"   && <ErrorState message={state.message} />}
      {state.status === "success" && reviews.length === 0 && (
        <EmptyState
          title="No reviews found"
          body={`No ${activeTab === "all" ? "" : activeTab + " "}reviews in the queue.`}
          icon="✓"
        />
      )}
      {state.status === "success" && reviews.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {reviews.map((review) => (
            <div
              key={review.id}
              data-testid="governance-review-row"
              style={{
                background: "#fff",
                border: "1px solid #e5e7eb",
                borderLeft: `4px solid ${
                  review.status === "approved" ? "#16a34a" :
                  review.status === "rejected" ? "#dc2626" :
                  review.status === "deferred" ? "#ea580c" : "#2563eb"
                }`,
                borderRadius: 10,
                padding: "16px 20px",
              }}
            >
              {/* Row header */}
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 10 }}>
                <div>
                  <div style={{ fontWeight: 700, fontSize: 15, color: "#111827" }}>
                    {review.entity_id}
                    <span style={{ fontWeight: 400, fontSize: 12, color: "#6b7280", marginLeft: 8 }}>
                      {review.entity_type}
                    </span>
                  </div>
                  <div style={{ fontSize: 12, color: "#9ca3af", marginTop: 2 }}>
                    Interpretation #{review.interpretation_id} · Review #{review.id}
                  </div>
                </div>
                <GovernanceStatusBadge status={review.status} />
              </div>

              {/* Risk + confidence */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 10 }}>
                <div>
                  <div style={LABEL}>Risk Level</div>
                  <RiskLevelBadge level={review.risk_level} />
                </div>
                <div>
                  <div style={LABEL}>Confidence</div>
                  <ConfidenceBar value={review.confidence} />
                </div>
              </div>

              {/* Governance reason */}
              <div style={{ marginBottom: 10 }}>
                <div style={LABEL}>Governance Reason</div>
                <div style={{ fontSize: 13, color: "#374151", lineHeight: 1.5 }}>
                  {review.governance_reason}
                </div>
              </div>

              {/* Decision metadata */}
              {review.reviewed_by && (
                <div style={{ borderTop: "1px solid #f3f4f6", paddingTop: 10, marginTop: 4 }}>
                  <div style={{ fontSize: 12, color: "#6b7280" }}>
                    Reviewed by <strong>{review.reviewed_by}</strong>
                    {review.reviewed_at && <> · {formatDate(review.reviewed_at)}</>}
                  </div>
                  {review.review_notes && (
                    <div style={{ fontSize: 12, color: "#374151", marginTop: 4, fontStyle: "italic" }}>
                      "{review.review_notes}"
                    </div>
                  )}
                </div>
              )}

              {/* Created timestamp */}
              <div style={{ fontSize: 11, color: "#9ca3af", marginTop: 8 }}>
                Created {formatDate(review.created_at)}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
