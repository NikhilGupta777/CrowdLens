import { useEffect, useState, ReactNode } from "react";
import { OverlayStyle } from "../components/SimulationCanvas";
import { useIsMobile } from "../hooks/use-mobile";
import {
  CheckCircle,
  Clock,
  Move,
  Package,
  ShieldAlert,
  Sliders,
  UserRoundX,
  Users,
  Zap,
} from "lucide-react";

interface Config {
  overcrowding_threshold: number;
  running_speed_threshold: number;
  unattended_object_time: number;
  stationary_threshold: number;
  unattended_owner_proximity_px: number;
  unattended_owner_grace_time: number;
  fall_model_confidence_threshold: number;
  fall_persistence_time: number;
  restricted_zone_enabled: boolean;
  restricted_zone_min_dwell: number;
  fight_detection_enabled: boolean;
  fight_proximity_px: number;
  fight_min_pair_speed: number;
  fight_persistence_time: number;
  fight_min_hit_streak: number;
  alert_cooldown_secs: number;
}

const DEFAULT_CONFIG: Config = {
  overcrowding_threshold: 4,
  running_speed_threshold: 18,
  unattended_object_time: 5,
  stationary_threshold: 150,
  unattended_owner_proximity_px: 180,
  unattended_owner_grace_time: 2.0,
  fall_model_confidence_threshold: 0.18,
  fall_persistence_time: 0.4,
  restricted_zone_enabled: true,
  restricted_zone_min_dwell: 0.6,
  fight_detection_enabled: true,
  fight_proximity_px: 180,
  fight_min_pair_speed: 16,
  fight_persistence_time: 0.8,
  fight_min_hit_streak: 3,
  alert_cooldown_secs: 5,
};

const COCO_CLASSES = [
  { id: 0, name: "Person", color: "#10b981" },
  { id: 24, name: "Backpack", color: "#f59e0b" },
  { id: 26, name: "Handbag", color: "#f59e0b" },
  { id: 28, name: "Suitcase", color: "#f59e0b" },
  { id: 39, name: "Bottle", color: "#f59e0b" },
  { id: 41, name: "Cup", color: "#f59e0b" },
  { id: 67, name: "Cell Phone", color: "#f59e0b" },
  { id: 73, name: "Book", color: "#f59e0b" },
];

function PremiumSlider({
  label,
  description,
  icon: Icon,
  color,
  value,
  min,
  max,
  step,
  onChange,
  unit,
}: {
  label: string;
  description: string;
  icon: typeof Sliders;
  color: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
  unit?: string;
}) {
  const pct = ((value - min) / (max - min)) * 100;

  return (
    <div style={{ marginBottom: 28 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
        <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
          <div style={{ background: `${color}18`, borderRadius: 8, padding: 7, marginTop: 1 }}>
            <Icon size={14} color={color} />
          </div>
          <div>
            <div style={{ fontWeight: 600, fontSize: 14, color: "var(--app-text)", marginBottom: 3 }}>{label}</div>
            <div style={{ fontSize: 11, color: "#475569", lineHeight: 1.5 }}>{description}</div>
          </div>
        </div>
        <div
          style={{
            background: `${color}18`,
            border: `1px solid ${color}33`,
            borderRadius: 10,
            padding: "6px 16px",
            fontSize: 20,
            fontWeight: 800,
            color,
            minWidth: 90,
            textAlign: "center",
            textShadow: `0 0 14px ${color}55`,
          }}
        >
          {value}
          {unit ?? ""}
        </div>
      </div>

      <div style={{ position: "relative", height: 6, background: "rgba(255,255,255,0.06)", borderRadius: 3 }}>
        <div
          style={{
            position: "absolute",
            left: 0,
            top: 0,
            bottom: 0,
            width: `${pct}%`,
            background: `linear-gradient(90deg, ${color}88, ${color})`,
            borderRadius: 3,
            transition: "width 0.1s",
          }}
        />
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
          style={{
            position: "absolute",
            inset: 0,
            width: "100%",
            opacity: 0,
            cursor: "pointer",
            height: "100%",
          }}
        />
        <div
          style={{
            position: "absolute",
            left: `${pct}%`,
            top: "50%",
            transform: "translate(-50%, -50%)",
            width: 14,
            height: 14,
            background: color,
            borderRadius: "50%",
            border: "2px solid #060a12",
            boxShadow: `0 0 8px ${color}`,
            pointerEvents: "none",
          }}
        />
      </div>

      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "#334155", marginTop: 8 }}>
        <span>{min}{unit}</span>
        <span>{max}{unit}</span>
      </div>
    </div>
  );
}

