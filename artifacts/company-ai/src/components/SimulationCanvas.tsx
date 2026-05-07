import { useEffect, useRef, RefObject, memo } from "react";
import { Track, Anomaly } from "../hooks/useSimulation";

const W = 1280;
const H = 720;

export type OverlayStyle = "corners" | "dots" | "heatmap" | "chips" | "auto";

function getAnomalyIds(anomalies: Anomaly[]): Set<number> {
  const ids = new Set<number>();
  for (const a of anomalies) if (a.track_id !== undefined) ids.add(a.track_id);
  return ids;
}

function drawCornerMarker(
  ctx: CanvasRenderingContext2D,
  x1: number, y1: number, x2: number, y2: number,
  color: string, size = 14,
) {
  ctx.strokeStyle = color;
  ctx.lineWidth = 2.5;
  ctx.lineCap = "square";
  ctx.beginPath(); ctx.moveTo(x1, y1 + size); ctx.lineTo(x1, y1); ctx.lineTo(x1 + size, y1); ctx.stroke();
  ctx.beginPath(); ctx.moveTo(x2 - size, y1); ctx.lineTo(x2, y1); ctx.lineTo(x2, y1 + size); ctx.stroke();
  ctx.beginPath(); ctx.moveTo(x2, y2 - size); ctx.lineTo(x2, y2); ctx.lineTo(x2 - size, y2); ctx.stroke();
  ctx.beginPath(); ctx.moveTo(x1 + size, y2); ctx.lineTo(x1, y2); ctx.lineTo(x1, y2 - size); ctx.stroke();
}

function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y); ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  ctx.lineTo(x + w, y + h - r); ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  ctx.lineTo(x + r, y + h); ctx.quadraticCurveTo(x, y + h, x, y + h - r);
  ctx.lineTo(x, y + r); ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
}

function drawLabel(
  ctx: CanvasRenderingContext2D,
  text: string,
  lx: number, ly: number,
  color: string,
  placedLabels: { lx: number; ly: number; lw: number; lh: number }[],
  clampRight = W,
) {
  ctx.font = "600 10px monospace";
  const tw = ctx.measureText(text).width;
  const lh = 16;
  const lw = tw + 10;
  const cx = Math.min(lx, clampRight - lw - 4);
  const pad = 2;
  for (const p of placedLabels) {
    if (cx < p.lx + p.lw + pad && cx + lw + pad > p.lx && ly < p.ly + p.lh + pad && ly + lh + pad > p.ly) return;
  }
  placedLabels.push({ lx: cx - 4, ly: ly - 1, lw, lh });
  roundRect(ctx, cx - 4, ly - 1, lw, lh, 4);
  ctx.fillStyle = color + "cc";
  ctx.fill();
  ctx.fillStyle = "#fff";
  ctx.fillText(text, cx, ly + 11);
}

function resolveStyle(style: OverlayStyle, tracks: Track[]): Exclude<OverlayStyle, "auto"> {
  if (style !== "auto") return style;
  const personCount = tracks.filter(t => t.class_id === 0).length;
  if (personCount < 8) return "corners";
  if (personCount < 20) return "chips";
  return "dots";
}

