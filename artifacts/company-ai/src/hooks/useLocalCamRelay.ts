/**
 * useLocalCamRelay — v3
 * ─────────────────────
 * Relays frames from a local IP camera to the CrowdLens backend via /ws/cam.
 *
 * Architecture (fetch-based, no canvas):
 * ┌─────────────────────────────────────────────────────────────────────────┐
 * │ MJPEG stream  → fetch() streaming reader → parse JPEG boundaries        │
 * │ JPEG snapshot → fetch() poll every 300 ms                               │
 * │ Both paths send raw JPEG ArrayBuffers directly to /ws/cam               │
 * │ No <canvas>, no crossOrigin, no CORS-taint SecurityError possible       │
 * └─────────────────────────────────────────────────────────────────────────┘
 *
 * Why no canvas?
 * The old approach (img → drawImage → toBlob) has two fatal flaws:
 *   1. crossOrigin="anonymous" on the img taints the canvas if the camera
 *      does not send Access-Control-Allow-Origin headers → toBlob throws
 *      SecurityError on the very first capture → relay silently dies.
 *   2. When the MJPEG stream drops (DroidCam stopped / phone slept), the img
 *      element retains the last frame (naturalWidth stays > 0, onerror never
 *      fires). The interval keeps drawing the same stale frame forever.
 *
 * This version bypasses both problems: fetch() reads raw bytes, we extract
 * JPEG frames from the multipart MJPEG boundary markers ourselves, and send
 * the raw ArrayBuffer to the backend WebSocket.  No canvas → no taint.
 * When the fetch stream ends we detect it immediately and reconnect.
 */
import { useCallback, useRef, useState } from "react";

const SNAPSHOT_INTERVAL_MS = 200;   // ~5 fps for snapshot mode
const MIN_FRAME_MS         = 200;   // max send rate to backend (5 fps) — DroidCam may
                                    // stream at 15-20 fps; we parse all frames but only
                                    // forward one every MIN_FRAME_MS to match CPU YOLO
const WS_BACKLOG           = 64_000; // bytes — skip frame if WebSocket is backed up
const RECONNECT_DELAY_MS   = 2000;  // pause before reconnecting camera
const STALE_TIMEOUT_MS     = 6000;  // surface "stalled" error after 6 s with no frame
const WS_RECONNECT_MS      = 2000;

