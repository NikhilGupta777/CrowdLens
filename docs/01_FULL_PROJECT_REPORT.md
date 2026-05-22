# CrowdLens — Campus AI Monitor
## Full Project Report

---

## 1. PROJECT OVERVIEW

### 1.1 Project Title
**CrowdLens: AI-Powered Real-Time Campus Surveillance and Anomaly Detection System**

### 1.2 What is CrowdLens?
CrowdLens is a full-stack, real-time intelligent surveillance system designed for campus and institutional security monitoring. It leverages state-of-the-art deep learning object detection (YOLOv11m), multi-object tracking (SORT with Kalman Filtering), and behavioural anomaly detection to automatically identify security threats — such as running individuals, overcrowding, unattended bags, person falls, potential fights, and unauthorized zone intrusions — all in real-time from live camera feeds, uploaded videos, or RTSP/HTTP streams.

### 1.3 Problem Statement
Traditional campus security relies heavily on:
- **Manual CCTV monitoring** — Security personnel must watch multiple screens simultaneously, leading to fatigue-induced missed events.
- **Reactive response** — Incidents are typically identified only after they occur (post-incident footage review).
- **No automated alerting** — Anomalies go undetected unless a human operator happens to be watching at that exact moment.
- **No intelligent analysis** — Raw video provides no metrics, trends, or actionable insights.

**Key Problems Addressed:**
1. Human fatigue in 24/7 surveillance environments
2. Delayed incident response due to lack of real-time detection
3. Absence of automated anomaly identification in crowded campus environments
4. No historical analytics or reporting on security incidents
5. Difficulty integrating multiple camera sources (IP cameras, webcams, video files)

### 1.4 Proposed Solution
CrowdLens provides an **AI-first, real-time surveillance platform** that:
- Automatically detects and tracks all persons and objects using YOLOv11m
- Identifies behavioural anomalies (running, fighting, falling, overcrowding)
- Detects security threats (unattended bags, restricted zone breaches)
- Sends instant email alerts for critical incidents
- Provides an AI assistant for natural-language querying of incident history
- Supports multiple input sources: live webcam, video upload, RTSP/HTTP streams, and IP cameras
- Maintains a persistent database of all incidents with evidence snapshots

### 1.5 Why CrowdLens is Better Than Existing Solutions

| Feature | Traditional CCTV | Basic Motion Detection | **CrowdLens** |
|---------|-----------------|----------------------|---------------|
| Real-time object detection | ❌ | ❌ | ✅ YOLOv11m |
| Multi-object tracking | ❌ | ❌ | ✅ SORT + Kalman |
| Behavioural anomaly detection | ❌ | ❌ | ✅ 6 anomaly types |
| Fall detection (dedicated model) | ❌ | ❌ | ✅ HuggingFace model |
| Fight suspicion detection | ❌ | ❌ | ✅ Heuristic pair-motion |
| Digital fencing / restricted zones | ❌ | ❌ | ✅ Configurable zones |
| Automated email alerts | ❌ | ❌ | ✅ AWS SES |
| AI-powered reporting | ❌ | ❌ | ✅ GPT integration |
| Multiple input sources | Limited | Limited | ✅ Webcam/Video/RTSP/HTTP |
| Browser-based dashboard | ❌ | ❌ | ✅ React SPA |
| Real-time WebSocket streaming | ❌ | ❌ | ✅ 10-15 FPS |
| Configurable thresholds | ❌ | ❌ | ✅ Live slider tuning |
| Evidence archival with snapshots | ❌ | ❌ | ✅ JPEG snapshots |
| Export (CSV/JSON) | ❌ | ❌ | ✅ Full export |
| Browser push notifications | ❌ | ❌ | ✅ Web Notifications API |
| Audio alerts | ❌ | ❌ | ✅ Web Audio API tones |
| Dark/Light theme | ❌ | ❌ | ✅ Full theming |

---

## 2. OBJECTIVES

### 2.1 Primary Objectives
1. Develop a real-time AI-powered surveillance system for campus security
2. Implement automatic detection of persons, vehicles, and baggage using YOLO
3. Build multi-object tracking to maintain identity persistence across frames
4. Detect behavioural anomalies: running, overcrowding, unattended objects, falls, fights, zone intrusions
5. Provide instant automated alerts via email and browser notifications
6. Create an intuitive web-based dashboard for monitoring and management

