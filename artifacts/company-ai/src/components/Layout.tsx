import { ReactNode, useEffect, useState } from "react";
import { Link, useRoute } from "wouter";
import {
  LayoutDashboard, History, Settings, Wifi, WifiOff,
  Shield, ShieldAlert, ShieldX, Activity, Bot, Menu, X, Moon, Sun, Aperture,
} from "lucide-react";
import { useIsMobile } from "../hooks/use-mobile";
import { useTheme } from "../hooks/useTheme";

interface Props {
  children: ReactNode;
  connected: boolean;
  threatLevel: "secure" | "warning" | "critical";
}

const navItems = [
  { path: "/", label: "Live Dashboard", icon: LayoutDashboard, exact: true },
  { path: "/history", label: "Alert History", icon: History, exact: false },
  { path: "/ai", label: "AI Assistant", icon: Bot, exact: false },
  { path: "/settings", label: "Settings", icon: Settings, exact: false },
];

function NavIcon({ path, label, icon: Icon, exact, onClick }: (typeof navItems)[0] & { onClick?: () => void }) {
  const [active] = useRoute(exact ? path : `${path}*`);
  return (
    <Link href={path} onClick={onClick}>
      <button
        title={label}
        style={{
          width: 56,
          height: 56,
          borderRadius: 14,
          border: "none",
          background: active ? "#34312f" : "transparent",
          color: active ? "#f7f7f5" : "#8a8580",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          cursor: "pointer",
          boxShadow: active ? "0 8px 22px rgba(0,0,0,0.22)" : "none",
          borderLeft: active ? "3px solid #0f8f83" : "3px solid transparent",
          transition: "all 0.2s ease",
        }}
      >
        <Icon size={23} />
      </button>
    </Link>
  );
}

function Clock() {
  const [time, setTime] = useState(new Date());
  useEffect(() => {
    const t = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  return (
    <span style={{ fontVariantNumeric: "tabular-nums" }}>
      {time.toLocaleString(undefined, {
        weekday: "short", month: "short", day: "numeric",
        hour: "2-digit", minute: "2-digit",
      })}
    </span>
  );
}

function RailContent({ connected, onNavClick }: { connected: boolean; onNavClick?: () => void }) {
  return (
    <>
      <div
        style={{
          width: 56,
          height: 56,
          borderRadius: 16,
          background: "linear-gradient(135deg, #0ea5a3, #0f766e)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "#ffffff",
          fontWeight: 800,
          fontSize: 24,
          letterSpacing: 1,
          boxShadow: "0 8px 26px rgba(20,184,166,0.28)",
          marginBottom: 24,
        }}
      >
        <Aperture size={27} strokeWidth={2.3} />
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 10, alignItems: "center", flex: 1 }}>
        {navItems.map((item) => <NavIcon key={item.path} {...item} onClick={onNavClick} />)}
      </div>

      <div
        style={{
          width: 56,
          borderRadius: 14,
          border: "1px solid rgba(255,255,255,0.10)",
          background: "rgba(255,255,255,0.03)",
          padding: "10px 0",
          display: "flex",
          justifyContent: "center",
          marginBottom: 8,
        }}
        title={connected ? "Engine connected" : "Engine reconnecting"}
      >
        {connected ? <Wifi size={20} color="#10b981" /> : <WifiOff size={20} color="#64748b" />}
      </div>

      <div
        style={{
          width: 10,
          height: 10,
          borderRadius: "50%",
          background: connected ? "#4ade80" : "#64748b",
          boxShadow: connected ? "0 0 10px #22c55e" : "none",
        }}
      />
    </>
  );
}

