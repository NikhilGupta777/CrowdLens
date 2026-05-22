# CrowdLens — Campus AI Monitor

<div align="center">

**Real-Time AI-Powered Surveillance & Anomaly Detection System**

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://python.org)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=white)](https://react.dev)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![YOLO](https://img.shields.io/badge/YOLO-v11m-FF6F00?logo=pytorch&logoColor=white)](https://docs.ultralytics.com)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

</div>

---

## Overview

CrowdLens is a full-stack real-time intelligent surveillance system for campus and institutional security. It uses **YOLOv11m** for object detection, **SORT** (Simple Online and Realtime Tracking) with Kalman filtering for multi-object tracking, and a suite of behavioural analysis algorithms to automatically detect **7 types of security anomalies** from live camera feeds, uploaded videos, or IP camera streams.

### Key Capabilities

| Anomaly Type | Method | Status |
|---|---|---|
| Running | Speed-based + persistence | ✅ Production |
| Overcrowding | Person count threshold | ✅ Production |
| Unattended Object | Stationary bag + owner absent | ✅ Production |
| Fall Detection | Dedicated HuggingFace model | ✅ Production |
| Fight Suspected | Pair proximity + speed heuristic | ✅ Prototype |
| Restricted Zone | Digital fencing (rectangular) | ✅ Production |
| Loitering | Dwell time in area | ✅ Production |

---

## Screenshots

> Dashboard with live Canvas 2D rendering, metric pills, alert feed, and multi-source controls.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **AI/ML** | YOLOv11m (Ultralytics), ONNX Runtime, HuggingFace Fall Model |
| **Backend** | Python 3.11, FastAPI, Uvicorn, WebSockets, SQLite |
| **Tracking** | SORT (Kalman Filter + Hungarian Algorithm) |
| **Frontend** | React 19, Vite 7, TailwindCSS v4, Canvas 2D, shadcn/ui |
| **Notifications** | AWS SES (Email), Web Notifications API, Web Audio API |
| **Streaming** | FFmpeg (RTSP/HTTP), WebSocket binary frames |
| **AI Assistant** | Google Gemini API (reports, chat, narration) |

---

## Features

### Detection & Tracking
- Real-time person, vehicle, and baggage detection (YOLOv11m)
- Multi-object tracking with persistent IDs (SORT + Kalman)
- 7 anomaly detection algorithms running simultaneously
- Dedicated fall detection model (HuggingFace)
- Configurable confidence thresholds per source mode

### Input Sources
- **Browser Webcam** — USB/built-in camera via getUserMedia
- **Video Upload** — MP4/AVI/MOV/MKV up to 500 MB
- **RTSP Stream** — IP cameras via FFmpeg pipe
- **HTTP/MJPEG Stream** — Network cameras, DroidCam
- **Local Network Camera** — Fetch-based MJPEG/snapshot relay

### Dashboard
- Live Canvas 2D rendering at 60fps (5 overlay styles)
- Real-time stats: person count, object count, anomalies, FPS
- Alert history with search, filter, charts, CSV/JSON export
- AI Assistant (incident reports, alert chat, live scene narration)
- Dark/Light mode, responsive mobile layout
- Configurable detection thresholds with live sliders

### Alerts & Notifications
- In-app real-time alerts via WebSocket
- Audio alert tones (unique per anomaly type)
- Browser push notifications
- Email alerts via AWS SES (HTML formatted)
- Evidence snapshot archival (7-day retention)

---

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 24+ with pnpm
- FFmpeg (for stream processing)

### Installation

```bash
# Clone the repository
git clone https://github.com/NikhilGupta777/Gemini-Clone.git
cd Gemini-Clone

# Install Python dependencies
pip install uv
uv sync

# Install frontend dependencies
pnpm install
```

### Running Locally

```bash
# Terminal 1 — Backend (port 8080)
uv run uvicorn backend.main:app --host 127.0.0.1 --port 8080 --reload

# Terminal 2 — Frontend (port 5173)
pnpm --filter @workspace/company-ai run dev
```

Open **http://localhost:5173** in your browser.

### Running with Campus IP Cameras

```bash
# Enable local network camera access
ALLOW_LOCAL_STREAMS=true uv run uvicorn backend.main:app --host 0.0.0.0 --port 8080 --reload
```

Then paste your camera URL (e.g., `rtsp://admin:pass@192.168.x.x:554/stream`) into the Stream panel.

### Windows Quick Start

Double-click `start.bat` — it launches both servers and opens the browser automatically.