### 2.2 Secondary Objectives
1. Support multiple video input sources (webcam, file, RTSP, HTTP streams)
2. Integrate AI assistant for natural-language incident querying
3. Maintain a persistent incident database with evidence snapshots
4. Allow real-time configuration of detection thresholds
5. Ensure the system runs efficiently on CPU (no GPU requirement)
6. Support local deployment for campus IP camera integration

---

## 3. SCOPE

### 3.1 In Scope
- Real-time person and object detection
- Multi-object tracking with ID persistence
- 6 types of anomaly detection
- Web-based dashboard with live canvas rendering
- WebSocket-based real-time data streaming
- Video upload processing (up to 500 MB)
- RTSP/HTTP stream integration
- Browser webcam capture and processing
- Email alert notifications (AWS SES)
- Browser push notifications
- AI-powered incident reports and chat
- Configurable detection parameters
- Alert history with search/filter/export
- Evidence snapshot archival
- Dark/Light mode UI

### 3.2 Out of Scope (Future Work)
- Multi-camera simultaneous feeds
- Facial recognition
- License plate recognition
- Cloud-hosted scalable deployment
- Mobile application
- Advanced fight detection with pose estimation
- Weapon detection
- Smoke/fire detection

---

## 4. TECHNOLOGY STACK

### 4.1 Backend
| Technology | Version | Purpose |
|-----------|---------|---------|
| Python | 3.11 | Core backend language |
| FastAPI | ≥0.110.0 | Async web framework |
| Uvicorn | ≥0.29.0 | ASGI server |
| Ultralytics (YOLO) | ≥8.0.0 | Object detection (YOLOv11m) |
| OpenCV | ≥4.13.0 | Image processing |
| NumPy | ≥1.24.0 | Numerical computations |
| SciPy | ≥1.11.0 | Hungarian algorithm (tracking) |
| FilterPy | ≥1.4.5 | Kalman filter implementation |
| PyTorch | ≥2.5.1 | Deep learning backend |
| ONNX Runtime | ≥1.16.0 | Optimized inference |
| SQLite | Built-in | Alert persistence |
| WebSockets | ≥12.0 | Real-time communication |
| HuggingFace Hub | ≥0.25.0 | Fall detection model |
| Python-Multipart | ≥0.0.9 | File upload handling |
| Pydantic | ≥2.0 | Data validation |

### 4.2 Frontend
| Technology | Version | Purpose |
|-----------|---------|---------|
| React | 19.1.0 | UI framework |
| Vite | 7.3.0 | Build tool / dev server |
| TailwindCSS | 4.1.14 | Utility-first CSS |
| TypeScript | ~5.9.2 | Type-safe JavaScript |
| Wouter | 3.3.5 | Client-side routing |
| Recharts | 2.15.2 | Data visualization charts |
| Lucide React | 0.545.0 | Icon library |
| Framer Motion | 12.35.1 | Animations |
| shadcn/ui | Latest | UI component library |
| Radix UI | Multiple | Accessible primitives |
| React Markdown | 10.1.0 | Markdown rendering |
| React Dropzone | 15.0.0 | File drag-and-drop |

### 4.3 AI/ML Models
| Model | Source | Purpose |
|-------|--------|---------|
| YOLOv11m | Ultralytics | Person/object detection |
| YOLO Fall Detection | HuggingFace (melihuzunoglu) | Dedicated fall detection |
| GPT (OpenAI) | API | AI reports, chat, narration |

### 4.4 Infrastructure
| Component | Technology |
|-----------|-----------|
| Package Manager | pnpm (Node) + uv (Python) |
| Monorepo | pnpm workspaces |
| Process Communication | WebSocket |
| Alert Notifications | AWS SES (email) |
| Database | SQLite with WAL mode |
| Model Format | ONNX (primary) / PyTorch (fallback) |

---

## 5. SYSTEM ARCHITECTURE

