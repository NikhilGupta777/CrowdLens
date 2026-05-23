import { useEffect, useMemo, useRef, useState } from "react";
import { Anomaly } from "./useSimulation";

interface StickyAnomaly {
  anomaly: Anomaly;
  expiresAt: number;
}

/**
 * Per-anomaly-type sticky-hold durations. Critical events stay visible
 * longer because operators need to react; transient events expire faster
 * to avoid cluttering the feed when the underlying behaviour stops.
 *
 * If a holdMs override is passed to the hook, it is used as the default
 * for unknown types only; known types still use these per-type values.
 */
const DEFAULT_HOLD_MS_BY_TYPE: Record<string, number> = {
  fall_detected:     12000,
  fight_suspected:   12000,
  restricted_zone:   10000,
  unattended_object: 10000,
  loitering:          8000,
  running:            6000,
  overcrowding:       6000,
};

const FALLBACK_HOLD_MS = 8000;

/**
 * Generate a stable deduplication key for an anomaly.
 *
 * Strategy by type:
 * - running / restricted_zone / loitering: keyed by track_id (one per person)
 * - fight_suspected: keyed by sorted track pair
 * - unattended_object: keyed by track_id (the object's tracker ID)
 * - fall_detected: keyed by bbox grid cell (fall has no stable track_id)
 * - overcrowding: keyed by cluster centroid grid cell so multiple distinct
 *   crowds (now that backend emits one alert per cluster) do not collapse
 *   into a single sticky entry.
 */
function anomalyKey(anomaly: Anomaly): string {
  const t = anomaly.type;

  // Types that are always per-track, except restricted_zone which must
  // also include zone_id — one person can be inside two overlapping zones
  // simultaneously, and they should appear as two distinct sticky cards
  // rather than collapsing onto a single track-level entry.
  if (t === "restricted_zone" && anomaly.track_id != null) {
    const zone = anomaly.zone_id ?? "unknown";
    return `${t}:${anomaly.track_id}:${zone}`;
  }
  if (
    (t === "running" || t === "loitering" || t === "unattended_object") &&
    anomaly.track_id != null
  ) {
    return `${t}:${anomaly.track_id}`;
  }

  // Fight: keyed by the pair of track IDs (sorted for stability)
  if (t === "fight_suspected" && anomaly.track_ids?.length) {
    const sorted = [...anomaly.track_ids].sort((a, b) => a - b);
    return `${t}:${sorted.join("-")}`;
  }

  // Overcrowding: backend emits one alert per cluster, so key by cluster
  // centroid (96 px grid) so two distinct crowds get two sticky cards.
  if (t === "overcrowding") {
    if (anomaly.position) {
      const [x, y] = anomaly.position;
      return `${t}:${Math.round(x / 96)}:${Math.round(y / 96)}`;
    }
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


export function useStickyAnomalies(
  anomalies: Anomaly[],
  holdMsOverrideOrDefault?: number | Record<string, number>,
): Anomaly[] {
  const [sticky, setSticky] = useState<Record<string, StickyAnomaly>>({});
  // Track the latest anomalies ref to avoid stale closure in interval
  const latestAnomaliesRef = useRef(anomalies);
  latestAnomaliesRef.current = anomalies;

  // Resolve effective hold-by-type: per-type table merges with optional override.
  const holdByType: Record<string, number> = (() => {
    if (!holdMsOverrideOrDefault) return DEFAULT_HOLD_MS_BY_TYPE;
    if (typeof holdMsOverrideOrDefault === "number") {
      // Numeric override is treated as a uniform default for ALL types
      // (preserves backwards-compat with the previous holdMs API).
      return Object.fromEntries(
        Object.keys(DEFAULT_HOLD_MS_BY_TYPE).map((t) => [t, holdMsOverrideOrDefault]),
      );
    }
    return { ...DEFAULT_HOLD_MS_BY_TYPE, ...holdMsOverrideOrDefault };
  })();
  const fallbackHold =
    typeof holdMsOverrideOrDefault === "number"
      ? holdMsOverrideOrDefault
      : FALLBACK_HOLD_MS;

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
        const hold = holdByType[anomaly.type] ?? fallbackHold;
        next[key] = {
          anomaly,  // always use latest data (updated duration, position, etc.)
          expiresAt: now + hold,
        };
      }

      return next;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [anomalies]);

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
