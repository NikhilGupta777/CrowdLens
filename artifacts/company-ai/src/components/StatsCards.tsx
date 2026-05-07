import { SimStats } from "../hooks/useSimulation";
import { Users, ShieldAlert, Activity, Clock } from "lucide-react";

function GlowNumber({ value, color }: { value: string | number; color: string }) {
  return (
    <div style={{
      fontSize: 48,
      fontWeight: 800,
      color,
      lineHeight: 1,
      fontVariantNumeric: "tabular-nums",
      textShadow: "none",
      letterSpacing: -1,
    }}>
      {value}
    </div>
  );
}

function Card({
  label, icon: Icon, value, color, sub, pulse,
}: {
  label: string;
  icon: typeof Users;
  value: string | number;
  color: string;
  sub?: string;
  pulse?: boolean;
}) {
  return (
    <div style={{
      background: "var(--app-card-bg)",
      border: "1px solid var(--app-card-border)",
      borderRadius: 18,
      padding: "30px 28px",
      minHeight: 158,
      position: "relative",
      overflow: "hidden",
      transition: "border-color 0.3s",
      borderLeft: `3px solid ${color}`,
      boxShadow: "0 2px 8px rgba(22,20,18,0.04)",
    }}>
      {/* Background tint */}
      <div style={{
        position: "absolute", top: 0, right: 0,
        width: 110, height: 110,
        background: `radial-gradient(circle at top right, ${color}14, transparent)`,
        pointerEvents: "none",
      }} />

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 22 }}>
        <div style={{ fontSize: 11, color: "var(--app-text-muted)", letterSpacing: 1.8, fontWeight: 700 }}>
          {label}
        </div>
        <div style={{
          background: color + "18",
          borderRadius: 14,
          padding: "12px",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}>
          <Icon size={23} color={color} />
        </div>
      </div>

      <GlowNumber value={value} color={color} />

      {sub && (
        <div style={{ fontSize: 14, color: "var(--app-text-muted)", marginTop: 10, fontWeight: 500 }}>
          {sub}
        </div>
      )}

      {pulse && (
        <div style={{
          position: "absolute", bottom: 12, right: 16,
          width: 8, height: 8, borderRadius: "50%",
          background: color,
          boxShadow: `0 0 12px ${color}`,
          animation: "pulse-ring 1.4s infinite",
        }} />
      )}
    </div>
  );
}

function formatUptime(s: number) {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
}

interface Props {
  stats: SimStats | null;
  anomalyCount: number;
}

export default function StatsCards({ stats, anomalyCount }: Props) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      <Card
        label="LIVE OCCUPANCY"
        icon={Users}
        value={stats?.person_count ?? 0}
        color="#3b82f6"
        sub={`${stats?.object_count ?? 0} object(s) tracked`}
      />
      <Card
        label="THREAT LEVEL"
        icon={ShieldAlert}
        value={anomalyCount}
        color={anomalyCount > 0 ? "#ef4444" : "#10b981"}
        sub={anomalyCount > 0 ? `${anomalyCount} incident(s) active` : "All clear · No threats"}
        pulse={anomalyCount > 0}
      />
      <Card
        label="TOTAL TRACKS"
        icon={Activity}
        value={(stats?.person_count ?? 0) + (stats?.object_count ?? 0)}
        color="#a855f7"
        sub="Entities in frame"
      />
      <Card
        label="SYSTEM UPTIME"
        icon={Clock}
        value={formatUptime(stats?.uptime_seconds ?? 0)}
        color="#10b981"
        sub={`${stats?.fps ?? 0} FPS · Detection engine running`}
      />
    </div>
  );
}
