import { useEffect, useMemo, useState } from "react";
import { AlertCircle, BarChart2, Camera, Download, Filter, RefreshCw, Search, ShieldAlert, Trash2, UserRoundX, Users, Zap } from "lucide-react";
import { useIsMobile } from "../hooks/use-mobile";
import { AlertRecord } from "../types";
import {
  Bar,
  BarChart,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const TYPE_META: Record<string, { color: string; Icon: typeof Zap; label: string; severity: string }> = {
  running:           { color: "#a855f7", Icon: Zap,         label: "Running",            severity: "CRITICAL" },
  fight_suspected:   { color: "#f43f5e", Icon: AlertCircle, label: "Fight Suspected",    severity: "CRITICAL" },
  unattended_object: { color: "#ef4444", Icon: AlertCircle, label: "Unattended Object",  severity: "HIGH" },
  overcrowding:      { color: "#f97316", Icon: Users,       label: "Overcrowding",       severity: "MEDIUM" },
  fall_detected:     { color: "#dc2626", Icon: UserRoundX,  label: "Fall Detected",      severity: "HIGH" },
  restricted_zone:   { color: "#eab308", Icon: ShieldAlert, label: "Restricted Zone",    severity: "HIGH" },
  manual_snapshot:   { color: "#60a5fa", Icon: Camera,      label: "Manual Snapshot",    severity: "INFO" },
};

const FILTER_OPTIONS = [
  "all",
  "running",
  "fight_suspected",
  "unattended_object",
  "overcrowding",
  "fall_detected",
  "restricted_zone",
  "manual_snapshot",
] as const;

interface ChartBucket {
  time: string;
  running: number;
  fight_suspected: number;
  unattended_object: number;
  overcrowding: number;
  fall_detected: number;
  restricted_zone: number;
  manual_snapshot: number;
}

function escapeCsvValue(value: string | number | undefined | null): string {
  if (value === null || value === undefined) return "";
  const str = String(value);
  // Prefix formula-injection characters with a single quote so spreadsheets
  // treat them as plain text rather than formula starters.
  if (/^[=+\-@\t\r]/.test(str)) return `'${str}`;
  // Wrap in double quotes if the value contains a comma, newline, or quote.
  if (/[,"\n\r]/.test(str)) return `"${str.replace(/"/g, '""')}"`;
  return str;
}

function exportJSON(alerts: AlertRecord[]) {
  const blob = new Blob([JSON.stringify(alerts, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `crowdlens_alerts_${new Date().toISOString().slice(0, 10)}.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

function exportCSV(alerts: AlertRecord[]) {
  const headers = [
    "Time",
    "ISO",
    "Type",
    "Severity",
    "Track ID",
    "Track Pair",
    "Count",
    "Speed (px/f)",
    "Pair Speed (px/f)",
    "Pair Distance (px)",
    "Duration (s)",
    "Fall Confidence",
    "Zone",
    "Position X",
    "Position Y",
    "Source",
    "Snapshot URL",
  ];

  const rows = alerts.map((record) => {
    const meta = TYPE_META[record.anomaly.type];
    return [
      escapeCsvValue(new Date(record.timestamp * 1000).toLocaleString()),
      escapeCsvValue(record.iso),
      escapeCsvValue(meta?.label ?? record.anomaly.type),
      escapeCsvValue(meta?.severity ?? "INFO"),
      escapeCsvValue(record.anomaly.track_id),
      escapeCsvValue(record.anomaly.track_ids ? record.anomaly.track_ids.join("-") : ""),
      escapeCsvValue(record.anomaly.count),
      escapeCsvValue(record.anomaly.avg_speed),
      escapeCsvValue(record.anomaly.avg_pair_speed),
      escapeCsvValue(record.anomaly.distance),
      escapeCsvValue(record.anomaly.duration),
      escapeCsvValue(record.anomaly.confidence),
      escapeCsvValue(record.anomaly.zone_name ?? record.anomaly.zone_id ?? ""),
      escapeCsvValue(record.anomaly.position ? Math.round(record.anomaly.position[0]) : ""),
      escapeCsvValue(record.anomaly.position ? Math.round(record.anomaly.position[1]) : ""),
      escapeCsvValue((record.source ?? "live").toUpperCase()),
      escapeCsvValue(record.snapshot_url ? `${window.location.origin}${record.snapshot_url}` : ""),
    ].join(",");
  });

  const csv = [headers.join(","), ...rows].join("\n");
  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `crowdlens_alerts_${new Date().toISOString().slice(0, 10)}.csv`;
  anchor.click();
  URL.revokeObjectURL(url);
}

function buildChartData(alerts: AlertRecord[]): ChartBucket[] {
  if (alerts.length === 0) return [];

  const buckets: Record<string, ChartBucket> = {};
  const now = Date.now() / 1000;
  const rangeSeconds = 600;

  for (let i = 0; i < 10; i++) {
    const t = Math.floor((now - (9 - i) * 60) / 60) * 60;
    const label = new Date(t * 1000).toLocaleTimeString(undefined, {
      hour: "2-digit",
      minute: "2-digit",
    });
    buckets[label] = {
      time: label,
      running: 0,
      fight_suspected: 0,
      unattended_object: 0,
      overcrowding: 0,
      fall_detected: 0,
      restricted_zone: 0,
      manual_snapshot: 0,
    };
  }

  for (const record of alerts) {
    if (now - record.timestamp > rangeSeconds) continue;
    const t = Math.floor(record.timestamp / 60) * 60;
    const label = new Date(t * 1000).toLocaleTimeString(undefined, {
      hour: "2-digit",
      minute: "2-digit",
    });

    const bucket = buckets[label];
    if (!bucket) continue;

    const type = record.anomaly.type as keyof Omit<ChartBucket, "time">;
    if (type in bucket) {
      bucket[type] = (bucket[type] ?? 0) + 1;
    }
  }

  return Object.values(buckets);
}

function renderDetails(record: AlertRecord): string {
  const parts: string[] = [];
  if (record.anomaly.track_id !== undefined) parts.push(`Track #${record.anomaly.track_id}`);
  if (record.anomaly.track_ids && record.anomaly.track_ids.length >= 2) {
    parts.push(`Pair #${record.anomaly.track_ids[0]} & #${record.anomaly.track_ids[1]}`);
  }
  if (record.anomaly.count !== undefined) parts.push(`${record.anomaly.count} people`);
  if (record.anomaly.avg_speed !== undefined) parts.push(`${record.anomaly.avg_speed} px/f`);
  if (record.anomaly.avg_pair_speed !== undefined) parts.push(`${record.anomaly.avg_pair_speed} pair px/f`);
  if (record.anomaly.distance !== undefined) parts.push(`${record.anomaly.distance}px apart`);
  if (record.anomaly.duration !== undefined) parts.push(`${record.anomaly.duration}s`);
  if (record.anomaly.confidence !== undefined) parts.push(`conf ${(record.anomaly.confidence * 100).toFixed(0)}%`);
  if (record.anomaly.owner_absent !== undefined) parts.push(`away ${record.anomaly.owner_absent}s`);
  if (record.anomaly.zone_name) parts.push(record.anomaly.zone_name);
  else if (record.anomaly.zone_id) parts.push(record.anomaly.zone_id);
  if (record.anomaly.note) parts.push(record.anomaly.note);
  return parts.join(" - ");
}

export default function AlertHistory() {
  const isMobile = useIsMobile();
  const [alerts, setAlerts] = useState<AlertRecord[]>([]);
  const [filter, setFilter] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [clearConfirm, setClearConfirm] = useState(false);
  const [showChart, setShowChart] = useState(!isMobile);

  const fetchHistory = async (showRefreshing = false) => {
    if (showRefreshing) setRefreshing(true);
    try {
      const response = await fetch("/api/alerts/history?limit=200");
      const data = await response.json();
      setAlerts(data.alerts || []);
    } catch {
      // Keep previous state; UI will continue to show last known data.
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchHistory();
    const interval = setInterval(() => {
      if (document.visibilityState === "visible") fetchHistory();
    }, 3000);
    return () => clearInterval(interval);
  }, []);

  const clearHistory = async () => {
    if (!clearConfirm) { setClearConfirm(true); setTimeout(() => setClearConfirm(false), 3500); return; }
    setClearing(true);
    setClearConfirm(false);
    try {
      await Promise.all([
        fetch("/api/alerts/clear", { method: "POST" }),
        fetch("/api/archive/clear", { method: "POST" }),
      ]);
      setAlerts([]);
    } finally {
      setClearing(false);
    }
  };

  const q = searchQuery.trim().toLowerCase();
  const filtered = alerts.filter((record) => {
    if (filter !== "all" && record.anomaly.type !== filter) return false;
    if (!q) return true;
    const meta = TYPE_META[record.anomaly.type];
    return (
      (meta?.label ?? record.anomaly.type).toLowerCase().includes(q) ||
      String(record.anomaly.track_id ?? "").includes(q) ||
      (record.anomaly.zone_name ?? "").toLowerCase().includes(q) ||
      (record.anomaly.zone_id ?? "").toLowerCase().includes(q) ||
      renderDetails(record).toLowerCase().includes(q) ||
      (record.source ?? "").toLowerCase().includes(q)
    );
  });

  const counts = alerts.reduce<Record<string, number>>((acc, record) => {
    acc[record.anomaly.type] = (acc[record.anomaly.type] || 0) + 1;
    return acc;
  }, {});

  const summaryCards = Object.entries(TYPE_META).map(([type, meta]) => ({
    type,
    ...meta,
    count: counts[type] ?? 0,
  }));

  const chartData = useMemo(() => buildChartData(alerts), [alerts]);

  return (
    <div>
      <div style={{
        display: "flex", alignItems: isMobile ? "flex-start" : "center",
        flexDirection: isMobile ? "column" : "row",
        justifyContent: "space-between", marginBottom: 20, gap: 12,
      }}>
        <div>
          <h1 style={{ fontSize: isMobile ? 18 : 22, fontWeight: 700, color: "var(--app-text)", letterSpacing: -0.5, marginBottom: 4 }}>
            Alert History
          </h1>
          <p style={{ color: "var(--app-text-muted)", fontSize: isMobile ? 11 : 13 }}>
            {alerts.length} total events recorded
          </p>
        </div>

        <div style={{ display: "flex", gap: 8, flexShrink: 0, flexWrap: "wrap" }}>
          <button
            onClick={() => setShowChart((v) => !v)}
            style={{
              display: "flex", alignItems: "center", gap: 6,
              padding: "7px 12px", borderRadius: 8,
              border: "1px solid rgba(255,255,255,0.1)",
              background: showChart ? "rgba(59,130,246,0.1)" : "rgba(255,255,255,0.04)",
              color: showChart ? "#3b82f6" : "#64748b",
              cursor: "pointer", fontSize: 12,
            }}
          >
            <BarChart2 size={13} />
            {!isMobile && (showChart ? "Hide Chart" : "Show Chart")}
          </button>

          <button
            onClick={() => exportCSV(filtered)}
            style={{
              display: "flex", alignItems: "center", gap: 6,
              padding: "7px 12px", borderRadius: 8,
              border: "1px solid rgba(255,255,255,0.1)",
              background: "rgba(255,255,255,0.04)",
              color: "var(--app-text-muted)", cursor: "pointer", fontSize: 12,
            }}
          >
            <Download size={13} />
            {!isMobile && "CSV"}
          </button>

          <button
            onClick={() => exportJSON(filtered)}
            style={{
              display: "flex", alignItems: "center", gap: 6,
              padding: "7px 12px", borderRadius: 8,
              border: "1px solid rgba(255,255,255,0.1)",
              background: "rgba(255,255,255,0.04)",
              color: "var(--app-text-muted)", cursor: "pointer", fontSize: 12,
            }}
          >
            <Download size={13} />
            {!isMobile && "JSON"}
          </button>

          <button
            onClick={() => fetchHistory(true)}
            style={{
              display: "flex", alignItems: "center", gap: 6,
              padding: "7px 12px", borderRadius: 8,
              border: "1px solid rgba(255,255,255,0.1)",
              background: "rgba(255,255,255,0.04)",
              color: "var(--app-text-muted)", cursor: "pointer", fontSize: 12,
            }}
          >
            <RefreshCw size={13} style={{ animation: refreshing ? "spin 0.8s linear infinite" : "none" }} />
            {!isMobile && "Refresh"}
          </button>

          <button
            onClick={clearHistory}
            disabled={clearing || alerts.length === 0}
            style={{
              display: "flex", alignItems: "center", gap: 6,
              padding: "7px 12px", borderRadius: 8,
              border: `1px solid ${clearConfirm ? "rgba(239,68,68,0.5)" : "rgba(255,255,255,0.1)"}`,
              background: clearConfirm ? "rgba(239,68,68,0.12)" : "rgba(255,255,255,0.04)",
              color: clearConfirm ? "#ef4444" : "#64748b",
              cursor: alerts.length === 0 ? "not-allowed" : "pointer",
              fontSize: 12, transition: "all 0.2s",
            }}
          >
            <Trash2 size={13} />
            {!isMobile && (clearConfirm ? "Confirm Clear" : "Clear All")}
          </button>
        </div>
      </div>

      <div style={{
        display: "grid",
        gridTemplateColumns: isMobile ? "repeat(2, 1fr)" : "repeat(4, minmax(0,1fr))",
        gap: isMobile ? 10 : 14,
        marginBottom: 20,
      }}>
        {summaryCards.map(({ type, color, Icon, label, count, severity }) => (
          <div
            key={type}
            onClick={() => setFilter(filter === type ? "all" : type)}
            style={{
              background: "var(--app-card-bg)",
              border: "1px solid var(--app-card-border)",
              borderRadius: 14,
              padding: "18px 16px",
              borderLeft: `3px solid ${color}`,
              cursor: "pointer",
              boxShadow: filter === type ? `0 0 20px ${color}22` : "none",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
              <div style={{ fontSize: 9, color: "var(--app-text-muted)", letterSpacing: 1.8, fontWeight: 700 }}>
                {label.toUpperCase()}
              </div>
              <div style={{ background: `${color}18`, borderRadius: 8, padding: 5 }}>
                <Icon size={13} color={color} />
              </div>
            </div>
            <div style={{ fontSize: 34, fontWeight: 800, color, lineHeight: 1, textShadow: `0 0 20px ${color}55` }}>
              {count}
            </div>
            <div style={{ fontSize: 10, color: "var(--app-text-muted)", marginTop: 8, fontWeight: 600, letterSpacing: 1 }}>
              {severity}
            </div>
          </div>
        ))}
      </div>

      {showChart && (
        <div
          style={{
            background: "var(--app-card-bg)",
            border: "1px solid var(--app-card-border)",
            borderRadius: 14,
            padding: "20px 24px",
            marginBottom: 20,
          }}
        >
          <div style={{ fontSize: 9, color: "var(--app-text-muted)", letterSpacing: 2, fontWeight: 700, marginBottom: 16 }}>
            ALERT TREND - LAST 10 MINUTES
          </div>
          {chartData.every((d) => (
            d.running === 0
            && d.fight_suspected === 0
            && d.unattended_object === 0
            && d.overcrowding === 0
            && d.fall_detected === 0
            && d.restricted_zone === 0
            && d.manual_snapshot === 0
          )) ? (
            <div style={{ textAlign: "center", padding: "20px 0", color: "var(--app-text-muted)", fontSize: 13 }}>
              No recent alert data - alerts will appear here as they occur
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={chartData} barCategoryGap="20%">
                <XAxis dataKey="time" tick={{ fill: "#334155", fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: "#334155", fontSize: 10 }} axisLine={false} tickLine={false} allowDecimals={false} />
                <Tooltip
                  contentStyle={{
                    background: "#0d1525",
                    border: "1px solid rgba(255,255,255,0.1)",
                    borderRadius: 8,
                    fontSize: 12,
                  }}
                  labelStyle={{ color: "#94a3b8" }}
                />
                <Legend wrapperStyle={{ fontSize: 11, color: "var(--app-text-muted)" }} />
                <Bar dataKey="running" name="Running" fill="#a855f7" radius={[3, 3, 0, 0]} />
                <Bar dataKey="fight_suspected" name="Fight Suspected" fill="#f43f5e" radius={[3, 3, 0, 0]} />
                <Bar dataKey="unattended_object" name="Unattended Object" fill="#ef4444" radius={[3, 3, 0, 0]} />
                <Bar dataKey="overcrowding" name="Overcrowding" fill="#f97316" radius={[3, 3, 0, 0]} />
                <Bar dataKey="fall_detected" name="Fall Detected" fill="#dc2626" radius={[3, 3, 0, 0]} />
                <Bar dataKey="restricted_zone" name="Restricted Zone" fill="#eab308" radius={[3, 3, 0, 0]} />
                <Bar dataKey="manual_snapshot" name="Manual Snapshot" fill="#60a5fa" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      )}

      <div style={{ position: "relative", marginBottom: 12 }}>
        <Search size={13} color="#475569" style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", pointerEvents: "none" }} />
        <input
          type="text"
          placeholder="Search by type, track ID, zone, source…"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          style={{
            width: "100%", boxSizing: "border-box",
            background: "rgba(255,255,255,0.04)",
            border: "1px solid rgba(255,255,255,0.08)",
            borderRadius: 8, padding: "8px 12px 8px 34px",
            color: "var(--app-text)", fontSize: 13, outline: "none",
          }}
        />
        {searchQuery && (
          <button
            onClick={() => setSearchQuery("")}
            style={{ position: "absolute", right: 10, top: "50%", transform: "translateY(-50%)", background: "none", border: "none", color: "var(--app-text-muted)", cursor: "pointer", fontSize: 16, lineHeight: 1 }}
          >×</button>
        )}
      </div>

      <div style={{
        display: "flex", alignItems: "center", gap: 8, marginBottom: 16,
        overflowX: isMobile ? "auto" : "visible",
        flexWrap: isMobile ? "nowrap" : "wrap",
        paddingBottom: isMobile ? 4 : 0,
        scrollbarWidth: "none",
      }}>
        <Filter size={13} color="#475569" style={{ flexShrink: 0 }} />
        {FILTER_OPTIONS.map((option) => {
          const meta = TYPE_META[option as keyof typeof TYPE_META];
          const active = filter === option;
          return (
            <button
              key={option}
              onClick={() => setFilter(option)}
              style={{
                padding: "6px 14px",
                borderRadius: 8,
                border: "1px solid",
                cursor: "pointer",
                fontSize: 12,
                fontWeight: 600,
                transition: "all 0.18s",
                borderColor: active ? (meta?.color ?? "#3b82f6") : "rgba(255,255,255,0.08)",
                background: active ? `${meta?.color ?? "#3b82f6"}18` : "rgba(255,255,255,0.03)",
                color: active ? (meta?.color ?? "#3b82f6") : "#64748b",
              }}
            >
              {option === "all" ? "All Events" : meta?.label ?? option}
            </button>
          );
        })}
        <div style={{ marginLeft: "auto", fontSize: 11, color: "var(--app-text-muted)" }}>
          {filtered.length} events
        </div>
      </div>

      <div
        style={{
          background: "var(--app-card-bg)",
          border: "1px solid var(--app-card-border)",
          borderRadius: 14,
          overflow: "hidden",
        }}
      >
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ background: "rgba(0,0,0,0.3)", color: "var(--app-text-muted)", fontSize: 9, letterSpacing: 1.5, fontWeight: 700 }}>
              {["TIME", "TYPE", "SEVERITY", "DETAILS", "POSITION", "SOURCE", "EVIDENCE"].map((header) => (
                <th key={header} style={{ padding: "12px 16px", textAlign: "left" }}>
                  {header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={7} style={{ padding: 32, textAlign: "center", color: "var(--app-text-muted)" }}>Loading...</td>
              </tr>
            ) : filtered.length === 0 ? (
              <tr>
                <td colSpan={7} style={{ padding: 32, textAlign: "center", color: "var(--app-text-muted)" }}>No incidents recorded</td>
              </tr>
            ) : (
              filtered.map((record) => {
                const meta = TYPE_META[record.anomaly.type] ?? {
                  color: "#94a3b8",
                  Icon: AlertCircle,
                  label: record.anomaly.type,
                  severity: "INFO",
                };
                const { Icon } = meta;

                return (
                  <tr
                    key={record.id}
                    className="alert-row"
                    style={{ borderTop: "1px solid rgba(255,255,255,0.04)" }}
                  >
                    <td style={{ padding: "11px 16px", color: "var(--app-text-muted)", whiteSpace: "nowrap", fontFamily: "monospace", fontSize: 12 }}>
                      {new Date(record.timestamp * 1000).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                    </td>
                    <td style={{ padding: "11px 16px" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <Icon size={13} color={meta.color} />
                        <span style={{ background: `${meta.color}18`, color: meta.color, padding: "3px 10px", borderRadius: 20, fontSize: 11, fontWeight: 700 }}>
                          {meta.label}
                        </span>
                      </div>
                    </td>
                    <td style={{ padding: "11px 16px" }}>
                      <span style={{ background: "rgba(255,255,255,0.04)", color: "var(--app-text-muted)", padding: "2px 8px", borderRadius: 6, fontSize: 9, fontWeight: 800, letterSpacing: 1 }}>
                        {meta.severity}
                      </span>
                    </td>
                    <td style={{ padding: "11px 16px", color: "var(--app-text-muted)", fontSize: 12 }}>
                      {renderDetails(record) || "-"}
                    </td>
                    <td style={{ padding: "11px 16px", color: "var(--app-text-muted)", fontSize: 11, fontFamily: "monospace" }}>
                      {record.anomaly.position
                        ? `(${Math.round(record.anomaly.position[0])}, ${Math.round(record.anomaly.position[1])})`
                        : "-"}
                    </td>
                    <td style={{ padding: "11px 16px" }}>
                      <span
                        style={{
                          fontSize: 9,
                          fontWeight: 700,
                          letterSpacing: 1,
                          padding: "2px 8px",
                          borderRadius: 6,
                          background:
                            record.source === "video"
                              ? "rgba(168,85,247,0.1)"
                              : record.source === "stream"
                                ? "rgba(245,158,11,0.1)"
                                : "rgba(16,185,129,0.1)",
                          color:
                            record.source === "video"
                              ? "#a855f7"
                              : record.source === "stream"
                                ? "#f59e0b"
                                : "#10b981",
                        }}
                      >
                        {record.source === "video"
                          ? "VIDEO"
                          : record.source === "stream"
                            ? "STREAM"
                            : record.source === "webcam"
                              ? "WEBCAM"
                              : (record.source ?? "LIVE").toUpperCase()}
                      </span>
                    </td>
                    <td style={{ padding: "8px 16px" }}>
                      {record.snapshot_url ? (
                        <a
                          href={record.snapshot_url}
                          target="_blank"
                          rel="noreferrer"
                          title="Click to open full snapshot"
                          style={{ display: "inline-block", lineHeight: 0, borderRadius: 6, overflow: "hidden", border: "1px solid rgba(255,255,255,0.12)", boxShadow: "0 2px 8px rgba(0,0,0,0.4)" }}
                        >
                          <img
                            src={record.snapshot_url}
                            alt="Incident snapshot"
                            style={{ width: 96, height: 54, objectFit: "cover", display: "block" }}
                            loading="lazy"
                            onError={(e) => {
                              (e.currentTarget.parentElement as HTMLElement).innerHTML =
                                '<span style="color:#334155;font-size:11px;padding:4px 8px;display:inline-block">No image</span>';
                            }}
                          />
                        </a>
                      ) : (
                        <span style={{ color: "var(--app-text-muted)", fontSize: 11 }}>—</span>
                      )}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

    </div>
  );
}


