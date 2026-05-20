import type { ReuseMetrics } from "../../types/sentinel";
import { GovernanceStatusBadge, SourceBadge } from "./StatusBadge";
import { LoadingState, ErrorState } from "./EmptyState";
import type { LoadState } from "../../types/sentinel";

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function MetricCard({
  label,
  value,
  subtitle,
  accent,
}: {
  label: string;
  value: string | number;
  subtitle?: string;
  accent?: string;
}) {
  return (
    <div
      style={{
        background: "#fff",
        border: "1px solid #e5e7eb",
        borderTop: `3px solid ${accent ?? "#2563eb"}`,
        borderRadius: 10,
        padding: "16px 20px",
      }}
    >
      <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.07em", color: "#9ca3af", marginBottom: 6 }}>
        {label}
      </div>
      <div style={{ fontSize: 28, fontWeight: 800, color: "#111827", lineHeight: 1 }}>{value}</div>
      {subtitle && <div style={{ fontSize: 12, color: "#6b7280", marginTop: 4 }}>{subtitle}</div>}
    </div>
  );
}

function DistributionRow({ label, value, total, color }: { label: string; value: number; total: number; color: string }) {
  const pct = total > 0 ? Math.round((value / total) * 100) : 0;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
      <div style={{ width: 80, fontSize: 12, color: "#374151", fontWeight: 600, textTransform: "capitalize" }}>{label}</div>
      <div style={{ flex: 1, height: 8, background: "#f3f4f6", borderRadius: 4, overflow: "hidden" }}>
        <div style={{ width: `${pct}%`, height: "100%", background: color, borderRadius: 4 }} />
      </div>
      <div style={{ width: 40, textAlign: "right", fontSize: 12, fontWeight: 700, color: "#374151" }}>{value}</div>
      <div style={{ width: 36, textAlign: "right", fontSize: 11, color: "#9ca3af" }}>{pct}%</div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

const RISK_COLORS: Record<string, string> = {
  low: "#16a34a", medium: "#d97706", high: "#ea580c", critical: "#dc2626", unknown: "#9ca3af",
};

const GEN_COLORS: Record<string, string> = {
  claude: "#7c3aed", fallback: "#dc2626", deterministic_engine: "#2563eb",
};

const STATUS_COLORS: Record<string, string> = {
  pending: "#2563eb", approved: "#16a34a", rejected: "#dc2626", deferred: "#ea580c",
};

interface ReuseMetricsProps {
  state: LoadState<ReuseMetrics>;
  onReload: () => void;
}

export function ReuseMetricsPanel({ state, onReload }: ReuseMetricsProps) {
  if (state.status === "idle" || state.status === "loading") return <LoadingState label="Loading pipeline metrics..." />;
  if (state.status === "error") return <ErrorState message={state.message} />;

  const m = state.data;

  return (
    <section>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: "#111827" }}>
            Reuse &amp; Regeneration Metrics
          </h2>
          <p style={{ margin: "4px 0 0", fontSize: 13, color: "#6b7280" }}>
            Pipeline throughput and material-change gate behavior
          </p>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <SourceBadge source={m.source} />
          <button
            onClick={onReload}
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

      {/* Top metrics grid */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12, marginBottom: 24 }}>
        <MetricCard label="Total Interpretations" value={m.total_interpretations} accent="#2563eb" />
        <MetricCard label="Active" value={m.active_interpretations} subtitle="Current live records" accent="#16a34a" />
        <MetricCard label="Invalidated" value={m.invalidated_interpretations} subtitle="Superseded by new data" accent="#9ca3af" />
        <MetricCard label="Pending Reviews" value={m.governance_summary.pending} subtitle="Awaiting human decision" accent="#ea580c" />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, marginBottom: 24 }}>
        {/* Risk level distribution */}
        <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 10, padding: "16px 20px" }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: "#111827", marginBottom: 14 }}>Risk Level Distribution</div>
          {Object.entries(m.by_risk_level).map(([level, count]) => (
            <DistributionRow
              key={level}
              label={level}
              value={count}
              total={m.total_interpretations}
              color={RISK_COLORS[level] ?? "#9ca3af"}
            />
          ))}
        </div>

        {/* Generated by distribution */}
        <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 10, padding: "16px 20px" }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: "#111827", marginBottom: 14 }}>Generated By</div>
          {Object.entries(m.by_generated_by).map(([gen, count]) => (
            <DistributionRow
              key={gen}
              label={gen.replace(/_/g, " ")}
              value={count}
              total={m.total_interpretations}
              color={GEN_COLORS[gen] ?? "#9ca3af"}
            />
          ))}
        </div>
      </div>

      {/* Governance summary */}
      <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 10, padding: "16px 20px", marginBottom: 20 }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: "#111827", marginBottom: 14 }}>Governance Decision Summary</div>
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
          {(["pending", "approved", "rejected", "deferred"] as const).map((s) => (
            <div key={s} style={{
              flex: 1, minWidth: 100, textAlign: "center",
              background: "#f9fafb", borderRadius: 8, padding: "12px 16px",
            }}>
              <div style={{ fontSize: 24, fontWeight: 800, color: STATUS_COLORS[s] }}>
                {m.governance_summary[s]}
              </div>
              <GovernanceStatusBadge status={s} />
            </div>
          ))}
        </div>
      </div>

      {/* Material change triggers */}
      {m.material_change_triggers && (
        <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 10, padding: "16px 20px", marginBottom: 20 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: "#111827", marginBottom: 14 }}>Material-Change Gate Trigger Counts</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: 10 }}>
            {Object.entries(m.material_change_triggers).map(([rule, count]) => (
              <div key={rule} style={{
                background: "#f9fafb", border: "1px solid #e5e7eb",
                borderRadius: 6, padding: "10px 14px",
              }}>
                <div style={{ fontSize: 20, fontWeight: 800, color: "#374151" }}>{count}</div>
                <div style={{ fontSize: 11, color: "#6b7280", textTransform: "capitalize", marginTop: 2 }}>
                  {rule.replace(/_/g, " ")}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Note */}
      <div style={{
        background: "#f9fafb", border: "1px solid #e5e7eb",
        borderRadius: 8, padding: "10px 14px",
        fontSize: 12, color: "#6b7280", fontStyle: "italic",
      }}>
        {m.note}
      </div>
    </section>
  );
}
