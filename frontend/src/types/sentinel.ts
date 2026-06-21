export type GovernanceStatus = "pending" | "approved" | "rejected" | "deferred";
export type RiskLevel = "low" | "medium" | "high" | "critical" | "unknown";
export type GeneratedBy = "claude" | "fallback" | "deterministic_engine";

export interface GovernanceReview {
  id: number;
  created_at: string;
  updated_at: string;
  interpretation_id: number;
  entity_id: string;
  entity_type: string;
  status: GovernanceStatus;
  reviewed_by: string | null;
  reviewed_at: string | null;
  review_notes: string | null;
  governance_reason: string;
  risk_level: RiskLevel;
  confidence: number;
  is_active: boolean;
}

export interface GovernanceReviewsResponse {
  reviews: GovernanceReview[];
  total: number;
  source: "db" | "mock";
}

export interface AIInterpretation {
  id: number;
  created_at: string;
  updated_at: string;
  invalidated_at: string | null;
  entity_id: string;
  entity_type: string;
  dimension: string;
  interpretation_version: number;
  confidence: number;
  risk_level: RiskLevel;
  summary: string;
  recommended_action: string | null;
  explainability: string[];
  generated_by: GeneratedBy;
  model_name: string | null;
  source_metrics_hash: string | null;
  stale_after: string | null;
  is_active: boolean;
  invalidation_reason: string | null;
}

export interface LatestInterpretationResponse {
  entity_id: string;
  latest: AIInterpretation | null;
  source: "db" | "mock";
}

export interface InterpretationHistoryResponse {
  entity_id: string;
  history: AIInterpretation[];
  total: number;
  source: "db" | "mock";
}

export interface MaterialChangeTriggers {
  confidence_delta: number;
  risk_escalation: number;
  new_fingerprint: number;
  stale: number;
  cross_dimension: number;
  reuse_default: number;
}

export interface ReuseMetrics {
  total_interpretations: number;
  active_interpretations: number;
  invalidated_interpretations: number;
  by_risk_level: Record<RiskLevel, number>;
  by_generated_by: Record<GeneratedBy, number>;
  material_change_triggers?: MaterialChangeTriggers;
  governance_summary: {
    pending: number;
    approved: number;
    rejected: number;
    deferred: number;
    total: number;
  };
  note: string;
  source: "db" | "mock";
}

export interface StudentOption {
  user_id: string;
  user_name: string;
  display_label: string;
  attendance: number | null;
  active_status: string | null;
  last_activity_days: number | null;
  is_class_active: number | null;
}

export interface StudentListResponse {
  students: StudentOption[];
  total: number;
  source: "db" | "mock";
}

export type LoadState<T> =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "success"; data: T }
  | { status: "error"; message: string };

// ---------------------------------------------------------------------------
// Governance action request bodies (mirrors backend Pydantic schemas)
// ---------------------------------------------------------------------------

export interface GovernanceActionApprove {
  reviewed_by:  string;
  review_notes?: string;
}

export interface GovernanceActionReject {
  reviewed_by:  string;
  review_notes: string;
}

export interface GovernanceActionDefer {
  reviewed_by:       string;
  governance_reason: string;
}

export type GovernanceActionType = "approve" | "reject" | "defer";

export type ActionState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "success" }
  | { status: "error"; message: string };