function drawCornersStyle(
  ctx: CanvasRenderingContext2D,
  tracks: Track[],
  anomalyIds: Set<number>,
  t: number,
) {
  const placedLabels: { lx: number; ly: number; lw: number; lh: number }[] = [];
  const sorted = [...tracks].sort((a, b) => {
    const as = (anomalyIds.has(a.id) || a.running) ? 1 : 0;
    const bs = (anomalyIds.has(b.id) || b.running) ? 1 : 0;
    return bs - as;
  });

  for (const track of sorted) {
    const { x1, y1, x2, y2, class_id, class_name, running, id, confidence } = track;
    const isAnomaly = anomalyIds.has(id);
    const isPerson = class_id === 0;
    const boxW = x2 - x1;
    const boxH = y2 - y1;

    let color: string;
    if (running) color = "#ef4444";
    else if (isAnomaly) color = "#f97316";
    else if (isPerson) color = "#3b82f6";
    else color = "#f59e0b";

    if (isAnomaly || running) { ctx.shadowBlur = 18; ctx.shadowColor = color; }
    drawCornerMarker(ctx, x1, y1, x2, y2, color);
    ctx.shadowBlur = 0;

    const tooSmall = boxW < 38 && boxH < 38;
    if (!tooSmall) {
      const confStr = confidence !== undefined ? ` ${(confidence * 100).toFixed(0)}%` : "";
      const labelText = `#${id} ${class_name}${confStr}${running ? " ⚡" : ""}`;
      const ly = y1 > 22 ? y1 - 20 : y2 + 4;
      drawLabel(ctx, labelText, x1, ly, color, placedLabels);
    }

    if (running) {
      const cx = (x1 + x2) / 2;
      const cy = (y1 + y2) / 2;
      ctx.fillStyle = color + "40";
      ctx.globalAlpha = 0.5 + 0.5 * Math.abs(Math.sin(t / 200));
      ctx.beginPath(); ctx.arc(cx, cy, 22, 0, 2 * Math.PI); ctx.fill();
      ctx.globalAlpha = 1;
    }
  }
}

function drawDotsStyle(
  ctx: CanvasRenderingContext2D,
  tracks: Track[],
  anomalyIds: Set<number>,
  t: number,
) {
  for (const track of tracks) {
    const { x1, x2, y2, class_id, id, running } = track;
    const isAnomaly = anomalyIds.has(id);
    const isPerson = class_id === 0;

    let color: string;
    if (running) color = "#ef4444";
    else if (isAnomaly) color = "#f97316";
    else if (isPerson) color = "#3b82f6";
    else color = "#f59e0b";

    const cx = (x1 + x2) / 2;
    const footY = y2;
    const radius = isAnomaly || running ? 7 : 5;
    const pulse = isAnomaly || running ? 0.6 + 0.4 * Math.abs(Math.sin(t / 250)) : 1;

    ctx.shadowBlur = isAnomaly || running ? 16 : 8;
    ctx.shadowColor = color;

    ctx.globalAlpha = pulse;
    ctx.beginPath();
    ctx.arc(cx, footY, radius, 0, 2 * Math.PI);
    ctx.fillStyle = color;
    ctx.fill();

    ctx.beginPath();
    ctx.arc(cx, footY, radius + 4, 0, 2 * Math.PI);
    ctx.fillStyle = color + "33";
    ctx.fill();

    ctx.globalAlpha = 1;
    ctx.shadowBlur = 0;

    ctx.font = "600 9px monospace";
    const label = `#${id}`;
    const lw = ctx.measureText(label).width;
    ctx.fillStyle = color + "cc";
    roundRect(ctx, cx - lw / 2 - 4, footY - radius - 17, lw + 8, 13, 3);
    ctx.fill();
    ctx.fillStyle = "#fff";
    ctx.fillText(label, cx - lw / 2, footY - radius - 7);
  }
}

function drawHeatmapStyle(
  ctx: CanvasRenderingContext2D,
  tracks: Track[],
) {
  if (tracks.length === 0) return;

  const prev = ctx.globalCompositeOperation;
  ctx.globalCompositeOperation = "screen";

  const personTracks = tracks.filter(t => t.class_id === 0);
  const radius = 120;

  for (const track of personTracks) {
    const cx = (track.x1 + track.x2) / 2;
    const cy = (track.y1 + track.y2) / 2;
    const bh = track.y2 - track.y1;
    const r = Math.max(40, Math.min(radius, bh * 1.4));

    const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, r);
    grad.addColorStop(0, "rgba(0,180,255,0.22)");
    grad.addColorStop(0.35, "rgba(0,255,120,0.12)");
    grad.addColorStop(0.65, "rgba(255,120,0,0.07)");
    grad.addColorStop(1, "rgba(0,0,0,0)");

    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, 2 * Math.PI);
    ctx.fillStyle = grad;
    ctx.fill();
  }

  ctx.globalCompositeOperation = prev;

  for (const track of personTracks) {
    const cx = (track.x1 + track.x2) / 2;
    const cy = (track.y1 + track.y2) / 2;
    ctx.beginPath();
    ctx.arc(cx, cy, 3, 0, 2 * Math.PI);
    ctx.fillStyle = "rgba(255,255,255,0.7)";
    ctx.fill();
  }
}

