import { useRef, useState, useCallback, useEffect } from "react";
import { useDetection } from "../context/DetectionContext";
import { useAlertSound } from "../hooks/useAlertSound";
import { useCamProcessor } from "../hooks/useCamProcessor";
import { useLocalCamRelay } from "../hooks/useLocalCamRelay";
import { useIsMobile } from "../hooks/use-mobile";
import SimulationCanvas, { OverlayStyle } from "../components/SimulationCanvas";
import AlertsFeed from "../components/AlertsFeed";
import { useStickyAnomalies } from "../hooks/useStickyAnomalies";
import {
  Camera, Monitor, Cpu, Users, Package,
  AlertTriangle, Activity, Upload, Video, StopCircle,
  CheckCircle, Loader, Volume2, VolumeX, Radio, Link, X, Bell, BellOff,
} from "lucide-react";
import { useNotifications } from "../hooks/useNotifications";

interface VideoStatusData {
  mode: string;
  filename: string | null;
  progress: number;
  total_frames: number;
  current_frame: number;
  model_ready: boolean;
  model_error: string | null;
  fall_model_ready?: boolean;
  fall_model_error?: string | null;
  error: string | null;
}

interface StreamStatusData {
  active: boolean;
  url: string | null;
  error: string | null;
  model_ready: boolean;
  model_error: string | null;
  fall_model_ready?: boolean;
  fall_model_error?: string | null;
}

interface WebcamStatusData {
  active: boolean;
  error: string | null;
  model_ready: boolean;
  model_error: string | null;
  fall_model_ready?: boolean;
  fall_model_error?: string | null;
}

interface RestrictedZone {
  id: string;
  name?: string;
  shape?: "rect" | "polygon";
  x1?: number;
  y1?: number;
  x2?: number;
  y2?: number;
  points?: [number, number][];
}

const PILL_STYLE = {
  background: "var(--app-card-bg)",
  border: "1px solid var(--app-card-border)",
  borderRadius: 14,
  padding: "10px 18px",
  display: "flex",
  alignItems: "center",
  gap: 10,
  flex: 1,
};

type ActivePanel = "none" | "video" | "stream" | "webcam";
type SourceMode = "idle" | "webcam" | "video" | "stream";
type CameraProfile = { id: string; name: string; url: string };
const MAX_CAMERAS = 10;
const CAMERA_PROFILE_KEY = "crowdlens_camera_profiles";

const DASHBOARD_CRITICAL_TYPES = new Set(["fight_suspected", "fall_detected", "unattended_object", "restricted_zone", "running"]);