function ToggleCard({
  label,
  description,
  enabled,
  onToggle,
}: {
  label: string;
  description: string;
  enabled: boolean;
  onToggle: (next: boolean) => void;
}) {
  return (
    <div
      style={{
        border: "1px solid rgba(255,255,255,0.08)",
        borderRadius: 10,
        background: enabled ? "rgba(16,185,129,0.08)" : "rgba(255,255,255,0.02)",
        padding: "12px 14px",
        marginBottom: 18,
      }}
    >
      <label style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 14, cursor: "pointer" }}>
        <div>
          <div style={{ color: "var(--app-text)", fontWeight: 600, fontSize: 13, marginBottom: 3 }}>{label}</div>
          <div style={{ color: "#475569", fontSize: 11, lineHeight: 1.4 }}>{description}</div>
        </div>
        <input
          type="checkbox"
          checked={enabled}
          onChange={(e) => onToggle(e.target.checked)}
          style={{ width: 16, height: 16, cursor: "pointer" }}
        />
      </label>
    </div>
  );
}

const OVERLAY_OPTIONS: {
  id: OverlayStyle;
  label: string;
  tag: string;
  description: string;
  preview: ReactNode;
  color: string;
}[] = [
  {
    id: "corners",
    label: "Corner Brackets",
    tag: "DEFAULT",
    description: "L-shaped corner markers with ID labels and confidence. Best for identifying individuals.",
    color: "#3b82f6",
    preview: (
      <svg width="56" height="42" viewBox="0 0 56 42">
        <line x1="4" y1="16" x2="4" y2="4" stroke="#3b82f6" strokeWidth="2.2" strokeLinecap="square"/>
        <line x1="4" y1="4" x2="16" y2="4" stroke="#3b82f6" strokeWidth="2.2" strokeLinecap="square"/>
        <line x1="52" y1="4" x2="40" y2="4" stroke="#3b82f6" strokeWidth="2.2" strokeLinecap="square"/>
        <line x1="52" y1="4" x2="52" y2="16" stroke="#3b82f6" strokeWidth="2.2" strokeLinecap="square"/>
        <line x1="4" y1="26" x2="4" y2="38" stroke="#3b82f6" strokeWidth="2.2" strokeLinecap="square"/>
        <line x1="4" y1="38" x2="16" y2="38" stroke="#3b82f6" strokeWidth="2.2" strokeLinecap="square"/>
        <line x1="52" y1="38" x2="40" y2="38" stroke="#3b82f6" strokeWidth="2.2" strokeLinecap="square"/>
        <line x1="52" y1="26" x2="52" y2="38" stroke="#3b82f6" strokeWidth="2.2" strokeLinecap="square"/>
        <rect x="10" y="17" width="36" height="4" rx="2" fill="#3b82f6" opacity="0.3"/>
      </svg>
    ),
  },
  {
    id: "dots",
    label: "Glowing Dots",
    tag: "MINIMAL",
    description: "Small glowing dots at each person's feet with track ID. Clean look for dense crowds.",
    color: "#10b981",
    preview: (
      <svg width="56" height="42" viewBox="0 0 56 42">
        {[12, 28, 44].map((cx, i) => (
          <g key={i}>
            <circle cx={cx} cy={32} r={9} fill="#10b981" opacity="0.12"/>
            <circle cx={cx} cy={32} r={5} fill="#10b981" opacity="0.4"/>
            <circle cx={cx} cy={32} r={3} fill="#10b981"/>
            <rect x={cx - 8} y={14} width={16} height={10} rx={3} fill="#10b981" opacity="0.7"/>
            <text x={cx} y={22} textAnchor="middle" fill="#fff" fontSize="6" fontFamily="monospace" fontWeight="bold">#{i + 1}</text>
          </g>
        ))}
      </svg>
    ),
  },
  {
    id: "heatmap",
    label: "Density Heatmap",
    tag: "ANALYTICS",
    description: "Color density overlay showing crowd concentration. Best for crowd analytics and hotspot analysis.",
    color: "#f97316",
    preview: (
      <svg width="56" height="42" viewBox="0 0 56 42">
        <defs>
          <radialGradient id="h1" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#ef4444" stopOpacity="0.9"/>
            <stop offset="60%" stopColor="#f97316" stopOpacity="0.5"/>
            <stop offset="100%" stopColor="#3b82f6" stopOpacity="0"/>
          </radialGradient>
          <radialGradient id="h2" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#f97316" stopOpacity="0.8"/>
            <stop offset="100%" stopColor="#3b82f6" stopOpacity="0"/>
          </radialGradient>
        </defs>
        <ellipse cx="22" cy="22" rx="18" ry="16" fill="url(#h1)"/>
        <ellipse cx="40" cy="18" rx="14" ry="12" fill="url(#h2)"/>
        <circle cx="22" cy="22" r="2" fill="white" opacity="0.7"/>
        <circle cx="40" cy="18" r="2" fill="white" opacity="0.7"/>
      </svg>
    ),
  },
  {
    id: "chips",
    label: "ID Chips Only",
    tag: "ULTRA CLEAN",
    description: "Just floating ID label chips, no boxes or markers. Most minimal — best for very large crowds.",
    color: "#a855f7",
    preview: (
      <svg width="56" height="42" viewBox="0 0 56 42">
        {[[4, 8], [18, 22], [32, 12], [10, 30]].map(([x, y], i) => (
          <g key={i}>
            <rect x={x} y={y} width={22} height={11} rx={4} fill="#a855f7" opacity="0.75"/>
            <text x={x + 11} y={y + 8} textAnchor="middle" fill="#fff" fontSize="6" fontFamily="monospace" fontWeight="bold">#{i + 1}</text>
          </g>
        ))}
      </svg>
    ),
  },
  {
    id: "auto",
    label: "Automatic",
    tag: "SMART",
    description: "Switches style based on crowd count: brackets (<8 people), chips (8–20), dots (20+). Always optimal.",
    color: "#eab308",
    preview: (
      <svg width="56" height="42" viewBox="0 0 56 42">
        <text x="28" y="16" textAnchor="middle" fill="#eab308" fontSize="9" fontFamily="monospace" fontWeight="bold">&lt;8</text>
        <line x1="14" y1="22" x2="14" y2="17" stroke="#3b82f6" strokeWidth="1.5"/>
        <line x1="14" y1="17" x2="19" y2="17" stroke="#3b82f6" strokeWidth="1.5"/>
        <text x="28" y="28" textAnchor="middle" fill="#eab308" fontSize="9" fontFamily="monospace" fontWeight="bold">20+</text>
        <circle cx="42" cy="35" r="4" fill="#10b981" opacity="0.9"/>
        <circle cx="42" cy="35" r="7" fill="#10b981" opacity="0.25"/>
        <rect x="18" y="33" width="14" height="7" rx="3" fill="#a855f7" opacity="0.75"/>
        <text x="25" y="39" textAnchor="middle" fill="#fff" fontSize="5" fontFamily="monospace">#12</text>
      </svg>
    ),
  },
];

