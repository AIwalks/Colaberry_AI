import React, { useEffect, useState } from "react";
import { SentinelDashboard } from "./pages/SentinelDashboard";
import { useStudentList } from "./hooks/useSentinelData";

// ---------------------------------------------------------------------------
// Insight Generator (original view — preserved unchanged)
// ---------------------------------------------------------------------------

interface Insight {
  id: number;
  title: string;
  body: string;
  insight_type: string;
  entity_type: string;
  entity_id: string;
  confidence: number;
  explanation?: string;
  recommended_action?: string;
  explainability?: string[];
  risk_level?: string;
}

function InsightCard({ insight }: { insight: Insight }) {
  const isKpi       = insight.insight_type === "kpi";
  const accentColor = isKpi ? "#16a34a" : "#dc2626";
  const badgeBg     = isKpi ? "#dcfce7" : "#fee2e2";
  const badgeColor  = isKpi ? "#15803d" : "#b91c1c";
  const pct         = (insight.confidence * 100).toFixed(0);

  const sectionLabel: React.CSSProperties = {
    fontSize: 11,
    fontWeight: 700,
    textTransform: "uppercase",
    letterSpacing: "0.07em",
    color: "#9ca3af",
    marginBottom: 4,
  };

  const sectionBody: React.CSSProperties = {
    fontSize: 14,
    lineHeight: 1.6,
    color: "#374151",
    margin: 0,
  };

  const typeBadge: React.CSSProperties = {
    fontSize: 11,
    fontWeight: 700,
    textTransform: "uppercase",
    letterSpacing: "0.06em",
    padding: "3px 10px",
    borderRadius: 20,
    background: badgeBg,
    color: badgeColor,
    whiteSpace: "nowrap",
    marginLeft: 12,
    flexShrink: 0,
  };

  return (
    <div
      style={{
        background: "#ffffff",
        border: "1px solid #e5e7eb",
        borderLeft: `4px solid ${accentColor}`,
        borderRadius: 10,
        padding: "20px 24px",
        boxShadow: "0 2px 8px rgba(0,0,0,0.07)",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div style={{ fontWeight: 700, fontSize: 17, color: "#111827", lineHeight: 1.3 }}>
          {insight.title}
        </div>
        <span style={typeBadge}>{insight.insight_type}</span>
      </div>

      <div style={{ fontSize: 12, color: "#6b7280", marginTop: 6 }}>
        Entity: <span style={{ fontWeight: 600 }}>{insight.entity_type}</span>
        {" · "}ID: <span style={{ fontWeight: 600 }}>{insight.entity_id}</span>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 12 }}>
        <span style={{ fontSize: 12, color: "#6b7280" }}>Confidence</span>
        <span style={{ fontSize: 12, fontWeight: 700, padding: "3px 10px", borderRadius: 20, background: badgeBg, color: badgeColor }}>
          {pct}%
        </span>
      </div>

      <div style={{ borderTop: "1px solid #f3f4f6", margin: "16px 0" }} />

      {Array.isArray(insight.explainability) && insight.explainability.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <div style={sectionLabel}>Explainability Trace</div>
          <ul style={{ margin: 0, paddingLeft: 18, listStyleType: "disc" }}>
            {insight.explainability.map((item, i) => (
              <li key={i} style={{ ...sectionBody, marginBottom: 4 }}>{item}</li>
            ))}
          </ul>
        </div>
      )}

      {insight.explanation && !(Array.isArray(insight.explainability) && insight.explainability.length > 0) && (
        <div style={{ marginBottom: 12 }}>
          <div style={sectionLabel}>Explanation</div>
          <p style={sectionBody}>{insight.explanation}</p>
        </div>
      )}

      {insight.recommended_action && (
        <div style={{ borderLeft: `3px solid ${accentColor}`, paddingLeft: 12 }}>
          <div style={sectionLabel}>Recommended Action</div>
          <p style={sectionBody}>{insight.recommended_action}</p>
        </div>
      )}

      {!insight.explanation && !insight.recommended_action && !(Array.isArray(insight.explainability) && insight.explainability.length > 0) && (
        <p style={{ fontSize: 13, color: "#4b5563", margin: 0, lineHeight: 1.5 }}>{insight.body}</p>
      )}
    </div>
  );
}

