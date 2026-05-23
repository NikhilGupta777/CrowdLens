import { Route, Switch } from "wouter";
import { DetectionProvider, useDetection } from "./context/DetectionContext";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import AlertHistory from "./pages/AlertHistory";
import Settings from "./pages/Settings";
import AIPanel from "./pages/AIPanel";
import { useStickyAnomalies } from "./hooks/useStickyAnomalies";

// Informational detections (faces, plates) are logged for review but are not
// threats, so they must not raise the security banner.
const INFO_ANOMALY_TYPES = ["face_detected", "lpr_detected"];
const CRITICAL_ANOMALY_TYPES = [
  "running", "unattended_object", "fight_suspected",
  "fall_detected", "restricted_zone", "ppe_violation",
];

function getThreatLevel(types: string[]): "secure" | "warning" | "critical" {
  const significant = types.filter((t) => !INFO_ANOMALY_TYPES.includes(t));
  if (significant.length === 0) return "secure";
  if (significant.some((t) => CRITICAL_ANOMALY_TYPES.includes(t))) return "critical";
  return "warning";
}

function AppShell() {
  const { frame, connected } = useDetection();
  // No explicit holdMs argument -> use the per-type table from useStickyAnomalies
  // (12s for fall/fight, 10s for restricted/unattended, 8s loitering, 6s
  // running/overcrowding). Critical events stay visible long enough for the
  // operator to react; transient events don't pile up in the feed.
  const stickyAnomalies = useStickyAnomalies(frame?.anomalies ?? []);
  const anomalyTypes = stickyAnomalies.map((a) => a.type);
  const threatLevel = getThreatLevel(anomalyTypes);

  return (
    <Layout connected={connected} threatLevel={threatLevel}>
      <Switch>
        <Route path="/" component={Dashboard} />
        <Route path="/history" component={AlertHistory} />
        <Route path="/ai" component={AIPanel} />
        <Route path="/settings" component={Settings} />
        <Route>
          <div style={{ color: "#64748b", padding: 40 }}>Page not found</div>
        </Route>
      </Switch>
    </Layout>
  );
}

export default function App() {
  return (
    <DetectionProvider>
      <AppShell />
    </DetectionProvider>
  );
}
