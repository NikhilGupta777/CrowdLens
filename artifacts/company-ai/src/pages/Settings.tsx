import { useEffect, useRef, useState, useCallback, ReactNode } from "react";
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

interface ZoneRect {
  id: string;
  name: string;
  shape: "rect";
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

interface ZonePolygon {
  id: string;
  name: string;
  shape: "polygon";
  points: [number, number][];
}

type Zone = ZoneRect | ZonePolygon;

interface Config {
  overcrowding_threshold: number;
  running_speed_threshold: number;
  running_body_heights_per_sec: number;
  running_pixel_floor: number;
  unattended_object_time: number;
  stationary_threshold: number;
  unattended_owner_proximity_px: number;
  unattended_owner_grace_time: number;
  unattended_bystander_attends: boolean;
  unattended_ghost_ttl: number;
  overcrowding_cluster_distance_px: number;
  overcrowding_min_cluster_size: number;
  fall_model_confidence_threshold: number;
  fall_persistence_time: number;
  fall_person_iou_min: number;
  restricted_zone_enabled: boolean;
  restricted_zone_min_dwell: number;
  fight_detection_enabled: boolean;
  fight_proximity_px: number;
  fight_min_pair_speed: number;
  fight_persistence_time: number;
  fight_min_hit_streak: number;
  alert_cooldown_secs: number;
  loitering_enabled: boolean;
  loitering_time_threshold: number;
  loitering_radius_px: number;
  alert_escalation_secs: number;
  // Phase 5 — PPE / Face / LPR
  ppe_detection_enabled: boolean;
  ppe_confidence_threshold: number;
  face_detection_enabled: boolean;
  face_scale_factor: number;
  face_min_neighbors: number;
  lpr_detection_enabled: boolean;
  lpr_confidence_threshold: number;
}

// Defaults match backend/config.py exactly. Mismatches previously caused the
// UI to display values different from what the detector actually used until
// the user clicked Save (e.g. loitering_radius_px showed 120 while the
// detector ran with 180; stationary_threshold showed 150 while the detector
// ran with 110.0). Now the UI mirrors the source of truth.
const DEFAULT_CONFIG: Config = {
  overcrowding_threshold: 4,
  running_speed_threshold: 270,
  running_body_heights_per_sec: 1.6,
  running_pixel_floor: 60,
  unattended_object_time: 5,
  stationary_threshold: 110,
  unattended_owner_proximity_px: 180,
  unattended_owner_grace_time: 2.0,
  unattended_bystander_attends: true,
  unattended_ghost_ttl: 8.0,
  overcrowding_cluster_distance_px: 200,
  overcrowding_min_cluster_size: 4,
  fall_model_confidence_threshold: 0.35,
  fall_persistence_time: 1.2,
  fall_person_iou_min: 0.20,
  restricted_zone_enabled: true,
  restricted_zone_min_dwell: 0.6,
  fight_detection_enabled: true,
  fight_proximity_px: 180,
  fight_min_pair_speed: 240,
  fight_persistence_time: 0.8,
  fight_min_hit_streak: 3,
  alert_cooldown_secs: 5,
  loitering_enabled: true,
  loitering_time_threshold: 15,
  loitering_radius_px: 180,
  alert_escalation_secs: 60,
  // Phase 5 — PPE / Face / LPR (opt-in extras, off by default)
  ppe_detection_enabled: false,
  ppe_confidence_threshold: 0.40,
  face_detection_enabled: false,
  face_scale_factor: 1.3,
  face_min_neighbors: 5,
  lpr_detection_enabled: false,
  lpr_confidence_threshold: 0.40,
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

// ── Canvas dimensions (half the canonical 1280×720 space) ──────────────────
const CANVAS_W = 640;
const CANVAS_H = 360;
const SCALE = 0.5; // canvas px = canonical px * SCALE

/** Convert canonical coords → canvas coords */
const toCanvas = (v: number) => v * SCALE;
/** Convert canvas coords → canonical coords */
const toCanonical = (v: number) => Math.round(v / SCALE);

const ZONE_COLORS = [
  "#eab308", "#f97316", "#3b82f6", "#10b981",
  "#a855f7", "#f43f5e", "#06b6d4", "#84cc16",
];

function getZoneColor(idx: number) {
  return ZONE_COLORS[idx % ZONE_COLORS.length];
}

// ── Rect handle positions: 8 handles around the rect ──────────────────────
type RectHandle = "tl" | "tm" | "tr" | "ml" | "mr" | "bl" | "bm" | "br" | "body";
function getRectHandles(z: ZoneRect): Record<RectHandle, [number, number]> {
  const x1 = toCanvas(z.x1), y1 = toCanvas(z.y1);
  const x2 = toCanvas(z.x2), y2 = toCanvas(z.y2);
  const mx = (x1 + x2) / 2, my = (y1 + y2) / 2;
  return {
    tl: [x1, y1], tm: [mx, y1], tr: [x2, y1],
    ml: [x1, my],               mr: [x2, my],
    bl: [x1, y2], bm: [mx, y2], br: [x2, y2],
    body: [mx, my],
  };
}

interface ZoneCanvasProps {
  zones: Zone[];
  onUpdateZone: (zone: Zone) => void;
}

function ZoneCanvas({ zones, onUpdateZone }: ZoneCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  // Drag state stored in a ref so it doesn't trigger re-renders on every mouse-move
  const dragRef = useRef<{
    zoneId: string;
    type: "rectHandle" | "polyVertex" | "body";
    handle?: RectHandle;
    vertexIdx?: number;
    startCanvasX: number;
    startCanvasY: number;
    startZone: Zone;
  } | null>(null);

  // ── Draw ────────────────────────────────────────────────────────────────
  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    ctx.clearRect(0, 0, CANVAS_W, CANVAS_H);

    // Background
    ctx.fillStyle = "rgba(6,10,18,0.95)";
    ctx.fillRect(0, 0, CANVAS_W, CANVAS_H);

    // Grid
    ctx.strokeStyle = "rgba(255,255,255,0.05)";
    ctx.lineWidth = 1;
    for (let x = 0; x <= CANVAS_W; x += 40) {
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, CANVAS_H); ctx.stroke();
    }
    for (let y = 0; y <= CANVAS_H; y += 40) {
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(CANVAS_W, y); ctx.stroke();
    }

    zones.forEach((zone, idx) => {
      const color = getZoneColor(idx);
      if (zone.shape === "rect") {
        const x1 = toCanvas(zone.x1), y1 = toCanvas(zone.y1);
        const w = toCanvas(zone.x2) - x1, h = toCanvas(zone.y2) - y1;
        // Fill
        ctx.fillStyle = color + "22";
        ctx.fillRect(x1, y1, w, h);
        // Border
        ctx.strokeStyle = color;
        ctx.lineWidth = 1.5;
        ctx.setLineDash([]);
        ctx.strokeRect(x1, y1, w, h);
        // Handles
        const handles = getRectHandles(zone);
        (Object.entries(handles) as [RectHandle, [number, number]][]).forEach(([key, [hx, hy]]) => {
          if (key === "body") return;
          ctx.fillStyle = "#ffffff";
          ctx.strokeStyle = color;
          ctx.lineWidth = 1.5;
          ctx.beginPath();
          ctx.arc(hx, hy, 5, 0, Math.PI * 2);
          ctx.fill(); ctx.stroke();
        });
        // Label
        ctx.fillStyle = color;
        ctx.font = "bold 11px monospace";
        ctx.fillText(zone.name, x1 + 6, y1 + 14);
      } else {
        // Polygon
        const pts = zone.points.map(([px, py]) => [toCanvas(px), toCanvas(py)] as [number, number]);
        if (pts.length < 2) return;
        ctx.beginPath();
        ctx.moveTo(pts[0][0], pts[0][1]);
        for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]);
        ctx.closePath();
        ctx.fillStyle = color + "22";
        ctx.fill();
        ctx.strokeStyle = color;
        ctx.lineWidth = 1.5;
        ctx.setLineDash([]);
        ctx.stroke();
        // Vertex dots
        pts.forEach(([vx, vy]) => {
          ctx.fillStyle = "#ffffff";
          ctx.strokeStyle = color;
          ctx.lineWidth = 1.5;
          ctx.beginPath();
          ctx.arc(vx, vy, 5, 0, Math.PI * 2);
          ctx.fill(); ctx.stroke();
        });
        // Label (near centroid)
        const cx = pts.reduce((s, [x]) => s + x, 0) / pts.length;
        const cy = pts.reduce((s, [, y]) => s + y, 0) / pts.length;
        ctx.fillStyle = color;
        ctx.font = "bold 11px monospace";
        ctx.fillText(zone.name, cx - 20, cy + 4);
      }
    });
  }, [zones]);

  useEffect(() => { draw(); }, [draw]);

  // ── Mouse helpers ────────────────────────────────────────────────────────
  const getCanvasPos = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = canvasRef.current!.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  };

  const hitRadius = 8;

  const findHit = useCallback((cx: number, cy: number): typeof dragRef.current => {
    // Test in reverse order (topmost zone drawn last gets priority)
    for (let i = zones.length - 1; i >= 0; i--) {
      const zone = zones[i];
      if (zone.shape === "rect") {
        const handles = getRectHandles(zone);
        for (const [key, [hx, hy]] of Object.entries(handles) as [RectHandle, [number, number]][]) {
          if (key === "body") continue;
          if (Math.hypot(cx - hx, cy - hy) <= hitRadius) {
            return { zoneId: zone.id, type: "rectHandle", handle: key as RectHandle, startCanvasX: cx, startCanvasY: cy, startZone: zone };
          }
        }
        // Body hit (inside rect)
        const x1c = toCanvas(zone.x1), y1c = toCanvas(zone.y1);
        const x2c = toCanvas(zone.x2), y2c = toCanvas(zone.y2);
        if (cx >= x1c && cx <= x2c && cy >= y1c && cy <= y2c) {
          return { zoneId: zone.id, type: "body", startCanvasX: cx, startCanvasY: cy, startZone: zone };
        }
      } else {
        const pts = zone.points.map(([px, py]) => [toCanvas(px), toCanvas(py)] as [number, number]);
        // Vertex hit
        for (let v = 0; v < pts.length; v++) {
          if (Math.hypot(cx - pts[v][0], cy - pts[v][1]) <= hitRadius) {
            return { zoneId: zone.id, type: "polyVertex", vertexIdx: v, startCanvasX: cx, startCanvasY: cy, startZone: zone };
          }
        }
        // Body hit (point in polygon)
        if (isPointInPolygon(cx, cy, pts)) {
          return { zoneId: zone.id, type: "body", startCanvasX: cx, startCanvasY: cy, startZone: zone };
        }
      }
    }
    return null;
  }, [zones]);

  const onMouseDown = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    if (e.button !== 0) return;
    const { x, y } = getCanvasPos(e);
    dragRef.current = findHit(x, y);
  }, [findHit]);

  const onMouseMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const drag = dragRef.current;
    if (!drag) return;
    const { x, y } = getCanvasPos(e);
    const dx = x - drag.startCanvasX;
    const dy = y - drag.startCanvasY;
    const sz = drag.startZone;

    if (sz.shape === "rect") {
      let nx1 = sz.x1, ny1 = sz.y1, nx2 = sz.x2, ny2 = sz.y2;
      const cdx = toCanonical(dx), cdy = toCanonical(dy);
      if (drag.type === "body") {
        nx1 = clampC(sz.x1 + cdx, 0, 1280); nx2 = clampC(sz.x2 + cdx, 0, 1280);
        ny1 = clampC(sz.y1 + cdy, 0, 720);  ny2 = clampC(sz.y2 + cdy, 0, 720);
      } else {
        const h = drag.handle!;
        if (h.includes("l")) nx1 = clampC(sz.x1 + cdx, 0, sz.x2 - 4);
        if (h.includes("r")) nx2 = clampC(sz.x2 + cdx, sz.x1 + 4, 1280);
        if (h.includes("t")) ny1 = clampC(sz.y1 + cdy, 0, sz.y2 - 4);
        if (h.includes("b")) ny2 = clampC(sz.y2 + cdy, sz.y1 + 4, 720);
      }
      const updated: ZoneRect = { ...sz, x1: nx1, y1: ny1, x2: nx2, y2: ny2 };
      // Optimistic update for smooth visual feedback (deferred API call on mouseUp)
      // We update the parent via a synthetic zone state in onUpdateZone—
      // but to avoid hammering the API, we store the live zone locally
      // and only persist on mouseUp. Use a canvas-only preview here:
      const canvas = canvasRef.current;
      if (!canvas) return;
      const ctx = canvas.getContext("2d")!;
      const color = getZoneColor(zones.findIndex(z => z.id === sz.id));
      // Re-draw with live preview
      drawPreview(ctx, zones, sz.id, updated);
    } else if (sz.shape === "polygon") {
      const pts = sz.points.map(([px, py]) => [px, py] as [number, number]);
      if (drag.type === "polyVertex" && drag.vertexIdx !== undefined) {
        pts[drag.vertexIdx] = [
          clampC(sz.points[drag.vertexIdx][0] + toCanonical(dx), 0, 1280),
          clampC(sz.points[drag.vertexIdx][1] + toCanonical(dy), 0, 720),
        ];
      } else if (drag.type === "body") {
        const cdx = toCanonical(dx), cdy = toCanonical(dy);
        for (let i = 0; i < pts.length; i++) {
          pts[i] = [clampC(sz.points[i][0] + cdx, 0, 1280), clampC(sz.points[i][1] + cdy, 0, 720)];
        }
      }
      const updated: ZonePolygon = { ...sz, points: pts };
      const canvas = canvasRef.current;
      if (!canvas) return;
      const ctx = canvas.getContext("2d")!;
      drawPreview(ctx, zones, sz.id, updated);
    }
  }, [zones]);

  const onMouseUp = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const drag = dragRef.current;
    if (!drag) return;
    dragRef.current = null;
    const { x, y } = getCanvasPos(e);
    const dx = x - drag.startCanvasX;
    const dy = y - drag.startCanvasY;
    const sz = drag.startZone;

    if (Math.hypot(dx, dy) < 2) return; // no movement — not a drag

    if (sz.shape === "rect") {
      let nx1 = sz.x1, ny1 = sz.y1, nx2 = sz.x2, ny2 = sz.y2;
      const cdx = toCanonical(dx), cdy = toCanonical(dy);
      if (drag.type === "body") {
        nx1 = clampC(sz.x1 + cdx, 0, 1280); nx2 = clampC(sz.x2 + cdx, 0, 1280);
        ny1 = clampC(sz.y1 + cdy, 0, 720);  ny2 = clampC(sz.y2 + cdy, 0, 720);
      } else {
        const h = drag.handle!;
        if (h.includes("l")) nx1 = clampC(sz.x1 + cdx, 0, sz.x2 - 4);
        if (h.includes("r")) nx2 = clampC(sz.x2 + cdx, sz.x1 + 4, 1280);
        if (h.includes("t")) ny1 = clampC(sz.y1 + cdy, 0, sz.y2 - 4);
        if (h.includes("b")) ny2 = clampC(sz.y2 + cdy, sz.y1 + 4, 720);
      }
      onUpdateZone({ ...sz, x1: nx1, y1: ny1, x2: nx2, y2: ny2 });
    } else if (sz.shape === "polygon") {
      const pts = sz.points.map(([px, py]) => [px, py] as [number, number]);
      if (drag.type === "polyVertex" && drag.vertexIdx !== undefined) {
        pts[drag.vertexIdx] = [
          clampC(sz.points[drag.vertexIdx][0] + toCanonical(dx), 0, 1280),
          clampC(sz.points[drag.vertexIdx][1] + toCanonical(dy), 0, 720),
        ];
      } else if (drag.type === "body") {
        const cdx = toCanonical(dx), cdy = toCanonical(dy);
        for (let i = 0; i < pts.length; i++) {
          pts[i] = [clampC(sz.points[i][0] + cdx, 0, 1280), clampC(sz.points[i][1] + cdy, 0, 720)];
        }
      }
      onUpdateZone({ ...sz, points: pts });
    }
  }, [zones, onUpdateZone]);

  // Double-click on polygon vertex → delete it
  const onDoubleClick = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const { x, y } = getCanvasPos(e);
    for (let i = zones.length - 1; i >= 0; i--) {
      const zone = zones[i];
      if (zone.shape !== "polygon") continue;
      const pts = zone.points.map(([px, py]) => [toCanvas(px), toCanvas(py)] as [number, number]);
      for (let v = 0; v < pts.length; v++) {
        if (Math.hypot(x - pts[v][0], y - pts[v][1]) <= hitRadius + 2) {
          if (pts.length <= 3) return; // minimum 3 vertices
          const newPts = zone.points.filter((_, idx) => idx !== v);
          onUpdateZone({ ...zone, points: newPts });
          return;
        }
      }
    }
  }, [zones, onUpdateZone]);

  // Right-click on polygon edge → insert vertex
  const onContextMenu = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    e.preventDefault();
    const { x, y } = getCanvasPos(e);
    for (let i = zones.length - 1; i >= 0; i--) {
      const zone = zones[i];
      if (zone.shape !== "polygon") continue;
      const pts = zone.points.map(([px, py]) => [toCanvas(px), toCanvas(py)] as [number, number]);
      // Find closest edge
      let bestDist = 12;
      let bestIdx = -1;
      for (let v = 0; v < pts.length; v++) {
        const next = (v + 1) % pts.length;
        const dist = distToSegment(x, y, pts[v][0], pts[v][1], pts[next][0], pts[next][1]);
        if (dist < bestDist) { bestDist = dist; bestIdx = v; }
      }
      if (bestIdx >= 0) {
        const newPts = [...zone.points];
        newPts.splice(bestIdx + 1, 0, [toCanonical(x), toCanonical(y)]);
        onUpdateZone({ ...zone, points: newPts });
        return;
      }
    }
  }, [zones, onUpdateZone]);

  return (
    <div style={{ position: "relative" }}>
      <canvas
        ref={canvasRef}
        width={CANVAS_W}
        height={CANVAS_H}
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
        onMouseLeave={() => { dragRef.current = null; }}
        onDoubleClick={onDoubleClick}
        onContextMenu={onContextMenu}
        style={{
          width: "100%",
          height: "auto",
          borderRadius: 10,
          cursor: "crosshair",
          border: "1px solid rgba(234,179,8,0.25)",
          display: "block",
          userSelect: "none",
        }}
      />
      <div style={{ fontSize: 10, color: "#475569", marginTop: 8, lineHeight: 1.6 }}>
        <strong style={{ color: "#94a3b8" }}>Rect zones:</strong> drag corners/edges to resize · drag body to move ·{" "}
        <strong style={{ color: "#94a3b8" }}>Polygon zones:</strong> drag vertex dots to move · double-click vertex to delete · right-click edge to add vertex
      </div>
    </div>
  );
}

