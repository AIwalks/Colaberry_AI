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

export default function App() {
  const [insights, setInsights] = useState<Insight[]>([]);
  const [loading, setLoading] = useState(false);

  async function generateInsights() {
    setLoading(true);
    try {
      const res = await fetch("http://localhost:8000/insight/generate", {
        method: "POST",
      });
      const data = await res.json();
      setInsights(data.insights ?? []);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main style={{ fontFamily: "sans-serif", maxWidth: 640, margin: "80px auto", padding: "0 24px" }}>
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
        {loading ? "Loading..." : "Generate Insights"}
      </button>

      <div
        style={{
          marginTop: 32,
          padding: 24,
          background: "#f9fafb",
          border: "1px solid #e5e7eb",
          borderRadius: 8,
          minHeight: 120,
        }}
      >
        {loading ? (
          <p style={{ color: "#6b7280", margin: 0 }}>Loading...</p>
        ) : insights.length === 0 ? (
          <p style={{ color: "#9ca3af", margin: 0 }}>No insights generated yet.</p>
        ) : (
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {insights.map((insight) => (
              <li
                key={insight.id}
                style={{
                  padding: "12px 0",
                  borderBottom: "1px solid #e5e7eb",
                }}
              >
                <div style={{ fontWeight: 600, marginBottom: 4 }}>{insight.title}</div>
                <div style={{ color: "#6b7280", fontSize: 13 }}>
                  Confidence: {(insight.confidence * 100).toFixed(0)}%
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </main>
  );
}
