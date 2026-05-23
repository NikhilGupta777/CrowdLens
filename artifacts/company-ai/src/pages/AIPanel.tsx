import { CSSProperties, useEffect, useRef, useState } from "react";
import {
  Bot, Brain, FileText, MessageSquare, Mic2, Send, Sparkles,
  AlertCircle, Loader2, ChevronDown, ChevronUp, RefreshCw, Zap,
  ShieldAlert, Users, UserRoundX, Package, Camera,
} from "lucide-react";
import { useDetection } from "../context/DetectionContext";
import { useIsMobile } from "../hooks/use-mobile";

import { AlertRecord } from "../types";

// ── types ───────────────────────────────────────────────────────────────────

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

// ── helpers ──────────────────────────────────────────────────────────────────

const TYPE_META: Record<string, { color: string; Icon: typeof Zap; label: string }> = {
  running:           { color: "#a855f7", Icon: Zap,          label: "Running" },
  fight_suspected:   { color: "#f43f5e", Icon: AlertCircle,  label: "Fight Suspected" },
  unattended_object: { color: "#ef4444", Icon: Package,      label: "Unattended Object" },
  overcrowding:      { color: "#f97316", Icon: Users,        label: "Overcrowding" },
  fall_detected:     { color: "#dc2626", Icon: UserRoundX,   label: "Fall Detected" },
  restricted_zone:   { color: "#eab308", Icon: ShieldAlert,  label: "Restricted Zone" },
  manual_snapshot:   { color: "#60a5fa", Icon: Camera,       label: "Manual Snapshot" },
};

const card: CSSProperties = {
  background: "var(--app-card-bg)",
  border: "1px solid var(--app-card-border)",
  borderRadius: 14,
  padding: "20px 24px",
};

function TabButton({
  active, onClick, icon: Icon, label,
}: { active: boolean; onClick: () => void; icon: typeof Bot; label: string }) {
  return (
    <button
      onClick={onClick}
      style={{
        display: "flex", alignItems: "center", gap: 8,
        padding: "10px 20px", borderRadius: 10, border: "none",
        cursor: "pointer", fontSize: 13, fontWeight: active ? 700 : 500,
        background: active
          ? "linear-gradient(90deg, rgba(99,102,241,0.25), rgba(59,130,246,0.15))"
          : "rgba(255,255,255,0.04)",
        color: active ? "#818cf8" : "var(--app-text-muted)",
        borderBottom: `2px solid ${active ? "#6366f1" : "transparent"}`,
        transition: "all 0.18s",
      }}
    >
      <Icon size={15} />
      {label}
    </button>
  );
}

// ── persistence helpers ─────────────────────────────────────────────────────
//
// AI reports and chat history are persisted in localStorage so they survive
// navigation between tabs (Settings, Dashboard, etc.) and full page reloads.
// Without this, generating a 5-second incident report and then clicking
// "Settings" wiped the report from memory; the user had to regenerate
// (and re-pay the Gemini cost) just to read it again.
//
// Storage shape is wrapped with `v: 1` so a future schema change can
// detect old payloads and migrate cleanly. Reports keyed by alert.id;
// chat is one rolling list.
const REPORTS_STORAGE_KEY = "crowdlens_ai_reports";
const CHAT_STORAGE_KEY = "crowdlens_ai_chat";
const REPORTS_RETENTION = 200;     // cap stored reports to keep localStorage small
const CHAT_RETENTION = 100;        // cap stored chat messages

interface ReportsBlob { v: 1; reports: Record<number, string> }
interface ChatBlob    { v: 1; messages: ChatMessage[] }

