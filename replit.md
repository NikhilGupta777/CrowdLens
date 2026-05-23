# CrowdLens · Campus AI Monitor

## Overview

Full-stack real-time surveillance and anomaly detection system. A Python FastAPI backend runs **YOLO11m + SORT tracking** on live webcam frames, uploaded video files, and RTSP/HTTP/MJPEG streams, with a dedicated Hugging Face fall-detection model. A simulation mode (`backend/simulation.py`) is available for development with synthetic entities. The React + Vite frontend renders a live surveillance dashboard with WebSocket-powered bounding boxes, stats, alert feed, history table, and an AI assistant panel.

## Stack

- **Monorepo tool**: pnpm workspaces
- **Node.js version**: 24
- **Python version**: 3.11
- **Package manager**: pnpm + uv (Python)
- **Frontend**: React 19 + Vite 7 + TailwindCSS v4 + shadcn/ui + recharts + wouter
- **Backend**: Python FastAPI + uvicorn + WebSockets + numpy + opencv-python-headless
- **Computer vision**:
  - YOLO11m (Ultralytics) via ONNX Runtime → PyTorch fallback, GPU → CPU fallback
  - Hugging Face fall-detection model (melihuzunoglu/human-fall-detection)
  - SORT multi-object tracker (filterpy Kalman + scipy Hungarian)
- **Persistence**: SQLite (alerts table with retention cap), JSON file for restricted-zone CRUD
- **Streaming I/O**: FFmpeg subprocess for RTSP / HTTP / MJPEG; WebSocket binary frames for browser webcam
- **AI assistant**: Google Gemini (`gemini-2.5-flash`) for incident reports, alert chat with real SSE streaming, and live scene narration
- **Notifications**: AWS SES (HTML email), Web Notifications API, Web Audio API for alert tones
- **Routing**: wouter (frontend SPA)

## Detection Modes

The backend runs one mode at a time (single-source). Switching modes cleanly cancels the prior loop and frees CUDA cache.

1. **Idle** — backend live but no source attached; canvas shows a light synthetic background
2. **Webcam (browser)** — JPEG frames captured at ~5 fps by `useCamProcessor` hook, sent over `/ws/cam`, processed server-side with YOLO + SORT + fall model
3. **Local IP camera (MJPEG / snapshot)** — `useLocalCamRelay` hook fetches frames in the browser and forwards them to `/ws/cam` (canvas-free to avoid CORS taint)
4. **Video Upload** — MP4 / AVI / MOV / MKV / WEBM up to 500 MB, processed at native FPS with frame-skip catch-up
5. **RTSP / HTTP / HLS Stream** — backend opens via FFmpeg subprocess at 15 fps target; HTTP file URLs auto-fall-back to a local download

Each mode constructs its own `AnomalyDetector` and `Sort` so per-loop state (track history, ghost cache, fall persistence) cannot bleed across mode switches.

## Anomaly Detection (7 algorithms)

All algorithms run simultaneously when a source is active. Each emits structured anomaly objects that the frontend renders as both canvas overlays (sticky-hold per type) and alert-feed cards.