export default function Layout({ children, connected, threatLevel }: Props) {
  const isMobile = useIsMobile();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const { theme, toggleTheme } = useTheme();

  useEffect(() => {
    if (!isMobile) setDrawerOpen(false);
  }, [isMobile]);

  const threatConfig = {
    secure: { color: "#16a34a", text: "System Secure", Icon: Shield, glow: "#16a34a" },
    warning: { color: "#ea580c", text: "Alert Active", Icon: ShieldAlert, glow: "#ea580c" },
    critical: { color: "#dc2626", text: "Threat Detected", Icon: ShieldX, glow: "#dc2626" },
  }[threatLevel];

  return (
    <div style={{ display: "flex", minHeight: "100vh", background: "var(--app-bg)", color: "var(--app-text)" }}>
      {!isMobile && (
        <aside
          style={{
            width: 96,
            minWidth: 96,
            background: "var(--app-sidebar-bg)",
            borderRight: "1px solid rgba(255,255,255,0.08)",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            padding: "28px 0 24px",
            position: "fixed",
            top: 0,
            left: 0,
            height: "100vh",
            zIndex: 100,
          }}
        >
          <RailContent connected={connected} />
        </aside>
      )}

      {isMobile && drawerOpen && (
        <div
          onClick={() => setDrawerOpen(false)}
          style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", zIndex: 200, backdropFilter: "blur(2px)" }}
        />
      )}

      {isMobile && (
        <aside
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            width: 96,
            height: "100vh",
            background: "var(--app-sidebar-bg)",
            borderRight: "1px solid rgba(255,255,255,0.08)",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            padding: "28px 0 24px",
            zIndex: 300,
            transform: drawerOpen ? "translateX(0)" : "translateX(-100%)",
            transition: "transform 0.25s ease",
          }}
        >
          <button
            onClick={() => setDrawerOpen(false)}
            style={{ position: "absolute", top: 8, right: 8, background: "none", border: "none", color: "#94a3b8", cursor: "pointer" }}
          >
            <X size={16} />
          </button>
          <RailContent connected={connected} onNavClick={() => setDrawerOpen(false)} />
        </aside>
      )}

      <div
        style={{
          marginLeft: isMobile ? 0 : 96,
          flex: 1,
          display: "flex",
          flexDirection: "column",
          minHeight: "100vh",
        }}
      >
        <header
          style={{
            background: "var(--app-card-bg)",
            borderBottom: "1px solid var(--app-card-border)",
            padding: isMobile ? "0 14px" : "0 46px",
            height: 84,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            position: "sticky",
            top: 0,
            zIndex: 50,
            gap: 12,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            {isMobile && (
              <button
                onClick={() => setDrawerOpen(true)}
                style={{ background: "none", border: "none", color: "var(--app-text-muted)", cursor: "pointer", padding: 2 }}
              >
                <Menu size={20} />
              </button>
            )}
            <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
              <div style={{ fontSize: 22, fontWeight: 800, lineHeight: 1, letterSpacing: 0 }}>
                CROWDLENS
              </div>
              <div style={{ width: 1, height: 26, background: "var(--app-card-border)" }} />
              <div style={{ fontSize: 14, color: "var(--app-text-muted)" }}>Campus AI Monitor</div>
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: isMobile ? 8 : 14 }}>
            <button
              onClick={toggleTheme}
              title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                width: 36,
                height: 36,
                borderRadius: 10,
                border: "1px solid var(--app-card-border)",
                background: "transparent",
                color: "var(--app-text-muted)",
                cursor: "pointer",
              }}
            >
              {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
            </button>

            {!isMobile && (
              <>
                <div style={{ fontSize: 14, color: "var(--app-text-muted)", fontVariantNumeric: "tabular-nums" }}>
                  <Clock />
                </div>
                <div style={{ width: 1, height: 24, background: "var(--app-card-border)" }} />
                <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                  <Activity size={16} color="var(--app-text-muted)" />
                  <span style={{ fontSize: 13, color: "var(--app-text-muted)" }}>Detection Engine</span>
                </div>
                <div style={{ width: 1, height: 24, background: "var(--app-card-border)" }} />
              </>
            )}

            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                border: `1px solid ${threatConfig.color}40`,
                borderRadius: 17,
                padding: "7px 22px",
                background: `${threatConfig.color}10`,
              }}
            >
              <div style={{ width: 10, height: 10, borderRadius: "50%", background: threatConfig.color }} />
              <span style={{ fontSize: 14, fontWeight: 700, color: threatConfig.color }}>{threatConfig.text}</span>
            </div>
          </div>
        </header>

        <main style={{ flex: 1, padding: isMobile ? "18px 14px" : "40px 46px 34px", background: "var(--app-bg)" }}>
          {children}
        </main>
      </div>
    </div>
  );
}
