import React, { useState } from "react";
import { useGovernanceReviews, useGovernanceAction } from "../../hooks/useSentinelData";
import type {
  GovernanceStatus,
  GovernanceActionType,
  GovernanceActionApprove,
  GovernanceActionReject,
  GovernanceActionDefer,
} from "../../types/sentinel";
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

const ACTION_CONFIG: Record<
  GovernanceActionType,
  {
    label:            string;
    bg:               string;
    text:             string;
    border:           string;
    extraLabel:       string;
    extraRequired:    boolean;
    extraPlaceholder: string;
  }
> = {
  approve: {
    label:            "Approve",
    bg:               "#f0fdf4",
    text:             "#15803d",
    border:           "#16a34a",
    extraLabel:       "Notes",
    extraRequired:    false,
    extraPlaceholder: "Add optional review notes...",
  },
  reject: {
    label:            "Reject",
    bg:               "#fef2f2",
    text:             "#b91c1c",
    border:           "#dc2626",
    extraLabel:       "Reason",
    extraRequired:    true,
    extraPlaceholder: "Explain why this interpretation is being rejected...",
  },
  defer: {
    label:            "Defer",
    bg:               "#fff7ed",
    text:             "#c2410c",
    border:           "#ea580c",
    extraLabel:       "Deferral reason",
    extraRequired:    true,
    extraPlaceholder: "Explain why this review is being deferred...",
  },
};

