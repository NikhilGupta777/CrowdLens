# CrowdLens — System Architecture Document

---

## 1. ARCHITECTURAL OVERVIEW

CrowdLens follows a **Client-Server Monorepo Architecture** with real-time bidirectional communication via WebSockets.

### 1.1 Architecture Pattern
- **Backend**: Asynchronous event-driven (FastAPI + asyncio)
- **Frontend**: Single Page Application (React SPA)
- **Communication**: WebSocket (real-time) + REST (configuration/management)
- **Database**: Embedded SQLite (no external DB server)
- **Monorepo**: pnpm workspaces managing both frontend and backend

### 1.2 Component Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              BROWSER CLIENT                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                      PRESENTATION LAYER                          │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐  │   │
│  │  │Dashboard │ │Alert Hist│ │ Settings │ │   AI Panel       │  │   │
│  │  │ Page     │ │  Page    │ │   Page   │ │(Reports/Chat/Nar)│  │   │
│  │  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────────┬─────────┘  │   │
│  └───────┼─────────────┼───────────┼──────────────────┼────────────┘   │
│          │             │           │                  │                 │
│  ┌───────┴─────────────┴───────────┴──────────────────┴────────────┐   │
│  │                       STATE LAYER                                │   │
│  │  ┌────────────────┐  ┌─────────────┐  ┌──────────────────────┐ │   │
│  │  │DetectionContext│  │ useSimulation│  │  useCamProcessor     │ │   │
│  │  │(React Context) │  │ (WebSocket)  │  │ (Frame Capture+Send) │ │   │
│  │  └────────────────┘  └─────────────┘  └──────────────────────┘ │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│          │                     │                     │                  │
│  ┌───────┴─────────────────────┴─────────────────────┴────────────┐    │
│  │                    TRANSPORT LAYER                               │    │
│  │         WebSocket /ws (receive)    WebSocket /ws/cam (send)      │    │
│  │         REST HTTP (config/upload)                                │    │
│  └──────────────────────────────┬──────────────────────────────────┘    │
└─────────────────────────────────┼───────────────────────────────────────┘
                                  │ Network