### 5.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         CLIENT (Browser)                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │  Dashboard   │  │ Alert History │  │  AI Assistant (GPT)      │  │
│  │  (Canvas 2D) │  │ (Table+Chart)│  │  (Reports/Chat/Narrator) │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────────┘  │
│         │                  │                      │                   │
│  ┌──────┴──────────────────┴──────────────────────┴───────────────┐  │
│  │              WebSocket Connection (ws:// + ws://cam)            │  │
│  └────────────────────────────────┬───────────────────────────────┘  │
└───────────────────────────────────┼──────────────────────────────────┘
                                    │
                                    ▼
┌───────────────────────────────────────────────────────────────────────┐
│                      BACKEND (FastAPI + Python)                        │
│                                                                       │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌────────────┐ │
│  │   REST API  │  │  WebSocket  │  │  WebSocket  │  │  Lifespan  │ │
│  │  Endpoints  │  │  /ws (out)  │  │ /ws/cam(in) │  │  Manager   │ │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └─────┬──────┘ │
│         │                 │                 │                │        │
│  ┌──────┴─────────────────┴─────────────────┴────────────────┴─────┐ │
│  │                    Processing Engine                              │ │
│  │  ┌──────────┐  ┌──────────────┐  ┌───────────────────────────┐  │ │
│  │  │  YOLO11m │  │ SORT Tracker │  │   Anomaly Detector        │  │ │
│  │  │ Detector │  │ (Kalman+IoU) │  │ (6 anomaly algorithms)    │  │ │
│  │  └──────────┘  └──────────────┘  └───────────────────────────┘  │ │
│  │  ┌──────────────┐  ┌─────────────────────────────────────────┐  │ │
│  │  │ Fall Detector │  │  Simulation Engine (fallback mode)      │  │ │
│  │  │ (HuggingFace)│  └─────────────────────────────────────────┘  │ │
│  │  └──────────────┘                                                │ │
│  └──────────────────────────────────────────────────────────────────┘ │
│                                                                       │
│  ┌──────────────────────────────────────────────────────────────────┐ │
│  │  Data Layer: SQLite DB │ Alert Archive │ Email (AWS SES)         │ │
│  └──────────────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────────────┘
```

### 5.2 Data Flow

```
Camera/Video → Frame Capture → YOLO11m Detection → SORT Tracking →
Anomaly Analysis → [Alert Recording + Email + DB] → WebSocket Broadcast →
Frontend Canvas Rendering + Stats Update
```

### 5.3 Detection Modes

| Mode | Input Source | Processing |
|------|-------------|-----------|
| **Simulation** | Synthetic entities | Client-side fallback when no source active |
| **Video Upload** | MP4/AVI/MOV file (≤500 MB) | Server-side YOLO + SORT at native FPS |
| **Webcam** | Browser camera (USB/built-in) | Browser captures JPEG → /ws/cam → server YOLO |
| **RTSP/HTTP Stream** | IP camera URL | FFmpeg pipe → server YOLO at 15 FPS |

### 5.4 Processing Pipeline (per frame)

1. **Frame Acquisition** — Read from video/webcam/stream
2. **Resize** — Scale to inference resolution (640×360)
3. **YOLO Detection** — Run YOLOv11m to get bounding boxes + class IDs + confidence
4. **Baggage Deduplication** — Merge overlapping backpack/handbag/suitcase detections
5. **SORT Update** — Kalman prediction + Hungarian matching + track ID assignment
6. **Fall Detection** — Run dedicated fall model on source-resolution frame
7. **Coordinate Scaling** — Map inference coords to 1280×720 canvas space
8. **Anomaly Detection** — Check all tracks against 6 anomaly algorithms
9. **Alert Recording** — If new anomaly, save to DB + queue email + archive snapshot
10. **Payload Construction** — Build JSON with tracks, anomalies, stats, frame JPEG
11. **WebSocket Broadcast** — Send to all connected dashboard clients

---

## 6. DETAILED FEATURE ANALYSIS

### 6.1 Object Detection (YOLOv11m)
- **Model**: YOLOv11m (Medium variant) — balance of accuracy and speed
- **Inference**: ONNX Runtime preferred (4× faster), PyTorch fallback
- **GPU/CPU**: Auto-detects CUDA; falls back gracefully to CPU
- **Input Resolution**: 640×640 (YOLO native)
- **Detected Classes**: Person (0), Car (2), Backpack (24), Baggage (26), Suitcase (28)
- **Confidence Thresholds**: Video=0.18, Webcam=0.20, Stream=0.25, Baggage floor=0.10
- **Baggage Canonicalization**: Overlapping bag detections merged to single "baggage" entity

### 6.2 Multi-Object Tracking (SORT)
- **Algorithm**: Simple Online and Realtime Tracking
- **State Estimation**: Kalman Filter (7D state: cx, cy, area, aspect_ratio, + velocities)
- **Association**: Hungarian algorithm (scipy.optimize.linear_sum_assignment)
- **Cost Function**: IoU-based for persons; center-distance fallback for bags
- **Track Persistence**: max_age=30 frames; bags held for 120 frames (strong) / 45 frames (weak)
- **Global ID Counter**: Thread-safe; prevents collisions across concurrent instances

### 6.3 Anomaly Detection Algorithms

#### 6.3.1 Running Detection
- Tracks 5-frame speed history for each person
- Average pixel/second speed compared to threshold (default: 270 px/s)
- Must persist for 0.8 seconds to confirm
- Minimum hit-streak of 4 frames required (eliminates jitter)

#### 6.3.2 Overcrowding Detection
- Counts persons in frame
- Triggers when count exceeds threshold (default: 4)
- Reports centroid position of all persons

#### 6.3.3 Unattended Object Detection
- Tracks stationary bags (backpack, handbag, suitcase)
- Identifies "owner" as nearest person within proximity radius (180 px)
- Alerts when bag is stationary for 5+ seconds AND owner absent for 2+ seconds
- Uses bbox center distance + foot distance for owner proximity

#### 6.3.4 Fall Detection (Dedicated Model)
- Dedicated YOLOv11 model trained on fall detection (HuggingFace: melihuzunoglu/human-fall-detection)
- Runs on source-resolution frame (not downscaled) for better posture fidelity
- Filters: minimum area, bottom-of-frame only, width/height ratio ≥ 0.65
- Must persist for 1.2 seconds to confirm (reduces false positives)
- IoU-based region matching across frames for persistence

#### 6.3.5 Fight Suspicion Detection (Heuristic)
- Identifies pairs of persons within proximity threshold (180 px)
- Both must exceed minimum speed (240 px/s)
- Both must have stable tracks (hit_streak ≥ 3)
- Must persist for 0.8 seconds
- De-duplicated with 1.5-second alert cooldown

#### 6.3.6 Restricted Zone / Digital Fencing
- Configurable rectangular zones (absolute pixel coordinates on 1280×720 canvas)
- Detects when persons enter restricted areas
- Minimum dwell time before alert (default: 0.6 seconds)
- Visual overlay on canvas with dashed borders

### 6.4 Alert System
- **Alert Cooldown**: 5 seconds between repeat alerts for same track+type
- **Email Notifications**: AWS SES with HTML-formatted alerts
- **Email Cooldown**: 45 seconds per alert_type+source combination (file-based lock for multi-process)
- **Browser Push Notifications**: Web Notifications API with per-type labels
- **Audio Alerts**: Web Audio API with different tone patterns per anomaly type
- **Evidence Snapshots**: JPEG images saved with 7-day retention

### 6.5 AI Assistant (GPT Integration)
- **Incident Reports**: Per-alert AI-generated incident reports
- **Alert Chat**: Natural-language querying of last 50 alerts
- **Live Narrator**: Real-time AI scene description (auto-refresh every 10 seconds)
- **Streaming Responses**: Server-Sent Events for progressive text display

### 6.6 Frontend Dashboard
- **Live Surveillance Canvas**: HTML5 Canvas 2D rendering at 60fps animation
- **5 Overlay Styles**: Corners, Dots, Heatmap, Chips, Auto (adaptive)
- **Bounding Box Smoothing**: Configurable exponential smoothing (Kalman-smoothed positions)
- **Metric Pills**: Live person count, object count, anomaly count, active tracks
- **Alert Feed**: Real-time scrolling alert panel with type-colored badges
- **Stats Cards**: Occupancy, FPS, uptime
- **Alert History**: Sortable table with chart visualization (Recharts)
- **Settings**: Real-time threshold adjustment with premium slider UI
- **Dark/Light Mode**: Full theme support

### 6.7 Input Source Management
- **Video Upload**: Drag-and-drop, progress bar, 500 MB limit
- **Stream**: RTSP/HTTP URL input, camera profile saving (localStorage)
- **Webcam**: Device enumeration, multi-camera selection
- **Local Network Camera**: MJPEG/Snapshot relay via fetch() streaming
- **SSRF Protection**: Private IP validation (bypassable for local deployment)

---

## 7. DATABASE DESIGN

### 7.1 SQLite Schema
```sql
CREATE TABLE alerts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id    INTEGER NOT NULL,
    anomaly     TEXT NOT NULL,        -- JSON blob
    timestamp   REAL NOT NULL,        -- Unix timestamp
    iso         TEXT NOT NULL,        -- ISO 8601 string
    source      TEXT NOT NULL DEFAULT '',  -- video/webcam/stream
    snapshot_url TEXT                 -- Path to evidence JPEG
);

