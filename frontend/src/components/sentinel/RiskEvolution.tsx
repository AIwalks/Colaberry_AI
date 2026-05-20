import type { AIInterpretation, RiskLevel } from "../../types/sentinel";
import { RiskLevelBadge, ConfidenceBar } from "./StatusBadge";
import { EmptyState, LoadingState, ErrorState } from "./EmptyState";
import type { LoadState } from "../../types/sentinel";

const RISK_RANK: Record<RiskLevel, number> = {
  unknown: 0, low: 1, medium: 2, high: 3, critical: 4,
};

function escalationArrow(prev: RiskLevel | null, current: RiskLevel): string {
  if (!prev) return "—";
  const delta = RISK_RANK[current] - RISK_RANK[prev];
  if (delta > 0)  return "↑";
  if (delta < 0)  return "↓";
  return "→";
}

function escalationColor(prev: RiskLevel | null, current: RiskLevel): string {
  if (!prev) return "#9ca3af";
  const delta = RISK_RANK[current] - RISK_RANK[prev];
  if (delta > 0)  return "#dc2626";
  if (delta < 0)  return "#16a34a";
  return "#6b7280";
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleString("en-US", {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

// ---------------------------------------------------------------------------
// Confidence sparkline (CSS-based, no charting library)
// ---------------------------------------------------------------------------

function ConfidenceSparkline({ history }: { history: AIInterpretation[] }) {
  const sorted = [...history].sort(
    (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
  );
  const max = sorted.length;
  if (max === 0) return null;

  return (
    <div style={{
      background: "#fff", border: "1px solid #e5e7eb",
      borderRadius: 10, padding: "16px 20px", marginBottom: 20,
    }}>
      <div style={{ fontSize: 13, fontWeight: 700, color: "#111827", marginBottom: 14 }}>
        Confidence Progression
      </div>
      <div style={{ display: "flex", alignItems: "flex-end", gap: 8, height: 80 }}>
        {sorted.map((interp) => {
          const pct = Math.round(interp.confidence * 100);
          const color = interp.is_active ? "#2563eb" : "#e5e7eb";
          const barHeight = Math.max(4, Math.round(interp.confidence * 80));
          return (
            <div key={interp.id} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center" }}>
              <div style={{ fontSize: 10, color: "#9ca3af", marginBottom: 4 }}>{pct}%</div>
              <div
                title={`v${interp.interpretation_version}: ${pct}% (${interp.risk_level})`}
                style={{
                  width: "100%", height: barHeight,
                  background: color, borderRadius: "3px 3px 0 0",
                  cursor: "default",
                }}
              />
              <div style={{ fontSize: 9, color: "#9ca3af", marginTop: 4, textAlign: "center" }}>
                v{interp.interpretation_version}
              </div>
            </div>
          );
        })}
      </div>
      <div style={{ fontSize: 11, color: "#9ca3af", marginTop: 8 }}>
        Blue = active · Gray = invalidated · Hover bar for details
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Risk escalation timeline table
// ---------------------------------------------------------------------------

function EscalationTable({ history }: { history: AIInterpretation[] }) {
  const sorted = [...history].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  );

  return (
    <div style={{
      background: "#fff", border: "1px solid #e5e7eb",
      borderRadius: 10, overflow: "hidden", marginBottom: 20,
    }}>
      <div style={{ padding: "14px 20px", borderBottom: "1px solid #f3f4f6" }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: "#111827" }}>Risk Escalation Timeline</div>
        <div style={{ fontSize: 12, color: "#6b7280", marginTop: 2 }}>
          Newest first — ↑ escalation, ↓ improvement, → unchanged
        </div>
      </div>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
        <thead>
          <tr style={{ background: "#f9fafb" }}>
            {["Version", "Created", "Risk Level", "Confidence", "Change", "State"].map((h) => (
              <th key={h} style={{
                padding: "8px 16px", textAlign: "left", fontSize: 11, fontWeight: 700,
                textTransform: "uppercase", letterSpacing: "0.06em", color: "#6b7280",
                borderBottom: "1px solid #e5e7eb",
              }}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((interp, idx) => {
            const prev = idx < sorted.length - 1 ? sorted[idx + 1].risk_level as RiskLevel : null;
            const arrow = escalationArrow(prev, interp.risk_level as RiskLevel);
            const arrowColor = escalationColor(prev, interp.risk_level as RiskLevel);
            const stale = interp.stale_after && new Date(interp.stale_after) < new Date();

            return (
              <tr key={interp.id} style={{ borderBottom: "1px solid #f3f4f6", opacity: interp.is_active ? 1 : 0.65 }}>
                <td style={{ padding: "10px 16px", color: "#374151", fontWeight: 600 }}>
                  v{interp.interpretation_version}
                </td>
                <td style={{ padding: "10px 16px", color: "#6b7280", whiteSpace: "nowrap" }}>
                  {formatDate(interp.created_at)}
                </td>
                <td style={{ padding: "10px 16px" }}>
                  <RiskLevelBadge level={interp.risk_level as RiskLevel} />
                </td>
                <td style={{ padding: "10px 16px", minWidth: 140 }}>
                  <ConfidenceBar value={interp.confidence} />
                </td>
                <td style={{ padding: "10px 16px", fontSize: 18, fontWeight: 700, color: arrowColor }}>
                  {arrow}
                </td>
                <td style={{ padding: "10px 16px" }}>
                  {interp.is_active ? (
                    <span style={{ fontSize: 11, fontWeight: 700, padding: "2px 8px", borderRadius: 10, background: "#f0fdf4", color: "#15803d" }}>
                      Active
                    </span>
                  ) : stale ? (
                    <span style={{ fontSize: 11, fontWeight: 700, padding: "2px 8px", borderRadius: 10, background: "#fffbeb", color: "#92400e" }}>
                      Stale
                    </span>
                  ) : (
                    <span style={{ fontSize: 11, fontWeight: 700, padding: "2px 8px", borderRadius: 10, background: "#f9fafb", color: "#6b7280" }}>
                      Invalidated
                    </span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Cross-dimension deterioration indicator
// ---------------------------------------------------------------------------

function DeteriorationBanner({ history }: { history: AIInterpretation[] }) {
  const active = history.filter((i) => i.is_active);
  const highOrCritical = active.filter(
    (i) => i.risk_level === "high" || i.risk_level === "critical"
  );
  if (active.length < 2 || highOrCritical.length < 2) return null;

  return (
    <div style={{
      background: "#fef2f2", border: "1px solid #fca5a5",
      borderLeft: "4px solid #dc2626", borderRadius: 8, padding: "12px 16px", marginBottom: 20,
    }}>
      <div style={{ fontWeight: 700, fontSize: 13, color: "#b91c1c", marginBottom: 4 }}>
        ⚠ Cross-dimensional deterioration detected
      </div>
      <div style={{ fontSize: 12, color: "#7f1d1d" }}>
        {highOrCritical.length} active dimensions showing high or critical risk:
        {" "}{highOrCritical.map((i) => i.dimension).join(", ")}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Public component
// ---------------------------------------------------------------------------

interface RiskEvolutionProps {
  entityId: string;
  historyState: LoadState<{ entity_id: string; history: AIInterpretation[]; total: number; source: "db" | "mock" }>;
}

export function RiskEvolution({ entityId, historyState }: RiskEvolutionProps) {
  if (historyState.status === "idle" || historyState.status === "loading") {
    return <LoadingState label={`Loading risk history for ${entityId}...`} />;
  }
  if (historyState.status === "error") {
    return <ErrorState message={historyState.message} />;
  }

  const history = historyState.data.history;

  if (history.length === 0) {
    return (
      <EmptyState
        title="No interpretation history"
        body={`No interpretations found for ${entityId}. Run an orchestration evaluation to start tracking risk evolution.`}
        icon="📈"
      />
    );
  }

  return (
    <div>
      <DeteriorationBanner history={history} />
      <ConfidenceSparkline history={history} />
      <EscalationTable history={history} />
    </div>
  );
}