function drawChipsStyle(
  ctx: CanvasRenderingContext2D,
  tracks: Track[],
  anomalyIds: Set<number>,
) {
  const placedLabels: { lx: number; ly: number; lw: number; lh: number }[] = [];

  const sorted = [...tracks].sort((a, b) => {
    const as = (anomalyIds.has(a.id) || a.running) ? 1 : 0;
    const bs = (anomalyIds.has(b.id) || b.running) ? 1 : 0;
    return bs - as;
  });

  for (const track of sorted) {
    const { x1, y1, x2, y2, class_id, class_name, running, id, confidence } = track;
    const isAnomaly = anomalyIds.has(id);
    const isPerson = class_id === 0;

    let color: string;
    if (running) color = "#ef4444";
    else if (isAnomaly) color = "#f97316";
    else if (isPerson) color = "#3b82f6";
    else color = "#f59e0b";

    const confStr = confidence !== undefined ? ` ${(confidence * 100).toFixed(0)}%` : "";
    const labelText = `#${id} ${class_name}${confStr}${running ? " ⚡" : ""}`;
    const ly = y1 > 22 ? y1 - 20 : y2 + 4;

    if (isAnomaly || running) {
      ctx.shadowBlur = 12;
      ctx.shadowColor = color;
    }
    drawLabel(ctx, labelText, x1, ly, color, placedLabels);
    ctx.shadowBlur = 0;

    const cx = (x1 + x2) / 2;
    const cy = (y1 + y2) / 2;
    ctx.beginPath();
    ctx.arc(cx, cy, 2.5, 0, 2 * Math.PI);
    ctx.fillStyle = color + "99";
    ctx.fill();
  }
}

type SourceMode = "idle" | "video" | "webcam" | "stream";

