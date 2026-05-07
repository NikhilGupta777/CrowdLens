import { useEffect, useMemo, useState } from "react";
import { Anomaly } from "./useSimulation";

interface StickyAnomaly {
  anomaly: Anomaly;
  expiresAt: number;
}

function anomalyKey(anomaly: Anomaly, index: number): string {
  if (anomaly.track_id !== undefined) return `${anomaly.type}:track:${anomaly.track_id}`;
  if (anomaly.track_ids?.length) return `${anomaly.type}:tracks:${anomaly.track_ids.join("-")}`;
  if (anomaly.zone_id) return `${anomaly.type}:zone:${anomaly.zone_id}`;
  if (anomaly.position) {
    const [x, y] = anomaly.position;
    return `${anomaly.type}:pos:${Math.round(x / 40)}:${Math.round(y / 40)}`;
  }
  return `${anomaly.type}:idx:${index}`;
}

export function useStickyAnomalies(anomalies: Anomaly[], holdMs = 8000): Anomaly[] {
  const [sticky, setSticky] = useState<Record<string, StickyAnomaly>>({});

  useEffect(() => {
    const now = Date.now();
    setSticky((prev) => {
      const next: Record<string, StickyAnomaly> = {};

      for (const [key, item] of Object.entries(prev)) {
        if (item.expiresAt > now) next[key] = item;
      }

      anomalies.forEach((anomaly, index) => {
        next[anomalyKey(anomaly, index)] = {
          anomaly,
          expiresAt: now + holdMs,
        };
      });

      return next;
    });
  }, [anomalies, holdMs]);

  useEffect(() => {
    const interval = window.setInterval(() => {
      const now = Date.now();
      setSticky((prev) => {
        const next = Object.fromEntries(
          Object.entries(prev).filter(([, item]) => item.expiresAt > now),
        );
        return Object.keys(next).length === Object.keys(prev).length ? prev : next;
      });
    }, 500);

    return () => window.clearInterval(interval);
  }, []);

  return useMemo(
    () => Object.values(sticky).sort((a, b) => b.expiresAt - a.expiresAt).map((item) => item.anomaly),
    [sticky],
  );
}