// ── Canvas helpers ───────────────────────────────────────────────────────────

function clampC(v: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, v));
}

function isPointInPolygon(px: number, py: number, pts: [number, number][]): boolean {
  let inside = false;
  let j = pts.length - 1;
  for (let i = 0; i < pts.length; i++) {
    const [xi, yi] = pts[i], [xj, yj] = pts[j];
    if ((yi > py) !== (yj > py) && px < ((xj - xi) * (py - yi)) / (yj - yi + 1e-9) + xi) {
      inside = !inside;
    }
    j = i;
  }
  return inside;
}

function distToSegment(px: number, py: number, ax: number, ay: number, bx: number, by: number): number {
  const dx = bx - ax, dy = by - ay;
  const lenSq = dx * dx + dy * dy;
  if (lenSq === 0) return Math.hypot(px - ax, py - ay);
  const t = Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / lenSq));
  return Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
}

function drawPreview(ctx: CanvasRenderingContext2D, zones: Zone[], updatedId: string, updated: Zone): void {
  ctx.clearRect(0, 0, CANVAS_W, CANVAS_H);
  ctx.fillStyle = "rgba(6,10,18,0.95)";
  ctx.fillRect(0, 0, CANVAS_W, CANVAS_H);
  ctx.strokeStyle = "rgba(255,255,255,0.05)";
  ctx.lineWidth = 1;
  for (let x = 0; x <= CANVAS_W; x += 40) {
    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, CANVAS_H); ctx.stroke();
  }
  for (let y = 0; y <= CANVAS_H; y += 40) {
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(CANVAS_W, y); ctx.stroke();
  }
  zones.forEach((zone, idx) => {
    const z = zone.id === updatedId ? updated : zone;
    const color = getZoneColor(idx);
    if (z.shape === "rect") {
      const x1 = toCanvas(z.x1), y1 = toCanvas(z.y1);
      const w = toCanvas(z.x2) - x1, h = toCanvas(z.y2) - y1;
      ctx.fillStyle = color + "22"; ctx.fillRect(x1, y1, w, h);
      ctx.strokeStyle = color; ctx.lineWidth = 1.5; ctx.setLineDash([]);
      ctx.strokeRect(x1, y1, w, h);
      const handles = getRectHandles(z);
      (Object.entries(handles) as [RectHandle, [number, number]][]).forEach(([key, [hx, hy]]) => {
        if (key === "body") return;
        ctx.fillStyle = "#ffffff"; ctx.strokeStyle = color; ctx.lineWidth = 1.5;
        ctx.beginPath(); ctx.arc(hx, hy, 5, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
      });
      ctx.fillStyle = color; ctx.font = "bold 11px monospace";
      ctx.fillText(z.name, x1 + 6, y1 + 14);
    } else {
      const pts = z.points.map(([px, py]) => [toCanvas(px), toCanvas(py)] as [number, number]);
      if (pts.length < 2) return;
      ctx.beginPath(); ctx.moveTo(pts[0][0], pts[0][1]);
      for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]);
      ctx.closePath();
      ctx.fillStyle = color + "22"; ctx.fill();
      ctx.strokeStyle = color; ctx.lineWidth = 1.5; ctx.setLineDash([]); ctx.stroke();
      pts.forEach(([vx, vy]) => {
        ctx.fillStyle = "#ffffff"; ctx.strokeStyle = color; ctx.lineWidth = 1.5;
        ctx.beginPath(); ctx.arc(vx, vy, 5, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
      });
      const cx = pts.reduce((s, [x]) => s + x, 0) / pts.length;
      const cy = pts.reduce((s, [, y]) => s + y, 0) / pts.length;
      ctx.fillStyle = color; ctx.font = "bold 11px monospace";
      ctx.fillText(z.name, cx - 20, cy + 4);
    }
  });
}