interface RestrictedZone {
  id: string;
  name?: string;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

interface SmoothedBox {
  x1: number; y1: number; x2: number; y2: number;
}

interface Props {
  tracks: Track[];
  anomalies: Anomaly[];
  cameraMode: "webcam" | "idle";
  videoRef: RefObject<HTMLVideoElement | null>;
  sourceMode?: SourceMode;
  frameJpeg?: string;
  restrictedZones?: RestrictedZone[];
  smoothFactor?: number;
  overlayStyle?: OverlayStyle;
}

function SimulationCanvas({
  tracks, anomalies, cameraMode, videoRef, sourceMode = "idle", frameJpeg,
  restrictedZones = [], smoothFactor = 0.3, overlayStyle = "corners",
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rafRef = useRef<number>(0);

  const backendImgRef = useRef<HTMLImageElement | null>(null);
  const lastJpegRef = useRef<string | undefined>(undefined);

  const smoothedMapRef = useRef<Map<number, SmoothedBox>>(new Map());
  const smoothRef = useRef(smoothFactor);
  const overlayRef = useRef(overlayStyle);

  useEffect(() => { smoothRef.current = smoothFactor; }, [smoothFactor]);
  useEffect(() => { overlayRef.current = overlayStyle; }, [overlayStyle]);

  useEffect(() => {
    if (!frameJpeg || frameJpeg === lastJpegRef.current) return;
    lastJpegRef.current = frameJpeg;
    if (!backendImgRef.current) {
      backendImgRef.current = new Image();
    }
    backendImgRef.current.src = `data:image/jpeg;base64,${frameJpeg}`;
  }, [frameJpeg]);

  const dataRef = useRef({ tracks, anomalies, cameraMode, sourceMode, restrictedZones });
  useEffect(() => {
    dataRef.current = { tracks, anomalies, cameraMode, sourceMode, restrictedZones };
  }, [tracks, anomalies, cameraMode, sourceMode, restrictedZones]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let lastIdleFrameTs = 0;
    const IDLE_FRAME_INTERVAL = 100;

    function draw() {
      if (!ctx || !canvas) return;
      const { tracks, anomalies, cameraMode, sourceMode, restrictedZones } = dataRef.current;
      // Invert smoothFactor so the slider is semantically correct:
      // 0 = no smoothing (snappy), 1 = maximum smoothing (laggy/smooth).
      // Clamp minimum alpha to 0.05 so even at full smoothing the box still tracks.
      const rawSmooth = smoothRef.current;
      const alpha = rawSmooth <= 0.01 ? 1.0 : Math.max(0.05, 1 - rawSmooth);
      const style = overlayRef.current;
      const smap = smoothedMapRef.current;
      const t = Date.now();

      if (sourceMode === "idle") {
        if (t - lastIdleFrameTs < IDLE_FRAME_INTERVAL) {
          rafRef.current = requestAnimationFrame(draw);
          return;
        }
        lastIdleFrameTs = t;
      }

      const anomalyIds = getAnomalyIds(anomalies);

      ctx.clearRect(0, 0, W, H);

      const vid = videoRef.current;
      const hasLiveWebcam = cameraMode === "webcam" && vid && vid.readyState >= 2;
      const hasBackendFrame = backendImgRef.current?.complete && backendImgRef.current.naturalWidth > 0;
      const isActiveMode = sourceMode === "video" || sourceMode === "stream" || sourceMode === "webcam";

      if (hasLiveWebcam) {
        ctx.drawImage(vid, 0, 0, W, H);
        ctx.fillStyle = "rgba(0,0,0,0.15)";
        ctx.fillRect(0, 0, W, H);
      } else if (isActiveMode && hasBackendFrame && backendImgRef.current) {
        ctx.drawImage(backendImgRef.current, 0, 0, W, H);
        ctx.fillStyle = "rgba(0,0,0,0.18)";
        ctx.fillRect(0, 0, W, H);
      } else if (isActiveMode) {
        const bg = ctx.createRadialGradient(W / 2, H / 2, 0, W / 2, H / 2, 700);
        bg.addColorStop(0, "#0a0f1f");
        bg.addColorStop(1, "#05080f");
        ctx.fillStyle = bg;
        ctx.fillRect(0, 0, W, H);
        ctx.strokeStyle = "rgba(168,85,247,0.06)";
        ctx.lineWidth = 1;
        for (let x = 80; x < W; x += 80) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke(); }
        for (let y = 80; y < H; y += 80) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke(); }
        ctx.font = "600 12px monospace";
        ctx.fillStyle = "#64748b";
        const wt = "Loading detection engine…";
        ctx.fillText(wt, W / 2 - ctx.measureText(wt).width / 2, H / 2);
      } else {
        const bg = ctx.createRadialGradient(W / 2, H / 2, 0, W / 2, H / 2, 700);
        bg.addColorStop(0, "#080e1c");
        bg.addColorStop(1, "#040810");
        ctx.fillStyle = bg;
        ctx.fillRect(0, 0, W, H);
        ctx.strokeStyle = "rgba(59,130,246,0.04)";
        ctx.lineWidth = 1;
        for (let x = 80; x < W; x += 80) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke(); }
        for (let y = 80; y < H; y += 80) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke(); }

        const pulse = 0.55 + 0.45 * Math.sin(t / 1200);
        ctx.globalAlpha = pulse;
        ctx.font = "700 13px monospace";
        ctx.fillStyle = "#1e3a5f";
        const msg = "SELECT A SOURCE — WEBCAM · UPLOAD · STREAM";
        ctx.fillText(msg, W / 2 - ctx.measureText(msg).width / 2, H / 2);
        ctx.font = "500 11px monospace";
        ctx.fillStyle = "#0f1f3d";
        const sub = "YOLO11m + SORT  ·  Real-time anomaly detection engine";
        ctx.fillText(sub, W / 2 - ctx.measureText(sub).width / 2, H / 2 + 22);
        ctx.globalAlpha = 1;
      }
      ctx.setLineDash([]);