export default function Settings() {
  const isMobile = useIsMobile();
  const [config, setConfig] = useState<Config>(DEFAULT_CONFIG);

  const [overlayStyle, setOverlayStyleState] = useState<OverlayStyle>(() => {
    return (localStorage.getItem("crowdlens_overlay_style") as OverlayStyle) ?? "corners";
  });

  const [boxSmooth, setBoxSmoothState] = useState<number>(() => {
    const saved = localStorage.getItem("crowdlens_box_smooth");
    return saved !== null ? parseFloat(saved) : 0.7;
  });

  const setOverlayStyle = (s: OverlayStyle) => {
    setOverlayStyleState(s);
    localStorage.setItem("crowdlens_overlay_style", s);
    window.dispatchEvent(new StorageEvent("storage", { key: "crowdlens_overlay_style", newValue: s }));
  };

  const setBoxSmooth = (v: number) => {
    setBoxSmoothState(v);
    localStorage.setItem("crowdlens_box_smooth", String(v));
    window.dispatchEvent(new StorageEvent("storage", { key: "crowdlens_box_smooth", newValue: String(v) }));
  };
  const [saved, setSaved] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/config")
      .then((r) => r.json())
      .then((data) => {
        setConfig({
          ...DEFAULT_CONFIG,
          ...data,
        });
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  useEffect(() => {
    const poll = async () => {
      if (document.visibilityState !== "visible") return;
      try {
        const res = await fetch("/api/config");
        const data = await res.json();
        setConfig((prev) => ({
          ...prev,
          restricted_zone_enabled:
            typeof data.restricted_zone_enabled === "boolean"
              ? data.restricted_zone_enabled
              : prev.restricted_zone_enabled,
          restricted_zone_min_dwell:
            typeof data.restricted_zone_min_dwell === "number"
              ? data.restricted_zone_min_dwell
              : prev.restricted_zone_min_dwell,
        }));
      } catch {
        // Keep previous local state on transient poll failures.
      }
    };
    const id = setInterval(poll, 2000);
    return () => clearInterval(id);
  }, []);

  const handleSave = async () => {
    setSaveError(null);
    try {
      const response = await fetch("/api/config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config),
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail ?? "Unable to save settings");
      }
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (err: unknown) {
      setSaveError(err instanceof Error ? err.message : "Unable to save settings");
    }
  };

  if (loading) {
    return (
      <div style={{ display: "flex", justifyContent: "center", padding: 60 }}>
        <div style={{ color: "#334155", fontSize: 13 }}>Loading configuration...</div>
      </div>
    );
  }

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 28 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 700, color: "var(--app-text)", letterSpacing: -0.5, marginBottom: 4 }}>
            Detection Settings
          </h1>
          <p style={{ color: "#475569", fontSize: 13 }}>
            Configure anomaly thresholds for crowding, motion, fall detection, and digital fencing.
          </p>
        </div>

        <button
          onClick={handleSave}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            padding: "10px 24px",
            borderRadius: 10,
            background: saved
              ? "linear-gradient(135deg, #059669, #10b981)"
              : "linear-gradient(135deg, #1d4ed8, #3b82f6)",
            color: "#fff",
            border: "none",
            fontWeight: 700,
            fontSize: 14,
            cursor: "pointer",
            boxShadow: saved ? "0 4px 20px #10b98155" : "0 4px 20px #3b82f655",
            transition: "all 0.3s",
          }}
        >
          {saved ? <CheckCircle size={15} /> : <Sliders size={15} />}
          {saved ? "Applied" : "Apply Settings"}
        </button>
      </div>

      {saveError && (
        <div style={{ color: "#ef4444", fontSize: 12, marginBottom: 12 }}>{saveError}</div>
      )}

      {/* ── Overlay Style ──────────────────────────────────────────────────── */}
      <div style={{
        background: "var(--app-card-bg)",
        border: "1px solid var(--app-card-border)",
        borderRadius: 14,
        padding: 24,
        marginBottom: 20,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 20 }}>
          <div style={{ fontSize: 9, color: "#475569", letterSpacing: 2, fontWeight: 700 }}>
            DETECTION OVERLAY STYLE
          </div>
          <div style={{
            marginLeft: "auto",
            background: "rgba(99,102,241,0.15)",
            color: "#818cf8",
            fontSize: 9,
            fontWeight: 800,
            padding: "2px 8px",
            borderRadius: 10,
            letterSpacing: 1,
          }}>
            LIVE PREVIEW
          </div>
        </div>

        <div style={{
          display: "grid",
          gridTemplateColumns: isMobile ? "1fr 1fr" : "repeat(5, 1fr)",
          gap: 10,
        }}>
          {OVERLAY_OPTIONS.map((opt) => {
            const active = overlayStyle === opt.id;
            return (
              <button
                key={opt.id}
                onClick={() => setOverlayStyle(opt.id)}
                style={{
                  background: active
                    ? `linear-gradient(135deg, ${opt.color}22, ${opt.color}10)`
                    : "rgba(255,255,255,0.02)",
                  border: `1.5px solid ${active ? opt.color : "rgba(255,255,255,0.07)"}`,
                  borderRadius: 12,
                  padding: "14px 10px 12px",
                  cursor: "pointer",
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  gap: 8,
                  transition: "all 0.18s",
                  boxShadow: active ? `0 0 18px ${opt.color}33` : "none",
                  position: "relative",
                }}
              >
                {active && (
                  <div style={{
                    position: "absolute",
                    top: 6,
                    right: 6,
                    width: 7,
                    height: 7,
                    borderRadius: "50%",
                    background: opt.color,
                    boxShadow: `0 0 6px ${opt.color}`,
                  }} />
                )}
                <div style={{
                  background: "rgba(0,0,0,0.3)",
                  borderRadius: 8,
                  padding: "6px 8px",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  minHeight: 52,
                }}>
                  {opt.preview}
                </div>
                <div style={{ textAlign: "center" }}>
                  <div style={{
                    fontSize: 11,
                    fontWeight: 700,
                    color: active ? opt.color : "#94a3b8",
                    marginBottom: 3,
                  }}>
                    {opt.label}
                  </div>
                  <div style={{
                    fontSize: 8,
                    fontWeight: 800,
                    color: active ? opt.color + "aa" : "#334155",
                    letterSpacing: 1.2,
                    marginBottom: 5,
                  }}>
                    {opt.tag}
                  </div>
                  <div style={{
                    fontSize: 9,
                    color: "#475569",
                    lineHeight: 1.4,
                    display: isMobile ? "none" : "block",
                  }}>
                    {opt.description}
                  </div>
                </div>
              </button>
            );
          })}
        </div>

        <div style={{ marginTop: 20, paddingTop: 20, borderTop: "1px solid rgba(255,255,255,0.05)" }}>
          <PremiumSlider
            label="Bounding Box Smoothing"
            description="Controls how quickly detection boxes catch up to real positions. Lower = snappier, higher = smoother motion."
            icon={Sliders}
            color="#6366f1"
            value={boxSmooth}
            min={0}
            max={1}
            step={0.05}
            onChange={setBoxSmooth}
          />
        </div>

        <div style={{ marginTop: 4, fontSize: 11, color: "#334155" }}>
          Overlay style and smoothing apply instantly to the live canvas — no save required.
          Anomaly warnings (overcrowding, fights, falls) always remain visible regardless of style.
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr", gap: 20, marginBottom: 20 }}>
        <div
          style={{
            background: "var(--app-card-bg)",
            border: "1px solid var(--app-card-border)",
            borderRadius: 14,
            padding: 24,
          }}
        >
          <div style={{ fontSize: 9, color: "#475569", letterSpacing: 2, fontWeight: 700, marginBottom: 24 }}>
            CROWD AND OCCUPANCY
          </div>

          <PremiumSlider
            label="Overcrowding Threshold"
            description="Trigger alert when persons in frame exceed this value."
            icon={Users}
            color="#f97316"
            value={config.overcrowding_threshold}
            min={1}
            max={20}
            step={1}
            onChange={(v) => setConfig((c) => ({ ...c, overcrowding_threshold: v }))}
            unit=" ppl"
          />

          <PremiumSlider
            label="Stationary Distance Limit"
            description="Movement below this pixel distance is treated as stationary."
            icon={Move}
            color="#3b82f6"
            value={config.stationary_threshold}
            min={20}
            max={300}
            step={10}
            onChange={(v) => setConfig((c) => ({ ...c, stationary_threshold: v }))}
            unit=" px"
          />
        </div>

        <div
          style={{
            background: "var(--app-card-bg)",
            border: "1px solid var(--app-card-border)",
            borderRadius: 14,
            padding: 24,
          }}
        >
          <div style={{ fontSize: 9, color: "#475569", letterSpacing: 2, fontWeight: 700, marginBottom: 24 }}>
            MOTION AND OBJECTS
          </div>

          <PremiumSlider
            label="Running Speed Threshold"
            description="Average pixel-per-frame speed above this is flagged as running."
            icon={Zap}
            color="#a855f7"
            value={config.running_speed_threshold}
            min={5}
            max={100}
            step={1}
            onChange={(v) => setConfig((c) => ({ ...c, running_speed_threshold: v }))}
            unit=" px/f"
          />

          <PremiumSlider
            label="Unattended Object Time"
            description="Seconds an object must remain still before alerting."
            icon={Clock}
            color="#ef4444"
            value={config.unattended_object_time}
            min={1}
            max={30}
            step={1}
            onChange={(v) => setConfig((c) => ({ ...c, unattended_object_time: v }))}
            unit=" s"
          />

          <PremiumSlider
            label="Owner Proximity Radius"
            description="Object is treated as attended if any person is within this radius."
            icon={Users}
            color="#f97316"
            value={config.unattended_owner_proximity_px}
            min={40}
            max={350}
            step={10}
            onChange={(v) => setConfig((c) => ({ ...c, unattended_owner_proximity_px: v }))}
            unit=" px"
          />

          <PremiumSlider
            label="Owner Absence Grace Time"
            description="Person must be away for this long before unattended alerting starts."
            icon={Clock}
            color="#ef4444"
            value={config.unattended_owner_grace_time}
            min={0.5}
            max={10}
            step={0.1}
            onChange={(v) => setConfig((c) => ({ ...c, unattended_owner_grace_time: Number(v.toFixed(1)) }))}
            unit=" s"
          />
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr", gap: 20, marginBottom: 20 }}>
        <div
          style={{
            background: "var(--app-card-bg)",
            border: "1px solid var(--app-card-border)",
            borderRadius: 14,
            padding: 24,
          }}
        >
          <div style={{ fontSize: 9, color: "#475569", letterSpacing: 2, fontWeight: 700, marginBottom: 24 }}>
            FALL DETECTION
          </div>

          <PremiumSlider
            label="Fall Model Confidence"
            description="Minimum confidence from the Hugging Face fall model to treat a detection as fallen."
            icon={UserRoundX}
            color="#dc2626"
            value={config.fall_model_confidence_threshold}
            min={0.05}
            max={0.95}
            step={0.05}
            onChange={(v) => setConfig((c) => ({ ...c, fall_model_confidence_threshold: Number(v.toFixed(2)) }))}
          />

          <PremiumSlider
            label="Fall Confirmation Window"
            description="Seconds fallen detection must persist before emitting a fall alert."
            icon={Clock}
            color="#dc2626"
            value={config.fall_persistence_time}
            min={0.2}
            max={5}
            step={0.1}
            onChange={(v) => setConfig((c) => ({ ...c, fall_persistence_time: Number(v.toFixed(1)) }))}
            unit=" s"
          />
        </div>

        <div
          style={{
            background: "var(--app-card-bg)",
            border: "1px solid var(--app-card-border)",
            borderRadius: 14,
            padding: 24,
          }}
        >
          <div style={{ fontSize: 9, color: "#475569", letterSpacing: 2, fontWeight: 700, marginBottom: 24 }}>
            DIGITAL FENCING
          </div>

          <ToggleCard
            label="Restricted Zone Monitoring"
            description="Detect people entering configured restricted regions."
            enabled={config.restricted_zone_enabled}
            onToggle={(next) => setConfig((c) => ({ ...c, restricted_zone_enabled: next }))}
          />

          <PremiumSlider
            label="Restricted Zone Dwell Time"
            description="Minimum time inside restricted region before raising alert."
            icon={ShieldAlert}
            color="#eab308"
            value={config.restricted_zone_min_dwell}
            min={0.2}
            max={10}
            step={0.1}
            onChange={(v) => setConfig((c) => ({ ...c, restricted_zone_min_dwell: Number(v.toFixed(1)) }))}
            unit=" s"
          />
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: 20, marginBottom: 20 }}>
        <div
          style={{
            background: "var(--app-card-bg)",
            border: "1px solid var(--app-card-border)",
            borderRadius: 14,
            padding: 24,
          }}
        >
          <div style={{ fontSize: 9, color: "#475569", letterSpacing: 2, fontWeight: 700, marginBottom: 24 }}>
            FIGHT PROTOTYPE
          </div>

          <ToggleCard
            label="Fight Suspicion Monitoring"
            description="Heuristic pair-motion detector for close high-speed person interactions."
            enabled={config.fight_detection_enabled}
            onToggle={(next) => setConfig((c) => ({ ...c, fight_detection_enabled: next }))}
          />

          <PremiumSlider
            label="Fight Pair Proximity"
            description="Maximum distance between two persons to consider a possible fight pair."
            icon={Users}
            color="#f43f5e"
            value={config.fight_proximity_px}
            min={60}
            max={320}
            step={10}
            onChange={(v) => setConfig((c) => ({ ...c, fight_proximity_px: v }))}
            unit=" px"
          />

          <PremiumSlider
            label="Fight Pair Speed"
            description="Both persons must exceed this average speed for suspicion."
            icon={Zap}
            color="#f43f5e"
            value={config.fight_min_pair_speed}
            min={6}
            max={80}
            step={1}
            onChange={(v) => setConfig((c) => ({ ...c, fight_min_pair_speed: v }))}
            unit=" px/f"
          />

          <PremiumSlider
            label="Fight Persistence"
            description="How long suspicious pair behavior must continue before alert."
            icon={Clock}
            color="#f43f5e"
            value={config.fight_persistence_time}
            min={0.2}
            max={5}
            step={0.1}
            onChange={(v) => setConfig((c) => ({ ...c, fight_persistence_time: Number(v.toFixed(1)) }))}
            unit=" s"
          />

          <PremiumSlider
            label="Fight Min Track Stability"
            description="Minimum tracker hit-streak for each person before pair evaluation."
            icon={CheckCircle}
            color="#f43f5e"
            value={config.fight_min_hit_streak}
            min={1}
            max={10}
            step={1}
            onChange={(v) => setConfig((c) => ({ ...c, fight_min_hit_streak: v }))}
          />
        </div>
      </div>

      <div
        style={{
          background: "var(--app-card-bg)",
          border: "1px solid var(--app-card-border)",
          borderRadius: 14,
          padding: 24,
          marginBottom: 20,
        }}
      >
        <div style={{ fontSize: 9, color: "#475569", letterSpacing: 2, fontWeight: 700, marginBottom: 24 }}>
          ALERT BEHAVIOUR
        </div>

        <PremiumSlider
          label="Alert Cooldown"
          description="Minimum seconds between repeat alerts of the same type for the same track. Lower values increase sensitivity; higher values reduce noise."
          icon={Clock}
          color="#3b82f6"
          value={config.alert_cooldown_secs}
          min={1}
          max={60}
          step={1}
          onChange={(v) => setConfig((c) => ({ ...c, alert_cooldown_secs: v }))}
          unit=" s"
        />
      </div>

      <div
        style={{
          background: "var(--app-card-bg)",
          border: "1px solid var(--app-card-border)",
          borderRadius: 14,
          padding: 24,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 18 }}>
          <Package size={14} color="#475569" />
          <div style={{ fontSize: 9, color: "#475569", letterSpacing: 2, fontWeight: 700 }}>
            MONITORED DETECTION CLASSES
          </div>
          <div
            style={{
              marginLeft: "auto",
              background: "rgba(59,130,246,0.1)",
              color: "#3b82f6",
              fontSize: 9,
              fontWeight: 800,
              padding: "2px 8px",
              borderRadius: 10,
              letterSpacing: 1,
            }}
          >
            COCO DATASET
          </div>
        </div>

        <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
          {COCO_CLASSES.map((item) => (
            <div
              key={item.id}
              style={{
                background: `${item.color}10`,
                color: item.color,
                border: `1px solid ${item.color}30`,
                borderRadius: 10,
                padding: "8px 14px",
                fontSize: 12,
                fontWeight: 600,
                display: "flex",
                alignItems: "center",
                gap: 7,
              }}
            >
              {item.name}
              <span
                style={{
                  background: "rgba(0,0,0,0.3)",
                  color: "#475569",
                  fontSize: 9,
                  fontWeight: 700,
                  padding: "1px 6px",
                  borderRadius: 6,
                }}
              >
                ID:{item.id}
              </span>
            </div>
          ))}
        </div>

        <div style={{ fontSize: 11, color: "#1e3a5f", marginTop: 14 }}>
          Person and unattended-object classes are tracked by YOLO11m plus SORT. Fall, restricted-zone, and
          fight-suspicion prototype settings are active immediately after applying this configuration.
        </div>
      </div>
    </div>
  );
}