export default function Dashboard() {
  const { frame, connected } = useDetection();
  const isMobile = useIsMobile();

  const [sourceMode, setSourceMode] = useState<SourceMode>("idle");
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [soundEnabled, setSoundEnabled] = useState(true);
  const [activePanel, setActivePanel] = useState<ActivePanel>("none");

  const [videoStatus, setVideoStatus] = useState<VideoStatusData | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);

  const [streamStatus, setStreamStatus] = useState<StreamStatusData | null>(null);
  const [streamUrl, setStreamUrl] = useState("");
  const [streamError, setStreamError] = useState<string | null>(null);
  const [cameraProfiles, setCameraProfiles] = useState<CameraProfile[]>(() => {
    try {
      const raw = localStorage.getItem(CAMERA_PROFILE_KEY);
      if (!raw) return [];
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed.slice(0, MAX_CAMERAS) : [];
    } catch {
      return [];
    }
  });
  const [cameraNameDraft, setCameraNameDraft] = useState("");
  const [captureInfo, setCaptureInfo] = useState<string | null>(null);
  const [capturingSnapshot, setCapturingSnapshot] = useState(false);

  const [webcamStatus, setWebcamStatus] = useState<WebcamStatusData | null>(null);
  const [restrictedZones, setRestrictedZones] = useState<RestrictedZone[]>([]);
  const [zoneEnabled, setZoneEnabled] = useState(true);

  // Camera device enumeration (USB webcam selector)
  const [cameraDevices, setCameraDevices] = useState<MediaDeviceInfo[]>([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState<string>("");

  const [localCamUrl, setLocalCamUrl] = useState<string>("");

  const [boxSmooth, setBoxSmooth] = useState<number>(() => {
    const saved = localStorage.getItem("crowdlens_box_smooth");
    return saved !== null ? parseFloat(saved) : 0.7;
  });

  const [overlayStyle, setOverlayStyle] = useState<OverlayStyle>(() => {
    return (localStorage.getItem("crowdlens_overlay_style") as OverlayStyle) ?? "corners";
  });

  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === "crowdlens_box_smooth" && e.newValue !== null) {
        setBoxSmooth(parseFloat(e.newValue));
      }
      if (e.key === "crowdlens_overlay_style" && e.newValue !== null) {
        setOverlayStyle(e.newValue as OverlayStyle);
      }
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  const localRelay = useLocalCamRelay();

  const videoElRef = useRef<HTMLVideoElement | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const tracks = frame?.tracks ?? [];
  const anomalies = frame?.anomalies ?? [];
  // Per-type sticky hold times: fall/fight 12 s, restricted/unattended 10 s,
  // loitering 8 s, running/overcrowding 6 s. See useStickyAnomalies for the
  // full table. Drop the legacy uniform 8 s so a fall alert lingers long
  // enough for the operator to react before it disappears from the feed.
  const visibleAnomalies = useStickyAnomalies(anomalies);
  const stats = frame?.stats ?? null;
  const displayMode = (frame?.mode as SourceMode) ?? sourceMode;

  useAlertSound(anomalies, soundEnabled);
  const { permission: notifPermission, enabled: notifEnabled, requestPermission } = useNotifications(anomalies);

  const criticalCount = visibleAnomalies.filter((a) => DASHBOARD_CRITICAL_TYPES.has(a.type)).length;
  useEffect(() => {
    if (criticalCount > 0) {
      document.title = `\u26a0 CrowdLens \u2014 ${criticalCount} Alert${criticalCount > 1 ? "s" : ""}`;
    } else {
      document.title = "CrowdLens \u00b7 Campus AI";
    }
    return () => { document.title = "CrowdLens \u00b7 Campus AI"; };
  }, [criticalCount]);

  useCamProcessor(
    sourceMode === "webcam" ? videoElRef : null,
    sourceMode === "webcam",
  );

  // Poll video status — no dependencies so interval is stable
  useEffect(() => {
    const poll = async () => {
      if (document.visibilityState !== "visible") return;
      try {
        const res = await fetch("/api/video/status");
        const data = await res.json();
        setVideoStatus(prev => {
          if (prev?.mode === "processing" && data.mode !== "processing") {
            setSourceMode(s => s === "video" ? "idle" : s);
          }
          return data;
        });
      } catch {}
    };
    poll();
    const id = setInterval(poll, 1500);
    return () => clearInterval(id);
  }, []);

  // Poll stream status — stable interval; auto-reset mode when stream errors out
  useEffect(() => {
    const poll = async () => {
      if (document.visibilityState !== "visible") return;
      try {
        const res = await fetch("/api/stream/status");
        const data = await res.json();
        setStreamStatus(data);
        // If backend says stream stopped with error, reset our UI state
        if (data.error && !data.active) {
          setSourceMode(prev => prev === "stream" ? "idle" : prev);
        }
      } catch {}
    };
    poll();
    const id = setInterval(poll, 2000);
    return () => clearInterval(id);
  }, []);

  // Poll webcam status — stable interval, no sourceMode dependency
  useEffect(() => {
    const poll = async () => {
      if (document.visibilityState !== "visible") return;
      try {
        const res = await fetch("/api/webcam/status");
        const data = await res.json();
        setWebcamStatus(data);
      } catch {}
    };
    poll();
    const id = setInterval(poll, 2000);
    return () => clearInterval(id);
  }, []);

  // Enumerate camera devices on mount and whenever permissions change
  useEffect(() => {
    const enumerate = async () => {
      try {
        const devices = await navigator.mediaDevices.enumerateDevices();
        setCameraDevices(devices.filter(d => d.kind === "videoinput"));
      } catch { /* browser may deny enumeration before permission is granted */ }
    };
    enumerate();
    navigator.mediaDevices.addEventListener?.("devicechange", enumerate);
    return () => navigator.mediaDevices.removeEventListener?.("devicechange", enumerate);
  }, []);

  useEffect(() => {
    localStorage.setItem(CAMERA_PROFILE_KEY, JSON.stringify(cameraProfiles.slice(0, MAX_CAMERAS)));
  }, [cameraProfiles]);

  useEffect(() => {
    const loadConfig = async () => {
      try {
        const res = await fetch("/api/config");
        const data = await res.json();
        if (Array.isArray(data.restricted_zones)) {
          setRestrictedZones(data.restricted_zones);
        }
        if (typeof data.restricted_zone_enabled === "boolean") {
          setZoneEnabled(data.restricted_zone_enabled);
        }
      } catch {}
    };
    loadConfig();
    const id = setInterval(() => {
      if (document.visibilityState !== "visible") return;
      loadConfig();
    }, 2000);
    return () => clearInterval(id);
  }, []);

  // ── Webcam ──────────────────────────────────────────────────────────────────

  const enableCamera = useCallback(async (deviceId?: string) => {
    setCameraError(null);
    try {
      // Stop any existing tracks
      mediaStreamRef.current?.getTracks().forEach(t => t.stop());

      const effectiveId = deviceId ?? selectedDeviceId;
      const videoConstraints = effectiveId
        ? { deviceId: { exact: effectiveId }, width: { ideal: 1280 }, height: { ideal: 720 } }
        : { width: { ideal: 1280 }, height: { ideal: 720 } };

      const stream = await navigator.mediaDevices.getUserMedia({
        video: videoConstraints,
        audio: false,
      });
      mediaStreamRef.current = stream;
      // Refresh device list now that permission is granted (labels become visible)
      try {
        const devices = await navigator.mediaDevices.enumerateDevices();
        setCameraDevices(devices.filter(d => d.kind === "videoinput"));
      } catch { /* ignore */ }

      // Reuse existing video element or create once
      if (!videoElRef.current) {
        const vid = document.createElement("video");
        vid.muted = true;
        vid.playsInline = true;
        vid.autoplay = true;
        videoElRef.current = vid;
      }
      videoElRef.current.srcObject = stream;
      await videoElRef.current.play();

      const res = await fetch("/api/webcam/start", { method: "POST" });
      if (!res.ok) {
        const d = await res.json();
        throw new Error(d.detail ?? "Could not start webcam processing");
      }

      setSourceMode("webcam");
      setActivePanel("none");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Camera access denied";
      setCameraError(msg);
      mediaStreamRef.current?.getTracks().forEach(t => t.stop());
      mediaStreamRef.current = null;
    }
  }, [selectedDeviceId]);

  const stopLocalCam = useCallback(async () => {
    localRelay.stop();
    await fetch("/api/webcam/stop", { method: "POST" }).catch(() => {});
    setSourceMode("idle");
  }, [localRelay]);

  const startLocalCam = useCallback(async () => {
    const url = localCamUrl.trim();
    if (!url) return;
    await localRelay.start(url, async () => {
      const res = await fetch("/api/webcam/start", { method: "POST" });
      if (!res.ok) {
        const d = await res.json();
        throw new Error(d.detail ?? "Could not start backend processing");
      }
    });
    setSourceMode("webcam");
    // Keep panel open so status & errors remain visible
  }, [localCamUrl, localRelay]);

  const disableCamera = useCallback(async () => {
    // Stop USB stream if active
    mediaStreamRef.current?.getTracks().forEach(t => t.stop());
    mediaStreamRef.current = null;
    if (videoElRef.current) {
      videoElRef.current.srcObject = null;
    }
    // Stop local relay if active
    localRelay.stop();
    await fetch("/api/webcam/stop", { method: "POST" }).catch(() => {});
    setSourceMode("idle");
    setCameraError(null);
  }, [localRelay]);

  // ── Video upload ─────────────────────────────────────────────────────────────

  const handleFileUpload = (file: File) => {
    const MAX_MB = 500;
    if (file.size > MAX_MB * 1024 * 1024) {
      setUploadError(`File is too large (${(file.size / 1e6).toFixed(0)} MB). Max is ${MAX_MB} MB.`);
      return;
    }

    setUploading(true);
    setUploadProgress(0);
    setUploadError(null);

    const form = new FormData();
    form.append("file", file);

    const xhr = new XMLHttpRequest();

    xhr.upload.addEventListener("progress", (e) => {
      if (e.lengthComputable) {
        setUploadProgress(Math.round((e.loaded / e.total) * 100));
      }
    });

    xhr.addEventListener("load", () => {
      setUploading(false);
      if (xhr.status >= 200 && xhr.status < 300) {
        setUploadProgress(100);
      } else {
        try {
          const data = JSON.parse(xhr.responseText);
          setUploadError(data.detail ?? `Upload failed (HTTP ${xhr.status})`);
        } catch {
          setUploadError(`Upload failed (HTTP ${xhr.status})`);
        }
      }
    });

    xhr.addEventListener("error", () => {
      setUploading(false);
      setUploadError("Network error — upload could not reach the server. Check your connection.");
    });

    xhr.addEventListener("timeout", () => {
      setUploading(false);
      setUploadError("Upload timed out. The file may be too large for the current connection.");
    });

    xhr.open("POST", "/api/video/upload");
    xhr.timeout = 10 * 60 * 1000; // 10 minute timeout
    xhr.send(form);
  };

  const startVideoProcessing = async () => {
    const res = await fetch("/api/video/start", { method: "POST" });
    if (!res.ok) {
      const d = await res.json();
      setUploadError(d.detail);
    } else {
      setSourceMode("video");
    }
  };

  const stopVideoProcessing = async () => {
    await fetch("/api/video/stop", { method: "POST" });
    setSourceMode("idle");
  };

  // ── Stream ────────────────────────────────────────────────────────────────────

  const startStream = async () => {
    setStreamError(null);
    const rawInput = streamUrl.trim();
    if (!rawInput) { setStreamError("Enter a stream URL first"); return; }

    const matched = rawInput.match(/(rtsp:\/\/[^\s]+|https?:\/\/[^\s]+)/i);
    if (!matched) {
      setStreamError("Enter a valid URL starting with rtsp://, http://, or https://");
      return;
    }
    const normalizedUrl = matched[1].replace(/[),.;]+$/, "");
    if (normalizedUrl !== rawInput) {
      setStreamUrl(normalizedUrl);
    }

    try {
      const res = await fetch("/api/stream/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: normalizedUrl }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.detail ?? "Could not start stream");
      setSourceMode("stream");
    } catch (e: unknown) {
      setStreamError(e instanceof Error ? e.message : "Stream error");
    }
  };

  const addCameraProfile = () => {
    const url = streamUrl.trim();
    if (!url || cameraProfiles.length >= MAX_CAMERAS) return;
    const name = (cameraNameDraft.trim() || `Camera ${cameraProfiles.length + 1}`).slice(0, 32);
    const next: CameraProfile = { id: crypto.randomUUID(), name, url };
    setCameraProfiles((prev) => [...prev, next].slice(0, MAX_CAMERAS));
    setCameraNameDraft("");
  };

  const removeCameraProfile = (id: string) => {
    setCameraProfiles((prev) => prev.filter((p) => p.id !== id));
  };

  const applyCameraProfile = (profile: CameraProfile) => {
    setStreamUrl(profile.url);
    setStreamError(null);
  };

  const stopStream = async () => {
    await fetch("/api/stream/stop", { method: "POST" });
    setSourceMode("idle");
  };

  const captureSnapshot = async () => {
    if (capturingSnapshot) return;
    setCapturingSnapshot(true);
    setCaptureInfo(null);
    try {
      const res = await fetch("/api/archive/capture", { method: "POST" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail ?? "Failed to capture snapshot");
      setCaptureInfo("Snapshot captured. Open Alert History and check latest entry.");
    } catch (e: unknown) {
      setCaptureInfo(e instanceof Error ? e.message : "Snapshot capture failed");
    } finally {
      setCapturingSnapshot(false);
    }
  };

  const toggleRestrictedZone = async () => {
    const next = !zoneEnabled;
    try {
      const res = await fetch("/api/config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ restricted_zone_enabled: next }),
      });
      if (!res.ok) throw new Error("Failed to update restricted zone setting");
      setZoneEnabled(next);
      setCaptureInfo(next ? "Restricted zone detection enabled." : "Restricted zone detection disabled.");
    } catch {
      setCaptureInfo("Could not change restricted zone setting.");
    }
  };

  const isVideoProcessing = videoStatus?.mode === "processing";
  const hasUpload = !!(videoStatus?.filename && videoStatus?.mode !== "idle");
  const isStreaming = streamStatus?.active === true || sourceMode === "stream";
  const modelReady = videoStatus?.model_ready ?? false;
  const modelError = videoStatus?.model_error ?? null;
  const fallModelReady = videoStatus?.fall_model_ready ?? false;
  const fallModelError = videoStatus?.fall_model_error ?? null;
  const allModelsReady = modelReady && fallModelReady;

  const metricPills = [
    { icon: Users,         label: "PERSONS",      value: stats?.person_count ?? 0,  color: "#3b82f6" },
    { icon: Package,       label: "OBJECTS",       value: stats?.object_count ?? 0,  color: "#f59e0b" },
    { icon: AlertTriangle, label: "ANOMALIES",     value: visibleAnomalies.length,   color: visibleAnomalies.length > 0 ? "#ef4444" : "#10b981" },
    { icon: Activity,      label: "ACTIVE TRACKS", value: tracks.length,             color: "#a855f7" },
  ];

  return (
    <div>
      {/* ── Hidden file input — always mounted so file picker works ── */}
      <input
        ref={fileInputRef}
        type="file"
        accept="video/*"
        style={{ display: "none" }}
        onChange={e => {
          const f = e.target.files?.[0];
          if (f) handleFileUpload(f);
          // Reset so the same file can be re-selected
          e.target.value = "";
        }}
      />

      {/* ── Header ── */}
      <div style={{ marginBottom: 26 }}>
        <div style={{ marginBottom: isMobile ? 18 : 28 }}>
          <h1 style={{ fontSize: isMobile ? 22 : 30, fontWeight: 800, color: "var(--app-text)", letterSpacing: 0, margin: "0 0 8px" }}>
            Live Surveillance
          </h1>
          <p style={{ color: "var(--app-text-muted)", fontSize: isMobile ? 13 : 18, margin: 0 }}>
            {displayMode === "video"  && "YOLO11m + SORT — processing uploaded video"}
            {displayMode === "webcam" && "YOLO11m + SORT — real-time webcam detection"}
            {displayMode === "stream" && `YOLO11m + SORT — live stream: ${streamStatus?.url ?? ""}`}
            {(displayMode === "idle" || !displayMode) && "Monitor your campus feeds in real time"}
          </p>
        </div>

        <div style={{
          display: "flex", alignItems: "center", gap: 12,
          overflowX: isMobile ? "auto" : "visible",
          flexWrap: isMobile ? "nowrap" : "wrap",
          paddingBottom: isMobile ? 4 : 0,
          scrollbarWidth: "none",
        }}>
          {/* Sound toggle */}
          <button
            onClick={() => setSoundEnabled(v => !v)}
            style={{
              display: "flex", alignItems: "center", justifyContent: "center", gap: 8, minWidth: 134, padding: "10px 18px", borderRadius: 10,
              border: soundEnabled ? "1px solid #b8e7df" : "1px solid var(--app-card-border)", background: soundEnabled ? "#ecfbf8" : "var(--app-card-bg)",
              color: soundEnabled ? "#0f8f83" : "var(--app-text-muted)", cursor: "pointer", fontSize: 18, fontWeight: 600,
            }}
          >
            {soundEnabled ? <Volume2 size={14} /> : <VolumeX size={14} />}
            {soundEnabled ? "Sound ON" : "Sound OFF"}
          </button>

          {/* Browser push notifications toggle */}
          {notifPermission !== "unsupported" && (
            <button
              onClick={requestPermission}
              title={
                notifPermission === "denied"
                  ? "Notifications blocked — enable in browser settings"
                  : notifEnabled
                  ? "Disable push notifications"
                  : "Enable push notifications"
              }
              style={{
                display: "flex", alignItems: "center", justifyContent: "center", gap: 8, minWidth: 134, padding: "10px 18px", borderRadius: 10,
                border: "1px solid var(--app-card-border)", background: "var(--app-card-bg)",
                color: notifEnabled ? "#f59e0b" : "var(--app-text-muted)",
                cursor: notifPermission === "denied" ? "not-allowed" : "pointer",
                fontSize: 18, fontWeight: 600, opacity: notifPermission === "denied" ? 0.5 : 1,
              }}
            >
              {notifEnabled ? <Bell size={14} /> : <BellOff size={14} />}
              {notifEnabled ? "Alerts ON" : "Alerts OFF"}
            </button>
          )}

          {/* Webcam button */}
          <button
            onClick={() => {
              if (sourceMode === "webcam") { disableCamera(); }
              else { setActivePanel(p => p === "webcam" ? "none" : "webcam"); }
            }}
            disabled={isVideoProcessing || isStreaming}
            style={{
              display: "flex", alignItems: "center", justifyContent: "center", gap: 8, minWidth: 136, padding: "10px 18px", borderRadius: 10,
              border: "1px solid", cursor: (isVideoProcessing || isStreaming) ? "not-allowed" : "pointer",
              fontSize: 18, fontWeight: 600, transition: "all 0.2s",
              borderColor: sourceMode === "webcam" ? "#0f8f83" : activePanel === "webcam" ? "#0f8f83" : "var(--app-card-border)",
              background: sourceMode === "webcam" ? "#ecfbf8" : activePanel === "webcam" ? "#f3fbf9" : "var(--app-card-bg)",
              color: sourceMode === "webcam" ? "#0f8f83" : activePanel === "webcam" ? "#0f8f83" : "var(--app-text-muted)",
              opacity: (isVideoProcessing || isStreaming) ? 0.4 : 1,
            }}
          >
            {sourceMode === "webcam" ? (
              webcamStatus?.active
                ? <><div style={{ width: 7, height: 7, borderRadius: "50%", background: "#10b981", boxShadow: "0 0 6px #10b981", animation: "pulse-dot 2s infinite" }} /> YOLO LIVE</>
                : <><Loader size={14} style={{ animation: "spin 1s linear infinite" }} /> YOLO Starting…</>
            ) : <><Camera size={14} /> Webcam</>}
          </button>

          {/* Video upload button */}
          <button
            onClick={() => setActivePanel(p => p === "video" ? "none" : "video")}
            style={{
              display: "flex", alignItems: "center", justifyContent: "center", gap: 8, minWidth: 126, padding: "10px 18px", borderRadius: 10,
              border: "1px solid", cursor: "pointer", fontSize: 18, fontWeight: 600,
              borderColor: activePanel === "video" || isVideoProcessing ? "#a855f7" : "var(--app-card-border)",
              background: activePanel === "video" || isVideoProcessing ? "rgba(168,85,247,0.12)" : "var(--app-card-bg)",
              color: activePanel === "video" || isVideoProcessing ? "#a855f7" : "var(--app-text-muted)",
            }}
          >
            <Video size={14} />
            {isVideoProcessing ? "Video Running" : "Upload"}
          </button>

          {/* Stream button */}
          <button
            onClick={() => setActivePanel(p => p === "stream" ? "none" : "stream")}
            style={{
              display: "flex", alignItems: "center", justifyContent: "center", gap: 8, minWidth: 126, padding: "10px 18px", borderRadius: 10,
              border: "1px solid", cursor: "pointer", fontSize: 18, fontWeight: 600,
              borderColor: activePanel === "stream" || isStreaming ? "#f59e0b" : "var(--app-card-border)",
              background: activePanel === "stream" || isStreaming ? "rgba(245,158,11,0.1)" : "var(--app-card-bg)",
              color: activePanel === "stream" || isStreaming ? "#f59e0b" : "var(--app-text-muted)",
            }}
          >
            <Radio size={14} />
            {isStreaming ? "Stream Active" : "Stream"}
          </button>

          <button
            onClick={captureSnapshot}
            disabled={capturingSnapshot || sourceMode === "idle"}
            style={{
              display: "flex", alignItems: "center", justifyContent: "center", gap: 8, minWidth: 146, padding: "10px 18px", borderRadius: 10,
              border: "1px solid var(--app-card-border)",
              cursor: (capturingSnapshot || sourceMode === "idle") ? "not-allowed" : "pointer",
              fontSize: 18, fontWeight: 600,
              background: "#eef5ff", color: "#9fc8ff",
              opacity: (capturingSnapshot || sourceMode === "idle") ? 0.5 : 1,
            }}
          >
            {capturingSnapshot ? <Loader size={14} style={{ animation: "spin 1s linear infinite" }} /> : <Camera size={14} />}
            Snapshot
          </button>

          <button
            onClick={toggleRestrictedZone}
            style={{
              display: "flex", alignItems: "center", justifyContent: "center", gap: 8, minWidth: 130, padding: "10px 18px", borderRadius: 10,
              border: zoneEnabled ? "1px solid #ef4444" : "1px solid var(--app-card-border)", cursor: "pointer",
              fontSize: 18, fontWeight: 700,
              background: zoneEnabled ? "#fff5f3" : "var(--app-card-bg)",
              color: zoneEnabled ? "#dc2626" : "var(--app-text-muted)",
            }}
          >
            <Monitor size={14} />
            {zoneEnabled ? "Zone ON" : "Zone OFF"}
          </button>
        </div>
      </div>

      {/* ── Video Upload Panel ── */}
      {captureInfo && (
        <div
          style={{
            color: captureInfo.toLowerCase().includes("fail") || captureInfo.toLowerCase().includes("no ")
              ? "#ef4444"
              : "#10b981",
            fontSize: 12,
            marginBottom: 12,
          }}
        >
          {captureInfo}
        </div>
      )}

      {activePanel === "video" && (
        <div style={{
          background: "rgba(168,85,247,0.05)", border: "1px solid rgba(168,85,247,0.2)",
          borderRadius: 14, padding: 20, marginBottom: 20,
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
            <div style={{ fontSize: 9, color: "#a855f7", letterSpacing: 2, fontWeight: 700 }}>
              YOLO11m REAL DETECTION · UPLOAD VIDEO FILE
            </div>
            <button onClick={() => setActivePanel("none")} style={{ background: "none", border: "none", cursor: "pointer", color: "#475569" }}>
              <X size={16} />
            </button>
          </div>

          {/* Model status */}
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16, fontSize: 11 }}>
            {allModelsReady ? (
              <><CheckCircle size={13} color="#10b981" /><span style={{ color: "#10b981" }}>YOLO11m + Fall model ready</span></>
            ) : fallModelError ? (
              <><X size={13} color="#ef4444" /><span style={{ color: "#ef4444" }}>Fall model error: {fallModelError}</span></>
            ) : modelError ? (
              <><X size={13} color="#ef4444" /><span style={{ color: "#ef4444" }}>Model error: {modelError}</span></>
            ) : (
              <><Loader size={13} color="#f59e0b" style={{ animation: "spin 1s linear infinite" }} />
              <span style={{ color: "#f59e0b" }}>Loading detection models…</span></>
            )}
          </div>

          {!isVideoProcessing && (
            <div
              onDragOver={e => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={e => {
                e.preventDefault();
                setDragOver(false);
                const f = e.dataTransfer.files[0];
                if (f) handleFileUpload(f);
              }}
              onClick={() => fileInputRef.current?.click()}
              style={{
                border: `2px dashed ${dragOver ? "#a855f7" : "rgba(168,85,247,0.3)"}`,
                borderRadius: 10, padding: "24px 20px", textAlign: "center",
                cursor: "pointer", transition: "border-color 0.2s",
                background: dragOver ? "rgba(168,85,247,0.08)" : "transparent", marginBottom: 12,
              }}
            >
              <Upload size={24} color="#a855f7" style={{ margin: "0 auto 8px", display: "block" }} />
              <div style={{ color: "#94a3b8", fontSize: 13 }}>
                {uploading
                  ? "Uploading…"
                  : (videoStatus?.filename && hasUpload)
                    ? <><span style={{ color: "#a855f7", fontWeight: 600 }}>{videoStatus.filename}</span> · ready to process</>
                    : "Drop video here or click to browse"
                }
              </div>
              <div style={{ fontSize: 11, color: "#475569", marginTop: 4 }}>MP4, AVI, MOV, MKV · max 500 MB</div>
            </div>
          )}

          {uploadError && (
            <div style={{ color: "#ef4444", fontSize: 12, marginBottom: 10 }}>{uploadError}</div>
          )}

          {isVideoProcessing && (
            <div style={{ marginBottom: 12 }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "#64748b", marginBottom: 6 }}>
                <span>{videoStatus?.filename}</span>
                <span>{videoStatus?.progress?.toFixed(1)}% · frame {videoStatus?.current_frame}/{videoStatus?.total_frames}</span>
              </div>
              <div style={{ height: 6, background: "rgba(255,255,255,0.06)", borderRadius: 3 }}>
                <div style={{
                  height: "100%", borderRadius: 3, width: `${videoStatus?.progress ?? 0}%`,
                  background: "linear-gradient(90deg,#7c3aed,#a855f7)", transition: "width 0.5s",
                }} />
              </div>
            </div>
          )}

          {videoStatus?.error && (
            <div style={{ color: "#ef4444", fontSize: 12, marginBottom: 10 }}>Error: {videoStatus.error}</div>
          )}

          <div style={{ display: "flex", gap: 10 }}>
            {!isVideoProcessing && hasUpload && (
              <button onClick={startVideoProcessing} disabled={!allModelsReady} style={{
                display: "flex", alignItems: "center", gap: 8, padding: "8px 18px", borderRadius: 8,
                border: "none", cursor: allModelsReady ? "pointer" : "not-allowed",
                background: allModelsReady ? "linear-gradient(135deg,#7c3aed,#a855f7)" : "#1e1b4b",
                color: "#fff", fontWeight: 700, fontSize: 13,
              }}>
                <Video size={14} /> Start Real Detection
              </button>
            )}
            {isVideoProcessing && (
              <button onClick={stopVideoProcessing} style={{
                display: "flex", alignItems: "center", gap: 8, padding: "8px 18px", borderRadius: 8,
                border: "none", cursor: "pointer", background: "rgba(239,68,68,0.15)",
                color: "#ef4444", fontWeight: 700, fontSize: 13, outline: "1px solid rgba(239,68,68,0.3)",
              }}>
                <StopCircle size={14} /> Stop Processing
              </button>
            )}
          </div>
        </div>
      )}

      {/* ── Webcam / Local Camera Panel ── */}
      {activePanel === "webcam" && (
        <div style={{
          background: "rgba(16,185,129,0.04)", border: "1px solid rgba(16,185,129,0.2)",
          borderRadius: 14, padding: 20, marginBottom: 20,
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
            <div style={{ fontSize: 9, color: "#10b981", letterSpacing: 2, fontWeight: 700 }}>
              LIVE CAMERA · YOLO11m REAL-TIME DETECTION
            </div>
            <button onClick={() => setActivePanel("none")} style={{ background: "none", border: "none", cursor: "pointer", color: "#475569" }}>
              <X size={16} />
            </button>
          </div>

          {/* ── USB / Built-in Camera ── */}
          <div style={{ marginBottom: 20 }}>
            <div style={{ fontSize: 12, color: "#94a3b8", fontWeight: 600, marginBottom: 8, display: "flex", alignItems: "center", gap: 6 }}>
              <Camera size={13} /> USB / Built-in Camera
            </div>
            {cameraError && <div style={{ color: "#ef4444", fontSize: 12, marginBottom: 8 }}>{cameraError}</div>}
            {cameraDevices.length > 1 ? (
              <select
                value={selectedDeviceId}
                onChange={e => setSelectedDeviceId(e.target.value)}
                style={{
                  width: "100%", padding: "8px 12px", borderRadius: 8, marginBottom: 10,
                  background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)",
                  color: "#f1f5f9", fontSize: 12, outline: "none", cursor: "pointer",
                }}
              >
                <option value="">Auto-select (default)</option>
                {cameraDevices.map(d => (
                  <option key={d.deviceId} value={d.deviceId}>
                    {d.label || `Camera ${d.deviceId.slice(0, 8)}…`}
                  </option>
                ))}
              </select>
            ) : cameraDevices.length === 0 ? (
              <div style={{ fontSize: 11, color: "#475569", marginBottom: 10 }}>
                No cameras detected yet — starting will prompt browser permission.
              </div>
            ) : (
              <div style={{ fontSize: 11, color: "#64748b", marginBottom: 10 }}>
                {cameraDevices[0]?.label || "Default camera detected"}
              </div>
            )}
            <button
              onClick={() => enableCamera()}
              disabled={isVideoProcessing || isStreaming}
              style={{
                display: "flex", alignItems: "center", gap: 8, padding: "8px 18px", borderRadius: 8,
                border: "none", cursor: "pointer",
                background: "linear-gradient(135deg,#059669,#10b981)", color: "#fff", fontWeight: 700, fontSize: 13,
              }}
            >
              <Camera size={14} /> Start USB Camera
            </button>
          </div>

          <hr style={{ border: "none", borderTop: "1px solid rgba(255,255,255,0.06)", marginBottom: 16 }} />

          {/* ── Local IP Camera (MJPEG Relay) ── */}
          <div>
            <div style={{ fontSize: 12, color: "#94a3b8", fontWeight: 600, marginBottom: 8, display: "flex", alignItems: "center", gap: 6 }}>
              <Radio size={13} /> Phone Camera — Browser MJPEG Relay
            </div>
            <div style={{
              fontSize: 11, color: "#64748b", background: "rgba(56,189,248,0.05)",
              border: "1px solid rgba(56,189,248,0.12)", borderRadius: 7, padding: "8px 10px", marginBottom: 10, lineHeight: 1.6,
            }}>
              <strong style={{ color: "#38bdf8" }}>For wired campus / IP cameras:</strong> use the{" "}
              <strong style={{ color: "#f59e0b" }}>Live Stream</strong> button above — paste your RTSP/HTTP URL there for best performance.
              This section is for <strong>phone cameras</strong> (DroidCam, IP Webcam) that expose an HTTP MJPEG endpoint.
            </div>
            <div style={{ fontSize: 10, color: "#64748b", marginBottom: 10, lineHeight: 1.9 }}>
              <strong style={{ color: "#94a3b8" }}>DroidCam (phone) URLs — replace IP with your phone's IP:</strong><br />
              MJPEG stream: <code style={{ color: "#38bdf8" }}>http://192.168.1.8:4747/video</code><br />
              Snapshot (more stable): <code style={{ color: "#38bdf8" }}>http://192.168.1.8:4747/shot.jpg</code>
            </div>
            <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
              <div style={{ position: "relative", flex: 1 }}>
                <Link size={13} color="#64748b" style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)" }} />
                <input
                  type="text"
                  value={localCamUrl}
                  onChange={e => setLocalCamUrl(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && localRelay.state === "idle" && startLocalCam()}
                  placeholder="http://192.168.1.8:4747/video  or  /shot.jpg"
                  disabled={localRelay.state === "active" || localRelay.state === "connecting"}
                  style={{
                    width: "100%", padding: "9px 12px 9px 32px", borderRadius: 8, boxSizing: "border-box",
                    background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.1)",
                    color: "#f1f5f9", fontSize: 12, outline: "none",
                  }}
                />
              </div>
              {localRelay.state !== "active" && localRelay.state !== "connecting" ? (
                <button
                  onClick={startLocalCam}
                  disabled={!localCamUrl.trim()}
                  style={{
                    display: "flex", alignItems: "center", gap: 8, padding: "9px 16px", borderRadius: 8,
                    border: "none", cursor: localCamUrl.trim() ? "pointer" : "not-allowed",
                    background: localCamUrl.trim() ? "linear-gradient(135deg,#0369a1,#38bdf8)" : "#1c2a3a",
                    color: "#fff", fontWeight: 700, fontSize: 13, whiteSpace: "nowrap",
                  }}
                >
                  <Radio size={14} /> Relay
                </button>
              ) : (
                <button
                  onClick={stopLocalCam}
                  style={{
                    display: "flex", alignItems: "center", gap: 8, padding: "9px 16px", borderRadius: 8,
                    border: "none", cursor: "pointer", background: "rgba(239,68,68,0.15)",
                    color: "#ef4444", fontWeight: 700, fontSize: 13, outline: "1px solid rgba(239,68,68,0.3)",
                    whiteSpace: "nowrap",
                  }}
                >
                  <StopCircle size={14} /> Stop
                </button>
              )}
            </div>
            {localRelay.state === "connecting" && (
              <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 11 }}>
                <Loader size={13} color="#38bdf8" style={{ animation: "spin 1s linear infinite" }} />
                <span style={{ color: "#38bdf8" }}>Connecting to camera…</span>
              </div>
            )}
            {localRelay.state === "active" && (
              <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 11 }}>
                <div style={{ width: 7, height: 7, borderRadius: "50%", background: "#10b981", boxShadow: "0 0 6px #10b981", animation: "pulse-dot 2s infinite" }} />
                <span style={{ color: "#10b981" }}>Relaying frames — YOLO11m processing live</span>
              </div>
            )}
            {localRelay.error && (
              <div style={{ color: "#ef4444", fontSize: 11, marginTop: 8, whiteSpace: "pre-wrap", lineHeight: 1.5 }}>
                {localRelay.error}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Stream / IP Camera Panel ── */}
      {activePanel === "stream" && (
        <div style={{
          background: "rgba(245,158,11,0.04)", border: "1px solid rgba(245,158,11,0.2)",
          borderRadius: 14, padding: 20, marginBottom: 20,
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
            <div style={{ fontSize: 9, color: "#f59e0b", letterSpacing: 2, fontWeight: 700 }}>
              IP CAMERA · RTSP / HTTP / MJPEG — YOLO11m REAL-TIME
            </div>
            <button onClick={() => setActivePanel("none")} style={{ background: "none", border: "none", cursor: "pointer", color: "#475569" }}>
              <X size={16} />
            </button>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14, fontSize: 11 }}>
            {(streamStatus?.model_ready && streamStatus?.fall_model_ready) ? (
              <><CheckCircle size={13} color="#10b981" /><span style={{ color: "#10b981" }}>YOLO11m + Fall model ready</span></>
            ) : streamStatus?.fall_model_error ? (
              <><X size={13} color="#ef4444" /><span style={{ color: "#ef4444" }}>Fall model error: {streamStatus.fall_model_error}</span></>
            ) : streamStatus?.model_error ? (
              <><X size={13} color="#ef4444" /><span style={{ color: "#ef4444" }}>Model error: {streamStatus.model_error}</span></>
            ) : (
              <><Loader size={13} color="#f59e0b" style={{ animation: "spin 1s linear infinite" }} />
              <span style={{ color: "#f59e0b" }}>Loading detection models…</span></>
            )}
          </div>

          {/* Camera URL examples */}
          <div style={{
            fontSize: 11, color: "#64748b", background: "rgba(255,255,255,0.03)",
            border: "1px solid rgba(255,255,255,0.07)", borderRadius: 8, padding: "10px 12px", marginBottom: 12, lineHeight: 2,
          }}>
            <div style={{ color: "#94a3b8", fontWeight: 700, fontSize: 10, letterSpacing: 1, marginBottom: 6 }}>WIRED IP CAMERA URLS (replace IP with your camera's IP)</div>
            <div><code style={{ color: "#10b981" }}>rtsp://admin:password@192.168.1.100:554/stream</code> <span style={{ color: "#475569" }}>— Universal RTSP</span></div>
            <div><code style={{ color: "#10b981" }}>rtsp://admin:password@192.168.1.100:554/Streaming/Channels/101</code> <span style={{ color: "#475569" }}>— Hikvision</span></div>
            <div><code style={{ color: "#10b981" }}>rtsp://admin:password@192.168.1.100:554/cam/realmonitor?channel=1&subtype=0</code> <span style={{ color: "#475569" }}>— Dahua</span></div>
            <div><code style={{ color: "#10b981" }}>rtsp://root:pass@192.168.1.100/axis-media/media.amp</code> <span style={{ color: "#475569" }}>— Axis</span></div>
            <div><code style={{ color: "#38bdf8" }}>http://192.168.1.100/video.cgi</code> <span style={{ color: "#475569" }}>— HTTP MJPEG stream</span></div>
          </div>

          <button
            onClick={() => setStreamUrl("http://localhost:8080/api/stream/test-feed")}
            style={{
              display: "inline-flex", alignItems: "center", gap: 6,
              marginBottom: 10, padding: "5px 12px", borderRadius: 6,
              border: "1px solid rgba(16,185,129,0.3)", background: "rgba(16,185,129,0.08)",
              color: "#10b981", fontSize: 11, fontWeight: 600, cursor: "pointer",
            }}
          >
            ⚡ Fill built-in test stream
          </button>

          <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
            <div style={{ position: "relative", flex: 1 }}>
              <Link size={13} color="#64748b" style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)" }} />
              <input
                type="text"
                value={streamUrl}
                onChange={e => setStreamUrl(e.target.value)}
                onKeyDown={e => e.key === "Enter" && !isStreaming && startStream()}
                placeholder="rtsp://admin:password@192.168.1.x:554/stream"
                disabled={isStreaming}
                style={{
                  width: "100%", padding: "9px 12px 9px 32px", borderRadius: 8, boxSizing: "border-box",
                  background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.1)",
                  color: "#f1f5f9", fontSize: 12, outline: "none",
                }}
              />
            </div>
            {!isStreaming ? (
              <button onClick={startStream} disabled={!(streamStatus?.model_ready && streamStatus?.fall_model_ready)} style={{
                display: "flex", alignItems: "center", gap: 8, padding: "9px 18px", borderRadius: 8,
                border: "none", cursor: (streamStatus?.model_ready && streamStatus?.fall_model_ready) ? "pointer" : "not-allowed",
                background: (streamStatus?.model_ready && streamStatus?.fall_model_ready) ? "linear-gradient(135deg,#d97706,#f59e0b)" : "#1c1a10",
                color: "#fff", fontWeight: 700, fontSize: 13, whiteSpace: "nowrap",
              }}>
                <Radio size={14} /> Connect
              </button>
            ) : (
              <button onClick={stopStream} style={{
                display: "flex", alignItems: "center", gap: 8, padding: "9px 18px", borderRadius: 8,
                border: "none", cursor: "pointer", background: "rgba(239,68,68,0.15)",
                color: "#ef4444", fontWeight: 700, fontSize: 13, outline: "1px solid rgba(239,68,68,0.3)",
                whiteSpace: "nowrap",
              }}>
                <StopCircle size={14} /> Disconnect
              </button>
            )}
          </div>

          <div
            style={{
              background: "rgba(255,255,255,0.03)",
              border: "1px solid rgba(255,255,255,0.08)",
              borderRadius: 10,
              padding: 12,
              marginBottom: 12,
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
              <div style={{ fontSize: 10, color: "#94a3b8", letterSpacing: 1, fontWeight: 700 }}>
                CAMERA WALL ({cameraProfiles.length}/{MAX_CAMERAS})
              </div>
              <button
                onClick={addCameraProfile}
                disabled={!streamUrl.trim() || cameraProfiles.length >= MAX_CAMERAS}
                style={{
                  border: "1px solid rgba(59,130,246,0.35)",
                  background: "rgba(59,130,246,0.14)",
                  color: "#60a5fa",
                  borderRadius: 6,
                  fontSize: 11,
                  fontWeight: 700,
                  padding: "4px 8px",
                  cursor: "pointer",
                }}
              >
                Save Camera
              </button>
            </div>
            <input
              type="text"
              value={cameraNameDraft}
              onChange={(e) => setCameraNameDraft(e.target.value)}
              placeholder="Camera name (optional)"
              style={{
                width: "100%",
                marginBottom: 8,
                padding: "7px 9px",
                borderRadius: 7,
                border: "1px solid rgba(255,255,255,0.12)",
                background: "rgba(255,255,255,0.03)",
                color: "#e2e8f0",
                fontSize: 12,
                outline: "none",
              }}
            />
            <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: 6, maxHeight: 220, overflowY: "auto" }}>
              {cameraProfiles.map((profile) => (
                <div
                  key={profile.id}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: 8,
                    border: "1px solid rgba(148,163,184,0.2)",
                    borderRadius: 8,
                    padding: "6px 8px",
                    background: "rgba(2,6,23,0.35)",
                  }}
                >
                  <button
                    onClick={() => applyCameraProfile(profile)}
                    style={{
                      flex: 1,
                      textAlign: "left",
                      background: "transparent",
                      border: "none",
                      color: "#cbd5e1",
                      cursor: "pointer",
                    }}
                  >
                    <div style={{ fontSize: 12, fontWeight: 700 }}>{profile.name}</div>
                    <div style={{ fontSize: 10, color: "#64748b", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                      {profile.url}
                    </div>
                  </button>
                  <button
                    onClick={() => removeCameraProfile(profile.id)}
                    style={{
                      border: "none",
                      background: "rgba(239,68,68,0.18)",
                      color: "#f87171",
                      borderRadius: 6,
                      cursor: "pointer",
                      padding: "5px 8px",
                      fontSize: 11,
                      fontWeight: 700,
                    }}
                  >
                    Remove
                  </button>
                </div>
              ))}
              {cameraProfiles.length === 0 && (
                <div style={{ fontSize: 11, color: "#64748b" }}>
                  Save up to 10 camera URLs here and switch quickly for operations.
                </div>
              )}
            </div>
          </div>

          {(streamError || streamStatus?.error) && (
            <div style={{ color: "#ef4444", fontSize: 12 }}>
              {streamError ?? `Stream error: ${streamStatus?.error}`}
            </div>
          )}

          {isStreaming && !streamStatus?.error && (
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 10, fontSize: 11 }}>
              <div style={{ width: 8, height: 8, borderRadius: "50%", background: "#f59e0b", boxShadow: "0 0 8px #f59e0b", animation: "pulse-amber 1.4s infinite" }} />
              <span style={{ color: "#f59e0b" }}>Stream active — YOLO11m processing</span>
            </div>
          )}
        </div>
      )}

      {/* ── Main grid ── */}
      <div style={{
        display: "grid",
        gridTemplateColumns: isMobile ? "1fr" : "minmax(0, 1fr) 340px",
        gap: isMobile ? 14 : 28,
        alignItems: "start",
      }}>
        <div>
          <div style={{
            borderRadius: 22, border: "1px solid #d9d6d2", overflow: "hidden",
            background: "#141414", position: "relative",
            boxShadow: "0 18px 45px rgba(22,20,18,0.12)",
          }}>
            {!connected && (
              <div style={{
                position: "absolute", inset: 0, background: "rgba(6,10,18,0.88)",
                display: "flex", alignItems: "center", justifyContent: "center",
                flexDirection: "column", gap: 14, zIndex: 10, backdropFilter: "blur(4px)",
              }}>
                <Cpu size={36} color="#1e3a5f" />
                <div style={{ color: "#64748b", fontSize: 14, fontWeight: 600 }}>Connecting to detection engine…</div>
                <div style={{ display: "flex", gap: 6 }}>
                  {[0, 1, 2].map(i => (
                    <div key={i} style={{
                      width: 8, height: 8, borderRadius: "50%", background: "#1e40af",
                      animation: `bounce-dot 1.2s ${i * 0.2}s infinite`,
                    }} />
                  ))}
                </div>
              </div>
            )}
            <SimulationCanvas
              tracks={tracks}
              anomalies={anomalies}
              cameraMode={sourceMode === "webcam" ? "webcam" : "idle"}
              videoRef={videoElRef}
              sourceMode={displayMode}
              frameJpeg={frame?.frame_jpeg}
              restrictedZones={zoneEnabled ? restrictedZones : []}
              smoothFactor={boxSmooth}
              overlayStyle={overlayStyle}
            />
          </div>

          {/* Metric pills */}
          <div style={{
            display: "grid",
            gridTemplateColumns: isMobile ? "1fr 1fr" : "repeat(4, 1fr)",
            gap: isMobile ? 8 : 12,
            marginTop: 16,
          }}>
            {metricPills.map(({ icon: Icon, label, value, color }) => (
              <div key={label} style={{ ...PILL_STYLE, flex: "unset" }}>
                <Icon size={16} color={color} style={{ flexShrink: 0 }} />
                <div>
                  <div style={{ fontSize: 22, fontWeight: 800, color, lineHeight: 1.2 }}>{value}</div>
                  <div style={{ fontSize: 9, color: "var(--app-text-muted)", fontWeight: 700, letterSpacing: 1.5, marginTop: 2 }}>
                    {label}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Right sidebar */}
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <AlertsFeed anomalies={visibleAnomalies} />
        </div>
      </div>

    </div>
  );
}