CREATE INDEX idx_alerts_timestamp ON alerts(timestamp DESC);
```

### 7.2 Design Decisions
- **WAL Mode**: Write-Ahead Logging for concurrent read/write performance
- **Thread-Local Connections**: Each thread gets its own connection (thread safety)
- **Async Wrapper**: asyncio.to_thread for non-blocking DB operations
- **In-Memory Deque**: 500-entry ring buffer for fast recent access
- **Startup Hydration**: DB contents loaded into deque at startup

---

## 8. API DOCUMENTATION

### 8.1 REST Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | /api/health | Health check + uptime |
| GET | /api/stats | Current detection statistics |
| GET | /api/alerts/history | Paginated alert history |
| POST | /api/alerts/clear | Clear all alerts + archive |
| GET | /api/config | Get detection thresholds |
| PUT | /api/config | Update detection thresholds (live) |
| POST | /api/video/upload | Upload video file (multipart) |
| POST | /api/video/start | Start video processing |
| POST | /api/video/stop | Stop video processing |
| GET | /api/video/status | Video mode status + model readiness |
| POST | /api/stream/start | Start RTSP/HTTP stream |
| POST | /api/stream/stop | Stop stream processing |
| GET | /api/stream/status | Stream mode status |
| POST | /api/webcam/start | Start webcam processing |
| POST | /api/webcam/stop | Stop webcam processing |
| GET | /api/archive | List archived evidence |
| POST | /api/archive/capture | Manual evidence snapshot |
| GET | /api/archive/image/{filename} | Serve evidence JPEG |
| POST | /api/archive/clear | Clear all archive snapshots |
| GET | /api/notify/status | Email notification metrics |
| POST | /api/notify/test | Send test email notification |
| POST | /api/ai/report | Generate AI incident report |
| POST | /api/ai/chat | AI chat (streaming SSE) |
| POST | /api/ai/narrate | AI scene narration |

### 8.2 WebSocket Endpoints

| Endpoint | Direction | Purpose |
|----------|-----------|---------|
| /ws | Server → Client | Broadcast detection frames (tracks, anomalies, stats, JPEG) |
| /ws/cam | Client → Server | Receive JPEG frames from browser webcam |

---

## 9. WHAT HAS BEEN IMPLEMENTED

### 9.1 Fully Implemented Features ✅
1. YOLOv11m object detection with ONNX/PyTorch multi-strategy loading
2. SORT multi-object tracking with Kalman filter
3. Running detection with speed + persistence thresholds
4. Overcrowding detection with configurable threshold
5. Unattended object detection with owner tracking
6. Fall detection using dedicated HuggingFace model
7. Fight suspicion detection (heuristic pair-motion)
8. Restricted zone / digital fencing
9. Real-time WebSocket streaming at 10-15 FPS
10. Video upload + looping playback processing
11. RTSP/HTTP stream processing via FFmpeg pipe
12. Browser webcam capture + server-side processing
13. Local network camera relay (MJPEG + snapshot modes)
14. Email alerts via AWS SES with HTML formatting
15. Browser push notifications
16. Audio alert tones (Web Audio API)
17. AI incident reports (GPT)
18. AI alert chat (streaming)
19. AI live scene narration
20. Alert history with search, filter, chart
21. CSV/JSON export
22. Evidence snapshot archival with 7-day retention
23. Configurable detection thresholds (live sliders)
24. 5 overlay rendering styles (corners, dots, heatmap, chips, auto)
25. Bounding box smoothing
26. Dark/Light mode
27. Camera profile saving
28. Multi-camera USB device selection
29. SQLite persistent storage with WAL mode
30. SSRF protection for stream URLs
31. Simulation fallback mode (no camera needed)

### 9.2 Partially Implemented / Prototype Stage ⚠️
1. **Fight Detection** — Works as a heuristic (pair proximity + speed), NOT vision-based pose estimation. May produce false positives in dense crowds.
2. **Fall Detection** — Relies on single HuggingFace model; may miss subtle falls or produce false positives from crouching/bending.

### 9.3 NOT Implemented (Future Scope) ❌
1. **Multi-camera dashboard** — Only one source processes at a time
2. **Facial recognition** — Not implemented (privacy concerns)
3. **License plate recognition (ANPR)** — Not implemented
4. **Weapon detection** — Not implemented
5. **Smoke/fire detection** — Not implemented
6. **Pose estimation** — Not used for fight/fall (would improve accuracy)
7. **Cloud deployment** — Designed for local/single-server
8. **Mobile app** — Web-only
9. **Advanced analytics** — No heatmap history, path analysis, or predictive models
10. **Video recording/DVR** — Does not record full video streams
11. **Multi-user authentication** — No login system
12. **Role-based access control** — No permission system

---

## 10. FIGHT DETECTION — DETAILED ANALYSIS

### 10.1 Current Implementation (Heuristic)
The fight detection in CrowdLens uses a **motion-based heuristic approach**:

**Algorithm:**
1. For every pair of tracked persons in the frame:
   - Check if distance between them ≤ FIGHT_PROXIMITY_PX (180 pixels)
   - Check if BOTH have average speed ≥ FIGHT_MIN_PAIR_SPEED (240 px/s)
   - Check if BOTH have stable tracking (hit_streak ≥ 3)
2. If all conditions met, start persistence timer
3. If conditions persist for ≥ FIGHT_PERSISTENCE_TIME (0.8 seconds), emit alert
4. De-duplicate with 1.5-second cooldown per pair

**Limitations:**
- Cannot distinguish fighting from hugging, playing, or dancing
- False positives when two people run past each other
- No pose estimation to detect aggressive postures
- No action recognition to classify the actual activity

### 10.2 Future Improvement Path
To achieve true fight detection, the system would need:
1. **Pose Estimation** (e.g., MediaPipe, OpenPose) — Detect aggressive body postures
2. **Action Recognition** (e.g., SlowFast, I3D networks) — Classify temporal action sequences
3. **Violence Detection Model** — Dedicated model trained on fight/violence datasets
4. **Skeleton-based Analysis** — Track limb movements for punch/kick patterns

---

## 11. PERFORMANCE CHARACTERISTICS

| Metric | Value |
|--------|-------|
| Detection FPS (CPU) | ~5-8 FPS |
| Detection FPS (GPU) | ~15-25 FPS |
| WebSocket latency | <100ms |
| Model loading time | 10-30 seconds |
| Video upload limit | 500 MB |
| Stream resolution | 640×360 |
| Canvas resolution | 1280×720 |
| Alert history capacity | 500 entries (in-memory) |
| Email cooldown | 45 seconds |
| Alert cooldown | 5 seconds |
| Archive retention | 7 days |

---

## 12. DEPLOYMENT

### 12.1 Local Development
```bash
# Terminal 1 — Backend
uv run uvicorn backend.main:app --host 127.0.0.1 --port 8080 --reload

