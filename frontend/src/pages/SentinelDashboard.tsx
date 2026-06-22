import React, { useState } from "react";
import { GovernanceQueue } from "../components/sentinel/GovernanceQueue";
import { InterpretationTimeline } from "../components/sentinel/InterpretationTimeline";
import { ReuseMetricsPanel } from "../components/sentinel/ReuseMetrics";
import { StudentDetailView } from "../components/sentinel/StudentDetailView";
import { RiskEvolution } from "../components/sentinel/RiskEvolution";
import { StudentResponsesPanel } from "../components/sentinel/StudentResponsesPanel";
import { KpiStrip } from "../components/sentinel/KpiStrip";
import {
  useGovernanceReviews,
  useInterpretationHistory,
  useLatestInterpretation,
  useReuseMetrics,
  useStudentList,
} from "../hooks/useSentinelData";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type TabKey = "governance" | "timeline" | "metrics" | "student" | "risk" | "responses";

const TABS: Array<{ key: TabKey; label: string; icon: string }> = [
  { key: "governance", label: "Governance Queue",          icon: "⚖" },
  { key: "timeline",   label: "Interpretation Timeline",   icon: "⏱" },
  { key: "metrics",    label: "Reuse & Metrics",           icon: "📊" },
  { key: "student",    label: "Student Detail",            icon: "🎓" },
  { key: "risk",       label: "Risk Evolution",            icon: "📈" },
  { key: "responses",  label: "Student Responses",         icon: "💬" },
];

// Student options are loaded dynamically from /sentinel/students

// ---------------------------------------------------------------------------
// Shared card wrapper
// ---------------------------------------------------------------------------

function SectionCard({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        background: "#f9fafb",
        border: "1px solid #e5e7eb",
        borderRadius: 12,
        padding: 24,
        minHeight: 300,
      }}
    >
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Observability notice banner
// ---------------------------------------------------------------------------

function ObservabilityBanner() {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 10,
        background: "#eff6ff",
        border: "1px solid #bfdbfe",
        borderRadius: 8,
        padding: "10px 16px",
        marginBottom: 20,
        fontSize: 12,
        color: "#1e40af",
      }}
    >
      <span style={{ fontSize: 16 }}>🔭</span>
      <span>
        <strong>Governed shadow mode.</strong>{" "}
        Approve, reject, and defer actions are available and fully audited. Outbound student-facing messages are suppressed in this environment.
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main dashboard
// ---------------------------------------------------------------------------

const _API_BASE = "http://localhost:8000";
const _API_KEY = (import.meta as { env: Record<string, string> }).env.VITE_API_KEY ?? "";