---

## Environment Variables

Copy `.env.example` to `.env` and configure:

```env
# AI Assistant (Gemini API)
AI_INTEGRATIONS_GEMINI_BASE_URL=https://generativelanguage.googleapis.com/v1beta
AI_INTEGRATIONS_GEMINI_API_KEY=your_gemini_api_key

# Email Alerts (AWS SES)
ALERT_EMAIL_TO=your-email@example.com
ALERT_EMAIL_FROM=your-email@example.com
ALERT_EMAIL_COOLDOWN_SECS=45

# Stream Security
ALLOW_LOCAL_STREAMS=true  # Set to true for campus IP cameras

# Fall Detection Model (optional local override)
FALL_MODEL_LOCAL_PATH=  # Path to local .pt file
```

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│  Browser (React 19 + Canvas 2D + WebSocket)          │
└────────────────────────┬─────────────────────────────┘
                         │ WebSocket + REST
┌────────────────────────┴─────────────────────────────┐
│  FastAPI Backend                                      │
│  ┌────────────┐ ┌──────────┐ ┌────────────────────┐ │
│  │ YOLOv11m   │ │  SORT    │ │ Anomaly Detector   │ │
│  │ Detector   │ │ Tracker  │ │ (7 algorithms)     │ │
│  └────────────┘ └──────────┘ └────────────────────┘ │
│  ┌────────────┐ ┌──────────┐ ┌────────────────────┐ │
│  │Fall Detect │ │ SQLite   │ │ Email + Archive    │ │
│  │(HuggingFace│ │ Database │ │ Notifications      │ │
│  └────────────┘ └──────────┘ └────────────────────┘ │
└──────────────────────────────────────────────────────┘
```

---

## Project Structure

```
├── backend/
│   ├── main.py           # FastAPI app, endpoints, processing loops
│   ├── detector.py       # YOLOv11m detection (ONNX/PyTorch)
│   ├── sort_tracker.py   # SORT multi-object tracker
│   ├── anomaly.py        # 7 anomaly detection algorithms
│   ├── fall_detector.py  # Dedicated fall model (HuggingFace)
│   ├── simulation.py     # Synthetic entity simulation (fallback)
│   ├── config.py         # Detection thresholds & constants
│   └── database.py       # SQLite async persistence
├── artifacts/company-ai/  # React frontend (Vite + TailwindCSS)
│   └── src/
│       ├── pages/         # Dashboard, AlertHistory, Settings, AIPanel
│       ├── components/    # SimulationCanvas, Layout, AlertsFeed
│       ├── hooks/         # useSimulation, useCamProcessor, etc.
│       └── context/       # DetectionContext (global state)
├── docs/                  # Project documentation
└── start.bat             # Windows quick launcher
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Health check + uptime |
| GET | `/api/stats` | Current detection statistics |
| GET | `/api/alerts/history` | Alert history (paginated) |
| GET/PUT | `/api/config` | Detection thresholds (live update) |
| POST | `/api/video/upload` | Upload video file (≤500 MB) |
| POST | `/api/stream/start` | Start RTSP/HTTP stream |
| POST | `/api/webcam/start` | Start webcam processing |
| WS | `/ws` | Real-time detection broadcast |
| WS | `/ws/cam` | Webcam frame ingestion |

---

## Detection Modes

| Mode | Source | Processing |
|------|--------|-----------|
| **Simulation** | Synthetic | Fallback when no source active |
| **Video** | Uploaded file | YOLO at native video FPS |
| **Webcam** | Browser camera | JPEG frames via WebSocket at 5fps |
| **Stream** | RTSP/HTTP URL | FFmpeg pipe at 15fps |

---

## Performance

| Metric | CPU (Intel i7) | GPU (NVIDIA) |
|--------|---------------|-------------|
| Detection FPS | 5-8 | 15-25 |
| End-to-end latency | 200-400ms | 80-150ms |
| Memory usage | 2-4 GB | 3-5 GB |
| Model loading | 10-30s | 5-15s |

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## License

This project is licensed under the MIT License.

---

## Acknowledgments

- [Ultralytics](https://ultralytics.com) — YOLOv11 object detection
- [melihuzunoglu](https://huggingface.co/melihuzunoglu/human-fall-detection) — Fall detection model
- [shadcn/ui](https://ui.shadcn.com) — UI component library
- [FastAPI](https://fastapi.tiangolo.com) — Python web framework
- SORT Algorithm — Bewley et al. (2016)