export default function Settings() {
  const isMobile = useIsMobile();
  const [config, setConfig] = useState<Config>(DEFAULT_CONFIG);
  const [zones, setZones] = useState<Zone[]>([]);
  const [zoneError, setZoneError] = useState<string | null>(null);
  const [zoneSaving, setZoneSaving] = useState(false);

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

  // ── Restricted-zone CRUD ─────────────────────────────────────────────────
  const reloadZones = async () => {
    try {
      const res = await fetch("/api/zones");
      const data = await res.json();
      const list = Array.isArray(data.zones) ? data.zones : [];
      // Coerce legacy zones (no shape field) into rect.
      setZones(list.map((z: Record<string, unknown>): Zone => {
        if (z.shape === "polygon") {
          const pts = Array.isArray(z.points)
            ? (z.points as unknown[]).map((p): [number, number] => {
                if (Array.isArray(p) && p.length >= 2) {
                  return [Number(p[0]) || 0, Number(p[1]) || 0];
                }
                return [0, 0];
              })
            : [];
          return {
            id: String(z.id ?? ""),
            name: String(z.name ?? z.id ?? "Zone"),
            shape: "polygon",
            points: pts,
          };
        }
        return {
          id: String(z.id ?? ""),
          name: String(z.name ?? z.id ?? "Zone"),
          shape: "rect",
          x1: Number(z.x1 ?? 0),
          y1: Number(z.y1 ?? 0),
          x2: Number(z.x2 ?? 0),
          y2: Number(z.y2 ?? 0),
        };
      }));
    } catch {
      // Keep previous list on transient failures.
    }
  };

  useEffect(() => {
    reloadZones();
  }, []);

  const addRectZone = async () => {
    setZoneError(null);
    setZoneSaving(true);
    try {
      const res = await fetch("/api/zones", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: `Zone ${zones.length + 1}`,
          shape: "rect",
          x1: 100, y1: 100, x2: 400, y2: 400,
        }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail ?? "Could not create zone");
      }
      await reloadZones();
    } catch (e) {
      setZoneError(e instanceof Error ? e.message : "Failed to add zone");
    } finally {
      setZoneSaving(false);
    }
  };

  const addPolygonZone = async () => {
    setZoneError(null);
    setZoneSaving(true);
    try {
      // Default hexagon centred at 640,360 in canonical coords
      const cx = 640, cy = 360, r = 150;
      const pts: [number, number][] = Array.from({ length: 6 }, (_, i) => {
        const angle = (Math.PI / 3) * i - Math.PI / 2;
        return [Math.round(cx + r * Math.cos(angle)), Math.round(cy + r * Math.sin(angle))];
      });
      const res = await fetch("/api/zones", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: `Polygon ${zones.length + 1}`,
          shape: "polygon",
          points: pts,
        }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail ?? "Could not create polygon zone");
      }
      await reloadZones();
    } catch (e) {
      setZoneError(e instanceof Error ? e.message : "Failed to add polygon zone");
    } finally {
      setZoneSaving(false);
    }
  };

  const updateZone = async (zone: Zone) => {
    setZoneError(null);
    try {
      const body: Record<string, unknown> = {
        name: zone.name,
        shape: zone.shape,
      };
      if (zone.shape === "rect") {
        body.x1 = zone.x1;
        body.y1 = zone.y1;
        body.x2 = zone.x2;
        body.y2 = zone.y2;
      } else {
        body.points = zone.points;
      }
      const res = await fetch(`/api/zones/${encodeURIComponent(zone.id)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail ?? "Could not save zone");
      }
      await reloadZones();
    } catch (e) {
      setZoneError(e instanceof Error ? e.message : "Failed to save zone");
    }
  };

  const deleteZone = async (zoneId: string) => {
    setZoneError(null);
    try {
      const res = await fetch(`/api/zones/${encodeURIComponent(zoneId)}`, {
        method: "DELETE",
      });
      if (!res.ok) throw new Error("Could not delete zone");
      await reloadZones();
    } catch (e) {
      setZoneError(e instanceof Error ? e.message : "Failed to delete zone");
    }
  };
  // ─────────────────────────────────────────────────────────────────────────

  // Pause /api/config polling for a window after the user touches any
  // control on this page. Without this, a 2-second poll fires mid-drag
  // on a slider and snaps the value back to the server's last-saved
  // state, making sliders feel "haunted" while editing.
  const lastUserEditRef = useRef<number>(0);
  const POLL_LOCKOUT_MS = 8000;
  const markUserEdit = () => { lastUserEditRef.current = Date.now(); };

  useEffect(() => {
    const poll = async () => {
      if (document.visibilityState !== "visible") return;
      // Skip the overwrite if the user is actively editing.
      if (Date.now() - lastUserEditRef.current < POLL_LOCKOUT_MS) return;
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
            description="Average pixel-per-second speed above this is flagged as running."
            icon={Zap}
            color="#a855f7"
            value={config.running_speed_threshold}
            min={50}
            max={800}
            step={10}
            onChange={(v) => setConfig((c) => ({ ...c, running_speed_threshold: v }))}
            unit=" px/s"
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

          <PremiumSlider
            label="Running — Body Heights / Sec"
            description="Distance-invariant running threshold: average speed must exceed this many bbox heights per second. Works at any camera distance."
            icon={Zap}
            color="#a855f7"
            value={config.running_body_heights_per_sec}
            min={0.4}
            max={4.0}
            step={0.1}
            onChange={(v) => setConfig((c) => ({ ...c, running_body_heights_per_sec: Number(v.toFixed(1)) }))}
            unit=" b/s"
          />

          <PremiumSlider
            label="Running — Pixel Floor (anti-jitter)"
            description="Body-heights/sec path also requires raw speed above this floor. Rejects tiny bboxes producing huge body-heights from a few pixels of YOLO jitter."
            icon={Move}
            color="#a855f7"
            value={config.running_pixel_floor}
            min={0}
            max={300}
            step={5}
            onChange={(v) => setConfig((c) => ({ ...c, running_pixel_floor: v }))}
            unit=" px/s"
          />

          <ToggleCard
            label="Bystander Attends Object"
            description="When ON, any person near an unattended object counts as a guardian (not just the original owner). Reduces false positives in busy areas where the owner walks away but a different person is right next to the bag."
            enabled={config.unattended_bystander_attends}
            onToggle={(next) => setConfig((c) => ({ ...c, unattended_bystander_attends: next }))}
          />

          <PremiumSlider
            label="Unattended Ghost Cache TTL"
            description="When a baggage track briefly disappears (occlusion), its stationary state is cached for this many seconds. A re-detected bag in the same area resumes the unattended timer instead of restarting from zero."
            icon={Clock}
            color="#f97316"
            value={config.unattended_ghost_ttl}
            min={0}
            max={30}
            step={0.5}
            onChange={(v) => setConfig((c) => ({ ...c, unattended_ghost_ttl: Number(v.toFixed(1)) }))}
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
            CROWD CLUSTERING
          </div>

          <PremiumSlider
            label="Cluster Distance"
            description="Two persons belong to the same cluster if they are within this many pixels of any cluster member (single-link). Tight crowds at a doorway trigger even when total scene count is low."
            icon={Move}
            color="#f97316"
            value={config.overcrowding_cluster_distance_px}
            min={50}
            max={500}
            step={10}
            onChange={(v) => setConfig((c) => ({ ...c, overcrowding_cluster_distance_px: v }))}
            unit=" px"
          />

          <PremiumSlider
            label="Min Cluster Size"
            description="Minimum cluster size to emit an overcrowding alert. Independent of overcrowding_threshold so small clusters in large crowds don't spam alerts."
            icon={Users}
            color="#f97316"
            value={config.overcrowding_min_cluster_size}
            min={2}
            max={20}
            step={1}
            onChange={(v) => setConfig((c) => ({ ...c, overcrowding_min_cluster_size: v }))}
            unit=" ppl"
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
            FALL ASSOCIATION
          </div>

          <PremiumSlider
            label="Fall ↔ Person IoU Min"
            description="Minimum bbox IoU between a fall detection and a person track to associate them. Lower = more aggressive linking; higher = fewer false associations."
            icon={UserRoundX}
            color="#dc2626"
            value={config.fall_person_iou_min}
            min={0}
            max={0.95}
            step={0.05}
            onChange={(v) => setConfig((c) => ({ ...c, fall_person_iou_min: Number(v.toFixed(2)) }))}
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
            onToggle={(next) => { markUserEdit(); setConfig((c) => ({ ...c, restricted_zone_enabled: next })); }}
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
            onChange={(v) => { markUserEdit(); setConfig((c) => ({ ...c, restricted_zone_min_dwell: Number(v.toFixed(1)) })); }}
            unit=" s"
          />
        </div>
      </div>

      {/* ── Restricted Zone Editor ─────────────────────────────────────────── */}
      <div
        style={{
          background: "var(--app-card-bg)",
          border: "1px solid var(--app-card-border)",
          borderRadius: 14,
          padding: 24,
          marginBottom: 20,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 18 }}>
          <div style={{ fontSize: 9, color: "#475569", letterSpacing: 2, fontWeight: 700 }}>
            RESTRICTED ZONES — CANVAS EDITOR
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button
              onClick={addRectZone}
              disabled={zoneSaving}
              style={{
                padding: "7px 14px", borderRadius: 8,
                border: "1px solid rgba(234,179,8,0.4)",
                background: zoneSaving ? "rgba(234,179,8,0.05)" : "rgba(234,179,8,0.12)",
                color: "#eab308", fontSize: 12, fontWeight: 700,
                cursor: zoneSaving ? "default" : "pointer",
              }}
            >
              + Add Rect Zone
            </button>
            <button
              onClick={addPolygonZone}
              disabled={zoneSaving}
              style={{
                padding: "7px 14px", borderRadius: 8,
                border: "1px solid rgba(99,102,241,0.4)",
                background: zoneSaving ? "rgba(99,102,241,0.05)" : "rgba(99,102,241,0.12)",
                color: "#818cf8", fontSize: 12, fontWeight: 700,
                cursor: zoneSaving ? "default" : "pointer",
              }}
            >
              + Add Polygon Zone
            </button>
          </div>
        </div>

        {zoneError && (
          <div style={{ color: "#ef4444", fontSize: 12, marginBottom: 12 }}>{zoneError}</div>
        )}

        {/* Canvas editor — renders all zones and handles drag interactions */}
        <ZoneCanvas
          zones={zones}
          onUpdateZone={(updated) => {
            // Optimistically update local state for instant feedback, then persist
            setZones((zs) => zs.map((z) => (z.id === updated.id ? updated : z)));
            updateZone(updated);
          }}
        />

        {zones.length === 0 ? (
          <div style={{ fontSize: 12, color: "#64748b", padding: "16px 0" }}>
            No restricted zones configured. Click <strong>+ Add Rect Zone</strong> or <strong>+ Add Polygon Zone</strong> above.
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 12, marginTop: 16 }}>
            {zones.map((zone, idx) => (
              <div
                key={zone.id}
                style={{
                  border: `1px solid ${getZoneColor(idx)}40`,
                  borderLeft: `3px solid ${getZoneColor(idx)}`,
                  borderRadius: 10,
                  padding: "12px 14px",
                  background: `${getZoneColor(idx)}08`,
                }}
              >
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, marginBottom: 8 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <ShieldAlert size={14} color={getZoneColor(idx)} />
                    <input
                      type="text"
                      value={zone.name}
                      maxLength={64}
                      onChange={(e) =>
                        setZones((zs) => zs.map((z) => (z.id === zone.id ? { ...z, name: e.target.value } : z)))
                      }
                      onBlur={() => updateZone(zone)}
                      style={{
                        background: "rgba(255,255,255,0.04)",
                        border: "1px solid rgba(255,255,255,0.08)",
                        borderRadius: 6, padding: "4px 8px",
                        color: "var(--app-text)", fontSize: 12, minWidth: 160,
                        outline: "none",
                      }}
                    />
                    <span style={{ fontSize: 9, color: "#475569", fontFamily: "monospace" }}>id={zone.id}</span>
                    <span style={{
                      fontSize: 9, color: "#94a3b8", letterSpacing: 1,
                      background: "rgba(255,255,255,0.04)",
                      borderRadius: 6, padding: "1px 6px", fontWeight: 700,
                    }}>{zone.shape.toUpperCase()}</span>
                    {zone.shape === "polygon" && (
                      <span style={{ fontSize: 9, color: "#818cf8" }}>{zone.points.length} pts</span>
                    )}
                  </div>
                  <button
                    onClick={() => deleteZone(zone.id)}
                    style={{
                      padding: "4px 10px", borderRadius: 6,
                      border: "1px solid rgba(239,68,68,0.4)",
                      background: "rgba(239,68,68,0.1)",
                      color: "#ef4444", fontSize: 11, fontWeight: 700,
                      cursor: "pointer",
                    }}
                  >
                    Delete
                  </button>
                </div>
                {zone.shape === "rect" && (
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8 }}>
                    {(["x1", "y1", "x2", "y2"] as const).map((field) => (
                      <label key={field} style={{ fontSize: 10, color: "#94a3b8" }}>
                        <span style={{ display: "block", letterSpacing: 1, fontWeight: 700, marginBottom: 4 }}>
                          {field.toUpperCase()}
                        </span>
                        <input
                          type="number"
                          min={0}
                          max={field.startsWith("x") ? 1280 : 720}
                          step={1}
                          value={zone[field]}
                          onChange={(e) => {
                            const val = Number(e.target.value);
                            setZones((zs) =>
                              zs.map((z) =>
                                z.id === zone.id && z.shape === "rect"
                                  ? { ...z, [field]: val }
                                  : z,
                              ),
                            );
                          }}
                          onBlur={() => updateZone(zone)}
                          style={{
                            width: "100%", boxSizing: "border-box",
                            background: "rgba(255,255,255,0.04)",
                            border: "1px solid rgba(255,255,255,0.08)",
                            borderRadius: 6, padding: "5px 8px",
                            color: "var(--app-text)", fontSize: 12,
                            fontFamily: "monospace", outline: "none",
                          }}
                        />
                      </label>
                    ))}
                  </div>
                )}
                {zone.shape === "polygon" && (
                  <div style={{ fontSize: 11, color: "#64748b" }}>
                    Use the canvas above to drag vertices, double-click to delete a vertex, or right-click an edge to insert a vertex.
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
      {/* ───────────────────────────────────────────────────────────────────── */}

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
            description="Both persons must exceed this average speed (px/s) for suspicion."
            icon={Zap}
            color="#f43f5e"
            value={config.fight_min_pair_speed}
            min={50}
            max={800}
            step={10}
            onChange={(v) => setConfig((c) => ({ ...c, fight_min_pair_speed: v }))}
            unit=" px/s"
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
            LOITERING DETECTION
          </div>

          <ToggleCard
            label="Loitering Detection"
            description="Detect persons who remain within a small area for an extended time."
            enabled={config.loitering_enabled}
            onToggle={(next) => setConfig((c) => ({ ...c, loitering_enabled: next }))}
          />

          <PremiumSlider
            label="Loitering Time Threshold"
            description="Seconds a person must remain in the same area before triggering a loitering alert."
            icon={Clock}
            color="#6366f1"
            value={config.loitering_time_threshold}
            min={3}
            max={120}
            step={1}
            onChange={(v) => setConfig((c) => ({ ...c, loitering_time_threshold: v }))}
            unit=" s"
          />

          <PremiumSlider
            label="Loitering Radius"
            description="Maximum movement radius (in pixels) to still count as loitering."
            icon={Move}
            color="#6366f1"
            value={config.loitering_radius_px}
            min={30}
            max={400}
            step={10}
            onChange={(v) => setConfig((c) => ({ ...c, loitering_radius_px: v }))}
            unit=" px"
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
          onChange={(v) => { markUserEdit(); setConfig((c) => ({ ...c, alert_cooldown_secs: v })); }}
          unit=" s"
        />

        <PremiumSlider
          label="Alert Escalation Timeout"
          description="If an alert is not acknowledged within this many seconds it is flagged as ESCALATED and a follow-up email is sent. Set to 0 to disable escalation."
          icon={CheckCircle}
          color="#f59e0b"
          value={config.alert_escalation_secs}
          min={0}
          max={600}
          step={10}
          onChange={(v) => { markUserEdit(); setConfig((c) => ({ ...c, alert_escalation_secs: v })); }}
          unit=" s"
        />
      </div>

      {/* ── PPE / Face / License Plate Detection ───────────────────────────── */}
      <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr 1fr", gap: 20, marginBottom: 20 }}>
        <div
          style={{
            background: "var(--app-card-bg)",
            border: "1px solid var(--app-card-border)",
            borderRadius: 14,
            padding: 24,
          }}
        >
          <div style={{ fontSize: 9, color: "#475569", letterSpacing: 2, fontWeight: 700, marginBottom: 24 }}>
            PPE DETECTION
          </div>

          <ToggleCard
            label="PPE (Hard-Hat) Detection"
            description="Detect missing hard-hats using a lightweight YOLO model. Triggers 'PPE Violation' alerts."
            enabled={config.ppe_detection_enabled}
            onToggle={(next) => setConfig((c) => ({ ...c, ppe_detection_enabled: next }))}
          />

          <PremiumSlider
            label="PPE Confidence"
            description="Minimum model confidence to flag a PPE violation."
            icon={ShieldAlert}
            color="#f59e0b"
            value={config.ppe_confidence_threshold}
            min={0.1}
            max={0.95}
            step={0.05}
            onChange={(v) => setConfig((c) => ({ ...c, ppe_confidence_threshold: Number(v.toFixed(2)) }))}
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
            FACE DETECTION
          </div>

          <ToggleCard
            label="Face Detection (Haar Cascade)"
            description="Detect faces using OpenCV's built-in Haar cascade. No download required."
            enabled={config.face_detection_enabled}
            onToggle={(next) => setConfig((c) => ({ ...c, face_detection_enabled: next }))}
          />

          <PremiumSlider
            label="Scale Factor"
            description="Image scale reduction at each cascade pass. Lower = more faces found but slower."
            icon={Users}
            color="#06b6d4"
            value={config.face_scale_factor}
            min={1.05}
            max={2.0}
            step={0.05}
            onChange={(v) => setConfig((c) => ({ ...c, face_scale_factor: Number(v.toFixed(2)) }))}
          />

          <PremiumSlider
            label="Min Neighbors"
            description="Higher = fewer false positives. Lower = more detections."
            icon={Users}
            color="#06b6d4"
            value={config.face_min_neighbors}
            min={1}
            max={15}
            step={1}
            onChange={(v) => setConfig((c) => ({ ...c, face_min_neighbors: v }))}
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
            LICENSE PLATE DETECTION
          </div>

          <ToggleCard
            label="License Plate Detection"
            description="Detect vehicle license plates using a lightweight YOLO model. No OCR — bbox only."
            enabled={config.lpr_detection_enabled}
            onToggle={(next) => setConfig((c) => ({ ...c, lpr_detection_enabled: next }))}
          />

          <PremiumSlider
            label="LPR Confidence"
            description="Minimum model confidence to flag a plate detection."
            icon={ShieldAlert}
            color="#84cc16"
            value={config.lpr_confidence_threshold}
            min={0.1}
            max={0.95}
            step={0.05}
            onChange={(v) => setConfig((c) => ({ ...c, lpr_confidence_threshold: Number(v.toFixed(2)) }))}
          />
        </div>
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