export function SentinelDashboard() {
  const [activeTab, setActiveTab] = useState<TabKey>("governance");
  const [selectedStudent, setSelectedStudent] = useState<string>("");
  const [evalStatus, setEvalStatus] = useState<"idle" | "running" | "done" | "error">("idle");
  const [evalMessage, setEvalMessage] = useState<string>("");

  const studentListResult = useStudentList();
  const studentOptions =
    studentListResult.state.status === "success"
      ? studentListResult.state.data.students
      : [];

  // Set the initial selection once the list arrives
  React.useEffect(() => {
    if (!selectedStudent && studentOptions.length > 0) {
      setSelectedStudent(studentOptions[0].user_id);
    }
  }, [selectedStudent, studentOptions]);

  const metricsResult    = useReuseMetrics();
  const latestResult     = useLatestInterpretation(selectedStudent);
  const historyResult    = useInterpretationHistory(selectedStudent);
  const reviewsResult    = useGovernanceReviews();
  const responsesUserId = selectedStudent ? parseInt(selectedStudent.replace(/\D/g, ""), 10) || undefined : undefined;

  // Reset evaluation banner when the selected student changes
  React.useEffect(() => {
    setEvalStatus("idle");
    setEvalMessage("");
  }, [selectedStudent]);

  const handleEvaluate = () => {
    if (!selectedStudent) return;
    setEvalStatus("running");
    setEvalMessage("");
    fetch(`${_API_BASE}/sentinel/evaluate`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Api-Key": _API_KEY },
      body: JSON.stringify({ entity_id: selectedStudent, entity_type: "student", dimension: "engagement" }),
    })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status} ${r.statusText}`);
        return r.json() as Promise<{
          evaluated: boolean;
          generated_new_interpretation: boolean;
          used_cached_interpretation: boolean;
          message?: string;
          evaluation_result?: { reason?: string };
        }>;
      })
      .then((data) => {
        let nextStatus: "done" | "error";
        let msg: string;
        if (data.generated_new_interpretation) {
          nextStatus = "done";
          msg = "New interpretation generated and queued for governance review.";
        } else if (data.used_cached_interpretation) {
          nextStatus = "done";
          msg = "No material change — existing interpretation is current.";
        } else {
          nextStatus = "error";
          msg = data.message || data.evaluation_result?.reason || "Evaluation failed — check server logs.";
        }
        setEvalStatus(nextStatus);
        setEvalMessage(msg);
        if (data.evaluated) {
          latestResult.reload();
          historyResult.reload();
          reviewsResult.reload();
        }
      })
      .catch((e: unknown) => {
        setEvalStatus("error");
        setEvalMessage(String(e));
      });
  };

  const studentReviews = {
    ...reviewsResult,
    state:
      reviewsResult.state.status === "success"
        ? {
            ...reviewsResult.state,
            data: {
              ...reviewsResult.state.data,
              reviews: reviewsResult.state.data.reviews.filter(
                (r) => r.entity_id === selectedStudent
              ),
            },
          }
        : reviewsResult.state,
  };

  return (
    <main
      style={{
        fontFamily: "sans-serif",
        maxWidth: 1100,
        margin: "0 auto",
        padding: "32px 24px 64px",
      }}
    >
      <style>{`@keyframes sentinel-spin { to { transform: rotate(360deg); } }`}</style>

      {/* Page header */}
      <div style={{ marginBottom: 24 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
          <span style={{ fontSize: 22, fontWeight: 800, color: "#111827" }}>
            Sentinel Dashboard
          </span>
          <span style={{
            fontSize: 10, fontWeight: 700, padding: "3px 10px",
            borderRadius: 10, background: "#faf5ff", color: "#7c3aed",
            border: "1px solid #ddd6fe", letterSpacing: "0.06em",
          }}>
            SHADOW MODE
          </span>
        </div>
        <p style={{ margin: 0, color: "#6b7280", fontSize: 14 }}>
          Operational visibility into AI interpretations, governance workflows, and pipeline behavior.
        </p>
      </div>

      <ObservabilityBanner />

      <KpiStrip />

      {/* Student picker — shared by Student Detail, Risk Evolution, and Responses tabs */}
      {(activeTab === "student" || activeTab === "timeline" || activeTab === "risk" || activeTab === "responses") && (
        <div style={{ marginBottom: 20 }}>
          <label htmlFor="student-picker" style={{ fontSize: 13, color: "#374151", display: "block", marginBottom: 6, fontWeight: 600 }}>
            Student
          </label>
          <select
            id="student-picker"
            value={selectedStudent}
            onChange={(e) => setSelectedStudent(e.target.value)}
            disabled={studentListResult.state.status === "loading" || studentOptions.length === 0}
            style={{
              padding: "8px 12px", fontSize: 14, border: "1px solid #d1d5db",
              borderRadius: 6, background: "#fff", color: "#111827",
              cursor: "pointer", minWidth: 200,
            }}
          >
            {studentListResult.state.status === "loading" && (
              <option value="">Loading students…</option>
            )}
            {studentListResult.state.status === "error" && (
              <option value="">Error loading students</option>
            )}
            {studentOptions.map((s) => (
              <option key={s.user_id} value={s.user_id}>
                {s.display_label}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Tab navigation */}
      <div
        style={{
          display: "flex", gap: 4, marginBottom: 20,
          borderBottom: "2px solid #e5e7eb", paddingBottom: 0, flexWrap: "wrap",
        }}
      >
        {TABS.map(({ key, label, icon }) => (
          <button
            key={key}
            onClick={() => setActiveTab(key)}
            style={{
              padding: "10px 18px",
              fontSize: 13,
              fontWeight: 600,
              border: "none",
              borderBottom: activeTab === key ? "2px solid #2563eb" : "2px solid transparent",
              background: "none",
              cursor: "pointer",
              color: activeTab === key ? "#2563eb" : "#6b7280",
              marginBottom: -2,
              whiteSpace: "nowrap",
            }}
          >
            {icon} {label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === "governance" && (
        <SectionCard>
          <GovernanceQueue />
        </SectionCard>
      )}

      {activeTab === "timeline" && (
        <SectionCard>
          <div style={{ marginBottom: 20 }}>
            <h2 style={{ margin: "0 0 4px", fontSize: 18, fontWeight: 700, color: "#111827" }}>
              AI Interpretation Timeline
            </h2>
            <p style={{ margin: 0, fontSize: 13, color: "#6b7280" }}>
              Full interpretation history for {selectedStudent} — shows active, invalidated, and stale records
            </p>
          </div>
          <InterpretationTimeline
            history={historyResult.state.status === "success" ? historyResult.state.data.history : []}
            loading={historyResult.state.status === "loading" || historyResult.state.status === "idle"}
            error={historyResult.state.status === "error" ? historyResult.state.message : undefined}
            entityId={selectedStudent}
          />
        </SectionCard>
      )}

      {activeTab === "metrics" && (
        <SectionCard>
          <ReuseMetricsPanel state={metricsResult.state} onReload={metricsResult.reload} />
        </SectionCard>
      )}

      {activeTab === "student" && (
        <SectionCard>
          {/* Evaluation controls */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 20 }}>
            <div>
              <h2 style={{ margin: "0 0 4px", fontSize: 18, fontWeight: 700, color: "#111827" }}>
                Student Detail
              </h2>
              <p style={{ margin: 0, fontSize: 13, color: "#6b7280" }}>
                AI interpretation and governance history for {selectedStudent || "—"}
              </p>
            </div>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 6 }}>
              <button
                onClick={handleEvaluate}
                disabled={!selectedStudent || evalStatus === "running"}
                style={{
                  padding: "8px 16px", fontSize: 13, fontWeight: 600,
                  background: evalStatus === "running" ? "#e5e7eb" : "#2563eb",
                  color: evalStatus === "running" ? "#6b7280" : "#fff",
                  border: "none", borderRadius: 6, cursor: evalStatus === "running" ? "not-allowed" : "pointer",
                  whiteSpace: "nowrap",
                }}
              >
                {evalStatus === "running" ? "Evaluating…" : "Run Evaluation"}
              </button>
              {evalStatus === "done" && (
                <span style={{ fontSize: 12, color: evalMessage.startsWith("New") ? "#059669" : "#6b7280" }}>
                  {evalMessage}
                </span>
              )}
              {evalStatus === "error" && (
                <span style={{ fontSize: 12, color: "#dc2626" }}>{evalMessage}</span>
              )}
            </div>
          </div>
          <StudentDetailView
            entityId={selectedStudent}
            latestState={latestResult.state}
            reviewsState={studentReviews.state}
          />
        </SectionCard>
      )}

      {activeTab === "risk" && (
        <SectionCard>
          <div style={{ marginBottom: 20 }}>
            <h2 style={{ margin: "0 0 4px", fontSize: 18, fontWeight: 700, color: "#111827" }}>
              Risk Evolution Tracking
            </h2>
            <p style={{ margin: 0, fontSize: 13, color: "#6b7280" }}>
              Confidence progression, risk escalation timeline, and cross-dimensional deterioration for {selectedStudent}
            </p>
          </div>
          <RiskEvolution entityId={selectedStudent} historyState={historyResult.state} />
        </SectionCard>
      )}

      {activeTab === "responses" && (
        <SectionCard>
          <StudentResponsesPanel userId={responsesUserId} />
        </SectionCard>
      )}
    </main>
  );
}