function getWsCamUrl() {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/ws/cam`;
}

export type RelayState = "idle" | "connecting" | "active" | "error";

// ─── Tiny MJPEG parser ──────────────────────────────────────────────────────
// Finds the first occurrence of a 2-byte sequence inside a Uint8Array.
function findSeq(buf: Uint8Array, a: number, b: number, from = 0): number {
  for (let i = from; i < buf.length - 1; i++) {
    if (buf[i] === a && buf[i + 1] === b) return i;
  }
  return -1;
}

// ─── Hook ───────────────────────────────────────────────────────────────────
export function useLocalCamRelay() {
  const [state, setState] = useState<RelayState>("idle");
  const [error, setError] = useState<string | null>(null);

  const wsRef          = useRef<WebSocket | null>(null);
  const activeRef      = useRef(false);
  const camStopRef     = useRef(false);      // signals camera fetch loop to stop
  const wsReconnRef    = useRef<ReturnType<typeof setTimeout> | null>(null);
  const camReconnRef   = useRef<ReturnType<typeof setTimeout> | null>(null);
  const staleTimerRef  = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastFrameRef   = useRef<number>(0);  // timestamp of last successful frame (stale detection)
  const lastSentRef    = useRef<number>(0);  // timestamp of last frame sent to backend (throttle)
  const snapshotRef    = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── cleanup helpers ───────────────────────────────────────────────────────
  const clearWsReconn  = () => { if (wsReconnRef.current)   { clearTimeout(wsReconnRef.current);   wsReconnRef.current   = null; } };
  const clearCamReconn = () => { if (camReconnRef.current)  { clearTimeout(camReconnRef.current);  camReconnRef.current  = null; } };
  const clearStale     = () => { if (staleTimerRef.current) { clearTimeout(staleTimerRef.current); staleTimerRef.current = null; } };
  const clearSnapshot  = () => { if (snapshotRef.current)   { clearInterval(snapshotRef.current);  snapshotRef.current   = null; } };

  const stop = useCallback(() => {
    activeRef.current  = false;
    camStopRef.current = true;
    clearWsReconn();
    clearCamReconn();
    clearStale();
    clearSnapshot();
    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.onerror = null;
      wsRef.current.close();
      wsRef.current = null;
    }
    setState("idle");
    setError(null);
  }, []);

  // ── stale-frame watchdog ──────────────────────────────────────────────────
  const armStale = (label: string) => {
    clearStale();
    staleTimerRef.current = setTimeout(() => {
      if (!activeRef.current) return;
      const age = Date.now() - lastFrameRef.current;
      if (age >= STALE_TIMEOUT_MS) {
        setError(
          `No frames received from the camera for ${Math.round(age / 1000)} s.\n` +
          "The camera may have stopped streaming — check it is powered on, reachable on the network, and the URL is correct."
        );
        setState("error");
        activeRef.current = false;
        camStopRef.current = true;
      }
    }, STALE_TIMEOUT_MS + 500);
  };

  const markFrame = () => {
    lastFrameRef.current = Date.now();
  };

  // ── send helper ───────────────────────────────────────────────────────────
  const sendFrame = (buf: ArrayBuffer) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    if (buf.byteLength < 100) return; // sanity: skip empty/corrupt frames
    if (ws.bufferedAmount > WS_BACKLOG) return; // backpressure guard

    // Rate-limit to MIN_FRAME_MS (≈5 fps) — MJPEG cameras may produce 15-20 fps
    // but CPU YOLO can only process ~5 fps; flooding it just adds latency.
    const now = Date.now();
    if (now - lastSentRef.current < MIN_FRAME_MS) return;
    lastSentRef.current = now;

    ws.send(buf);
    markFrame();
  };

  // ════════════════════════════════════════════════════════════════════════════
  // MODE 1 — MJPEG stream via fetch() streaming reader
  // Parses multipart JPEG frames from the raw byte stream without any canvas.
  // ════════════════════════════════════════════════════════════════════════════
  const _runMjpegFetch = async (url: string): Promise<void> => {
    let resp: Response;
    try {
      resp = await fetch(url);
    } catch (e) {
      throw new Error(`Cannot reach camera at ${url}: ${e instanceof Error ? e.message : e}`);
    }

    if (!resp.ok) {
      throw new Error(`Camera returned HTTP ${resp.status} — check the URL`);
    }
    if (!resp.body) {
      throw new Error("Camera stream has no body");
    }

    const reader = resp.body.getReader();
    // Use a list of chunks and only flatten when searching for JPEG boundaries.
    // This avoids O(n²) Uint8Array copies on every read() call.
    let buf = new Uint8Array(0);
    let bufCapacity = 0;

    function appendToBuffer(chunk: Uint8Array) {
      const needed = buf.length + chunk.length;
      if (needed > bufCapacity) {
        // Grow by at least 2× to amortize allocations
        bufCapacity = Math.max(needed, bufCapacity * 2, 65536);
        const grown = new Uint8Array(bufCapacity);
        grown.set(buf);
        buf = grown;
      }
      buf.set(chunk, buf.length);
      // Update the "logical length" via a view trick — store length externally
      buf = new Uint8Array(buf.buffer, 0, needed);
    }

    try {
      while (!camStopRef.current) {
        const { value, done } = await reader.read();
        if (done) break;

        // Grow buffer efficiently
        appendToBuffer(value);

        // Extract all complete JPEG frames (SOI 0xFF 0xD8 … EOI 0xFF 0xD9)
        let attempts = 0;
        while (buf.length > 4 && attempts++ < 20) {
          const soi = findSeq(buf, 0xff, 0xd8);
          if (soi === -1) { buf = new Uint8Array(0); bufCapacity = 0; break; }

          const eoi = findSeq(buf, 0xff, 0xd9, soi + 2);
          if (eoi === -1) {
            // incomplete — keep from SOI onwards and wait for more data
            if (soi > 0) {
              const remaining = buf.slice(soi);
              buf = remaining;
              bufCapacity = remaining.length;
            }
            break;
          }

          // Complete frame found: [soi … eoi+1]
          const frame = buf.slice(soi, eoi + 2);
          sendFrame(frame.buffer.slice(frame.byteOffset, frame.byteOffset + frame.byteLength) as ArrayBuffer);

          const remaining = buf.slice(eoi + 2);
          buf = remaining;
          bufCapacity = remaining.length;
        }

        // Safety: prevent unbounded buffer growth (> 2 MB = something is wrong)
        if (buf.length > 2 * 1024 * 1024) {
          console.warn("[relay] Buffer overrun — flushing");
          buf = new Uint8Array(0);
          bufCapacity = 0;
        }
      }
    } finally {
      reader.cancel().catch(() => {});
    }
  };

  // ════════════════════════════════════════════════════════════════════════════
  // MODE 2 — JPEG snapshot polling
  // Fetches a fresh snapshot JPEG every SNAPSHOT_INTERVAL_MS.
  // No canvas, no parsing needed — the server returns a complete JPEG.
  // ════════════════════════════════════════════════════════════════════════════
  const _startSnapshotRelay = (url: string) => {
    clearSnapshot();
    snapshotRef.current = setInterval(async () => {
      if (!activeRef.current) return;
      const ws = wsRef.current;
      if (!ws || ws.readyState !== WebSocket.OPEN) return;

      try {
        const ts  = Date.now();
        const sep = url.includes("?") ? "&" : "?";
        const res = await fetch(`${url}${sep}_t=${ts}`);
        if (!res.ok) return;
        const buf = await res.arrayBuffer();
        sendFrame(buf);
      } catch {
        // network hiccup — try again next tick
      }
    }, SNAPSHOT_INTERVAL_MS);
  };

  // ════════════════════════════════════════════════════════════════════════════
  // RELAY ENTRY — detect mode, start camera loop
  // ════════════════════════════════════════════════════════════════════════════
  const _startCameraRelay = useCallback(async (url: string) => {
    if (!activeRef.current) return;

    // Detect snapshot vs MJPEG
    const isSnapshot = /\.(jpe?g|png)(\?|$)/i.test(url)
      || /snapshot|capture|shot\.jpg|still/i.test(url);

    if (isSnapshot) {
      _startSnapshotRelay(url);
      armStale(url);
      setState("active");
      return;
    }

    // MJPEG loop with auto-reconnect
    camStopRef.current = false;
    setState("active");
    armStale(url);

    while (activeRef.current && !camStopRef.current) {
      try {
        await _runMjpegFetch(url);
      } catch (e) {
        if (!activeRef.current) break;
        const msg = e instanceof Error ? e.message : String(e);
        console.warn("[relay] MJPEG error:", msg);

        // On first failure before any frames, surface error immediately
        if (lastFrameRef.current === 0) {
          setError(
            msg + "\n\n" +
            "If the URL is correct, make sure:\n" +
            "• The camera is powered on and reachable on the network\n" +
            "• This device and the camera are on the same network\n" +
            "• The stream URL is correct (e.g. http://192.168.x.x:port/video)\n" +
            "• For DroidCam: HTTPS is OFF in DroidCam → Settings → IP Webcam"
          );
          setState("error");
          activeRef.current = false;
          break;
        }
      }

      if (!activeRef.current || camStopRef.current) break;

      // Stream ended (DroidCam stopped) — show warning and reconnect
      if (lastFrameRef.current > 0) {
        console.warn("[relay] MJPEG stream ended — reconnecting in 2 s…");
        // Keep state "active" so UI doesn't jump; reconnect quietly
        await new Promise<void>(res => {
          camReconnRef.current = setTimeout(res, RECONNECT_DELAY_MS);
        });
        clearCamReconn();
        armStale(url); // reset watchdog for next connection
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ════════════════════════════════════════════════════════════════════════════
  // WebSocket management
  // ════════════════════════════════════════════════════════════════════════════
  const _connectWs = useCallback((url: string) => {
    clearWsReconn();
    if (!activeRef.current) return;

    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.close();
      wsRef.current = null;
    }

    setState("connecting");
    const ws = new WebSocket(getWsCamUrl());
    ws.binaryType = "arraybuffer";
    wsRef.current  = ws;

    ws.onopen = () => {
      if (!activeRef.current) { ws.close(); return; }
      // WebSocket is up → start camera relay
      _startCameraRelay(url);
    };

    ws.onclose = () => {
      clearStale();
      clearSnapshot();
      camStopRef.current = true;
      if (activeRef.current) {
        setState("connecting");
        wsReconnRef.current = setTimeout(() => {
          if (activeRef.current) {
            lastFrameRef.current = 0; // reset so first-frame error logic works
            _connectWs(url);
          }
        }, WS_RECONNECT_MS);
      }
    };

    ws.onerror = () => { ws.close(); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [_startCameraRelay]);

  // ════════════════════════════════════════════════════════════════════════════
  // Public API
  // ════════════════════════════════════════════════════════════════════════════
  const start = useCallback(async (
    url: string,
    startBackend: () => Promise<void>,
  ) => {
    stop();
    setError(null);
    setState("connecting");
    activeRef.current  = true;
    camStopRef.current = false;
    lastFrameRef.current = 0;

    // Quick sanity check
    if (!url.trim()) {
      setError("Please enter a camera URL (e.g. http://192.168.1.8:4747/video)");
      setState("error");
      activeRef.current = false;
      return;
    }

    try {
      await startBackend();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start backend processing");
      setState("error");
      activeRef.current = false;
      return;
    }

    _connectWs(url);
  }, [stop, _connectWs]);

  return { state, error, start, stop };
}
