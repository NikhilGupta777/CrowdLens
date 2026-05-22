import { useCallback, useEffect, useRef, useState } from "react";
import { Anomaly } from "./useSimulation";

type Permission = "default" | "granted" | "denied" | "unsupported";

const ANOMALY_LABELS: Record<string, string> = {
  running:           "🏃 Running detected",
  overcrowding:      "⚠️ Overcrowding alert",
  unattended_object: "🎒 Unattended object",
  fight_suspected:   "🚨 Fight suspected",
  fall_detected:     "🆘 Fall detected",
  restricted_zone:   "🚧 Restricted zone breach",
  loitering:         "🕐 Loitering detected",
};

export function useNotifications(anomalies: Anomaly[]) {
  const [permission, setPermission] = useState<Permission>(() => {
    if (typeof Notification === "undefined") return "unsupported";
    return Notification.permission as Permission;
  });

  const [enabled, setEnabled] = useState(false);
  const lastFiredRef = useRef<Set<string>>(new Set());

  const requestPermission = useCallback(async () => {
    if (typeof Notification === "undefined") return;
    if (Notification.permission === "granted") {
      setEnabled(v => !v);
      return;
    }
    const result = await Notification.requestPermission();
    setPermission(result as Permission);
    if (result === "granted") setEnabled(true);
  }, []);

  useEffect(() => {
    if (!enabled || permission !== "granted") return;
    if (anomalies.length === 0) return;

    for (const a of anomalies) {
      const key = `${a.type}-${a.track_id ?? ""}`;
      if (lastFiredRef.current.has(key)) continue;
      lastFiredRef.current.add(key);

      const title = ANOMALY_LABELS[a.type] ?? "⚠️ Security Alert";
      const body = [
        a.track_id !== undefined ? `Track #${a.track_id}` : null,
        a.count !== undefined ? `${a.count} people` : null,
        a.zone_name ? `Zone: ${a.zone_name}` : null,
      ].filter(Boolean).join(" · ") || "Anomaly detected on campus feed";

      try {
        new Notification(title, { body, icon: "/favicon.ico", silent: false });
      } catch {}
    }
  }, [anomalies, enabled, permission]);

  useEffect(() => {
    if (lastFiredRef.current.size > 200) {
      // Prevent unbounded growth: keep only keys from current anomalies
      const currentKeys = new Set(anomalies.map((a) => `${a.type}-${a.track_id ?? ""}`));
      lastFiredRef.current = currentKeys;
    }
  }, [anomalies]);

  return { permission, enabled, requestPermission };
}