function ResultsPanel({ insights, filter }: { insights: Insight[]; filter: "all" | "kpi" | "risk" | "ai" }) {
  const visible = insights
    .filter((i) => filter === "all" || i.insight_type === filter)
    .slice()
    .sort((a, b) => b.confidence - a.confidence);

  const kpiCount  = visible.filter((i) => i.insight_type === "kpi").length;
  const riskCount = visible.filter((i) => i.insight_type === "risk").length;
  const aiCount   = visible.filter((i) => i.insight_type === "ai").length;

  return (
    <>
      <p style={{ fontSize: 13, color: "#6b7280", margin: "0 0 12px 0" }}>
        {visible.length} Insight{visible.length !== 1 ? "s" : ""}
        {" "}&bull; {kpiCount} KPI &bull; {riskCount} Risk{aiCount > 0 ? ` · ${aiCount} AI` : ""}
      </p>
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        {visible.length === 0 ? (
          <p style={{ color: "#9ca3af", margin: 0 }}>No {filter.toUpperCase()} insights found.</p>
        ) : (
          visible.map((insight) => <InsightCard key={insight.id} insight={insight} />)
        )}
      </div>
    </>
  );
}

function InsightGenerator() {
  const [insights, setInsights]         = useState<Insight[]>([]);
  const [loadingMode, setLoadingMode]   = useState<"standard" | "ai" | null>(null);
  const [filter, setFilter]             = useState<"all" | "kpi" | "risk" | "ai">("all");
  const [error, setError]               = useState<string | null>(null);
  const [selectedStudentId, setSelectedStudentId] = useState("");

  const studentListResult = useStudentList();
  const studentOptions =
    studentListResult.state.status === "success"
      ? studentListResult.state.data.students
      : [];

  // Auto-select the first student once the list loads
  useEffect(() => {
    if (!selectedStudentId && studentOptions.length > 0) {
      setSelectedStudentId(studentOptions[0].user_id);
    }
  }, [selectedStudentId, studentOptions]);

  const loading = loadingMode !== null;

  async function generateInsights(endpoint: "/insight/generate" | "/insight/generate/ai") {
    setLoadingMode(endpoint === "/insight/generate" ? "standard" : "ai");
    setError(null);
    try {
      const res = await fetch(`http://localhost:8000${endpoint}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Api-Key": (import.meta as { env: Record<string, string> }).env.VITE_API_KEY ?? "",
        },
        body: JSON.stringify({ entity_id: selectedStudentId, entity_type: "student" }),
      });
      if (!res.ok) {
        setError(`Request failed: HTTP ${res.status} ${res.statusText}`);
        return;
      }
      const data = await res.json() as { insights?: Insight[] };
      setInsights(data.insights ?? []);
    } catch {
      setError("Could not reach the server. Check that the backend is running.");
    } finally {
      setLoadingMode(null);
    }
  }

  return (
    <main style={{ fontFamily: "sans-serif", maxWidth: 640, margin: "0 auto", padding: "32px 24px" }}>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      <h1 style={{ marginBottom: 8 }}>Insight Generator</h1>
      <p style={{ color: "#555", marginBottom: 32 }}>Generate insights from KPI and fingerprint data.</p>

      <div style={{ marginBottom: 16 }}>
        <label style={{ fontSize: 13, color: "#374151", display: "block", marginBottom: 6 }}>Student</label>
        <select
          value={selectedStudentId}
          onChange={(e) => setSelectedStudentId(e.target.value)}
          disabled={loading}
          style={{
            padding: "8px 12px", fontSize: 14, border: "1px solid #d1d5db",
            borderRadius: 6, background: "#fff", color: "#111827",
            cursor: loading ? "not-allowed" : "pointer", minWidth: 220,
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
              {s.display_label} ({s.user_id})
            </option>
          ))}
        </select>
      </div>

      <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
        <button
          onClick={() => generateInsights("/insight/generate")}
          disabled={loading}
          style={{
            padding: "10px 20px", fontSize: 14,
            background: loadingMode === "standard" ? "#93c5fd" : "#2563eb",
            color: "#fff", border: "none", borderRadius: 6, cursor: loading ? "not-allowed" : "pointer",
          }}
        >
          {loadingMode === "standard" ? "Generating..." : "Generate Standard Insights"}
        </button>
        <button
          onClick={() => generateInsights("/insight/generate/ai")}
          disabled={loading}
          style={{
            padding: "10px 20px", fontSize: 14,
            background: loadingMode === "ai" ? "#a78bfa" : "#7c3aed",
            color: "#fff", border: "none", borderRadius: 6, cursor: loading ? "not-allowed" : "pointer",
          }}
        >
          {loadingMode === "ai" ? "Generating..." : "Generate AI Insights"}
        </button>
      </div>
      <p style={{ fontSize: 12, color: "#9ca3af", margin: "8px 0 0 0" }}>
        Standard uses deterministic KPI/risk rules. AI uses Claude-generated explainability.
      </p>

      {insights.length > 0 && (() => {
        const hasAi = insights.some((i) => i.insight_type === "ai");
        const tabs: Array<"all" | "kpi" | "risk" | "ai"> = hasAi
          ? ["all", "kpi", "risk", "ai"]
          : ["all", "kpi", "risk"];
        return (
          <div style={{ display: "flex", gap: 8, marginTop: 24 }}>
            {tabs.map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                style={{
                  padding: "6px 16px", fontSize: 13, fontWeight: 600,
                  borderRadius: 6, border: "1px solid", cursor: "pointer",
                  borderColor: filter === f ? "#2563eb" : "#d1d5db",
                  background: filter === f ? "#2563eb" : "#fff",
                  color: filter === f ? "#fff" : "#374151",
                }}
              >
                {f === "all" ? "All" : f.toUpperCase()}
              </button>
            ))}
          </div>
        );
      })()}

      <div style={{
        marginTop: 16, padding: 24, background: "#f9fafb",
        border: "1px solid #e5e7eb", borderRadius: 8, minHeight: 120,
      }}>
        {loading ? (
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "32px 0" }}>
            <div style={{
              width: 36, height: 36, border: "3px solid #e5e7eb",
              borderTop: "3px solid #2563eb", borderRadius: "50%",
              animation: "spin 0.75s linear infinite",
            }} />
            <p style={{ color: "#6b7280", fontSize: 13, marginTop: 12, marginBottom: 0 }}>Generating insights...</p>
          </div>
        ) : error ? (
          <div style={{
            background: "#fef2f2", border: "1px solid #fca5a5",
            borderLeft: "4px solid #dc2626", borderRadius: 8, padding: "12px 16px",
          }}>
            <div style={{ fontWeight: 700, fontSize: 13, color: "#b91c1c", marginBottom: 4 }}>Request failed</div>
            <div style={{ fontSize: 13, color: "#7f1d1d" }}>{error}</div>
          </div>
        ) : insights.length === 0 ? (
          <p style={{ color: "#9ca3af", margin: 0 }}>No insights generated yet.</p>
        ) : (
          <ResultsPanel insights={insights} filter={filter} />
        )}
      </div>
    </main>
  );
}

// ---------------------------------------------------------------------------
// Root — top-level navigation
// ---------------------------------------------------------------------------

type View = "insights" | "sentinel";

export default function App() {
  const [view, setView] = useState<View>("insights");

  return (
    <div style={{ fontFamily: "sans-serif" }}>
      {/* Top navigation bar */}
      <nav
        style={{
          display: "flex",
          alignItems: "center",
          gap: 2,
          padding: "0 24px",
          borderBottom: "1px solid #e5e7eb",
          background: "#fff",
          position: "sticky",
          top: 0,
          zIndex: 100,
          boxShadow: "0 1px 3px rgba(0,0,0,0.06)",
        }}
      >
        <div style={{ fontWeight: 800, fontSize: 15, color: "#111827", marginRight: 24, padding: "14px 0" }}>
          Colaberry AI
        </div>
        {(
          [
            { key: "insights", label: "Insight Generator" },
            { key: "sentinel", label: "Sentinel Dashboard" },
          ] as Array<{ key: View; label: string }>
        ).map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setView(key)}
            style={{
              padding: "14px 16px",
              fontSize: 13,
              fontWeight: 600,
              border: "none",
              borderBottom: view === key ? "2px solid #2563eb" : "2px solid transparent",
              background: "none",
              cursor: "pointer",
              color: view === key ? "#2563eb" : "#6b7280",
              marginBottom: -1,
            }}
          >
            {label}
          </button>
        ))}
        <div style={{ marginLeft: "auto", fontSize: 11, color: "#9ca3af", padding: "14px 0" }}>
          shadow-mode
        </div>
      </nav>

      {/* View content */}
      {view === "insights"  && <InsightGenerator />}
      {view === "sentinel"  && <SentinelDashboard />}
    </div>
  );
}