| Anomaly | Method | Key tunables |
|---|---|---|
| **Running** | Dual-metric: pixel speed OR body-heights/sec, with 0.4 s grace time | `RUNNING_SPEED_THRESHOLD`, `RUNNING_BODY_HEIGHTS_PER_SEC`, `RUNNING_PIXEL_FLOOR`, `RUNNING_RESET_GRACE_TIME`, `RUNNING_PERSISTENCE_TIME` |
| **Overcrowding** | Single-link spatial clustering, alerts when one cluster exceeds threshold | `OVERCROWDING_THRESHOLD`, `OVERCROWDING_CLUSTER_DISTANCE_PX`, `OVERCROWDING_MIN_CLUSTER_SIZE` |
| **Unattended object** | Stationary baggage + owner absent, with spatial-cell ghost cache to survive SORT id churn during occlusion | `UNATTENDED_OBJECT_TIME`, `UNATTENDED_OWNER_PROXIMITY_PX`, `UNATTENDED_OWNER_GRACE_TIME`, `UNATTENDED_BYSTANDER_ATTENDS`, `UNATTENDED_GHOST_TTL` |
| **Fall detected** | Dedicated HF model with NMS + sanity filters, IoU-associated to person tracks | `FALL_MODEL_CONFIDENCE_THRESHOLD`, `FALL_PERSISTENCE_TIME`, `FALL_PERSON_IOU_MIN`, `FALL_ALERT_HOLD_TIME` |
| **Fight suspected** | Pair proximity + dual speed + persistence + 0.4 s grace tolerance | `FIGHT_PROXIMITY_PX`, `FIGHT_MIN_PAIR_SPEED`, `FIGHT_PERSISTENCE_TIME`, `FIGHT_RESET_GRACE_TIME` |
| **Restricted zone** | Rectangle OR polygon zones with foot-point + bbox-overlap detection, dwell-time gated | `RESTRICTED_ZONE_MIN_DWELL`, `RESTRICTED_ZONE_USE_FEET`, plus per-zone CRUD via `/api/zones` |
| **Loitering** | Anchor + hysteresis re-anchor factor, dwells longer than threshold | `LOITERING_TIME_THRESHOLD`, `LOITERING_RADIUS_PX`, `LOITERING_REANCHOR_FACTOR` |

Predicted (Kalman-extrapolated, held-over) tracks are explicitly skipped for behavioural timers so a person leaving frame doesn't keep accumulating loitering / running / zone-dwell time during the SORT hold window.

## Frontend Pages

| Path | Component | Purpose |
|---|---|---|
| `/` | `Dashboard.tsx` | Live canvas + source controls (webcam / video / stream) + metric pills + alerts feed sidebar |
| `/history` | `AlertHistory.tsx` | Searchable / filterable history table with 10-min trend chart, CSV / JSON export, snapshot evidence thumbnails |
| `/ai` | `AIPanel.tsx` | Three tabs: Live Narrator (scene description), Incident Reports (per-alert), Alert Chat (Gemini streaming over SSE). Reports and chat are localStorage-persisted with schema versioning |
| `/settings` | `Settings.tsx` | Live slider tuning of all detection thresholds, restricted-zone rectangle CRUD, overlay-style picker, bbox smoothing |

## Structure

```
├── artifacts/company-ai/             # React + Vite frontend (workspace package)
│   ├── src/
│   │   ├── App.tsx                   # Router + threat-level + sticky-anomaly wiring
│   │   ├── main.tsx                  # ErrorBoundary + StrictMode root
│   │   ├── components/
│   │   │   ├── SimulationCanvas.tsx  # Renders all modes (live + idle background)
│   │   │   ├── AlertsFeed.tsx
│   │   │   ├── Layout.tsx
│   │   │   ├── ErrorBoundary.tsx
│   │   │   └── StatsCards.tsx
│   │   ├── pages/                    # Dashboard / AlertHistory / AIPanel / Settings
│   │   ├── hooks/
│   │   │   ├── useSimulation.ts      # /ws WebSocket reader (frame-dropping via rAF)
│   │   │   ├── useCamProcessor.ts    # Browser webcam → /ws/cam JPEG relay
│   │   │   ├── useLocalCamRelay.ts   # Local IP camera (MJPEG / snapshot) → /ws/cam
│   │   │   ├── useStickyAnomalies.ts # Per-type hold times for canvas + feed
│   │   │   ├── useAlertSound.ts      # Distinct Web Audio tones per anomaly type
│   │   │   └── useNotifications.ts   # Browser push notifications
│   │   ├── context/DetectionContext.tsx
│   │   └── types/index.ts
│   └── vite.config.ts                # Proxies /api + /ws to backend port 8080
├── backend/
│   ├── main.py                       # FastAPI app + all REST + WS routes + processing loops
│   ├── detector.py                   # YOLO11m loader (ONNX → PyTorch, GPU → CPU fallback)
│   ├── fall_detector.py              # Hugging Face fall-detection model + NMS
│   ├── sort_tracker.py               # SORT multi-object tracker (Kalman + Hungarian)
│   ├── anomaly.py                    # All 7 anomaly algorithms
│   ├── config.py                     # Detection thresholds, COCO classes, retention cap
│   ├── database.py                   # SQLite alerts table with ALTER-TABLE migration
│   └── simulation.py                 # Synthetic-entity engine (idle-mode canvas only)
├── docs/                             # 6 markdown design docs
└── start.bat                         # Windows quick launcher
```