      if (sourceMode !== "idle" && restrictedZones.length > 0) {
        const activeRestrictedIds = new Set(
          anomalies
            .filter((a) => a.type === "restricted_zone" && a.zone_id)
            .map((a) => a.zone_id as string)
        );

        for (const zone of restrictedZones) {
          const isActive = activeRestrictedIds.has(zone.id);
          ctx.setLineDash([6, 5]);
          ctx.lineWidth = isActive ? 2.5 : 1.6;
          ctx.strokeStyle = isActive ? "rgba(234,179,8,0.95)" : "rgba(234,179,8,0.45)";
          ctx.strokeRect(zone.x1, zone.y1, zone.x2 - zone.x1, zone.y2 - zone.y1);
          ctx.setLineDash([]);

          ctx.fillStyle = isActive ? "rgba(234,179,8,0.16)" : "rgba(234,179,8,0.08)";
          ctx.fillRect(zone.x1, zone.y1, zone.x2 - zone.x1, zone.y2 - zone.y1);

          const zoneLabel = zone.name ? `${zone.name} (${zone.id})` : zone.id;
          ctx.font = "700 10px monospace";
          const lw = ctx.measureText(zoneLabel).width;
          roundRect(ctx, zone.x1 + 6, Math.max(6, zone.y1 - 18), lw + 12, 14, 4);
          ctx.fillStyle = isActive ? "rgba(234,179,8,0.85)" : "rgba(234,179,8,0.6)";
          ctx.fill();
          ctx.fillStyle = "#05080f";
          ctx.fillText(zoneLabel, zone.x1 + 12, Math.max(16, zone.y1 - 8));
        }
      }

      const activeIds = new Set(tracks.map(tk => tk.id));
      for (const id of smap.keys()) {
        if (!activeIds.has(id)) smap.delete(id);
      }

      const smoothedTracks = tracks.map(tk => {
        const prev = smap.get(tk.id);
        if (!prev || alpha >= 0.99) {
          const box = { x1: tk.x1, y1: tk.y1, x2: tk.x2, y2: tk.y2 };
          smap.set(tk.id, box);
          return tk;
        }
        const sx1 = prev.x1 + (tk.x1 - prev.x1) * alpha;
        const sy1 = prev.y1 + (tk.y1 - prev.y1) * alpha;
        const sx2 = prev.x2 + (tk.x2 - prev.x2) * alpha;
        const sy2 = prev.y2 + (tk.y2 - prev.y2) * alpha;
        const box = { x1: sx1, y1: sy1, x2: sx2, y2: sy2 };
        smap.set(tk.id, box);
        return { ...tk, x1: sx1, y1: sy1, x2: sx2, y2: sy2 };
      });

      const resolved = resolveStyle(style, smoothedTracks);

      if (resolved === "heatmap") {
        drawHeatmapStyle(ctx, smoothedTracks);
      } else if (resolved === "dots") {
        drawDotsStyle(ctx, smoothedTracks, anomalyIds, t);
      } else if (resolved === "chips") {
        drawChipsStyle(ctx, smoothedTracks, anomalyIds);
      } else {
        drawCornersStyle(ctx, smoothedTracks, anomalyIds, t);
      }

