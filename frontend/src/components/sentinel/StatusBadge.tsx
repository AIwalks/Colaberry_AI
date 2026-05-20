import type { GovernanceStatus, RiskLevel } from "../../types/sentinel";

// ---------------------------------------------------------------------------
// Color maps
// ---------------------------------------------------------------------------

const STATUS_COLORS: Record<GovernanceStatus, { bg: string; text: string; dot: string }> = {
  pending:  { bg: "#eff6ff", text: "#1d4ed8", dot: "#2563eb" },
  approved: { bg: "#f0fdf4", text: "#15803d", dot: "#16a34a" },
  rejected: { bg: "#fef2f2", text: "#b91c1c", dot: "#dc2626" },
  deferred: { bg: "#fff7ed", text: "#c2410c", dot: "#ea580c" },
};

const RISK_COLORS: Record<RiskLevel, { bg: string; text: string; border: string }> = {
  low:      { bg: "#f0fdf4", text: "#15803d", border: "#16a34a" },
  medium:   { bg: "#fffbeb", text: "#92400e", border: "#d97706" },
  high:     { bg: "#fff7ed", text: "#9a3412", border: "#ea580c" },
  critical: { bg: "#fef2f2", text: "#991b1b", border: "#dc2626" },
  unknown:  { bg: "#f9fafb", text: "#4b5563", border: "#9ca3af" },
};

// ---------------------------------------------------------------------------
// GovernanceStatusBadge
// ---------------------------------------------------------------------------

interface StatusBadgeProps {
  status: GovernanceStatus;
}

export function GovernanceStatusBadge({ status }: StatusBadgeProps) {
  const c = STATUS_COLORS[status] ?? STATUS_COLORS.pending;
  return (
    <span
      data-testid={`status-badge-${status}`}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 5,
        fontSize: 11,
        fontWeight: 700,
        textTransform: "uppercase",
        letterSpacing: "0.06em",
        padding: "3px 10px",
        borderRadius: 20,
        background: c.bg,
        color: c.text,
        whiteSpace: "nowrap",
      }}
    >
      <span
        style={{
          width: 6,
          height: 6,
          borderRadius: "50%",
          background: c.dot,
          flexShrink: 0,
        }}
      />
      {status}
    </span>
  );
}

// ---------------------------------------------------------------------------
// RiskLevelBadge
// ---------------------------------------------------------------------------

interface RiskBadgeProps {
  level: RiskLevel;
}

export function RiskLevelBadge({ level }: RiskBadgeProps) {
  const c = RISK_COLORS[level] ?? RISK_COLORS.unknown;
  return (
    <span
      data-testid={`risk-badge-${level}`}
      style={{
        fontSize: 11,
        fontWeight: 700,
        textTransform: "uppercase",
        letterSpacing: "0.06em",
        padding: "3px 10px",
        borderRadius: 4,
        background: c.bg,
        color: c.text,
        border: `1px solid ${c.border}`,
        whiteSpace: "nowrap",
      }}
    >
      {level}
    </span>
  );
}

// ---------------------------------------------------------------------------
// ConfidenceBar
// ---------------------------------------------------------------------------

interface ConfidenceBarProps {
  value: number;
}

export function ConfidenceBar({ value }: ConfidenceBarProps) {
  const pct = Math.round(value * 100);
  const color = value >= 0.85 ? "#16a34a" : value >= 0.65 ? "#d97706" : "#dc2626";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <div
        style={{
          flex: 1,
          height: 6,
          background: "#e5e7eb",
          borderRadius: 3,
          overflow: "hidden",
        }}
      >
        <div
          style={{
            width: `${pct}%`,
            height: "100%",
            background: color,
            borderRadius: 3,
            transition: "width 0.3s ease",
          }}
        />
      </div>
      <span style={{ fontSize: 12, fontWeight: 700, color, minWidth: 36, textAlign: "right" }}>
        {pct}%
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// SourceBadge (db vs mock)
// ---------------------------------------------------------------------------

interface SourceBadgeProps {
  source: "db" | "mock";
}

export function SourceBadge({ source }: SourceBadgeProps) {
  const isDb = source === "db";
  return (
    <span
      style={{
        fontSize: 10,
        fontWeight: 600,
        padding: "2px 8px",
        borderRadius: 10,
        background: isDb ? "#eff6ff" : "#faf5ff",
        color: isDb ? "#1d4ed8" : "#7c3aed",
        border: `1px solid ${isDb ? "#bfdbfe" : "#ddd6fe"}`,
      }}
    >
      {isDb ? "live db" : "mock data"}
    </span>
  );
}
