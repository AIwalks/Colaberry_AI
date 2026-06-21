import { useState, useEffect, useCallback } from "react";
import type {
  GovernanceReviewsResponse,
  LatestInterpretationResponse,
  InterpretationHistoryResponse,
  ReuseMetrics,
  StudentListResponse,
  LoadState,
  GovernanceActionApprove,
  GovernanceActionReject,
  GovernanceActionDefer,
  GovernanceActionType,
  ActionState,
} from "../types/sentinel";

const API_BASE = "http://localhost:8000";
const API_KEY  = (import.meta as { env: Record<string, string> }).env.VITE_API_KEY ?? "";

async function sentinelGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "X-Api-Key": API_KEY },
  });
  if (!res.ok) throw new Error(`HTTP ${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export function useGovernanceReviews(statusFilter?: string) {
  const [state, setState] = useState<LoadState<GovernanceReviewsResponse>>({ status: "idle" });

  const load = useCallback(() => {
    setState({ status: "loading" });
    const qs = statusFilter ? `?status=${statusFilter}` : "";
    sentinelGet<GovernanceReviewsResponse>(`/sentinel/governance/reviews${qs}`)
      .then((data) => setState({ status: "success", data }))
      .catch((e: unknown) => setState({ status: "error", message: String(e) }));
  }, [statusFilter]);

  useEffect(() => { load(); }, [load]);

  return { state, reload: load };
}

export function usePendingReviews() {
  const [state, setState] = useState<LoadState<GovernanceReviewsResponse>>({ status: "idle" });

  const load = useCallback(() => {
    setState({ status: "loading" });
    sentinelGet<GovernanceReviewsResponse>("/sentinel/governance/reviews/pending")
      .then((data) => setState({ status: "success", data }))
      .catch((e: unknown) => setState({ status: "error", message: String(e) }));
  }, []);

  useEffect(() => { load(); }, [load]);

  return { state, reload: load };
}

export function useLatestInterpretation(entityId: string) {
  const [state, setState] = useState<LoadState<LatestInterpretationResponse>>({ status: "idle" });

  const load = useCallback(() => {
    if (!entityId) return;
    setState({ status: "loading" });
    sentinelGet<LatestInterpretationResponse>(`/sentinel/interpretations/${entityId}/latest`)
      .then((data) => setState({ status: "success", data }))
      .catch((e: unknown) => setState({ status: "error", message: String(e) }));
  }, [entityId]);

  useEffect(() => { load(); }, [load]);

  return { state, reload: load };
}

export function useInterpretationHistory(entityId: string) {
  const [state, setState] = useState<LoadState<InterpretationHistoryResponse>>({ status: "idle" });

  const load = useCallback(() => {
    if (!entityId) return;
    setState({ status: "loading" });
    sentinelGet<InterpretationHistoryResponse>(`/sentinel/interpretations/${entityId}/history`)
      .then((data) => setState({ status: "success", data }))
      .catch((e: unknown) => setState({ status: "error", message: String(e) }));
  }, [entityId]);

  useEffect(() => { load(); }, [load]);

  return { state, reload: load };
}

export function useReuseMetrics() {
  const [state, setState] = useState<LoadState<ReuseMetrics>>({ status: "idle" });

  const load = useCallback(() => {
    setState({ status: "loading" });
    sentinelGet<ReuseMetrics>("/sentinel/analytics/reuse-metrics")
      .then((data) => setState({ status: "success", data }))
      .catch((e: unknown) => setState({ status: "error", message: String(e) }));
  }, []);

  useEffect(() => { load(); }, [load]);

  return { state, reload: load };
}

export function useStudentList() {
  const [state, setState] = useState<LoadState<StudentListResponse>>({ status: "idle" });

  const load = useCallback(() => {
    setState({ status: "loading" });
    sentinelGet<StudentListResponse>("/sentinel/students")
      .then((data) => setState({ status: "success", data }))
      .catch((e: unknown) => setState({ status: "error", message: String(e) }));
  }, []);

  useEffect(() => { load(); }, [load]);

  return { state, reload: load };
}

export function useGovernanceAction() {
  const [state, setState] = useState<ActionState>({ status: "idle" });

  const execute = useCallback(async (
    reviewId: number,
    action:   GovernanceActionType,
    body:     GovernanceActionApprove | GovernanceActionReject | GovernanceActionDefer,
  ): Promise<boolean> => {
    setState({ status: "loading" });
    try {
      const res = await fetch(
        `${API_BASE}/sentinel/governance/reviews/${reviewId}/${action}`,
        {
          method:  "POST",
          headers: { "Content-Type": "application/json", "X-Api-Key": API_KEY },
          body:    JSON.stringify(body),
        },
      );
      if (!res.ok) {
        let detail = `HTTP ${res.status}`;
        try {
          const data = await res.json() as { detail?: string };
          if (data.detail) detail = `${detail}: ${data.detail}`;
        } catch { /* non-JSON error body — keep default detail string */ }
        setState({ status: "error", message: detail });
        return false;
      }
      setState({ status: "success" });
      return true;
    } catch (e: unknown) {
      setState({ status: "error", message: String(e) });
      return false;
    }
  }, []);

  const reset = useCallback(() => setState({ status: "idle" }), []);

  return { state, execute, reset };
}
