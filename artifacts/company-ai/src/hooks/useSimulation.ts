import { useEffect, useRef, useState, useCallback } from "react";

export interface Track {
  id: number;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  class_id: number;
  class_name: string;
  running: boolean;
  confidence?: number;
  zone?: "A" | "B" | "C";
}

export interface Anomaly {
  type:
    | "running"
    | "unattended_object"
    | "overcrowding"
    | "fall_detected"
    | "restricted_zone"
    | "fight_suspected"
    | "loitering";
  track_id?: number;
  track_ids?: number[];
  count?: number;
  duration?: number;
  avg_speed?: number;
  body_heights_per_sec?: number;
  avg_pair_speed?: number;
  distance?: number;
  confidence?: number;
  owner_absent?: number;
  zone_id?: string;
  zone_name?: string;
  note?: string;
  class_name?: string;
  bbox?: [number, number, number, number];
  position: [number, number] | null;
}

export interface SimStats {
  person_count: number;
  object_count: number;
  anomaly_count: number;
  fps: number;
  uptime_seconds: number;
}

export interface FrameData {
  tracks: Track[];
  anomalies: Anomaly[];
  stats: SimStats;
  timestamp: number;
  mode?: "idle" | "video" | "webcam" | "stream";
  frame_jpeg?: string;
}


function getWsUrl() {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/ws`;
}

/**
 * Enrich tracks with a `running` boolean derived from the anomalies array.
 * The backend now sends running as an anomaly (not a track-level field), so
 * we must cross-reference here for the canvas to highlight running persons.
 */
function enrichTracks(tracks: Track[], anomalies: Anomaly[]): Track[] {
  const runningIds = new Set<number>();
  for (const a of anomalies) {
    if (a.type === "running" && a.track_id != null) {
      runningIds.add(a.track_id);
    }
  }
  // Only allocate new array if there are running tracks to mark
  if (runningIds.size === 0) {
    // Ensure all have running: false (backend may omit field)
    return tracks.map((t) => (t.running ? { ...t, running: false } : t.running === false ? t : { ...t, running: false }));
  }
  return tracks.map((t) => ({
    ...t,
    running: runningIds.has(t.id),
  }));
}

export function useSimulation() {
  const [frame, setFrame] = useState<FrameData | null>(null);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const shouldReconnectRef = useRef(true);
  // Frame-dropping: only process most recent message per animation frame
  const pendingFrameRef = useRef<FrameData | null>(null);
  const rafRef = useRef<number | null>(null);

  const scheduleUpdate = useCallback((data: FrameData) => {
    pendingFrameRef.current = data;
    if (rafRef.current === null) {
      rafRef.current = requestAnimationFrame(() => {
        rafRef.current = null;
        const pending = pendingFrameRef.current;
        if (pending) {
          pendingFrameRef.current = null;
          // Enrich tracks with running status from anomalies
          const enriched: FrameData = {
            ...pending,
            tracks: enrichTracks(pending.tracks ?? [], pending.anomalies ?? []),
          };
          setFrame(enriched);
        }
      });
    }
  }, []);

  const connect = useCallback(() => {
    if (!shouldReconnectRef.current) return;
    try {
      const ws = new WebSocket(getWsUrl());
      wsRef.current = ws;

      ws.onopen = () => {
        setConnected(true);
        if (reconnectRef.current) {
          clearTimeout(reconnectRef.current);
          reconnectRef.current = null;
        }
      };

      ws.onmessage = (e) => {
        // Skip binary messages (not expected but defensive)
        if (typeof e.data !== "string") return;
        try {
          const data: FrameData = JSON.parse(e.data);
          scheduleUpdate(data);
        } catch {
          // Malformed JSON — drop frame silently
        }
      };

      ws.onclose = () => {
        setConnected(false);
        wsRef.current = null;
        if (!shouldReconnectRef.current) return;
        reconnectRef.current = setTimeout(connect, 2000);
      };

      ws.onerror = () => {
        ws.close();
      };
    } catch {
      if (!shouldReconnectRef.current) return;
      reconnectRef.current = setTimeout(connect, 2000);
    }
  }, [scheduleUpdate]);

  useEffect(() => {
    shouldReconnectRef.current = true;
    connect();
    return () => {
      shouldReconnectRef.current = false;
      if (reconnectRef.current) {
        clearTimeout(reconnectRef.current);
        reconnectRef.current = null;
      }
      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
      const ws = wsRef.current;
      if (ws) {
        // Prevent reconnect from firing during teardown
        ws.onclose = null;
        ws.onerror = null;
        ws.close();
        wsRef.current = null;
      }
    };
  }, [connect]);

  return { frame, connected };
}
