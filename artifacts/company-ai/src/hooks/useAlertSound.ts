import { useEffect, useRef } from "react";
import { Anomaly } from "./useSimulation";

function playTone(
  ctx: AudioContext,
  freq: number,
  duration: number,
  vol: number,
  delayMs = 0
) {
  try {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.type = "square";
    osc.frequency.value = freq;
    const start = ctx.currentTime + delayMs / 1000;
    gain.gain.setValueAtTime(vol, start);
    gain.gain.exponentialRampToValueAtTime(0.001, start + duration);
    osc.start(start);
    osc.stop(start + duration + 0.05);
  } catch {
    // AudioContext may be suspended; play() called below will resume it
  }
}

const COOLDOWN_MS = 2000;

export function useAlertSound(anomalies: Anomaly[], enabled = true) {
  const ctxRef = useRef<AudioContext | null>(null);
  const lastTypeSetRef = useRef<Set<string>>(new Set());
  const lastPlayedRef = useRef<Record<string, number>>({});

  // Resume AudioContext on any user interaction (browser autoplay policy)
  useEffect(() => {
    const resume = () => {
      if (ctxRef.current && ctxRef.current.state === "suspended") {
        ctxRef.current.resume();
      }
    };
    document.addEventListener("click", resume, { once: false });
    document.addEventListener("keydown", resume, { once: false });
    return () => {
      document.removeEventListener("click", resume);
      document.removeEventListener("keydown", resume);
    };
  }, []);

  useEffect(() => {
    if (!enabled) return;

    const currentTypes = new Set(anomalies.map((a) => a.type));
    const now = Date.now();

    for (const type of currentTypes) {
      const alreadyActive = lastTypeSetRef.current.has(type);
      const lastPlayed = lastPlayedRef.current[type] ?? 0;
      const cooledDown = now - lastPlayed > COOLDOWN_MS;

      if (!alreadyActive && cooledDown) {
        // Lazy-create AudioContext on first alert (requires user gesture first)
        if (!ctxRef.current) {
          try {
            ctxRef.current = new (window.AudioContext ||
              (window as any).webkitAudioContext)();
          } catch {
            // AudioContext not supported
          }
        }
        const ctx = ctxRef.current;
        if (!ctx) continue;

        // Resume if suspended (browser policy)
        if (ctx.state === "suspended") {
          ctx.resume().catch(() => {});
        }

        if (type === "running") {
          playTone(ctx, 1000, 0.2, 0.25, 0);
          playTone(ctx, 1200, 0.15, 0.2, 260);
        } else if (type === "fight_suspected") {
          playTone(ctx, 1100, 0.18, 0.28, 0);
          playTone(ctx, 900, 0.18, 0.24, 220);
          playTone(ctx, 1300, 0.16, 0.2, 440);
        } else if (type === "unattended_object") {
          playTone(ctx, 800, 0.3, 0.25, 0);
        } else if (type === "overcrowding") {
          playTone(ctx, 600, 0.4, 0.15, 0);
        } else if (type === "fall_detected") {
          playTone(ctx, 720, 0.3, 0.22, 0);
          playTone(ctx, 520, 0.25, 0.18, 300);
        } else if (type === "restricted_zone") {
          playTone(ctx, 950, 0.22, 0.2, 0);
        } else if (type === "loitering") {
          playTone(ctx, 550, 0.35, 0.15, 0);
          playTone(ctx, 650, 0.25, 0.12, 400);
        } else if (type === "ppe_violation") {
          playTone(ctx, 880, 0.22, 0.22, 0);
          playTone(ctx, 660, 0.2, 0.18, 240);
        }
        // face_detected / lpr_detected are informational — intentionally silent.

        lastPlayedRef.current[type] = now;
      }
    }

    lastTypeSetRef.current = currentTypes;
  }, [anomalies, enabled]);
}
