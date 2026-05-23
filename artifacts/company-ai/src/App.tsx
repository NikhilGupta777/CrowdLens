import { Route, Switch } from "wouter";
import { DetectionProvider, useDetection } from "./context/DetectionContext";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import AlertHistory from "./pages/AlertHistory";
import Settings from "./pages/Settings";
import AIPanel from "./pages/AIPanel";
import { useStickyAnomalies } from "./hooks/useStickyAnomalies";

function getThreatLevel(anomalyCount: number, types: string[]): "secure" | "warning" | "critical" {
  if (anomalyCount === 0) return "secure";
  if (
    types.includes("running")
    || types.includes("unattended_object")
    || types.includes("fight_suspected")
    || types.includes("fall_detected")
    || types.includes("restricted_zone")
  ) return "critical";
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
  const threatLevel = getThreatLevel(stickyAnomalies.length, anomalyTypes);

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