function loadReports(): Record<number, string> {
  try {
    const raw = localStorage.getItem(REPORTS_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as ReportsBlob | Record<number, string>;
    // Backwards compat: pre-versioning blob was a flat record.
    if (parsed && typeof parsed === "object" && "v" in parsed && parsed.v === 1) {
      return parsed.reports ?? {};
    }
    if (parsed && typeof parsed === "object") {
      return parsed as Record<number, string>;
    }
  } catch {
    // Corrupt JSON — drop and start fresh
  }
  return {};
}

function saveReports(reports: Record<number, string>) {
  try {
    // Trim to retention cap before saving (oldest by alert id removed).
    const ids = Object.keys(reports).map(Number).sort((a, b) => b - a);
    const trimmed: Record<number, string> = {};
    for (const id of ids.slice(0, REPORTS_RETENTION)) {
      trimmed[id] = reports[id];
    }
    const blob: ReportsBlob = { v: 1, reports: trimmed };
    localStorage.setItem(REPORTS_STORAGE_KEY, JSON.stringify(blob));
  } catch {
    // QuotaExceededError or storage disabled — silently skip persistence
  }
}

function loadChat(): ChatMessage[] {
  try {
    const raw = localStorage.getItem(CHAT_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as ChatBlob | ChatMessage[];
    if (Array.isArray(parsed)) return parsed; // legacy flat array
    if (parsed && typeof parsed === "object" && "v" in parsed && parsed.v === 1) {
      return parsed.messages ?? [];
    }
  } catch {
    // Corrupt JSON
  }
  return [];
}

function saveChat(messages: ChatMessage[]) {
  try {
    const trimmed = messages.slice(-CHAT_RETENTION);
    const blob: ChatBlob = { v: 1, messages: trimmed };
    localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(blob));
  } catch {
    // ignore
  }
}

// ── REPORTS TAB ──────────────────────────────────────────────────────────────

function ReportsTab() {
  const [alerts, setAlerts] = useState<AlertRecord[]>([]);
  const [loading, setLoading] = useState(true);
  // Hydrate from localStorage so reports survive tab navigation + reloads.
  // The backend doesn't store reports — they live only in the browser.
  const [reports, setReports] = useState<Record<number, string>>(() => loadReports());
  const [generating, setGenerating] = useState<Record<number, boolean>>({});
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});

  // Persist whenever reports map changes
  useEffect(() => {
    saveReports(reports);
  }, [reports]);

  useEffect(() => {
    fetch("/api/alerts/history?limit=30")
      .then((r) => r.json())
      .then((d) => setAlerts(d.alerts || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const generateReport = async (alert: AlertRecord) => {
    setGenerating((p) => ({ ...p, [alert.id]: true }));
    try {
      const res = await fetch("/api/ai/report", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ alert }),
      });
      const data = await res.json();
      setReports((p) => ({ ...p, [alert.id]: data.report }));
      setExpanded((p) => ({ ...p, [alert.id]: true }));
    } catch {
      setReports((p) => ({ ...p, [alert.id]: "Failed to generate report. Please try again." }));
    } finally {
      setGenerating((p) => ({ ...p, [alert.id]: false }));
    }
  };

  if (loading) {
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 10, color: "#64748b", padding: 40 }}>
        <Loader2 size={16} style={{ animation: "spin 1s linear infinite" }} />
        Loading alert history…
      </div>
    );
  }

  if (alerts.length === 0) {
    return (
      <div style={{ ...card, textAlign: "center", padding: 48 }}>
        <Bot size={32} color="var(--app-text-muted)" style={{ marginBottom: 12 }} />
        <div style={{ color: "var(--app-text-muted)", fontSize: 14 }}>No alerts recorded yet.</div>
        <div style={{ color: "var(--app-text-muted)", fontSize: 12, marginTop: 6 }}>
          Start a detection session to generate incident reports.
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ fontSize: 12, color: "var(--app-text-muted)", marginBottom: 4 }}>
        {alerts.length} incidents available — click Generate to produce an AI incident report for any alert.
      </div>
      {alerts.map((alert) => {
        const meta = TYPE_META[alert.anomaly.type] ?? { color: "var(--app-text-muted)", Icon: AlertCircle, label: alert.anomaly.type };
        const { Icon } = meta;
        const report = reports[alert.id];
        const isGenerating = generating[alert.id];
        const isExpanded = expanded[alert.id];

        return (
          <div key={alert.id} style={{ ...card, padding: "16px 20px", borderLeft: `3px solid ${meta.color}` }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <div style={{ background: `${meta.color}18`, borderRadius: 8, padding: 6 }}>
                  <Icon size={14} color={meta.color} />
                </div>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 700, color: meta.color }}>{meta.label}</div>
                  <div style={{ fontSize: 11, color: "var(--app-text-muted)", marginTop: 2, fontFamily: "monospace" }}>
                    {new Date(alert.timestamp * 1000).toLocaleString(undefined)}
                    {alert.anomaly.track_id !== undefined && ` · Track #${alert.anomaly.track_id}`}
                    {alert.anomaly.count !== undefined && ` · ${alert.anomaly.count} people`}
                    {alert.source && ` · ${alert.source.toUpperCase()}`}
                  </div>
                </div>
              </div>

              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                {report && (
                  <button
                    onClick={() => setExpanded((p) => ({ ...p, [alert.id]: !isExpanded }))}
                    style={{
                      display: "flex", alignItems: "center", gap: 4,
                      padding: "5px 12px", borderRadius: 8, border: "1px solid rgba(255,255,255,0.1)",
                      background: "transparent", color: "var(--app-text-muted)", cursor: "pointer", fontSize: 11,
                    }}
                  >
                    {isExpanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                    {isExpanded ? "Collapse" : "View"}
                  </button>
                )}
                <button
                  onClick={() => generateReport(alert)}
                  disabled={isGenerating}
                  style={{
                    display: "flex", alignItems: "center", gap: 6,
                    padding: "6px 14px", borderRadius: 8,
                    border: "1px solid rgba(99,102,241,0.4)",
                    background: isGenerating ? "rgba(99,102,241,0.06)" : "rgba(99,102,241,0.12)",
                    color: isGenerating ? "var(--app-text-muted)" : "#818cf8",
                    cursor: isGenerating ? "default" : "pointer", fontSize: 12, fontWeight: 600,
                  }}
                >
                  {isGenerating
                    ? <><Loader2 size={12} style={{ animation: "spin 1s linear infinite" }} /> Generating…</>
                    : <><Sparkles size={12} /> {report ? "Regenerate" : "Generate Report"}</>}
                </button>
              </div>
            </div>

            {report && isExpanded && (
              <div style={{
                marginTop: 16,
                background: "rgba(99,102,241,0.05)",
                border: "1px solid rgba(99,102,241,0.15)",
                borderRadius: 10,
                padding: "16px 18px",
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 10 }}>
                  <FileText size={13} color="#818cf8" />
                  <span style={{ fontSize: 10, color: "#818cf8", fontWeight: 700, letterSpacing: 1.5 }}>AI INCIDENT REPORT</span>
                </div>
                <pre style={{
                  fontFamily: "inherit", fontSize: 13, color: "var(--app-text)",
                  lineHeight: 1.7, whiteSpace: "pre-wrap", margin: 0,
                }}>
                  {report}
                </pre>
                {alert.snapshot_url && (
                  <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid rgba(255,255,255,0.06)" }}>
                    <a href={alert.snapshot_url} target="_blank" rel="noreferrer">
                      <img
                        src={alert.snapshot_url}
                        alt="Incident snapshot"
                        style={{ height: 72, borderRadius: 6, border: "1px solid rgba(255,255,255,0.1)", cursor: "pointer" }}
                      />
                    </a>
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── CHAT TAB ─────────────────────────────────────────────────────────────────

function ChatTab() {
  // Hydrate from localStorage so chat history survives navigation + reload.
  const [messages, setMessages] = useState<ChatMessage[]>(() => loadChat());
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [alertHistory, setAlertHistory] = useState<AlertRecord[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Persist messages whenever they change. Saved blob is capped at the
  // last CHAT_RETENTION items to keep localStorage size bounded.
  useEffect(() => {
    saveChat(messages);
  }, [messages]);

  useEffect(() => {
    const fetchHistory = () => {
      if (document.visibilityState !== "visible") return;
      fetch("/api/alerts/history?limit=50")
        .then((r) => r.json())
        .then((d) => setAlertHistory(d.alerts || []))
        .catch(() => {});
    };
    fetchHistory();
    const id = setInterval(fetchHistory, 15000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = async () => {
    const text = input.trim();
    if (!text || streaming) return;
    setInput("");

    const userMsg: ChatMessage = { role: "user", content: text };
    setMessages((p) => [...p, userMsg]);
    setStreaming(true);

    const assistantMsg: ChatMessage = { role: "assistant", content: "" };
    setMessages((p) => [...p, assistantMsg]);

    try {
      const allMessages = [...messages, userMsg];
      const recentMessages = allMessages.slice(-30);
      const res = await fetch("/api/ai/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: recentMessages.map((m) => ({ role: m.role, content: m.content })),
          alert_history: alertHistory,
        }),
      });

      const reader = res.body?.getReader();
      const decoder = new TextDecoder();
      if (!reader) throw new Error("No stream");

      let lineBuf = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        lineBuf += decoder.decode(value, { stream: true });
        const lines = lineBuf.split("\n");
        // Keep the last element — it may be an incomplete line
        lineBuf = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const payload = JSON.parse(line.slice(6));
            if (payload.done) break;
            if (payload.error) throw new Error(payload.error);
            if (payload.content) {
              setMessages((p) => {
                const updated = [...p];
                updated[updated.length - 1] = {
                  ...updated[updated.length - 1],
                  content: updated[updated.length - 1].content + payload.content,
                };
                return updated;
              });
            }
          } catch (parseErr) {
            // Skip malformed lines — may be partial chunk
            if (parseErr instanceof SyntaxError) continue;
            throw parseErr;
          }
        }
      }
    } catch (err) {
      setMessages((p) => {
        const updated = [...p];
        updated[updated.length - 1] = { ...updated[updated.length - 1], content: "Error: could not get response." };
        return updated;
      });
    } finally {
      setStreaming(false);
    }
  };

  const suggestions = [
    "How many anomalies were detected today?",
    "Which track ID appeared in the most alerts?",
    "Summarise all restricted zone breaches",
    "Were any fights or running incidents detected?",
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "calc(100vh - 320px)", minHeight: 480 }}>
      {/* Messages */}
      <div style={{
        flex: 1, overflowY: "auto", padding: "16px 0", display: "flex", flexDirection: "column", gap: 12,
      }}>
        {messages.length === 0 && (
          <div style={{ padding: "24px 0" }}>
            <div style={{ ...card, marginBottom: 16, textAlign: "center", padding: "24px 20px" }}>
              <Brain size={28} color="#6366f1" style={{ marginBottom: 10 }} />
              <div style={{ fontSize: 14, color: "var(--app-text)", fontWeight: 600, marginBottom: 6 }}>
                AI Alert Assistant
              </div>
              <div style={{ fontSize: 12, color: "var(--app-text-muted)" }}>
                Ask anything about your alert history. The AI has access to your last 50 events.
              </div>
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {suggestions.map((s) => (
                <button
                  key={s}
                  onClick={() => setInput(s)}
                  style={{
                    padding: "8px 14px", borderRadius: 20, fontSize: 12,
                    border: "1px solid rgba(99,102,241,0.25)",
                    background: "rgba(99,102,241,0.06)",
                    color: "#64748b", cursor: "pointer",
                  }}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <div
            key={i}
            style={{
              display: "flex",
              justifyContent: msg.role === "user" ? "flex-end" : "flex-start",
            }}
          >
            <div
              style={{
                maxWidth: "78%",
                padding: "12px 16px",
                borderRadius: msg.role === "user" ? "14px 14px 4px 14px" : "14px 14px 14px 4px",
                background: msg.role === "user"
                  ? "linear-gradient(135deg, #3b82f6, #6366f1)"
                  : "rgba(255,255,255,0.04)",
                border: msg.role === "assistant" ? "1px solid rgba(255,255,255,0.07)" : "none",
                color: msg.role === "user" ? "#fff" : "var(--app-text)",
                fontSize: 13,
                lineHeight: 1.65,
                whiteSpace: "pre-wrap",
              }}
            >
              {msg.content}
              {msg.role === "assistant" && streaming && i === messages.length - 1 && (
                <span style={{
                  display: "inline-block", width: 8, height: 14,
                  background: "#6366f1", marginLeft: 2, borderRadius: 2,
                  animation: "blink-cursor 0.8s infinite",
                }} />
              )}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div style={{
        borderTop: "1px solid rgba(255,255,255,0.06)",
        paddingTop: 16, display: "flex", gap: 10, alignItems: "flex-end",
      }}>
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); } }}
          placeholder="Ask about your alerts… (Enter to send)"
          rows={2}
          style={{
            flex: 1, padding: "12px 16px", borderRadius: 12, resize: "none",
            border: "1px solid rgba(255,255,255,0.1)",
            background: "rgba(255,255,255,0.04)",
            color: "var(--app-text)", fontSize: 13, fontFamily: "inherit",
            outline: "none",
          }}
        />
        {messages.length > 0 && !streaming && (
          <button
            onClick={() => {
              if (confirm("Clear all chat history? This cannot be undone.")) {
                setMessages([]);
              }
            }}
            title="Clear chat history"
            style={{
              padding: "12px 14px", borderRadius: 12, border: "1px solid rgba(239,68,68,0.3)",
              background: "rgba(239,68,68,0.08)", color: "#ef4444",
              cursor: "pointer", fontSize: 12, fontWeight: 600,
            }}
          >
            Clear
          </button>
        )}
        <button
          onClick={sendMessage}
          disabled={!input.trim() || streaming}
          style={{
            padding: "12px 18px", borderRadius: 12, border: "none",
            background: input.trim() && !streaming
              ? "linear-gradient(135deg, #3b82f6, #6366f1)"
              : "rgba(255,255,255,0.06)",
            color: input.trim() && !streaming ? "#fff" : "var(--app-text-muted)",
            cursor: input.trim() && !streaming ? "pointer" : "default",
            display: "flex", alignItems: "center", gap: 6, fontSize: 13, fontWeight: 600,
          }}
        >
          {streaming
            ? <Loader2 size={15} style={{ animation: "spin 1s linear infinite" }} />
            : <Send size={15} />}
        </button>
      </div>
    </div>
  );
}

// ── NARRATOR TAB ─────────────────────────────────────────────────────────────

function NarratorTab() {
  const { frame } = useDetection();
  const [narration, setNarration] = useState("");
  const [loading, setLoading] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const narrate = async () => {
    setLoading(true);
    try {
      const persons = frame?.tracks.filter((t) => t.class_id === 0).length ?? 0;
      const objects = frame?.tracks.filter((t) => t.class_id !== 0).length ?? 0;
      const res = await fetch("/api/ai/narrate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tracks: frame?.tracks ?? [],
          anomalies: frame?.anomalies ?? [],
          person_count: persons,
          object_count: objects,
          source_mode: frame ? "active" : "idle",
        }),
      });
      const data = await res.json();
      setNarration(data.narration ?? "");
      setLastUpdated(new Date());
    } catch {
      setNarration("Failed to analyse scene. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  // Keep a ref to the latest narrate function so the interval always
  // calls the up-to-date version (with the current frame) without
  // recreating the interval on every frame update.
  const narrateRef = useRef(narrate);
  useEffect(() => { narrateRef.current = narrate; });

  useEffect(() => {
    if (autoRefresh) {
      timerRef.current = setInterval(() => narrateRef.current(), 10000);
    } else {
      if (timerRef.current) clearInterval(timerRef.current);
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [autoRefresh]); // intentionally excludes frame — narrateRef handles currency

  const persons = frame?.tracks.filter((t) => t.class_id === 0).length ?? 0;
  const objects = frame?.tracks.filter((t) => t.class_id !== 0).length ?? 0;
  const anomalies = frame?.anomalies.length ?? 0;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {/* Live stats strip */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 12 }}>
        {[
          { label: "PERSONS", value: persons, color: "#3b82f6" },
          { label: "OBJECTS", value: objects, color: "#f59e0b" },
          { label: "ANOMALIES", value: anomalies, color: anomalies > 0 ? "#ef4444" : "#10b981" },
        ].map(({ label, value, color }) => (
          <div key={label} style={{ ...card, textAlign: "center" }}>
            <div style={{ fontSize: 9, color: "#334155", letterSpacing: 2, fontWeight: 700, marginBottom: 8 }}>{label}</div>
            <div style={{ fontSize: 32, fontWeight: 800, color, lineHeight: 1 }}>{value}</div>
          </div>
        ))}
      </div>

      {/* Narration panel */}
      <div style={card}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <Mic2 size={16} color="#6366f1" />
            <span style={{ fontSize: 13, fontWeight: 700, color: "#94a3b8" }}>Scene Narration</span>
            {lastUpdated && (
              <span style={{ fontSize: 10, color: "#334155", fontFamily: "monospace" }}>
                Updated {lastUpdated.toLocaleTimeString(undefined)}
              </span>
            )}
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button
              onClick={() => setAutoRefresh((v) => !v)}
              style={{
                display: "flex", alignItems: "center", gap: 6,
                padding: "6px 14px", borderRadius: 8, fontSize: 11, fontWeight: 600,
                border: "1px solid rgba(255,255,255,0.1)",
                background: autoRefresh ? "rgba(16,185,129,0.1)" : "rgba(255,255,255,0.04)",
                color: autoRefresh ? "#10b981" : "#475569", cursor: "pointer",
              }}
            >
              <RefreshCw size={11} style={{ animation: autoRefresh ? "spin 2s linear infinite" : "none" }} />
              {autoRefresh ? "Auto ON" : "Auto OFF"}
            </button>
            <button
              onClick={narrate}
              disabled={loading}
              style={{
                display: "flex", alignItems: "center", gap: 8,
                padding: "8px 20px", borderRadius: 10, border: "none",
                background: loading
                  ? "rgba(99,102,241,0.08)"
                  : "linear-gradient(135deg, #4f46e5, #3b82f6)",
                color: loading ? "#334155" : "#fff",
                cursor: loading ? "default" : "pointer",
                fontSize: 13, fontWeight: 700,
              }}
            >
              {loading
                ? <><Loader2 size={14} style={{ animation: "spin 1s linear infinite" }} /> Analysing…</>
                : <><Sparkles size={14} /> Analyse Scene</>}
            </button>
          </div>
        </div>

        {narration ? (
          <div style={{
            background: "rgba(99,102,241,0.05)",
            border: "1px solid rgba(99,102,241,0.15)",
            borderRadius: 10, padding: "18px 20px",
          }}>
            <p style={{ margin: 0, fontSize: 14, color: "#94a3b8", lineHeight: 1.8 }}>
              {narration}
            </p>
          </div>
        ) : (
          <div style={{
            textAlign: "center", padding: "32px 20px",
            color: "#334155", fontSize: 13,
          }}>
            {frame
              ? "Press Analyse Scene to get an AI description of what's currently happening."
              : "Start a detection session first, then analyse the live scene."}
          </div>
        )}
      </div>

      <div style={{ fontSize: 11, color: "#1e3a5f", textAlign: "center" }}>
        Auto-refresh narrates the scene every 10 seconds automatically.
      </div>
    </div>
  );
}

// ── MAIN PAGE ────────────────────────────────────────────────────────────────

type Tab = "reports" | "chat" | "narrator";

export default function AIPanel() {
  const [tab, setTab] = useState<Tab>("narrator");
  const isMobile = useIsMobile();

  return (
    <div>
      {/* Header */}
      <div style={{
        display: "flex", alignItems: isMobile ? "flex-start" : "center",
        justifyContent: "space-between", flexDirection: isMobile ? "column" : "row",
        gap: 12, marginBottom: isMobile ? 18 : 28,
      }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 6 }}>
            <div style={{
              width: 36, height: 36, borderRadius: 10,
              background: "linear-gradient(135deg, #4f46e5, #6366f1)",
              display: "flex", alignItems: "center", justifyContent: "center",
              boxShadow: "0 4px 20px rgba(99,102,241,0.4)",
              flexShrink: 0,
            }}>
              <Bot size={18} color="#fff" />
            </div>
            <h1 style={{ fontSize: isMobile ? 18 : 22, fontWeight: 800, color: "var(--app-text)", letterSpacing: -0.5, margin: 0 }}>
              AI Assistant
            </h1>
          </div>
          <p style={{ color: "#475569", fontSize: isMobile ? 11 : 13, margin: 0 }}>
            Powered by GPT · Incident reports, alert chat, and live scene narration
          </p>
        </div>
        <div style={{
          background: "rgba(99,102,241,0.1)", border: "1px solid rgba(99,102,241,0.2)",
          borderRadius: 20, padding: "4px 14px", display: "flex", alignItems: "center", gap: 6,
          alignSelf: isMobile ? "flex-start" : "center",
        }}>
          <div style={{ width: 6, height: 6, borderRadius: "50%", background: "#6366f1", boxShadow: "0 0 8px #6366f1" }} />
          <span style={{ fontSize: 11, color: "#818cf8", fontWeight: 700, letterSpacing: 1 }}>AI ONLINE</span>
        </div>
      </div>

      {/* Tabs */}
      <div style={{
        display: "flex", gap: 4, marginBottom: 20,
        borderBottom: "1px solid rgba(255,255,255,0.06)", paddingBottom: 2,
        overflowX: isMobile ? "auto" : "visible",
        scrollbarWidth: "none",
      }}>
        <TabButton active={tab === "narrator"} onClick={() => setTab("narrator")} icon={Mic2}          label="Live Narrator" />
        <TabButton active={tab === "reports"}  onClick={() => setTab("reports")}  icon={FileText}      label="Incident Reports" />
        <TabButton active={tab === "chat"}     onClick={() => setTab("chat")}     icon={MessageSquare} label="Alert Chat" />
      </div>

      {/* Content */}
      {tab === "narrator" && <NarratorTab />}
      {tab === "reports"  && <ReportsTab />}
      {tab === "chat"     && <ChatTab />}

    </div>
  );
}