# Terminal 2 — Frontend
pnpm --filter @workspace/company-ai run dev
```

### 12.2 Campus Deployment (with IP Cameras)
```bash
# Enable local stream access
ALLOW_LOCAL_STREAMS=true uv run uvicorn backend.main:app --host 0.0.0.0 --port 8080 --reload
```

### 12.3 System Requirements
- **Minimum**: 8 GB RAM, 4-core CPU, Python 3.11+, Node.js 24+
- **Recommended**: 16 GB RAM, GPU (NVIDIA), SSD storage
- **OS**: Windows, Linux, macOS

---

## 13. CONCLUSION

CrowdLens represents a comprehensive, production-quality implementation of an AI-powered campus surveillance system. It successfully integrates multiple cutting-edge technologies — deep learning object detection, real-time tracking, behavioural analysis, and modern web technologies — into a cohesive platform that addresses real-world campus security challenges.

The system demonstrates that effective surveillance automation is achievable with open-source tools and can run on commodity hardware without requiring expensive proprietary solutions. The modular architecture ensures easy extensibility for future enhancements like pose-based fight detection, weapon detection, and multi-camera support.

---

## 14. REFERENCES

1. Ultralytics YOLOv11 — https://docs.ultralytics.com/
2. SORT Algorithm — Bewley et al., "Simple Online and Realtime Tracking" (2016)
3. Kalman Filter — R.E. Kalman, "A New Approach to Linear Filtering" (1960)
4. FastAPI Documentation — https://fastapi.tiangolo.com/
5. React 19 — https://react.dev/
6. HuggingFace Fall Detection — https://huggingface.co/melihuzunoglu/human-fall-detection
7. ONNX Runtime — https://onnxruntime.ai/
8. Hungarian Algorithm — Kuhn (1955), Munkres (1957)
9. WebSocket Protocol — RFC 6455
10. Canvas 2D API — https://developer.mozilla.org/en-US/docs/Web/API/Canvas_API

---
*Report generated for CrowdLens Campus AI Monitor Project*
*Repository: NikhilGupta777/Gemini-Clone*