┌─────────────────────────────────┼───────────────────────────────────────┐
│                          BACKEND SERVER                                   │
├─────────────────────────────────┼───────────────────────────────────────┤
│                                 ▼                                        │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                      API LAYER (FastAPI)                          │   │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────────┐  ┌───────────────┐  │   │
│  │  │REST API │  │ WS /ws  │  │ WS /ws/cam  │  │  Middleware   │  │   │
│  │  │Endpoints│  │(Outbound)│  │  (Inbound)  │  │  (CORS)       │  │   │
│  │  └─────────┘  └─────────┘  └─────────────┘  └───────────────┘  │   │
│  └───────────────────────────────┬──────────────────────────────────┘   │
│                                  │                                       │
│  ┌───────────────────────────────┴──────────────────────────────────┐   │
│  │                    PROCESSING LAYER                               │   │
│  │                                                                   │   │
│  │  ┌─────────────────────┐  ┌──────────────────────────────────┐  │   │
│  │  │  Detection Engine   │  │       Tracking Engine             │  │   │
│  │  │  ┌───────────────┐  │  │  ┌────────────────────────────┐  │  │   │
│  │  │  │  YOLOv11m     │  │  │  │  SORT Tracker              │  │  │   │
│  │  │  │  (ONNX/PyTorch│  │  │  │  ┌───────────────────────┐ │  │  │   │
│  │  │  │   Multi-GPU/  │  │  │  │  │ KalmanBoxTracker (×N)  │ │  │  │   │
│  │  │  │   CPU fallback│  │  │  │  │ (7D state per target)  │ │  │  │   │
│  │  │  └───────────────┘  │  │  │  └───────────────────────┘ │  │  │   │
│  │  │  ┌───────────────┐  │  │  │  ┌───────────────────────┐ │  │  │   │
│  │  │  │ Fall Detector  │  │  │  │  │ Hungarian Algorithm   │ │  │  │   │
│  │  │  │ (HuggingFace) │  │  │  │  │ (scipy linear_sum)    │ │  │  │   │
│  │  │  └───────────────┘  │  │  │  └───────────────────────┘ │  │  │   │
│  │  └─────────────────────┘  │  └──────────────────────────────┘  │   │
│  │                                                                   │   │
│  │  ┌──────────────────────────────────────────────────────────────┐│   │
│  │  │                   Anomaly Detection Engine                    ││   │
│  │  │  ┌────────┐ ┌────────┐ ┌──────────┐ ┌──────┐ ┌──────────┐ ││   │
│  │  │  │Running │ │Overcrowd│ │Unattended│ │ Fall │ │  Fight   │ ││   │
│  │  │  │Detector│ │Detector │ │Object Det│ │ Det  │ │Heuristic │ ││   │
│  │  │  └────────┘ └────────┘ └──────────┘ └──────┘ └──────────┘ ││   │
│  │  │  ┌────────────────┐                                         ││   │
│  │  │  │Restricted Zone │                                         ││   │
│  │  │  │ (Digital Fence)│                                         ││   │
│  │  │  └────────────────┘                                         ││   │
│  │  └──────────────────────────────────────────────────────────────┘│   │
│  │                                                                   │   │
│  │  ┌──────────────────────────────────────────────────────────────┐│   │
│  │  │              Input Acquisition Layer                          ││   │
│  │  │  ┌──────────────┐ ┌────────────┐ ┌───────────────────────┐ ││   │
│  │  │  │Video Capture │ │ FFmpeg Pipe│ │  WebSocket Frame RX   │ ││   │
│  │  │  │(cv2.VideoCapt│ │(RTSP/HTTP) │ │  (Browser Webcam)     │ ││   │
│  │  │  └──────────────┘ └────────────┘ └───────────────────────┘ ││   │
│  │  └──────────────────────────────────────────────────────────────┘│   │
│  └───────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                       DATA LAYER                                   │  │
│  │  ┌────────────┐  ┌──────────────┐  ┌────────────┐  ┌──────────┐ │  │
│  │  │ SQLite DB  │  │ Alert Deque  │  │  Archive   │  │ Config   │ │  │
│  │  │ (WAL mode) │  │ (in-memory)  │  │ (JPEGs)    │  │ (state)  │ │  │
│  │  └────────────┘  └──────────────┘  └────────────┘  └──────────┘ │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                     NOTIFICATION LAYER                             │  │
│  │  ┌──────────────────┐  ┌─────────────────────────────────────┐   │  │
│  │  │ AWS SES (Email)  │  │  ThreadPoolExecutor (async workers) │   │  │
│  │  └──────────────────┘  └─────────────────────────────────────┘   │  │
│  └───────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 2. BACKEND ARCHITECTURE

### 2.1 Module Structure

```
backend/
├── main.py           # FastAPI app, all endpoints, processing loops
├── detector.py       # YOLOv11m loading, inference, baggage dedup
├── sort_tracker.py   # SORT tracker with Kalman filter
├── anomaly.py        # 6 anomaly detection algorithms
├── fall_detector.py  # Dedicated fall model (HuggingFace)
├── simulation.py     # Synthetic entity simulation engine
├── config.py         # All configurable constants/thresholds
├── database.py       # SQLite async wrapper
└── requirements.txt  # Python dependencies
```

### 2.2 Concurrency Model

```
┌──────────────────────────────────────────────────────────────┐
│                    asyncio Event Loop (main)                   │
│                                                              │
│  ┌────────────────┐  ┌────────────────┐  ┌──────────────┐  │
│  │ video_loop()   │  │ stream_loop()  │  │ webcam_loop()│  │
│  │ (async task)   │  │ (async task)   │  │ (async task) │  │
│  └───────┬────────┘  └───────┬────────┘  └──────┬───────┘  │
│          │                    │                   │           │
│          ▼                    ▼                   ▼           │
│  ┌─────────────────────────────────────────────────────────┐│
│  │        ThreadPoolExecutor (YOLO inference)               ││
│  │        loop.run_in_executor(None, detect_fn, frame)      ││
│  └─────────────────────────────────────────────────────────┘│
│                                                              │
│  ┌────────────────────┐  ┌────────────────────────────────┐│
│  │ _db_executor       │  │ _notify_executor               ││
│  │ (2 workers - DB)   │  │ (1 worker - email)             ││
│  └────────────────────┘  └────────────────────────────────┘│
└──────────────────────────────────────────────────────────────┘
```

### 2.3 Model Loading Strategy (detector.py)

```
Startup → Background Thread:
  1. Check CUDA availability
  2. Try ONNX export (one-time)
  3. Strategy cascade:
     ├── ONNX + GPU  ← fastest
     ├── ONNX + CPU  ← fast, portable
     ├── PyTorch + GPU
     └── PyTorch + CPU  ← always works
  4. Warm-up inference (640×640 zeros)
  5. Set _model_ready = True
```

### 2.4 Stream Processing Architecture

```
                FFmpeg Subprocess
                ┌─────────────┐
  RTSP/HTTP ──→ │ ffmpeg -i   │ ──→ stdout (raw BGR24 frames)
  Camera URL    │ -f rawvideo │         │
                │ -pix_fmt bgr│         ▼
                │ -vf scale,fps        Reader Thread
                └─────────────┘    ┌─────────────────┐
                                   │ Read FRAME_BYTES │
                                   │ Put to Queue(1) │ ← keeps only latest
                                   └────────┬────────┘
                                            │
                                            ▼
                                   async Processing Loop
                                   ┌─────────────────────┐
                                   │ queue.get()          │
                                   │ → detect(frame)      │
                                   │ → track(detections)  │
                                   │ → anomaly(tracks)    │
                                   │ → broadcast(payload) │
                                   └─────────────────────┘
```

---

## 3. FRONTEND ARCHITECTURE

### 3.1 Component Hierarchy

```
App
├── DetectionProvider (Context)
│   └── AppShell
│       ├── Layout (sidebar + header + threat level)
│       └── Router (wouter)
│           ├── Dashboard
│           │   ├── SimulationCanvas (Canvas 2D rendering)
│           │   ├── AlertsFeed (live anomaly cards)
│           │   ├── StatsCards (metric pills)
│           │   ├── Video Upload Panel
│           │   ├── Stream Panel
│           │   └── Webcam Panel
│           ├── AlertHistory
│           │   ├── Summary Cards
│           │   ├── Bar Chart (Recharts)
│           │   ├── Filter/Search
│           │   └── Data Table
│           ├── AIPanel
│           │   ├── NarratorTab
│           │   ├── ReportsTab
│           │   └── ChatTab
│           └── Settings
│               ├── Overlay Style Selector
│               ├── Detection Sliders
│               └── Toggle Cards
```

### 3.2 Real-Time Data Flow

```
WebSocket /ws ──→ useSimulation hook ──→ DetectionContext ──→ All pages

Frame Data (FrameData):
{
  tracks: Track[],        // All tracked entities with bbox
  anomalies: Anomaly[],   // Active anomalies
  stats: SimStats,        // person_count, fps, uptime
  timestamp: number,      // Unix timestamp
  mode: string,           // idle/video/webcam/stream
  frame_jpeg?: string     // Base64 JPEG preview
}
```

### 3.3 Canvas Rendering Pipeline (SimulationCanvas)

```
requestAnimationFrame loop (60fps):
  1. Clear canvas (1280×720)
  2. Draw background:
     - Live webcam video (drawImage from <video>)
     - OR backend frame (decode base64 JPEG → drawImage)
     - OR dark gradient (idle/loading)
  3. Draw restricted zones (dashed rectangles)
  4. Apply bounding box smoothing (exponential interpolation)
  5. Resolve overlay style (auto picks based on crowd count)
  6. Draw tracks in selected style:
     - corners: L-shaped corner brackets + labels
     - dots: Glowing dots at feet + ID chips
     - heatmap: Radial gradient density overlay
     - chips: Floating ID labels only
  7. Draw anomaly overlays (pulsing circles, dashed boxes, warnings)
  8. Draw HUD (timestamp, mode badge, LIVE indicator)
```

### 3.4 Webcam Frame Pipeline

```
Browser Camera → <video> element → useCamProcessor hook:
  setInterval(200ms = 5fps):
    1. Check WebSocket open + not backed up
    2. drawImage(video → canvas 640×360)
    3. canvas.toBlob(JPEG, quality=0.60)
    4. blob → ArrayBuffer → ws.send()
    
  → /ws/cam WebSocket → Backend queue → webcam_processing_loop
```

---

## 4. TRACKING ALGORITHM DETAIL

### 4.1 SORT Algorithm Flow

```
Frame N detections ──→ SORT.update()
                        │
                        ├── 1. Predict: each tracker.predict()
                        │       (Kalman state → predicted bbox)
                        │
                        ├── 2. Associate: Hungarian algorithm
                        │       Cost matrix: 1 - IoU (persons)
                        │                    center_distance (bags)
                        │       → matched, unmatched_dets, unmatched_trks
                        │
                        ├── 3. Update matched trackers
                        │       tracker.update(detection bbox)
                        │
                        ├── 4. Create new trackers for unmatched detections
                        │
                        ├── 5. Collect active tracks
                        │       (recently detected OR within hold window)
                        │
                        └── 6. Prune dead trackers
                                (time_since_update > hold limit)
```

### 4.2 Kalman Filter State

```
State vector x = [cx, cy, s, r, v_cx, v_cy, v_s]ᵀ
  cx, cy  = box center
  s       = box area
  r       = aspect ratio (width/height)
  v_*     = velocities

Measurement z = [cx, cy, s, r]ᵀ

Transition F: position += velocity × Δt
Measurement H: identity on first 4 states
```

---

## 5. SECURITY CONSIDERATIONS

### 5.1 SSRF Protection
- Stream URLs validated against private IP ranges
- ALLOW_LOCAL_STREAMS flag for campus deployment
- Blocked: loopback, link-local, multicast addresses

### 5.2 Input Validation
- WebSocket message size capped at 1 MB
- Video upload capped at 500 MB
- File extension whitelist for uploads
- Path traversal guard on archive image serving

### 5.3 Resource Protection
- Alert cooldown prevents flooding (5s per track+type)
- Email cooldown prevents spam (45s per type+source)
- Frame queue bounded (size=4, drop oldest)
- WebSocket backpressure detection (skip frames when buffered)
- Archive cleanup (7-day retention)
- Thread pool bounded (2 DB workers, 1 notify worker)

---

## 6. SCALABILITY NOTES

### Current Design (Single-Server)
- Single asyncio event loop
- One processing source at a time
- SQLite (single-writer)
- In-memory alert deque (500 entries)

### Future Scaling Path
- Multiple workers (Gunicorn + uvicorn)
- Redis for pub/sub broadcast
- PostgreSQL for multi-writer
- Message queue (RabbitMQ/Kafka) for processing pipeline
- Kubernetes for horizontal scaling
- GPU inference service (TensorRT/Triton)

---

*Architecture Document — CrowdLens Campus AI Monitor*