      for (const anomaly of anomalies) {
        if (!anomaly.position) continue;
        const [ax, ay] = anomaly.position;
        const pulse = 0.5 + 0.5 * Math.sin(t / 350);

        if (anomaly.type === "overcrowding") {
          ctx.strokeStyle = `rgba(239,68,68,${0.3 + 0.3 * pulse})`;
          ctx.lineWidth = 2;
          ctx.setLineDash([8, 6]);
          ctx.beginPath(); ctx.arc(ax, ay, 80, 0, 2 * Math.PI); ctx.stroke();
          ctx.setLineDash([]);
          ctx.fillStyle = `rgba(239,68,68,${0.08 + 0.06 * pulse})`;
          ctx.beginPath(); ctx.arc(ax, ay, 80, 0, 2 * Math.PI); ctx.fill();
          ctx.font = "700 10px monospace";
          ctx.fillStyle = "#ef4444";
          const txt = `⚠ OVERCROWDING${anomaly.count ? ` · ${anomaly.count} PPL` : ""}`;
          ctx.fillText(txt, ax - ctx.measureText(txt).width / 2, ay - 90);
        } else if (anomaly.type === "unattended_object") {
          ctx.strokeStyle = `rgba(249,115,22,${0.4 + 0.3 * pulse})`;
          ctx.lineWidth = 2.5;
          ctx.setLineDash([5, 5]);
          ctx.strokeRect(ax - 30, ay - 30, 60, 60);
          ctx.setLineDash([]);
          ctx.font = "700 10px monospace";
          ctx.fillStyle = "#f97316";
          const txt = "⚠ UNATTENDED OBJECT";
          ctx.fillText(txt, ax - ctx.measureText(txt).width / 2, ay - 38);
        } else if (anomaly.type === "running") {
          ctx.strokeStyle = `rgba(239,68,68,${0.4 + 0.3 * pulse})`;
          ctx.lineWidth = 2;
          ctx.setLineDash([4, 4]);
          ctx.beginPath(); ctx.arc(ax, ay, 50, 0, 2 * Math.PI); ctx.stroke();
          ctx.setLineDash([]);
        } else if (anomaly.type === "fight_suspected") {
          ctx.strokeStyle = `rgba(244,63,94,${0.45 + 0.3 * pulse})`;
          ctx.lineWidth = 3;
          ctx.setLineDash([10, 4]);
          ctx.beginPath(); ctx.arc(ax, ay, 56, 0, 2 * Math.PI); ctx.stroke();
          ctx.setLineDash([]);
          ctx.font = "700 10px monospace";
          ctx.fillStyle = "#f43f5e";
          const txt = "⚠ FIGHT SUSPECTED";
          ctx.fillText(txt, ax - ctx.measureText(txt).width / 2, ay - 64);
        } else if (anomaly.type === "fall_detected") {
          const bbox = anomaly.bbox;
          if (bbox && bbox.length === 4) {
            const [bx1, by1, bx2, by2] = bbox;
            ctx.strokeStyle = `rgba(220,38,38,${0.5 + 0.3 * pulse})`;
            ctx.lineWidth = 2.5;
            ctx.setLineDash([8, 4]);
            ctx.strokeRect(bx1, by1, Math.max(1, bx2 - bx1), Math.max(1, by2 - by1));
            ctx.setLineDash([]);
          }
          ctx.strokeStyle = `rgba(220,38,38,${0.45 + 0.3 * pulse})`;
          ctx.lineWidth = 2.5;
          ctx.setLineDash([8, 4]);
          ctx.beginPath(); ctx.arc(ax, ay, 42, 0, 2 * Math.PI); ctx.stroke();
          ctx.setLineDash([]);
          ctx.font = "700 10px monospace";
          ctx.fillStyle = "#dc2626";
          const txt = "⚠ FALL DETECTED";
          ctx.fillText(txt, ax - ctx.measureText(txt).width / 2, ay - 50);
        } else if (anomaly.type === "restricted_zone") {
          ctx.strokeStyle = `rgba(234,179,8,${0.45 + 0.3 * pulse})`;
          ctx.lineWidth = 2.5;
          ctx.setLineDash([6, 4]);
          ctx.beginPath(); ctx.arc(ax, ay, 38, 0, 2 * Math.PI); ctx.stroke();
          ctx.setLineDash([]);
          ctx.font = "700 10px monospace";
          ctx.fillStyle = "#eab308";
          const zoneText = anomaly.zone_name ?? anomaly.zone_id ?? "ZONE";
          const txt = `⚠ RESTRICTED ${zoneText}`;
          ctx.fillText(txt, ax - ctx.measureText(txt).width / 2, ay - 46);
        }
      }

