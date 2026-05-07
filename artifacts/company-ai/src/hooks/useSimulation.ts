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
  confidence?: number;   // real value from YOLO11m, undefined in simulation
  zone?: "A" | "B" | "C";
}

export interface Anomaly {
  type: "running" | "unattended_object" | "overcrowding" | "fall_detected" | "restricted_zone" | "fight_suspected";
  track_id?: number;
  track_ids?: number[];
  count?: number;
  duration?: number;
  avg_speed?: number;
  avg_pair_speed?: number;
  distance?: number;
  confidence?: number;
  owner_absent?: number;
  zone_id?: string;
  zone_name?: string;
  note?: string;
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

export function useSimulation() {
  const [frame, setFrame] = useState<FrameData | null>(null);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const shouldReconnectRef = useRef(true);

  const connect = useCallback(() => {
    if (!shouldReconnectRef.current) return;
    try {
      const ws = new WebSocket(getWsUrl());
      wsRef.current = ws;

      ws.onopen = () => {
        setConnected(true);
        if (reconnectRef.current) clearTimeout(reconnectRef.current);
      };

      ws.onmessage = (e) => {
        try {
          const data: FrameData = JSON.parse(e.data);
          setFrame(data);
        } catch {}
      };

      ws.onclose = () => {
        setConnected(false);
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
  }, []);

  useEffect(() => {
    shouldReconnectRef.current = true;
    connect();
    return () => {
      shouldReconnectRef.current = false;
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.onerror = null;
      }
      wsRef.current?.close();
    };
  }, [connect]);

  return { frame, connected };
}