function formatDate(iso: string) {
  return new Date(iso).toLocaleString("en-US", {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

export function GovernanceQueue() {
  const [activeTab, setActiveTab] = useState<GovernanceStatus | "all">("all");
  const { state, reload } = useGovernanceReviews(activeTab === "all" ? undefined : activeTab);

  // Action panel state — only one panel open at a time
  const [activePanel, setActivePanel] = useState<{
    reviewId: number;
    action:   GovernanceActionType;
  } | null>(null);
  const [reviewedBy, setReviewedBy] = useState("");
  const [extraField, setExtraField] = useState("");

  const { state: actionState, execute, reset: resetAction } = useGovernanceAction();

  const reviews = state.status === "success" ? state.data.reviews : [];
  const source  = state.status === "success" ? state.data.source  : null;

  function openPanel(reviewId: number, action: GovernanceActionType) {
    setActivePanel({ reviewId, action });
    setReviewedBy("");
    setExtraField("");
    resetAction();
  }

  function closePanel() {
    setActivePanel(null);
    setReviewedBy("");
    setExtraField("");
    resetAction();
  }

  async function submitAction() {
    if (!activePanel) return;
    const { reviewId, action } = activePanel;

    let body: GovernanceActionApprove | GovernanceActionReject | GovernanceActionDefer;
    if (action === "approve") {
      body = { reviewed_by: reviewedBy, ...(extraField.trim() ? { review_notes: extraField } : {}) };
    } else if (action === "reject") {
      body = { reviewed_by: reviewedBy, review_notes: extraField };
    } else {
      body = { reviewed_by: reviewedBy, governance_reason: extraField };
    }

    const success = await execute(reviewId, action, body);
    if (success) {
      closePanel();
      reload();
    }
  }

  const isSubmitting = actionState.status === "loading";

  function canSubmit(): boolean {
    if (!activePanel || !reviewedBy.trim()) return false;
    if (ACTION_CONFIG[activePanel.action].extraRequired && !extraField.trim()) return false;
    return true;
  }

  return (
    <section>
      {/* Section header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: "#111827" }}>
            Governance Review Queue
          </h2>
          <p style={{ margin: "4px 0 0", fontSize: 13, color: "#6b7280" }}>
            AI interpretations awaiting human review
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
              background:  activeTab === key ? "#2563eb" : "#fff",
              color:       activeTab === key ? "#fff"    : "#374151",
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
          {reviews.map((review) => {
            const isPending   = review.status === "pending";
            const panelOpen   = activePanel?.reviewId === review.id;
            const panelAction = panelOpen ? activePanel!.action : null;
            const cfg         = panelAction ? ACTION_CONFIG[panelAction] : null;

            return (
              <div
                key={review.id}
                data-testid="governance-review-row"
                style={{
                  background:  "#fff",
                  border:      "1px solid #e5e7eb",
                  borderLeft: `4px solid ${
                    review.status === "approved" ? "#16a34a" :
                    review.status === "rejected" ? "#dc2626" :
                    review.status === "deferred" ? "#ea580c" : "#2563eb"
                  }`,
                  borderRadius: 10,
                  padding:      "16px 20px",
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

                {/* Action buttons — pending reviews only, hidden when panel is open */}
                {isPending && !panelOpen && (
                  <div
                    data-testid={`action-buttons-${review.id}`}
                    style={{
                      display:    "flex",
                      gap:        8,
                      marginTop:  14,
                      paddingTop: 12,
                      borderTop:  "1px solid #f3f4f6",
                    }}
                  >
                    {(["approve", "reject", "defer"] as GovernanceActionType[]).map((action) => {
                      const btnCfg = ACTION_CONFIG[action];
                      return (
                        <button
                          key={action}
                          data-testid={`action-btn-${action}-${review.id}`}
                          onClick={() => openPanel(review.id, action)}
                          style={{
                            padding:    "6px 14px",
                            fontSize:   12,
                            fontWeight: 600,
                            borderRadius: 6,
                            border:     `1px solid ${btnCfg.border}`,
                            background: btnCfg.bg,
                            color:      btnCfg.text,
                            cursor:     "pointer",
                          }}
                        >
                          {btnCfg.label}
                        </button>
                      );
                    })}
                  </div>
                )}

                {/* Action panel — inline form, replaces buttons when open */}
                {isPending && panelOpen && cfg && (
                  <div
                    data-testid={`action-panel-${review.id}`}
                    style={{
                      marginTop:    14,
                      borderTop:    "1px solid #f3f4f6",
                      paddingTop:   12,
                      background:   "#f9fafb",
                      borderRadius: 8,
                      padding:      16,
                    }}
                  >
                    <div style={{ fontWeight: 600, fontSize: 13, color: "#111827", marginBottom: 12 }}>
                      {cfg.label} review #{review.id}
                    </div>

                    {/* Reviewer email */}
                    <div style={{ marginBottom: 10 }}>
                      <label
                        htmlFor={`reviewed-by-${review.id}`}
                        style={{ fontSize: 12, fontWeight: 600, color: "#374151", display: "block", marginBottom: 4 }}
                      >
                        Reviewer email <span style={{ color: "#dc2626" }}>*</span>
                      </label>
                      <input
                        id={`reviewed-by-${review.id}`}
                        data-testid="input-reviewed-by"
                        type="text"
                        value={reviewedBy}
                        onChange={(e) => setReviewedBy(e.target.value)}
                        placeholder="reviewer@colaberry.com"
                        disabled={isSubmitting}
                        style={{
                          width:      "100%",
                          padding:    "7px 10px",
                          fontSize:   13,
                          border:     "1px solid #d1d5db",
                          borderRadius: 6,
                          background: isSubmitting ? "#f3f4f6" : "#fff",
                          color:      "#111827",
                          boxSizing:  "border-box",
                        }}
                      />
                    </div>

                    {/* Extra field — review_notes (approve/reject) or governance_reason (defer) */}
                    <div style={{ marginBottom: 12 }}>
                      <label
                        htmlFor={`extra-field-${review.id}`}
                        style={{ fontSize: 12, fontWeight: 600, color: "#374151", display: "block", marginBottom: 4 }}
                      >
                        {cfg.extraLabel}
                        {cfg.extraRequired
                          ? <span style={{ color: "#dc2626" }}> *</span>
                          : <span style={{ fontWeight: 400, color: "#9ca3af" }}> (optional)</span>
                        }
                      </label>
                      <textarea
                        id={`extra-field-${review.id}`}
                        data-testid="input-extra-field"
                        value={extraField}
                        onChange={(e) => setExtraField(e.target.value)}
                        placeholder={cfg.extraPlaceholder}
                        disabled={isSubmitting}
                        rows={3}
                        style={{
                          width:      "100%",
                          padding:    "7px 10px",
                          fontSize:   13,
                          border:     "1px solid #d1d5db",
                          borderRadius: 6,
                          background: isSubmitting ? "#f3f4f6" : "#fff",
                          color:      "#111827",
                          resize:     "vertical",
                          boxSizing:  "border-box",
                        }}
                      />
                    </div>

                    {/* Error banner */}
                    {actionState.status === "error" && (
                      <div
                        data-testid="action-error"
                        style={{
                          fontSize:     12,
                          color:        "#b91c1c",
                          background:   "#fef2f2",
                          border:       "1px solid #fca5a5",
                          borderRadius: 6,
                          padding:      "8px 12px",
                          marginBottom: 12,
                        }}
                      >
                        {actionState.message}
                      </div>
                    )}

                    {/* Submit / Cancel */}
                    <div style={{ display: "flex", gap: 8 }}>
                      <button
                        data-testid="submit-action"
                        onClick={submitAction}
                        disabled={!canSubmit() || isSubmitting}
                        style={{
                          padding:    "7px 16px",
                          fontSize:   13,
                          fontWeight: 600,
                          borderRadius: 6,
                          border:     `1px solid ${cfg.border}`,
                          background: (!canSubmit() || isSubmitting) ? "#e5e7eb" : cfg.bg,
                          color:      (!canSubmit() || isSubmitting) ? "#9ca3af" : cfg.text,
                          cursor:     (!canSubmit() || isSubmitting) ? "not-allowed" : "pointer",
                        }}
                      >
                        {isSubmitting ? "Submitting..." : cfg.label}
                      </button>
                      <button
                        data-testid="cancel-action"
                        onClick={closePanel}
                        disabled={isSubmitting}
                        style={{
                          padding:    "7px 16px",
                          fontSize:   13,
                          fontWeight: 600,
                          borderRadius: 6,
                          border:     "1px solid #e5e7eb",
                          background: "#fff",
                          color:      "#374151",
                          cursor:     isSubmitting ? "not-allowed" : "pointer",
                        }}
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
