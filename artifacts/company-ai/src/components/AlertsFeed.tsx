import { Anomaly } from "../hooks/useSimulation";
import { Zap, AlertCircle, Users, ShieldAlert, PersonStanding } from "lucide-react";

const ANOMALY_META: Record<string, {
  color: string;
  bg: string;
  Icon: typeof Zap;
  label: string;
  severity: string;
}> = {
  running:          { color: "#a855f7", bg: "rgba(168,85,247,0.08)",  Icon: Zap,         label: "Running Detected",   severity: "CRITICAL" },
  fight_suspected:  { color: "#f43f5e", bg: "rgba(244,63,94,0.10)",   Icon: AlertCircle, label: "Fight Suspected",    severity: "CRITICAL" },
  unattended_object:{ color: "#ef4444", bg: "rgba(239,68,68,0.08)",   Icon: AlertCircle, label: "Unattended Object",  severity: "HIGH"     },
  overcrowding:     { color: "#f97316", bg: "rgba(249,115,22,0.08)",  Icon: Users,       label: "Overcrowding",       severity: "MEDIUM"   },
  fall_detected:    { color: "#dc2626", bg: "rgba(220,38,38,0.10)",   Icon: PersonStanding, label: "Fall Detected",   severity: "HIGH"     },
  restricted_zone:  { color: "#eab308", bg: "rgba(234,179,8,0.10)",   Icon: ShieldAlert, label: "Restricted Zone",    severity: "HIGH"     },
};

interface Props {
  anomalies: Anomaly[];
}

export default function AlertsFeed({ anomalies }: Props) {
  return (
    <div style={{
      background: "var(--app-card-bg)",
      border: "1px solid var(--app-card-border)",
      borderRadius: 14,
      padding: "18px",
    }}>
      <div style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        marginBottom: 14,
        paddingBottom: 12,
        borderBottom: "1px solid rgba(255,255,255,0.06)",
      }}>
        <div style={{ fontSize: 9, color: "var(--app-text-muted)", letterSpacing: 2, fontWeight: 700 }}>
          RECENT INCIDENTS
        </div>
        {anomalies.length > 0 && (
          <div style={{
            background: "rgba(239,68,68,0.15)",
            color: "#ef4444",
            fontSize: 9,
            fontWeight: 800,
            padding: "2px 8px",
            borderRadius: 20,
            letterSpacing: 1,
          }}>
            {anomalies.length} RECENT
          </div>
        )}
      </div>

      {anomalies.length === 0 ? (
        <div style={{
          textAlign: "center",
          padding: "24px 0",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 10,
        }}>
          <div style={{
            width: 40, height: 40, borderRadius: "50%",
            background: "rgba(16,185,129,0.1)",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}>
            <span style={{ fontSize: 20 }}>✓</span>
          </div>
          <div style={{ color: "var(--app-text)", fontSize: 12, fontWeight: 600 }}>No recent threats</div>
          <div style={{ color: "var(--app-text-muted)", fontSize: 11 }}>All zones nominal</div>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {anomalies.map((a, i) => {
            const meta = ANOMALY_META[a.type] ?? {
              color: "#94a3b8", bg: "rgba(148,163,184,0.08)",
              Icon: AlertCircle, label: a.type.toUpperCase(), severity: "INFO",
            };
            const { Icon } = meta;
            const stableKey = a.track_id !== undefined
              ? `${a.type}-${a.track_id}`
              : a.track_ids?.length
                ? `${a.type}-${a.track_ids.join("-")}`
                : `${a.type}-${i}`;
            return (
              <div
                key={stableKey}
                className="slide-in"
                style={{
                  background: meta.bg,
                  border: `1px solid ${meta.color}30`,
                  borderRadius: 10,
                  padding: "11px 13px",
                  position: "relative",
                  overflow: "hidden",
                }}
              >
                {/* Glow strip */}
                <div style={{
                  position: "absolute", left: 0, top: 0, bottom: 0, width: 3,
                  background: `linear-gradient(180deg, ${meta.color}, ${meta.color}88)`,
                  borderRadius: "3px 0 0 3px",
                }} />

                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                  <Icon size={13} color={meta.color} />
                  <span style={{ color: meta.color, fontWeight: 700, fontSize: 12 }}>
                    {meta.label}
                  </span>
                  <span style={{
                    marginLeft: "auto",
                    background: meta.color + "22",
                    color: meta.color,
                    fontSize: 8,
                    fontWeight: 800,
                    padding: "1px 6px",
                    borderRadius: 10,
                    letterSpacing: 1,
                  }}>
                    {meta.severity}
                  </span>
                </div>

                <div style={{ display: "flex", flexWrap: "wrap", gap: 8, paddingLeft: 2 }}>
                  {a.track_id !== undefined && (
                    <span style={{ fontSize: 10, color: "#64748b" }}>Track #{a.track_id}</span>
                  )}
                  {a.count !== undefined && (
                    <span style={{ fontSize: 10, color: "#64748b" }}>{a.count} people</span>
                  )}
                  {a.avg_speed !== undefined && (
                    <span style={{ fontSize: 10, color: "#a855f7", fontWeight: 600 }}>{a.avg_speed} px/f</span>
                  )}
                  {a.avg_pair_speed !== undefined && (
                    <span style={{ fontSize: 10, color: "#f43f5e", fontWeight: 600 }}>{a.avg_pair_speed} pair px/f</span>
                  )}
                  {a.distance !== undefined && (
                    <span style={{ fontSize: 10, color: "#f43f5e", fontWeight: 600 }}>{a.distance}px separation</span>
                  )}
                  {a.track_ids && a.track_ids.length >= 2 && (
                    <span style={{ fontSize: 10, color: "#f43f5e" }}>Pair #{a.track_ids[0]} & #{a.track_ids[1]}</span>
                  )}
                  {a.duration !== undefined && (
                    <span style={{ fontSize: 10, color: "#64748b" }}>{a.duration}s elapsed</span>
                  )}
                  {a.confidence !== undefined && (
                    <span style={{ fontSize: 10, color: "#dc2626", fontWeight: 600 }}>
                      conf {(a.confidence * 100).toFixed(0)}%
                    </span>
                  )}
                  {a.zone_name && (
                    <span style={{ fontSize: 10, color: "#eab308", fontWeight: 600 }}>{a.zone_name}</span>
                  )}
                  {a.position && (
                    <span style={{ fontSize: 10, color: "#475569", fontFamily: "monospace" }}>
                      ({Math.round(a.position[0])}, {Math.round(a.position[1])})
                    </span>
                  )}
                  {a.note && (
                    <span style={{ fontSize: 10, color: "#64748b" }}>{a.note}</span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

