interface EmptyStateProps {
  title: string;
  body?: string;
  icon?: string;
}

export function EmptyState({ title, body, icon = "○" }: EmptyStateProps) {
  return (
    <div
      data-testid="empty-state"
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: "48px 24px",
        color: "#9ca3af",
        textAlign: "center",
      }}
    >
      <div style={{ fontSize: 32, marginBottom: 12, opacity: 0.5 }}>{icon}</div>
      <div style={{ fontSize: 15, fontWeight: 600, color: "#6b7280", marginBottom: 6 }}>{title}</div>
      {body && <div style={{ fontSize: 13, lineHeight: 1.6 }}>{body}</div>}
    </div>
  );
}

export function LoadingState({ label = "Loading..." }: { label?: string }) {
  return (
    <div
      data-testid="loading-state"
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: "48px 24px",
      }}
    >
      <style>{`@keyframes sentinel-spin { to { transform: rotate(360deg); } }`}</style>
      <div
        style={{
          width: 32,
          height: 32,
          border: "3px solid #e5e7eb",
          borderTop: "3px solid #2563eb",
          borderRadius: "50%",
          animation: "sentinel-spin 0.75s linear infinite",
        }}
      />
      <div style={{ fontSize: 13, color: "#6b7280", marginTop: 12 }}>{label}</div>
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div
      data-testid="error-state"
      style={{
        background: "#fef2f2",
        border: "1px solid #fca5a5",
        borderLeft: "4px solid #dc2626",
        borderRadius: 8,
        padding: "12px 16px",
      }}
    >
      <div style={{ fontWeight: 700, fontSize: 13, color: "#b91c1c", marginBottom: 4 }}>
        Could not load data
      </div>
      <div style={{ fontSize: 12, color: "#7f1d1d" }}>{message}</div>
    </div>
  );
}