## Running

### Vite dev server

The frontend dev server defaults to port 5173 (`pnpm --filter @workspace/company-ai run dev`). The Vite proxy forwards `/api` and `/ws` to the backend on port 8080.

### Local launch (Windows quick start)

`start.bat` opens two terminals — one running uvicorn on 8080, one running Vite — then auto-opens the browser. The repo is intended for local single-user use on Windows.

### Manual launch (any OS)

```bash
# Terminal 1 — Backend
ALLOW_LOCAL_STREAMS=true uv run uvicorn backend.main:app --host 127.0.0.1 --port 8080 --reload

# Terminal 2 — Frontend
pnpm --filter @workspace/company-ai run dev
```

Open `http://localhost:5173`.

`ALLOW_LOCAL_STREAMS=true` removes the SSRF guard so private-network IP cameras work:
- RTSP cameras: `rtsp://admin:pass@192.168.x.x:554/stream` → **Live Stream** panel
- HTTP MJPEG: `http://192.168.x.x/video.cgi` → **Live Stream** panel (preferred for IP cameras)
- DroidCam phone: `http://192.168.x.x:4747/video` → **Webcam → Phone Camera (Browser MJPEG Relay)**
- Snapshot URL (zero CORS): `http://192.168.x.x:4747/shot.jpg` → same panel

## API Endpoints

### Health & stats
- `GET /api/health` — uptime + per-model loading stage (`model_progress.stage`, `fall_model_progress.stage`)
- `GET /api/stats` — current detection statistics

### Alerts & evidence archive
- `GET /api/alerts/history?limit=N` — incident log (paginated)
- `POST /api/alerts/clear` — wipes deque + DB rows + on-disk archive JPGs
- `GET /api/archive` — alerts that have evidence snapshots
- `POST /api/archive/capture` — manual snapshot of latest processed frame (rejects HTTP 409 when idle)
- `GET /api/archive/image/{filename}` — fetch a snapshot
- `POST /api/archive/clear` — delete all snapshots

### Configuration
- `GET /api/config` / `PUT /api/config` — all 35+ detection thresholds + tracker tuning. Live update, no restart
- `GET /api/zones` / `POST /api/zones` / `PUT /api/zones/{id}` / `DELETE /api/zones/{id}` — restricted-zone CRUD (rectangle + polygon), persisted to `backend/zones.json`

### Source modes
- `POST /api/video/upload` — upload video file (≤500 MB)
- `POST /api/video/start` / `POST /api/video/stop` / `GET /api/video/status`
- `POST /api/webcam/start` / `POST /api/webcam/stop` / `GET /api/webcam/status`
- `POST /api/stream/start` / `POST /api/stream/stop` / `GET /api/stream/status`
- `GET /api/stream/test-feed` — built-in synthetic MJPEG for pipeline testing

### Notifications
- `GET /api/notify/status` — email metrics
- `POST /api/notify/test?force=true` — send test email

### AI assistant (Gemini)
- `POST /api/ai/report` — incident report for a single alert
- `POST /api/ai/chat` — SSE chat with real `streamGenerateContent` streaming
- `POST /api/ai/narrate` — scene description from current frame state

### WebSockets
- `WS /ws` — outbound detection frames (tracks, anomalies, stats, JPEG preview)
- `WS /ws/cam` — inbound webcam JPEG frames (browser → backend)

## Persistence Notes

- SQLite alerts table has a retention cap (`DB_ALERT_RETENTION`, default 5000) — oldest rows pruned on insert
- Forward-migration on startup adds `snapshot_url` column to older DBs
- `/api/alerts/clear` is now atomic across deque + DB + archive JPGs
- AI reports + chat history persist in browser `localStorage` with `{v:1}` schema versioning
- Camera profiles persist in browser `localStorage` with `{v:1}` schema versioning

## Nix / OS Dependencies

- `xorg.libxcb`, `xorg.libX11`, `xorg.libXext` — required by OpenCV headless for internal threading even without a display
- `ffmpeg` — required for RTSP / HTTP / HLS stream input