      const modeLabel = (() => {
        if (sourceMode === "video")  return "YOLO · VIDEO";
        if (sourceMode === "webcam") return "YOLO · WEBCAM";
        if (sourceMode === "stream") return "YOLO · STREAM";
        return "STANDBY";
      })();

      const modeColor = (() => {
        if (sourceMode === "video")  return "#a855f7";
        if (sourceMode === "webcam") return "#10b981";
        if (sourceMode === "stream") return "#f59e0b";
        return "#1e3a5f";
      })();

      ctx.fillStyle = "rgba(0,0,0,0.65)";
      roundRect(ctx, 12, H - 36, 230, 26, 6);
      ctx.fill();
      ctx.fillStyle = modeColor;
      ctx.font = "11px monospace";
      ctx.fillText(`${new Date().toLocaleTimeString()}  ·  ${modeLabel}`, 20, H - 17);

      const isReal = sourceMode !== "idle";
      const badgeText = isReal ? "⚡ LIVE DETECT" : "◉ STANDBY";
      const badgeW = 126;
      ctx.fillStyle = "rgba(0,0,0,0.65)";
      roundRect(ctx, W - badgeW - 12, H - 36, badgeW, 26, 6);
      ctx.fill();
      ctx.fillStyle = modeColor;
      ctx.font = "700 10px monospace";
      ctx.fillText(badgeText, W - badgeW, H - 17);

      rafRef.current = requestAnimationFrame(draw);
    }

    rafRef.current = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(rafRef.current);
  }, [videoRef]);

  return (
    <canvas
      ref={canvasRef}
      width={W}
      height={H}
      style={{ width: "100%", height: "auto", display: "block" }}
    />
  );
}

export default memo(SimulationCanvas, (prev, next) => {
  if (prev.frameJpeg !== next.frameJpeg) return false;
  if (prev.sourceMode !== next.sourceMode) return false;
  if (prev.cameraMode !== next.cameraMode) return false;
  if (prev.videoRef !== next.videoRef) return false;
  if (prev.smoothFactor !== next.smoothFactor) return false;
  if (prev.overlayStyle !== next.overlayStyle) return false;
  if ((prev.restrictedZones?.length ?? 0) !== (next.restrictedZones?.length ?? 0)) return false;
  if ((prev.restrictedZones?.length ?? 0) > 0) {
    for (let i = 0; i < (prev.restrictedZones?.length ?? 0); i++) {
      const pz = prev.restrictedZones?.[i];
      const nz = next.restrictedZones?.[i];
      if (!pz || !nz) return false;
      if (pz.id !== nz.id || pz.x1 !== nz.x1 || pz.y1 !== nz.y1 || pz.x2 !== nz.x2 || pz.y2 !== nz.y2) return false;
    }
  }
  if (prev.tracks.length !== next.tracks.length) return false;
  if (prev.anomalies.length !== next.anomalies.length) return false;
  for (let i = 0; i < prev.tracks.length; i++) {
    const p = prev.tracks[i], n = next.tracks[i];
    if (p.id !== n.id || p.x1 !== n.x1 || p.y1 !== n.y1 || p.x2 !== n.x2 || p.y2 !== n.y2
      || p.running !== n.running || p.confidence !== n.confidence || p.class_name !== n.class_name) return false;
  }
  for (let i = 0; i < prev.anomalies.length; i++) {
    const p = prev.anomalies[i], n = next.anomalies[i];
    if (p.type !== n.type || p.track_id !== n.track_id) return false;
    const pp = p.position, np = n.position;
    if ((pp == null) !== (np == null)) return false;
    if (pp && np && (pp[0] !== np[0] || pp[1] !== np[1])) return false;
  }
  return true;
});
