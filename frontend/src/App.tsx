import { useState } from "react";

interface Insight {
  id: number;
  title: string;
  body: string;
  insight_type: string;
  entity_type: string;
  entity_id: string;
  confidence: number;
}

function ResultsPanel({ insights, filter }: { insights: Insight[]; filter: "all" | "kpi" | "risk" }) {
  const visible = insights
    .filter((i) => filter === "all" || i.insight_type === filter)
    .slice()
    .sort((a, b) => b.confidence - a.confidence);

  const kpiCount  = visible.filter((i) => i.insight_type === "kpi").length;
  const riskCount = visible.filter((i) => i.insight_type === "risk").length;

  return (
    <>
      <p style={{ fontSize: 13, color: "#6b7280", margin: "0 0 12px 0" }}>
        {visible.length} Insight{visible.length !== 1 ? "s" : ""} &bull; {kpiCount} KPI &bull; {riskCount} Risk
      </p>
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        {visible.length === 0 ? (
          <p style={{ color: "#9ca3af", margin: 0 }}>No {filter.toUpperCase()} insights found.</p>
        ) : (
          visible.map((insight) => {
            const isKpi = insight.insight_type === "kpi";
            const accentColor = isKpi ? "#16a34a" : "#dc2626";
            const badgeBg    = isKpi ? "#dcfce7" : "#fee2e2";
            const badgeColor = isKpi ? "#15803d" : "#b91c1c";
            const alpha  = 0.05 + insight.confidence * 0.15;
            const cardBg = isKpi
              ? `rgba(22, 163, 74, ${alpha})`
              : `rgba(220, 38, 38, ${alpha})`;
            return (
              <div
                key={insight.id}
                style={{
                  background: cardBg,
                  border: "1px solid #e5e7eb",
                  borderLeft: `4px solid ${accentColor}`,
                  borderRadius: 8,
                  padding: "16px 20px",
                  boxShadow: "0 1px 4px rgba(0,0,0,0.06)",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
                  <div style={{ fontWeight: 700, fontSize: 16, color: "#111827" }}>{insight.title}</div>
                  <span
                    style={{
                      fontSize: 11,
                      fontWeight: 700,
                      textTransform: "uppercase",
                      letterSpacing: "0.06em",
                      padding: "3px 10px",
                      borderRadius: 12,
                      background: badgeBg,
                      color: badgeColor,
                      whiteSpace: "nowrap",
                      marginLeft: 12,
                    }}
                  >
                    {insight.insight_type}
                  </span>
                </div>
                <div style={{ fontSize: 13, color: "#4b5563", marginBottom: 12, lineHeight: 1.5 }}>{insight.body}</div>
                <div style={{ fontSize: 12, color: "#6b7280" }}>
                  Confidence: <strong style={{ color: "#111827" }}>{(insight.confidence * 100).toFixed(0)}%</strong>
                </div>
              </div>
            );
          })
        )}
      </div>
    </>
  );
}

export default function App() {
  const [insights, setInsights] = useState<Insight[]>([]);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState<"all" | "kpi" | "risk">("all");
  const [error, setError] = useState<string | null>(null);

  async function generateInsights() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("http://localhost:8000/insight/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ entity_id: "student_101", entity_type: "student" }),
      });
      if (!res.ok) {
        setError(`Request failed: HTTP ${res.status} ${res.statusText}`);
        return;
      }
      const data = await res.json();
      setInsights(data.insights ?? []);
    } catch (e) {
      setError("Could not reach the server. Check that the backend is running.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main style={{ fontFamily: "sans-serif", maxWidth: 640, margin: "80px auto", padding: "0 24px" }}>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      <h1 style={{ marginBottom: 8 }}>Insight Generator</h1>
      <p style={{ color: "#555", marginBottom: 32 }}>
        Generate insights from KPI and fingerprint data.
      </p>

      <button
        onClick={generateInsights}
        disabled={loading}
        style={{
          padding: "10px 24px",
          fontSize: 15,
          background: loading ? "#93c5fd" : "#2563eb",
          color: "#fff",
          border: "none",
          borderRadius: 6,
          cursor: loading ? "not-allowed" : "pointer",
        }}
      >
        {loading ? "Generating..." : "Generate Insights"}
      </button>

      {insights.length > 0 && (
        <div style={{ display: "flex", gap: 8, marginTop: 24 }}>
          {(["all", "kpi", "risk"] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              style={{
                padding: "6px 16px",
                fontSize: 13,
                fontWeight: 600,
                borderRadius: 6,
                border: "1px solid",
                cursor: "pointer",
                borderColor: filter === f ? "#2563eb" : "#d1d5db",
                background: filter === f ? "#2563eb" : "#fff",
                color: filter === f ? "#fff" : "#374151",
              }}
            >
              {f === "all" ? "All" : f.toUpperCase()}
            </button>
          ))}
        </div>
      )}

      <div
        style={{
          marginTop: 16,
          padding: 24,
          background: "#f9fafb",
          border: "1px solid #e5e7eb",
          borderRadius: 8,
          minHeight: 120,
        }}
      >
        {loading ? (
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "32px 0" }}>
            <div
              style={{
                width: 36,
                height: 36,
                border: "3px solid #e5e7eb",
                borderTop: "3px solid #2563eb",
                borderRadius: "50%",
                animation: "spin 0.75s linear infinite",
              }}
            />
            <p style={{ color: "#6b7280", fontSize: 13, marginTop: 12, marginBottom: 0 }}>Generating insights...</p>
          </div>
        ) : error ? (
          <div
            style={{
              background: "#fef2f2",
              border: "1px solid #fca5a5",
              borderLeft: "4px solid #dc2626",
              borderRadius: 8,
              padding: "12px 16px",
            }}
          >
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
