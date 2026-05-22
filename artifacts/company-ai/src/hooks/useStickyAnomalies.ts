import { useEffect, useMemo, useRef, useState } from "react";
import { Anomaly } from "./useSimulation";

interface StickyAnomaly {
  anomaly: Anomaly;
  expiresAt: number;
}

/**
 * Generate a stable deduplication key for an anomaly.
 *
 * Strategy by type:
 * - running / restricted_zone / loitering: keyed by track_id (one per person)
 * - fight_suspected: keyed by sorted track pair
 * - unattended_object: keyed by track_id (the object's tracker ID)
 * - fall_detected: keyed by bbox grid cell (fall has no stable track_id)
 * - overcrowding: singleton key (only one overcrowding alert at a time)
 */
function anomalyKey(anomaly: Anomaly): string {
  const t = anomaly.type;

  // Types that are always per-track
  if (
    (t === "running" || t === "restricted_zone" || t === "loitering" || t === "unattended_object") &&
    anomaly.track_id != null
  ) {
    return `${t}:${anomaly.track_id}`;
  }

  // Fight: keyed by the pair of track IDs (sorted for stability)
  if (t === "fight_suspected" && anomaly.track_ids?.length) {
    const sorted = [...anomaly.track_ids].sort((a, b) => a - b);
    return `${t}:${sorted.join("-")}`;
  }

  // Overcrowding: only one active at a time globally
  if (t === "overcrowding") {
    return "overcrowding";
  }

  // Fall: use coarser position grid (64px cells) since fall bbox shifts
  if (t === "fall_detected" && anomaly.position) {
    const [x, y] = anomaly.position;
    return `${t}:${Math.round(x / 64)}:${Math.round(y / 64)}`;
  }

  // Zone-based fallback
  if (anomaly.zone_id) {
    return `${t}:zone:${anomaly.zone_id}`;
  }

  // Position fallback with finer grid (24px)
  if (anomaly.position) {
    const [x, y] = anomaly.position;
    return `${t}:pos:${Math.round(x / 24)}:${Math.round(y / 24)}`;
  }

  // Last resort: type-only (prevents index-based duplicates)
  return `${t}:singleton`;
}


export function useStickyAnomalies(anomalies: Anomaly[], holdMs = 8000): Anomaly[] {
  const [sticky, setSticky] = useState<Record<string, StickyAnomaly>>({});
  // Track the latest anomalies ref to avoid stale closure in interval
  const latestAnomaliesRef = useRef(anomalies);
  latestAnomaliesRef.current = anomalies;

  // Update sticky map when new anomalies arrive
  useEffect(() => {
    if (!anomalies || anomalies.length === 0) return;
    const now = Date.now();
    setSticky((prev) => {
      const next: Record<string, StickyAnomaly> = {};

      // Keep unexpired entries
      for (const [key, item] of Object.entries(prev)) {
        if (item.expiresAt > now) {
          next[key] = item;
        }
      }

      // Upsert current frame's anomalies (extends expiry if already exists)
      for (const anomaly of anomalies) {
        const key = anomalyKey(anomaly);
        next[key] = {
          anomaly,  // always use latest data (updated duration, position, etc.)
          expiresAt: now + holdMs,
        };
      }

      return next;
    });
  }, [anomalies, holdMs]);

  // Periodic cleanup of expired entries
  useEffect(() => {
    const interval = window.setInterval(() => {
      const now = Date.now();
      setSticky((prev) => {
        let changed = false;
        const next: Record<string, StickyAnomaly> = {};
        for (const [key, item] of Object.entries(prev)) {
          if (item.expiresAt > now) {
            next[key] = item;
          } else {
            changed = true;
          }
        }
        return changed ? next : prev;
      });
    }, 500);

    return () => window.clearInterval(interval);
  }, []);

  // Return sorted by most recent first
  return useMemo(
    () =>
      Object.values(sticky)
        .sort((a, b) => b.expiresAt - a.expiresAt)
        .map((item) => item.anomaly),
    [sticky],
  );
}
